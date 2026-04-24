"""Tests for statistical calculations."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-stats"

import pytest
from app.core.statistics import (
    wilson_ci,
    margin_of_error_display,
    cohens_kappa,
    fleiss_kappa,
    pearson_correlation,
    spearman_correlation,
    bootstrap_ci,
    cohens_d,
    wilcoxon_test,
    holm_bonferroni,
    recommend_sample_size,
)


class TestWilsonCI:
    def test_perfect_wins(self):
        """5/5 wins should have CI upper bound = 1.0 and lower > 0.5."""
        lower, upper = wilson_ci(successes=5, total=5)
        assert upper == 1.0 or upper > 0.9
        assert lower > 0.5

    def test_no_wins(self):
        """0/5 wins should have CI lower bound = 0.0 and upper < 0.5."""
        lower, upper = wilson_ci(successes=0, total=5)
        assert lower == 0.0 or lower < 0.1
        assert upper < 0.5

    def test_even_split(self):
        """50/100 should be close to (0.4, 0.6) at 95% CI."""
        lower, upper = wilson_ci(successes=50, total=100)
        assert 0.35 < lower < 0.45
        assert 0.55 < upper < 0.65

    def test_zero_total_returns_zero(self):
        """Edge case: no questions at all."""
        lower, upper = wilson_ci(successes=0, total=0)
        assert lower == 0.0
        assert upper == 0.0

    def test_ci_width_decreases_with_sample_size(self):
        """More questions → narrower CI."""
        _, u10 = wilson_ci(5, 10)
        l10, _ = wilson_ci(5, 10)
        _, u100 = wilson_ci(50, 100)
        l100, _ = wilson_ci(50, 100)
        width_10 = u10 - l10
        width_100 = u100 - l100
        assert width_100 < width_10


class TestMarginOfErrorDisplay:
    def test_format(self):
        """Should return a string like '±12.3%'."""
        result = margin_of_error_display(successes=3, total=5)
        assert result.startswith("±")
        assert result.endswith("%")

    def test_zero_total(self):
        result = margin_of_error_display(successes=0, total=0)
        assert result == "±0.0%"


class TestCohensKappa:
    def test_perfect_agreement(self):
        ratings_a = ["A", "B", "A", "B", "A"]
        ratings_b = ["A", "B", "A", "B", "A"]
        assert cohens_kappa(ratings_a, ratings_b) == 1.0

    def test_systematic_disagreement(self):
        ratings_a = ["A", "B", "A", "B"]
        ratings_b = ["B", "A", "B", "A"]
        k = cohens_kappa(ratings_a, ratings_b)
        assert k < 0

    def test_disjoint_categories_kappa_zero(self):
        ratings_a = ["A", "A", "A"]
        ratings_b = ["B", "B", "B"]
        k = cohens_kappa(ratings_a, ratings_b)
        assert k == 0.0

    def test_moderate_agreement(self):
        ratings_a = ["A", "B", "A", "B", "C"]
        ratings_b = ["A", "B", "B", "B", "C"]
        k = cohens_kappa(ratings_a, ratings_b)
        assert 0 < k < 1

    def test_empty_ratings(self):
        assert cohens_kappa([], []) == 0.0

    def test_single_category(self):
        k = cohens_kappa(["A", "A", "A"], ["A", "A", "A"])
        assert k == 1.0


class TestFleissKappa:
    def test_perfect_agreement(self):
        matrix = [[3, 0], [0, 3], [3, 0]]
        assert fleiss_kappa(matrix) == pytest.approx(1.0, abs=0.01)

    def test_random_agreement(self):
        matrix = [[2, 1], [1, 2], [2, 1], [1, 2]]
        k = fleiss_kappa(matrix)
        assert -0.5 < k < 0.5

    def test_empty_matrix(self):
        assert fleiss_kappa([]) == 0.0


class TestPearsonCorrelation:
    def test_perfect_positive(self):
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        assert pearson_correlation(x, y) == pytest.approx(1.0, abs=0.01)

    def test_perfect_negative(self):
        x = [1, 2, 3, 4, 5]
        y = [10, 8, 6, 4, 2]
        assert pearson_correlation(x, y) == pytest.approx(-1.0, abs=0.01)

    def test_no_correlation(self):
        x = [1, 2, 3, 4, 5]
        y = [5, 1, 4, 2, 3]
        r = pearson_correlation(x, y)
        assert -0.5 < r < 0.5

    def test_too_few_points(self):
        assert pearson_correlation([1], [2]) is None
        assert pearson_correlation([1, 2], [3, 4]) is None

    def test_zero_variance(self):
        assert pearson_correlation([5, 5, 5], [1, 2, 3]) is None


class TestSpearmanCorrelation:
    def test_perfect_monotonic_positive(self):
        """Perfect monotonic (non-linear) relationship → ρ = 1.0, whereas Pearson would be < 1."""
        x = [1, 2, 3, 4, 5]
        y = [1, 4, 9, 16, 25]  # y = x^2 — monotonic but not linear
        assert spearman_correlation(x, y) == pytest.approx(1.0, abs=0.01)

    def test_perfect_monotonic_negative(self):
        x = [1, 2, 3, 4, 5]
        y = [25, 16, 9, 4, 1]
        assert spearman_correlation(x, y) == pytest.approx(-1.0, abs=0.01)

    def test_diverges_from_pearson_on_nonlinear_data(self):
        """On an asymmetric/nonlinear fixture, Spearman and Pearson give meaningfully different values.

        This is the B4 completion check: the length-bias export path needs rank-based
        correlation because score-vs-length is monotonic but not linear.
        """
        # Sharp nonlinear jump at the end — Pearson dominated by outlier, Spearman unaffected
        x = [1, 2, 3, 4, 5, 6]
        y = [1, 2, 3, 4, 5, 100]
        pearson = pearson_correlation(x, y)
        spearman = spearman_correlation(x, y)
        assert spearman == pytest.approx(1.0, abs=0.01)
        # Pearson is still high but measurably below 1.0 because of the outlier
        assert pearson is not None
        assert pearson < spearman
        assert abs(spearman - pearson) > 0.05

    def test_too_few_points(self):
        assert spearman_correlation([1], [2]) is None
        assert spearman_correlation([1, 2], [3, 4]) is None

    def test_length_mismatch(self):
        assert spearman_correlation([1, 2, 3], [1, 2]) is None


class TestBootstrapCI:
    def test_basic_ci(self):
        data = [7.0, 8.0, 6.5, 7.5, 8.5, 7.0, 6.0, 9.0, 7.5, 8.0]
        lower, mean, upper = bootstrap_ci(data, confidence=0.95, n_bootstrap=10000)
        assert 6.5 < lower < 7.5
        assert 7.0 < mean < 8.0
        assert 7.5 < upper < 8.5
        assert lower < mean < upper

    def test_single_value(self):
        lower, mean, upper = bootstrap_ci([5.0])
        assert lower == mean == upper == 5.0

    def test_empty_returns_none(self):
        result = bootstrap_ci([])
        assert result is None

    def test_identical_values(self):
        lower, mean, upper = bootstrap_ci([7.0, 7.0, 7.0, 7.0])
        assert lower == mean == upper == 7.0


class TestCohensD:
    def test_large_effect(self):
        a = [8.0, 9.0, 8.5, 9.5, 8.0]
        b = [4.0, 5.0, 4.5, 5.5, 4.0]
        d = cohens_d(a, b)
        assert d > 0.8

    def test_no_effect(self):
        a = [5.0, 5.0, 5.0]
        b = [5.0, 5.0, 5.0]
        d = cohens_d(a, b)
        assert d == 0.0

    def test_empty_returns_none(self):
        assert cohens_d([], [1.0]) is None
        assert cohens_d([1.0], []) is None

    def test_sign_direction(self):
        a = [8.0, 9.0, 8.5]
        b = [4.0, 5.0, 4.5]
        d = cohens_d(a, b)
        assert d > 0

    def test_single_element_returns_none(self):
        """n=1 per group: var(ddof=1) is undefined, should return None not NaN."""
        assert cohens_d([5.0], [3.0, 4.0]) is None
        assert cohens_d([5.0, 6.0], [3.0]) is None
        assert cohens_d([5.0], [3.0]) is None


class TestWilcoxon:
    def test_significant_difference(self):
        a = [8.0, 9.0, 8.5, 9.5, 8.0, 9.0, 8.5, 7.5]
        b = [4.0, 5.0, 4.5, 5.5, 4.0, 5.0, 4.5, 3.5]
        result = wilcoxon_test(a, b)
        assert result["significant"] is True
        assert result["p_value"] < 0.05

    def test_no_difference(self):
        a = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
        b = [5.0, 5.0, 5.0, 5.0, 5.0, 5.0]
        result = wilcoxon_test(a, b)
        assert result["significant"] is False

    def test_too_few_samples(self):
        result = wilcoxon_test([5.0], [6.0])
        assert result is None


class TestHolmBonferroni:
    def test_correction(self):
        p_values = {"A_vs_B": 0.01, "A_vs_C": 0.04, "B_vs_C": 0.03}
        result = holm_bonferroni(p_values, alpha=0.05)
        assert result["A_vs_B"]["significant"] is True
        assert "adjusted_p" in result["A_vs_B"]

    def test_single_comparison(self):
        result = holm_bonferroni({"A_vs_B": 0.03})
        assert result["A_vs_B"]["significant"] is True
        assert result["A_vs_B"]["adjusted_p"] == 0.03

    def test_step_down_rejection(self):
        p_values = {"A_vs_B": 0.01, "A_vs_C": 0.04, "B_vs_C": 0.80}
        result = holm_bonferroni(p_values, alpha=0.05)
        assert result["A_vs_B"]["significant"] is True
        assert result["B_vs_C"]["significant"] is False
        assert result["A_vs_C"]["significant"] is False

    def test_empty(self):
        result = holm_bonferroni({})
        assert result == {}


class TestPowerAnalysis:
    def test_small_effect(self):
        n = recommend_sample_size(effect_size=0.2, power=0.8, alpha=0.05)
        assert n >= 150

    def test_large_effect(self):
        n = recommend_sample_size(effect_size=0.8, power=0.8, alpha=0.05)
        assert n <= 30

    def test_higher_power_needs_more(self):
        n80 = recommend_sample_size(effect_size=0.5, power=0.8)
        n95 = recommend_sample_size(effect_size=0.5, power=0.95)
        assert n95 > n80
