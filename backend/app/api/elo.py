from collections import defaultdict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import (
    EloRating, EloHistory, ModelPreset, BenchmarkRun,
    Question, Generation, Judgment, RunStatus, TaskStatus, JudgeMode,
)
from app.schemas.elo import EloRatingResponse, EloHistoryPoint, EloLeaderboardResponse, AggregateLeaderboardResponse, AggregateModelEntry
from app.core.display_labels import resolve_display_labels

router = APIRouter(prefix="/api/elo", tags=["elo"])


@router.get("/", response_model=EloLeaderboardResponse)
async def get_elo_leaderboard(db: Session = Depends(get_db)):
    ratings = db.query(EloRating).join(ModelPreset).order_by(EloRating.rating.desc()).all()
    all_presets = [r.model_preset for r in ratings]
    resolved = resolve_display_labels(all_presets)
    items = []
    for r in ratings:
        preset = r.model_preset
        items.append(EloRatingResponse(
            model_id=r.model_preset_id,
            model_name=resolved.get(preset.id, preset.name),
            provider=preset.provider.value,
            rating=round(r.rating, 1),
            uncertainty=round(r.uncertainty, 1),
            games_played=r.games_played,
            updated_at=r.updated_at,
            is_reasoning=bool(preset.is_reasoning),
            reasoning_level=preset.reasoning_level.value if preset.reasoning_level else None,
        ))
    return EloLeaderboardResponse(ratings=items, total_models=len(items))


# --- Aggregate leaderboard cache ----------------------------------------------
#
# Computing the aggregate leaderboard is inherently expensive: it has to walk
# every completed run, every question, and every successful generation/judgment
# across the entire history. Even after the N+1 fix this still costs a couple
# hundred milliseconds against any non-trivial database, which makes the Home
# page feel laggy on every revisit.
#
# Strategy: cache the fully-built `AggregateLeaderboardResponse` in process
# memory and rebuild only when something that could affect the result mutates.
# Invalidation is triggered explicitly from every code path that:
#   1. transitions a run to/from `completed` (runner._update_elo_on_completion,
#      benchmarks.rerun_benchmark, benchmarks.delete_benchmark)
#   2. mutates a successful generation or judgment (benchmarks.retry_item)
#   3. archives a model preset (models.delete_model)
#
# The cache is a single module-level reference. Reads/writes of a single Python
# pointer are atomic under the GIL, so no lock is needed — at worst two concurrent
# requests will both compute and both write the same value.
_cached_aggregate_leaderboard: AggregateLeaderboardResponse | None = None


def invalidate_aggregate_leaderboard_cache() -> None:
    """Drop the cached aggregate leaderboard. Call from any mutation path that
    could change the result of `get_aggregate_leaderboard`."""
    global _cached_aggregate_leaderboard
    _cached_aggregate_leaderboard = None


@router.get("/aggregate-leaderboard", response_model=AggregateLeaderboardResponse)
async def get_aggregate_leaderboard(db: Session = Depends(get_db)):
    global _cached_aggregate_leaderboard
    if _cached_aggregate_leaderboard is not None:
        return _cached_aggregate_leaderboard

    response = _compute_aggregate_leaderboard(db)
    _cached_aggregate_leaderboard = response
    return response


def _compute_aggregate_leaderboard(db: Session) -> AggregateLeaderboardResponse:
    # Fetch all non-archived model presets keyed by id
    all_presets = {p.id: p for p in db.query(ModelPreset).filter(ModelPreset.is_archived == 0).all()}
    resolved = resolve_display_labels(list(all_presets.values()))

    # Accumulators per model_preset_id
    wins: dict[int, int] = defaultdict(int)
    losses: dict[int, int] = defaultdict(int)
    ties: dict[int, int] = defaultdict(int)
    score_sum: dict[int, float] = defaultdict(float)
    scored_questions: dict[int, int] = defaultdict(int)
    runs_participated: dict[int, set] = defaultdict(set)

    # Spin-offs (parent_run_id IS NOT NULL) are excluded so that re-judging the same
    # generations with different criteria does not double-count model performance.
    completed_runs = db.query(BenchmarkRun).filter(
        BenchmarkRun.status == RunStatus.completed,
        BenchmarkRun.parent_run_id.is_(None),
    ).all()

    # Batch-load questions, successful generations, and successful judgments for all
    # completed runs up front. Previously this endpoint issued O(runs + 2 × questions)
    # ORM round-trips — ~3.5k queries for a moderately-used DB — which dominated the
    # response time. Grouping in Python after three bulk fetches gets us to O(1)
    # query count regardless of how much history the user has accumulated.
    run_ids = [r.id for r in completed_runs]
    questions_by_run: dict[int, list[Question]] = defaultdict(list)
    successful_model_ids_by_q: dict[int, set[int]] = defaultdict(set)
    judgments_by_q: dict[int, list[Judgment]] = defaultdict(list)

    if run_ids:
        # Only need (id, benchmark_id) for questions — skip prompts/expected_answer.
        question_rows = db.query(
            Question.id, Question.benchmark_id
        ).filter(Question.benchmark_id.in_(run_ids)).all()
        for qid, bench_id in question_rows:
            questions_by_run[bench_id].append(qid)

        question_ids = [qid for qid, _ in question_rows]
        if question_ids:
            # Only need (question_id, model_preset_id) — skip the massive `content`
            # TEXT column. Hydrating 15k+ full Generation rows dominated the response
            # time even though we never touch the response text.
            gen_rows = db.query(
                Generation.question_id, Generation.model_preset_id
            ).filter(
                Generation.question_id.in_(question_ids),
                Generation.status == TaskStatus.success,
            ).all()
            for qid, mid in gen_rows:
                if mid in all_presets:
                    successful_model_ids_by_q[qid].add(mid)

            # Only need the JSON columns the aggregation logic reads.
            jud_rows = db.query(
                Judgment.question_id,
                Judgment.scores,
                Judgment.rankings,
                Judgment.blind_mapping,
            ).filter(
                Judgment.question_id.in_(question_ids),
                Judgment.status == TaskStatus.success,
            ).all()
            for qid, scores, rankings, blind_mapping in jud_rows:
                judgments_by_q[qid].append((scores, rankings, blind_mapping))

    for run in completed_runs:
        criteria = run.criteria or []
        weight_map = {c["name"]: c.get("weight", 1.0) for c in criteria}
        total_weight = sum(weight_map.values()) or 1.0

        for question_id in questions_by_run.get(run.id, []):
            # Determine which models have a successful generation for this question
            successful_model_ids = successful_model_ids_by_q.get(question_id, set())
            if not successful_model_ids:
                continue

            # Mark participation for each model with a successful generation
            for mid in successful_model_ids:
                runs_participated[mid].add(run.id)

            # Successful judgments for this question (tuples: scores, rankings, blind_mapping)
            judgments = judgments_by_q.get(question_id, [])

            # --- Score aggregation (applies to both modes for avg_weighted_score) ---
            # q_model_crit_scores[model_id][crit_name] = [score, ...]
            q_model_crit_scores: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))

            for jud_scores, _jud_rankings, _jud_blind in judgments:
                if not jud_scores:
                    continue
                for raw_mid, crit_scores in jud_scores.items():
                    mid = int(raw_mid)
                    if mid not in all_presets or not isinstance(crit_scores, dict):
                        continue
                    for crit, score in crit_scores.items():
                        if score is not None:
                            q_model_crit_scores[mid][crit].append(score)

            for mid in successful_model_ids:
                crit_data = q_model_crit_scores.get(mid, {})
                if not crit_data:
                    continue
                weighted_sum = 0.0
                has_any = False
                for crit_name in [c["name"] for c in criteria]:
                    scores = crit_data.get(crit_name, [])
                    if not scores:
                        continue
                    has_any = True
                    avg = sum(scores) / len(scores)
                    weighted_sum += avg * weight_map.get(crit_name, 1.0)
                if has_any:
                    score_sum[mid] += weighted_sum / total_weight
                    scored_questions[mid] += 1

            # --- Win/loss/tie derivation ---
            if run.judge_mode == JudgeMode.comparison:
                # Count how many judges ranked each model first
                first_place_votes: dict[int, int] = defaultdict(int)
                valid_judgments = 0
                for _jud_scores, jud_rankings, jud_blind in judgments:
                    if not jud_rankings or not jud_blind:
                        continue
                    winner_label = jud_rankings[0]
                    winner_id_raw = jud_blind.get(winner_label)
                    if winner_id_raw is None:
                        continue
                    winner_id = int(winner_id_raw)
                    if winner_id not in all_presets:
                        continue
                    first_place_votes[winner_id] += 1
                    valid_judgments += 1

                if valid_judgments == 0:
                    continue

                max_votes = max(first_place_votes.values()) if first_place_votes else 0
                question_winners = {mid for mid, v in first_place_votes.items() if v == max_votes}

                if len(question_winners) == 1:
                    # Clear winner
                    winner = next(iter(question_winners))
                    for mid in successful_model_ids:
                        if mid == winner:
                            wins[mid] += 1
                        else:
                            losses[mid] += 1
                else:
                    # Tie among multiple winners; non-winners get a loss
                    for mid in successful_model_ids:
                        if mid in question_winners:
                            ties[mid] += 1
                        else:
                            losses[mid] += 1

            else:
                # Separate mode: derive winner from weighted scores
                q_weighted: dict[int, float] = {}
                for mid in successful_model_ids:
                    crit_data = q_model_crit_scores.get(mid, {})
                    if not crit_data:
                        continue
                    weighted_sum = 0.0
                    has_any = False
                    for crit_name in [c["name"] for c in criteria]:
                        scores = crit_data.get(crit_name, [])
                        if not scores:
                            continue
                        has_any = True
                        avg = sum(scores) / len(scores)
                        weighted_sum += avg * weight_map.get(crit_name, 1.0)
                    if has_any:
                        q_weighted[mid] = weighted_sum / total_weight

                if not q_weighted:
                    continue

                max_score = max(q_weighted.values())
                EPSILON = 0.01
                question_winners = {mid for mid, s in q_weighted.items() if abs(s - max_score) < EPSILON}

                if len(question_winners) == 1:
                    winner = next(iter(question_winners))
                    for mid in successful_model_ids:
                        if mid == winner:
                            wins[mid] += 1
                        else:
                            losses[mid] += 1
                else:
                    for mid in successful_model_ids:
                        if mid in question_winners:
                            ties[mid] += 1
                        else:
                            losses[mid] += 1

    # Build response entries for all models that participated in at least one run
    # or that appear in any run's model_ids (even if wins/losses are zero)
    # Actually: only include models that have participation data.
    all_involved = set(wins) | set(losses) | set(ties) | set(scored_questions)
    # Also include models that participated but had all nulls (runs_participated has them)
    all_involved |= set(runs_participated)
    # Filter to non-archived models only
    all_involved = {mid for mid in all_involved if mid in all_presets}

    entries = []
    for mid in all_involved:
        preset = all_presets[mid]
        total_q = wins[mid] + losses[mid] + ties[mid]
        sq = scored_questions[mid]
        entries.append(AggregateModelEntry(
            model_preset_id=mid,
            model_name=resolved.get(mid, preset.name),
            provider=preset.provider.value,
            questions_won=wins[mid],
            questions_lost=losses[mid],
            questions_tied=ties[mid],
            total_questions=total_q,
            win_rate=(wins[mid] / total_q) if total_q > 0 else None,
            avg_weighted_score=(score_sum[mid] / sq) if sq > 0 else None,
            scored_questions=sq,
            runs_participated=len(runs_participated[mid]),
            is_reasoning=bool(preset.is_reasoning),
            reasoning_level=preset.reasoning_level.value if preset.reasoning_level else None,
        ))

    # Sort: win_rate descending (None last), then questions_won descending
    entries.sort(key=lambda e: (e.win_rate is None, -(e.win_rate or 0), -e.questions_won))

    return AggregateLeaderboardResponse(models=entries)


@router.get("/{model_id}/history", response_model=list[EloHistoryPoint])
async def get_elo_history(model_id: int, db: Session = Depends(get_db)):
    history = db.query(EloHistory).filter_by(model_preset_id=model_id).order_by(EloHistory.created_at).all()
    items = []
    for h in history:
        run = db.query(BenchmarkRun).filter_by(id=h.benchmark_run_id).first()
        items.append(EloHistoryPoint(
            benchmark_run_id=h.benchmark_run_id,
            run_name=run.name if run else "Deleted Run",
            rating_before=round(h.rating_before, 1),
            rating_after=round(h.rating_after, 1),
            games_in_run=h.games_in_run,
            created_at=h.created_at,
        ))
    return items
