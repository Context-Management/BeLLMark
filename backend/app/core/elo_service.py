"""Service layer for updating ELO ratings after benchmark completion."""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.models import (
    BenchmarkRun, Question, Judgment, EloRating, EloHistory, TaskStatus,
)
from app.core.elo import update_elo, bayesian_k_factor, update_uncertainty


def update_elo_ratings_for_run(db: Session, run_id: int) -> None:
    """Process all judgments in a completed run and update ELO ratings.

    Idempotent: skips if this run has already been processed (EloHistory exists).
    Spin-offs (parent_run_id IS NOT NULL) are excluded from ELO so that
    re-judging the same generations with different judges/criteria does not
    inflate or distort the global rankings.
    """
    # Guard: skip if already processed
    existing = db.query(EloHistory).filter_by(benchmark_run_id=run_id).first()
    if existing:
        return

    run = db.query(BenchmarkRun).filter_by(id=run_id).first()
    if not run:
        return

    # Guard: spin-offs must not affect ELO (same generations, different judge)
    if run.parent_run_id is not None:
        return

    model_ids = run.model_ids
    ratings = {}
    for mid in model_ids:
        elo = db.query(EloRating).filter_by(model_preset_id=mid).first()
        if not elo:
            elo = EloRating(model_preset_id=mid, rating=1500.0, uncertainty=350.0, games_played=0)
            db.add(elo)
            db.flush()
        ratings[mid] = {
            "before": elo.rating,
            "current": elo.rating,
            "uncertainty": elo.uncertainty,
            "games": elo.games_played,
        }

    questions = db.query(Question).filter_by(benchmark_id=run_id).all()
    games_per_model = {mid: 0 for mid in model_ids}

    for q in questions:
        judgments = db.query(Judgment).filter(
            Judgment.question_id == q.id,
            Judgment.status == TaskStatus.success,
        ).all()

        for jud in judgments:
            if not jud.rankings or not jud.blind_mapping:
                continue

            ranked_ids = []
            for label in jud.rankings:
                mid = jud.blind_mapping.get(label)
                if mid and mid in ratings:
                    ranked_ids.append(mid)

            for i, winner_id in enumerate(ranked_ids):
                for loser_id in ranked_ids[i + 1:]:
                    k_w = bayesian_k_factor(ratings[winner_id]["games"], ratings[winner_id]["uncertainty"])
                    k_l = bayesian_k_factor(ratings[loser_id]["games"], ratings[loser_id]["uncertainty"])
                    k = (k_w + k_l) / 2

                    new_w, new_l = update_elo(
                        ratings[winner_id]["current"],
                        ratings[loser_id]["current"],
                        score_a=1.0, k=k,
                    )
                    ratings[winner_id]["current"] = new_w
                    ratings[loser_id]["current"] = new_l
                    games_per_model[winner_id] += 1
                    games_per_model[loser_id] += 1

    for mid in model_ids:
        elo = db.query(EloRating).filter_by(model_preset_id=mid).first()
        elo.rating = ratings[mid]["current"]
        elo.games_played += games_per_model[mid]
        elo.uncertainty = update_uncertainty(ratings[mid]["uncertainty"], games_per_model[mid])
        elo.updated_at = datetime.now(timezone.utc)

        history = EloHistory(
            model_preset_id=mid,
            benchmark_run_id=run_id,
            rating_before=ratings[mid]["before"],
            rating_after=ratings[mid]["current"],
            games_in_run=games_per_model[mid],
        )
        db.add(history)

    db.commit()
