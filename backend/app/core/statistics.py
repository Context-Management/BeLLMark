"""Statistical utilities for benchmark result analysis."""
import math
from collections import Counter
import numpy as np
from scipy import stats as scipy_stats


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """
    Wilson score confidence interval for a binomial proportion.

    Args:
        successes: Number of wins
        total: Total comparisons
        z: Z-score (1.96 = 95% CI, 1.645 = 90% CI)

    Returns:
        (lower, upper) bounds as floats in [0, 1]
    """
    if total == 0:
        return (0.0, 0.0)

    # Clamp successes to valid range for binomial proportion
    successes = max(0, min(successes, total))
    p = successes / total
    denominator = 1 + z * z / total
    centre = p + z * z / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)

    lower = max(0.0, (centre - spread) / denominator)
    upper = min(1.0, (centre + spread) / denominator)
    return (round(lower, 4), round(upper, 4))


def margin_of_error_display(successes: int, total: int) -> str:
    """Format margin of error as '±X.X%' string for UI display."""
    if total == 0:
        return "±0.0%"
    lower, upper = wilson_ci(successes, total)
    p = successes / total
    margin = max(upper - p, p - lower)
    return f"±{margin * 100:.1f}%"


def cohens_kappa(ratings_a: list[str], ratings_b: list[str]) -> float:
    """
    Cohen's Kappa for 2 raters.
    Returns: κ value: 1.0 = perfect, 0 = chance, < 0 = worse than chance
    """
    if not ratings_a or not ratings_b:
        return 0.0

    n = len(ratings_a)
    if n != len(ratings_b):
        raise ValueError("Rating lists must have same length")

    categories = sorted(set(ratings_a) | set(ratings_b))
    if len(categories) <= 1:
        return 1.0  # No variation — trivially "agree"

    observed = sum(1 for a, b in zip(ratings_a, ratings_b) if a == b) / n

    count_a = Counter(ratings_a)
    count_b = Counter(ratings_b)
    expected = sum((count_a[c] / n) * (count_b[c] / n) for c in categories)

    if expected == 1.0:
        return 1.0

    return round((observed - expected) / (1 - expected), 4)


def fleiss_kappa(matrix: list[list[int]]) -> float:
    """
    Fleiss' Kappa for 3+ raters.
    matrix: N×k where N = items, k = categories. matrix[i][j] = # raters who assigned item i to category j.
    Returns: κ value
    """
    if not matrix or not matrix[0]:
        return 0.0

    N = len(matrix)
    k = len(matrix[0])
    n = sum(matrix[0])

    if N == 0 or n <= 1:
        return 0.0

    total_assignments = N * n
    p_j = []
    for j in range(k):
        col_sum = sum(matrix[i][j] for i in range(N))
        p_j.append(col_sum / total_assignments)

    P_bar_e = sum(p ** 2 for p in p_j)

    P_i = []
    for i in range(N):
        sum_sq = sum(matrix[i][j] ** 2 for j in range(k))
        P_i.append((sum_sq - n) / (n * (n - 1)))

    P_bar = sum(P_i) / N

    if P_bar_e == 1.0:
        return 1.0

    return round((P_bar - P_bar_e) / (1 - P_bar_e), 4)


def pearson_correlation(x: list[float], y: list[float]) -> float | None:
    """
    Pearson correlation coefficient between two lists.
    Returns None if fewer than 3 points or zero variance.
    """
    n = len(x)
    if n < 3 or n != len(y):
        return None

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)

    if var_x == 0 or var_y == 0:
        return None

    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    return round(cov / math.sqrt(var_x * var_y), 4)


def spearman_correlation(x: list[float], y: list[float]) -> float | None:
    """
    Spearman rank correlation coefficient between two lists.

    Rank-based — robust to non-linear monotonic relationships and outliers,
    which makes it the right choice for score-vs-length bias analysis where
    the relationship is typically monotonic but not linear.

    Returns None if fewer than 3 points, length mismatch, or zero variance
    (after ranking).
    """
    n = len(x)
    if n < 3 or n != len(y):
        return None

    result = scipy_stats.spearmanr(x, y)
    rho = float(result.statistic)
    if math.isnan(rho):
        return None
    return round(rho, 4)


def bootstrap_ci(
    data: list[float],
    confidence: float = 0.95,
    n_bootstrap: int = 10000,
    seed: int = 42,
) -> tuple[float, float, float] | None:
    """Bootstrap confidence interval. Returns (lower, mean, upper) or None if empty."""
    if not data:
        return None
    if len(data) == 1:
        return (data[0], data[0], data[0])

    arr = np.array(data)
    rng = np.random.default_rng(seed)
    means = np.array([
        rng.choice(arr, size=len(arr), replace=True).mean()
        for _ in range(n_bootstrap)
    ])
    alpha = 1 - confidence
    lower = float(np.percentile(means, 100 * alpha / 2))
    upper = float(np.percentile(means, 100 * (1 - alpha / 2)))
    return (round(lower, 4), round(float(arr.mean()), 4), round(upper, 4))


def cohens_d(group_a: list[float], group_b: list[float]) -> float | None:
    """Cohen's d effect size. Positive = group_a higher. Returns None if insufficient data."""
    if not group_a or not group_b:
        return None
    a, b = np.array(group_a), np.array(group_b)
    n_a, n_b = len(a), len(b)
    # Need at least 2 per group for var(ddof=1) to be defined
    if n_a < 2 or n_b < 2:
        return None
    pooled_std = np.sqrt(((n_a - 1) * a.var(ddof=1) + (n_b - 1) * b.var(ddof=1)) / (n_a + n_b - 2))
    if pooled_std == 0 or np.isnan(pooled_std):
        return 0.0
    d = float((a.mean() - b.mean()) / pooled_std)
    if math.isnan(d) or math.isinf(d):
        return None
    return round(d, 4)


def wilcoxon_test(
    scores_a: list[float],
    scores_b: list[float],
    alpha: float = 0.05,
) -> dict | None:
    """Wilcoxon signed-rank test for paired samples. Returns None if < 6 pairs."""
    if len(scores_a) != len(scores_b) or len(scores_a) < 6:
        return None
    diffs = np.array(scores_a) - np.array(scores_b)
    if np.all(diffs == 0):
        return {"statistic": 0.0, "p_value": 1.0, "significant": False}
    stat, p = scipy_stats.wilcoxon(diffs)
    return {
        "statistic": round(float(stat), 4),
        "p_value": round(float(p), 6),
        "significant": bool(p < alpha),
    }


def holm_bonferroni(
    p_values: dict[str, float],
    alpha: float = 0.05,
) -> dict[str, dict]:
    """Holm-Bonferroni step-down correction for multiple comparisons."""
    if not p_values:
        return {}
    n = len(p_values)
    sorted_pairs = sorted(p_values.items(), key=lambda x: x[1])
    results = {}
    rejected_so_far = True
    max_adjusted_p = 0.0
    for rank, (label, p) in enumerate(sorted_pairs):
        adjusted_p = min(max(p * (n - rank), max_adjusted_p), 1.0)
        max_adjusted_p = adjusted_p
        if not rejected_so_far or adjusted_p >= alpha:
            rejected_so_far = False
        results[label] = {
            "original_p": round(p, 6),
            "adjusted_p": round(adjusted_p, 6),
            "significant": rejected_so_far and adjusted_p < alpha,
        }
    return results


def recommend_sample_size(
    effect_size: float = 0.5,
    power: float = 0.8,
    alpha: float = 0.05,
) -> int:
    """Recommend minimum question count for desired statistical power."""
    z_alpha = scipy_stats.norm.ppf(1 - alpha / 2)
    z_beta = scipy_stats.norm.ppf(power)
    n = ((z_alpha + z_beta) / effect_size) ** 2
    return int(np.ceil(n))
