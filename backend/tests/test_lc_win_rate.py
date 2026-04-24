"""Tests for length-controlled win rate computation (C17).

Based on dubois2024 (LC AlpacaEval) and kamoi2024 research on verbosity bias.
Verbose models gain unfair advantage in blind comparisons because judges tend
to prefer longer responses. LC win rates debias this.
"""
from app.core.run_statistics import compute_lc_win_rates


def test_lc_win_rate_reduces_verbose_advantage():
    """LC win rate reduces advantage of verbose responses."""
    # Pairs where model A won (1) or lost (0), with token counts for A's response
    wins = [1, 1, 1, 1, 0, 1, 1, 1, 0, 1]  # A wins 8/10 raw
    lengths_winner = [2000, 2100, 1900, 2050, 500, 2200, 1800, 2000, 500, 1950]
    lengths_loser = [500, 450, 550, 480, 2000, 520, 600, 510, 1800, 470]

    result = compute_lc_win_rates(wins, lengths_winner, lengths_loser)
    raw_wr = sum(wins) / len(wins)  # 0.8
    assert result is not None
    assert result["lc_win_rate"] < raw_wr  # LC should reduce verbose model's advantage
    assert result["raw_win_rate"] == raw_wr
    assert "length_bias_detected" in result


def test_lc_returns_none_insufficient_data():
    """LC win rate returns None with fewer than 6 data points."""
    result = compute_lc_win_rates([1, 0, 1], [100, 200, 150], [90, 180, 140])
    assert result is None


def test_lc_no_bias_when_equal_lengths():
    """No length bias when responses are similar length."""
    wins = [1, 0, 1, 0, 1, 0, 1, 0]  # 50/50
    lengths_w = [500, 510, 490, 505, 495, 500, 510, 490]
    lengths_l = [500, 490, 510, 495, 505, 500, 490, 510]
    result = compute_lc_win_rates(wins, lengths_w, lengths_l)
    assert result is not None
    # With equal lengths, LC should be very close to raw
    assert abs(result["lc_win_rate"] - result["raw_win_rate"]) < 0.15


def test_lc_result_structure():
    """Result dict contains all expected keys."""
    wins = [1, 0, 1, 1, 0, 1, 1, 0]
    lengths_w = [1000, 500, 1200, 800, 400, 1100, 900, 600]
    lengths_l = [500, 1000, 600, 400, 1200, 550, 450, 1100]
    result = compute_lc_win_rates(wins, lengths_w, lengths_l)
    assert result is not None
    assert "raw_win_rate" in result
    assert "lc_win_rate" in result
    assert "n_flagged" in result
    assert "n_total" in result
    assert "length_bias_detected" in result
    assert "bias_magnitude" in result
    assert result["n_total"] == len(wins)


def test_lc_flags_correct_count():
    """n_flagged counts only wins where winner was >1.5x longer."""
    # 6 pairs: wins at index 0, 1, 2 — only index 0 and 1 have ratio > 1.5
    wins = [1, 1, 1, 0, 0, 0]
    lengths_winner = [2000, 1600, 1100, 500, 300, 200]
    lengths_loser  = [500,  500,  800,  500, 300, 200]
    # Index 0: 2000/500 = 4.0 > 1.5 → flagged
    # Index 1: 1600/500 = 3.2 > 1.5 → flagged
    # Index 2: 1100/800 = 1.375 < 1.5 → not flagged
    result = compute_lc_win_rates(wins, lengths_winner, lengths_loser)
    assert result is not None
    assert result["n_flagged"] == 2


def test_lc_bias_magnitude_matches():
    """bias_magnitude equals raw_win_rate - lc_win_rate."""
    wins = [1, 1, 1, 1, 0, 1, 1, 1, 0, 1]
    lengths_winner = [2000, 2100, 1900, 2050, 500, 2200, 1800, 2000, 500, 1950]
    lengths_loser = [500, 450, 550, 480, 2000, 520, 600, 510, 1800, 470]
    result = compute_lc_win_rates(wins, lengths_winner, lengths_loser)
    assert result is not None
    expected_magnitude = round(result["raw_win_rate"] - result["lc_win_rate"], 4)
    assert abs(result["bias_magnitude"] - expected_magnitude) < 1e-9


def test_lc_exactly_six_pairs():
    """LC win rate works with exactly 6 pairs (minimum threshold)."""
    wins = [1, 0, 1, 0, 1, 0]
    lengths_w = [500, 200, 600, 300, 400, 100]
    lengths_l = [200, 500, 300, 600, 100, 400]
    result = compute_lc_win_rates(wins, lengths_w, lengths_l)
    assert result is not None
    assert result["n_total"] == 6


def test_lc_five_pairs_returns_none():
    """Exactly 5 pairs (below minimum) returns None."""
    result = compute_lc_win_rates([1, 0, 1, 0, 1], [500]*5, [300]*5)
    assert result is None
