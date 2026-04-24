import pytest
from app.db.models import ModelPreset, ReasoningLevel

def test_model_preset_has_reasoning_fields():
    """ModelPreset should have is_reasoning and reasoning_level fields."""
    preset = ModelPreset(
        name="Test Model",
        provider="openai",
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-5.2",
        is_reasoning=True,
        reasoning_level=ReasoningLevel.high
    )
    assert preset.is_reasoning is True
    assert preset.reasoning_level == ReasoningLevel.high

def test_model_preset_reasoning_defaults():
    """Non-reasoning models should have None reasoning_level."""
    preset = ModelPreset(
        name="Non-reasoning",
        provider="openai",
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-5.2-chat-latest",
        is_reasoning=False
    )
    assert preset.is_reasoning is False
    assert preset.reasoning_level is None
