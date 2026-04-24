"""Tests for aggregate leaderboard endpoint."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-agg"

import pytest
from fastapi.testclient import TestClient

from app.db.database import get_db
from app.main import app
from app.db.models import (
    BenchmarkRun, Question, Generation, Judgment,
    ModelPreset, RunStatus, TaskStatus, JudgeMode,
    ProviderType, TemperatureMode,
)


class TestAggregateLeaderboardSchemas:
    """Verify the endpoint exists and returns correct shape."""

    def test_endpoint_exists(self, client: TestClient):
        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200

    def test_empty_response_shape(self, client: TestClient):
        resp = client.get("/api/elo/aggregate-leaderboard")
        data = resp.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) == 0


def _get_db():
    return next(app.dependency_overrides[get_db]())


def _make_presets(db):
    """Create model_a, model_b, and judge and return them."""
    model_a = ModelPreset(
        id=1, name="Model-A", provider=ProviderType.openai,
        base_url="http://test", model_id="model-a",
    )
    model_b = ModelPreset(
        id=2, name="Model-B", provider=ProviderType.anthropic,
        base_url="http://test", model_id="model-b",
    )
    judge = ModelPreset(
        id=3, name="Judge-1", provider=ProviderType.openai,
        base_url="http://test", model_id="judge-1",
    )
    db.add_all([model_a, model_b, judge])
    db.flush()
    return model_a, model_b, judge


def _make_run(db, judge_mode=JudgeMode.comparison, criteria=None, run_id=1):
    if criteria is None:
        criteria = [{"name": "quality", "description": "Overall quality", "weight": 1.0}]
    run = BenchmarkRun(
        id=run_id, name="Test Run", status=RunStatus.completed,
        model_ids=[1, 2], judge_ids=[3],
        judge_mode=judge_mode,
        criteria=criteria,
        temperature=0.7, temperature_mode=TemperatureMode.normalized,
    )
    db.add(run)
    db.flush()
    return run


def _make_questions(db, run_id, count=2):
    questions = []
    for i in range(count):
        q = Question(
            id=run_id * 100 + i + 1,
            benchmark_id=run_id,
            order=i,
            system_prompt="sys",
            user_prompt=f"q{i}",
        )
        db.add(q)
        questions.append(q)
    db.flush()
    return questions


def _make_generations(db, question_id, gen_id_offset=0):
    """Create successful generations for model A (id=1) and model B (id=2)."""
    gens = []
    for idx, model_id in enumerate([1, 2]):
        g = Generation(
            id=gen_id_offset + question_id * 10 + model_id,
            question_id=question_id,
            model_preset_id=model_id,
            status=TaskStatus.success,
            content=f"response from model {model_id}",
        )
        db.add(g)
        gens.append(g)
    db.flush()
    return gens


def _make_comparison_judgment(db, question_id, judge_id, rankings, blind_mapping, jud_id):
    """Create a comparison-mode judgment."""
    j = Judgment(
        id=jud_id,
        question_id=question_id,
        judge_preset_id=judge_id,
        status=TaskStatus.success,
        rankings=rankings,
        blind_mapping=blind_mapping,
    )
    db.add(j)
    db.flush()
    return j


def _make_separate_judgment(db, question_id, judge_id, scores, jud_id):
    """Create a separate-mode judgment."""
    j = Judgment(
        id=jud_id,
        question_id=question_id,
        judge_preset_id=judge_id,
        status=TaskStatus.success,
        scores=scores,
    )
    db.add(j)
    db.flush()
    return j


class TestAggregateLeaderboardLogic:
    """Functional tests for the aggregate leaderboard endpoint."""

    def test_empty_db(self, client: TestClient):
        """No completed runs means empty list."""
        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        assert resp.json()["models"] == []

    def test_comparison_mode_wins(self, client: TestClient):
        """2 models, 2 questions, 1 judge. A wins q1, B wins q2. Each has 1 win + 1 loss."""
        db = _get_db()

        _make_presets(db)
        _make_run(db)
        q1, q2 = _make_questions(db, run_id=1, count=2)
        _make_generations(db, q1.id)
        _make_generations(db, q2.id)

        # q1: A wins — blind_mapping: "A"->1 (model_a), "B"->2 (model_b)
        _make_comparison_judgment(
            db, q1.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=1,
        )
        # q2: B wins — blind_mapping: "A"->2 (model_b), "B"->1 (model_a)
        _make_comparison_judgment(
            db, q2.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 2, "B": 1},
            jud_id=2,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        models = {m["model_name"]: m for m in resp.json()["models"]}

        assert models["Model-A"]["questions_won"] == 1
        assert models["Model-A"]["questions_lost"] == 1
        assert models["Model-A"]["questions_tied"] == 0
        assert models["Model-A"]["total_questions"] == 2

        assert models["Model-B"]["questions_won"] == 1
        assert models["Model-B"]["questions_lost"] == 1
        assert models["Model-B"]["questions_tied"] == 0
        assert models["Model-B"]["total_questions"] == 2

    def test_avg_weighted_score(self, client: TestClient):
        """Verify weighted scores are averaged correctly across questions."""
        db = _get_db()

        _make_presets(db)
        criteria = [
            {"name": "quality", "description": "Quality", "weight": 2.0},
            {"name": "clarity", "description": "Clarity", "weight": 1.0},
        ]
        _make_run(db, judge_mode=JudgeMode.separate, criteria=criteria)
        (q1,) = _make_questions(db, run_id=1, count=1)
        _make_generations(db, q1.id)

        # Model A scores: quality=8, clarity=6 => weighted = (8*2 + 6*1)/3 = 22/3
        # Model B scores: quality=6, clarity=9 => weighted = (6*2 + 9*1)/3 = 21/3
        _make_separate_judgment(
            db, q1.id, judge_id=3,
            scores={"1": {"quality": 8.0, "clarity": 6.0}, "2": {"quality": 6.0, "clarity": 9.0}},
            jud_id=1,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        models = {m["model_name"]: m for m in resp.json()["models"]}

        expected_a = (8.0 * 2.0 + 6.0 * 1.0) / 3.0
        expected_b = (6.0 * 2.0 + 9.0 * 1.0) / 3.0
        assert abs(models["Model-A"]["avg_weighted_score"] - expected_a) < 1e-6
        assert abs(models["Model-B"]["avg_weighted_score"] - expected_b) < 1e-6
        assert models["Model-A"]["scored_questions"] == 1
        assert models["Model-B"]["scored_questions"] == 1

    def test_archived_models_excluded(self, client: TestClient):
        """Archived models should not appear in the leaderboard."""
        db = _get_db()

        model_a, model_b, judge = _make_presets(db)
        # Archive model_b
        model_b.is_archived = 1
        db.flush()

        _make_run(db)
        (q1,) = _make_questions(db, run_id=1, count=1)
        _make_generations(db, q1.id)

        _make_comparison_judgment(
            db, q1.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=1,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        names = [m["model_name"] for m in resp.json()["models"]]
        assert "Model-A" in names
        assert "Model-B" not in names

    def test_runs_participated(self, client: TestClient):
        """Each model participated in exactly 1 run."""
        db = _get_db()

        _make_presets(db)
        _make_run(db)
        (q1,) = _make_questions(db, run_id=1, count=1)
        _make_generations(db, q1.id)

        _make_comparison_judgment(
            db, q1.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=1,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        models = {m["model_name"]: m for m in resp.json()["models"]}

        assert models["Model-A"]["runs_participated"] == 1
        assert models["Model-B"]["runs_participated"] == 1

    def test_majority_vote_with_multiple_judges(self, client: TestClient):
        """2 models, 1 question, 3 judges. 2 say A wins, 1 says B. A gets 1 win."""
        db = _get_db()

        _make_presets(db)
        # Add a 4th and 5th preset for extra judges
        judge2 = ModelPreset(
            id=4, name="Judge-2", provider=ProviderType.openai,
            base_url="http://test", model_id="judge-2",
        )
        judge3 = ModelPreset(
            id=5, name="Judge-3", provider=ProviderType.openai,
            base_url="http://test", model_id="judge-3",
        )
        db.add_all([judge2, judge3])
        db.flush()

        _make_run(db)
        (q1,) = _make_questions(db, run_id=1, count=1)
        _make_generations(db, q1.id)

        # Judge 1: A wins (model 1)
        _make_comparison_judgment(
            db, q1.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=1,
        )
        # Judge 2: A wins (model 1)
        _make_comparison_judgment(
            db, q1.id, judge_id=4,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=2,
        )
        # Judge 3: B wins (model 2)
        _make_comparison_judgment(
            db, q1.id, judge_id=5,
            rankings=["B", "A"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=3,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        models = {m["model_name"]: m for m in resp.json()["models"]}

        assert models["Model-A"]["questions_won"] == 1
        assert models["Model-A"]["questions_lost"] == 0
        assert models["Model-B"]["questions_won"] == 0
        assert models["Model-B"]["questions_lost"] == 1

    def test_win_rate_computed_correctly(self, client: TestClient):
        """win_rate = questions_won / total_questions."""
        db = _get_db()

        _make_presets(db)
        _make_run(db)
        q1, q2 = _make_questions(db, run_id=1, count=2)
        _make_generations(db, q1.id)
        _make_generations(db, q2.id)

        # A wins both questions
        _make_comparison_judgment(
            db, q1.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=1,
        )
        _make_comparison_judgment(
            db, q2.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=2,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        models = {m["model_name"]: m for m in resp.json()["models"]}

        assert models["Model-A"]["win_rate"] == pytest.approx(1.0)
        assert models["Model-B"]["win_rate"] == pytest.approx(0.0)

        # Model-A should be sorted first (higher win_rate)
        result_list = resp.json()["models"]
        assert result_list[0]["model_name"] == "Model-A"

    def test_tie_logic(self, client: TestClient):
        """When two judges split 1-1, both models tie on the question."""
        db = _get_db()

        _make_presets(db)
        judge2 = ModelPreset(
            id=4, name="Judge-2", provider=ProviderType.openai,
            base_url="http://test", model_id="judge-2",
        )
        db.add(judge2)
        db.flush()

        _make_run(db)
        (q1,) = _make_questions(db, run_id=1, count=1)
        _make_generations(db, q1.id)

        # Judge 1 says A wins
        _make_comparison_judgment(
            db, q1.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=1,
        )
        # Judge 2 says B wins
        _make_comparison_judgment(
            db, q1.id, judge_id=4,
            rankings=["B", "A"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=2,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        models = {m["model_name"]: m for m in resp.json()["models"]}

        assert models["Model-A"]["questions_tied"] == 1
        assert models["Model-A"]["questions_won"] == 0
        assert models["Model-B"]["questions_tied"] == 1
        assert models["Model-B"]["questions_won"] == 0
        # win_rate should be 0 for both (tied questions don't count as wins)
        assert models["Model-A"]["win_rate"] == pytest.approx(0.0)

    def test_incomplete_runs_excluded(self, client: TestClient):
        """Runs that are not completed should not contribute to the leaderboard."""
        db = _get_db()

        _make_presets(db)
        # Create a run that is still running
        run = BenchmarkRun(
            id=1, name="Running Run", status=RunStatus.running,
            model_ids=[1, 2], judge_ids=[3],
            judge_mode=JudgeMode.comparison,
            criteria=[{"name": "quality", "description": "q", "weight": 1.0}],
            temperature=0.7, temperature_mode=TemperatureMode.normalized,
        )
        db.add(run)
        db.flush()
        (q1,) = _make_questions(db, run_id=1, count=1)
        _make_generations(db, q1.id)
        _make_comparison_judgment(
            db, q1.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": 1, "B": 2},
            jud_id=1,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        assert resp.json()["models"] == []

    def test_string_blind_mapping_keys_coercion(self, client: TestClient):
        """blind_mapping values stored as strings should still resolve correctly."""
        db = _get_db()

        _make_presets(db)
        _make_run(db)
        (q1,) = _make_questions(db, run_id=1, count=1)
        _make_generations(db, q1.id)

        # Store blind_mapping values as strings instead of ints
        _make_comparison_judgment(
            db, q1.id, judge_id=3,
            rankings=["A", "B"],
            blind_mapping={"A": "1", "B": "2"},  # string values
            jud_id=1,
        )
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        models = {m["model_name"]: m for m in resp.json()["models"]}

        # Should correctly identify model 1 (Model-A) as winner
        assert models["Model-A"]["questions_won"] == 1
        assert models["Model-B"]["questions_won"] == 0
