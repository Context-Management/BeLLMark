from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import (
    BenchmarkRun,
    Generation,
    Judgment,
    JudgeMode,
    ModelPreset,
    ProviderType,
    Question,
    RunStatus,
    TaskStatus,
)
from scripts.backfill_score_rationales import BackfillStats, backfill_score_rationales, main_async


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def create_model_preset(session, preset_id: int, name: str, provider=ProviderType.anthropic) -> ModelPreset:
    preset = ModelPreset(
        id=preset_id,
        name=name,
        provider=provider,
        base_url="https://api.example.com/v1/chat/completions",
        model_id=f"model-{preset_id}",
        price_input=0.0,
        price_output=0.0,
    )
    session.add(preset)
    session.commit()
    return preset


def create_run(session, *, model_ids: list[int], judge_ids: list[int], judge_mode: JudgeMode) -> BenchmarkRun:
    run = BenchmarkRun(
        name="Backfill Test Run",
        model_ids=model_ids,
        judge_ids=judge_ids,
        judge_mode=judge_mode,
        criteria=[{"name": "Quality", "description": "Quality", "weight": 1.0}],
        status=RunStatus.completed,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_context_tokens=0,
    )
    session.add(run)
    session.commit()
    return run


def create_question(session, run_id: int, order: int, *, expected_answer: str | None = None) -> Question:
    question = Question(
        benchmark_id=run_id,
        order=order,
        system_prompt="System prompt",
        user_prompt=f"User prompt {order}",
        expected_answer=expected_answer,
        context_tokens=0,
    )
    session.add(question)
    session.commit()
    return question


def create_generation(session, question_id: int, model_preset_id: int, *, content: str = "Answer") -> Generation:
    generation = Generation(
        question_id=question_id,
        model_preset_id=model_preset_id,
        content=content,
        tokens=25,
        raw_chars=len(content),
        answer_chars=len(content),
        latency_ms=1500,
        status=TaskStatus.success,
        retries=0,
    )
    session.add(generation)
    session.commit()
    return generation


def create_comparison_judgment(
    session,
    *,
    question_id: int,
    judge_preset_id: int,
    blind_mapping: dict[str, int],
    rankings: list[str],
    scores: dict,
    comments: dict,
    score_rationales: dict | None,
) -> Judgment:
    judgment = Judgment(
        question_id=question_id,
        judge_preset_id=judge_preset_id,
        blind_mapping=blind_mapping,
        rankings=rankings,
        scores=scores,
        reasoning="Comparison reasoning",
        comments=comments,
        score_rationales=score_rationales,
        latency_ms=2000,
        tokens=100,
        status=TaskStatus.success,
        retries=0,
    )
    session.add(judgment)
    session.commit()
    return judgment


def create_separate_judgment(
    session,
    *,
    question_id: int,
    generation_id: int,
    judge_preset_id: int,
    scores: dict,
    comments: list[dict],
    score_rationales: dict | None,
) -> Judgment:
    judgment = Judgment(
        question_id=question_id,
        judge_preset_id=judge_preset_id,
        generation_id=generation_id,
        scores=scores,
        reasoning="Separate reasoning",
        comments=comments,
        score_rationales=score_rationales,
        latency_ms=1700,
        tokens=90,
        status=TaskStatus.success,
        retries=0,
    )
    session.add(judgment)
    session.commit()
    return judgment


@pytest.mark.asyncio
async def test_backfill_comparison_fills_missing_only_and_is_idempotent(session, monkeypatch):
    model_a = create_model_preset(session, 11, "Model A")
    model_b = create_model_preset(session, 22, "Model B")
    judge = create_model_preset(session, 99, "Judge")
    run = create_run(session, model_ids=[model_a.id, model_b.id], judge_ids=[judge.id], judge_mode=JudgeMode.comparison)
    question = create_question(session, run.id, 1)
    create_generation(session, question.id, model_a.id, content="Answer A")
    create_generation(session, question.id, model_b.id, content="Answer B")
    judgment = create_comparison_judgment(
        session,
        question_id=question.id,
        judge_preset_id=judge.id,
        blind_mapping={"A": model_a.id, "B": model_b.id},
        rankings=["A", "B"],
        scores={
            str(model_a.id): {"Quality": 9.0},
            str(model_b.id): {"Quality": 6.0},
        },
        comments={
            str(model_a.id): [{"text": "Strong answer", "sentiment": "positive"}],
            str(model_b.id): [{"text": "Weaker answer", "sentiment": "negative"}],
        },
        score_rationales={str(model_a.id): "Existing rationale."},
    )

    calls = []

    async def fake_generate(*args, **kwargs):
        calls.append((args, kwargs))
        return {"success": True, "content": "Generated rationale for model B."}

    monkeypatch.setattr("scripts.backfill_score_rationales.generate", fake_generate)

    stats = await backfill_score_rationales(session, batch_size=10)
    assert stats.judgments_seen == 1
    assert stats.judgments_updated == 1
    assert stats.entries_written == 1
    assert len(calls) == 1

    session.expire_all()
    stored = session.get(Judgment, judgment.id)
    assert stored.score_rationales == {
        "11": "Existing rationale.",
        "22": "Generated rationale for model B.",
    }

    async def fail_generate(*args, **kwargs):
        raise AssertionError("generate should not be called on rerun once rationales are filled")

    monkeypatch.setattr("scripts.backfill_score_rationales.generate", fail_generate)
    stats_rerun = await backfill_score_rationales(session, batch_size=10)
    assert stats_rerun.entries_written == 0
    assert stats_rerun.entries_skipped == 1
    session.expire_all()
    stored_rerun = session.get(Judgment, judgment.id)
    assert stored_rerun.score_rationales == stored.score_rationales


@pytest.mark.asyncio
async def test_backfill_treats_blank_string_rationales_as_missing(session, monkeypatch):
    model = create_model_preset(session, 55, "Blank Model")
    judge = create_model_preset(session, 96, "Judge")
    run = create_run(session, model_ids=[model.id], judge_ids=[judge.id], judge_mode=JudgeMode.separate)
    question = create_question(session, run.id, 1)
    generation = create_generation(session, question.id, model.id, content="Blank answer")
    judgment = create_separate_judgment(
        session,
        question_id=question.id,
        generation_id=generation.id,
        judge_preset_id=judge.id,
        scores={"Quality": 6.0},
        comments=[{"text": "Needs rationale", "sentiment": "negative"}],
        score_rationales={"55": "   "},
    )

    calls = []

    async def fake_generate(*args, **kwargs):
        calls.append((args, kwargs))
        return {"success": True, "content": "Blank rationale filled."}

    monkeypatch.setattr("scripts.backfill_score_rationales.generate", fake_generate)

    stats = await backfill_score_rationales(session, batch_size=10)
    assert stats.judgments_seen == 1
    assert stats.entries_written == 1
    assert len(calls) == 1

    session.expire_all()
    stored = session.get(Judgment, judgment.id)
    assert stored.score_rationales == {"55": "Blank rationale filled."}


@pytest.mark.asyncio
async def test_backfill_separate_fills_single_entry_mapping(session, monkeypatch):
    model = create_model_preset(session, 31, "Solo Model")
    judge = create_model_preset(session, 98, "Judge")
    run = create_run(session, model_ids=[model.id], judge_ids=[judge.id], judge_mode=JudgeMode.separate)
    question = create_question(session, run.id, 1)
    generation = create_generation(session, question.id, model.id, content="A focused answer")
    judgment = create_separate_judgment(
        session,
        question_id=question.id,
        generation_id=generation.id,
        judge_preset_id=judge.id,
        scores={"Quality": 8.0},
        comments=[{"text": "Focused and clear", "sentiment": "positive"}],
        score_rationales=None,
    )

    async def fake_generate(*args, **kwargs):
        return {"success": True, "content": "Concise rationale."}

    monkeypatch.setattr("scripts.backfill_score_rationales.generate", fake_generate)

    stats = await backfill_score_rationales(session, batch_size=10)
    assert stats.judgments_seen == 1
    assert stats.entries_written == 1

    session.expire_all()
    stored = session.get(Judgment, judgment.id)
    assert stored.score_rationales == {"31": "Concise rationale."}


@pytest.mark.asyncio
async def test_backfill_preserves_existing_separate_rationale_and_skips_rerun(session, monkeypatch):
    model = create_model_preset(session, 41, "Existing Model")
    judge = create_model_preset(session, 97, "Judge")
    run = create_run(session, model_ids=[model.id], judge_ids=[judge.id], judge_mode=JudgeMode.separate)
    question = create_question(session, run.id, 1)
    generation = create_generation(session, question.id, model.id, content="Existing answer")
    judgment = create_separate_judgment(
        session,
        question_id=question.id,
        generation_id=generation.id,
        judge_preset_id=judge.id,
        scores={"Quality": 7.0},
        comments=[{"text": "Already good", "sentiment": "positive"}],
        score_rationales={"41": "Already there."},
    )

    async def fail_generate(*args, **kwargs):
        raise AssertionError("generate should not be called when rationale already exists")

    monkeypatch.setattr("scripts.backfill_score_rationales.generate", fail_generate)

    stats = await backfill_score_rationales(session, batch_size=10)
    assert stats.entries_written == 0
    assert stats.entries_skipped == 1

    session.expire_all()
    stored = session.get(Judgment, judgment.id)
    assert stored.score_rationales == {"41": "Already there."}

    stats_rerun = await backfill_score_rationales(session, batch_size=10)
    assert stats_rerun.entries_written == 0
    assert stats_rerun.entries_skipped == 1
    session.expire_all()
    stored_rerun = session.get(Judgment, judgment.id)
    assert stored_rerun.score_rationales == {"41": "Already there."}


@pytest.mark.asyncio
async def test_main_async_returns_non_zero_when_generation_failures_occur(monkeypatch):
    class FakeDB:
        def close(self):
            self.closed = True

    fake_db = FakeDB()

    async def fake_backfill(*args, **kwargs):
        return BackfillStats(judgments_seen=2, judgments_updated=1, entries_written=1, entries_skipped=1, failures=2)

    monkeypatch.setattr("scripts.backfill_score_rationales.SessionLocal", lambda: fake_db)
    monkeypatch.setattr("scripts.backfill_score_rationales.backfill_score_rationales", fake_backfill)

    class Args:
        batch_size = 10
        limit = None
        temperature = 0.2
        dry_run = False

    exit_code = await main_async(Args())
    assert exit_code == 1
    assert getattr(fake_db, "closed", False) is True
