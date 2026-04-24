"""Tests for judge calibration."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-calibration"

import pytest
from app.core.calibration import cohens_kappa, fleiss_kappa, icc, judge_reliability_score


class TestCohensKappa:
    def test_perfect_agreement(self):
        a = ["A", "B", "A", "A", "B"]
        b = ["A", "B", "A", "A", "B"]
        k = cohens_kappa(a, b)
        assert k == 1.0

    def test_no_agreement(self):
        a = ["A", "A", "A", "A"]
        b = ["B", "B", "B", "B"]
        k = cohens_kappa(a, b)
        assert k <= 0

    def test_moderate_agreement(self):
        a = ["A", "B", "A", "A", "B", "B", "A", "B"]
        b = ["A", "B", "B", "A", "B", "A", "A", "B"]
        k = cohens_kappa(a, b)
        assert 0.0 < k < 1.0

    def test_empty(self):
        assert cohens_kappa([], []) is None


class TestFleissKappa:
    def test_perfect_agreement(self):
        matrix = [[3, 0], [0, 3], [3, 0], [0, 3], [3, 0]]
        k = fleiss_kappa(matrix)
        assert k == 1.0

    def test_random_agreement(self):
        matrix = [[1, 2], [2, 1], [1, 2], [2, 1]]
        k = fleiss_kappa(matrix)
        assert -0.5 < k < 0.5


class TestICC:
    def test_perfect_consistency(self):
        ratings = [[7, 7, 7], [5, 5, 5], [8, 8, 8], [3, 3, 3], [9, 9, 9]]
        result = icc(ratings)
        assert result > 0.99

    def test_no_consistency(self):
        ratings = [[1, 9, 5], [9, 1, 5], [5, 5, 5], [1, 9, 1]]
        result = icc(ratings)
        assert result < 0.5


class TestJudgeReliability:
    def test_reliable_judge(self):
        scores = [7.0, 7.2, 6.8, 7.1, 7.0, 6.9, 7.3, 7.0]
        score = judge_reliability_score(scores)
        assert score > 0.8

    def test_unreliable_judge(self):
        scores = [1.0, 9.0, 3.0, 8.0, 2.0, 10.0, 1.0, 7.0]
        score = judge_reliability_score(scores)
        assert score < 0.5
