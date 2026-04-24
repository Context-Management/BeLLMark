"""Tests for benchmark runner orchestration."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-runner"

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import (
    BenchmarkRun, Question, Generation, Judgment, ModelPreset,
    RunStatus, TaskStatus, JudgeMode, ProviderType, TemperatureMode
)
from app.core.runner import BenchmarkRunner

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestConcurrencySemaphore:
    def test_runner_has_provider_semaphores(self):
        db = TestSession()
        # Create minimal run to instantiate runner
        run = BenchmarkRun(
            name="Test", status=RunStatus.pending,
            judge_mode=JudgeMode.comparison,
            criteria=[{"name": "Quality", "description": "test", "weight": 1}],
            model_ids=[1], judge_ids=[2],
            temperature_mode=TemperatureMode.normalized,
        )
        db.add(run)
        db.commit()
        runner = BenchmarkRunner(db, run.id)
        assert hasattr(runner, '_provider_semaphores')
        assert isinstance(runner._provider_semaphores, dict)
        db.close()


@pytest.mark.asyncio
async def test_reconcile_lmstudio_snapshot_variants_retargets_running_benchmark():
    db = TestSession()

    preset = ModelPreset(
        id=101,
        name="Qwen3.5 27B",
        provider=ProviderType.lmstudio,
        base_url="http://mini.local:1234/v1/chat/completions",
        model_id="qwen3.5-27b",
        is_reasoning=0,
        quantization="8bit",
        model_format="MLX",
    )
    db.add(preset)

    run = BenchmarkRun(
        name="Repair me",
        status=RunStatus.running,
        judge_mode=JudgeMode.comparison,
        criteria=[{"name": "Quality", "description": "test", "weight": 1}],
        model_ids=[101],
        judge_ids=[],
        temperature_mode=TemperatureMode.normalized,
        run_config_snapshot={
            "models": [
                {
                    "id": 101,
                    "name": "Qwen3.5 27B",
                    "provider": "lmstudio",
                    "base_url": "http://mini.local:1234/v1/chat/completions",
                    "model_id": "qwen3.5-27b",
                    "quantization": "4bit",
                    "model_format": "MLX",
                }
            ]
        },
    )
    db.add(run)
    db.flush()

    question = Question(benchmark_id=run.id, order=0, system_prompt="s", user_prompt="u")
    db.add(question)
    db.flush()

    gen = Generation(
        question_id=question.id,
        model_preset_id=101,
        status=TaskStatus.success,
        content="wrong variant",
        model_version="qwen3.5-27b@8bit",
    )
    db.add(gen)
    db.commit()

    runner = BenchmarkRunner(db, run.id)

    discovered = [
        {
            "model_id": "qwen3.5-27b@4bit",
            "name": "Qwen3.5 27B",
            "quantization": "4bit",
            "model_format": "MLX",
            "provider_default_url": "http://mini.local:1234/v1/chat/completions",
        }
    ]

    with patch("app.core.runner.discover_lmstudio", AsyncMock(return_value=discovered)):
        await runner._reconcile_lmstudio_snapshot_variants([question], {101: preset})

    db.expire_all()
    repaired = db.query(ModelPreset).filter(ModelPreset.id == 101).first()
    remaining = db.query(Generation).filter(Generation.question_id == question.id, Generation.model_preset_id == 101).all()
    repaired_run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run.id).first()

    assert repaired.model_id == "qwen3.5-27b@4bit"
    assert repaired.quantization == "4bit"
    assert repaired.model_format == "MLX"
    assert remaining == []
    assert repaired_run.run_config_snapshot["models"][0]["model_id"] == "qwen3.5-27b@4bit"

    db.close()


@pytest.mark.asyncio
async def test_thinking_only_generation_triggers_retry(monkeypatch):
    """When generate() returns thinking_only=True, the runner should retry once."""
    db = TestSession()

    preset = ModelPreset(
        id=201,
        name="Sonnet Reasoning",
        provider=ProviderType.lmstudio,
        base_url="http://localhost:1234/v1/chat/completions",
        model_id="sonnet",
        is_reasoning=1,
    )
    db.add(preset)

    run = BenchmarkRun(
        name="Thinking Only Test",
        status=RunStatus.running,
        judge_mode=JudgeMode.comparison,
        criteria=[{"name": "Quality", "description": "test", "weight": 1}],
        model_ids=[201],
        judge_ids=[],
        temperature_mode=TemperatureMode.normalized,
    )
    db.add(run)
    db.flush()

    question = Question(benchmark_id=run.id, order=0, system_prompt="s", user_prompt="u")
    db.add(question)
    db.flush()

    gen = Generation(
        question_id=question.id,
        model_preset_id=201,
        status=TaskStatus.pending,
    )
    db.add(gen)
    db.commit()
    gen_id = gen.id
    question_id = question.id

    call_count = 0

    async def mock_generate(preset, system, user, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return {
                "success": True,
                "content": "",
                "thinking_only": True,
                "tokens": 64000,
                "output_tokens": 64000,
                "input_tokens": 500,
                "raw_chars": 50000,
                "answer_chars": 0,
                "latency_ms": 900000,
            }
        return {
            "success": True,
            "content": "Here is the actual answer.",
            "tokens": 10000,
            "output_tokens": 10000,
            "input_tokens": 500,
            "raw_chars": 8000,
            "answer_chars": 200,
            "latency_ms": 30000,
        }

    monkeypatch.setattr("app.core.runner.generate", mock_generate)

    # Patch manager and SessionLocal so the runner uses our in-memory DB
    mock_manager = MagicMock()
    mock_manager.send_generation = AsyncMock()
    monkeypatch.setattr("app.core.runner.manager", mock_manager)
    monkeypatch.setattr("app.db.database.SessionLocal", TestSession)

    runner = BenchmarkRunner(db, run.id)
    await runner._generate_with_retry(gen_id, preset, question_id, "s", "u", "Sonnet Reasoning")

    # generate() should have been called twice: once for thinking-only, once for real answer
    assert call_count == 2

    # The generation should be marked success with the real answer
    db2 = TestSession()
    final_gen = db2.query(Generation).filter(Generation.id == gen_id).first()
    assert final_gen.status == TaskStatus.success
    assert final_gen.content == "Here is the actual answer."
    db2.close()
    db.close()
