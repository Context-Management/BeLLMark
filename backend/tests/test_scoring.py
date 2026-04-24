"""
Tests for weighted scoring calculation.

Verifies that multi-judge scoring correctly:
1. Averages scores per criterion across judges first
2. Then applies criterion weights
3. Maintains consistency between aggregate and per-question scores
"""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-for-scoring-tests"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timezone

from app.db.database import Base
from app.db.models import (
    BenchmarkRun, Question, Generation, Judgment, ModelPreset,
    TaskStatus, JudgeMode, ProviderType, RunStatus
)
from app.core.exports.common import prepare_export_data


@pytest.fixture
def db_session():
    """Create in-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


def create_model_preset(session, name: str, preset_id: int) -> ModelPreset:
    """Helper to create a model preset."""
    preset = ModelPreset(
        id=preset_id,
        name=name,
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id=f"model-{name.lower()}",
        price_input=0.0,
        price_output=0.0,
    )
    session.add(preset)
    session.commit()
    return preset


def create_benchmark_run(
    session,
    name: str,
    model_ids: list[int],
    judge_ids: list[int],
    criteria: list[dict],
) -> BenchmarkRun:
    """Helper to create a benchmark run."""
    run = BenchmarkRun(
        name=name,
        model_ids=model_ids,
        judge_ids=judge_ids,
        judge_mode=JudgeMode.comparison,
        criteria=criteria,
        status=RunStatus.completed,
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        total_context_tokens=0,
    )
    session.add(run)
    session.commit()
    return run


def create_question(session, benchmark_id: int, order: int) -> Question:
    """Helper to create a question."""
    q = Question(
        benchmark_id=benchmark_id,
        order=order,
        system_prompt="Test system prompt",
        user_prompt=f"Test question {order}",
        context_tokens=100,
    )
    session.add(q)
    session.commit()
    return q


def create_generation(
    session,
    question_id: int,
    model_preset_id: int,
    content: str = "Test response",
) -> Generation:
    """Helper to create a generation."""
    gen = Generation(
        question_id=question_id,
        model_preset_id=model_preset_id,
        content=content,
        tokens=50,
        raw_chars=len(content),
        answer_chars=len(content),
        latency_ms=1000,
        status=TaskStatus.success,
        retries=0,
    )
    session.add(gen)
    session.commit()
    return gen


def create_judgment(
    session,
    question_id: int,
    judge_preset_id: int,
    scores: dict,
    blind_mapping: dict = None,
    rankings: list = None,
) -> Judgment:
    """Helper to create a judgment."""
    jud = Judgment(
        question_id=question_id,
        judge_preset_id=judge_preset_id,
        blind_mapping=blind_mapping,
        rankings=rankings,
        scores=scores,
        reasoning="Test reasoning",
        comments={},
        latency_ms=2000,
        tokens=100,
        status=TaskStatus.success,
        retries=0,
    )
    session.add(jud)
    session.commit()
    return jud


def test_single_judge_weighted_score(db_session):
    """
    Test weighted score with single judge.

    Expected: (8*3 + 6*1) / 4 = 7.5
    """
    # Setup: 1 model, 1 judge, 2 criteria (weight 3 and 1)
    model = create_model_preset(db_session, "Model A", 1)
    judge = create_model_preset(db_session, "Judge 1", 2)

    criteria = [
        {"name": "Quality", "weight": 3.0},
        {"name": "Speed", "weight": 1.0},
    ]

    run = create_benchmark_run(
        db_session,
        "Single Judge Test",
        model_ids=[1],
        judge_ids=[2],
        criteria=criteria,
    )

    question = create_question(db_session, run.id, order=1)
    create_generation(db_session, question.id, model.id)

    # Judge gives scores: Quality=8, Speed=6
    scores = {
        "1": {"Quality": 8.0, "Speed": 6.0}
    }
    create_judgment(
        db_session,
        question.id,
        judge.id,
        scores=scores,
        blind_mapping={"A": 1},
        rankings=["A"],
    )

    # Export and verify
    data = prepare_export_data(db_session, run.id)
    assert data is not None

    model_data = data["models"][0]
    assert model_data["name"] == "Model A"
    assert model_data["weighted_score"] == 7.5
    assert model_data["per_criterion_scores"]["Quality"] == 8.0
    assert model_data["per_criterion_scores"]["Speed"] == 6.0

    # Per-question score should match aggregate for single question
    assert len(model_data["per_question_scores"]) == 1
    assert model_data["per_question_scores"][0]["score"] == 7.5


def test_two_judges_weighted_score(db_session):
    """
    Test weighted score with two judges.

    Judge 1: Quality=8, Speed=5
    Judge 2: Quality=8, Speed=5
    Average per criterion first: Quality=8, Speed=5
    Expected: (8*3 + 5*1) / 4 = 7.25
    """
    # Setup: 1 model, 2 judges, 2 criteria
    model = create_model_preset(db_session, "Model A", 1)
    judge1 = create_model_preset(db_session, "Judge 1", 2)
    judge2 = create_model_preset(db_session, "Judge 2", 3)

    criteria = [
        {"name": "Quality", "weight": 3.0},
        {"name": "Speed", "weight": 1.0},
    ]

    run = create_benchmark_run(
        db_session,
        "Two Judges Test",
        model_ids=[1],
        judge_ids=[2, 3],
        criteria=criteria,
    )

    question = create_question(db_session, run.id, order=1)
    create_generation(db_session, question.id, model.id)

    # Judge 1 scores
    scores1 = {"1": {"Quality": 8.0, "Speed": 5.0}}
    create_judgment(
        db_session,
        question.id,
        judge1.id,
        scores=scores1,
        blind_mapping={"A": 1},
        rankings=["A"],
    )

    # Judge 2 scores (same to simplify test)
    scores2 = {"1": {"Quality": 8.0, "Speed": 5.0}}
    create_judgment(
        db_session,
        question.id,
        judge2.id,
        scores=scores2,
        blind_mapping={"A": 1},
        rankings=["A"],
    )

    # Export and verify
    data = prepare_export_data(db_session, run.id)
    assert data is not None

    model_data = data["models"][0]
    assert model_data["name"] == "Model A"
    assert model_data["weighted_score"] == 7.25
    assert model_data["per_criterion_scores"]["Quality"] == 8.0
    assert model_data["per_criterion_scores"]["Speed"] == 5.0


def test_two_judges_different_scores(db_session):
    """
    Test weighted score with two judges giving different scores.

    Judge 1: Quality=9, Speed=6
    Judge 2: Quality=7, Speed=4
    Average per criterion first: Quality=8, Speed=5
    Expected: (8*3 + 5*1) / 4 = 7.25
    """
    # Setup
    model = create_model_preset(db_session, "Model A", 1)
    judge1 = create_model_preset(db_session, "Judge 1", 2)
    judge2 = create_model_preset(db_session, "Judge 2", 3)

    criteria = [
        {"name": "Quality", "weight": 3.0},
        {"name": "Speed", "weight": 1.0},
    ]

    run = create_benchmark_run(
        db_session,
        "Different Scores Test",
        model_ids=[1],
        judge_ids=[2, 3],
        criteria=criteria,
    )

    question = create_question(db_session, run.id, order=1)
    create_generation(db_session, question.id, model.id)

    # Judge 1: Quality=9, Speed=6
    scores1 = {"1": {"Quality": 9.0, "Speed": 6.0}}
    create_judgment(
        db_session,
        question.id,
        judge1.id,
        scores=scores1,
        blind_mapping={"A": 1},
        rankings=["A"],
    )

    # Judge 2: Quality=7, Speed=4
    scores2 = {"1": {"Quality": 7.0, "Speed": 4.0}}
    create_judgment(
        db_session,
        question.id,
        judge2.id,
        scores=scores2,
        blind_mapping={"A": 1},
        rankings=["A"],
    )

    # Export and verify
    data = prepare_export_data(db_session, run.id)
    assert data is not None

    model_data = data["models"][0]
    assert model_data["name"] == "Model A"

    # Verify per-criterion averages
    assert model_data["per_criterion_scores"]["Quality"] == 8.0  # (9+7)/2
    assert model_data["per_criterion_scores"]["Speed"] == 5.0   # (6+4)/2

    # Verify weighted score: (8*3 + 5*1) / 4 = 7.25
    assert model_data["weighted_score"] == 7.25


def test_multi_question_scoring(db_session):
    """
    Test that per-question scores are calculated correctly and aggregate properly.

    Question 1: Quality=8, Speed=6 -> weighted = 7.5
    Question 2: Quality=6, Speed=4 -> weighted = 5.5
    Aggregate: Quality=7, Speed=5 -> weighted = 6.5
    """
    # Setup
    model = create_model_preset(db_session, "Model A", 1)
    judge = create_model_preset(db_session, "Judge 1", 2)

    criteria = [
        {"name": "Quality", "weight": 3.0},
        {"name": "Speed", "weight": 1.0},
    ]

    run = create_benchmark_run(
        db_session,
        "Multi Question Test",
        model_ids=[1],
        judge_ids=[2],
        criteria=criteria,
    )

    # Question 1
    q1 = create_question(db_session, run.id, order=1)
    create_generation(db_session, q1.id, model.id, "Response 1")
    scores_q1 = {"1": {"Quality": 8.0, "Speed": 6.0}}
    create_judgment(db_session, q1.id, judge.id, scores=scores_q1)

    # Question 2
    q2 = create_question(db_session, run.id, order=2)
    create_generation(db_session, q2.id, model.id, "Response 2")
    scores_q2 = {"1": {"Quality": 6.0, "Speed": 4.0}}
    create_judgment(db_session, q2.id, judge.id, scores=scores_q2)

    # Export and verify
    data = prepare_export_data(db_session, run.id)
    assert data is not None

    model_data = data["models"][0]

    # Check aggregate scores
    assert model_data["per_criterion_scores"]["Quality"] == 7.0  # (8+6)/2
    assert model_data["per_criterion_scores"]["Speed"] == 5.0   # (6+4)/2
    assert model_data["weighted_score"] == 6.5  # (7*3 + 5*1) / 4

    # Check per-question scores
    assert len(model_data["per_question_scores"]) == 2

    q1_score = [q for q in model_data["per_question_scores"] if q["order"] == 1][0]
    assert q1_score["score"] == 7.5  # (8*3 + 6*1) / 4

    q2_score = [q for q in model_data["per_question_scores"] if q["order"] == 2][0]
    assert q2_score["score"] == 5.5  # (6*3 + 4*1) / 4


def test_multi_question_multi_judge_scoring(db_session):
    """
    Test scoring with multiple questions and multiple judges.

    Question 1:
      - Judge 1: Quality=9, Speed=6
      - Judge 2: Quality=7, Speed=4
      - Avg: Quality=8, Speed=5 -> weighted = 7.25

    Question 2:
      - Judge 1: Quality=7, Speed=5
      - Judge 2: Quality=5, Speed=3
      - Avg: Quality=6, Speed=4 -> weighted = 5.5

    Aggregate:
      - Quality: (9+7+7+5)/4 = 7.0
      - Speed: (6+4+5+3)/4 = 4.5
      - Weighted: (7*3 + 4.5*1) / 4 = 6.375
    """
    # Setup
    model = create_model_preset(db_session, "Model A", 1)
    judge1 = create_model_preset(db_session, "Judge 1", 2)
    judge2 = create_model_preset(db_session, "Judge 2", 3)

    criteria = [
        {"name": "Quality", "weight": 3.0},
        {"name": "Speed", "weight": 1.0},
    ]

    run = create_benchmark_run(
        db_session,
        "Multi Q Multi J Test",
        model_ids=[1],
        judge_ids=[2, 3],
        criteria=criteria,
    )

    # Question 1
    q1 = create_question(db_session, run.id, order=1)
    create_generation(db_session, q1.id, model.id, "Response 1")
    create_judgment(db_session, q1.id, judge1.id, scores={"1": {"Quality": 9.0, "Speed": 6.0}})
    create_judgment(db_session, q1.id, judge2.id, scores={"1": {"Quality": 7.0, "Speed": 4.0}})

    # Question 2
    q2 = create_question(db_session, run.id, order=2)
    create_generation(db_session, q2.id, model.id, "Response 2")
    create_judgment(db_session, q2.id, judge1.id, scores={"1": {"Quality": 7.0, "Speed": 5.0}})
    create_judgment(db_session, q2.id, judge2.id, scores={"1": {"Quality": 5.0, "Speed": 3.0}})

    # Export and verify
    data = prepare_export_data(db_session, run.id)
    assert data is not None

    model_data = data["models"][0]

    # Check aggregate criterion scores
    # Quality: (9+7+7+5)/4 = 7.0
    # Speed: (6+4+5+3)/4 = 4.5
    assert model_data["per_criterion_scores"]["Quality"] == 7.0
    assert model_data["per_criterion_scores"]["Speed"] == 4.5

    # Check aggregate weighted score: (7*3 + 4.5*1) / 4 = 6.375
    assert model_data["weighted_score"] == 6.38  # rounded to 2 decimals

    # Check per-question scores
    q1_scores = [q for q in model_data["per_question_scores"] if q["order"] == 1][0]
    # Q1: Quality avg=(9+7)/2=8, Speed avg=(6+4)/2=5
    # Weighted: (8*3 + 5*1) / 4 = 7.25
    assert q1_scores["score"] == 7.25

    q2_scores = [q for q in model_data["per_question_scores"] if q["order"] == 2][0]
    # Q2: Quality avg=(7+5)/2=6, Speed avg=(5+3)/2=4
    # Weighted: (6*3 + 4*1) / 4 = 5.5
    assert q2_scores["score"] == 5.5


def test_compare_endpoint_scoring_consistency(db_session):
    """
    Test that scoring is consistent when comparing multiple runs.

    This test verifies that weighted scores are calculated consistently
    across different runs with the same criteria but different scores.
    """
    # Setup
    model = create_model_preset(db_session, "Model A", 1)
    judge = create_model_preset(db_session, "Judge 1", 2)

    criteria = [
        {"name": "Quality", "weight": 3.0},
        {"name": "Speed", "weight": 1.0},
    ]

    # Run 1: Higher scores
    run1 = create_benchmark_run(
        db_session,
        "Compare Test Run 1",
        model_ids=[1],
        judge_ids=[2],
        criteria=criteria,
    )
    q1 = create_question(db_session, run1.id, order=1)
    create_generation(db_session, q1.id, model.id)
    create_judgment(db_session, q1.id, judge.id, scores={"1": {"Quality": 9.0, "Speed": 6.0}})

    # Run 2: Lower scores
    run2 = create_benchmark_run(
        db_session,
        "Compare Test Run 2",
        model_ids=[1],
        judge_ids=[2],
        criteria=criteria,
    )
    q2 = create_question(db_session, run2.id, order=1)
    create_generation(db_session, q2.id, model.id)
    create_judgment(db_session, q2.id, judge.id, scores={"1": {"Quality": 6.0, "Speed": 4.0}})

    # Get export data for both runs
    export_data1 = prepare_export_data(db_session, run1.id)
    export_data2 = prepare_export_data(db_session, run2.id)

    weighted1 = export_data1["models"][0]["weighted_score"]
    weighted2 = export_data2["models"][0]["weighted_score"]

    # Run 1: (9*3 + 6*1) / 4 = 8.25
    assert weighted1 == 8.25

    # Run 2: (6*3 + 4*1) / 4 = 5.5
    assert weighted2 == 5.5

    # Ensure they're different (proving weights are applied correctly)
    assert weighted1 > weighted2


def test_equal_weights_unweighted_match(db_session):
    """
    Test that when all weights are equal, weighted and unweighted scores match.
    """
    # Setup
    model = create_model_preset(db_session, "Model A", 1)
    judge = create_model_preset(db_session, "Judge 1", 2)

    # All criteria have equal weight
    criteria = [
        {"name": "Quality", "weight": 1.0},
        {"name": "Speed", "weight": 1.0},
        {"name": "Accuracy", "weight": 1.0},
    ]

    run = create_benchmark_run(
        db_session,
        "Equal Weights Test",
        model_ids=[1],
        judge_ids=[2],
        criteria=criteria,
    )

    question = create_question(db_session, run.id, order=1)
    create_generation(db_session, question.id, model.id)

    scores = {"1": {"Quality": 8.0, "Speed": 6.0, "Accuracy": 7.0}}
    create_judgment(db_session, question.id, judge.id, scores=scores)

    # Export and verify
    data = prepare_export_data(db_session, run.id)
    model_data = data["models"][0]

    # With equal weights, weighted and unweighted should be the same
    expected = (8.0 + 6.0 + 7.0) / 3  # 7.0
    assert model_data["weighted_score"] == round(expected, 2)
    assert model_data["unweighted_score"] == round(expected, 2)
    assert model_data["weighted_score"] == model_data["unweighted_score"]


def test_failed_judgments_excluded(db_session):
    """
    Test that failed judgments are excluded from scoring calculations.
    """
    # Setup
    model = create_model_preset(db_session, "Model A", 1)
    judge1 = create_model_preset(db_session, "Judge 1", 2)
    judge2 = create_model_preset(db_session, "Judge 2", 3)

    criteria = [
        {"name": "Quality", "weight": 3.0},
        {"name": "Speed", "weight": 1.0},
    ]

    run = create_benchmark_run(
        db_session,
        "Failed Judgment Test",
        model_ids=[1],
        judge_ids=[2, 3],
        criteria=criteria,
    )

    question = create_question(db_session, run.id, order=1)
    create_generation(db_session, question.id, model.id)

    # Judge 1: Success with scores
    create_judgment(
        db_session,
        question.id,
        judge1.id,
        scores={"1": {"Quality": 8.0, "Speed": 6.0}}
    )

    # Judge 2: Failed (no scores should be counted)
    failed_judgment = Judgment(
        question_id=question.id,
        judge_preset_id=judge2.id,
        status=TaskStatus.failed,
        error="Test error",
    )
    db_session.add(failed_judgment)
    db_session.commit()

    # Export and verify
    data = prepare_export_data(db_session, run.id)
    model_data = data["models"][0]

    # Should only use Judge 1's scores
    assert model_data["per_criterion_scores"]["Quality"] == 8.0
    assert model_data["per_criterion_scores"]["Speed"] == 6.0
    assert model_data["weighted_score"] == 7.5  # (8*3 + 6*1) / 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
