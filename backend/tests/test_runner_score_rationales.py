"""Runner persistence tests for score rationales."""

import os

os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-runner"

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import (
    BenchmarkRun,
    Judgment,
    Generation,
    ModelPreset,
    Question,
    JudgeMode,
    ProviderType,
    RunStatus,
    TaskStatus,
    TemperatureMode,
)
from app.core.runner import BenchmarkRunner


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _make_preset(db, preset_id: int, name: str = "Model", provider: ProviderType = ProviderType.openai):
    preset = ModelPreset(
        id=preset_id,
        name=name,
        provider=provider,
        base_url="https://api.openai.com/v1",
        model_id=f"model-{preset_id}",
    )
    db.add(preset)
    return preset


def _make_run(db, judge_mode: JudgeMode) -> BenchmarkRun:
    run = BenchmarkRun(
        name="Runner score rationale test",
        status=RunStatus.running,
        judge_mode=judge_mode,
        criteria=[{"name": "Accuracy", "description": "test", "weight": 1}],
        model_ids=[11, 22, 33],
        judge_ids=[99],
        temperature_mode=TemperatureMode.normalized,
    )
    db.add(run)
    db.flush()
    return run


@pytest.mark.asyncio
async def test_comparison_success_stores_score_rationales(monkeypatch):
    db = TestSession()
    _make_preset(db, 11, "Alpha")
    _make_preset(db, 22, "Beta")
    _make_preset(db, 33, "Gamma")
    judge_preset = _make_preset(db, 99, "Judge")
    run = _make_run(db, JudgeMode.comparison)
    question = Question(benchmark_id=run.id, order=0, system_prompt="sys", user_prompt="usr")
    db.add(question)
    db.flush()
    judgment = Judgment(
        question_id=question.id,
        judge_preset_id=judge_preset.id,
        status=TaskStatus.pending,
    )
    db.add(judgment)
    db.commit()

    mock_manager = MagicMock()
    mock_manager.send_judgment = AsyncMock()
    monkeypatch.setattr("app.core.runner.manager", mock_manager)
    monkeypatch.setattr("app.db.database.SessionLocal", TestSession)

    comparison_result = {
        "success": True,
        "blind_mapping": {"A": 11, "B": 22, "C": 33},
        "presentation_mapping": {"1": "A", "2": "B", "3": "C"},
        "rankings": ["A", "B", "C"],
        "scores": {11: {"Accuracy": 9}, 22: {"Accuracy": 8}, 33: {"Accuracy": 7}},
        "comments": {11: [], 22: [], 33: []},
        "score_rationales": {11: "alpha rationale", 22: "beta rationale", 33: "gamma rationale"},
        "reasoning": "A wins",
        "temperature": 0.3,
        "tokens": 123,
        "latency_ms": 456,
    }

    with patch("app.core.runner.judge_comparison", new_callable=AsyncMock, return_value=comparison_result):
        runner = BenchmarkRunner(db, run.id)
        await runner._judge_comparison_with_retry(
            judgment.id,
            judge_preset,
            question.id,
            "sys",
            "usr",
            {11: "alpha", 22: "beta", 33: "gamma"},
            run.criteria,
            "Judge",
        )

    db.expire_all()
    stored = db.query(Judgment).filter(Judgment.id == judgment.id).first()
    assert stored.score_rationales == {"11": "alpha rationale", "22": "beta rationale", "33": "gamma rationale"}
    db.close()


@pytest.mark.asyncio
async def test_separate_success_wraps_score_rationale(monkeypatch):
    db = TestSession()
    _make_preset(db, 11, "Alpha")
    judge_preset = _make_preset(db, 99, "Judge")
    run = _make_run(db, JudgeMode.separate)
    question = Question(benchmark_id=run.id, order=0, system_prompt="sys", user_prompt="usr")
    db.add(question)
    db.flush()
    generation = Generation(
        question_id=question.id,
        model_preset_id=11,
        status=TaskStatus.success,
        content="alpha answer",
    )
    db.add(generation)
    db.flush()
    judgment = Judgment(
        question_id=question.id,
        judge_preset_id=judge_preset.id,
        generation_id=generation.id,
        status=TaskStatus.pending,
    )
    db.add(judgment)
    db.commit()

    mock_manager = MagicMock()
    mock_manager.send_judgment = AsyncMock()
    monkeypatch.setattr("app.core.runner.manager", mock_manager)
    monkeypatch.setattr("app.db.database.SessionLocal", TestSession)

    separate_result = {
        "success": True,
        "scores": {"Accuracy": 9},
        "comments": [{"text": "good", "sentiment": "positive"}],
        "score_rationale": "Concise, accurate, and complete.",
        "reasoning": "Strong answer",
        "temperature": 0.2,
        "tokens": 77,
        "latency_ms": 321,
    }

    with patch("app.core.runner.judge_separate", new_callable=AsyncMock, return_value=separate_result):
        runner = BenchmarkRunner(db, run.id)
        await runner._judge_separate_with_retry(
            judgment.id,
            judge_preset,
            question.id,
            "sys",
            "usr",
            "alpha answer",
            11,
            run.criteria,
            "Judge",
        )

    db.expire_all()
    stored = db.query(Judgment).filter(Judgment.id == judgment.id).first()
    assert stored.score_rationales == {"11": "Concise, accurate, and complete."}
    db.close()


@pytest.mark.asyncio
async def test_comparison_retry_replaces_existing_score_rationales(monkeypatch):
    db = TestSession()
    _make_preset(db, 11, "Alpha")
    _make_preset(db, 22, "Beta")
    _make_preset(db, 33, "Gamma")
    judge_preset = _make_preset(db, 99, "Judge")
    run = _make_run(db, JudgeMode.comparison)
    question = Question(benchmark_id=run.id, order=0, system_prompt="sys", user_prompt="usr")
    db.add(question)
    db.flush()
    judgment = Judgment(
        question_id=question.id,
        judge_preset_id=judge_preset.id,
        status=TaskStatus.pending,
        score_rationales={999: "old rationale"},
    )
    db.add(judgment)
    db.commit()

    mock_manager = MagicMock()
    mock_manager.send_judgment = AsyncMock()
    monkeypatch.setattr("app.core.runner.manager", mock_manager)
    monkeypatch.setattr("app.db.database.SessionLocal", TestSession)

    comparison_result = {
        "success": True,
        "blind_mapping": {"A": 11, "B": 22, "C": 33},
        "presentation_mapping": {"1": "A", "2": "B", "3": "C"},
        "rankings": ["A", "B", "C"],
        "scores": {11: {"Accuracy": 9}, 22: {"Accuracy": 8}, 33: {"Accuracy": 7}},
        "comments": {11: [], 22: [], 33: []},
        "score_rationales": {11: "new alpha", 22: "new beta", 33: "new gamma"},
        "reasoning": "A wins",
        "temperature": 0.3,
        "tokens": 123,
        "latency_ms": 456,
    }

    with patch("app.core.runner.judge_comparison", new_callable=AsyncMock, return_value=comparison_result):
        runner = BenchmarkRunner(db, run.id)
        await runner._judge_comparison_with_retry(
            judgment.id,
            judge_preset,
            question.id,
            "sys",
            "usr",
            {11: "alpha", 22: "beta", 33: "gamma"},
            run.criteria,
            "Judge",
        )

    db.expire_all()
    stored = db.query(Judgment).filter(Judgment.id == judgment.id).first()
    assert stored.score_rationales == {"11": "new alpha", "22": "new beta", "33": "new gamma"}
    assert "999" not in stored.score_rationales
    db.close()
