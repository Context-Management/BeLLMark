"""Tests for the overnight suite autoresearch loop."""

import asyncio
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import (
    BenchmarkRun,
    JudgeMode,
    Judgment,
    ModelPreset,
    PromptSuite,
    PromptSuiteItem,
    ProviderType,
    Question,
    ReasoningLevel,
    RunStatus,
    TaskStatus,
    TemperatureMode,
)

from app.core.autoresearch import (
    ExperimentDecision,
    QuestionEvaluation,
    SuiteAutoresearchConfig,
    SuiteAutoresearchService,
    decide_experiment,
)
from scripts.autoresearch_suite import build_parser


def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture()
def session():
    engine = _make_engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def _config(output_dir: Path | None = None, max_iterations: int = 3) -> SuiteAutoresearchConfig:
    return SuiteAutoresearchConfig(
        suite_id=None,
        subject_model_ids=[18, 144, 143, 116],
        judge_model_ids=[120, 49],
        editor_model_id=120,
        max_iterations=max_iterations,
        output_dir=output_dir or Path("/tmp/autoresearch-test"),
        dry_run=True,
    )


def _make_model(
    db,
    preset_id: int,
    name: str,
    provider: ProviderType,
    model_id: str,
    *,
    reasoning: bool = True,
):
    preset = ModelPreset(
        id=preset_id,
        name=name,
        provider=provider,
        base_url=f"https://example.com/{preset_id}",
        model_id=model_id,
        is_reasoning=1 if reasoning else 0,
        reasoning_level=ReasoningLevel.high if reasoning else None,
    )
    db.add(preset)
    return preset


def _seed_panel(db):
    _make_model(db, 18, "Claude Haiku 4.5 [Reasoning (high)]", ProviderType.anthropic, "claude-haiku-4-5-20251001")
    _make_model(db, 144, "GPT-5.4-nano [Reasoning (high)]", ProviderType.openai, "gpt-5.4-nano")
    _make_model(db, 143, "Grok 4.20-0309-reasoning [Reasoning]", ProviderType.grok, "grok-4.20-0309-reasoning")
    _make_model(db, 116, "Gemini 3.1 Flash Lite Preview [Thinking (high)]", ProviderType.google, "gemini-3.1-flash-lite-preview")
    _make_model(db, 120, "GPT-5.4-mini [Reasoning (high)]", ProviderType.openai, "gpt-5.4-mini")
    _make_model(db, 49, "Kimi K2.5 [Reasoning]", ProviderType.kimi, "kimi-k2.5")


def _seed_suite(db, suite_id: int = 10, item_count: int = 25):
    suite = PromptSuite(
        id=suite_id,
        name="Analytical Reasoning & Multi-Step Problem Solving",
        description="Seed suite",
        default_criteria=[
            {"name": "Reasoning Validity", "description": "Logic", "weight": 2.0},
            {"name": "Accuracy", "description": "Correctness", "weight": 1.0},
        ],
    )
    db.add(suite)
    for idx in range(item_count):
        db.add(
            PromptSuiteItem(
                suite_id=suite_id,
                order=idx,
                system_prompt=f"System {idx}",
                user_prompt=f"Question {idx}",
                expected_answer=f"Answer {idx}",
                category="reasoning",
                difficulty="medium",
                criteria=[{"name": "Reasoning Validity", "description": "Logic", "weight": 1.0}],
            )
        )
    return suite


def _seed_completed_run(db, suite_id: int, quality_by_order: dict[int, tuple[float, float, bool]], *, name: str):
    run = BenchmarkRun(
        name=name,
        status=RunStatus.completed,
        judge_mode=JudgeMode.comparison,
        criteria=[
            {"name": "Reasoning Validity", "description": "Logic", "weight": 2.0},
            {"name": "Accuracy", "description": "Correctness", "weight": 1.0},
        ],
        model_ids=[18, 144, 143, 116],
        judge_ids=[120, 49],
        temperature_mode=TemperatureMode.normalized,
        source_suite_id=suite_id,
    )
    db.add(run)
    db.flush()

    for order in range(25):
        discrimination, stability, agree = quality_by_order.get(order, (0.7, 0.9, True))
        question = Question(
            benchmark_id=run.id,
            order=order,
            system_prompt=f"System {order}",
            user_prompt=f"Prompt {order}",
            expected_answer=f"Expected {order}",
        )
        db.add(question)
        db.flush()

        # Build weighted score patterns that encode the requested quality.
        if discrimination < 0.3:
            judge_one = {"18": {"Reasoning Validity": 5.2, "Accuracy": 5.0}, "144": {"Reasoning Validity": 5.4, "Accuracy": 5.2}, "143": {"Reasoning Validity": 5.0, "Accuracy": 4.9}, "116": {"Reasoning Validity": 5.1, "Accuracy": 5.0}}
            judge_two = {"18": {"Reasoning Validity": 5.0, "Accuracy": 4.8}, "144": {"Reasoning Validity": 5.1, "Accuracy": 5.0}, "143": {"Reasoning Validity": 5.3, "Accuracy": 5.1}, "116": {"Reasoning Validity": 5.2, "Accuracy": 4.9}}
        else:
            judge_one = {"18": {"Reasoning Validity": 8.8, "Accuracy": 8.5}, "144": {"Reasoning Validity": 7.2, "Accuracy": 7.0}, "143": {"Reasoning Validity": 5.4, "Accuracy": 5.0}, "116": {"Reasoning Validity": 4.6, "Accuracy": 4.4}}
            judge_two = {"18": {"Reasoning Validity": 8.5, "Accuracy": 8.4}, "144": {"Reasoning Validity": 7.0, "Accuracy": 7.1}, "143": {"Reasoning Validity": 5.6, "Accuracy": 5.2}, "116": {"Reasoning Validity": 4.8, "Accuracy": 4.5}}

        rankings_one = ["A", "B", "C", "D"]
        rankings_two = ["A", "B", "C", "D"] if agree else ["C", "B", "A", "D"]
        blind_mapping = {"A": 18, "B": 144, "C": 143, "D": 116}

        db.add(
            Judgment(
                question_id=question.id,
                judge_preset_id=120,
                blind_mapping=blind_mapping,
                rankings=rankings_one,
                scores=judge_one,
                status=TaskStatus.success,
            )
        )
        db.add(
            Judgment(
                question_id=question.id,
                judge_preset_id=49,
                blind_mapping=blind_mapping,
                rankings=rankings_two,
                scores=judge_two if stability > 0.5 else judge_one,
                status=TaskStatus.success,
            )
        )

    db.commit()
    return run


def test_selects_most_used_suite_from_completed_history(session):
    _seed_panel(session)
    _seed_suite(session, suite_id=10)
    _seed_suite(session, suite_id=11)
    for idx in range(3):
        _seed_completed_run(session, 10, {24: (0.1, 0.4, False)}, name=f"Suite 10 run {idx}")
    _seed_completed_run(session, 11, {}, name="Suite 11 run")

    service = SuiteAutoresearchService(session=session, config=_config())
    suite_id = service.select_baseline_suite_id()

    assert suite_id == 10


def test_builds_question_baseline_scores_from_completed_runs(session, tmp_path):
    _seed_panel(session)
    _seed_suite(session, suite_id=10)
    weak = {24: (0.1, 0.4, False)}
    _seed_completed_run(session, 10, weak, name="run-1")
    _seed_completed_run(session, 10, weak, name="run-2")

    service = SuiteAutoresearchService(session=session, config=_config(output_dir=tmp_path))
    summary = service.build_suite_baseline(suite_id=10)

    assert summary.question_count == 25
    assert summary.completed_run_count == 2
    assert summary.question_rankings[0].question_order == 24
    assert summary.question_rankings[0].weakness_score > summary.question_rankings[-1].weakness_score


def test_experiment_decision_prefers_candidate_only_when_quality_margin_is_positive():
    incumbent = QuestionEvaluation(
        quality=0.42,
        discrimination=0.39,
        stability=0.71,
        judge_agreement=0.50,
        winner_entropy=0.60,
        sample_count=2,
        details={},
    )
    candidate = QuestionEvaluation(
        quality=0.51,
        discrimination=0.47,
        stability=0.74,
        judge_agreement=1.0,
        winner_entropy=0.30,
        sample_count=2,
        details={},
    )

    decision = decide_experiment(incumbent=incumbent, candidate=candidate)

    assert isinstance(decision, ExperimentDecision)
    assert decision.action == "keep"
    assert decision.quality_delta > 0


def test_writes_start_work_result_artifacts(session, tmp_path):
    _seed_panel(session)
    _seed_suite(session, suite_id=10)
    _seed_completed_run(session, 10, {24: (0.1, 0.4, False)}, name="run-1")

    service = SuiteAutoresearchService(session=session, config=_config(output_dir=tmp_path))
    artifacts = service.initialize_artifacts(suite_id=10)

    assert (artifacts.start_dir / "baseline-suite.json").exists()
    assert (artifacts.start_dir / "baseline-summary.json").exists()
    assert (artifacts.work_dir / "experiments.tsv").exists()
    assert artifacts.result_dir.exists()


def test_merge_item_change_parses_stringified_question_payload(session):
    _seed_panel(session)
    _seed_suite(session, suite_id=10)
    service = SuiteAutoresearchService(session=session, config=_config())

    incumbent = {
        "order": 24,
        "system_prompt": "Old system",
        "user_prompt": "Old prompt",
        "expected_answer": "Old answer",
    }
    candidate_change = {
        "change_type": "refine",
        "change_description": "Tightened wording",
        "question": json.dumps(
            {
                "system_prompt": "New system",
                "user_prompt": "New prompt",
                "expected_answer": "New answer",
            }
        ),
    }

    merged = service._merge_item_change(incumbent, candidate_change)

    assert merged["system_prompt"] == "New system"
    assert merged["user_prompt"] == "New prompt"
    assert merged["expected_answer"] == "New answer"


@pytest.mark.asyncio
async def test_run_loop_stops_after_iteration_budget_and_returns_final_suite(session, tmp_path, monkeypatch):
    _seed_panel(session)
    _seed_suite(session, suite_id=10)
    _seed_completed_run(session, 10, {24: (0.1, 0.4, False)}, name="run-1")

    service = SuiteAutoresearchService(session=session, config=_config(output_dir=tmp_path, max_iterations=3))

    async def fake_candidate(*args, **kwargs):
        return {
            "change_type": "refine",
            "question": {
                "system_prompt": "Improved system",
                "user_prompt": "Improved prompt",
                "expected_answer": "Improved answer",
            },
            "change_description": "Tightened constraints",
        }

    async def fake_evaluate(*args, **kwargs):
        return (
            QuestionEvaluation(quality=0.40, discrimination=0.30, stability=0.55, judge_agreement=0.5, winner_entropy=0.7, sample_count=2, details={}),
            QuestionEvaluation(quality=0.55, discrimination=0.48, stability=0.72, judge_agreement=1.0, winner_entropy=0.2, sample_count=2, details={}),
        )

    monkeypatch.setattr(service, "_propose_candidate_change", fake_candidate)
    monkeypatch.setattr(service, "_evaluate_experiment", fake_evaluate)

    result = await service.run()

    assert result.iterations_completed == 3
    assert result.final_suite_path.exists()
    payload = json.loads(result.final_suite_path.read_text())
    assert payload["item_count"] >= 25


def test_cli_parses_default_panel_and_suite_override(tmp_path):
    parser = build_parser()

    args = parser.parse_args([
        "--suite-id", "10", "--max-iterations", "5", "--output-dir", str(tmp_path),
        "--subject-model-ids", "1,2,3", "--judge-model-ids", "4,5", "--editor-model-id", "6",
    ])

    assert args.suite_id == 10
    assert args.max_iterations == 5
    assert args.subject_model_ids == "1,2,3"
    assert args.judge_model_ids == "4,5"
    assert args.editor_model_id == 6
