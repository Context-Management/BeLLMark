"""Tests for spin-off deep copy utility - Task 2."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ.setdefault("BELLMARK_SECRET_KEY", "test-secret-key")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import (
    BenchmarkRun, Question, Generation, Judgment, QuestionAttachment,
    ModelPreset, Attachment,
    JudgeMode, TaskStatus, ProviderType, RunStatus,
)
from app.core.spinoffs import deep_copy_questions_and_generations


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


def _make_parent_run(db) -> tuple:
    """Create a complete parent run with questions, generations, and attachments."""
    model = ModelPreset(name="Model A", provider=ProviderType.openai, base_url="http://x", model_id="gpt-4")
    judge = ModelPreset(name="Judge", provider=ProviderType.anthropic, base_url="http://y", model_id="claude-3")
    db.add_all([model, judge])
    db.flush()

    attachment = Attachment(filename="file.txt", storage_path="uploads/file.txt", mime_type="text/plain", size_bytes=10)
    db.add(attachment)
    db.flush()

    parent = BenchmarkRun(
        name="Parent Run",
        judge_mode=JudgeMode.comparison,
        criteria=[{"name": "Quality", "weight": 1.0}],
        model_ids=[model.id],
        judge_ids=[judge.id],
        status=RunStatus.completed,
    )
    db.add(parent)
    db.flush()

    questions = []
    for i in range(2):
        q = Question(
            benchmark_id=parent.id,
            order=i,
            system_prompt=f"System {i}",
            user_prompt=f"User question {i}",
            expected_answer=f"Expected {i}",
        )
        db.add(q)
        db.flush()

        # Add attachment to first question
        if i == 0:
            qa = QuestionAttachment(question_id=q.id, attachment_id=attachment.id, inherited=1)
            db.add(qa)

        gen = Generation(
            question_id=q.id,
            model_preset_id=model.id,
            content=f"Response for question {i}",
            tokens=100 + i * 10,
            input_tokens=50 + i,
            output_tokens=50 + i,
            cached_input_tokens=0,
            reasoning_tokens=0,
            raw_chars=200 + i,
            answer_chars=200 + i,
            latency_ms=500 + i * 100,
            status=TaskStatus.success,
            retries=0,
            model_version="gpt-4-turbo",
        )
        db.add(gen)
        db.flush()

        # Add a completed judgment (should NOT be copied)
        jud = Judgment(
            question_id=q.id,
            judge_preset_id=judge.id,
            blind_mapping={"A": model.id},
            rankings=["A"],
            scores={str(model.id): {"Quality": 9}},
            status=TaskStatus.success,
        )
        db.add(jud)

        questions.append(q)

    db.commit()
    return parent, model, judge, attachment, questions


class TestDeepCopyQuestionsAndGenerations:
    def test_creates_new_question_rows_with_new_ids(self):
        db = TestSession()
        parent, model, judge, attachment, orig_questions = _make_parent_run(db)

        spinoff = BenchmarkRun(
            name="Spinoff",
            judge_mode=JudgeMode.comparison,
            criteria=[{"name": "Quality", "weight": 1.0}],
            model_ids=[model.id],
            judge_ids=[judge.id],
            parent_run_id=parent.id,
        )
        db.add(spinoff)
        db.flush()

        deep_copy_questions_and_generations(db, parent.id, spinoff.id)
        db.commit()

        new_questions = db.query(Question).filter(Question.benchmark_id == spinoff.id).all()
        assert len(new_questions) == 2
        orig_ids = {q.id for q in orig_questions}
        new_ids = {q.id for q in new_questions}
        assert orig_ids.isdisjoint(new_ids), "New questions must have different IDs"
        db.close()

    def test_copies_question_fields(self):
        db = TestSession()
        parent, model, judge, attachment, orig_questions = _make_parent_run(db)

        spinoff = BenchmarkRun(
            name="Spinoff",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[model.id],
            judge_ids=[judge.id],
            parent_run_id=parent.id,
        )
        db.add(spinoff)
        db.flush()
        deep_copy_questions_and_generations(db, parent.id, spinoff.id)
        db.commit()

        new_qs = db.query(Question).filter(Question.benchmark_id == spinoff.id).order_by(Question.order).all()
        for i, q in enumerate(new_qs):
            assert q.system_prompt == f"System {i}"
            assert q.user_prompt == f"User question {i}"
            assert q.expected_answer == f"Expected {i}"
            assert q.order == i
        db.close()

    def test_copies_generations_with_new_ids(self):
        db = TestSession()
        parent, model, judge, attachment, orig_questions = _make_parent_run(db)

        spinoff = BenchmarkRun(
            name="Spinoff",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[model.id],
            judge_ids=[judge.id],
            parent_run_id=parent.id,
        )
        db.add(spinoff)
        db.flush()
        deep_copy_questions_and_generations(db, parent.id, spinoff.id)
        db.commit()

        new_qs = db.query(Question).filter(Question.benchmark_id == spinoff.id).all()
        for q in new_qs:
            gens = db.query(Generation).filter(Generation.question_id == q.id).all()
            assert len(gens) == 1, "Each question should have exactly one generation"
            gen = gens[0]
            assert gen.model_preset_id == model.id
            assert gen.status == TaskStatus.success
            # Generation id must differ from any original
        db.close()

    def test_copies_all_generation_fields(self):
        db = TestSession()
        parent, model, judge, attachment, orig_questions = _make_parent_run(db)

        spinoff = BenchmarkRun(
            name="Spinoff",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[model.id],
            judge_ids=[judge.id],
            parent_run_id=parent.id,
        )
        db.add(spinoff)
        db.flush()
        deep_copy_questions_and_generations(db, parent.id, spinoff.id)
        db.commit()

        new_qs = db.query(Question).filter(Question.benchmark_id == spinoff.id).order_by(Question.order).all()
        for i, q in enumerate(new_qs):
            gen = db.query(Generation).filter(Generation.question_id == q.id).first()
            assert gen.content == f"Response for question {i}"
            assert gen.tokens == 100 + i * 10
            assert gen.input_tokens == 50 + i
            assert gen.output_tokens == 50 + i
            assert gen.latency_ms == 500 + i * 100
            assert gen.model_version == "gpt-4-turbo"
        db.close()

    def test_copies_question_attachment_junction_rows(self):
        """QuestionAttachment junction rows are copied with new question_ids, same attachment_id."""
        db = TestSession()
        parent, model, judge, attachment, orig_questions = _make_parent_run(db)

        spinoff = BenchmarkRun(
            name="Spinoff",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[model.id],
            judge_ids=[judge.id],
            parent_run_id=parent.id,
        )
        db.add(spinoff)
        db.flush()
        deep_copy_questions_and_generations(db, parent.id, spinoff.id)
        db.commit()

        new_qs = db.query(Question).filter(Question.benchmark_id == spinoff.id).order_by(Question.order).all()
        # First question should have the attachment
        qa = db.query(QuestionAttachment).filter(QuestionAttachment.question_id == new_qs[0].id).all()
        assert len(qa) == 1
        assert qa[0].attachment_id == attachment.id
        # Second question should have no attachment
        qa2 = db.query(QuestionAttachment).filter(QuestionAttachment.question_id == new_qs[1].id).all()
        assert len(qa2) == 0
        db.close()

    def test_does_not_copy_judgments(self):
        """Judgments from parent run must NOT be copied to spinoff."""
        db = TestSession()
        parent, model, judge, attachment, orig_questions = _make_parent_run(db)

        spinoff = BenchmarkRun(
            name="Spinoff",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[model.id],
            judge_ids=[judge.id],
            parent_run_id=parent.id,
        )
        db.add(spinoff)
        db.flush()
        deep_copy_questions_and_generations(db, parent.id, spinoff.id)
        db.commit()

        new_qs = db.query(Question).filter(Question.benchmark_id == spinoff.id).all()
        for q in new_qs:
            jud_count = db.query(Judgment).filter(Judgment.question_id == q.id).count()
            assert jud_count == 0, "Spinoff questions must start with zero judgments"
        db.close()

    def test_preserves_original_questions_and_generations(self):
        """Original parent questions/generations must not be modified."""
        db = TestSession()
        parent, model, judge, attachment, orig_questions = _make_parent_run(db)

        spinoff = BenchmarkRun(
            name="Spinoff",
            judge_mode=JudgeMode.comparison,
            criteria=[],
            model_ids=[model.id],
            judge_ids=[judge.id],
            parent_run_id=parent.id,
        )
        db.add(spinoff)
        db.flush()
        deep_copy_questions_and_generations(db, parent.id, spinoff.id)
        db.commit()

        # Original still has its questions, generations, and judgments
        orig_qs = db.query(Question).filter(Question.benchmark_id == parent.id).all()
        assert len(orig_qs) == 2
        for q in orig_qs:
            assert db.query(Generation).filter(Generation.question_id == q.id).count() == 1
            assert db.query(Judgment).filter(Judgment.question_id == q.id).count() == 1
        db.close()
