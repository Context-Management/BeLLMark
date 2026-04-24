from app.core.run_statistics import compute_friedman_test


def test_friedman_with_significant_differences():
    """Friedman test detects known differences in model scores."""
    scores_a = [8, 7, 9, 8, 7, 8, 9, 7]
    scores_b = [3, 4, 3, 2, 4, 3, 2, 4]
    scores_c = [5, 6, 5, 5, 6, 5, 6, 5]
    result = compute_friedman_test([scores_a, scores_b, scores_c])
    assert result["p_value"] < 0.05
    assert result["significant"] is True


def test_friedman_skipped_for_two_models():
    """Friedman test is skipped when only 2 models are compared."""
    result = compute_friedman_test([[8, 7, 9], [3, 4, 3]])
    assert result is None


def test_friedman_insufficient_samples():
    """Friedman test returns error with fewer than 3 samples."""
    result = compute_friedman_test([[8, 7], [3, 4], [5, 6]])
    assert "error" in result
