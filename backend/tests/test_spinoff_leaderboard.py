"""Tests for aggregate leaderboard spinoff exclusion - Task 4 (leaderboard part).

Uses conftest fixtures (db_session + client) so test data and the app
share the same in-memory SQLite database.
"""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ.setdefault("BELLMARK_SECRET_KEY", "test-secret-key")

from fastapi.testclient import TestClient

from app.db.database import get_db
from app.db.models import (
    ModelPreset, BenchmarkRun, Question, Generation, Judgment,
    ProviderType, JudgeMode, TaskStatus, RunStatus,
)
from app.main import app


def _get_db():
    """Get the DB session used by the app (via conftest override)."""
    return next(app.dependency_overrides[get_db]())


class TestAggregateLeaderboardExcludesSpinoffs:
    def test_spinoff_excluded_from_aggregate_leaderboard(self, client: TestClient):
        """Aggregate leaderboard must only count root (non-spinoff) completed runs."""
        db = _get_db()
        model = ModelPreset(
            id=10, name="MyModel", provider=ProviderType.openai,
            base_url="http://x", model_id="gpt-4",
        )
        judge = ModelPreset(
            id=11, name="Judge", provider=ProviderType.anthropic,
            base_url="http://y", model_id="claude-3",
        )
        db.add_all([model, judge])
        db.flush()

        # Root run (should count toward leaderboard)
        root = BenchmarkRun(
            id=100, name="Root",
            judge_mode=JudgeMode.comparison,
            criteria=[{"name": "Q", "weight": 1.0}],
            model_ids=[model.id],
            judge_ids=[judge.id],
            status=RunStatus.completed,
            parent_run_id=None,
        )
        db.add(root)
        db.flush()
        q_root = Question(id=1001, benchmark_id=root.id, order=0, system_prompt="s", user_prompt="u")
        db.add(q_root)
        db.flush()
        gen_root = Generation(
            id=3001, question_id=q_root.id, model_preset_id=model.id,
            content="response", tokens=100, status=TaskStatus.success,
        )
        db.add(gen_root)
        j_root = Judgment(
            id=2001, question_id=q_root.id, judge_preset_id=judge.id,
            blind_mapping={"A": model.id}, rankings=["A"],
            scores={str(model.id): {"Q": 9}}, status=TaskStatus.success,
        )
        db.add(j_root)

        # Spinoff run (should be EXCLUDED from leaderboard)
        spinoff = BenchmarkRun(
            id=101, name="Spinoff",
            judge_mode=JudgeMode.comparison,
            criteria=[{"name": "Q", "weight": 1.0}],
            model_ids=[model.id],
            judge_ids=[judge.id],
            status=RunStatus.completed,
            parent_run_id=root.id,
        )
        db.add(spinoff)
        db.flush()
        q_spinoff = Question(id=1002, benchmark_id=spinoff.id, order=0, system_prompt="s", user_prompt="u")
        db.add(q_spinoff)
        db.flush()
        gen_spinoff = Generation(
            id=3002, question_id=q_spinoff.id, model_preset_id=model.id,
            content="response", tokens=100, status=TaskStatus.success,
        )
        db.add(gen_spinoff)
        j_spinoff = Judgment(
            id=2002, question_id=q_spinoff.id, judge_preset_id=judge.id,
            blind_mapping={"A": model.id}, rankings=["A"],
            scores={str(model.id): {"Q": 9}}, status=TaskStatus.success,
        )
        db.add(j_spinoff)
        db.commit()

        resp = client.get("/api/elo/aggregate-leaderboard")
        assert resp.status_code == 200
        data = resp.json()
        model_entry = next((m for m in data["models"] if m["model_preset_id"] == model.id), None)
        assert model_entry is not None, (
            f"Expected model {model.id} in leaderboard, "
            f"got: {[m['model_preset_id'] for m in data['models']]}"
        )
        # Should count only the root run (1 run), NOT the spinoff
        assert model_entry["runs_participated"] == 1, (
            f"Expected 1 run participated (root only), got {model_entry['runs_participated']}"
        )
        # Should have 1 win (root question), not 2
        assert model_entry["questions_won"] == 1, (
            f"Expected 1 win (root question only), got {model_entry['questions_won']}"
        )
