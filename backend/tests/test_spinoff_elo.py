"""Tests for spin-off ELO exclusion - Task 4."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ.setdefault("BELLMARK_SECRET_KEY", "test-secret-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.db.database import Base, get_db
from app.db.models import (
    ModelPreset, BenchmarkRun, Question, Judgment, EloRating, EloHistory,
    ProviderType, JudgeMode, TaskStatus, RunStatus,
)
from app.core.elo_service import update_elo_ratings_for_run
from app.main import app


# Separate engine for ELO service unit tests (don't need the app's DB)
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _make_run(db, parent_id=None, status=RunStatus.completed):
    model_a = ModelPreset(name=f"ModelA-{parent_id}", provider=ProviderType.openai, base_url="http://x", model_id=f"a-{parent_id}")
    model_b = ModelPreset(name=f"ModelB-{parent_id}", provider=ProviderType.openai, base_url="http://x", model_id=f"b-{parent_id}")
    judge = ModelPreset(name=f"Judge-{parent_id}", provider=ProviderType.anthropic, base_url="http://x", model_id=f"j-{parent_id}")
    db.add_all([model_a, model_b, judge])
    db.flush()

    run = BenchmarkRun(
        name="Test", judge_mode=JudgeMode.comparison,
        criteria=[{"name": "Quality", "weight": 1.0}],
        model_ids=[model_a.id, model_b.id],
        judge_ids=[judge.id],
        status=status,
        parent_run_id=parent_id,
    )
    db.add(run)
    db.flush()

    q = Question(benchmark_id=run.id, order=0, system_prompt="sys", user_prompt="q")
    db.add(q)
    db.flush()
    jud = Judgment(
        question_id=q.id, judge_preset_id=judge.id,
        blind_mapping={"A": model_a.id, "B": model_b.id},
        rankings=["A", "B"],
        scores={str(model_a.id): {"Quality": 9}, str(model_b.id): {"Quality": 5}},
        status=TaskStatus.success,
    )
    db.add(jud)
    db.commit()
    return run.id, model_a.id, model_b.id


class TestEloExcludesSpinoffs:
    def test_elo_not_updated_for_spinoff(self):
        """ELO must NOT be updated when parent_run_id is set."""
        db = TestSession()
        # Create a parent run first
        parent_id, _, _ = _make_run(db, parent_id=None)
        # Create a spinoff that references the parent
        spinoff_id, mid_a, mid_b = _make_run(db, parent_id=parent_id)

        update_elo_ratings_for_run(db, spinoff_id)

        # ELO history should NOT have entries for the spinoff run
        history = db.query(EloHistory).filter_by(benchmark_run_id=spinoff_id).all()
        assert len(history) == 0, "Spin-off run must not create ELO history entries"
        db.close()

    def test_elo_updated_for_root_run(self):
        """ELO IS updated for root (non-spinoff) runs."""
        db = TestSession()
        root_id, mid_a, mid_b = _make_run(db, parent_id=None)
        update_elo_ratings_for_run(db, root_id)
        history = db.query(EloHistory).filter_by(benchmark_run_id=root_id).all()
        assert len(history) == 2, "Root run must create ELO history entries"
        db.close()

    def test_runner_skips_elo_for_spinoff(self):
        """_update_elo_on_completion skips when parent_run_id is set."""
        db = TestSession()
        parent_id, _, _ = _make_run(db, parent_id=None)
        spinoff_id, mid_a, mid_b = _make_run(db, parent_id=parent_id)

        from app.core.runner import BenchmarkRunner
        runner = BenchmarkRunner(db, spinoff_id)
        runner._update_elo_on_completion()

        history = db.query(EloHistory).filter_by(benchmark_run_id=spinoff_id).all()
        assert len(history) == 0
        db.close()


