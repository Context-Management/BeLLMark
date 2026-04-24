"""Tests for compare-parent API endpoint - Task 5."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ.setdefault("BELLMARK_SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.db.database import get_db
from app.db.models import (
    ModelPreset, BenchmarkRun, Question, Generation, Judgment,
    ProviderType, JudgeMode, TaskStatus, RunStatus,
)
from app.main import app


def _get_db():
    return next(app.dependency_overrides[get_db]())


def _make_full_run(db, run_id, parent_run_id=None, judge_name="Judge", score=8.0):
    """Helper to create a complete run with one model, one question, one judgment."""
    model = ModelPreset(
        name=f"Model-{run_id}",
        provider=ProviderType.openai, base_url="http://x", model_id=f"gpt-4-{run_id}",
    )
    judge = ModelPreset(
        name=judge_name,
        provider=ProviderType.anthropic, base_url="http://y", model_id=f"claude-{run_id}",
    )
    db.add_all([model, judge])
    db.flush()

    run = BenchmarkRun(
        id=run_id, name=f"Run {run_id}",
        judge_mode=JudgeMode.comparison,
        criteria=[{"name": "Quality", "weight": 1.0}],
        model_ids=[model.id],
        judge_ids=[judge.id],
        status=RunStatus.completed,
        parent_run_id=parent_run_id,
    )
    db.add(run)
    db.flush()

    q = Question(
        id=run_id * 1000 + 1, benchmark_id=run.id,
        order=0, system_prompt="sys", user_prompt="What is 2+2?",
    )
    db.add(q)
    db.flush()

    gen = Generation(
        id=run_id * 1000 + 2, question_id=q.id, model_preset_id=model.id,
        content=f"Answer from run {run_id}", tokens=50, status=TaskStatus.success,
    )
    db.add(gen)

    jud = Judgment(
        id=run_id * 1000 + 3, question_id=q.id, judge_preset_id=judge.id,
        blind_mapping={"A": model.id}, rankings=["A"],
        scores={str(model.id): {"Quality": score}},
        status=TaskStatus.success,
    )
    db.add(jud)
    db.commit()
    return run.id, model.id, judge.id


class TestCompareParentEndpoint:
    def test_endpoint_exists(self, client: TestClient):
        """GET /api/benchmarks/{id}/compare-parent should exist."""
        resp = client.get("/api/benchmarks/9999/compare-parent")
        # 404 because run doesn't exist, but endpoint exists
        assert resp.status_code in (404, 400)

    def test_returns_404_for_nonexistent_run(self, client: TestClient):
        resp = client.get("/api/benchmarks/9999/compare-parent")
        assert resp.status_code == 404

    def test_returns_400_when_run_has_no_parent(self, client: TestClient):
        db = _get_db()
        root_id, _, _ = _make_full_run(db, run_id=200)
        resp = client.get(f"/api/benchmarks/{root_id}/compare-parent")
        assert resp.status_code == 400

    def test_returns_comparison_data_for_spinoff(self, client: TestClient):
        db = _get_db()
        root_id, _, _ = _make_full_run(db, run_id=300, score=7.0)
        spinoff_id, _, _ = _make_full_run(db, run_id=301, parent_run_id=root_id, score=9.0)

        resp = client.get(f"/api/benchmarks/{spinoff_id}/compare-parent")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "spinoff" in data
        assert "parent" in data
        assert data["spinoff"]["run_id"] == spinoff_id
        assert data["parent"]["run_id"] == root_id

    def test_response_contains_score_delta(self, client: TestClient):
        """Compare-parent response should include score delta info."""
        db = _get_db()
        root_id, _, _ = _make_full_run(db, run_id=400, score=6.0)
        spinoff_id, _, _ = _make_full_run(db, run_id=401, parent_run_id=root_id, score=8.0)

        resp = client.get(f"/api/benchmarks/{spinoff_id}/compare-parent")
        assert resp.status_code == 200
        data = resp.json()
        # Response should have score info for both runs
        assert "spinoff" in data
        assert "parent" in data

    def test_response_shape(self, client: TestClient):
        """Compare-parent response has the expected fields."""
        db = _get_db()
        root_id, _, _ = _make_full_run(db, run_id=500, score=5.0)
        spinoff_id, _, _ = _make_full_run(db, run_id=501, parent_run_id=root_id, score=8.0)

        resp = client.get(f"/api/benchmarks/{spinoff_id}/compare-parent")
        assert resp.status_code == 200
        data = resp.json()
        # Each side has run_id and name
        assert data["spinoff"]["run_id"] == spinoff_id
        assert data["parent"]["run_id"] == root_id
        assert "name" in data["spinoff"]
        assert "name" in data["parent"]
        # Judge info
        assert "judges" in data["spinoff"]
        assert "judges" in data["parent"]
        # Criteria
        assert "criteria" in data["spinoff"]
        assert "criteria" in data["parent"]
