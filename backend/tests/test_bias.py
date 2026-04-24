"""Tests for bias detection."""
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ["BELLMARK_SECRET_KEY"] = "test-secret-key-bias"

import pytest
from app.core.bias import (
    detect_position_bias,
    detect_length_bias,
    detect_self_preference,
    classify_severity,
)


class TestPositionBias:
    def test_no_bias_random_positions(self):
        positions_and_wins = [
            (0, True), (1, False),
            (1, True), (0, False),
            (0, True), (1, False),
            (1, True), (0, False),
        ]
        result = detect_position_bias(positions_and_wins)
        assert result["severity"] in ("none", "low")

    def test_strong_position_bias(self):
        positions_and_wins = [(0, True), (1, False)] * 20
        result = detect_position_bias(positions_and_wins)
        assert result["severity"] in ("moderate", "high")


class TestLengthBias:
    def test_no_correlation(self):
        lengths_and_scores = [(100, 7), (200, 5), (150, 8), (300, 4), (50, 9)]
        result = detect_length_bias(lengths_and_scores)
        assert result["severity"] in ("none", "low")

    def test_strong_length_bias(self):
        lengths_and_scores = [(i * 100, i) for i in range(1, 11)]
        result = detect_length_bias(lengths_and_scores)
        assert result["severity"] in ("moderate", "high")
        assert result["correlation"] > 0.8


class TestSelfPreference:
    def test_no_self_preference(self):
        scores = [
            {"judge_provider": "openai", "model_provider": "openai", "score": 7.0},
            {"judge_provider": "openai", "model_provider": "anthropic", "score": 7.0},
            {"judge_provider": "openai", "model_provider": "openai", "score": 6.0},
            {"judge_provider": "openai", "model_provider": "anthropic", "score": 6.0},
        ]
        result = detect_self_preference(scores)
        assert result["severity"] == "none"

    def test_strong_self_preference(self):
        scores = [
            {"judge_provider": "openai", "model_provider": "openai", "score": 9.0},
            {"judge_provider": "openai", "model_provider": "anthropic", "score": 4.0},
        ] * 10
        result = detect_self_preference(scores)
        assert result["severity"] in ("moderate", "high")


class TestConstantInputs:
    """NaN guard: constant inputs should not crash with JSON-serialization errors."""

    def test_constant_positions_no_crash(self):
        data = [(0, True)] * 10  # all same position, all wins
        result = detect_position_bias(data)
        assert result["severity"] == "none"
        assert result["correlation"] is None  # NaN avoided

    def test_constant_lengths_no_crash(self):
        data = [(100, 7.0)] * 10  # all same length and score
        result = detect_length_bias(data)
        assert result["severity"] == "none"
        assert result["correlation"] is None

    def test_constant_scores_no_crash(self):
        from app.core.bias import detect_verbosity_bias
        data = [(i * 100, 5.0) for i in range(10)]  # varying length, constant score
        result = detect_verbosity_bias(data)
        assert result["severity"] == "none"
        assert result["correlation"] is None


class TestClassifySeverity:
    def test_thresholds(self):
        assert classify_severity(0.0) == "none"
        assert classify_severity(0.15) == "low"
        assert classify_severity(0.35) == "moderate"
        assert classify_severity(0.6) == "high"
