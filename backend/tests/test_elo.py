"""Tests for ELO rating engine."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-elo"

import pytest
from app.core.elo import expected_score, update_elo, bayesian_k_factor

class TestEloEngine:
    def test_expected_score_equal_rating(self):
        e = expected_score(1500, 1500)
        assert abs(e - 0.5) < 0.001

    def test_expected_score_higher_rated_favored(self):
        e = expected_score(1700, 1500)
        assert e > 0.7

    def test_update_elo_winner_gains(self):
        new_a, new_b = update_elo(1500, 1500, score_a=1.0, k=32)
        assert new_a > 1500
        assert new_b < 1500
        assert abs((new_a - 1500) + (new_b - 1500)) < 0.01  # Zero-sum

    def test_upset_gives_more_points(self):
        new_a_upset, _ = update_elo(1300, 1700, score_a=1.0, k=32)
        gain_upset = new_a_upset - 1300
        new_a_expected, _ = update_elo(1700, 1300, score_a=1.0, k=32)
        gain_expected = new_a_expected - 1700
        assert gain_upset > gain_expected

    def test_bayesian_k_factor_high_uncertainty(self):
        k = bayesian_k_factor(games_played=0, uncertainty=350.0)
        assert k > 40

    def test_bayesian_k_factor_low_uncertainty(self):
        k = bayesian_k_factor(games_played=100, uncertainty=50.0)
        assert k < 20

    def test_draw(self):
        new_a, new_b = update_elo(1500, 1500, score_a=0.5, k=32)
        assert abs(new_a - 1500) < 0.01
        assert abs(new_b - 1500) < 0.01
