"""Tests for spin-off / rejudging feature - Task 1: parent_run_id column."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ.setdefault("BELLMARK_SECRET_KEY", "test-secret-key")

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import BenchmarkRun, JudgeMode, RunStatus


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


class TestParentRunIdColumn:
    def test_benchmark_run_has_parent_run_id_column(self):
        """BenchmarkRun model should have parent_run_id column."""
        insp = sa_inspect(engine)
        cols = {c["name"] for c in insp.get_columns("benchmark_runs")}
        assert "parent_run_id" in cols, "benchmark_runs table must have parent_run_id column"

    def test_parent_run_id_is_nullable(self):
        """parent_run_id must be nullable (regular runs have no parent)."""
        insp = sa_inspect(engine)
        cols = {c["name"]: c for c in insp.get_columns("benchmark_runs")}
        assert cols["parent_run_id"]["nullable"] is True

    def test_create_run_without_parent(self):
        """Creating a run with no parent sets parent_run_id = None."""
        db = TestSession()
        run = BenchmarkRun(
            name="Root Run",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[1],
            judge_ids=[2],
            parent_run_id=None,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        assert run.parent_run_id is None
        db.close()

    def test_create_spinoff_with_parent_run_id(self):
        """Creating a spin-off run stores the parent_run_id correctly."""
        db = TestSession()
        parent = BenchmarkRun(
            name="Parent Run",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[1],
            judge_ids=[2],
        )
        db.add(parent)
        db.flush()

        spinoff = BenchmarkRun(
            name="Spinoff Run",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[1],
            judge_ids=[3],
            parent_run_id=parent.id,
        )
        db.add(spinoff)
        db.commit()
        db.refresh(spinoff)

        assert spinoff.parent_run_id == parent.id
        db.close()
