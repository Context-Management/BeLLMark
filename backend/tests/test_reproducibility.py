"""Tests for reproducibility metadata capture."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-repro"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import BenchmarkRun, Judgment, Generation, RunStatus

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


class TestReproducibilityMetadata:
    def test_benchmark_run_has_random_seed(self):
        db = TestSession()
        run = BenchmarkRun(
            name="test", status=RunStatus.pending,
            judge_mode="comparison",
            criteria=[{"name": "Quality", "weight": 1}],
            model_ids=[1], judge_ids=[2],
            random_seed=42
        )
        db.add(run)
        db.commit()
        assert run.random_seed == 42
        db.close()

    def test_judgment_stores_temperature(self):
        db = TestSession()
        j = Judgment.__table__.columns
        assert "judge_temperature" in [c.name for c in j]
        db.close()

    def test_generation_stores_model_version(self):
        g = Generation.__table__.columns
        assert "model_version" in [c.name for c in g]
