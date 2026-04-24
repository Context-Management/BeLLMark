from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.benchmarks import get_benchmark
from app.core.exports.common import prepare_export_data
from app.core.pricing import calculate_model_cost, calculate_usage_cost
from app.db.database import Base
from app.db.models import BenchmarkRun, Generation, JudgeMode, ModelPreset, ProviderType, Question, RunStatus, TaskStatus


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    yield db
    db.close()


def _create_model(session, preset_id: int, name: str, *, price_input: float, price_output: float) -> ModelPreset:
    preset = ModelPreset(
        id=preset_id,
        name=name,
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-4.1",
        price_input=price_input,
        price_output=price_output,
    )
    session.add(preset)
    session.commit()
    return preset


def _create_run(session, model_ids: list[int]) -> BenchmarkRun:
    run = BenchmarkRun(
        name="Cost Test",
        status=RunStatus.completed,
        judge_mode=JudgeMode.comparison,
        criteria=[],
        model_ids=model_ids,
        judge_ids=[],
        created_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    session.add(run)
    session.commit()
    return run


def _create_question(session, run_id: int) -> Question:
    question = Question(
        benchmark_id=run_id,
        order=1,
        system_prompt="system",
        user_prompt="user",
        context_tokens=0,
    )
    session.add(question)
    session.commit()
    return question


def test_calculate_usage_cost_handles_cached_prompt_tokens():
    cost = calculate_usage_cost(
        input_tokens=1000,
        output_tokens=100,
        price_input=2.0,
        price_output=8.0,
        cached_input_tokens=500,
    )

    assert cost == 0.0028


def test_calculate_model_cost_uses_legacy_split_when_usage_breakdown_missing():
    cost, used_estimate = calculate_model_cost(
        "openai",
        "gpt-4.1",
        2.0,
        8.0,
        total_tokens=1000,
    )

    assert used_estimate is True
    assert round(cost, 4) == 0.0068


def test_get_benchmark_uses_persisted_usage_for_costs(session):
    model = _create_model(session, 1, "GPT-4.1", price_input=2.0, price_output=8.0)
    run = _create_run(session, [model.id])
    question = _create_question(session, run.id)

    generation = Generation(
        question_id=question.id,
        model_preset_id=model.id,
        content="answer",
        tokens=1100,
        input_tokens=1000,
        output_tokens=100,
        cached_input_tokens=500,
        latency_ms=1000,
        status=TaskStatus.success,
    )
    session.add(generation)
    session.commit()

    response = get_benchmark(run.id, session)

    assert response.performance_metrics["GPT-4.1"].estimated_cost == 0.0028


def test_prepare_export_data_falls_back_to_legacy_split_without_usage_breakdown(session):
    model = _create_model(session, 1, "GPT-4.1", price_input=2.0, price_output=8.0)
    run = _create_run(session, [model.id])
    question = _create_question(session, run.id)

    generation = Generation(
        question_id=question.id,
        model_preset_id=model.id,
        content="answer",
        tokens=1000,
        latency_ms=1000,
        status=TaskStatus.success,
    )
    session.add(generation)
    session.commit()

    export_data = prepare_export_data(session, run.id)

    assert export_data["models"][0]["estimated_cost"] == 0.0068
