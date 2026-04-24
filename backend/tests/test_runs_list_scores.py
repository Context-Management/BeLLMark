"""Tests for runs list weighted score top_models."""
import os
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-runs"

import pytest
from fastapi.testclient import TestClient
from app.db.database import get_db
from app.main import app
from app.db.models import (
    ModelPreset, BenchmarkRun, Question, Generation, Judgment,
    ProviderType, RunStatus, JudgeMode, TaskStatus, TemperatureMode
)


def _seed_run_with_scores(db):
    """Seed a completed run: Model-A scores 9.0, Model-B scores 6.0."""
    model_a = ModelPreset(id=1, name="Model-A", provider=ProviderType.openai, base_url="http://test", model_id="model-a")
    model_b = ModelPreset(id=2, name="Model-B", provider=ProviderType.anthropic, base_url="http://test", model_id="model-b")
    judge = ModelPreset(id=3, name="Judge", provider=ProviderType.openai, base_url="http://test", model_id="judge")
    db.add_all([model_a, model_b, judge])
    db.flush()

    run = BenchmarkRun(
        id=1, name="Score Run", status=RunStatus.completed,
        model_ids=[1, 2], judge_ids=[3],
        judge_mode=JudgeMode.comparison,
        criteria=[{"name": "quality", "description": "Quality", "weight": 1.0}],
        temperature=0.7, temperature_mode=TemperatureMode.normalized,
    )
    db.add(run)
    db.flush()

    q1 = Question(id=1, benchmark_id=1, order=0, system_prompt="s", user_prompt="q1")
    db.add(q1)
    db.flush()
    db.add(Generation(question_id=1, model_preset_id=1, status=TaskStatus.success, content="a"))
    db.add(Generation(question_id=1, model_preset_id=2, status=TaskStatus.success, content="b"))
    db.add(Judgment(
        question_id=1, judge_preset_id=3, status=TaskStatus.success,
        rankings=["A", "B"], blind_mapping={"A": 1, "B": 2},
        scores={"1": {"quality": 9.0}, "2": {"quality": 6.0}},
    ))
    db.flush()
    db.commit()


class TestRunsListTopModels:
    def test_top_models_have_scores(self, client: TestClient):
        db = next(app.dependency_overrides[get_db]())
        _seed_run_with_scores(db)
        resp = client.get("/api/benchmarks/")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) == 1
        top = runs[0]["top_models"]
        assert len(top) >= 1
        assert isinstance(top[0], dict)
        assert "name" in top[0]
        assert "weighted_score" in top[0]

    def test_top_models_sorted_by_score(self, client: TestClient):
        db = next(app.dependency_overrides[get_db]())
        _seed_run_with_scores(db)
        resp = client.get("/api/benchmarks/")
        top = resp.json()[0]["top_models"]
        assert top[0]["name"] == "Model-A"
        assert top[0]["weighted_score"] > top[1]["weighted_score"]

    def test_top_models_max_five(self, client: TestClient):
        db = next(app.dependency_overrides[get_db]())
        _seed_run_with_scores(db)
        resp = client.get("/api/benchmarks/")
        top = resp.json()[0]["top_models"]
        assert len(top) <= 5
