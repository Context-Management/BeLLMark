"""Tests for is_reasoning and reasoning_level fields in ELO endpoints."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-elo-reasoning"

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.db.models import (
    BenchmarkRun, Question, Generation, Judgment,
    ModelPreset, EloRating, EloHistory,
    RunStatus, TaskStatus, JudgeMode, ProviderType, TemperatureMode, ReasoningLevel,
)


def _get_db():
    return next(app.dependency_overrides[get_db]())


def _make_preset(db, pid, name, is_reasoning=0, reasoning_level=None):
    p = ModelPreset(
        id=pid, name=name, provider=ProviderType.openai,
        base_url="http://test", model_id=f"model-{pid}",
        is_reasoning=is_reasoning,
        reasoning_level=reasoning_level,
        is_archived=0,
    )
    db.add(p)
    db.flush()
    return p


def _make_elo_rating(db, preset_id, rating=1500.0, uncertainty=200.0, games_played=10, rid=None):
    r = EloRating(
        id=rid or preset_id,
        model_preset_id=preset_id,
        rating=rating,
        uncertainty=uncertainty,
        games_played=games_played,
    )
    db.add(r)
    db.flush()
    return r


def _make_run(db, run_id=1):
    run = BenchmarkRun(
        id=run_id, name="Test Run", status=RunStatus.completed,
        model_ids=[1, 2], judge_ids=[3],
        judge_mode=JudgeMode.comparison,
        criteria=[{"name": "quality", "description": "q", "weight": 1.0}],
        temperature=0.7, temperature_mode=TemperatureMode.normalized,
    )
    db.add(run)
    db.flush()
    return run


def _make_question(db, run_id, qid):
    q = Question(
        id=qid, benchmark_id=run_id, order=0,
        system_prompt="sys", user_prompt="q",
    )
    db.add(q)
    db.flush()
    return q


def _make_generation(db, qid, model_id, gen_id):
    g = Generation(
        id=gen_id, question_id=qid,
        model_preset_id=model_id,
        status=TaskStatus.success,
        content="response",
    )
    db.add(g)
    db.flush()
    return g


def _make_judgment(db, qid, judge_id, rankings, blind_mapping, jud_id):
    j = Judgment(
        id=jud_id, question_id=qid, judge_preset_id=judge_id,
        status=TaskStatus.success,
        rankings=rankings,
        blind_mapping=blind_mapping,
    )
    db.add(j)
    db.flush()
    return j


class TestEloLeaderboardReasoningFields:
    """ELO leaderboard endpoint exposes is_reasoning and reasoning_level."""

    def test_standard_model_has_false_reasoning(self, client: TestClient):
        db = _get_db()
        _make_preset(db, 1, "Standard-Model", is_reasoning=0, reasoning_level=None)
        _make_elo_rating(db, 1)
        db.commit()

        resp = client.get("/api/elo/")
        assert resp.status_code == 200
        ratings = resp.json()["ratings"]
        assert len(ratings) == 1
        assert ratings[0]["is_reasoning"] is False
        assert ratings[0]["reasoning_level"] is None

    def test_reasoning_model_fields_propagate(self, client: TestClient):
        db = _get_db()
        _make_preset(db, 1, "Reasoning-Model", is_reasoning=1,
                     reasoning_level=ReasoningLevel.high)
        _make_elo_rating(db, 1)
        db.commit()

        resp = client.get("/api/elo/")
        assert resp.status_code == 200
        ratings = resp.json()["ratings"]
        assert len(ratings) == 1
        assert ratings[0]["is_reasoning"] is True
        assert ratings[0]["reasoning_level"] == "high"

    def test_mixed_models_in_elo_leaderboard(self, client: TestClient):
        db = _get_db()
        _make_preset(db, 1, "Std-Model", is_reasoning=0, reasoning_level=None)
        _make_preset(db, 2, "Think-Model", is_reasoning=1,
                     reasoning_level=ReasoningLevel.medium)
        _make_elo_rating(db, preset_id=1, rating=1600.0, rid=10)
        _make_elo_rating(db, preset_id=2, rating=1400.0, rid=20)
        db.commit()

        resp = client.get("/api/elo/")
        assert resp.status_code == 200
        # Key by model_id to avoid display-label decoration effects
        by_id = {r["model_id"]: r for r in resp.json()["ratings"]}
        assert by_id[1]["is_reasoning"] is False
        assert by_id[1]["reasoning_level"] is None
        assert by_id[2]["is_reasoning"] is True
        assert by_id[2]["reasoning_level"] == "medium"


class TestAggregateLeaderboardReasoningFields:
    """Aggregate leaderboard endpoint exposes is_reasoning and reasoning_level."""

    def _setup_completed_run(self, db):
        """Create a minimal completed run with two models."""
        _make_preset(db, 1, "Std-Model", is_reasoning=0, reasoning_level=None)
        _make_preset(db, 2, "Think-Model", is_reasoning=1,
                     reasoning_level=ReasoningLevel.low)
        judge = ModelPreset(
            id=3, name="Judge", provider=ProviderType.openai,
            base_url="http://test", model_id="judge",
            is_archived=0,
        )
        db.add(judge)
        db.flush()
        _make_run(db, run_id=1)
        q = _make_question(db, run_id=1, qid=101)
        _make_generation(db, q.id, 1, gen_id=1001)
        _make_generation(db, q.id, 2, gen_id=1002)
        _make_judgment(db, q.id, 3,
                       rankings=["A", "B"],
                       blind_mapping={"A": 1, "B": 2},
                       jud_id=9001)
        db.commit()

    def test_standard_model_aggregate_fields(self, client: TestClient):
        db = _get_db()
        self._setup_completed_run(db)

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        # Key by model_preset_id to avoid display-label decoration effects
        by_id = {m["model_preset_id"]: m for m in resp.json()["models"]}
        assert by_id[1]["is_reasoning"] is False
        assert by_id[1]["reasoning_level"] is None

    def test_reasoning_model_aggregate_fields(self, client: TestClient):
        db = _get_db()
        self._setup_completed_run(db)

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        # Key by model_preset_id to avoid display-label decoration effects
        by_id = {m["model_preset_id"]: m for m in resp.json()["models"]}
        assert by_id[2]["is_reasoning"] is True
        assert by_id[2]["reasoning_level"] == "low"

    def test_reasoning_level_none_when_is_reasoning_false(self, client: TestClient):
        """A model with is_reasoning=False should have reasoning_level=None regardless."""
        db = _get_db()
        _make_preset(db, 1, "Std-Model", is_reasoning=0, reasoning_level=None)
        _make_preset(db, 2, "OtherModel", is_reasoning=0, reasoning_level=None)
        judge = ModelPreset(
            id=3, name="Judge", provider=ProviderType.openai,
            base_url="http://test", model_id="judge",
            is_archived=0,
        )
        db.add(judge)
        db.flush()
        _make_run(db, run_id=1)
        q = _make_question(db, run_id=1, qid=201)
        _make_generation(db, q.id, 1, gen_id=2001)
        _make_generation(db, q.id, 2, gen_id=2002)
        _make_judgment(db, q.id, 3,
                       rankings=["A", "B"],
                       blind_mapping={"A": 1, "B": 2},
                       jud_id=9002)
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        for model in resp.json()["models"]:
            assert model["is_reasoning"] is False
            assert model["reasoning_level"] is None
