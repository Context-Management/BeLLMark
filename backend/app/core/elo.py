"""ELO rating system for persistent model rankings across benchmark runs."""
import math


def expected_score(rating_a: float, rating_b: float) -> float:
    """Expected score for player A given both ratings."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def bayesian_k_factor(
    games_played: int,
    uncertainty: float,
    k_min: float = 10.0,
    k_max: float = 64.0,
) -> float:
    """Adaptive K-factor that decreases with more games."""
    game_factor = math.exp(-games_played / 30)
    uncertainty_factor = min(uncertainty / 350.0, 1.0)
    blend = 0.6 * game_factor + 0.4 * uncertainty_factor
    return k_min + blend * (k_max - k_min)


def update_elo(
    rating_a: float,
    rating_b: float,
    score_a: float,
    k: float = 32.0,
) -> tuple[float, float]:
    """Update ELO ratings. score_a: 1.0=win, 0.5=draw, 0.0=loss."""
    ea = expected_score(rating_a, rating_b)
    eb = 1.0 - ea
    score_b = 1.0 - score_a
    new_a = rating_a + k * (score_a - ea)
    new_b = rating_b + k * (score_b - eb)
    return (round(new_a, 2), round(new_b, 2))


def update_uncertainty(current: float, games_played: int) -> float:
    """Shrink uncertainty as model plays more games."""
    min_uncertainty = 50.0
    decay_rate = 0.02
    return max(min_uncertainty, current * math.exp(-decay_rate * games_played))
