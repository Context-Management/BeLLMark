# backend/app/core/bias.py
"""Bias detection for LLM judge evaluations."""
import math
import numpy as np
from scipy import stats
from typing import Optional


def _safe_float(val: float) -> float | None:
    """Convert to float, returning None for NaN/Inf (not JSON-serializable)."""
    f = float(val)
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def classify_severity(abs_correlation: float) -> str:
    """Map absolute correlation to severity level."""
    if abs_correlation < 0.1:
        return "none"
    elif abs_correlation < 0.3:
        return "low"
    elif abs_correlation < 0.5:
        return "moderate"
    return "high"


def detect_position_bias(positions_and_wins: list[tuple[int, bool]]) -> dict:
    """Detect if earlier positions are favored by judges."""
    if len(positions_and_wins) < 6:
        return {"name": "Position Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient data for position bias analysis."}

    positions = np.array([p for p, _ in positions_and_wins], dtype=float)
    wins = np.array([1.0 if w else 0.0 for _, w in positions_and_wins])

    # Guard: constant inputs produce NaN correlations
    if np.std(positions) == 0 or np.std(wins) == 0:
        return {"name": "Position Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient variance for position bias analysis."}

    r, p = stats.pointbiserialr(positions, wins)
    r_safe, p_safe = _safe_float(r), _safe_float(p)
    if r_safe is None:
        return {"name": "Position Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient variance for position bias analysis."}
    severity = classify_severity(abs(r_safe))

    return {
        "name": "Position Bias",
        "severity": severity,
        "correlation": round(r_safe, 4),
        "p_value": round(p_safe, 6) if p_safe is not None else None,
        "description": _position_description(r_safe, severity),
    }


def detect_length_bias(lengths_and_scores: list[tuple[int, float]]) -> dict:
    """Detect if response length correlates with scores."""
    if len(lengths_and_scores) < 6:
        return {"name": "Length Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient data for length bias analysis."}

    lengths = np.array([l for l, _ in lengths_and_scores], dtype=float)
    scores = np.array([s for _, s in lengths_and_scores], dtype=float)

    if np.std(lengths) == 0 or np.std(scores) == 0:
        return {"name": "Length Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient variance for length bias analysis."}

    r, p = stats.spearmanr(lengths, scores)
    r_safe, p_safe = _safe_float(r), _safe_float(p)
    if r_safe is None:
        return {"name": "Length Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient variance for length bias analysis."}
    severity = classify_severity(abs(r_safe))

    return {
        "name": "Length Bias",
        "severity": severity,
        "correlation": round(r_safe, 4),
        "p_value": round(p_safe, 6) if p_safe is not None else None,
        "description": _length_description(r_safe, severity),
    }


def detect_self_preference(scores: list[dict]) -> dict:
    """Detect if judges score same-provider models higher."""
    if len(scores) < 6:
        return {"name": "Self-Preference", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient data for self-preference analysis."}

    same_provider = [s["score"] for s in scores if s["judge_provider"] == s["model_provider"]]
    diff_provider = [s["score"] for s in scores if s["judge_provider"] != s["model_provider"]]

    if not same_provider or not diff_provider:
        return {"name": "Self-Preference", "severity": "none", "correlation": None,
                "p_value": None, "description": "No cross-provider comparisons available."}

    if len(same_provider) >= 3 and len(diff_provider) >= 3:
        stat, p = stats.mannwhitneyu(same_provider, diff_provider, alternative="greater")
        mean_diff = np.mean(same_provider) - np.mean(diff_provider)
        n1, n2 = len(same_provider), len(diff_provider)
        r = 1 - (2 * stat) / (n1 * n2)
        severity = classify_severity(abs(r))
    else:
        mean_diff = np.mean(same_provider) - np.mean(diff_provider)
        r, p = 0.0, 1.0
        severity = "none"

    return {
        "name": "Self-Preference",
        "severity": severity,
        "correlation": round(float(r), 4),
        "p_value": round(float(p), 6),
        "description": _self_pref_description(mean_diff, severity),
        "details": {
            "same_provider_mean": round(float(np.mean(same_provider)), 2),
            "diff_provider_mean": round(float(np.mean(diff_provider)), 2),
            "mean_difference": round(float(mean_diff), 2),
        },
    }


def detect_verbosity_bias(reasoning_lengths_and_scores: list[tuple[int, float]]) -> dict:
    """Detect if longer judge reasoning correlates with higher scores."""
    if len(reasoning_lengths_and_scores) < 6:
        return {"name": "Verbosity Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient data for verbosity bias analysis."}

    lengths = np.array([l for l, _ in reasoning_lengths_and_scores], dtype=float)
    scores = np.array([s for _, s in reasoning_lengths_and_scores], dtype=float)

    if np.std(lengths) == 0 or np.std(scores) == 0:
        return {"name": "Verbosity Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient variance for verbosity bias analysis."}

    r, p = stats.spearmanr(lengths, scores)
    r_safe, p_safe = _safe_float(r), _safe_float(p)
    if r_safe is None:
        return {"name": "Verbosity Bias", "severity": "none", "correlation": None,
                "p_value": None, "description": "Insufficient variance for verbosity bias analysis."}
    severity = classify_severity(abs(r_safe))

    return {
        "name": "Verbosity Bias",
        "severity": severity,
        "correlation": round(r_safe, 4),
        "p_value": round(p_safe, 6) if p_safe is not None else None,
        "description": _verbosity_description(r_safe, severity),
    }


def _position_description(r: float, severity: str) -> str:
    if severity == "none":
        return "No significant position bias detected. Judges evaluate responses fairly regardless of presentation order."
    direction = "earlier" if r < 0 else "later"
    return f"Judges tend to favor responses presented {direction} in the list (r={r:.2f}). Severity: {severity}."


def _length_description(r: float, severity: str) -> str:
    if severity == "none":
        return "No significant length bias detected. Response length does not correlate with scores."
    direction = "longer" if r > 0 else "shorter"
    return f"Judges tend to score {direction} responses higher (r={r:.2f}). Severity: {severity}."


def _self_pref_description(mean_diff: float, severity: str) -> str:
    if severity == "none":
        return "No self-preference detected. Judges score same-provider and different-provider models similarly."
    return f"Judges score same-provider models {mean_diff:+.1f} points higher on average. Severity: {severity}."


def _verbosity_description(r: float, severity: str) -> str:
    if severity == "none":
        return "No verbosity bias detected. Judge reasoning length does not correlate with scores."
    return f"Longer judge reasoning correlates with {'higher' if r > 0 else 'lower'} scores (r={r:.2f}). Severity: {severity}."


def compute_bias_report(db_session, run_id: int) -> dict | None:
    """Compute full bias report for a benchmark run using DB data."""
    from app.db.models import BenchmarkRun, Question, Generation, Judgment, ModelPreset, TaskStatus

    run = db_session.query(BenchmarkRun).filter_by(id=run_id).first()
    if not run:
        return None

    presets = {p.id: p for p in db_session.query(ModelPreset).filter(
        ModelPreset.id.in_(set(run.model_ids + run.judge_ids))
    ).all()}

    questions = db_session.query(Question).filter_by(benchmark_id=run_id).all()

    position_data = []
    length_data = []
    self_pref_data = []
    verbosity_data = []

    for q in questions:
        judgments = db_session.query(Judgment).filter(
            Judgment.question_id == q.id, Judgment.status == TaskStatus.success
        ).all()
        generations = db_session.query(Generation).filter(
            Generation.question_id == q.id, Generation.status == TaskStatus.success
        ).all()
        gen_map = {g.model_preset_id: g for g in generations}

        for jud in judgments:
            judge_preset = presets.get(jud.judge_preset_id)
            if not judge_preset:
                continue

            if jud.rankings and jud.blind_mapping:
                if jud.presentation_mapping:
                    # Use actual presentation order: presentation_mapping is {"1": "A", "2": "C", ...}
                    blind_to_position = {blind: int(pres) - 1 for pres, blind in jud.presentation_mapping.items()}
                else:
                    # Fallback for pre-migration judgments: assume alphabetical order (A=0, B=1, C=2)
                    blind_to_position = {label: i for i, label in enumerate(sorted(jud.blind_mapping.keys()))}
                for label, position in blind_to_position.items():
                    won = jud.rankings[0] == label
                    position_data.append((position, won))

            if jud.scores:
                for mid_str, crit_scores in jud.scores.items():
                    mid = int(mid_str)
                    model_preset = presets.get(mid)
                    if not model_preset:
                        continue
                    avg_score = sum(crit_scores.values()) / len(crit_scores) if crit_scores else 0

                    gen = gen_map.get(mid)
                    if gen and gen.tokens:
                        length_data.append((gen.tokens, avg_score))

                    self_pref_data.append({
                        "judge_provider": judge_preset.provider.value,
                        "model_provider": model_preset.provider.value,
                        "score": avg_score,
                    })

                if jud.reasoning:
                    avg_all = np.mean([
                        sum(cs.values()) / len(cs) for cs in jud.scores.values() if cs
                    ])
                    verbosity_data.append((len(jud.reasoning), float(avg_all)))

    pos_result = detect_position_bias(position_data)
    len_result = detect_length_bias(length_data)
    self_result = detect_self_preference(self_pref_data)
    verb_result = detect_verbosity_bias(verbosity_data)

    severities = [pos_result["severity"], len_result["severity"], self_result["severity"], verb_result["severity"]]
    severity_order = {"none": 0, "low": 1, "moderate": 2, "high": 3}
    max_severity = max(severities, key=lambda s: severity_order.get(s, 0))

    bias_count = sum(1 for s in severities if s not in ("none", "low"))
    if bias_count == 0:
        summary = "No significant biases detected. Results appear trustworthy."
    elif bias_count == 1:
        summary = f"One potential bias detected ({max_severity} severity). Review the flagged indicator."
    else:
        summary = f"{bias_count} potential biases detected (worst: {max_severity}). Consider these when interpreting results."

    return {
        "position_bias": pos_result,
        "length_bias": len_result,
        "self_preference": self_result,
        "verbosity_bias": verb_result,
        "overall_severity": max_severity,
        "summary": summary,
    }
