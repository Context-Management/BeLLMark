"""Spin-off / Rejudging utilities.

Provides deep_copy_questions_and_generations() which duplicates a parent
run's questions, question-attachment links, and generations into a new
(spin-off) benchmark run — without copying judgments, so the spin-off can
be re-judged with different judges / criteria.
"""
from sqlalchemy.orm import Session

from app.db.models import Question, Generation, QuestionAttachment


def deep_copy_questions_and_generations(
    db: Session,
    parent_run_id: int,
    spinoff_run_id: int,
) -> None:
    """Copy questions and their completed generations from parent to spinoff.

    For each question in the parent run (ordered by `order`):
    1. Creates a new Question row with a new PK pointing to spinoff_run_id.
    2. Creates new QuestionAttachment junction rows (same attachment_id).
    3. Creates new Generation rows (all fields copied, new PKs).

    Judgments are intentionally NOT copied — the spin-off starts with
    fresh judgments so a different judge / criterion set can be applied.

    The caller is responsible for flushing/committing after this call.
    """
    parent_questions = (
        db.query(Question)
        .filter(Question.benchmark_id == parent_run_id)
        .order_by(Question.order)
        .all()
    )

    for parent_q in parent_questions:
        # --- Copy the Question row ---
        new_q = Question(
            benchmark_id=spinoff_run_id,
            order=parent_q.order,
            system_prompt=parent_q.system_prompt,
            user_prompt=parent_q.user_prompt,
            expected_answer=parent_q.expected_answer,
            context_tokens=parent_q.context_tokens,
        )
        db.add(new_q)
        db.flush()  # Populate new_q.id before adding children

        # --- Copy QuestionAttachment junction rows (same attachment_id) ---
        parent_attachments = (
            db.query(QuestionAttachment)
            .filter(QuestionAttachment.question_id == parent_q.id)
            .all()
        )
        for pa in parent_attachments:
            new_qa = QuestionAttachment(
                question_id=new_q.id,
                attachment_id=pa.attachment_id,
                inherited=pa.inherited,
            )
            db.add(new_qa)

        # --- Copy Generation rows (all fields, new IDs) ---
        parent_gens = (
            db.query(Generation)
            .filter(Generation.question_id == parent_q.id)
            .all()
        )
        for pg in parent_gens:
            new_gen = Generation(
                question_id=new_q.id,
                model_preset_id=pg.model_preset_id,
                content=pg.content,
                tokens=pg.tokens,
                input_tokens=pg.input_tokens,
                output_tokens=pg.output_tokens,
                cached_input_tokens=pg.cached_input_tokens,
                reasoning_tokens=pg.reasoning_tokens,
                raw_chars=pg.raw_chars,
                answer_chars=pg.answer_chars,
                latency_ms=pg.latency_ms,
                status=pg.status,
                error=pg.error,
                retries=pg.retries,
                started_at=pg.started_at,
                completed_at=pg.completed_at,
                model_version=pg.model_version,
            )
            db.add(new_gen)
