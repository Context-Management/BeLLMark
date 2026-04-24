import pytest
from app.core.pricing import get_model_prices

def test_gpt5_mini_pricing():
    """GPT-5 mini should have its own pricing."""
    prices = get_model_prices("openai", "gpt-5-mini")
    assert prices == (0.25, 2.00)

def test_gpt5_nano_pricing():
    """GPT-5 nano should have its own pricing."""
    prices = get_model_prices("openai", "gpt-5-nano")
    assert prices == (0.05, 0.40)


def test_gpt54_nano_pricing():
    """GPT-5.4 nano should not silently fall back to zero pricing."""
    prices = get_model_prices("openai", "gpt-5.4-nano")
    assert prices == (0.20, 1.25)


def test_gpt52_codex_pricing():
    """GPT-5.2 Codex should have its own pricing."""
    prices = get_model_prices("openai", "gpt-5.2-codex")
    assert prices == (1.75, 14.00)


def test_gpt53_chat_latest_pricing():
    """GPT-5.3 chat latest should track the current OpenAI pricing."""
    prices = get_model_prices("openai", "gpt-5.3-chat-latest")
    assert prices == (1.75, 14.00)


def test_grok_41_fast_pricing():
    """Grok 4.1 Fast should have its own pricing."""
    prices = get_model_prices("grok", "grok-4-1-fast-reasoning")
    assert prices == (0.20, 0.50)


def test_grok_4200309_reasoning_pricing():
    """Grok 4.20-0309 reasoning should have an exact catalog price."""
    prices = get_model_prices("grok", "grok-4.20-0309-reasoning")
    assert prices == (2.00, 6.00)


def test_gemini3_pro_preview_pricing():
    """Gemini 3 Pro Preview should have its own pricing."""
    prices = get_model_prices("google", "gemini-3-pro-preview")
    assert prices == (2.00, 12.00)
