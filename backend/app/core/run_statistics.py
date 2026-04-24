# backend/app/core/run_statistics.py
"""Compute statistical analysis for a completed benchmark run."""
from itertools import combinations
from scipy.stats import friedmanchisquare
from sqlalchemy.orm import Session
from app.db.models import BenchmarkRun, Question, Generation, Judgment, ModelPreset, TaskStatus
from app.core.statistics import bootstrap_ci, cohens_d, wilcoxon_test, holm_bonferroni, recommend_sample_size


def compute_friedman_test(score_arrays: list[list[float]]) -> dict | None:
    """Omnibus test for k>=3 models. Returns None for k<3.

    Based on Demsar 2006 (JMLR): when comparing k>=3 models, run Friedman
    test first as omnibus. Only if significant should pairwise tests be
    considered confirmatory rather than exploratory.
    """
    if len(score_arrays) < 3:
        return None
    min_len = min(len(a) for a in score_arrays)
    if min_len < 3:
        return {"error": "Insufficient samples for Friedman test (need >= 3 questions)"}
    trimmed = [a[:min_len] for a in score_arrays]
    stat, p_value = friedmanchisquare(*trimmed)
    return {
        "chi_square": float(stat),
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05),
        "n_models": len(score_arrays),
        "n_questions": min_len,
    }


def _effect_label(d: float | None) -> str:
    if d is None:
        return "unknown"
    d = abs(d)
    if d < 0.2:
        return "negligible"
    elif d < 0.5:
        return "small"
    elif d < 0.8:
        return "medium"
    return "large"


def compute_lc_win_rates(
    wins: list[int],
    lengths_winner: list[int],
    lengths_loser: list[int],
    threshold: float = 1.5,
) -> dict | None:
    """Length-controlled win rate via length-ratio flagging.

    Approach: Flag pairs where the winning response is >threshold times longer
    than the losing response. Flagged wins are counted as 0.5 (ties) instead of 1.
    This reduces the advantage of verbose responses.

    Based on dubois2024 (LC AlpacaEval) simplified to ratio-flagging approach.

    Args:
        wins: List of 1/0 for each comparison pair (1=model won)
        lengths_winner: Token count of the winning response in each pair
        lengths_loser: Token count of the losing response in each pair
        threshold: Length ratio above which a win is flagged (default 1.5x)

    Returns:
        Dict with raw_win_rate, lc_win_rate, n_flagged, length_bias_detected, or None if <6 pairs
    """
    if len(wins) < 6:
        return None

    raw_wr = sum(wins) / len(wins)

    adjusted_wins = []
    n_flagged = 0
    for w, lw, ll in zip(wins, lengths_winner, lengths_loser):
        if w == 1 and ll > 0 and lw / ll > threshold:
            # Winner was significantly longer — discount this win
            adjusted_wins.append(0.5)
            n_flagged += 1
        elif w == 0 and lw > 0 and ll / lw > threshold:
            # Loser was significantly longer — this loss is "genuine"
            adjusted_wins.append(0)
        else:
            adjusted_wins.append(w)

    lc_wr = sum(adjusted_wins) / len(adjusted_wins)

    # Length bias detected if flagged pairs shift the win rate by >5pp
    length_bias_detected = abs(raw_wr - lc_wr) > 0.05

    return {
        "raw_win_rate": raw_wr,
        "lc_win_rate": round(lc_wr, 4),
        "n_flagged": n_flagged,
        "n_total": len(wins),
        "length_bias_detected": length_bias_detected,
        "bias_magnitude": round(raw_wr - lc_wr, 4),
    }


def compute_run_statistics(db: Session, run_id: int) -> dict | None:
    """Compute full statistical analysis for a benchmark run."""
    run = db.query(BenchmarkRun).filter_by(id=run_id).first()
    if not run:
        return None

    criteria = run.criteria or []
    weight_map = {c["name"]: c.get("weight", 1.0) for c in criteria}
    total_weight = sum(weight_map.values()) or 1.0

    presets = {p.id: p for p in db.query(ModelPreset).filter(ModelPreset.id.in_(run.model_ids)).all()}
    questions = db.query(Question).filter_by(benchmark_id=run_id).order_by(Question.order).all()

    # Collect per-question weighted scores per model, keyed by question index for pairing
    # model_scores_by_q[mid][q_idx] = weighted_score (only present if model has data for that question)
    model_scores_by_q: dict[int, dict[int, float]] = {mid: {} for mid in run.model_ids}
    model_criterion_scores: dict[int, dict[str, list[float]]] = {mid: {} for mid in run.model_ids}
    model_wins: dict[int, int] = {mid: 0 for mid in run.model_ids}
    total_games = 0
    # Token counts per model per question for LC win rate computation
    # model_tokens_by_q[mid][q_idx] = token_count (approximated from chars if tokens unavailable)
    model_tokens_by_q: dict[int, dict[int, int]] = {mid: {} for mid in run.model_ids}

    for q_idx, q in enumerate(questions):
        # Collect token counts from generations for LC win rate
        generations = db.query(Generation).filter(
            Generation.question_id == q.id,
            Generation.status == TaskStatus.success,
            Generation.model_preset_id.in_(run.model_ids),
        ).all()
        for gen in generations:
            tokens = gen.tokens
            if tokens is None and gen.answer_chars:
                # Approximate: ~4 chars per token
                tokens = gen.answer_chars // 4
            elif tokens is None and gen.raw_chars:
                tokens = gen.raw_chars // 4
            if tokens is not None and tokens > 0:
                model_tokens_by_q[gen.model_preset_id][q_idx] = tokens

        judgments = db.query(Judgment).filter(
            Judgment.question_id == q.id,
            Judgment.status == TaskStatus.success,
        ).all()

        q_model_crit_scores: dict[int, dict[str, list[float]]] = {}
        for jud in judgments:
            if not jud.scores:
                continue
            for mid_str, crit_scores in jud.scores.items():
                mid = int(mid_str)
                if mid not in q_model_crit_scores:
                    q_model_crit_scores[mid] = {}
                for crit, score in crit_scores.items():
                    q_model_crit_scores[mid].setdefault(crit, []).append(score)

            if jud.rankings and jud.blind_mapping:
                winner_label = jud.rankings[0]
                winner_id = jud.blind_mapping.get(winner_label)
                if winner_id and winner_id in model_wins:
                    model_wins[winner_id] += 1
                    total_games += 1

        for mid in run.model_ids:
            crit_data = q_model_crit_scores.get(mid, {})
            if not crit_data:
                continue
            weighted_sum = 0.0
            has_any_score = False
            for crit_name in [c["name"] for c in criteria]:
                scores = crit_data.get(crit_name, [])
                if not scores:
                    continue
                has_any_score = True
                avg = sum(scores) / len(scores)
                weighted_sum += avg * weight_map.get(crit_name, 1.0)
                model_criterion_scores[mid].setdefault(crit_name, []).append(avg)
            if has_any_score:
                model_scores_by_q[mid][q_idx] = weighted_sum / total_weight

    # Flat score lists per model (for bootstrap CI)
    model_question_scores: dict[int, list[float]] = {
        mid: list(q_scores.values()) for mid, q_scores in model_scores_by_q.items()
    }

    n_questions = len(questions)

    # Build per-model LC win rate by aggregating across all pairwise opponents
    # model_lc_data[mid] = {"wins": [...], "lengths_winner": [...], "lengths_loser": [...]}
    model_lc_inputs: dict[int, dict[str, list]] = {
        mid: {"wins": [], "lengths_winner": [], "lengths_loser": []}
        for mid in run.model_ids
    }
    for (mid_a, mid_b) in combinations(run.model_ids, 2):
        shared_qs = set(model_scores_by_q[mid_a].keys()) & set(model_scores_by_q[mid_b].keys())
        for qi in sorted(shared_qs):
            score_a = model_scores_by_q[mid_a][qi]
            score_b = model_scores_by_q[mid_b][qi]
            tok_a = model_tokens_by_q[mid_a].get(qi, 0)
            tok_b = model_tokens_by_q[mid_b].get(qi, 0)
            if score_a > score_b:
                # A won this question
                model_lc_inputs[mid_a]["wins"].append(1)
                model_lc_inputs[mid_a]["lengths_winner"].append(tok_a)
                model_lc_inputs[mid_a]["lengths_loser"].append(tok_b)
                model_lc_inputs[mid_b]["wins"].append(0)
                model_lc_inputs[mid_b]["lengths_winner"].append(tok_b)
                model_lc_inputs[mid_b]["lengths_loser"].append(tok_a)
            elif score_b > score_a:
                # B won this question
                model_lc_inputs[mid_b]["wins"].append(1)
                model_lc_inputs[mid_b]["lengths_winner"].append(tok_b)
                model_lc_inputs[mid_b]["lengths_loser"].append(tok_a)
                model_lc_inputs[mid_a]["wins"].append(0)
                model_lc_inputs[mid_a]["lengths_winner"].append(tok_a)
                model_lc_inputs[mid_a]["lengths_loser"].append(tok_b)

    model_lc_by_id: dict[int, dict | None] = {}
    for mid in run.model_ids:
        d = model_lc_inputs[mid]
        model_lc_by_id[mid] = compute_lc_win_rates(
            d["wins"], d["lengths_winner"], d["lengths_loser"]
        )

    model_stats = []
    for mid in run.model_ids:
        name = presets[mid].name if mid in presets else "Unknown"
        scores = model_question_scores[mid]
        ci = bootstrap_ci(scores)
        ci_dict = {"lower": ci[0], "mean": ci[1], "upper": ci[2]} if ci else None

        crit_cis = {}
        for crit_name in [c["name"] for c in criteria]:
            crit_scores = model_criterion_scores[mid].get(crit_name, [])
            cci = bootstrap_ci(crit_scores)
            if cci:
                crit_cis[crit_name] = {"lower": cci[0], "mean": cci[1], "upper": cci[2]}

        wins = model_wins.get(mid, 0)
        win_rate = wins / total_games if total_games > 0 else 0.0
        win_ci = bootstrap_ci([1.0] * wins + [0.0] * (total_games - wins)) if total_games > 0 else None
        win_ci_dict = {"lower": win_ci[0], "mean": win_ci[1], "upper": win_ci[2]} if win_ci else None

        lc = model_lc_by_id.get(mid)

        model_stats.append({
            "model_name": name,
            "weighted_score_ci": ci_dict,
            "per_criterion_ci": crit_cis,
            "win_rate": round(win_rate, 4),
            "win_rate_ci": win_ci_dict,
            "lc_win_rate": lc,
        })

    pairwise = []
    raw_p_values = {}
    pair_data = {}
    for (mid_a, mid_b) in combinations(run.model_ids, 2):
        name_a = presets[mid_a].name if mid_a in presets else "Unknown"
        name_b = presets[mid_b].name if mid_b in presets else "Unknown"

        # Build paired scores: only questions where BOTH models have data
        shared_qs = set(model_scores_by_q[mid_a].keys()) & set(model_scores_by_q[mid_b].keys())
        paired_a = [model_scores_by_q[mid_a][qi] for qi in sorted(shared_qs)]
        paired_b = [model_scores_by_q[mid_b][qi] for qi in sorted(shared_qs)]

        d = cohens_d(paired_a, paired_b)
        wt = wilcoxon_test(paired_a, paired_b)
        label = f"{name_a}_vs_{name_b}"
        p = wt["p_value"] if wt else None
        if p is not None:
            raw_p_values[label] = p

        mean_a = sum(paired_a) / len(paired_a) if paired_a else 0
        mean_b = sum(paired_b) / len(paired_b) if paired_b else 0

        # Compute LC win rates for this pair using shared questions
        # For each shared question, determine which model "won" (higher score) and both lengths
        lc_wins: list[int] = []
        lc_lengths_winner: list[int] = []
        lc_lengths_loser: list[int] = []
        for qi in sorted(shared_qs):
            score_a = model_scores_by_q[mid_a][qi]
            score_b = model_scores_by_q[mid_b][qi]
            tok_a = model_tokens_by_q[mid_a].get(qi, 0)
            tok_b = model_tokens_by_q[mid_b].get(qi, 0)
            if score_a > score_b:
                lc_wins.append(1)
                lc_lengths_winner.append(tok_a)
                lc_lengths_loser.append(tok_b)
            elif score_b > score_a:
                lc_wins.append(0)
                lc_lengths_winner.append(tok_b)
                lc_lengths_loser.append(tok_a)
            # Ties (equal scores) are skipped — they don't contribute to win rate
        lc_data = compute_lc_win_rates(lc_wins, lc_lengths_winner, lc_lengths_loser)

        pair_data[label] = {
            "model_a": name_a,
            "model_b": name_b,
            "score_diff": round(mean_a - mean_b, 4),
            "cohens_d": d,
            "p_value": p,
            "effect_label": _effect_label(d),
            "lc_win_rate": lc_data,
        }

    # Friedman omnibus test (k>=3 models) — Demsar 2006
    model_score_arrays = []
    for mid in run.model_ids:
        scores = []
        for q_idx in sorted(model_scores_by_q[mid].keys()):
            scores.append(model_scores_by_q[mid][q_idx])
        if scores:
            model_score_arrays.append(scores)

    friedman = compute_friedman_test(model_score_arrays)

    # Pairwise comparisons are exploratory when Friedman is not significant
    pairwise_exploratory = friedman is not None and not friedman.get("significant", True)

    corrected = holm_bonferroni(raw_p_values)
    for label, data in pair_data.items():
        adj = corrected.get(label)
        data["adjusted_p"] = adj["adjusted_p"] if adj else data["p_value"]
        p_significant = adj["significant"] if adj else (data["p_value"] is not None and data["p_value"] < 0.05)
        d_meaningful = data["cohens_d"] is not None and abs(data["cohens_d"]) >= 0.2
        data["significant"] = p_significant and d_meaningful
        data["exploratory"] = pairwise_exploratory
        pairwise.append(data)

    # rec_small requires the MOST questions (detecting small effects needs large samples)
    # so rec_small > rec_medium > rec_large — check from hardest threshold down
    rec_small = recommend_sample_size(effect_size=0.2)
    rec_medium = recommend_sample_size(effect_size=0.5)
    rec_large = recommend_sample_size(effect_size=0.8)

    if n_questions >= rec_small:
        adequate_for = "small"       # can detect even small effects (best)
    elif n_questions >= rec_medium:
        adequate_for = "medium"      # can detect medium+ effects
    elif n_questions >= rec_large:
        adequate_for = "large"       # can detect only large effects
    else:
        adequate_for = "insufficient"

    power_analysis = {
        "current_questions": n_questions,
        "recommended_small_effect": rec_small,
        "recommended_medium_effect": rec_medium,
        "recommended_large_effect": rec_large,
        "adequate_for": adequate_for,
    }

    warning = None
    if n_questions < 5:
        warning = f"Only {n_questions} questions. Results are not statistically reliable. Consider 10+ questions for meaningful analysis."
    elif n_questions < rec_large:
        warning = f"With {n_questions} questions, only large effect sizes (d>0.8) can be reliably detected. Consider {rec_medium}+ questions."

    return {
        "model_statistics": model_stats,
        "pairwise_comparisons": pairwise,
        "friedman": friedman,
        "power_analysis": power_analysis,
        "sample_size_warning": warning,
    }
