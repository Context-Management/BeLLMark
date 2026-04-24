# backend/app/api/benchmarks.py
import os
from collections import defaultdict
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import List

from app.db.database import get_db
from app.db.models import (
    BenchmarkRun, Question, Generation, Judgment, ModelPreset,
    RunStatus, TaskStatus, JudgeMode, QuestionAttachment, SuiteAttachment, Attachment
)
import logging

logger = logging.getLogger(__name__)
from app.schemas.benchmarks import (
    BenchmarkCreate, BenchmarkListResponse, BenchmarkDetailResponse,
    BenchmarkStartResponse, QuestionDetail, GenerationDetail, JudgmentDetail,
    JudgeSummary, ModelPerformanceMetrics, JudgePerformanceMetrics, QuestionAttachmentInfo,
    TopModelEntry
)
from app.core.runner import BenchmarkRunner, active_runners
from app.core.pricing import get_model_prices, calculate_model_cost
from app.core.judges import detect_family_overlap
from app.core.display_labels import resolve_display_labels
from app.core.model_validation import LOCAL_PROVIDERS, validate_run_local_presets
from app.core.spinoffs import deep_copy_questions_and_generations
from app.api.elo import invalidate_aggregate_leaderboard_cache

router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])

# Add environment flag to disable background runs for testing
DISABLE_BACKGROUND_RUNS = os.getenv("BELLMARK_DISABLE_BACKGROUND_RUNS", "").lower() in ("1", "true", "yes")
BLOCKED_LOCAL_VALIDATION_STATUSES = {"missing", "server_unreachable", "needs_probe", "validation_failed"}


def _calculate_judge_summary_from_objects(questions, model_presets):
    """Calculate judge agreement statistics from SQLAlchemy objects."""
    # Initialize per-judge winner counts
    per_judge_winners = {}

    # Track agreement per question
    disagreement_questions = []
    total_questions = 0
    agreed_questions = 0

    for q in questions:
        # Get successful judgments only
        successful_judgments = [j for j in q.judgments if j.status == TaskStatus.success]

        if len(successful_judgments) == 0:
            continue

        # Only count questions with comparison-mode judgments (with rankings)
        has_rankings = any(j.rankings and len(j.rankings) > 0 and j.blind_mapping for j in successful_judgments)
        if not has_rankings:
            continue

        total_questions += 1

        # Track winners from each judge for this question
        winners_this_question = []

        for j in successful_judgments:
            judge_name = model_presets.get(j.judge_preset_id, "Unknown")

            # Determine winner from rankings
            if j.rankings and len(j.rankings) > 0 and j.blind_mapping:
                winner_label = j.rankings[0]
                winner_id = j.blind_mapping.get(winner_label)
                winner_name = model_presets.get(winner_id, "Unknown")

                # Track for per-judge winner count
                if judge_name not in per_judge_winners:
                    per_judge_winners[judge_name] = {}
                if winner_name not in per_judge_winners[judge_name]:
                    per_judge_winners[judge_name][winner_name] = 0
                per_judge_winners[judge_name][winner_name] += 1

                # Track for agreement calculation
                winners_this_question.append(winner_name)

        # Check if all judges agree (all selected same winner)
        if len(winners_this_question) > 0:
            if len(set(winners_this_question)) == 1:
                agreed_questions += 1
            else:
                disagreement_questions.append(q.order)

    # Calculate agreement rate
    agreement_rate = agreed_questions / total_questions if total_questions > 0 else 0.0

    return JudgeSummary(
        agreement_rate=agreement_rate,
        disagreement_count=len(disagreement_questions),
        disagreement_questions=disagreement_questions,
        per_judge_winners=per_judge_winners
    )


async def run_benchmark_task(run_id: int):
    """Background task to run benchmark."""
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        runner = BenchmarkRunner(db, run_id)
        active_runners[run_id] = runner
        await runner.run()
    finally:
        active_runners.pop(run_id, None)
        db.close()


async def run_spinoff_task(run_id: int):
    """Background task to run a spin-off benchmark (generations exist, only judge)."""
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        runner = BenchmarkRunner(db, run_id)
        active_runners[run_id] = runner
        await runner.resume()
    finally:
        active_runners.pop(run_id, None)
        db.close()


@router.post("/", response_model=BenchmarkStartResponse)
async def create_benchmark(
    benchmark: BenchmarkCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create and start a new benchmark run."""
    # Validate that all model and judge IDs exist and are not archived
    model_presets = db.query(ModelPreset).filter(
        ModelPreset.id.in_(benchmark.model_ids)
    ).all()
    if len(model_presets) != len(benchmark.model_ids):
        raise HTTPException(status_code=400, detail="One or more model IDs not found")
    archived_models = [p.name for p in model_presets if p.is_archived]
    if archived_models:
        raise HTTPException(status_code=400, detail=f"Archived models cannot be benchmarked: {', '.join(archived_models)}")

    judge_presets = db.query(ModelPreset).filter(
        ModelPreset.id.in_(benchmark.judge_ids)
    ).all()
    if len(judge_presets) != len(benchmark.judge_ids):
        raise HTTPException(status_code=400, detail="One or more judge IDs not found")
    archived_judges = [p.name for p in judge_presets if p.is_archived]
    if archived_judges:
        raise HTTPException(status_code=400, detail=f"Archived models cannot be used as judges: {', '.join(archived_judges)}")

    selected_local_presets = [
        preset for preset in [*model_presets, *judge_presets]
        if preset.provider in LOCAL_PROVIDERS and not preset.is_archived
    ]
    validation_results = await validate_run_local_presets(db, selected_local_presets)
    blocked_results = [result for result in validation_results if result.status in BLOCKED_LOCAL_VALIDATION_STATUSES]
    if blocked_results:
        preset_by_id = {preset.id: preset for preset in [*model_presets, *judge_presets]}

        def describe(result):
            preset = preset_by_id.get(result.preset_id)
            if preset is None:
                return f"preset {result.preset_id}"
            return preset.name

        grouped: dict[str, list[str]] = defaultdict(list)
        for result in blocked_results:
            grouped[result.status].append(describe(result))

        parts = []
        for status in ("missing", "server_unreachable", "needs_probe", "validation_failed"):
            names = grouped.get(status)
            if names:
                parts.append(f"{status}: {', '.join(names)}")

        raise HTTPException(
            status_code=400,
            detail=f"Local preset validation failed before benchmark start: {'; '.join(parts)}",
        )

    if validation_results:
        db.commit()

    # Prevent self-judging: models cannot judge their own outputs
    overlap = set(benchmark.model_ids) & set(benchmark.judge_ids)
    if overlap:
        overlap_names = [
            p.name for p in model_presets if p.id in overlap
        ] or [
            p.name for p in judge_presets if p.id in overlap
        ]
        raise HTTPException(
            status_code=400,
            detail=f"Self-judging detected: {', '.join(overlap_names)} selected as both competitor and judge. "
                   f"A model cannot judge its own outputs — this creates severe self-enhancement bias."
        )

    # If this is a spin-off, validate the parent run exists
    parent_run = None
    if benchmark.parent_run_id is not None:
        parent_run = db.query(BenchmarkRun).filter(BenchmarkRun.id == benchmark.parent_run_id).first()
        if not parent_run:
            raise HTTPException(status_code=404, detail=f"Parent run {benchmark.parent_run_id} not found")

    # Build run config snapshot
    def snapshot_preset(preset):
        reasoning_level = getattr(preset, "reasoning_level", None)
        if hasattr(reasoning_level, "value"):
            reasoning_level = reasoning_level.value

        return {
            "id": preset.id,
            "name": preset.name,
            "provider": preset.provider.value if hasattr(preset.provider, "value") else str(preset.provider),
            "base_url": preset.base_url,
            "model_id": preset.model_id,
            "quantization": preset.quantization,
            "model_format": preset.model_format,
            "model_source": preset.model_source,
            "is_reasoning": getattr(preset, "is_reasoning", None),
            "reasoning_level": reasoning_level,
            "selected_variant": getattr(preset, "selected_variant", None),
            "model_architecture": getattr(preset, "model_architecture", None),
        }

    snapshot = {
        "judge_mode": benchmark.judge_mode.value if hasattr(benchmark.judge_mode, "value") else str(benchmark.judge_mode),
        "temperature": benchmark.temperature,
        "temperature_mode": benchmark.temperature_mode.value if hasattr(benchmark.temperature_mode, "value") else str(benchmark.temperature_mode),
        "criteria": [c.model_dump() for c in benchmark.criteria],
        "models": [snapshot_preset(m) for m in model_presets],
        "judges": [snapshot_preset(j) for j in judge_presets],
    }

    # Validate all attachment IDs exist BEFORE creating the run (only for normal runs)
    if parent_run is None:
        all_attachment_ids = set()
        for q in benchmark.questions:
            all_attachment_ids.update(q.attachment_ids)

        if all_attachment_ids:
            existing_ids = {a.id for a in db.query(Attachment.id).filter(
                Attachment.id.in_(all_attachment_ids)
            ).all()}
            missing_ids = all_attachment_ids - existing_ids
            if missing_ids:
                raise HTTPException(status_code=400, detail=f"Attachment IDs not found: {missing_ids}")

    # Create BenchmarkRun
    run = BenchmarkRun(
        name=benchmark.name,
        status=RunStatus.pending,
        judge_mode=benchmark.judge_mode,
        criteria=[c.model_dump() for c in benchmark.criteria],
        model_ids=benchmark.model_ids,
        judge_ids=benchmark.judge_ids,
        temperature=benchmark.temperature,
        temperature_mode=benchmark.temperature_mode,
        run_config_snapshot=snapshot,
        source_suite_id=benchmark.source_suite_id,
        sequential_mode=benchmark.sequential_mode,
        parent_run_id=benchmark.parent_run_id,
    )
    db.add(run)
    db.flush()  # Get run.id without committing — entire create is one transaction

    if parent_run is not None:
        # Spin-off path: deep-copy questions and their completed generations from parent
        deep_copy_questions_and_generations(db, parent_run.id, run.id)
    else:
        # Normal path: create questions from the request payload
        # Pre-fetch suite attachments if applicable (avoid N+1 in loop)
        suite_attachments = []
        if benchmark.source_suite_id:
            suite_attachments = db.query(SuiteAttachment).options(
                joinedload(SuiteAttachment.suite_item)
            ).filter(
                SuiteAttachment.suite_id == benchmark.source_suite_id
            ).all()

        for i, q in enumerate(benchmark.questions):
            question = Question(
                benchmark_id=run.id,
                order=i,
                system_prompt=q.system_prompt,
                user_prompt=q.user_prompt,
                expected_answer=q.expected_answer
            )
            db.add(question)
            db.flush()  # Get question.id before adding attachments

            # After creating question, link attachments
            # First inherit from suite if applicable
            for sa in suite_attachments:
                # Include if scope is all_questions or matches this question's order
                if sa.scope.value == "all_questions" or (sa.suite_item and sa.suite_item.order == i):
                    qa = QuestionAttachment(
                        question_id=question.id,
                        attachment_id=sa.attachment_id,
                        inherited=1  # From suite
                    )
                    db.add(qa)

            # Then add question-specific attachments
            for att_id in q.attachment_ids:
                qa = QuestionAttachment(
                    question_id=question.id,
                    attachment_id=att_id,
                    inherited=0  # Added at run time
                )
                db.add(qa)

    # Single atomic commit: BenchmarkRun + all Questions + all attachments
    db.commit()
    db.refresh(run)

    # Start background task (unless disabled for testing)
    if not DISABLE_BACKGROUND_RUNS:
        if parent_run is not None:
            # Spin-off: generations exist, only judging needed → use resume()
            background_tasks.add_task(run_spinoff_task, run.id)
        else:
            background_tasks.add_task(run_benchmark_task, run.id)

    # Detect family-level judge/model overlap (C18 — preference leakage warning)
    eval_model_ids = [m.model_id for m in model_presets]
    family_warnings: list[dict] = []
    for judge in judge_presets:
        family_warnings.extend(detect_family_overlap(judge.model_id, eval_model_ids))

    return BenchmarkStartResponse(id=run.id, status="started", warnings=family_warnings)


@router.get("/", response_model=List[BenchmarkListResponse])
def list_benchmarks(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List all benchmark runs with pagination.

    Optimized: uses 5 batch SQL queries instead of N+1 lazy loading.
    """
    runs = db.query(BenchmarkRun).order_by(BenchmarkRun.created_at.desc()).offset(offset).limit(limit).all()
    if not runs:
        return []

    # All subsequent batch queries must be scoped to just these run IDs — without
    # this filter they scan successful generations/judgments across the entire DB
    # history on every request (hundreds of ms wasted pulling rows for runs the
    # caller isn't even going to render).
    run_ids = [r.id for r in runs]

    # Get all model IDs across all runs for name/pricing lookup
    all_model_ids = set()
    for run in runs:
        all_model_ids.update(run.model_ids)
        all_model_ids.update(run.judge_ids)

    model_preset_map = {
        m.id: m for m in db.query(ModelPreset).filter(ModelPreset.id.in_(all_model_ids)).all()
    }

    # Batch query 1: question counts per benchmark (scoped to the listed runs)
    q_counts = dict(
        db.query(Question.benchmark_id, func.count(Question.id))
        .filter(Question.benchmark_id.in_(run_ids))
        .group_by(Question.benchmark_id).all()
    )

    # Batch query 2: all successful judgments with scores (for weighted score calculation)
    score_rows = (
        db.query(Question.benchmark_id, Question.id.label("question_id"), Judgment.scores)
        .select_from(Judgment)
        .join(Question, Judgment.question_id == Question.id)
        .filter(
            Question.benchmark_id.in_(run_ids),
            Judgment.status == TaskStatus.success,
            Judgment.scores.isnot(None),
        ).all()
    )

    # Group: rqmc_scores[run_id][question_id][model_id][criterion] = [judge_scores]
    rqmc_scores = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(list))))
    for benchmark_id, question_id, scores in score_rows:
        if not scores:
            continue
        for mid_str, crit_scores in scores.items():
            mid = int(mid_str)
            if not isinstance(crit_scores, dict):
                continue
            for crit, score in crit_scores.items():
                if score is not None:
                    rqmc_scores[benchmark_id][question_id][mid][crit].append(score)

    # Batch query 3: generation token totals per (benchmark, model)
    gen_tokens = (
        db.query(
            Question.benchmark_id,
            Generation.model_preset_id,
            func.sum(Generation.tokens).label('total_tokens'),
            func.sum(Generation.input_tokens).label('input_tokens'),
            func.sum(Generation.output_tokens).label('output_tokens'),
            func.sum(Generation.cached_input_tokens).label('cached_input_tokens'),
        )
        .select_from(Generation)
        .join(Question, Generation.question_id == Question.id)
        .filter(
            Question.benchmark_id.in_(run_ids),
            Generation.status == TaskStatus.success,
            Generation.tokens.isnot(None),
        )
        .group_by(Question.benchmark_id, Generation.model_preset_id)
        .all()
    )

    # Batch query 4: judgment token totals per (benchmark, judge)
    jud_tokens = (
        db.query(
            Question.benchmark_id,
            Judgment.judge_preset_id,
            func.sum(Judgment.tokens).label('total_tokens'),
            func.sum(Judgment.input_tokens).label('input_tokens'),
            func.sum(Judgment.output_tokens).label('output_tokens'),
            func.sum(Judgment.cached_input_tokens).label('cached_input_tokens'),
        )
        .select_from(Judgment)
        .join(Question, Judgment.question_id == Question.id)
        .filter(
            Question.benchmark_id.in_(run_ids),
            Judgment.status == TaskStatus.success,
            Judgment.tokens.isnot(None),
        )
        .group_by(Question.benchmark_id, Judgment.judge_preset_id)
        .all()
    )

    # Calculate costs per benchmark from batch data
    run_costs: dict[int, float] = {}
    for benchmark_id, model_id, total_tokens, input_tokens, output_tokens, cached_input_tokens in gen_tokens:
        preset = model_preset_map.get(model_id)
        if preset and total_tokens:
            if preset.price_input is not None and preset.price_output is not None:
                price_in, price_out = preset.price_input, preset.price_output
            else:
                price_in, price_out = get_model_prices(preset.provider.value, preset.model_id)
            cost, _ = calculate_model_cost(
                preset.provider.value,
                preset.model_id,
                price_in,
                price_out,
                total_tokens=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
                cached_input_price=price_in if preset.price_input is not None and preset.price_output is not None else None,
            )
            run_costs[benchmark_id] = run_costs.get(benchmark_id, 0) + cost

    for benchmark_id, judge_id, total_tokens, input_tokens, output_tokens, cached_input_tokens in jud_tokens:
        preset = model_preset_map.get(judge_id)
        if preset and total_tokens:
            if preset.price_input is not None and preset.price_output is not None:
                price_in, price_out = preset.price_input, preset.price_output
            else:
                price_in, price_out = get_model_prices(preset.provider.value, preset.model_id)
            cost, _ = calculate_model_cost(
                preset.provider.value,
                preset.model_id,
                price_in,
                price_out,
                total_tokens=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
                cached_input_price=price_in if preset.price_input is not None and preset.price_output is not None else None,
            )
            run_costs[benchmark_id] = run_costs.get(benchmark_id, 0) + cost

    # Build response from pre-computed data
    result = []
    for run in runs:
        # Top models by weighted score
        run_criteria = run.criteria or []
        weight_map_run = {c["name"]: c.get("weight", 1.0) for c in run_criteria}
        total_weight_run = sum(weight_map_run.values()) or 1.0

        model_weighted_avgs: dict[int, list[float]] = defaultdict(list)
        run_question_data = rqmc_scores.get(run.id, {})
        for q_id, q_model_data in run_question_data.items():
            for mid, crit_data in q_model_data.items():
                weighted_sum = 0.0
                has_any = False
                for c in run_criteria:
                    crit_name = c["name"]
                    judge_scores = crit_data.get(crit_name, [])
                    if judge_scores:
                        has_any = True
                        avg_score = sum(judge_scores) / len(judge_scores)
                        weighted_sum += avg_score * weight_map_run.get(crit_name, 1.0)
                if has_any:
                    model_weighted_avgs[mid].append(weighted_sum / total_weight_run)

        # Average across questions, sort, take top 5
        model_final_scores = {}
        for mid, q_scores in model_weighted_avgs.items():
            if q_scores:
                model_final_scores[mid] = sum(q_scores) / len(q_scores)

        sorted_top = sorted(model_final_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        top_models = [
            TopModelEntry(
                name=(model_preset_map[mid].name if mid in model_preset_map else "Unknown"),
                weighted_score=round(score, 4),
            )
            for mid, score in sorted_top
        ]

        total_cost = run_costs.get(run.id, 0.0)

        result.append(BenchmarkListResponse(
            id=run.id,
            name=run.name,
            status=run.status,
            created_at=run.created_at,
            model_count=len(run.model_ids),
            model_ids=run.model_ids,
            judge_count=len(run.judge_ids),
            judge_ids=run.judge_ids,
            question_count=q_counts.get(run.id, 0),
            top_models=top_models,
            total_cost=round(total_cost, 4) if total_cost > 0 else None
        ))

    return result


@router.get("/{run_id}/compare-parent")
def compare_with_parent(run_id: int, db: Session = Depends(get_db)):
    """Compare a spin-off run against its parent run.

    Returns a summary object with run metadata and per-model score info
    for both the spinoff and its parent, enabling delta analysis.
    """
    from app.core.exports.common import prepare_export_data

    spinoff = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not spinoff:
        raise HTTPException(status_code=404, detail="Benchmark run not found")
    if spinoff.parent_run_id is None:
        raise HTTPException(
            status_code=400,
            detail="This run is not a spin-off — it has no parent run to compare against",
        )

    parent = db.query(BenchmarkRun).filter(BenchmarkRun.id == spinoff.parent_run_id).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent run not found")

    def _summarize(run: BenchmarkRun) -> dict:
        """Build a compact summary from export data."""
        data = prepare_export_data(db, run.id)
        if data is None:
            return {}

        # Extract judge names
        judge_ids = run.judge_ids or []
        judge_presets = db.query(ModelPreset).filter(ModelPreset.id.in_(judge_ids)).all()
        judge_names = [p.name for p in judge_presets]

        # Per-model average weighted score across all questions
        model_scores: dict[str, float | None] = {}
        if data.get("models"):
            for m in data["models"]:
                model_scores[m["name"]] = m.get("avg_weighted_score")

        return {
            "run_id": run.id,
            "name": run.name,
            "status": run.status.value,
            "judge_mode": run.judge_mode.value,
            "judges": judge_names,
            "criteria": run.criteria,
            "model_scores": model_scores,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

    return {
        "spinoff": _summarize(spinoff),
        "parent": _summarize(parent),
    }


@router.get("/compare")
def compare_benchmarks(ids: str, db: Session = Depends(get_db)):
    """Compare multiple benchmark runs."""
    run_ids = [int(x) for x in ids.split(",")]
    unique_run_ids = list(set(run_ids))

    runs = db.query(BenchmarkRun).filter(BenchmarkRun.id.in_(unique_run_ids)).all()
    if len(runs) != len(unique_run_ids):
        raise HTTPException(status_code=404, detail="One or more runs not found")

    # Load model presets for name lookups
    all_model_ids = set()
    for run in runs:
        all_model_ids.update(run.model_ids)
    all_preset_objects = {m.id: m for m in db.query(ModelPreset).filter(ModelPreset.id.in_(all_model_ids)).all()}

    result = {"runs": []}

    for run in runs:
        # Resolve labels per-run to avoid cross-run collision contamination
        run_presets = [all_preset_objects[mid] for mid in run.model_ids if mid in all_preset_objects]
        run_labels = resolve_display_labels(run_presets)
        model_presets = {mid: run_labels.get(mid, all_preset_objects[mid].name) for mid in run.model_ids if mid in all_preset_objects}
        model_scores = {}
        win_counts = {}

        # Build weight map from criteria
        weight_map = {c["name"]: c.get("weight", 1.0) for c in run.criteria}
        total_weight = sum(weight_map.values())

        for question in run.questions:
            for judgment in question.judgments:
                if judgment.status != TaskStatus.success:
                    continue

                # Count wins
                if judgment.rankings and judgment.blind_mapping:
                    winner_label = judgment.rankings[0]
                    winner_id = judgment.blind_mapping.get(winner_label)
                    if winner_id:
                        winner_name = model_presets.get(winner_id, "Unknown")
                        win_counts[winner_name] = win_counts.get(winner_name, 0) + 1

                # Aggregate scores per criterion
                if judgment.scores:
                    for model_id_str, criterion_scores in judgment.scores.items():
                        model_name = model_presets.get(int(model_id_str), "Unknown")
                        if model_name not in model_scores:
                            model_scores[model_name] = {}
                        for criterion, score in criterion_scores.items():
                            if criterion not in model_scores[model_name]:
                                model_scores[model_name][criterion] = []
                            model_scores[model_name][criterion].append(score)

        # Calculate unweighted and weighted averages
        avg_scores = {}
        weighted_scores = {}
        for model_name, criterion_scores in model_scores.items():
            # Unweighted average (all scores)
            all_scores = []
            for scores in criterion_scores.values():
                all_scores.extend(scores)
            avg_scores[model_name] = sum(all_scores) / len(all_scores) if all_scores else 0

            # Weighted average (by criterion weight)
            weighted_sum = 0
            for criterion, scores in criterion_scores.items():
                weight = weight_map.get(criterion, 1.0)
                avg = sum(scores) / len(scores) if scores else 0
                weighted_sum += avg * weight
            weighted_scores[model_name] = weighted_sum / total_weight if total_weight > 0 else 0

        result["runs"].append({
            "id": run.id,
            "name": run.name,
            "model_scores": avg_scores,
            "weighted_scores": weighted_scores,
            "win_counts": win_counts
        })

    return result


def _build_question_detail(question, model_presets: dict, db: Session) -> QuestionDetail:
    """Build question detail with attachments."""
    # Build generations
    generations = [
        GenerationDetail(
            id=gen.id,
            model_preset_id=gen.model_preset_id,
            model_name=model_presets.get(gen.model_preset_id, "Unknown"),
            content=gen.content,
            tokens=gen.tokens,
            input_tokens=gen.input_tokens,
            output_tokens=gen.output_tokens,
            cached_input_tokens=gen.cached_input_tokens,
            reasoning_tokens=gen.reasoning_tokens,
            raw_chars=gen.raw_chars,
            answer_chars=gen.answer_chars,
            latency_ms=gen.latency_ms,
            status=gen.status,
            error=gen.error,
            retries=gen.retries,
            completed_at=gen.completed_at
        )
        for gen in question.generations
    ]

    # Build judgments
    judgments = [
        JudgmentDetail(
            id=judge.id,
            judge_preset_id=judge.judge_preset_id,
            judge_name=model_presets.get(judge.judge_preset_id, "Unknown"),
            generation_id=judge.generation_id,
            blind_mapping=judge.blind_mapping,
            rankings=judge.rankings,
            scores=judge.scores,
            score_rationales=judge.score_rationales,
            reasoning=judge.reasoning,
            comments=judge.comments,
            latency_ms=judge.latency_ms,
            tokens=judge.tokens,
            input_tokens=judge.input_tokens,
            output_tokens=judge.output_tokens,
            cached_input_tokens=judge.cached_input_tokens,
            reasoning_tokens=judge.reasoning_tokens,
            status=judge.status,
            error=judge.error,
            retries=judge.retries,
            completed_at=judge.completed_at
        )
        for judge in question.judgments
    ]

    # Build attachments
    attachments = []
    question_attachments = db.query(QuestionAttachment).filter(
        QuestionAttachment.question_id == question.id
    ).options(joinedload(QuestionAttachment.attachment)).all()

    for qa in question_attachments:
        attachments.append(QuestionAttachmentInfo(
            id=qa.attachment.id,
            filename=qa.attachment.filename,
            mime_type=qa.attachment.mime_type,
            inherited=bool(qa.inherited)
        ))

    return QuestionDetail(
        id=question.id,
        order=question.order,
        system_prompt=question.system_prompt,
        user_prompt=question.user_prompt,
        expected_answer=question.expected_answer,
        estimated_context_tokens=question.context_tokens,
        attachments=attachments,
        generations=generations,
        judgments=judgments
    )


@router.get("/{run_id}", response_model=BenchmarkDetailResponse)
def get_benchmark(run_id: int, db: Session = Depends(get_db)):
    """Get detailed benchmark run information with all results."""
    # Use eager loading to avoid N+1 queries
    run = db.query(BenchmarkRun).options(
        joinedload(BenchmarkRun.questions).joinedload(Question.generations),
        joinedload(BenchmarkRun.questions).joinedload(Question.judgments)
    ).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")

    # Load full model presets for name lookups and pricing
    model_preset_objects = {
        m.id: m for m in
        db.query(ModelPreset).filter(ModelPreset.id.in_(run.model_ids + run.judge_ids)).all()
    }
    resolved_labels = resolve_display_labels(list(model_preset_objects.values()))
    model_presets = {m_id: resolved_labels.get(m_id, m.name) for m_id, m in model_preset_objects.items()}

    # Build questions with all details (relationships already loaded)
    questions = []
    for question in run.questions:
        questions.append(_build_question_detail(question, model_presets, db))

    # Calculate judge summary
    judge_summary = _calculate_judge_summary_from_objects(run.questions, model_presets)

    # Calculate performance metrics per model
    performance_metrics = {}
    for model_id in run.model_ids:
        preset = model_preset_objects.get(model_id)
        if not preset:
            continue

        model_name = preset.name
        total_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_input_tokens = 0
        total_latency_ms = 0

        # Aggregate from all successful generations
        for question in run.questions:
            for gen in question.generations:
                if gen.model_preset_id == model_id and gen.status == TaskStatus.success:
                    total_tokens += gen.tokens or 0
                    total_input_tokens += gen.input_tokens or 0
                    total_output_tokens += gen.output_tokens or 0
                    total_cached_input_tokens += gen.cached_input_tokens or 0
                    total_latency_ms += gen.latency_ms or 0

        # Calculate tokens per second
        tokens_per_second = None
        if total_latency_ms > 0:
            tokens_per_second = round(total_tokens / (total_latency_ms / 1000), 1)

        # Calculate estimated cost
        # Get pricing (preset override or provider default)
        if preset.price_input is not None and preset.price_output is not None:
            price_in, price_out = preset.price_input, preset.price_output
        else:
            price_in, price_out = get_model_prices(preset.provider.value, preset.model_id)

        estimated_cost, _ = calculate_model_cost(
            preset.provider.value,
            preset.model_id,
            price_in,
            price_out,
            total_tokens=total_tokens,
            input_tokens=total_input_tokens if total_input_tokens > 0 else None,
            output_tokens=total_output_tokens if total_output_tokens > 0 else None,
            cached_input_tokens=total_cached_input_tokens if total_cached_input_tokens > 0 else None,
            cached_input_price=price_in if preset.price_input is not None and preset.price_output is not None else None,
        )
        estimated_cost = round(estimated_cost, 4)

        performance_metrics[model_name] = ModelPerformanceMetrics(
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
            tokens_per_second=tokens_per_second,
            estimated_cost=estimated_cost,
            price_input_1m=price_in,
            price_output_1m=price_out,
            provider=preset.provider.value
        )

    # Calculate judge performance metrics
    judge_metrics = {}
    for judge_id in run.judge_ids:
        judge_preset = model_preset_objects.get(judge_id)
        if not judge_preset:
            continue

        judge_name = judge_preset.name
        total_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_input_tokens = 0
        total_latency_ms = 0
        judgment_count = 0

        # Aggregate from all successful judgments for this judge
        for question in run.questions:
            for judgment in question.judgments:
                if judgment.judge_preset_id == judge_id and judgment.status == TaskStatus.success:
                    total_tokens += judgment.tokens or 0
                    total_input_tokens += judgment.input_tokens or 0
                    total_output_tokens += judgment.output_tokens or 0
                    total_cached_input_tokens += judgment.cached_input_tokens or 0
                    total_latency_ms += judgment.latency_ms or 0
                    judgment_count += 1

        # Calculate tokens per second
        tokens_per_second = None
        if total_latency_ms > 0:
            tokens_per_second = round(total_tokens / (total_latency_ms / 1000), 1)

        # Calculate estimated cost
        if judge_preset.price_input is not None and judge_preset.price_output is not None:
            price_in, price_out = judge_preset.price_input, judge_preset.price_output
        else:
            price_in, price_out = get_model_prices(judge_preset.provider.value, judge_preset.model_id)

        estimated_cost, _ = calculate_model_cost(
            judge_preset.provider.value,
            judge_preset.model_id,
            price_in,
            price_out,
            total_tokens=total_tokens,
            input_tokens=total_input_tokens if total_input_tokens > 0 else None,
            output_tokens=total_output_tokens if total_output_tokens > 0 else None,
            cached_input_tokens=total_cached_input_tokens if total_cached_input_tokens > 0 else None,
            cached_input_price=price_in if judge_preset.price_input is not None and judge_preset.price_output is not None else None,
        )
        estimated_cost = round(estimated_cost, 4)

        judge_metrics[judge_name] = JudgePerformanceMetrics(
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
            tokens_per_second=tokens_per_second,
            estimated_cost=estimated_cost,
            judgment_count=judgment_count
        )

    return BenchmarkDetailResponse(
        id=run.id,
        name=run.name,
        status=run.status,
        judge_mode=run.judge_mode,
        criteria=run.criteria,
        model_ids=run.model_ids,
        judge_ids=run.judge_ids,
        created_at=run.created_at,
        completed_at=run.completed_at,
        preset_labels=model_presets,
        questions=questions,
        run_config_snapshot=run.run_config_snapshot,
        source_suite_id=run.source_suite_id,
        judge_summary=judge_summary,
        performance_metrics=performance_metrics,
        judge_metrics=judge_metrics,
        comment_summaries=run.comment_summaries
    )


@router.post("/{run_id}/retry/{item_type}/{item_id}")
async def retry_item(
    run_id: int,
    item_type: str,
    item_id: int,
    db: Session = Depends(get_db)
):
    """Manually retry a specific failed generation or judgment."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")

    if item_type == "generation":
        gen = db.query(Generation).filter(Generation.id == item_id).first()
        if not gen:
            raise HTTPException(status_code=404, detail="Generation not found")

        # Load model preset and question
        preset = db.query(ModelPreset).filter(ModelPreset.id == gen.model_preset_id).first()
        question = gen.question

        if not preset or not question:
            raise HTTPException(status_code=400, detail="Invalid generation state")

        # Create a temporary runner to retry
        runner = BenchmarkRunner(db, run_id)
        await runner._generate_with_retry(
            gen.id,
            preset,
            question.id,
            question.system_prompt,
            question.user_prompt,
            preset.name,
        )

        # Successful generation retry can change which models "successfully
        # generated" for this question, which flows into the leaderboard.
        invalidate_aggregate_leaderboard_cache()
        return {"status": "retried", "item_type": "generation", "item_id": item_id}

    elif item_type == "judgment":
        judgment = db.query(Judgment).filter(Judgment.id == item_id).first()
        if not judgment:
            raise HTTPException(status_code=404, detail="Judgment not found")

        # Load judge preset and question
        preset = db.query(ModelPreset).filter(ModelPreset.id == judgment.judge_preset_id).first()
        question = judgment.question

        if not preset or not question:
            raise HTTPException(status_code=400, detail="Invalid judgment state")

        # Create a temporary runner to retry
        runner = BenchmarkRunner(db, run_id)

        if run.judge_mode == JudgeMode.comparison:
            # Get all successful generations for this question
            generations = db.query(Generation).filter(
                Generation.question_id == question.id,
                Generation.status == TaskStatus.success
            ).all()
            gen_dict = {g.model_preset_id: g.content for g in generations}
            await runner._judge_comparison_with_retry(
                judgment.id,
                preset,
                question.id,
                question.system_prompt,
                question.user_prompt,
                gen_dict,
                run.criteria,
                preset.name
            )
        else:
            # Separate mode
            gen = judgment.generation
            if not gen:
                raise HTTPException(status_code=400, detail="No generation associated with judgment")
            await runner._judge_separate_with_retry(
                judgment.id,
                preset,
                question.id,
                question.system_prompt,
                question.user_prompt,
                gen.content,
                gen.model_preset_id,
                run.criteria,
                preset.name
            )

        # Successful judgment retry changes scores/rankings that feed the
        # leaderboard aggregation.
        invalidate_aggregate_leaderboard_cache()
        return {"status": "retried", "item_type": "judgment", "item_id": item_id}

    else:
        raise HTTPException(status_code=400, detail="Invalid item_type. Must be 'generation' or 'judgment'")


@router.post("/{run_id}/rerun")
async def rerun_benchmark(
    run_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Rerun a failed or completed benchmark."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")

    if run.status == RunStatus.running or run_id in active_runners:
        raise HTTPException(status_code=400, detail="Benchmark is already running")

    # Reserve the slot immediately to prevent race condition with concurrent requests
    active_runners[run_id] = None

    # Clear previous generations and judgments
    for question in run.questions:
        db.query(Judgment).filter(Judgment.question_id == question.id).delete()
        db.query(Generation).filter(Generation.question_id == question.id).delete()

    # Reset status
    run.status = RunStatus.pending
    run.completed_at = None
    db.commit()

    # Run has left the `completed` set — invalidate immediately. When it
    # finishes, the runner's completion hook will invalidate again.
    if run.parent_run_id is None:
        invalidate_aggregate_leaderboard_cache()

    # Start background task (unless disabled for testing)
    if not DISABLE_BACKGROUND_RUNS:
        background_tasks.add_task(run_benchmark_task, run.id)

    return {"status": "restarted", "id": run.id}


async def resume_benchmark_task(run_id: int):
    """Background task to resume benchmark.

    Logs any exception with full traceback. Without this, exceptions raised
    during startup auto-resume (asyncio.create_task) are silently swallowed
    and the run shows up as ``failed`` with no clue what went wrong.
    """
    import traceback
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        runner = BenchmarkRunner(db, run_id)
        active_runners[run_id] = runner
        await runner.resume()
    except Exception as e:
        print(f"[Run {run_id}] Resume task crashed: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise
    finally:
        active_runners.pop(run_id, None)
        db.close()


@router.post("/{run_id}/resume")
async def resume_benchmark(
    run_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Resume a benchmark from where it left off, filling in missing generations and judgments."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")

    if run.status == RunStatus.running or run_id in active_runners:
        raise HTTPException(status_code=400, detail="Benchmark is already running")

    # Reserve the slot immediately to prevent race condition with concurrent requests
    active_runners[run_id] = None

    # Reset orphaned "running" generations to "pending" (from crashed/restarted server)
    # Clear ALL judgments — runner.resume() will re-judge from scratch anyway
    for question in run.questions:
        for gen in question.generations:
            if gen.status == TaskStatus.running:
                gen.status = TaskStatus.pending
        db.query(Judgment).filter(Judgment.question_id == question.id).delete()

    # Set status to pending so startup auto-resume can recover if the server
    # crashes after this commit but before the background task starts.
    run.status = RunStatus.pending
    db.commit()

    # Start background task (unless disabled for testing)
    if not DISABLE_BACKGROUND_RUNS:
        background_tasks.add_task(resume_benchmark_task, run.id)

    return {"status": "resumed", "id": run.id}


@router.post("/{run_id}/cancel")
def cancel_benchmark(run_id: int, db: Session = Depends(get_db)):
    """Cancel a running benchmark."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")

    if run.status not in [RunStatus.pending, RunStatus.running]:
        raise HTTPException(status_code=400, detail="Can only cancel pending or running benchmarks")

    # Cancel the active runner if it exists
    runner = active_runners.get(run_id)
    if runner:
        runner.cancel()

    # Immediately mark all pending/running generations and judgments as failed
    db.query(Generation).join(Question).filter(
        Question.benchmark_id == run_id,
        Generation.status.in_([TaskStatus.pending, TaskStatus.running])
    ).update({Generation.status: TaskStatus.failed}, synchronize_session='fetch')

    db.query(Judgment).join(Question).filter(
        Question.benchmark_id == run_id,
        Judgment.status.in_([TaskStatus.pending, TaskStatus.running])
    ).update({Judgment.status: TaskStatus.failed}, synchronize_session='fetch')

    # Update status
    run.status = RunStatus.cancelled
    db.commit()

    return {"status": "cancelled"}


@router.delete("/{run_id}")
def delete_benchmark(run_id: int, db: Session = Depends(get_db)):
    """Delete a benchmark run and all its data."""
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Benchmark run not found")

    if run.status == RunStatus.running:
        raise HTTPException(status_code=400, detail="Cannot delete a running benchmark. Cancel it first.")

    # Only completed non-spin-off runs affect the aggregate leaderboard, so
    # we only need to invalidate when one of those is deleted. Capture this
    # before the delete so we can still read the fields.
    affects_leaderboard = (
        run.status == RunStatus.completed and run.parent_run_id is None
    )

    try:
        # Delete in order: judgments -> generations -> question_attachments -> questions -> run
        for question in run.questions:
            db.query(Judgment).filter(Judgment.question_id == question.id).delete()
            db.query(Generation).filter(Generation.question_id == question.id).delete()
            db.query(QuestionAttachment).filter(QuestionAttachment.question_id == question.id).delete()
        db.query(Question).filter(Question.benchmark_id == run_id).delete()
        db.delete(run)
        db.commit()
        logger.info(f"Deleted benchmark run {run_id}")
        if affects_leaderboard:
            invalidate_aggregate_leaderboard_cache()
        return {"status": "deleted", "id": run_id}
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete benchmark run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete: {str(e)}")
