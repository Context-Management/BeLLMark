from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from typing import List
from pydantic import BaseModel, Field, field_validator, model_validator
from urllib.parse import urlparse
import asyncio
import httpx
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone

from app.db.database import get_db

logger = logging.getLogger(__name__)
from app.db.models import (
    Attachment,
    BenchmarkRun,
    ModelPreset,
    PromptSuite,
    PromptSuiteItem,
    Question,
    RunStatus,
    SuiteAttachment,
    SuiteGenerationJob,
)
from app.schemas.attachments import SuiteAttachmentCreate, SuiteAttachmentResponse, AttachmentResponse
from app.core.generators import generate
from app.core.attachments import load_attachment_content
from app.core.suite_coverage import count_required_leaves, normalize_coverage_spec, parse_coverage_outline

# Module-level registry for background tasks (session_id -> asyncio.Task)
active_suite_pipeline_tasks: dict[str, asyncio.Task] = {}

router = APIRouter(prefix="/api/suites", tags=["suites"])

class PromptItemCreate(BaseModel):
    system_prompt: str
    user_prompt: str
    expected_answer: str | None = None
    category: str | None = None
    difficulty: str | None = None
    criteria: List[dict] | None = None

class SuiteCreate(BaseModel):
    name: str
    description: str = ""
    items: List[PromptItemCreate]
    default_criteria: List[dict] | None = None

class PromptItemResponse(BaseModel):
    id: int
    order: int
    system_prompt: str
    user_prompt: str
    expected_answer: str | None = None
    category: str | None = None
    difficulty: str | None = None
    criteria: List[dict] | None = None

class SuiteResponse(BaseModel):
    id: int
    name: str
    description: str
    created_at: str
    items: List[PromptItemResponse] = []
    default_criteria: List[dict] | None = None
    item_count: int = 0
    attachment_count: int = 0
    answer_count: int = 0
    generation_metadata: dict | None = None
    coverage_report: dict | None = None
    dedupe_report: dict | None = None

class SuiteGenerateRequest(BaseModel):
    name: str
    model_id: int
    topic: str
    count: int = 5
    system_context: str = ""
    context_attachment_id: int | None = None  # Optional attachment for context

class SuiteFromRunRequest(BaseModel):
    name: str
    description: str = ""


class CoverageTopicLeaf(BaseModel):
    id: str
    label: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)


class CoverageTopicGroup(BaseModel):
    id: str
    label: str
    leaves: list[CoverageTopicLeaf] = Field(default_factory=list)


class CoverageSpec(BaseModel):
    version: str = "1"
    groups: list[CoverageTopicGroup] = Field(default_factory=list)


class CoverageOutlineParseRequest(BaseModel):
    outline: str


class SuiteGenerateV2Request(BaseModel):
    name: str
    topic: str
    count: int = 10
    generator_model_id: int | None = None
    generator_model_ids: list[int] = Field(default_factory=list)
    editor_model_id: int | None = None
    reviewer_model_ids: list[int] = Field(default_factory=list)
    difficulty: str = "balanced"
    categories: list[str] = Field(default_factory=list)
    generate_answers: bool = True
    criteria_depth: str = "basic"
    coverage_mode: str = "none"
    coverage_spec: CoverageSpec | None = None
    coverage_outline_text: str | None = None
    max_topics_per_question: int = 1
    context_attachment_id: int | None = None

    @field_validator("count")
    @classmethod
    def count_in_range(cls, v):
        if not (1 <= v <= 50):
            raise ValueError("count must be between 1 and 50")
        return v

    @field_validator("reviewer_model_ids")
    @classmethod
    def max_three_reviewers(cls, v):
        if len(v) > 3:
            raise ValueError("reviewer_model_ids must have at most 3 entries")
        return v

    @field_validator("coverage_mode")
    @classmethod
    def valid_coverage_mode(cls, v):
        allowed = {"none", "strict_leaf_coverage", "compact_leaf_coverage", "group_coverage"}
        if v not in allowed:
            raise ValueError(f"coverage_mode must be one of {sorted(allowed)}")
        return v

    @field_validator("difficulty")
    @classmethod
    def valid_difficulty(cls, v):
        allowed = {"balanced", "easy", "hard", "mixed"}
        if v not in allowed:
            raise ValueError(f"difficulty must be one of {sorted(allowed)}")
        return v

    @field_validator("criteria_depth")
    @classmethod
    def valid_criteria_depth(cls, v):
        allowed = {"basic", "detailed"}
        if v not in allowed:
            raise ValueError(f"criteria_depth must be one of {sorted(allowed)}")
        return v

    @field_validator("max_topics_per_question")
    @classmethod
    def valid_max_topics_per_question(cls, v):
        if v < 1:
            raise ValueError("max_topics_per_question must be at least 1")
        return v

    @model_validator(mode="after")
    def normalize_generators(self):
        if not self.generator_model_ids:
            if self.generator_model_id is None:
                raise ValueError("at least one generator model is required")
            self.generator_model_ids = [self.generator_model_id]
        if len(set(self.generator_model_ids)) != len(self.generator_model_ids):
            raise ValueError("generator_model_ids must not contain duplicates")
        if self.editor_model_id is None:
            self.editor_model_id = self.generator_model_ids[0]

        coverage_spec = self.coverage_spec
        if self.coverage_outline_text and coverage_spec is None:
            coverage_spec = CoverageSpec.model_validate(parse_coverage_outline(self.coverage_outline_text))
        if coverage_spec is not None:
            normalized_spec = normalize_coverage_spec(coverage_spec.model_dump())
            coverage_spec = CoverageSpec.model_validate(normalized_spec)

        if self.coverage_mode != "none":
            if coverage_spec is None:
                raise ValueError("coverage_spec or coverage_outline_text is required when coverage_mode is enabled")

            required_leaf_count = count_required_leaves(coverage_spec.model_dump())
            if self.coverage_mode == "strict_leaf_coverage":
                if required_leaf_count > 50:
                    raise ValueError("strict_leaf_coverage supports at most 50 required leaves")
                if self.count < required_leaf_count:
                    raise ValueError(
                        f"count must be at least {required_leaf_count} for strict_leaf_coverage"
                    )
            elif self.coverage_mode == "compact_leaf_coverage":
                if self.count * self.max_topics_per_question < required_leaf_count:
                    raise ValueError(
                        "count * max_topics_per_question must be at least the number of required leaves"
                    )

        self.coverage_spec = coverage_spec
        return self


def _pipeline_config_payload(request: SuiteGenerateV2Request) -> dict:
    return {
        "difficulty": request.difficulty,
        "categories": list(request.categories or []),
        "generate_answers": request.generate_answers,
        "criteria_depth": request.criteria_depth,
        "generation_concurrency": 5,
        "review_batch_concurrency": 5,
    }


def _checkpoint_payload() -> dict:
    return {
        "generation_results": [],
        "review_outcomes": [],
        "merged_batches": [],
        "prepared_questions": None,
        "rubric": None,
        "coverage_validation_results": {},
        "dedupe_report": None,
    }


def build_suite_pipeline_from_job(job: SuiteGenerationJob, db: Session, suite_manager=None):
    from app.core.suite_pipeline import PipelineConfig, SuitePipeline  # noqa: PLC0415

    generator_ids = list(job.generator_model_ids or [])
    reviewer_ids = list(job.reviewer_model_ids or [])
    generator_presets = (
        db.query(ModelPreset)
        .filter(ModelPreset.id.in_(generator_ids))
        .all()
        if generator_ids
        else []
    )
    generators_by_id = {preset.id: preset for preset in generator_presets}
    ordered_generators = [generators_by_id[model_id] for model_id in generator_ids if model_id in generators_by_id]
    if len(ordered_generators) != len(generator_ids):
        raise HTTPException(status_code=500, detail=f"Missing generator preset(s) for suite job {job.session_id}")

    editor_preset = db.query(ModelPreset).filter(ModelPreset.id == job.editor_model_id).first()
    if editor_preset is None:
        raise HTTPException(status_code=500, detail=f"Missing editor preset for suite job {job.session_id}")

    reviewer_presets = (
        db.query(ModelPreset)
        .filter(ModelPreset.id.in_(reviewer_ids))
        .all()
        if reviewer_ids
        else []
    )
    reviewers_by_id = {preset.id: preset for preset in reviewer_presets}
    ordered_reviewers = [reviewers_by_id[model_id] for model_id in reviewer_ids if model_id in reviewers_by_id]
    if len(ordered_reviewers) != len(reviewer_ids):
        raise HTTPException(status_code=500, detail=f"Missing reviewer preset(s) for suite job {job.session_id}")

    pipeline_config = dict(job.pipeline_config or {})
    config = PipelineConfig(
        difficulty=pipeline_config.get("difficulty", "balanced"),
        categories=pipeline_config.get("categories") or None,
        generate_answers=bool(pipeline_config.get("generate_answers", True)),
        criteria_depth=pipeline_config.get("criteria_depth", "basic"),
        generation_concurrency=int(pipeline_config.get("generation_concurrency", 5)),
        review_batch_concurrency=int(pipeline_config.get("review_batch_concurrency", 5)),
    )
    return SuitePipeline(
        session_id=job.session_id,
        generator_presets=ordered_generators,
        editor_preset=editor_preset,
        reviewer_presets=ordered_reviewers,
        name=job.name,
        topic=job.topic,
        count=job.count,
        config=config,
        coverage_mode=job.coverage_mode or "none",
        coverage_spec=job.coverage_spec,
        max_topics_per_question=job.max_topics_per_question or 1,
        context_attachment_id=job.context_attachment_id,
        job_id=job.id,
        resume_checkpoint=job.checkpoint_payload or {},
        suite_manager=suite_manager,
    )


async def resume_suite_generation_task(job_id: int) -> None:
    from app.db.database import SessionLocal  # noqa: PLC0415
    from app.ws.suite_progress import suite_manager  # noqa: PLC0415

    db = SessionLocal()
    try:
        job = db.query(SuiteGenerationJob).filter(SuiteGenerationJob.id == job_id).first()
        if job is None or job.status != RunStatus.running:
            return
        if job.session_id in active_suite_pipeline_tasks:
            return
        pipeline = build_suite_pipeline_from_job(job, db, suite_manager=suite_manager)
    finally:
        db.close()

    task = asyncio.create_task(run_suite_generation_task(pipeline.session_id, pipeline))
    active_suite_pipeline_tasks[pipeline.session_id] = task


async def run_suite_generation_task(session_id: str, pipeline) -> None:
    """Background task that runs the pipeline and emits exactly one terminal event."""
    from app.core.suite_pipeline import PipelineCancelledError, PipelinePausedForResume  # noqa: PLC0415
    from app.ws.suite_progress import suite_manager  # noqa: PLC0415

    logger.info("Suite generation task started: session=%s name=%r", session_id, pipeline.name)
    try:
        suite = await pipeline.run()
        logger.info("Suite generation complete: session=%s suite_id=%d saved=%d questions",
                     session_id, suite.id, pipeline.saved_count)
        await suite_manager.send_progress(session_id, {
            "type": "suite_complete",
            "suite_id": suite.id,
            "question_count": pipeline.saved_count,
            "reviewers_used": len(pipeline.reviewer_presets),
        })
    except PipelinePausedForResume:
        logger.info("Suite generation paused for resume: session=%s", session_id)
    except asyncio.CancelledError:
        # Persist a terminal state regardless of whether the cancel was user-initiated
        # or came from an asyncio task interrupt (SIGTERM, shutdown, etc). Previously
        # the non-user branch only logged, which left `status=running` in the DB —
        # startup auto-resume would then pick the job up on every subsequent restart
        # and silently recreate the same PromptSuite row each time.
        if getattr(pipeline, "_cancelled", False):
            logger.info("Suite generation cancelled (task interrupt): session=%s", session_id)
            cancel_error = "Cancelled by user"
        else:
            logger.info("Suite generation cancelled (asyncio): session=%s", session_id)
            cancel_error = "Interrupted (task cancelled externally)"
        try:
            await pipeline._persist_job_state(
                status=RunStatus.cancelled,
                phase=getattr(pipeline, "_current_phase", "unknown"),
                snapshot_payload=pipeline.snapshot(),
                checkpoint_payload=getattr(pipeline, "_job_checkpoint", None),
                error=cancel_error,
                completed=True,
            )
        except Exception:
            logger.warning("Failed to persist terminal state on cancel: session=%s", session_id)
        await suite_manager.send_progress(session_id, {
            "type": "suite_cancelled",
            "phase": getattr(pipeline, "_current_phase", "unknown"),
            "questions_generated": getattr(pipeline, "_questions_generated", 0),
        })
    except PipelineCancelledError:
        logger.info("Suite generation cancelled (user): session=%s", session_id)
        if getattr(pipeline, "_partial_suite", None):
            await suite_manager.send_progress(session_id, {
                "type": "suite_partial",
                "suite_id": pipeline._partial_suite.id,
                "question_count": pipeline.saved_count,
                "requested_count": pipeline.count,
                "error": "Cancelled by user",
                "phase": getattr(pipeline, "_current_phase", "unknown"),
            })
        else:
            await suite_manager.send_progress(session_id, {
                "type": "suite_cancelled",
                "phase": getattr(pipeline, "_current_phase", "unknown"),
                "questions_generated": getattr(pipeline, "_questions_generated", 0),
            })
    except Exception as e:
        logger.exception("Suite generation failed: session=%s phase=%s error=%s",
                         session_id, getattr(pipeline, "_current_phase", "unknown"), e)
        try:
            if getattr(pipeline, "_partial_suite", None):
                await suite_manager.send_progress(session_id, {
                    "type": "suite_partial",
                    "suite_id": pipeline._partial_suite.id,
                    "question_count": pipeline.saved_count,
                    "requested_count": pipeline.count,
                    "error": pipeline._partial_error,
                    "phase": getattr(pipeline, "_current_phase", "unknown"),
                })
            else:
                await suite_manager.send_progress(session_id, {
                    "type": "suite_error",
                    "phase": getattr(pipeline, "_current_phase", "unknown"),
                    "error": str(e),
                })
        except Exception:
            logger.warning("Failed to send suite_error via WS: session=%s", session_id)
    finally:
        active_suite_pipeline_tasks.pop(session_id, None)


def cancel_suite_generation_session(session_id: str, db: Session) -> bool:
    """Cancel an active or persisted suite generation session."""
    from app.core.suite_pipeline import active_suite_pipelines  # noqa: PLC0415

    pipeline = active_suite_pipelines.get(session_id)
    task = active_suite_pipeline_tasks.get(session_id)
    job = (
        db.query(SuiteGenerationJob)
        .filter(SuiteGenerationJob.session_id == session_id)
        .first()
    )
    if pipeline is None and task is None and job is None:
        return False

    if pipeline is not None:
        pipeline.cancel()
    if task is not None:
        task.cancel()

    if job is not None and job.status == RunStatus.running:
        snapshot_payload = pipeline.snapshot() if pipeline is not None else job.snapshot_payload
        current_phase = getattr(pipeline, "_current_phase", None)
        if not isinstance(current_phase, str):
            current_phase = None
        if current_phase is None and isinstance(snapshot_payload, dict):
            current_phase = snapshot_payload.get("phase")
        job.status = RunStatus.cancelled
        job.phase = current_phase or job.phase
        job.snapshot_payload = snapshot_payload
        job.error = "Cancelled by user"
        now = datetime.now(timezone.utc)
        job.updated_at = now
        job.completed_at = now
        db.commit()

    return True


@router.get("/pipelines")
def list_active_pipelines(db: Session = Depends(get_db)):
    """Return status of all active suite generation pipelines."""
    from app.core.suite_pipeline import active_suite_pipelines  # noqa: PLC0415

    snapshots = [pipeline.snapshot() for pipeline in active_suite_pipelines.values()]
    active_session_ids = {snapshot["session_id"] for snapshot in snapshots}
    persisted_jobs = (
        db.query(SuiteGenerationJob)
        .filter(SuiteGenerationJob.status == RunStatus.running)
        .order_by(SuiteGenerationJob.updated_at.desc())
        .all()
    )
    for job in persisted_jobs:
        if job.session_id in active_session_ids or not job.snapshot_payload:
            continue
        snapshots.append(job.snapshot_payload)
    return snapshots


@router.post("/pipelines/{session_id}/cancel")
def cancel_pipeline(session_id: str, db: Session = Depends(get_db)):
    """Cancel an active suite generation pipeline."""
    if not cancel_suite_generation_session(session_id, db):
        raise HTTPException(status_code=404, detail="Suite generation session not found")
    return {"session_id": session_id, "cancelled": True}


@router.post("/parse-coverage-outline")
def parse_coverage_outline_endpoint(request: CoverageOutlineParseRequest):
    spec = parse_coverage_outline(request.outline)
    return {"spec": spec}


@router.get("/", response_model=List[SuiteResponse])
def list_suites(db: Session = Depends(get_db)):
    item_count_sub = (
        db.query(PromptSuiteItem.suite_id, func.count(PromptSuiteItem.id).label("cnt"))
        .group_by(PromptSuiteItem.suite_id)
        .subquery()
    )
    attach_count_sub = (
        db.query(SuiteAttachment.suite_id, func.count(SuiteAttachment.id).label("cnt"))
        .group_by(SuiteAttachment.suite_id)
        .subquery()
    )
    answer_count_sub = (
        db.query(PromptSuiteItem.suite_id, func.count(PromptSuiteItem.id).label("cnt"))
        .filter(PromptSuiteItem.expected_answer.isnot(None), PromptSuiteItem.expected_answer != "")
        .group_by(PromptSuiteItem.suite_id)
        .subquery()
    )
    rows = (
        db.query(
            PromptSuite,
            func.coalesce(item_count_sub.c.cnt, 0).label("item_count"),
            func.coalesce(attach_count_sub.c.cnt, 0).label("attachment_count"),
            func.coalesce(answer_count_sub.c.cnt, 0).label("answer_count"),
        )
        .outerjoin(item_count_sub, PromptSuite.id == item_count_sub.c.suite_id)
        .outerjoin(attach_count_sub, PromptSuite.id == attach_count_sub.c.suite_id)
        .outerjoin(answer_count_sub, PromptSuite.id == answer_count_sub.c.suite_id)
        .order_by(PromptSuite.created_at.desc())
        .all()
    )
    return [SuiteResponse(
        id=s.id, name=s.name, description=s.description or "",
        created_at=s.created_at.isoformat(), items=[],
        default_criteria=s.default_criteria,
        item_count=ic, attachment_count=ac, answer_count=ansc,
        generation_metadata=getattr(s, "generation_metadata", None),
        coverage_report=getattr(s, "coverage_report", None),
        dedupe_report=getattr(s, "dedupe_report", None),
    ) for s, ic, ac, ansc in rows]

@router.post("/", response_model=SuiteResponse)
def create_suite(suite: SuiteCreate, db: Session = Depends(get_db)):
    db_suite = PromptSuite(
        name=suite.name,
        description=suite.description,
        default_criteria=suite.default_criteria,
    )
    db.add(db_suite)
    db.commit()
    db.refresh(db_suite)

    for i, item in enumerate(suite.items):
        db_item = PromptSuiteItem(
            suite_id=db_suite.id, order=i,
            system_prompt=item.system_prompt, user_prompt=item.user_prompt,
            expected_answer=item.expected_answer,
            category=item.category,
            difficulty=item.difficulty,
            criteria=item.criteria,
        )
        db.add(db_item)
    db.commit()
    db.refresh(db_suite)

    return SuiteResponse(
        id=db_suite.id, name=db_suite.name, description=db_suite.description or "",
        created_at=db_suite.created_at.isoformat(),
        default_criteria=db_suite.default_criteria,
        items=[PromptItemResponse(
            id=it.id, order=it.order,
            system_prompt=it.system_prompt, user_prompt=it.user_prompt,
            expected_answer=it.expected_answer,
            category=it.category,
            difficulty=it.difficulty,
            criteria=it.criteria,
        ) for it in db_suite.items]
    )

SUITE_GENERATION_PROMPT = '''Generate {count} benchmark prompt pairs about: {topic}

{context}

For each prompt pair, provide:
1. A system prompt that sets the context for the AI being tested
2. A user prompt that contains the actual question/task

Respond ONLY with a JSON array in this exact format:
[
  {{
    "system_prompt": "You are an expert in...",
    "user_prompt": "Explain..."
  }},
  ...
]

Generate diverse prompts that test different aspects of the topic.'''

@router.post("/generate", response_model=SuiteResponse)
async def generate_suite(request: SuiteGenerateRequest, db: Session = Depends(get_db)):
    preset = db.query(ModelPreset).filter(ModelPreset.id == request.model_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Model not found")

    # Build context from system_context and/or attachment
    context_parts = []
    if request.system_context:
        context_parts.append(request.system_context)

    if request.context_attachment_id:
        attachment = db.query(Attachment).filter(Attachment.id == request.context_attachment_id).first()
        if not attachment:
            raise HTTPException(status_code=404, detail="Context attachment not found")
        if not attachment.mime_type.startswith("text/"):
            raise HTTPException(status_code=400, detail="Context attachment must be a text file")
        try:
            content_bytes = load_attachment_content(attachment.storage_path)
            file_content = content_bytes.decode("utf-8")
            context_parts.append(f"--- Document: {attachment.filename} ---\n{file_content}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read attachment: {str(e)}")

    context = f"Additional context:\n{chr(10).join(context_parts)}" if context_parts else ""
    prompt = SUITE_GENERATION_PROMPT.format(
        count=request.count,
        topic=request.topic,
        context=context
    )

    result = await generate(
        preset,
        "You are a benchmark prompt generator. Generate clear, specific prompts for evaluating AI models.",
        prompt
    )

    if not result["success"]:
        raise HTTPException(status_code=500, detail=f"Generation failed: {result['error']}")

    try:
        content = result["content"]
        start = content.find("[")
        end = content.rfind("]") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON array found in response")

        items_data = json.loads(content[start:end])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse generated prompts: {str(e)}")

    # Create the suite
    db_suite = PromptSuite(name=request.name, description=f"AI-generated suite about: {request.topic}")
    db.add(db_suite)
    db.commit()
    db.refresh(db_suite)

    for i, item in enumerate(items_data):
        db_item = PromptSuiteItem(
            suite_id=db_suite.id, order=i,
            system_prompt=item["system_prompt"], user_prompt=item["user_prompt"],
            expected_answer=None,
            category=None,
            difficulty=None,
            criteria=None,
        )
        db.add(db_item)
    db.commit()
    db.refresh(db_suite)

    return SuiteResponse(
        id=db_suite.id, name=db_suite.name, description=db_suite.description or "",
        created_at=db_suite.created_at.isoformat(),
        default_criteria=db_suite.default_criteria,
        items=[PromptItemResponse(
            id=it.id, order=it.order,
            system_prompt=it.system_prompt, user_prompt=it.user_prompt,
            expected_answer=it.expected_answer,
            category=it.category,
            difficulty=it.difficulty,
            criteria=it.criteria,
        ) for it in db_suite.items]
    )


@router.post("/generate-v2")
async def generate_suite_v2(request: SuiteGenerateV2Request, db: Session = Depends(get_db)):
    """Start async pipeline suite generation. Returns session_id for WebSocket tracking."""
    from app.core.suite_pipeline import active_suite_pipelines, SuitePipeline, PipelineConfig  # noqa: PLC0415
    from app.ws.suite_progress import suite_manager  # noqa: PLC0415

    # Look up generator presets
    generator_presets = []
    for gid in request.generator_model_ids:
        preset = db.query(ModelPreset).filter(ModelPreset.id == gid).first()
        if not preset:
            raise HTTPException(status_code=404, detail=f"Generator model {gid} not found")
        generator_presets.append(preset)

    editor_preset = db.query(ModelPreset).filter(ModelPreset.id == request.editor_model_id).first()
    if not editor_preset:
        raise HTTPException(status_code=404, detail=f"Editor model {request.editor_model_id} not found")

    # Look up reviewer presets
    reviewer_presets = []
    for rid in request.reviewer_model_ids:
        preset = db.query(ModelPreset).filter(ModelPreset.id == rid).first()
        if not preset:
            raise HTTPException(status_code=404, detail=f"Reviewer model {rid} not found")
        reviewer_presets.append(preset)

    # Validate context attachment (must be text if provided)
    if request.context_attachment_id is not None:
        attachment = db.query(Attachment).filter(Attachment.id == request.context_attachment_id).first()
        if not attachment:
            raise HTTPException(status_code=404, detail="Context attachment not found")
        if not attachment.mime_type.startswith("text/"):
            raise HTTPException(
                status_code=422,
                detail="context_attachment_id must reference a text attachment",
            )

    generator_model_ids = [preset.id for preset in generator_presets]
    editor_model_id = editor_preset.id
    reviewer_model_ids = [preset.id for preset in reviewer_presets]
    seen_presets: set[int] = set()
    for preset in [*generator_presets, editor_preset, *reviewer_presets]:
        preset_identity = id(preset)
        if preset_identity in seen_presets:
            continue
        db.expunge(preset)
        seen_presets.add(preset_identity)

    session_id = str(uuid.uuid4())
    config_payload = _pipeline_config_payload(request)
    config = PipelineConfig(
        difficulty=config_payload["difficulty"],
        categories=config_payload["categories"] or None,
        generate_answers=config_payload["generate_answers"],
        criteria_depth=config_payload["criteria_depth"],
        generation_concurrency=config_payload["generation_concurrency"],
        review_batch_concurrency=config_payload["review_batch_concurrency"],
    )
    job = SuiteGenerationJob(
        session_id=session_id,
        status=RunStatus.running,
        name=request.name,
        topic=request.topic,
        count=request.count,
        generator_model_ids=generator_model_ids,
        editor_model_id=editor_model_id,
        reviewer_model_ids=reviewer_model_ids,
        pipeline_config=config_payload,
        coverage_mode=request.coverage_mode,
        coverage_spec=request.coverage_spec.model_dump() if request.coverage_spec else None,
        max_topics_per_question=request.max_topics_per_question,
        context_attachment_id=request.context_attachment_id,
        phase="init",
        snapshot_payload=None,
        checkpoint_payload=_checkpoint_payload(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    # Tests set BELLMARK_DISABLE_BACKGROUND_RUNS=1 to prevent real pipeline work from
    # escaping into the background. Honour it here — otherwise a test that exercises
    # this endpoint without mocking SuitePipeline would spawn an asyncio task whose
    # pipeline uses the *prod* SessionLocal (late-bound in SuitePipeline.__init__),
    # writing through to backend/bellmark.db even though the endpoint itself is using
    # the test's in-memory override. That was the source of ghost "V2 Suite" entries
    # appearing in production's Active Generations panel.
    if os.getenv("BELLMARK_DISABLE_BACKGROUND_RUNS"):
        return {"session_id": session_id}

    pipeline = SuitePipeline(
        session_id=session_id,
        generator_presets=generator_presets,
        editor_preset=editor_preset,
        reviewer_presets=reviewer_presets,
        name=request.name,
        topic=request.topic,
        count=request.count,
        config=config,
        coverage_mode=request.coverage_mode,
        coverage_spec=request.coverage_spec.model_dump() if request.coverage_spec else None,
        max_topics_per_question=request.max_topics_per_question,
        context_attachment_id=request.context_attachment_id,
        job_id=job.id,
        suite_manager=suite_manager,
    )
    # Pipeline registers itself in active_suite_pipelines during run()
    task = asyncio.create_task(run_suite_generation_task(session_id, pipeline))
    active_suite_pipeline_tasks[session_id] = task

    return {"session_id": session_id}


@router.post("/from-run/{run_id}", response_model=SuiteResponse)
def create_suite_from_run(run_id: int, request: SuiteFromRunRequest, db: Session = Depends(get_db)):
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")

    questions = db.query(Question).filter(Question.benchmark_id == run_id).order_by(Question.order).all()
    if not questions:
        raise HTTPException(status_code=400, detail="Run has no questions")

    description = request.description or f"Created from benchmark run: {run.name}"
    db_suite = PromptSuite(
        name=request.name,
        description=description,
        default_criteria=run.criteria if hasattr(run, "criteria") else None,
    )
    db.add(db_suite)
    db.commit()
    db.refresh(db_suite)

    for i, q in enumerate(questions):
        db_item = PromptSuiteItem(
            suite_id=db_suite.id, order=i,
            system_prompt=q.system_prompt, user_prompt=q.user_prompt,
            expected_answer=q.expected_answer if hasattr(q, "expected_answer") else None,
            category=None,
            difficulty=None,
            criteria=None,
        )
        db.add(db_item)
    db.commit()
    db.refresh(db_suite)

    return SuiteResponse(
        id=db_suite.id, name=db_suite.name, description=db_suite.description or "",
        created_at=db_suite.created_at.isoformat(),
        default_criteria=db_suite.default_criteria,
        items=[PromptItemResponse(
            id=it.id, order=it.order,
            system_prompt=it.system_prompt, user_prompt=it.user_prompt,
            expected_answer=it.expected_answer,
            category=it.category,
            difficulty=it.difficulty,
            criteria=it.criteria,
        ) for it in db_suite.items]
    )

class ImportCriterion(BaseModel):
    name: str
    description: str
    weight: float = 1.0

class ImportQuestion(BaseModel):
    system_prompt: str | None = None
    user_prompt: str
    expected_answer: str | None = None
    category: str | None = None
    difficulty: str | None = None
    criteria: List[ImportCriterion] | None = None

class SuiteImportRequest(BaseModel):
    bellmark_version: str = "1.0"
    type: str = "suite"
    name: str
    description: str | None = None
    default_criteria: List[ImportCriterion] | None = None
    questions: List[ImportQuestion]

    @field_validator("questions")
    @classmethod
    def questions_must_not_be_empty(cls, v):
        if not v:
            raise ValueError("questions must not be empty")
        return v

@router.post("/import", response_model=SuiteResponse)
def import_suite(data: SuiteImportRequest, db: Session = Depends(get_db)):
    criteria_dicts = (
        [c.model_dump() for c in data.default_criteria]
        if data.default_criteria is not None
        else None
    )
    db_suite = PromptSuite(
        name=data.name,
        description=data.description or "",
        default_criteria=criteria_dicts,
    )
    db.add(db_suite)
    db.commit()
    db.refresh(db_suite)

    for i, q in enumerate(data.questions):
        db_item = PromptSuiteItem(
            suite_id=db_suite.id,
            order=i,
            system_prompt=q.system_prompt or "",
            user_prompt=q.user_prompt,
            expected_answer=q.expected_answer,
            category=q.category,
            difficulty=q.difficulty,
            criteria=[c.model_dump() for c in q.criteria] if q.criteria is not None else None,
        )
        db.add(db_item)
    db.commit()
    db.refresh(db_suite)

    return SuiteResponse(
        id=db_suite.id,
        name=db_suite.name,
        description=db_suite.description or "",
        created_at=db_suite.created_at.isoformat(),
        default_criteria=db_suite.default_criteria,
        items=[
            PromptItemResponse(
                id=it.id, order=it.order,
                system_prompt=it.system_prompt, user_prompt=it.user_prompt,
                expected_answer=it.expected_answer,
                category=it.category,
                difficulty=it.difficulty,
                criteria=it.criteria,
            )
            for it in db_suite.items
        ],
    )

# Allowlist for the lightweight URL-based suite import. Restricting hosts
# avoids turning BeLLMark into an open SSRF proxy and makes the audit story
# trivial. To add a host, add it here and document why in the PR.
_ALLOWED_IMPORT_HOSTS = {
    "raw.githubusercontent.com",
    "gist.githubusercontent.com",
    "huggingface.co",
}
_IMPORT_URL_TIMEOUT_SECONDS = 10.0
_IMPORT_URL_MAX_BYTES = 1_048_576  # 1 MB — suites are small JSON; this leaves headroom


class ImportFromUrlRequest(BaseModel):
    url: str


@router.post("/import-url", response_model=SuiteResponse)
async def import_suite_from_url(payload: ImportFromUrlRequest, db: Session = Depends(get_db)):
    """Fetch a suite JSON from an allowlisted URL and import it.

    Designed for lightweight community sharing: users export a suite to a
    GitHub Gist or push it to a public repo, then anyone can import it by
    URL without uploading a file. The host allowlist (raw.githubusercontent
    .com, gist.githubusercontent.com, huggingface.co) keeps the surface
    small. Response size is capped at 1 MB.
    """
    parsed = urlparse(payload.url)

    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="URL must use https://")

    if not parsed.hostname:
        raise HTTPException(status_code=400, detail="URL must include a hostname")

    if parsed.hostname not in _ALLOWED_IMPORT_HOSTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Host '{parsed.hostname}' is not allowed. Allowed hosts: "
                f"{sorted(_ALLOWED_IMPORT_HOSTS)}"
            ),
        )

    try:
        async with httpx.AsyncClient(
            timeout=_IMPORT_URL_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as http_client:
            response = await http_client.get(payload.url)
            response.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="URL fetch timed out")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502,
            detail=f"URL returned HTTP {e.response.status_code}",
        )
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"URL fetch failed: {type(e).__name__}",
        )

    if len(response.content) > _IMPORT_URL_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Response exceeds {_IMPORT_URL_MAX_BYTES} bytes",
        )

    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="URL did not return valid JSON")

    try:
        import_request = SuiteImportRequest.model_validate(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid suite schema: {e}")

    return import_suite(import_request, db)


@router.get("/{suite_id}/export")
def export_suite(suite_id: int, db: Session = Depends(get_db)):
    suite = db.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    payload = {
        "bellmark_version": "1.0",
        "type": "suite",
        "name": suite.name,
        "description": suite.description or "",
        "default_criteria": suite.default_criteria,
        "generation_metadata": getattr(suite, "generation_metadata", None),
        "coverage_report": getattr(suite, "coverage_report", None),
        "dedupe_report": getattr(suite, "dedupe_report", None),
        "questions": [
            {
                "system_prompt": it.system_prompt,
                "user_prompt": it.user_prompt,
                "expected_answer": it.expected_answer,
                "category": it.category,
                "difficulty": it.difficulty,
                "criteria": it.criteria,
                "coverage_topic_ids": getattr(it, "coverage_topic_ids", None),
                "coverage_topic_labels": getattr(it, "coverage_topic_labels", None),
                "generation_slot_index": getattr(it, "generation_slot_index", None),
            }
            for it in sorted(suite.items, key=lambda x: x.order)
        ],
    }

    safe_name = re.sub(r"[^\w\-.]", "_", suite.name)
    filename = f"{safe_name}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/{suite_id}", response_model=SuiteResponse)
def get_suite(suite_id: int, db: Session = Depends(get_db)):
    suite = db.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")
    return SuiteResponse(
        id=suite.id, name=suite.name, description=suite.description or "",
        created_at=suite.created_at.isoformat(),
        default_criteria=suite.default_criteria,
        generation_metadata=getattr(suite, "generation_metadata", None),
        coverage_report=getattr(suite, "coverage_report", None),
        dedupe_report=getattr(suite, "dedupe_report", None),
        items=[PromptItemResponse(
            id=it.id, order=it.order,
            system_prompt=it.system_prompt, user_prompt=it.user_prompt,
            expected_answer=it.expected_answer,
            category=it.category,
            difficulty=it.difficulty,
            criteria=it.criteria,
        ) for it in suite.items]
    )

@router.put("/{suite_id}", response_model=SuiteResponse)
def update_suite(suite_id: int, suite: SuiteCreate, db: Session = Depends(get_db)):
    db_suite = db.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
    if not db_suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    # Update suite metadata
    db_suite.name = suite.name
    db_suite.description = suite.description
    db_suite.default_criteria = suite.default_criteria

    # Preserve attachment links: collect old item_id → order mapping
    old_items = db.query(PromptSuiteItem).filter(PromptSuiteItem.suite_id == suite_id).all()
    old_id_to_order = {item.id: item.order for item in old_items}

    # Delete existing items and recreate
    db.query(PromptSuiteItem).filter(PromptSuiteItem.suite_id == suite_id).delete()

    new_items_by_order = {}
    for i, item in enumerate(suite.items):
        db_item = PromptSuiteItem(
            suite_id=suite_id, order=i,
            system_prompt=item.system_prompt, user_prompt=item.user_prompt,
            expected_answer=item.expected_answer,
            category=item.category,
            difficulty=item.difficulty,
            criteria=item.criteria,
        )
        db.add(db_item)
        db.flush()  # Assign ID so we can re-link attachments
        new_items_by_order[i] = db_item.id

    # Re-link suite attachments to new item IDs
    suite_attachments = db.query(SuiteAttachment).filter(
        SuiteAttachment.suite_id == suite_id,
        SuiteAttachment.suite_item_id.isnot(None)
    ).all()
    for sa in suite_attachments:
        old_order = old_id_to_order.get(sa.suite_item_id)
        if old_order is not None and old_order in new_items_by_order:
            sa.suite_item_id = new_items_by_order[old_order]
        else:
            # Item was removed — clear the link
            sa.suite_item_id = None

    db.commit()
    db.refresh(db_suite)

    return SuiteResponse(
        id=db_suite.id, name=db_suite.name, description=db_suite.description or "",
        created_at=db_suite.created_at.isoformat(),
        default_criteria=db_suite.default_criteria,
        items=[PromptItemResponse(
            id=it.id, order=it.order,
            system_prompt=it.system_prompt, user_prompt=it.user_prompt,
            expected_answer=it.expected_answer,
            category=it.category,
            difficulty=it.difficulty,
            criteria=it.criteria,
        ) for it in db_suite.items]
    )

@router.delete("/{suite_id}")
def delete_suite(suite_id: int, db: Session = Depends(get_db)):
    suite = db.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    blocking_runs = db.query(BenchmarkRun).filter(BenchmarkRun.source_suite_id == suite_id).all()
    if blocking_runs:
        run_names = ", ".join(run.name for run in blocking_runs[:3])
        suffix = "" if len(blocking_runs) <= 3 else f" and {len(blocking_runs) - 3} more"
        raise HTTPException(
            status_code=409,
            detail=f"Suite is referenced by benchmark run(s): {run_names}{suffix}",
        )

    generation_jobs = (
        db.query(SuiteGenerationJob)
        .filter(
            or_(
                SuiteGenerationJob.suite_id == suite_id,
                SuiteGenerationJob.partial_suite_id == suite_id,
            )
        )
        .all()
    )
    for job in generation_jobs:
        if job.suite_id == suite_id:
            job.suite_id = None
        if job.partial_suite_id == suite_id:
            job.partial_suite_id = None

    db.query(SuiteAttachment).filter(SuiteAttachment.suite_id == suite_id).delete()
    db.query(PromptSuiteItem).filter(PromptSuiteItem.suite_id == suite_id).delete()
    db.delete(suite)
    db.commit()
    return {"status": "deleted"}

# Suite Attachment Management

def _build_suite_attachment_response(sa: SuiteAttachment, attachment: Attachment = None, db: Session = None) -> SuiteAttachmentResponse:
    """Build response with nested attachment data and resolved order.

    Can use pre-loaded attachment (for eager loading) or query if db provided.
    """
    # Use pre-loaded attachment or query
    if attachment is None:
        if db is None:
            raise ValueError("Either attachment or db must be provided")
        attachment = db.query(Attachment).filter(Attachment.id == sa.attachment_id).first()

    if not attachment:
        raise HTTPException(status_code=500, detail=f"Attachment {sa.attachment_id} not found (data integrity issue)")

    # Resolve suite_item_id back to order for response
    suite_item_order = None
    if sa.suite_item_id:
        if db:
            item = db.query(PromptSuiteItem).filter(PromptSuiteItem.id == sa.suite_item_id).first()
            if item:
                suite_item_order = item.order
        elif hasattr(sa, 'suite_item') and sa.suite_item:
            suite_item_order = sa.suite_item.order

    return SuiteAttachmentResponse(
        id=sa.id,
        attachment_id=sa.attachment_id,
        scope=sa.scope.value,  # Convert enum to string
        suite_item_order=suite_item_order,
        attachment=AttachmentResponse(
            id=attachment.id,
            filename=attachment.filename,
            mime_type=attachment.mime_type,
            size_bytes=attachment.size_bytes,
            created_at=attachment.created_at
        )
    )

@router.post("/{suite_id}/attachments", response_model=SuiteAttachmentResponse)
def add_suite_attachment(
    suite_id: int,
    data: SuiteAttachmentCreate,
    db: Session = Depends(get_db)
):
    """Attach a file to a suite."""
    # Verify suite exists
    suite = db.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    # Verify attachment exists
    attachment = db.query(Attachment).filter(Attachment.id == data.attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # If scope is "specific", resolve suite_item_order to suite_item_id
    suite_item_id = None
    if data.scope == "specific":
        if data.suite_item_order is None:
            raise HTTPException(status_code=400, detail="suite_item_order required for specific scope")
        item = db.query(PromptSuiteItem).filter(
            PromptSuiteItem.suite_id == suite_id,
            PromptSuiteItem.order == data.suite_item_order
        ).first()
        if not item:
            raise HTTPException(status_code=404, detail=f"Suite item with order {data.suite_item_order} not found")
        suite_item_id = item.id

    suite_attachment = SuiteAttachment(
        suite_id=suite_id,
        attachment_id=data.attachment_id,
        scope=data.scope,
        suite_item_id=suite_item_id
    )
    db.add(suite_attachment)
    db.commit()
    db.refresh(suite_attachment)

    return _build_suite_attachment_response(suite_attachment, db=db)

@router.get("/{suite_id}/attachments", response_model=List[SuiteAttachmentResponse])
def list_suite_attachments(suite_id: int, db: Session = Depends(get_db)):
    """List all attachments for a suite."""
    suite = db.query(PromptSuite).filter(PromptSuite.id == suite_id).first()
    if not suite:
        raise HTTPException(status_code=404, detail="Suite not found")

    # Use eager loading to avoid N+1 queries
    suite_attachments = db.query(SuiteAttachment).filter(
        SuiteAttachment.suite_id == suite_id
    ).options(
        joinedload(SuiteAttachment.attachment),
        joinedload(SuiteAttachment.suite_item)
    ).all()

    return [_build_suite_attachment_response(sa, attachment=sa.attachment) for sa in suite_attachments]

@router.delete("/{suite_id}/attachments/{attachment_id}")
def remove_suite_attachment(
    suite_id: int,
    attachment_id: int,
    db: Session = Depends(get_db)
):
    """Remove attachment from suite (doesn't delete the attachment file)."""
    suite_attachment = db.query(SuiteAttachment).filter(
        SuiteAttachment.suite_id == suite_id,
        SuiteAttachment.attachment_id == attachment_id
    ).first()

    if not suite_attachment:
        raise HTTPException(status_code=404, detail="Suite attachment not found")

    db.delete(suite_attachment)
    db.commit()
    return {"status": "removed"}
