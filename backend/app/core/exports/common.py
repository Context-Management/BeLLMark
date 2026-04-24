"""Shared data preparation and brand constants for all export formats."""
import colorsys
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session
from app.db.models import BenchmarkRun, Question, Generation, Judgment, ModelPreset, TaskStatus, EloHistory, EloRating
from app.core.pricing import get_model_prices, calculate_model_cost
from app.core.statistics import wilson_ci, margin_of_error_display, cohens_kappa, fleiss_kappa, spearman_correlation

ASSETS_DIR = Path(__file__).parent / "assets"
LOGO_PATH = ASSETS_DIR / "bellmark-logo.png"

# Brand colors (RGB tuples)
DARK_BG = (26, 26, 46)       # #1a1a2e
CARD_BG = (22, 33, 62)       # #16213e
ACCENT_BG = (15, 52, 96)     # #0f3460
GREEN = (74, 222, 128)       # #4ade80
AMBER = (245, 158, 11)       # #f59e0b
YELLOW = (251, 191, 36)      # #fbbf24
LIGHT_TEXT = (238, 238, 238)  # #eeeeee
MUTED_TEXT = (136, 136, 136)  # #888888
WHITE = (255, 255, 255)

BELLMARK_VERSION = "1.0"

MAX_QUESTION_DISPLAY_CHARS = 300


def truncate_text(text: str, max_chars: int = MAX_QUESTION_DISPLAY_CHARS) -> str:
    """Truncate text to max_chars, adding '...' if truncated."""
    if not text or len(text) <= max_chars:
        return text or ""
    return text[:max_chars] + "..."


def compute_export_integrity(data: dict, run_id: int) -> dict:
    """Compute SHA-256 integrity hash for export data.

    Serializes ``data`` to canonical JSON (sorted keys, no whitespace) and
    computes its SHA-256 digest.  The hash is computed BEFORE the
    ``_integrity`` block is added, so a recipient can verify it by
    re-serialising the export payload (minus ``_integrity``) and comparing.

    Returns a dict suitable for use as the ``_integrity`` metadata block:
        {
            "sha256": "<hex digest>",
            "generated_at": "<ISO 8601 UTC timestamp>",
            "bellmark_version": "1.0",
            "run_id": <int>,
        }
    """
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "sha256": digest,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bellmark_version": BELLMARK_VERSION,
        "run_id": run_id,
    }


def score_color_rgb(score: float) -> tuple[int, int, int]:
    """Map a 0-10 score to an RGB color matching frontend scoreColors.ts."""
    if score >= 8:
        # Lime to Green: hue 90 -> 120
        t = (score - 8) / 2
        hue = 90 + t * 30
    elif score >= 6:
        # Yellow to Lime: hue 60 -> 90
        t = (score - 6) / 2
        hue = 60 + t * 30
    elif score >= 5:
        # Orange to Yellow: hue 35 -> 60
        t = score - 5
        hue = 35 + t * 25
    elif score >= 4:
        # Red-Orange to Orange: hue 15 -> 35
        t = score - 4
        hue = 15 + t * 20
    elif score >= 3:
        # Red to Red-Orange: hue 0 -> 15
        t = score - 3
        hue = t * 15
    elif score >= 1:
        # Magenta to Red: hue 320 -> 360
        t = (score - 1) / 2
        hue = 320 + t * 40
    else:
        # Purple to Magenta: hue 280 -> 320
        t = score
        hue = 280 + t * 40

    r, g, b = colorsys.hsv_to_rgb(hue / 360, 0.7, 0.85)
    return (int(r * 255), int(g * 255), int(b * 255))


def format_duration(seconds: int | None) -> str:
    """Format duration in seconds as human-readable string like '5m 30s' or '1h 2m'."""
    if seconds is None:
        return "N/A"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def format_cost(usd: float) -> str:
    """Format cost in USD as string like '$0.12' or 'Free'."""
    if usd == 0:
        return "Free"
    elif usd < 0.01:
        return f"${usd:.4f}"
    elif usd < 1:
        return f"${usd:.2f}"
    else:
        return f"${usd:.2f}"


def extract_comment_text(summary) -> str:
    """Extract plain text from a comment summary (string or structured dict)."""
    if isinstance(summary, dict):
        parts = []
        if summary.get("verdict"):
            parts.append(summary["verdict"])
        for s in summary.get("strengths", []):
            parts.append(f"+ {s}")
        for w in summary.get("weaknesses", []):
            parts.append(f"- {w}")
        return " | ".join(parts) if parts else ""
    return str(summary) if summary else ""


def sanitize_latin1(text: str) -> str:
    """Replace Unicode characters that can't be encoded in latin-1 (for fpdf2 built-in fonts)."""
    replacements = {
        "\u201c": '"', "\u201d": '"',  # curly double quotes
        "\u2018": "'", "\u2019": "'",  # curly single quotes
        "\u2013": "-", "\u2014": "--", # en-dash, em-dash
        "\u2026": "...",               # ellipsis
        "\u2022": "*",                 # bullet
        "\u00a0": " ",                 # non-breaking space
        "\u2212": "-",                 # minus sign
        "\u2032": "'",                 # prime
        "\u2033": '"',                 # double prime
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    # Fallback: replace any remaining non-latin1 chars with ?
    return text.encode("latin-1", errors="replace").decode("latin-1")


def prepare_export_data(db: Session, run_id: int) -> dict | None:
    """
    Prepare comprehensive export data for any format.

    Returns a dict with all computed metrics, scores, and raw data
    needed by any export format.
    """
    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
    if not run:
        return None

    # Load presets
    all_ids = set(run.model_ids + run.judge_ids)
    presets = {p.id: p for p in db.query(ModelPreset).filter(ModelPreset.id.in_(all_ids)).all()}
    model_presets = {pid: presets[pid] for pid in run.model_ids if pid in presets}
    judge_presets = {pid: presets[pid] for pid in run.judge_ids if pid in presets}

    # Weight map from criteria
    criteria = run.criteria or []
    weight_map = {c["name"]: c.get("weight", 1.0) for c in criteria}
    total_weight = sum(weight_map.values()) or 1.0

    # Load questions with generations and judgments
    questions = db.query(Question).filter(
        Question.benchmark_id == run_id
    ).order_by(Question.order).all()

    # --- Aggregate scores ---
    # model_id -> criterion -> [scores]
    model_criterion_scores = {}
    # model_id -> question_order -> criterion -> [scores]
    model_question_scores = {}
    # Judge agreement tracking
    question_winners = []  # list of {question_order, winners: [model_names]}

    questions_data = []
    for q in questions:
        gens = db.query(Generation).filter(Generation.question_id == q.id).all()
        juds = db.query(Judgment).filter(Judgment.question_id == q.id).all()

        gen_data = []
        for gen in gens:
            model_name = model_presets[gen.model_preset_id].name if gen.model_preset_id in model_presets else "Unknown"
            gen_data.append({
                "model_id": gen.model_preset_id,
                "model_name": model_name,
                "content": gen.content,
                "tokens": gen.tokens,
                "input_tokens": gen.input_tokens,
                "output_tokens": gen.output_tokens,
                "cached_input_tokens": gen.cached_input_tokens,
                "reasoning_tokens": gen.reasoning_tokens,
                "raw_chars": gen.raw_chars,
                "answer_chars": gen.answer_chars,
                "latency_ms": gen.latency_ms,
                "status": gen.status.value if gen.status else "unknown",
                "error": gen.error,
                "retries": gen.retries,
                # Reproducibility: model version string captured from provider API response
                # (claims-ledger row 3). Null on local models or when the provider does not return it.
                "model_version": gen.model_version,
            })

        jud_data = []
        winners_this_q = []
        for jud in juds:
            judge_name = judge_presets[jud.judge_preset_id].name if jud.judge_preset_id in judge_presets else "Unknown"
            jud_data.append({
                "judge_id": jud.judge_preset_id,
                "judge_name": judge_name,
                "blind_mapping": jud.blind_mapping,
                "rankings": jud.rankings,
                "scores": jud.scores,
                "reasoning": jud.reasoning,
                "score_rationales": jud.score_rationales,
                "comments": jud.comments,
                "latency_ms": jud.latency_ms,
                "tokens": jud.tokens,
                "input_tokens": jud.input_tokens,
                "output_tokens": jud.output_tokens,
                "cached_input_tokens": jud.cached_input_tokens,
                "reasoning_tokens": jud.reasoning_tokens,
                "status": jud.status.value if jud.status else "unknown",
                "error": jud.error,
                # Reproducibility: effective temperature used for this judgment
                # (claims-ledger row 2). Null for older judgments before the field was captured.
                "judge_temperature": jud.judge_temperature,
            })

            if jud.status == TaskStatus.success and jud.scores:
                for mid_str, crit_scores in jud.scores.items():
                    mid = int(mid_str) if isinstance(mid_str, str) else mid_str
                    if mid not in model_criterion_scores:
                        model_criterion_scores[mid] = {}
                    if mid not in model_question_scores:
                        model_question_scores[mid] = {}
                    if q.order not in model_question_scores[mid]:
                        model_question_scores[mid][q.order] = {}
                    for crit, score in crit_scores.items():
                        model_criterion_scores[mid].setdefault(crit, []).append(score)
                        model_question_scores[mid][q.order].setdefault(crit, []).append(score)

            if jud.status == TaskStatus.success and jud.rankings and jud.blind_mapping:
                winner_label = jud.rankings[0]
                winner_id = jud.blind_mapping.get(winner_label)
                if winner_id and winner_id in model_presets:
                    winners_this_q.append(model_presets[winner_id].name)

        question_winners.append({"order": q.order, "winners": winners_this_q})

        questions_data.append({
            "id": q.id,
            "order": q.order,
            "system_prompt": q.system_prompt,
            "user_prompt": q.user_prompt,
            "context_tokens": q.context_tokens,
            "generations": gen_data,
            "judgments": jud_data,
        })

    # --- Compute per-model metrics ---
    models_data = []
    for mid, preset in model_presets.items():
        # Aggregate generation stats
        total_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_input_tokens = 0
        total_latency = 0
        gen_count = 0
        latencies = []
        for q in questions_data:
            for g in q["generations"]:
                if g["model_id"] == mid and g["status"] == "success":
                    total_tokens += g["tokens"] or 0
                    total_input_tokens += g.get("input_tokens") or 0
                    total_output_tokens += g.get("output_tokens") or 0
                    total_cached_input_tokens += g.get("cached_input_tokens") or 0
                    total_latency += g["latency_ms"] or 0
                    gen_count += 1
                    if g["latency_ms"]:
                        latencies.append(g["latency_ms"])

        tok_per_sec = (total_tokens / (total_latency / 1000)) if total_latency > 0 else None

        # Cost
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
            input_tokens=total_input_tokens if total_input_tokens > 0 else None,
            output_tokens=total_output_tokens if total_output_tokens > 0 else None,
            cached_input_tokens=total_cached_input_tokens if total_cached_input_tokens > 0 else None,
            cached_input_price=price_in if preset.price_input is not None and preset.price_output is not None else None,
        )
        cost = round(cost, 4)

        # Latency percentiles
        latencies.sort()
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p50 = latencies[len(latencies) // 2] if latencies else 0
        p95_idx = int(len(latencies) * 0.95)
        p95 = latencies[min(p95_idx, len(latencies) - 1)] if latencies else 0

        # Scores
        crit_scores = model_criterion_scores.get(mid, {})
        per_criterion = {}
        weighted_sum = 0
        unweighted_scores = []
        for crit_name in [c["name"] for c in criteria]:
            scores = crit_scores.get(crit_name, [])
            avg = sum(scores) / len(scores) if scores else 0
            per_criterion[crit_name] = round(avg, 2)
            unweighted_scores.append(avg)
            weighted_sum += avg * weight_map.get(crit_name, 1.0)

        weighted_score = round(weighted_sum / total_weight, 2)
        unweighted_score = round(sum(unweighted_scores) / len(unweighted_scores), 2) if unweighted_scores else 0

        # Per-question weighted scores
        per_question = []
        q_scores = model_question_scores.get(mid, {})
        for q_order in sorted(q_scores.keys()):
            q_crit = q_scores[q_order]
            q_weighted = 0
            for crit_name, scores in q_crit.items():
                avg = sum(scores) / len(scores) if scores else 0
                q_weighted += avg * weight_map.get(crit_name, 1.0)
            per_question.append({
                "order": q_order,
                "score": round(q_weighted / total_weight, 2)
            })

        # Win count: number of questions where this model was voted winner
        # (count each question at most once, even if multiple judges voted for this model)
        win_count = sum(
            1 for qw in question_winners
            if preset.name in qw["winners"]
        )

        # Confidence intervals for win rate
        total_questions = len(question_winners)
        win_lower, win_upper = wilson_ci(win_count, total_questions)
        win_rate = round(win_count / total_questions, 4) if total_questions > 0 else 0

        # Length bias analysis: correlate token count with scores
        token_score_pairs = []
        for q in questions_data:
            # Find this model's generation for this question
            model_gen = None
            for g in q["generations"]:
                if g["model_id"] == mid and g["status"] == "success":
                    model_gen = g
                    break

            if model_gen and model_gen["tokens"]:
                # Find the per-question score for this model
                q_score_item = next((qs for qs in per_question if qs["order"] == q["order"]), None)
                if q_score_item:
                    token_score_pairs.append((model_gen["tokens"], q_score_item["score"]))

        length_bias_r = None
        if len(token_score_pairs) >= 3:
            tokens_list = [p[0] for p in token_score_pairs]
            scores_list = [p[1] for p in token_score_pairs]
            length_bias_r = spearman_correlation(tokens_list, scores_list)

        models_data.append({
            "id": mid,
            "name": preset.name,
            "provider": preset.provider.value,
            "model_id": preset.model_id,
            "weighted_score": weighted_score,
            "unweighted_score": unweighted_score,
            "win_count": win_count,
            "win_rate": win_rate,
            "win_ci_lower": win_lower,
            "win_ci_upper": win_upper,
            "win_margin_of_error": margin_of_error_display(win_count, total_questions),
            "total_tokens": total_tokens,
            "tokens_per_second": round(tok_per_sec, 1) if tok_per_sec else None,
            "estimated_cost": cost,
            "avg_latency_ms": round(avg_latency),
            "p50_latency_ms": p50,
            "p95_latency_ms": p95,
            "per_criterion_scores": per_criterion,
            "per_question_scores": per_question,
            "length_bias_r": length_bias_r,
            "length_bias_warning": length_bias_r is not None and abs(length_bias_r) > 0.5,
        })

    # Sort by weighted score descending
    models_data.sort(key=lambda m: m["weighted_score"], reverse=True)
    for i, m in enumerate(models_data):
        m["rank"] = i + 1

    # --- Insight badges ---
    if len(models_data) > 1:
        costs = [(m["name"], m["estimated_cost"]) for m in models_data]
        speeds = [(m["name"], m["tokens_per_second"]) for m in models_data if m["tokens_per_second"]]
        tokens = [(m["name"], m["total_tokens"]) for m in models_data]

        for m in models_data:
            badges = []
            if m["estimated_cost"] == 0:
                badges.append("Free")
            elif costs and m["name"] == min(costs, key=lambda x: x[1])[0] and m["estimated_cost"] > 0:
                badges.append("Cheapest")
            if costs and m["name"] == max(costs, key=lambda x: x[1])[0] and m["estimated_cost"] > 0:
                badges.append("Most Expensive")
            if speeds and m["name"] == max(speeds, key=lambda x: x[1])[0]:
                badges.append("Fastest")
            if speeds and m["name"] == min(speeds, key=lambda x: x[1])[0]:
                badges.append("Slowest")
            if tokens and m["name"] == max(tokens, key=lambda x: x[1])[0]:
                badges.append("Most Verbose")
            if tokens and m["name"] == min(tokens, key=lambda x: x[1])[0]:
                badges.append("Most Concise")
            m["insights"] = badges

    # --- Judge metrics ---
    judges_data = []
    for jid, preset in judge_presets.items():
        total_tokens = 0
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_input_tokens = 0
        total_latency = 0
        jud_count = 0
        for q in questions_data:
            for j in q["judgments"]:
                if j["judge_id"] == jid and j["status"] == "success":
                    total_tokens += j["tokens"] or 0
                    total_input_tokens += j.get("input_tokens") or 0
                    total_output_tokens += j.get("output_tokens") or 0
                    total_cached_input_tokens += j.get("cached_input_tokens") or 0
                    total_latency += j["latency_ms"] or 0
                    jud_count += 1

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
            input_tokens=total_input_tokens if total_input_tokens > 0 else None,
            output_tokens=total_output_tokens if total_output_tokens > 0 else None,
            cached_input_tokens=total_cached_input_tokens if total_cached_input_tokens > 0 else None,
            cached_input_price=price_in if preset.price_input is not None and preset.price_output is not None else None,
        )
        cost = round(cost, 4)

        judges_data.append({
            "id": jid,
            "name": preset.name,
            "provider": preset.provider.value,
            "total_tokens": total_tokens,
            "total_latency_ms": total_latency,
            "estimated_cost": cost,
            "judgment_count": jud_count,
        })

    # --- Judge agreement ---
    total_q = 0
    agreed_q = 0
    disagreement_orders = []
    per_judge_winners = {}
    for qw in question_winners:
        if not qw["winners"]:
            continue
        total_q += 1
        if len(set(qw["winners"])) == 1:
            agreed_q += 1
        else:
            disagreement_orders.append(qw["order"])

    # Per-judge winner counts (from raw judgment data)
    for q in questions_data:
        for j in q["judgments"]:
            if j["status"] == "success" and j["rankings"] and j["blind_mapping"]:
                judge_name = j["judge_name"]
                winner_label = j["rankings"][0]
                winner_id = j["blind_mapping"].get(winner_label)
                if winner_id and winner_id in model_presets:
                    winner_name = model_presets[winner_id].name
                    per_judge_winners.setdefault(judge_name, {})
                    per_judge_winners[judge_name][winner_name] = per_judge_winners[judge_name].get(winner_name, 0) + 1

    # Build per-question winner per judge, keyed by question order for alignment
    judge_ratings_by_q = {}  # {judge_id: {q_order: winner_model_name}}
    for q in questions:
        for jud in q.judgments:
            if jud.status == TaskStatus.success and jud.rankings and jud.blind_mapping:
                winner_label = jud.rankings[0]
                winner_id = jud.blind_mapping.get(winner_label)
                winner_name = model_presets[winner_id].name if winner_id in model_presets else "unknown"
                judge_ratings_by_q.setdefault(jud.judge_preset_id, {})[q.order] = winner_name

    # Calculate kappa — align by shared questions only
    judge_ids_list = sorted(judge_ratings_by_q.keys())
    kappa_value = None
    kappa_type = None

    if len(judge_ids_list) >= 2:
        # Find questions rated by ALL judges
        shared_orders = set.intersection(*(set(judge_ratings_by_q[jid].keys()) for jid in judge_ids_list))
        shared_orders_sorted = sorted(shared_orders)

    if len(judge_ids_list) == 2 and shared_orders_sorted:
        r_a = [judge_ratings_by_q[judge_ids_list[0]][o] for o in shared_orders_sorted]
        r_b = [judge_ratings_by_q[judge_ids_list[1]][o] for o in shared_orders_sorted]
        kappa_value = cohens_kappa(r_a, r_b)
        kappa_type = "cohen"
    elif len(judge_ids_list) >= 3 and shared_orders_sorted:
        # Build Fleiss matrix: rows = questions, columns = models (categories)
        all_models = sorted(set(m for q_map in judge_ratings_by_q.values() for m in q_map.values()))
        model_to_idx = {m: i for i, m in enumerate(all_models)}

        fleiss_matrix = []
        for q_order in shared_orders_sorted:
            row = [0] * len(all_models)
            for jid in judge_ids_list:
                winner = judge_ratings_by_q[jid][q_order]
                row[model_to_idx[winner]] += 1
            fleiss_matrix.append(row)

        if fleiss_matrix:
            kappa_value = fleiss_kappa(fleiss_matrix)
            kappa_type = "fleiss"

    judge_summary = {
        "agreement_rate": round(agreed_q / total_q, 3) if total_q > 0 else 0,
        "disagreement_count": len(disagreement_orders),
        "disagreement_questions": disagreement_orders,
        "per_judge_winners": per_judge_winners,
    }

    # --- Duration ---
    duration_seconds = None
    if run.created_at and run.completed_at:
        duration_seconds = int((run.completed_at - run.created_at).total_seconds())

    # --- Total cost ---
    total_cost = sum(m["estimated_cost"] for m in models_data) + sum(j["estimated_cost"] for j in judges_data)

    # --- Comment summaries ---
    comment_summaries = run.comment_summaries or {}

    # --- Scores by criterion matrix (for heatmap) ---
    scores_by_criterion = {}
    for m in models_data:
        scores_by_criterion[m["name"]] = m["per_criterion_scores"]

    # --- Statistical analysis (optional - may fail for small runs) ---
    try:
        from app.core.run_statistics import compute_run_statistics
        stats = compute_run_statistics(db, run_id)
    except Exception:
        stats = None

    # Annotate models_data with LC win rate from stats (stats was computed from the same run)
    if stats and stats.get("model_statistics"):
        lc_by_name = {ms["model_name"]: ms.get("lc_win_rate") for ms in stats["model_statistics"]}
        for m in models_data:
            m["lc_win_rate"] = lc_by_name.get(m["name"])

    try:
        from app.core.bias import compute_bias_report
        bias = compute_bias_report(db, run_id)
    except Exception:
        bias = None

    try:
        from app.core.calibration import compute_calibration_report
        calibration = compute_calibration_report(db, run_id)
    except Exception:
        calibration = None

    # --- ELO rating snapshots (claims-ledger row 4) ---
    # EloHistory stores before/after ratings for every model that participated in this run;
    # EloRating stores each model's current global rating. Exporting both lets a reviewer see
    # the per-run delta and the leaderboard standing at export time.
    elo_for_run: list[dict] = []
    try:
        history_rows = (
            db.query(EloHistory)
            .filter(EloHistory.benchmark_run_id == run_id)
            .all()
        )
        current_ratings = {
            r.model_preset_id: r
            for r in db.query(EloRating)
            .filter(EloRating.model_preset_id.in_(list(model_presets.keys())))
            .all()
        }
        for h in history_rows:
            preset = model_presets.get(h.model_preset_id)
            if preset is None:
                continue
            current = current_ratings.get(h.model_preset_id)
            elo_for_run.append({
                "model_id": h.model_preset_id,
                "model_name": preset.name,
                "rating_before": round(h.rating_before, 1),
                "rating_after": round(h.rating_after, 1),
                "delta": round(h.rating_after - h.rating_before, 1),
                "games_in_run": h.games_in_run,
                "current_rating": round(current.rating, 1) if current else None,
                "current_uncertainty": round(current.uncertainty, 1) if current else None,
                "current_games_played": current.games_played if current else None,
            })
        # Sort by current rating (desc) for stable output; fall back to rating_after.
        elo_for_run.sort(
            key=lambda r: (r["current_rating"] or r["rating_after"]),
            reverse=True,
        )
    except Exception:
        # ELO is a post-completion enrichment; never fail the export because of it.
        elo_for_run = []

    # --- Model preset snapshots (reproducibility: temperature config, reasoning, quantization) ---
    # Reviewers need the exact configuration each model ran with, not just names.
    def _preset_snapshot(preset: ModelPreset) -> dict:
        # Note: `temperature_mode` lives on the run (applies to all presets in the run),
        # not on the preset. `custom_temperature` on the preset is the override used
        # when the run's temperature_mode == "custom".
        return {
            "id": preset.id,
            "name": preset.name,
            "provider": preset.provider.value,
            "model_id": preset.model_id,
            "custom_temperature": preset.custom_temperature,
            "is_reasoning": bool(preset.is_reasoning),
            "reasoning_level": preset.reasoning_level.value if preset.reasoning_level else None,
            "quantization": preset.quantization,
            "model_format": preset.model_format,
            "parameter_count": preset.parameter_count,
        }

    model_preset_snapshots = [_preset_snapshot(p) for p in model_presets.values()]
    judge_preset_snapshots = [_preset_snapshot(p) for p in judge_presets.values()]

    return {
        "run": {
            "id": run.id,
            "name": run.name,
            "status": run.status.value,
            "judge_mode": run.judge_mode.value,
            "criteria": criteria,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "duration_seconds": duration_seconds,
            "total_cost": round(total_cost, 4),
            "total_context_tokens": run.total_context_tokens,
            "run_config_snapshot": run.run_config_snapshot,
            "random_seed": run.random_seed,
            # Reproducibility surface expanded for claims-ledger rows 1-3:
            # base temperature, mode, and run topology so a reviewer can
            # reconstruct exactly what was executed.
            "temperature": run.temperature,
            "temperature_mode": run.temperature_mode.value if run.temperature_mode else None,
            "sequential_mode": bool(run.sequential_mode),
            "parent_run_id": run.parent_run_id,
            "source_suite_id": run.source_suite_id,
            "model_preset_snapshots": model_preset_snapshots,
            "judge_preset_snapshots": judge_preset_snapshots,
        },
        # Top-level methodology block — lets reviewers verify claim by claim
        # without reading code. Aligns with `docs/claims-ledger.md`.
        "methodology": {
            "bellmark_version": BELLMARK_VERSION,
            "blind_label_shuffling": "seeded" if run.random_seed is not None else "unseeded",
            "presentation_order_randomization": "independent_of_blind_labels",
            "length_bias_correlation": "spearman",
            "win_rate_confidence_interval": "wilson_score",
            "inter_rater_reliability": "cohens_kappa_2j_or_fleiss_kappa_3j_plus",
            "multiple_comparison_correction": "holm_bonferroni",
            "self_preference_detection": "mann_whitney_u",
            "effect_size": "cohens_d",
            "non_parametric_pairwise": "wilcoxon_signed_rank",
        },
        "models": models_data,
        "judges": judges_data,
        "judge_summary": judge_summary,
        "comment_summaries": comment_summaries,
        "scores_by_criterion": scores_by_criterion,
        "questions": questions_data,
        "kappa_value": kappa_value,
        "kappa_type": kappa_type,
        "statistics": stats,
        "bias_report": bias,
        "calibration_report": calibration,
        "elo_for_run": elo_for_run,
    }
