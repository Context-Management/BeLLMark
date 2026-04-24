"""Tests for run statistics computation."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-runstats"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.database import Base
from app.db.models import *
from app.core.run_statistics import compute_run_statistics

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)

@pytest.fixture(autouse=True)
def setup():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def _seed_run(db, n_questions=10, model_a_score=8.0, model_b_score=5.0):
    """Create a benchmark run with deterministic scores for testing."""
    ma = ModelPreset(name="ModelA", provider=ProviderType.openai, base_url="http://x", model_id="a")
    mb = ModelPreset(name="ModelB", provider=ProviderType.openai, base_url="http://x", model_id="b")
    judge = ModelPreset(name="Judge", provider=ProviderType.anthropic, base_url="http://x", model_id="j")
    db.add_all([ma, mb, judge])
    db.flush()

    run = BenchmarkRun(
        name="Test", judge_mode=JudgeMode.comparison,
        criteria=[{"name": "Quality", "weight": 1.0}],
        model_ids=[ma.id, mb.id], judge_ids=[judge.id],
    )
    db.add(run)
    db.flush()

    for i in range(n_questions):
        q = Question(benchmark_id=run.id, order=i, system_prompt="s", user_prompt=f"q{i}")
        db.add(q)
        db.flush()
        noise = (i % 3 - 1) * 0.5
        jud = Judgment(
            question_id=q.id, judge_preset_id=judge.id,
            blind_mapping={"A": ma.id, "B": mb.id},
            rankings=["A", "B"],
            scores={
                str(ma.id): {"Quality": model_a_score + noise},
                str(mb.id): {"Quality": model_b_score + noise},
            },
            status=TaskStatus.success,
        )
        db.add(jud)
    db.commit()
    return run.id


class TestRunStatistics:
    def test_computes_confidence_intervals(self):
        db = TestSession()
        run_id = _seed_run(db, n_questions=10)
        result = compute_run_statistics(db, run_id)
        assert len(result["model_statistics"]) == 2
        for ms in result["model_statistics"]:
            assert ms["weighted_score_ci"] is not None
            assert ms["weighted_score_ci"]["lower"] <= ms["weighted_score_ci"]["mean"]
            assert ms["weighted_score_ci"]["mean"] <= ms["weighted_score_ci"]["upper"]
        db.close()

    def test_pairwise_comparisons(self):
        db = TestSession()
        run_id = _seed_run(db, n_questions=10, model_a_score=8.0, model_b_score=5.0)
        result = compute_run_statistics(db, run_id)
        assert len(result["pairwise_comparisons"]) == 1
        comp = result["pairwise_comparisons"][0]
        assert comp["significant"] is True
        assert comp["cohens_d"] > 0.8
        db.close()

    def test_power_analysis(self):
        db = TestSession()
        run_id = _seed_run(db, n_questions=5)
        result = compute_run_statistics(db, run_id)
        pa = result["power_analysis"]
        assert pa["current_questions"] == 5
        assert pa["recommended_small_effect"] > pa["recommended_large_effect"]
        db.close()

    def test_small_sample_warning(self):
        db = TestSession()
        run_id = _seed_run(db, n_questions=3)
        result = compute_run_statistics(db, run_id)
        assert result["sample_size_warning"] is not None
        db.close()
