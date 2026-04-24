"""Tests for the async suite generator pipeline (Generate → Review → Merge → Rubric → Save)."""
import asyncio
import json
import pytest
from math import ceil
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.models import ModelPreset, ProviderType, PromptSuite, PromptSuiteItem
from app.core.suite_pipeline import (
    DEDUPE_ADJUDICATOR_SYSTEM_PROMPT,
    COVERAGE_DIGEST_SYSTEM_PROMPT,
    COVERAGE_VALIDATION_SYSTEM_PROMPT,
    MERGE_SYSTEM_PROMPT,
    PipelineConfig,
    ReviewBatchOutcome,
    REVIEWER_SYSTEM_PROMPT,
    RUBRIC_SYSTEM_PROMPT,
    SuitePipeline,
    active_suite_pipelines,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


def _make_preset(name="Generator", provider=ProviderType.openai):
    return ModelPreset(
        id=1,
        name=name,
        provider=provider,
        base_url="http://fake/v1/chat/completions",
        model_id="gpt-test",
    )


def _make_reviewer_preset(id_offset=0):
    return ModelPreset(
        id=10 + id_offset,
        name=f"Reviewer{id_offset}",
        provider=ProviderType.anthropic,
        base_url="http://fake2/v1/chat/completions",
        model_id="claude-test",
    )


def _sample_question(idx=0):
    """Return a minimal valid question dict as the LLM would produce."""
    return {
        "system_prompt": f"You are an expert system {idx}.",
        "user_prompt": f"Complex question {idx} with constraints A and B.",
        "reference_answer": f"Gold answer {idx} with detailed reasoning.",
        "criteria": [
            {"name": "Criterion A", "description": "Tests criterion A", "weight": 1.0},
            {"name": "Criterion B", "description": "Tests criterion B", "weight": 1.0},
        ],
        "category": "reasoning",
        "difficulty": "medium",
        "quality_self_score": 6,
    }


def _sample_review(question):
    """Return a minimal valid review dict."""
    return {
        "scores": {
            "specificity": 4,
            "discrimination": 4,
            "clarity": 4,
            "feasibility": 4,
            "constraints": 4,
        },
        "defects": [],
        "revised": question,
        "changes": "Minor wording improvement.",
    }


def _make_generate_response(questions: list[dict]) -> dict:
    """Wrap questions in the format returned by the generate() function."""
    return {"success": True, "content": json.dumps(questions), "tokens": 500, "error": None}


def _make_review_response(reviews: list[dict]) -> dict:
    return {"success": True, "content": json.dumps(reviews), "tokens": 200, "error": None}


def _make_rubric_response(criteria: list[dict]) -> dict:
    return {"success": True, "content": json.dumps(criteria), "tokens": 100, "error": None}


def _make_manager():
    """Create a mock suite_manager with send_progress."""
    mgr = MagicMock()
    mgr.send_progress = AsyncMock()
    return mgr


def _extract_json_between_markers(text: str, start_marker: str, end_marker: str) -> list[dict]:
    start = text.index(start_marker) + len(start_marker)
    end = text.index(end_marker, start)
    return json.loads(text[start:end].strip())


def _make_distinct_dedupe_response(user_prompt: str) -> dict:
    pairs = _extract_json_between_markers(
        user_prompt,
        "Pairs:\n",
        "\n\nReturn the adjudication JSON array now.",
    )
    return _make_generate_response([
        {
            "pair_index": pair["pair_index"],
            "label": "distinct",
            "keep_index": pair["left_index"],
            "reason": "test fixture treats these prompts as distinct",
        }
        for pair in pairs
    ])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def engine():
    e = _make_engine()
    yield e
    Base.metadata.drop_all(bind=e)


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture()
def generator_preset():
    return _make_preset()


@pytest.fixture()
def reviewer_presets():
    return [_make_reviewer_preset(0), _make_reviewer_preset(1)]


# ---------------------------------------------------------------------------
# Test: generation batching and ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_generation_batches_can_run_concurrently_across_generators(session_factory):
    gen_a = _make_preset("Generator A")
    gen_a.id = 31
    gen_b = _make_preset("Generator B")
    gen_b.id = 32

    released = asyncio.Event()
    started_models: list[str] = []
    active = 0
    max_active = 0
    concurrency = 4

    async def fake_generate_batch(self, assignment):
        nonlocal active, max_active
        started_models.append(assignment.preset.name)
        active += 1
        max_active = max(max_active, active)
        if len(started_models) == concurrency:
            released.set()
        await released.wait()
        active -= 1
        return [_sample_question(assignment.global_batch_index + 100)]

    async def fake_synthesize_rubric(self, questions):
        return [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]

    pipeline = SuitePipeline(
        session_id="concurrent-generators",
        generator_presets=[gen_a, gen_b],
        editor_preset=gen_a,
        reviewer_presets=[],
        name="Concurrent Generators",
        topic="Concurrency",
        count=40,
        config=PipelineConfig(generation_concurrency=concurrency),
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with (
        patch.object(SuitePipeline, "_generate_batch", fake_generate_batch),
        patch.object(SuitePipeline, "_synthesize_rubric", fake_synthesize_rubric),
        patch.object(SuitePipeline, "_dedupe_questions", AsyncMock(side_effect=lambda questions: questions)),
    ):
        await pipeline.run()

    assert max_active >= concurrency
    assert set(started_models[:concurrency]) == {"Generator A", "Generator B"}


@pytest.mark.asyncio
async def test_pipeline_concurrent_generation_reassembles_questions_in_batch_order(
    generator_preset, session_factory
):
    async def fake_generate_batch(self, assignment):
        if assignment.generator_batch_index == 1:
            await asyncio.sleep(0.05)
        elif assignment.generator_batch_index == 2:
            await asyncio.sleep(0.01)

        return [
            {
                **_sample_question(assignment.generator_batch_index * 100 + item_index),
                "user_prompt": f"Question from batch {assignment.generator_batch_index}.{item_index + 1}",
            }
            for item_index in range(assignment.question_count)
        ]

    async def fake_synthesize_rubric(self, questions):
        return [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]

    pipeline = SuitePipeline(
        session_id="concurrent-order",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Concurrent Order",
        topic="Ordering",
        count=11,
        config=PipelineConfig(generation_concurrency=3),
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with (
        patch.object(SuitePipeline, "_generate_batch", fake_generate_batch),
        patch.object(SuitePipeline, "_synthesize_rubric", fake_synthesize_rubric),
        patch.object(SuitePipeline, "_dedupe_questions", AsyncMock(side_effect=lambda questions: questions)),
    ):
        suite = await pipeline.run()

    db = session_factory()
    try:
        items = (
            db.query(PromptSuiteItem)
            .filter_by(suite_id=suite.id)
            .order_by(PromptSuiteItem.order)
            .all()
        )
        assert [item.user_prompt for item in items] == [
            "Question from batch 1.1",
            "Question from batch 1.2",
            "Question from batch 1.3",
            "Question from batch 1.4",
            "Question from batch 1.5",
            "Question from batch 2.1",
            "Question from batch 2.2",
            "Question from batch 2.3",
            "Question from batch 2.4",
            "Question from batch 2.5",
            "Question from batch 3.1",
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test: pipeline without reviewers generates rubric and saves suite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_without_reviewers_generates_rubric_and_saves_suite(
    generator_preset, session_factory
):
    """
    With 0 reviewers: generate → rubric → save.
    - generate() called once per batch (ceil(10/5) = 2 batches → 2 generate calls)
    - rubric synthesized once
    - PromptSuite + PromptSuiteItem rows saved
    - progress messages contain required keys
    """
    count = 10
    questions_batch1 = [_sample_question(i) for i in range(5)]
    questions_batch2 = [_sample_question(i) for i in range(5, 10)]
    rubric = [
        {"name": "Accuracy", "description": "Factually correct", "weight": 1.0},
        {"name": "Depth", "description": "Comprehensive analysis", "weight": 1.0},
        {"name": "Constraint Satisfaction", "description": "Addresses all constraints", "weight": 1.0},
    ]

    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        call_count[0] += 1
        n = call_count[0]
        if n == 1:
            return _make_generate_response(questions_batch1)
        elif n == 2:
            return _make_generate_response(questions_batch2)
        else:
            # rubric call
            return _make_rubric_response(rubric)

    manager = _make_manager()
    config = PipelineConfig(difficulty="balanced", generate_answers=True)
    pipeline = SuitePipeline(
        session_id="test-session-1",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Test Suite",
        topic="Distributed systems",
        count=count,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with (
        patch("app.core.suite_pipeline.generate", side_effect=fake_generate),
        patch.object(SuitePipeline, "_dedupe_questions", AsyncMock(side_effect=lambda questions: questions)),
    ):
        suite = await pipeline.run()

    # Suite saved
    assert suite is not None
    assert isinstance(suite, PromptSuite)
    assert suite.id is not None

    # Verify DB row
    db = session_factory()
    try:
        saved = db.query(PromptSuite).filter_by(id=suite.id).first()
        assert saved is not None
        assert saved.name == "Test Suite"
        assert saved.default_criteria is not None
        assert len(saved.default_criteria) == 3

        items = db.query(PromptSuiteItem).filter_by(suite_id=suite.id).all()
        assert len(items) == count  # 12 items

        # generate_answers=True → expected_answer must be populated
        for item in items:
            assert item.expected_answer is not None, (
                f"Item {item.order} has expected_answer=None with generate_answers=True"
            )
    finally:
        db.close()

    # generate() called: 2 generate batches + 1 rubric = 3 total
    assert call_count[0] == 3

    # Progress messages emitted with required keys
    assert manager.send_progress.call_count > 0
    for call in manager.send_progress.call_args_list:
        data = call.args[1] if call.args else call.kwargs.get("data", {})
        assert "type" in data
        # suite_progress messages must have phase, counters, overall_percent, phases list
        if data.get("type") == "suite_progress":
            assert "phase" in data
            assert "phases" in data
            assert "questions_generated" in data
            assert "question_count" in data
            assert "overall_percent" in data


# ---------------------------------------------------------------------------
# Test: generate_answers=False saves expected_answer as None
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_generate_answers_false_saves_expected_answer_as_none(
    generator_preset, session_factory
):
    """
    When generate_answers=False:
    - reference_answer key is present in JSON but value is null
    - PromptSuiteItem.expected_answer is saved as None
    """
    question_no_answer = _sample_question(0)
    question_no_answer["reference_answer"] = None

    rubric = [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]

    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_generate_response([question_no_answer])
        else:
            return _make_rubric_response(rubric)

    manager = _make_manager()
    config = PipelineConfig(generate_answers=False)
    pipeline = SuitePipeline(
        session_id="test-session-2",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="No Answers Suite",
        topic="Testing",
        count=1,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with (
        patch("app.core.suite_pipeline.generate", side_effect=fake_generate),
        patch.object(SuitePipeline, "_dedupe_questions", AsyncMock(side_effect=lambda questions: questions)),
    ):
        suite = await pipeline.run()

    db = session_factory()
    try:
        items = db.query(PromptSuiteItem).filter_by(suite_id=suite.id).all()
        assert len(items) == 1
        assert items[0].expected_answer is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test: cancellation before save does not commit suite
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_cancelled_before_review_does_not_save_partial_suite(
    generator_preset, session_factory
):
    """
    If _cancelled is set before save, no PromptSuite row is committed.
    """
    question = _sample_question(0)
    rubric = [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]

    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_generate_response([question])
        else:
            return _make_rubric_response(rubric)

    manager = _make_manager()
    config = PipelineConfig()
    pipeline = SuitePipeline(
        session_id="test-session-3",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Cancelled Suite",
        topic="Testing",
        count=1,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    # Cancel pipeline before it can save
    pipeline.cancel()

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        with pytest.raises(Exception):  # CancelledError or pipeline-specific exception
            await pipeline.run()

    # No suite should be saved
    db = session_factory()
    try:
        count = db.query(PromptSuite).count()
        assert count == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test: JSON fence stripping and retry on parse error
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_strips_json_fences_and_retries_once_on_parse_error(
    generator_preset, session_factory
):
    """
    - First call returns JSON wrapped in ```json fences → should parse OK after stripping
    - Second call (rubric) returns invalid JSON first → pipeline retries once → succeeds
    """
    question = _sample_question(0)
    rubric = [{"name": "Clarity", "description": "Clear language", "weight": 1.0}]

    fenced_questions = f"```json\n{json.dumps([question])}\n```"
    invalid_rubric = "This is not valid JSON at all..."
    valid_rubric = json.dumps(rubric)

    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_count[0] += 1
        n = call_count[0]
        if n == 1:
            # Return fenced JSON for questions
            return {"success": True, "content": fenced_questions, "tokens": 100, "error": None}
        elif n == 2:
            # First rubric attempt: invalid JSON
            return {"success": True, "content": invalid_rubric, "tokens": 50, "error": None}
        else:
            # Retry rubric: valid JSON
            return {"success": True, "content": valid_rubric, "tokens": 100, "error": None}

    manager = _make_manager()
    config = PipelineConfig()
    pipeline = SuitePipeline(
        session_id="test-session-4",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Fence Test Suite",
        topic="JSON parsing",
        count=1,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    assert suite is not None
    # call 1: generate batch, call 2: rubric attempt 1 (failed), call 3: rubric retry
    assert call_count[0] == 3

    db = session_factory()
    try:
        items = db.query(PromptSuiteItem).filter_by(suite_id=suite.id).all()
        assert len(items) == 1
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test: reviewer fan-out uses asyncio.gather (parallel review)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_reviewer_fanout_is_parallel(
    generator_preset, session_factory
):
    """
    With 2 reviewers: review calls should be issued in parallel via asyncio.gather.
    We track call ordering to verify both reviewers are called per batch.
    """
    questions = [_sample_question(0)]
    reviews = [_sample_review(questions[0])]
    rubric = [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]

    reviewer1 = _make_reviewer_preset(0)
    reviewer2 = _make_reviewer_preset(1)

    seen_presets = []
    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        seen_presets.append(preset.id)
        call_count[0] += 1
        n = call_count[0]
        if n == 1:
            # Initial generation
            return _make_generate_response(questions)
        elif n in (2, 3):
            # Review calls from reviewer1 and reviewer2
            return _make_review_response(reviews)
        elif n == 4:
            # Merge call
            return _make_generate_response(questions)
        else:
            # Rubric
            return _make_rubric_response(rubric)

    manager = _make_manager()
    config = PipelineConfig()
    pipeline = SuitePipeline(
        session_id="test-session-5",
        generator_preset=generator_preset,
        reviewer_presets=[reviewer1, reviewer2],
        name="Fanout Test Suite",
        topic="Testing",
        count=1,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    assert suite is not None
    # Both reviewers should have been called
    assert reviewer1.id in seen_presets
    assert reviewer2.id in seen_presets


@pytest.mark.asyncio
async def test_generate_and_review_overlap_starts_review_before_generation_finishes(
    generator_preset, session_factory
):
    reviewer = _make_reviewer_preset(5)
    second_generation_started = asyncio.Event()
    release_second_generation = asyncio.Event()
    second_generation_finished = asyncio.Event()
    review_started = asyncio.Event()
    release_review = asyncio.Event()

    async def fake_generate_batch(self, assignment):
        if assignment.generator_batch_index == 2:
            second_generation_started.set()
            await release_second_generation.wait()
            second_generation_finished.set()
        return [
            {
                **_sample_question((assignment.generator_batch_index - 1) * 10 + item_index),
                "user_prompt": f"Generated {assignment.generator_batch_index}.{item_index}",
            }
            for item_index in range(assignment.question_count)
        ]

    async def fake_review_batch(self, batch_questions, batch_index, total_batches):
        review_started.set()
        await release_review.wait()
        return ReviewBatchOutcome(
            task_id=f"review-batch-{batch_index}",
            batch_index=batch_index,
            total_batches=total_batches,
            questions=batch_questions,
            successful_reviews=[],
            required_reviewers=[reviewer.name],
            skipped_reviewers=[],
        )

    pipeline = SuitePipeline(
        session_id="overlap-review",
        generator_preset=generator_preset,
        reviewer_presets=[reviewer],
        name="Overlap Review",
        topic="Overlap",
        count=10,
        config=PipelineConfig(generation_concurrency=2, review_batch_concurrency=2),
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    task = None
    try:
        with (
            patch.object(SuitePipeline, "_generate_batch", fake_generate_batch),
            patch.object(SuitePipeline, "_review_batch", fake_review_batch),
        ):
            task = asyncio.create_task(
                pipeline._generate_and_review_across_generators([(generator_preset, 10)])
            )
            await asyncio.wait_for(second_generation_started.wait(), timeout=1)
            await asyncio.wait_for(review_started.wait(), timeout=1)
            assert not second_generation_finished.is_set()
            release_second_generation.set()
            release_review.set()
            outcomes = await asyncio.wait_for(task, timeout=1)
    finally:
        release_second_generation.set()
        release_review.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert [outcome.batch_index for outcome in outcomes] == [1, 2]


@pytest.mark.asyncio
async def test_generate_and_review_backfills_review_slots_when_one_finishes(
    generator_preset, session_factory
):
    reviewer = _make_reviewer_preset(6)
    first_two_reviews_started = asyncio.Event()
    third_review_started = asyncio.Event()
    release_review_one = asyncio.Event()
    release_review_two = asyncio.Event()
    release_review_three = asyncio.Event()
    active_reviews = 0
    max_active_reviews = 0
    started_batches: list[int] = []

    async def fake_generate_batch(self, assignment):
        return [
            {
                **_sample_question((assignment.generator_batch_index - 1) * 10 + item_index),
                "user_prompt": f"Generated {assignment.generator_batch_index}.{item_index}",
            }
            for item_index in range(assignment.question_count)
        ]

    async def fake_review_batch(self, batch_questions, batch_index, total_batches):
        nonlocal active_reviews, max_active_reviews
        started_batches.append(batch_index)
        active_reviews += 1
        max_active_reviews = max(max_active_reviews, active_reviews)
        if active_reviews >= 2:
            first_two_reviews_started.set()
        if batch_index == 1:
            await release_review_one.wait()
        elif batch_index == 2:
            await release_review_two.wait()
        else:
            third_review_started.set()
            await release_review_three.wait()
        active_reviews -= 1
        return ReviewBatchOutcome(
            task_id=f"review-batch-{batch_index}",
            batch_index=batch_index,
            total_batches=total_batches,
            questions=batch_questions,
            successful_reviews=[],
            required_reviewers=[reviewer.name],
            skipped_reviewers=[],
        )

    pipeline = SuitePipeline(
        session_id="backfill-review",
        generator_preset=generator_preset,
        reviewer_presets=[reviewer],
        name="Backfill Review",
        topic="Backfill",
        count=15,
        config=PipelineConfig(generation_concurrency=3, review_batch_concurrency=2),
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    task = None
    try:
        with (
            patch.object(SuitePipeline, "_generate_batch", fake_generate_batch),
            patch.object(SuitePipeline, "_review_batch", fake_review_batch),
        ):
            task = asyncio.create_task(
                pipeline._generate_and_review_across_generators([(generator_preset, 15)])
            )
            await asyncio.wait_for(first_two_reviews_started.wait(), timeout=1)
            assert started_batches[:2] == [1, 2]
            assert not third_review_started.is_set()
            release_review_one.set()
            await asyncio.wait_for(third_review_started.wait(), timeout=1)
            release_review_two.set()
            release_review_three.set()
            outcomes = await asyncio.wait_for(task, timeout=1)
    finally:
        release_review_one.set()
        release_review_two.set()
        release_review_three.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert max_active_reviews == 2
    assert started_batches == [1, 2, 3]
    assert [outcome.batch_index for outcome in outcomes] == [1, 2, 3]


@pytest.mark.asyncio
async def test_merge_batches_can_run_concurrently(
    generator_preset, session_factory
):
    reviewer = _make_reviewer_preset(8)
    release_merge = asyncio.Event()
    first_two_merges_started = asyncio.Event()
    active_merges = 0
    max_active_merges = 0

    outcomes = [
        ReviewBatchOutcome(
            task_id="review-batch-1",
            batch_index=1,
            total_batches=2,
            questions=[{**_sample_question(1), "user_prompt": "Merged 1"}],
            successful_reviews=[[{"revised": _sample_question(1)}]],
            required_reviewers=[reviewer.name],
            skipped_reviewers=[],
        ),
        ReviewBatchOutcome(
            task_id="review-batch-2",
            batch_index=2,
            total_batches=2,
            questions=[{**_sample_question(2), "user_prompt": "Merged 2"}],
            successful_reviews=[[{"revised": _sample_question(2)}]],
            required_reviewers=[reviewer.name],
            skipped_reviewers=[],
        ),
    ]

    async def fake_merge_batch(self, questions, all_reviews, batch_index, total_batches):
        nonlocal active_merges, max_active_merges
        active_merges += 1
        max_active_merges = max(max_active_merges, active_merges)
        if active_merges >= 2:
            first_two_merges_started.set()
        await release_merge.wait()
        active_merges -= 1
        return questions

    pipeline = SuitePipeline(
        session_id="concurrent-merge",
        generator_preset=generator_preset,
        reviewer_presets=[reviewer],
        name="Concurrent Merge",
        topic="Concurrency",
        count=10,
        config=PipelineConfig(review_batch_concurrency=2),
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    task = None
    try:
        with patch.object(SuitePipeline, "_merge_batch", fake_merge_batch):
            task = asyncio.create_task(pipeline._merge_review_outcomes(outcomes))
            await asyncio.wait_for(first_two_merges_started.wait(), timeout=1)
            release_merge.set()
            merged_questions = await asyncio.wait_for(task, timeout=1)
    finally:
        release_merge.set()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    assert max_active_merges == 2
    assert [question["user_prompt"] for question in merged_questions] == ["Merged 1", "Merged 2"]


@pytest.mark.asyncio
async def test_generate_and_review_resume_skips_checkpointed_batches(
    generator_preset, session_factory
):
    reviewer = _make_reviewer_preset(7)
    restored_batch_questions = [_sample_question(index) for index in range(5)]
    called_generation_batches: list[int] = []
    called_review_batches: list[int] = []

    async def fake_generate_batch(self, assignment):
        called_generation_batches.append(assignment.generator_batch_index)
        return [
            _sample_question(100 + item_index)
            for item_index in range(assignment.question_count)
        ]

    async def fake_review_batch(self, batch_questions, batch_index, total_batches):
        called_review_batches.append(batch_index)
        return ReviewBatchOutcome(
            task_id=f"review-batch-{batch_index}",
            batch_index=batch_index,
            total_batches=total_batches,
            questions=batch_questions,
            successful_reviews=[],
            required_reviewers=[reviewer.name],
            skipped_reviewers=[],
        )

    resume_checkpoint = {
        "generation_results": [
            {
                "task_id": "generator-1-batch-1-global-1",
                "questions": restored_batch_questions,
            },
        ],
        "review_outcomes": [
            {
                "task_id": "review-batch-1",
                "batch_index": 1,
                "total_batches": 2,
                "questions": restored_batch_questions,
                "successful_reviews": [],
                "required_reviewers": [reviewer.name],
                "skipped_reviewers": [],
            },
        ],
        "merged_batches": [],
        "prepared_questions": None,
        "rubric": None,
        "coverage_validation_results": {},
        "dedupe_report": None,
    }

    pipeline = SuitePipeline(
        session_id="resume-review-batches",
        generator_preset=generator_preset,
        reviewer_presets=[reviewer],
        name="Resume Review Batches",
        topic="Resume",
        count=10,
        config=PipelineConfig(generation_concurrency=2, review_batch_concurrency=2),
        resume_checkpoint=resume_checkpoint,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with (
        patch.object(SuitePipeline, "_generate_batch", fake_generate_batch),
        patch.object(SuitePipeline, "_review_batch", fake_review_batch),
    ):
        outcomes = await pipeline._generate_and_review_across_generators([(generator_preset, 10)])

    assert called_generation_batches == [2]
    assert called_review_batches == [2]
    assert [outcome.batch_index for outcome in outcomes] == [1, 2]


# ---------------------------------------------------------------------------
# Test: batch sizes respect batch_size=10 cap
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_batch_sizes_are_capped_at_5(
    generator_preset, session_factory
):
    """
    For count=12, pipeline should call generate 3 times (5+5+2).
    """
    from app.core.suite_pipeline import _BATCH_SIZE

    count = 12
    expected_batches = ceil(count / _BATCH_SIZE)  # 3

    batch_calls = []

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        is_rubric = len(batch_calls) >= expected_batches
        if is_rubric:
            return _make_rubric_response([
                {"name": "Accuracy", "description": "Correct", "weight": 1.0}
            ])
        else:
            batch_size_hint = _BATCH_SIZE if len(batch_calls) < expected_batches - 1 else (count % _BATCH_SIZE or _BATCH_SIZE)
            batch_calls.append(batch_size_hint)
            qs = [_sample_question(i) for i in range(batch_size_hint)]
            return _make_generate_response(qs)

    manager = _make_manager()
    config = PipelineConfig()
    pipeline = SuitePipeline(
        session_id="test-session-6",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Batch Size Test",
        topic="Testing",
        count=count,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    assert suite is not None
    assert len(batch_calls) == expected_batches  # 3 batch generate calls


# ---------------------------------------------------------------------------
# Test: log emission, retry resilience, partial save, and snapshot hydration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_emits_log_events_via_websocket(generator_preset, session_factory):
    """Log events are sent via suite_manager and stored in pipeline._log."""
    questions = [_sample_question(i) for i in range(5)]
    rubric = [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]
    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_generate_response(questions)
        return _make_rubric_response(rubric)

    manager = _make_manager()
    pipeline = SuitePipeline(
        session_id="test-log-session",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Log Test",
        topic="Testing",
        count=5,
        config=PipelineConfig(),
        suite_manager=manager,
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        await pipeline.run()

    assert len(pipeline._log) > 0, "Pipeline should have log entries"
    log_events = [
        call.args[1] if call.args else call.kwargs.get("data", {})
        for call in manager.send_progress.call_args_list
        if (call.args[1] if call.args else call.kwargs.get("data", {})).get("type") == "suite_log"
    ]
    assert len(log_events) > 0, "Should have sent suite_log events"
    for evt in log_events:
        assert "timestamp" in evt
        assert "level" in evt
        assert "message" in evt
        assert evt["level"] in ("info", "warning", "error")
    assert "Started pipeline" in pipeline._log[0]["message"]


@pytest.mark.asyncio
async def test_pipeline_retries_on_generate_failure(generator_preset, session_factory):
    """Generate fails once, retries, succeeds on second attempt."""
    questions = [_sample_question(i) for i in range(5)]
    rubric = [{"name": "Acc", "description": "Correct", "weight": 1.0}]
    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        call_count[0] += 1
        if call_count[0] == 1:
            return {"success": False, "error": "Rate limited"}
        if "rubric" in system_prompt.lower():
            return _make_rubric_response(rubric)
        return _make_generate_response(questions)

    manager = _make_manager()
    pipeline = SuitePipeline(
        session_id="test-retry",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Retry Test",
        topic="Testing",
        count=5,
        config=PipelineConfig(),
        suite_manager=manager,
        session_factory=session_factory,
    )

    with (
        patch("app.core.suite_pipeline.generate", side_effect=fake_generate),
        patch("app.core.suite_pipeline.asyncio.sleep", new=AsyncMock()),
    ):
        suite = await pipeline.run()

    assert suite is not None
    retry_logs = [e for e in pipeline._log if "retry" in e["message"].lower() or "⟳" in e["message"]]
    assert len(retry_logs) > 0, "Should have logged the retry"


@pytest.mark.asyncio
async def test_pipeline_reviewer_skip_after_retries_exhausted(generator_preset, session_factory):
    """Reviewer fails all retries, is skipped, and pipeline continues."""
    questions = [_sample_question(i) for i in range(5)]
    rubric = [{"name": "Acc", "description": "Correct", "weight": 1.0}]
    reviewer_preset = _make_reviewer_preset(9)
    reviewer_preset.name = "Bad Reviewer"
    reviewer_preset.model_id = "bad/reviewer"

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        if preset.name == "Bad Reviewer":
            return {"success": False, "error": "Service unavailable"}
        if "merge" in system_prompt.lower():
            return _make_generate_response(questions)
        if "rubric" in system_prompt.lower():
            return _make_rubric_response(rubric)
        return _make_generate_response(questions)

    manager = _make_manager()
    pipeline = SuitePipeline(
        session_id="test-skip-reviewer",
        generator_preset=generator_preset,
        reviewer_presets=[reviewer_preset],
        name="Skip Test",
        topic="Testing",
        count=5,
        config=PipelineConfig(),
        suite_manager=manager,
        session_factory=session_factory,
    )

    with (
        patch("app.core.suite_pipeline.generate", side_effect=fake_generate),
        patch("app.core.suite_pipeline.asyncio.sleep", new=AsyncMock()),
    ):
        suite = await pipeline.run()

    assert suite is not None
    skip_logs = [e for e in pipeline._log if "skipped" in e["message"].lower()]
    assert len(skip_logs) > 0


@pytest.mark.asyncio
async def test_pipeline_partial_save_on_generate_failure_after_completed_batches(
    generator_preset, session_factory
):
    """If generate fails on batch 2, batch 1 is saved as a partial suite."""
    questions_b1 = [_sample_question(i) for i in range(5)]
    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_generate_response(questions_b1)
        return {"success": False, "error": "Model overloaded"}

    manager = _make_manager()
    pipeline = SuitePipeline(
        session_id="test-partial",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Partial Test",
        topic="Testing",
        count=10,
        config=PipelineConfig(),
        suite_manager=manager,
        session_factory=session_factory,
    )

    with (
        patch("app.core.suite_pipeline.generate", side_effect=fake_generate),
        patch("app.core.suite_pipeline.asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(Exception):
            await pipeline.run()

    assert pipeline._partial_suite is not None
    assert pipeline._partial_suite.name == "Partial Test [PARTIAL]"
    assert pipeline.saved_count == 5

    db = session_factory()
    try:
        items = db.query(PromptSuiteItem).filter_by(suite_id=pipeline._partial_suite.id).all()
        assert len(items) == 5
    finally:
        db.close()


@pytest.mark.asyncio
async def test_pipeline_review_provenance_in_description(generator_preset, session_factory):
    """Suite description includes review coverage per batch."""
    reviewer_preset = _make_reviewer_preset(8)
    reviewer_preset.name = "Flaky Reviewer"
    reviewer_preset.model_id = "flaky/model"
    questions = [_sample_question(i) for i in range(5)]
    rubric = [{"name": "Acc", "description": "Correct", "weight": 1.0}]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        if preset.name == "Flaky Reviewer":
            return {"success": False, "error": "Model overloaded"}
        if "merge" in system_prompt.lower():
            return _make_generate_response(questions)
        if "rubric" in system_prompt.lower():
            return _make_rubric_response(rubric)
        return _make_generate_response(questions)

    manager = _make_manager()
    pipeline = SuitePipeline(
        session_id="test-provenance",
        generator_preset=generator_preset,
        reviewer_presets=[reviewer_preset],
        name="Provenance Test",
        topic="Testing",
        count=5,
        config=PipelineConfig(),
        suite_manager=manager,
        session_factory=session_factory,
    )

    with (
        patch("app.core.suite_pipeline.generate", side_effect=fake_generate),
        patch("app.core.suite_pipeline.asyncio.sleep", new=AsyncMock()),
    ):
        suite = await pipeline.run()

    assert suite is not None
    desc = suite.description or ""
    assert "review" in desc.lower() or "coverage" in desc.lower() or "skipped" in desc.lower()


def test_pipeline_snapshot_returns_full_activity_state(generator_preset, session_factory):
    """snapshot() returns all fields needed for reconnect hydration."""
    pipeline = SuitePipeline(
        session_id="test-snapshot",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Snapshot Test",
        topic="Testing",
        count=5,
        config=PipelineConfig(),
        suite_manager=None,
        session_factory=session_factory,
    )

    snap = pipeline.snapshot()
    required_keys = [
        "session_id", "name", "phase", "phase_index", "total_phases",
        "phases", "batch", "total_batches", "overall_percent",
        "call_started_at", "model", "reviewers_status",
        "questions_generated", "questions_reviewed", "questions_merged",
        "question_count", "coverage_mode", "required_leaf_count",
        "covered_leaf_count", "missing_leaf_count", "duplicate_cluster_count",
        "replacement_count", "completed_generation_batches", "active_generation_batches",
        "active_generation_calls", "active_review_batches", "generator", "reviewers",
        "elapsed_seconds", "recent_log",
    ]
    for key in required_keys:
        assert key in snap, f"Missing '{key}' in snapshot"


@pytest.mark.asyncio
async def test_pipeline_multiple_generators_use_editor_and_interleave_outputs(session_factory):
    """Generator pools should interleave outputs and use a separate editor for rubric synthesis."""
    gen_a = _make_preset("Generator A")
    gen_a.id = 11
    gen_a.model_id = "gen/a"
    gen_b = _make_preset("Generator B")
    gen_b.id = 12
    gen_b.model_id = "gen/b"
    editor = _make_preset("Editor")
    editor.id = 13
    editor.model_id = "editor/model"

    reviewer = _make_reviewer_preset(4)
    reviewer.name = "Reviewer 3"
    reviewer.model_id = "reviewer/model"

    call_log: list[tuple[str, str]] = []

    def extract_json_block(text: str, start_marker: str, end_marker: str) -> list[dict]:
        start = text.index(start_marker) + len(start_marker)
        end = text.index(end_marker, start)
        return json.loads(text[start:end].strip())

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_log.append((preset.name, system_prompt))
        lower = system_prompt.lower()
        if preset.id == gen_a.id:
            return _make_generate_response([
                _sample_question(0),
                _sample_question(2),
            ])
        if preset.id == gen_b.id:
            return _make_generate_response([
                _sample_question(1),
            ])
        if preset.id == reviewer.id:
            questions = extract_json_block(user_prompt, "Questions to review:\n", "\nReturn your review array now.")
            return _make_review_response([_sample_review(question) for question in questions])
        if preset.id == editor.id and "strongest version" in lower:
            questions = extract_json_block(user_prompt, "Original questions:\n", "\nReviewer critiques and revisions:")
            return _make_generate_response(questions)
        if preset.id == editor.id and "rubric" in lower:
            return _make_rubric_response([
                {"name": "Accuracy", "description": "Correct", "weight": 1.0},
            ])
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        raise AssertionError(f"Unexpected preset {preset.name}")

    manager = _make_manager()
    pipeline = SuitePipeline(
        session_id="test-multi-generator",
        generator_presets=[gen_a, gen_b],
        editor_preset=editor,
        reviewer_presets=[reviewer],
        name="Multi Generator Test",
        topic="Testing",
        count=3,
        config=PipelineConfig(),
        suite_manager=manager,
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    assert suite is not None

    db = session_factory()
    try:
        items = db.query(PromptSuiteItem).filter_by(suite_id=suite.id).order_by(PromptSuiteItem.order).all()
        assert [item.user_prompt for item in items] == [
            "Complex question 0 with constraints A and B.",
            "Complex question 1 with constraints A and B.",
            "Complex question 2 with constraints A and B.",
        ]
    finally:
        db.close()

    snap = pipeline.snapshot()
    assert snap["generators"] == ["Generator A", "Generator B"]
    assert snap["editor"] == "Editor"
    assert any("Scheduled generator" in entry["message"] for entry in pipeline._log)
    assert any(name == "Editor" and "merge" in prompt.lower() for name, prompt in call_log)
    assert any(name == "Editor" and "rubric" in prompt.lower() for name, prompt in call_log)


@pytest.mark.asyncio
async def test_generate_and_review_starts_review_before_all_generation_finishes(session_factory):
    gen_a = _make_preset("Generator A")
    gen_a.id = 41
    gen_b = _make_preset("Generator B")
    gen_b.id = 42
    reviewer = _make_reviewer_preset(9)

    second_wave_release = asyncio.Event()
    review_release = asyncio.Event()
    review_started = asyncio.Event()
    started_blocked_generation_batches: list[str] = []

    pipeline = SuitePipeline(
        session_id="test-overlap-generate-review",
        generator_presets=[gen_a, gen_b],
        reviewer_presets=[reviewer],
        name="Overlap Test",
        topic="Testing",
        count=20,
        config=PipelineConfig(generation_concurrency=4, review_batch_concurrency=2),
        suite_manager=None,
        session_factory=session_factory,
    )

    async def fake_generate_batch(self, assignment):
        if assignment.generator_batch_index > 1:
            started_blocked_generation_batches.append(assignment.task_id)
            await second_wave_release.wait()
        return [_sample_question(index) for index in assignment.final_order_indices or []]

    async def fake_review_batch(self, batch_questions, batch_index, total_batches):
        review_started.set()
        await review_release.wait()
        return ReviewBatchOutcome(
            task_id=f"review-batch-{batch_index}",
            batch_index=batch_index,
            total_batches=total_batches,
            questions=batch_questions,
            successful_reviews=[],
            required_reviewers=[reviewer.name],
            skipped_reviewers=[],
        )

    with (
        patch.object(SuitePipeline, "_generate_batch", new=fake_generate_batch),
        patch.object(SuitePipeline, "_review_batch", new=fake_review_batch),
    ):
        task = asyncio.create_task(
            pipeline._generate_and_review_across_generators([(gen_a, 10), (gen_b, 10)]),
        )
        await asyncio.wait_for(review_started.wait(), timeout=1)
        assert len(started_blocked_generation_batches) == 2
        assert not task.done()
        review_release.set()
        second_wave_release.set()
        outcomes = await asyncio.wait_for(task, timeout=1)

    assert len(outcomes) == 4


@pytest.mark.asyncio
async def test_generate_and_review_backfills_review_batches_up_to_concurrency(session_factory):
    gen_a = _make_preset("Generator A")
    gen_a.id = 51
    gen_b = _make_preset("Generator B")
    gen_b.id = 52
    reviewer = _make_reviewer_preset(10)

    release_events = {index: asyncio.Event() for index in range(1, 5)}
    first_review_wave_ready = asyncio.Event()
    batch3_started = asyncio.Event()
    started_batches: list[int] = []
    active = 0
    max_active = 0

    pipeline = SuitePipeline(
        session_id="test-review-backfill",
        generator_presets=[gen_a, gen_b],
        reviewer_presets=[reviewer],
        name="Review Backfill Test",
        topic="Testing",
        count=20,
        config=PipelineConfig(generation_concurrency=4, review_batch_concurrency=2),
        suite_manager=None,
        session_factory=session_factory,
    )

    async def fake_generate_batch(self, assignment):
        return [_sample_question(index) for index in assignment.final_order_indices or []]

    async def fake_review_batch(self, batch_questions, batch_index, total_batches):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        started_batches.append(batch_index)
        if 1 in started_batches and 2 in started_batches:
            first_review_wave_ready.set()
        if batch_index == 3:
            batch3_started.set()
        await release_events[batch_index].wait()
        active -= 1
        return ReviewBatchOutcome(
            task_id=f"review-batch-{batch_index}",
            batch_index=batch_index,
            total_batches=total_batches,
            questions=batch_questions,
            successful_reviews=[],
            required_reviewers=[reviewer.name],
            skipped_reviewers=[],
        )

    with (
        patch.object(SuitePipeline, "_generate_batch", new=fake_generate_batch),
        patch.object(SuitePipeline, "_review_batch", new=fake_review_batch),
    ):
        task = asyncio.create_task(
            pipeline._generate_and_review_across_generators([(gen_a, 10), (gen_b, 10)]),
        )
        await asyncio.wait_for(first_review_wave_ready.wait(), timeout=1)
        assert max_active == 2

        release_events[1].set()
        await asyncio.wait_for(batch3_started.wait(), timeout=1)
        assert max_active == 2

        for event in release_events.values():
            event.set()
        outcomes = await asyncio.wait_for(task, timeout=1)

    assert len(outcomes) == 4
    assert started_batches[:3] == [1, 2, 3]


@pytest.mark.asyncio
async def test_pipeline_coverage_mode_uses_plan_phase_and_batches_assignments(
    generator_preset, session_factory
):
    """Coverage mode should add plan phase and batch slot assignments up to 4 per call."""
    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. LLM Integration & Orchestration",
                "leaves": [
                    {"id": "a.api", "label": "Multi-provider API abstraction"},
                    {"id": "a.reasoning", "label": "Reasoning mode handling"},
                    {"id": "a.streaming", "label": "Streaming responses"},
                    {"id": "a.json", "label": "JSON output parsing"},
                    {"id": "a.tokens", "label": "Token counting and budget management"},
                ],
            }
        ],
    }

    call_sizes: list[int] = []

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            return _make_generate_response([
                {
                    "slot_index": question["slot_index"],
                    "coverage_status": "covered",
                    "reason": "covers assigned leaf topic",
                }
                for question in questions
            ])
        if "Coverage assignments:" in user_prompt:
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            call_sizes.append(len(assignments))
            questions = []
            for assignment in assignments:
                questions.append({
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"Question for {assignment['slot_label']}",
                })
            return _make_generate_response(questions)
        return _make_rubric_response([
            {"name": "Accuracy", "description": "Correct", "weight": 1.0}
        ])

    manager = _make_manager()
    pipeline = SuitePipeline(
        session_id="test-coverage-plan",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Coverage Plan Test",
        topic="Coverage topic",
        count=5,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with (
        patch("app.core.suite_pipeline.generate", side_effect=fake_generate),
        patch.object(SuitePipeline, "_dedupe_questions", AsyncMock(side_effect=lambda questions: questions)),
    ):
        suite = await pipeline.run()

    assert suite is not None
    assert call_sizes == [4, 1]

    progress_messages = [
        (call.args[1] if call.args else call.kwargs.get("data", {}))
        for call in manager.send_progress.call_args_list
        if (call.args[1] if call.args else call.kwargs.get("data", {})).get("type") == "suite_progress"
    ]
    assert progress_messages[0]["phase"] == "plan"
    assert "plan" in progress_messages[0]["phases"]


@pytest.mark.asyncio
async def test_pipeline_strict_coverage_generates_requested_count_when_count_exceeds_leaf_count(
    generator_preset, session_factory
):
    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. Coverage",
                "leaves": [
                    {"id": "a.one", "label": "Leaf One"},
                    {"id": "a.two", "label": "Leaf Two"},
                    {"id": "a.three", "label": "Leaf Three"},
                ],
            }
        ],
    }

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            return _make_generate_response([
                {
                    "slot_index": question["slot_index"],
                    "coverage_status": "covered",
                    "reason": "slot validated",
                }
                for question in questions
            ])
        if "Coverage assignments:" in user_prompt:
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            return _make_generate_response([
                {
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"Question for {assignment['slot_label']}",
                }
                for assignment in assignments
            ])
        return _make_rubric_response([
            {"name": "Accuracy", "description": "Correct", "weight": 1.0}
        ])

    pipeline = SuitePipeline(
        session_id="strict-coverage-extra-count",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Strict Coverage Extra Count",
        topic="Coverage topic",
        count=6,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    db = session_factory()
    try:
        items = (
            db.query(PromptSuiteItem)
            .filter_by(suite_id=suite.id)
            .order_by(PromptSuiteItem.order)
            .all()
        )
        assert len(items) == 6
        assert [item.generation_slot_index for item in items] == list(range(6))
        assert [item.coverage_topic_ids for item in items] == [
            ["a.one"],
            ["a.two"],
            ["a.three"],
            ["a.one"],
            ["a.two"],
            ["a.three"],
        ]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_pipeline_coverage_mode_distributes_slots_deterministically_across_generators(
    session_factory
):
    """Coverage slots should be assigned to generators deterministically in generator order."""
    gen_a = _make_preset("Generator A")
    gen_a.id = 21
    gen_b = _make_preset("Generator B")
    gen_b.id = 22

    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. Full Stack Web Development",
                "leaves": [
                    {"id": "a.fastapi", "label": "Python backends"},
                    {"id": "a.react", "label": "React frontends"},
                    {"id": "a.ui", "label": "UI systems"},
                    {"id": "a.realtime", "label": "Real-time"},
                    {"id": "a.viz", "label": "Data viz"},
                ],
            }
        ],
    }

    generator_calls: list[tuple[str, int]] = []

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            return _make_generate_response([
                {
                    "slot_index": question["slot_index"],
                    "coverage_status": "covered",
                    "reason": f"{question['user_prompt']} covers assigned leaf topic",
                }
                for question in questions
            ])
        if "Coverage assignments:" in user_prompt:
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            generator_calls.append((preset.name, len(assignments)))
            questions = []
            for assignment in assignments:
                questions.append({
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"{preset.name} covers {assignment['slot_label']}",
                })
            return _make_generate_response(questions)
        return _make_rubric_response([
            {"name": "Accuracy", "description": "Correct", "weight": 1.0}
        ])

    pipeline = SuitePipeline(
        session_id="test-coverage-generators",
        generator_presets=[gen_a, gen_b],
        editor_preset=gen_a,
        reviewer_presets=[],
        name="Coverage Generator Test",
        topic="Coverage topic",
        count=5,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    assert suite is not None
    assert generator_calls == [("Generator A", 3), ("Generator B", 2)]


@pytest.mark.asyncio
async def test_pipeline_strict_coverage_respects_requested_count_when_it_exceeds_leaf_count(
    generator_preset, session_factory
):
    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. Coverage",
                "leaves": [
                    {"id": "a.one", "label": "One"},
                    {"id": "a.two", "label": "Two"},
                ],
            }
        ],
    }

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            return _make_generate_response([
                {
                    "slot_index": question["slot_index"],
                    "coverage_status": "covered",
                    "reason": f"slot {question['slot_index']} validated",
                }
                for question in questions
            ])
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        if "Coverage assignments:" in user_prompt:
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            return _make_generate_response([
                {
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"Question for slot {assignment['slot_index']}",
                }
                for assignment in assignments
            ])
        return _make_rubric_response([
            {"name": "Accuracy", "description": "Correct", "weight": 1.0}
        ])

    pipeline = SuitePipeline(
        session_id="strict-count-repeat",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Strict Count Repeat",
        topic="Coverage topic",
        count=4,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with (
        patch("app.core.suite_pipeline.generate", side_effect=fake_generate),
        patch.object(SuitePipeline, "_dedupe_questions", AsyncMock(side_effect=lambda questions: questions)),
    ):
        suite = await pipeline.run()

    db = session_factory()
    try:
        items = (
            db.query(PromptSuiteItem)
            .filter_by(suite_id=suite.id)
            .order_by(PromptSuiteItem.order)
            .all()
        )
        assert len(items) == 4
        assert [item.generation_slot_index for item in items] == [0, 1, 2, 3]
        assert [item.coverage_topic_ids for item in items] == [
            ["a.one"],
            ["a.two"],
            ["a.one"],
            ["a.two"],
        ]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_pipeline_coverage_context_digest_is_used_in_generation_prompt(
    generator_preset, session_factory
):
    """Coverage mode should summarize context once and reuse the digest in generation prompts."""
    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. LLM Integration & Orchestration",
                "leaves": [
                    {"id": "a.api", "label": "Multi-provider API abstraction"},
                    {"id": "a.streaming", "label": "Streaming responses"},
                ],
            }
        ],
    }

    call_log: list[tuple[str, str]] = []
    digest_text = "DIGEST: condensed coverage context for orchestration and streaming"
    raw_context = "RAW CONTEXT: this should not appear in coverage generation prompts"

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_log.append((system_prompt, user_prompt))
        if system_prompt == COVERAGE_DIGEST_SYSTEM_PROMPT:
            assert raw_context in user_prompt
            return {"success": True, "content": digest_text, "tokens": 20, "error": None}
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            return _make_generate_response([
                {
                    "slot_index": question["slot_index"],
                    "coverage_status": "covered",
                    "reason": "coverage matches",
                }
                for question in questions
            ])
        if "Coverage assignments:" in user_prompt:
            assert digest_text in user_prompt
            assert raw_context not in user_prompt
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            questions = []
            for assignment in assignments:
                questions.append({
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"Question for {assignment['slot_label']}",
                })
            return _make_generate_response(questions)
        return _make_rubric_response([
            {"name": "Accuracy", "description": "Correct", "weight": 1.0}
        ])

    pipeline = SuitePipeline(
        session_id="test-coverage-digest",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Coverage Digest Test",
        topic="Coverage topic",
        count=2,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        context_attachment_id=1,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )
    pipeline._load_context_attachment = lambda: raw_context

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    assert suite is not None
    assert pipeline._context_digest == digest_text
    assert any(system_prompt == COVERAGE_DIGEST_SYSTEM_PROMPT for system_prompt, _ in call_log)
    assert any(
        "Coverage assignments:" in user_prompt and digest_text in user_prompt
        for _, user_prompt in call_log
    )


@pytest.mark.asyncio
async def test_pipeline_coverage_validation_batches_results_by_slot_index(
    generator_preset, session_factory
):
    """Coverage validation should batch questions and keep results keyed by generation_slot_index."""
    leaves = [
        {"id": f"a.leaf-{index}", "label": f"Leaf {index}"}
        for index in range(11)
    ]
    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. LLM Integration & Orchestration",
                "leaves": leaves,
            }
        ],
    }

    validate_batch_sizes: list[int] = []
    validation_statuses: dict[int, str] = {}

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            validate_batch_sizes.append(len(questions))
            response = []
            for question in questions:
                slot_index = question["slot_index"]
                status = "covered"
                validation_statuses[slot_index] = status
                response.append({
                    "slot_index": slot_index,
                    "coverage_status": status,
                    "reason": f"slot {slot_index} classified as {status}",
                })
            return _make_generate_response(response)
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            pairs = _extract_json_between_markers(
                user_prompt,
                "Pairs:\n",
                "\n\nReturn the adjudication JSON array now.",
            )
            return _make_generate_response([
                {
                    "pair_index": pair["pair_index"],
                    "label": "distinct",
                    "keep_index": pair["left_index"],
                    "reason": "validation test keeps all slots distinct",
                }
                for pair in pairs
            ])
        if "Coverage assignments:" in user_prompt:
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            questions = []
            for assignment in assignments:
                questions.append({
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"Question for {assignment['slot_label']}",
                })
            return _make_generate_response(questions)
        return _make_rubric_response([
            {"name": "Accuracy", "description": "Correct", "weight": 1.0}
        ])

    pipeline = SuitePipeline(
        session_id="test-coverage-validate",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Coverage Validation Test",
        topic="Coverage topic",
        count=11,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    assert suite is not None
    assert validate_batch_sizes == [10, 1]
    assert pipeline._coverage_validation_results.keys() == set(range(11))
    assert {
        slot_index: result["coverage_status"]
        for slot_index, result in pipeline._coverage_validation_results.items()
    } == validation_statuses
    assert all("slot_index" in result for result in pipeline._coverage_validation_results.values())


@pytest.mark.asyncio
async def test_pipeline_dedupe_removes_duplicate_and_generates_replacement(session_factory):
    """A duplicate question should be removed and replaced so the final suite count stays fixed."""
    generator = _make_preset("Generator")
    duplicate_questions = [
        {
            **_sample_question(0),
            "user_prompt": "Explain SSE streaming in detail.",
        },
        {
            **_sample_question(1),
            "user_prompt": "Explain SSE streaming in detail.",
        },
    ]
    replacement_question = {
        **_sample_question(2),
        "user_prompt": "Design a websocket relay with backpressure and reconnect handling.",
    }
    rubric = [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_generate_response([
                {
                    "pair_index": 0,
                    "label": "duplicate",
                    "keep_index": 0,
                    "reason": "same prompt with trivial wording changes",
                }
            ])
        if "Repair targets:" in user_prompt:
            return _make_generate_response([replacement_question])
        if "Generate exactly 2 questions." in user_prompt:
            return _make_generate_response(duplicate_questions)
        if "rubric" in system_prompt.lower():
            return _make_rubric_response(rubric)
        raise AssertionError(f"Unexpected prompt path: {preset.name} / {system_prompt[:40]}")

    pipeline = SuitePipeline(
        session_id="test-dedupe-repair",
        generator_preset=generator,
        reviewer_presets=[],
        name="Dedupe Repair Test",
        topic="Distributed systems",
        count=2,
        config=PipelineConfig(),
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    assert suite is not None

    db = session_factory()
    try:
        items = db.query(PromptSuiteItem).filter_by(suite_id=suite.id).order_by(PromptSuiteItem.order).all()
        assert len(items) == 2
        assert items[0].user_prompt == "Explain SSE streaming in detail."
        assert items[1].user_prompt == "Design a websocket relay with backpressure and reconnect handling."
    finally:
        db.close()


@pytest.mark.asyncio
async def test_pipeline_strict_coverage_fails_partial_when_leaf_remains_uncovered(
    generator_preset, session_factory
):
    """Strict coverage should partial-save when an assigned leaf remains uncovered after validation."""
    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. LLM Integration & Orchestration",
                "leaves": [
                    {"id": "a.one", "label": "Multi-provider API abstraction"},
                    {"id": "a.two", "label": "Streaming responses"},
                ],
            }
        ],
    }

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            return _make_generate_response([
                {
                    "slot_index": question["slot_index"],
                    "coverage_status": "covered" if question["slot_index"] == 0 else "not_covered",
                    "reason": "slot validated",
                }
                for question in questions
            ])
        if "Coverage assignments:" in user_prompt:
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            return _make_generate_response([
                {
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"Question for {assignment['slot_label']}",
                }
                for assignment in assignments
            ])
        raise AssertionError(f"Unexpected prompt path: {preset.name} / {system_prompt[:40]}")

    pipeline = SuitePipeline(
        session_id="test-uncovered-partial",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Strict Coverage Partial",
        topic="Coverage topic",
        count=2,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        with pytest.raises(Exception):
            await pipeline.run()

    assert pipeline._partial_suite is not None

    db = session_factory()
    try:
        saved_suite = db.query(PromptSuite).filter_by(id=pipeline._partial_suite.id).first()
        assert saved_suite is not None
        assert saved_suite.name.endswith("[PARTIAL]")
        assert saved_suite.generation_metadata["coverage_mode"] == "strict_leaf_coverage"
        assert saved_suite.coverage_report["uncovered_leaf_ids"] == ["a.two"]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_pipeline_strict_coverage_with_reviewers_preserves_slot_metadata_through_merge(
    generator_preset, reviewer_presets, session_factory
):
    """Reviewer + merge flows must preserve slot metadata for strict coverage validation."""
    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. Coverage",
                "leaves": [
                    {"id": "a.one", "label": "Server-Sent Events"},
                    {"id": "a.two", "label": "WebSocket"},
                ],
            }
        ],
    }
    rubric = [
        {"name": "Accuracy", "description": "Factually correct", "weight": 1.0},
        {"name": "Completeness", "description": "Addresses all requirements", "weight": 1.0},
        {"name": "Robustness", "description": "Production-aware solution", "weight": 1.0},
    ]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            assert [question["slot_index"] for question in questions] == [0, 1]
            assert [question["coverage_topic_ids"] for question in questions] == [["a.one"], ["a.two"]]
            return _make_generate_response([
                {
                    "slot_index": question["slot_index"],
                    "coverage_status": "covered",
                    "reason": "slot metadata preserved through merge",
                }
                for question in questions
            ])
        if system_prompt == DEDUPE_ADJUDICATOR_SYSTEM_PROMPT:
            return _make_distinct_dedupe_response(user_prompt)
        if system_prompt == REVIEWER_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions to review:\n",
                "\n\nReturn your review array now.",
            )
            return _make_review_response([
                {
                    "scores": {
                        "specificity": 4,
                        "discrimination": 4,
                        "clarity": 4,
                        "feasibility": 4,
                        "constraints": 4,
                    },
                    "defects": [],
                    "revised": {
                        **_sample_question(question["generation_slot_index"]),
                        "user_prompt": f"Reviewed {question['user_prompt']}",
                    },
                    "changes": "Reviewer tightened the wording.",
                }
                for question in questions
            ])
        if system_prompt == MERGE_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Original questions:\n",
                "\n\nReviewer critiques and revisions:",
            )
            return _make_generate_response([
                {
                    **_sample_question(question["generation_slot_index"]),
                    "user_prompt": f"Merged {question['user_prompt']}",
                }
                for question in questions
            ])
        if system_prompt == RUBRIC_SYSTEM_PROMPT:
            return _make_rubric_response(rubric)
        if "Coverage assignments:" in user_prompt:
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            return _make_generate_response([
                {
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"Question for {assignment['slot_label']}",
                }
                for assignment in assignments
            ])
        raise AssertionError(f"Unexpected prompt path: {preset.name} / {system_prompt[:40]}")

    pipeline = SuitePipeline(
        session_id="test-reviewed-coverage-merge",
        generator_preset=generator_preset,
        reviewer_presets=reviewer_presets,
        name="Strict Coverage Reviewed",
        topic="Coverage topic",
        count=2,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    db = session_factory()
    try:
        saved_suite = db.query(PromptSuite).filter_by(id=suite.id).first()
        assert saved_suite is not None
        assert not saved_suite.name.endswith("[PARTIAL]")
        assert saved_suite.coverage_report["covered_leaf_ids"] == ["a.one", "a.two"]

        items = (
            db.query(PromptSuiteItem)
            .filter_by(suite_id=suite.id)
            .order_by(PromptSuiteItem.order)
            .all()
        )
        assert len(items) == 2
        assert [item.generation_slot_index for item in items] == [0, 1]
        assert [item.coverage_topic_ids for item in items] == [["a.one"], ["a.two"]]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_pipeline_save_persists_item_coverage_fields_and_suite_reports(
    generator_preset, session_factory
):
    """Coverage-aware saves should persist suite reports and item slot metadata."""
    coverage_spec = {
        "version": "1",
        "groups": [
            {
                "id": "a",
                "label": "A. LLM Integration & Orchestration",
                "leaves": [
                    {"id": "a.one", "label": "Multi-provider API abstraction"},
                ],
            }
        ],
    }

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        if system_prompt == COVERAGE_VALIDATION_SYSTEM_PROMPT:
            questions = _extract_json_between_markers(
                user_prompt,
                "Questions:\n",
                "\n\nReturn the validation JSON array now.",
            )
            return _make_generate_response([
                {
                    "slot_index": question["slot_index"],
                    "coverage_status": "covered",
                    "reason": "slot validated",
                }
                for question in questions
            ])
        if "Coverage assignments:" in user_prompt:
            assignments = _extract_json_between_markers(
                user_prompt,
                "Coverage assignments:\n",
                "\nGenerate one question per assignment in the same order.",
            )
            return _make_generate_response([
                {
                    **_sample_question(assignment["slot_index"]),
                    "user_prompt": f"Question for {assignment['slot_label']}",
                }
                for assignment in assignments
            ])
        if "rubric" in system_prompt.lower():
            return _make_rubric_response([
                {"name": "Accuracy", "description": "Correct", "weight": 1.0},
            ])
        raise AssertionError(f"Unexpected prompt path: {preset.name} / {system_prompt[:40]}")

    pipeline = SuitePipeline(
        session_id="test-save-reports",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Coverage Save Test",
        topic="Coverage topic",
        count=1,
        config=PipelineConfig(),
        coverage_mode="strict_leaf_coverage",
        coverage_spec=coverage_spec,
        max_topics_per_question=1,
        suite_manager=_make_manager(),
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    db = session_factory()
    try:
        saved_suite = db.query(PromptSuite).filter_by(id=suite.id).first()
        saved_item = db.query(PromptSuiteItem).filter_by(suite_id=suite.id).first()
        assert saved_suite is not None
        assert saved_item is not None
        assert saved_suite.generation_metadata["coverage_mode"] == "strict_leaf_coverage"
        assert saved_suite.coverage_report["covered_leaf_ids"] == ["a.one"]
        assert saved_suite.dedupe_report["removed_count"] == 0
        assert saved_item.coverage_topic_ids == ["a.one"]
        assert saved_item.coverage_topic_labels == ["Multi-provider API abstraction"]
        assert saved_item.generation_slot_index == 0
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test: active_suite_pipelines registry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_registered_in_active_registry_and_removed_on_completion(
    generator_preset, session_factory
):
    """
    Pipeline is added to active_suite_pipelines during run() and removed on finish.
    """
    question = _sample_question(0)
    rubric = [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]

    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_generate_response([question])
        else:
            return _make_rubric_response(rubric)

    manager = _make_manager()
    config = PipelineConfig()
    session_id = "test-registry-session"
    pipeline = SuitePipeline(
        session_id=session_id,
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Registry Test",
        topic="Testing",
        count=1,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    # Pipeline should not be in registry before run
    assert session_id not in active_suite_pipelines

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    # Pipeline should be removed from registry after completion
    assert session_id not in active_suite_pipelines
    assert suite is not None


# ---------------------------------------------------------------------------
# Test: progress messages include required fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_progress_messages_have_required_fields(
    generator_preset, session_factory
):
    """
    All suite_progress messages must include: type, phase, current, total, overall_percent.
    """
    question = _sample_question(0)
    rubric = [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]
    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_generate_response([question])
        else:
            return _make_rubric_response(rubric)

    manager = _make_manager()
    config = PipelineConfig()
    pipeline = SuitePipeline(
        session_id="test-progress-session",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Progress Test",
        topic="Testing",
        count=1,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        await pipeline.run()

    progress_messages = [
        (call.args[1] if call.args else call.kwargs.get("data", {}))
        for call in manager.send_progress.call_args_list
        if (call.args[1] if call.args else call.kwargs.get("data", {})
            ).get("type") == "suite_progress"
    ]

    assert len(progress_messages) > 0
    for msg in progress_messages:
        assert "type" in msg, f"Missing 'type' in {msg}"
        assert "phase" in msg, f"Missing 'phase' in {msg}"
        assert "phase_index" in msg, f"Missing 'phase_index' in {msg}"
        assert "total_phases" in msg, f"Missing 'total_phases' in {msg}"
        assert "phases" in msg, f"Missing 'phases' in {msg}"
        assert "questions_generated" in msg, f"Missing 'questions_generated' in {msg}"
        assert "question_count" in msg, f"Missing 'question_count' in {msg}"
        assert "overall_percent" in msg, f"Missing 'overall_percent' in {msg}"
        assert "active_generation_calls" in msg, f"Missing 'active_generation_calls' in {msg}"
        assert "active_review_batches" in msg, f"Missing 'active_review_batches' in {msg}"


# ---------------------------------------------------------------------------
# Test: suite description includes methodology summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_suite_description_includes_methodology(
    generator_preset, session_factory
):
    """
    PromptSuite.description should contain generator and reviewer info.
    """
    question = _sample_question(0)
    rubric = [{"name": "Accuracy", "description": "Correct", "weight": 1.0}]
    call_count = [0]

    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return _make_generate_response([question])
        else:
            return _make_rubric_response(rubric)

    manager = _make_manager()
    config = PipelineConfig(difficulty="hard", generate_answers=True, criteria_depth="detailed")
    pipeline = SuitePipeline(
        session_id="test-desc-session",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Description Test",
        topic="Testing methodology",
        count=1,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        suite = await pipeline.run()

    db = session_factory()
    try:
        saved = db.query(PromptSuite).filter_by(id=suite.id).first()
        assert saved.description is not None
        assert len(saved.description) > 0
        # Description should be human-readable (not the old technical "Topic: ... Models: ..." format).
        # It must mention the topic, the generator, and the criteria depth.
        assert "Generated by pipeline:" not in saved.description
        assert "Topic:" not in saved.description
        assert "Models:" not in saved.description
        assert "Testing methodology" in saved.description
        assert generator_preset.name in saved.description
        assert "detailed criteria" in saved.description
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Test: generate_success=False from LLM raises/handles error gracefully
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_llm_failure_propagates_error(
    generator_preset, session_factory
):
    """
    If generate() returns success=False, the pipeline should raise an exception
    (not silently produce an empty suite).
    """
    async def fake_generate(preset, system_prompt, user_prompt, **kwargs):
        return {"success": False, "content": "", "tokens": 0, "error": "Rate limited"}

    manager = _make_manager()
    config = PipelineConfig()
    pipeline = SuitePipeline(
        session_id="test-error-session",
        generator_preset=generator_preset,
        reviewer_presets=[],
        name="Error Test",
        topic="Testing errors",
        count=5,
        config=config,
        context_attachment_id=None,
        suite_manager=manager,
        session_factory=session_factory,
    )

    with patch("app.core.suite_pipeline.generate", side_effect=fake_generate):
        with pytest.raises(Exception):
            await pipeline.run()

    # No suite saved
    db = session_factory()
    try:
        count = db.query(PromptSuite).count()
        assert count == 0
    finally:
        db.close()
