# backend/app/core/calibration.py
"""Judge calibration and inter-rater reliability metrics."""
import numpy as np
from typing import Optional


def cohens_kappa(rater_a: list, rater_b: list) -> Optional[float]:
    """Cohen's Kappa for two raters. Returns None if insufficient data."""
    if not rater_a or not rater_b or len(rater_a) != len(rater_b):
        return None

    categories = sorted(set(rater_a) | set(rater_b))
    n = len(rater_a)
    if n == 0:
        return None

    matrix = {}
    for cat in categories:
        matrix[cat] = {c: 0 for c in categories}
    for a, b in zip(rater_a, rater_b):
        matrix[a][b] += 1

    po = sum(matrix[c][c] for c in categories) / n

    pe = 0.0
    for c in categories:
        row_sum = sum(matrix[c].values()) / n
        col_sum = sum(matrix[r][c] for r in categories) / n
        pe += row_sum * col_sum

    if pe == 1.0:
        return 1.0 if po == 1.0 else 0.0
    return round(float((po - pe) / (1 - pe)), 4)


def fleiss_kappa(rating_matrix: list[list[int]]) -> Optional[float]:
    """Fleiss' Kappa for multiple raters. Returns None if insufficient data."""
    if not rating_matrix or not rating_matrix[0]:
        return None

    mat = np.array(rating_matrix, dtype=float)
    n_items, n_cats = mat.shape
    n_raters = int(mat[0].sum())

    if n_raters < 2 or n_items < 2:
        return None

    p_j = mat.sum(axis=0) / (n_items * n_raters)
    P_i = (mat ** 2).sum(axis=1) - n_raters
    P_i = P_i / (n_raters * (n_raters - 1))

    P_bar = P_i.mean()
    P_e = (p_j ** 2).sum()

    if P_e == 1.0:
        return 1.0 if P_bar == 1.0 else 0.0
    return round(float((P_bar - P_e) / (1 - P_e)), 4)


def icc(ratings: list[list[float]], icc_type: str = "ICC(3,1)") -> Optional[float]:
    """Intraclass Correlation Coefficient (two-way mixed, single measures).
    ratings: N subjects x K raters matrix."""
    if not ratings or len(ratings) < 2:
        return None

    mat = np.array(ratings, dtype=float)
    n, k = mat.shape
    if k < 2 or n < 2:
        return None

    grand_mean = mat.mean()
    row_means = mat.mean(axis=1)
    col_means = mat.mean(axis=0)

    ss_total = ((mat - grand_mean) ** 2).sum()
    ss_rows = k * ((row_means - grand_mean) ** 2).sum()
    ss_cols = n * ((col_means - grand_mean) ** 2).sum()
    ss_error = ss_total - ss_rows - ss_cols

    ms_rows = ss_rows / (n - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))

    if ms_rows + (k - 1) * ms_error == 0:
        return None
    icc_val = (ms_rows - ms_error) / (ms_rows + (k - 1) * ms_error)
    return round(float(max(0.0, min(1.0, icc_val))), 4)


def judge_reliability_score(scores: list[float]) -> float:
    """Compute a 0-1 reliability score based on coefficient of variation."""
    if not scores or len(scores) < 2:
        return 1.0
    arr = np.array(scores)
    mean = arr.mean()
    if mean == 0:
        return 0.0
    cv = arr.std(ddof=1) / abs(mean)
    return round(float(max(0.0, 1.0 - cv)), 4)


def compute_calibration_report(db_session, run_id: int) -> dict | None:
    """Compute judge calibration report for a benchmark run."""
    from app.db.models import BenchmarkRun, Question, Judgment, ModelPreset, TaskStatus

    run = db_session.query(BenchmarkRun).filter_by(id=run_id).first()
    if not run:
        return None

    presets = {p.id: p for p in db_session.query(ModelPreset).filter(
        ModelPreset.id.in_(set(run.model_ids + run.judge_ids))
    ).all()}

    questions = db_session.query(Question).filter_by(benchmark_id=run_id).order_by(Question.order).all()

    judge_winners_by_q: dict[int, dict[int, str]] = {}
    judge_all_scores: dict[int, list[float]] = {}
    icc_matrix: list[list[float]] = []

    judge_ids = run.judge_ids
    judge_idx_map = {jid: i for i, jid in enumerate(judge_ids)}

    for q in questions:
        judgments = db_session.query(Judgment).filter(
            Judgment.question_id == q.id, Judgment.status == TaskStatus.success
        ).all()

        row = [None] * len(judge_ids)
        for jud in judgments:
            jid = jud.judge_preset_id
            if jid not in judge_idx_map:
                continue

            if jud.rankings and jud.blind_mapping:
                winner_label = jud.rankings[0]
                winner_id = jud.blind_mapping.get(winner_label)
                winner_name = presets[winner_id].name if winner_id and winner_id in presets else "Unknown"
                judge_winners_by_q.setdefault(jid, {})[q.order] = winner_name

            if jud.scores:
                all_crit_scores = []
                for mid_str, crit_scores in jud.scores.items():
                    all_crit_scores.extend(crit_scores.values())
                avg = sum(all_crit_scores) / len(all_crit_scores) if all_crit_scores else 0
                judge_all_scores.setdefault(jid, []).append(avg)
                row[judge_idx_map[jid]] = avg

        if all(v is not None for v in row):
            icc_matrix.append(row)

    kappa_pairs = {}
    judge_id_list = list(judge_winners_by_q.keys())
    for i in range(len(judge_id_list)):
        for j in range(i + 1, len(judge_id_list)):
            jid_a, jid_b = judge_id_list[i], judge_id_list[j]
            name_a = presets[jid_a].name if jid_a in presets else "Unknown"
            name_b = presets[jid_b].name if jid_b in presets else "Unknown"
            common_orders = sorted(
                set(judge_winners_by_q[jid_a].keys()) & set(judge_winners_by_q[jid_b].keys())
            )
            winners_a = [judge_winners_by_q[jid_a][o] for o in common_orders]
            winners_b = [judge_winners_by_q[jid_b][o] for o in common_orders]
            k = cohens_kappa(winners_a, winners_b)
            kappa_pairs[f"{name_a} vs {name_b}"] = {
                "kappa": k,
                "interpretation": _kappa_interpretation(k) if k is not None else "N/A",
            }

    icc_value = icc(icc_matrix) if len(icc_matrix) >= 2 else None

    judge_reliability = {}
    for jid in judge_ids:
        name = presets[jid].name if jid in presets else "Unknown"
        scores = judge_all_scores.get(jid, [])
        reliability = judge_reliability_score(scores)
        judge_reliability[name] = {
            "reliability": reliability,
            "judgment_count": len(scores),
            "interpretation": "Reliable" if reliability >= 0.7 else "Inconsistent" if reliability >= 0.4 else "Unreliable",
        }

    recommendations = []
    for name, data in judge_reliability.items():
        if data["reliability"] < 0.4:
            recommendations.append(f"Consider removing {name} — reliability score {data['reliability']:.2f} suggests inconsistent evaluation.")
    if icc_value is not None and icc_value < 0.5:
        recommendations.append(f"Low inter-rater consistency (ICC={icc_value:.2f}). Judges may be using different evaluation standards.")

    return {
        "pairwise_kappa": kappa_pairs,
        "icc": icc_value,
        "icc_interpretation": _icc_interpretation(icc_value) if icc_value is not None else "N/A",
        "judge_reliability": judge_reliability,
        "recommendations": recommendations,
    }


def _kappa_interpretation(k: float) -> str:
    if k < 0:
        return "Less than chance"
    elif k < 0.21:
        return "Slight"
    elif k < 0.41:
        return "Fair"
    elif k < 0.61:
        return "Moderate"
    elif k < 0.81:
        return "Substantial"
    return "Almost perfect"


def _icc_interpretation(icc_val: float) -> str:
    if icc_val < 0.5:
        return "Poor"
    elif icc_val < 0.75:
        return "Moderate"
    elif icc_val < 0.9:
        return "Good"
    return "Excellent"
