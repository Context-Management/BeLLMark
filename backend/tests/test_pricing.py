# backend/tests/test_pricing.py
import pytest
from app.core.pricing import get_model_prices, calculate_cost


def test_get_model_prices_exact_match():
    """Test exact model ID match."""
    price_in, price_out = get_model_prices("anthropic", "claude-sonnet-4-5")
    assert price_in == 3.00
    assert price_out == 15.00


def test_get_model_prices_partial_match():
    """Test partial model ID match (model_id contains key)."""
    price_in, price_out = get_model_prices("openai", "gpt-4o-2024-08-06")
    assert price_in == 2.50
    assert price_out == 10.00


def test_get_model_prices_hosted_unknown_model_fails_closed():
    """Hosted providers should not silently fall back to provider defaults."""
    price_in, price_out = get_model_prices("anthropic", "claude-unknown-model")
    assert price_in == 0.0
    assert price_out == 0.0


def test_get_model_prices_lmstudio_free():
    """Test LM Studio is always free."""
    price_in, price_out = get_model_prices("lmstudio", "any-local-model")
    assert price_in == 0.0
    assert price_out == 0.0


def test_get_model_prices_unknown_provider():
    """Test unknown provider returns zeros."""
    price_in, price_out = get_model_prices("unknown_provider", "some-model")
    assert price_in == 0.0
    assert price_out == 0.0


def test_calculate_cost():
    """Test cost calculation."""
    # 1000 input tokens at $1.50/1M + 2000 output tokens at $7.50/1M
    cost = calculate_cost(1000, 2000, 1.50, 7.50)
    # (1000 * 1.5 + 2000 * 7.5) / 1_000_000 = (1500 + 15000) / 1_000_000 = 0.0165
    assert cost == pytest.approx(0.0165, rel=1e-6)


def test_calculate_cost_zero_tokens():
    """Test cost calculation with zero tokens."""
    cost = calculate_cost(0, 0, 1.50, 7.50)
    assert cost == 0.0


def test_get_model_prices_substring_priority():
    """Test that longer model ID matches take priority over shorter substrings."""
    # Should match gpt-4o-mini, not gpt-4o
    price_in, price_out = get_model_prices("openai", "gpt-4o-mini-2024-11-20")
    assert price_in == 0.15
    assert price_out == 0.60

    # Should match grok-4-fast, not grok-4
    price_in, price_out = get_model_prices("grok", "grok-4-fast-latest")
    assert price_in == 0.20
    assert price_out == 0.50
