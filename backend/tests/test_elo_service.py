"""Tests for ELO service integration."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-elo-svc"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db.database import Base
from app.db.models import (
    ModelPreset, BenchmarkRun, Question, Judgment, EloRating, EloHistory,
    ProviderType, JudgeMode, TaskStatus
)
from app.core.elo_service import update_elo_ratings_for_run

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine)

@pytest.fixture(autouse=True)
def setup():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

class TestEloService:
    def _create_models_and_run(self, db):
        model_a = ModelPreset(name="ModelA", provider=ProviderType.openai, base_url="http://x", model_id="a")
        model_b = ModelPreset(name="ModelB", provider=ProviderType.openai, base_url="http://x", model_id="b")
        judge = ModelPreset(name="Judge", provider=ProviderType.anthropic, base_url="http://x", model_id="j")
        db.add_all([model_a, model_b, judge])
        db.flush()

        run = BenchmarkRun(
            name="Test", judge_mode=JudgeMode.comparison,
            criteria=[{"name": "Quality", "weight": 1.0}],
            model_ids=[model_a.id, model_b.id], judge_ids=[judge.id],
        )
        db.add(run)
        db.flush()

        for i in range(3):
            q = Question(benchmark_id=run.id, order=i, system_prompt="sys", user_prompt=f"q{i}")
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

    def test_creates_initial_ratings(self):
        db = TestSession()
        run_id, mid_a, mid_b = self._create_models_and_run(db)
        update_elo_ratings_for_run(db, run_id)
        rating_a = db.query(EloRating).filter_by(model_preset_id=mid_a).first()
        rating_b = db.query(EloRating).filter_by(model_preset_id=mid_b).first()
        assert rating_a is not None
        assert rating_b is not None
        assert rating_a.rating > 1500
        assert rating_b.rating < 1500
        db.close()

    def test_creates_history(self):
        db = TestSession()
        run_id, mid_a, _ = self._create_models_and_run(db)
        update_elo_ratings_for_run(db, run_id)
        history = db.query(EloHistory).filter_by(model_preset_id=mid_a).all()
        assert len(history) == 1
        assert history[0].rating_before == 1500.0
        assert history[0].rating_after > 1500.0
        db.close()

    def test_updates_existing_ratings(self):
        db = TestSession()
        run_id, mid_a, mid_b = self._create_models_and_run(db)
        db.add(EloRating(model_preset_id=mid_a, rating=1600.0, games_played=10))
        db.add(EloRating(model_preset_id=mid_b, rating=1400.0, games_played=10))
        db.commit()
        update_elo_ratings_for_run(db, run_id)
        rating_a = db.query(EloRating).filter_by(model_preset_id=mid_a).first()
        assert rating_a.rating > 1600.0
        assert rating_a.games_played == 13
        db.close()

    def test_idempotent_double_call(self):
        """Calling update twice for the same run should not double-count."""
        db = TestSession()
        run_id, mid_a, mid_b = self._create_models_and_run(db)
        update_elo_ratings_for_run(db, run_id)
        rating_after_first = db.query(EloRating).filter_by(model_preset_id=mid_a).first().rating
        games_after_first = db.query(EloRating).filter_by(model_preset_id=mid_a).first().games_played
        history_count_first = db.query(EloHistory).filter_by(benchmark_run_id=run_id).count()

        # Call again — should be a no-op
        update_elo_ratings_for_run(db, run_id)
        rating_after_second = db.query(EloRating).filter_by(model_preset_id=mid_a).first().rating
        games_after_second = db.query(EloRating).filter_by(model_preset_id=mid_a).first().games_played
        history_count_second = db.query(EloHistory).filter_by(benchmark_run_id=run_id).count()

        assert rating_after_first == rating_after_second
        assert games_after_first == games_after_second
        assert history_count_first == history_count_second
        db.close()
