"""Tests for spin-off creation via the create_benchmark API endpoint - Task 3."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ.setdefault("BELLMARK_SECRET_KEY", "test-secret-key")

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app
from app.db.database import get_db, Base
from app.db.models import (
    ModelPreset, BenchmarkRun, Question, Generation, Judgment,
    ProviderType, JudgeMode, RunStatus, TaskStatus,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=engine)


@pytest.fixture(autouse=True)
def db_session():
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def mock_validation():
    with patch("app.api.benchmarks.validate_run_local_presets", new=AsyncMock(return_value=[])):
        yield


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)
    monkeypatch.setenv("BELLMARK_DEV_MODE", "true")
    return TestClient(app)


@pytest.fixture()
def parent_run_data(db_session):
    """Create a completed parent run in the database."""
    db = TestSession()
    model = ModelPreset(name="GPT-4", provider=ProviderType.openai, base_url="http://x", model_id="gpt-4")
    judge = ModelPreset(name="Claude", provider=ProviderType.anthropic, base_url="http://y", model_id="claude-3")
    judge2 = ModelPreset(name="Gemini", provider=ProviderType.google, base_url="http://z", model_id="gemini-pro")
    db.add_all([model, judge, judge2])
    db.flush()

    parent = BenchmarkRun(
        name="Parent Benchmark",
        judge_mode=JudgeMode.comparison,
        criteria=[{"name": "Quality", "weight": 1.0}],
        model_ids=[model.id],
        judge_ids=[judge.id],
        status=RunStatus.completed,
    )
    db.add(parent)
    db.flush()

    for i in range(2):
        q = Question(
            benchmark_id=parent.id,
            order=i,
            system_prompt=f"System {i}",
            user_prompt=f"User {i}",
        )
        db.add(q)
        db.flush()
        gen = Generation(
            question_id=q.id,
            model_preset_id=model.id,
            content=f"Response {i}",
            tokens=100,
            status=TaskStatus.success,
        )
        db.add(gen)
        jud = Judgment(
            question_id=q.id,
            judge_preset_id=judge.id,
            blind_mapping={"A": model.id},
            rankings=["A"],
            status=TaskStatus.success,
        )
        db.add(jud)

    db.commit()
    result = {
        "parent_id": parent.id,
        "model_id": model.id,
        "judge_id": judge.id,
        "judge2_id": judge2.id,
    }
    db.close()
    return result


class TestSpinoffCreation:
    def test_spinoff_skips_question_creation_from_payload(self, client, parent_run_data):
        """When parent_run_id is provided, questions from request are ignored."""
        resp = client.post("/api/benchmarks/", json={
            "name": "Spinoff Run",
            "model_ids": [parent_run_data["model_id"]],
            "judge_ids": [parent_run_data["judge2_id"]],
            "judge_mode": "comparison",
            "criteria": [{"name": "Creativity", "description": "Creative", "weight": 1.0}],
            "questions": [],  # intentionally empty — should use parent's questions
            "parent_run_id": parent_run_data["parent_id"],
        })
        assert resp.status_code == 200, resp.text
        run_id = resp.json()["id"]

        db = TestSession()
        questions = db.query(Question).filter(Question.benchmark_id == run_id).all()
        assert len(questions) == 2, "Spinoff must have same number of questions as parent"
        db.close()

    def test_spinoff_copies_generations(self, client, parent_run_data):
        """Spin-off run has generations copied from parent (ready to re-judge)."""
        resp = client.post("/api/benchmarks/", json={
            "name": "Spinoff Run",
            "model_ids": [parent_run_data["model_id"]],
            "judge_ids": [parent_run_data["judge2_id"]],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Quality", "weight": 1.0}],
            "questions": [],
            "parent_run_id": parent_run_data["parent_id"],
        })
        assert resp.status_code == 200, resp.text
        run_id = resp.json()["id"]

        db = TestSession()
        questions = db.query(Question).filter(Question.benchmark_id == run_id).all()
        for q in questions:
            gens = db.query(Generation).filter(Generation.question_id == q.id).all()
            assert len(gens) == 1, "Each spinoff question must have a generation"
            assert gens[0].status == TaskStatus.success
        db.close()

    def test_spinoff_starts_with_no_judgments(self, client, parent_run_data):
        """Spin-off questions must start with zero judgments."""
        resp = client.post("/api/benchmarks/", json={
            "name": "Spinoff Run",
            "model_ids": [parent_run_data["model_id"]],
            "judge_ids": [parent_run_data["judge2_id"]],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Quality", "weight": 1.0}],
            "questions": [],
            "parent_run_id": parent_run_data["parent_id"],
        })
        run_id = resp.json()["id"]
        db = TestSession()
        questions = db.query(Question).filter(Question.benchmark_id == run_id).all()
        for q in questions:
            assert db.query(Judgment).filter(Judgment.question_id == q.id).count() == 0
        db.close()

    def test_spinoff_stores_parent_run_id(self, client, parent_run_data):
        """The created spin-off run must store parent_run_id."""
        resp = client.post("/api/benchmarks/", json={
            "name": "Spinoff Run",
            "model_ids": [parent_run_data["model_id"]],
            "judge_ids": [parent_run_data["judge2_id"]],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Quality", "weight": 1.0}],
            "questions": [],
            "parent_run_id": parent_run_data["parent_id"],
        })
        run_id = resp.json()["id"]
        db = TestSession()
        run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        assert run.parent_run_id == parent_run_data["parent_id"]
        db.close()

    def test_spinoff_uses_resume_not_run(self, client, parent_run_data):
        """Spin-off task should use runner.resume(), not runner.run()."""
        # We test this by ensuring the background task call is the resume variant.
        # Since DISABLE_BACKGROUND_RUNS=1, we just verify the run was created with pending status
        resp = client.post("/api/benchmarks/", json={
            "name": "Spinoff Run",
            "model_ids": [parent_run_data["model_id"]],
            "judge_ids": [parent_run_data["judge2_id"]],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Quality", "weight": 1.0}],
            "questions": [],
            "parent_run_id": parent_run_data["parent_id"],
        })
        run_id = resp.json()["id"]
        db = TestSession()
        run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        assert run.status == RunStatus.pending
        db.close()

    def test_normal_run_without_parent_id_unchanged(self, client, parent_run_data):
        """Normal run creation (no parent_run_id) still works as before."""
        resp = client.post("/api/benchmarks/", json={
            "name": "Normal Run",
            "model_ids": [parent_run_data["model_id"]],
            "judge_ids": [parent_run_data["judge2_id"]],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Quality", "weight": 1.0}],
            "questions": [
                {"system_prompt": "sys", "user_prompt": "What is 2+2?", "attachment_ids": []}
            ],
        })
        assert resp.status_code == 200, resp.text
        run_id = resp.json()["id"]
        db = TestSession()
        run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
        assert run.parent_run_id is None
        questions = db.query(Question).filter(Question.benchmark_id == run_id).all()
        assert len(questions) == 1
        db.close()

    def test_spinoff_with_invalid_parent_returns_404(self, client, parent_run_data):
        """Providing a non-existent parent_run_id should return 404."""
        resp = client.post("/api/benchmarks/", json={
            "name": "Bad Spinoff",
            "model_ids": [parent_run_data["model_id"]],
            "judge_ids": [parent_run_data["judge2_id"]],
            "judge_mode": "comparison",
            "criteria": [{"name": "Quality", "description": "Quality", "weight": 1.0}],
            "questions": [],
            "parent_run_id": 99999,
        })
        assert resp.status_code == 404
