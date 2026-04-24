import pytest
from pydantic import ValidationError
from app.schemas.models import ModelPresetCreate, ModelPresetResponse


def test_discovered_model_includes_pricing_fields():
    """DiscoveredModel should accept and return pricing fields."""
    from app.schemas.models import DiscoveredModel
    m = DiscoveredModel(
        model_id="anthropic/claude-sonnet-4-5",
        name="Claude Sonnet 4.5",
        price_input=3.0,
        price_output=15.0,
    )
    assert m.price_input == 3.0
    assert m.price_output == 15.0


def test_discovered_model_accepts_pricing_provenance():
    from app.schemas.models import DiscoveredModel
    m = DiscoveredModel(
        model_id="openai/gpt-4.1",
        name="GPT-4.1",
        price_source="catalog",
        price_source_url="https://openai.com/api/pricing/",
        price_currency="USD",
        price_checked_at="2026-03-26T00:00:00Z",
    )
    assert m.price_source == "catalog"
    assert m.price_source_url == "https://openai.com/api/pricing/"
    assert m.price_currency == "USD"


def test_discovered_model_pricing_defaults_to_none():
    """DiscoveredModel pricing should default to None (not required)."""
    from app.schemas.models import DiscoveredModel
    m = DiscoveredModel(model_id="test", name="Test")
    assert m.price_input is None
    assert m.price_output is None


def test_model_create_with_reasoning():
    """ModelPresetCreate should accept reasoning fields."""
    data = ModelPresetCreate(
        name="GPT-5.2 Reasoning",
        provider="openai",
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-5.2",
        is_reasoning=True,
        reasoning_level="high"
    )
    assert data.is_reasoning is True
    assert data.reasoning_level == "high"


def test_model_create_rejects_custom_temperature_above_range():
    """Custom temperature should be capped at 2.0 in the schema."""
    with pytest.raises(ValidationError):
        ModelPresetCreate(
            name="Too Hot",
            provider="openai",
            base_url="https://api.openai.com/v1/chat/completions",
            model_id="gpt-4.1",
            custom_temperature=2.5,
        )

def test_model_response_includes_reasoning():
    """ModelPresetResponse should include reasoning fields."""
    response = ModelPresetResponse(
        id=1,
        name="Test",
        provider="openai",
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-5.2",
        has_api_key=False,
        price_input=None,
        price_output=None,
        supports_vision=None,
        context_limit=None,
        is_reasoning=True,
        reasoning_level="high",
        created_at="2026-02-03T00:00:00"
    )
    assert response.is_reasoning is True
    assert response.reasoning_level == "high"


def test_model_response_allows_legacy_custom_temperature():
    response = ModelPresetResponse(
        id=1,
        name="Legacy Temp",
        provider="openai",
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-4.1",
        has_api_key=False,
        price_input=2.0,
        price_output=8.0,
        price_source="catalog",
        price_source_url="https://openai.com/api/pricing/",
        price_checked_at="2026-03-26T00:00:00Z",
        price_currency="USD",
        supports_vision=None,
        context_limit=None,
        is_reasoning=False,
        reasoning_level=None,
        custom_temperature=2.5,
        created_at="2026-02-03T00:00:00",
    )
    assert response.custom_temperature == 2.5
    assert response.price_source == "catalog"


def test_lmstudio_metadata_fields_are_present_on_schemas():
    from app.schemas.models import DiscoveredModel

    for field in (
        "parameter_count",
        "quantization_bits",
        "selected_variant",
        "model_architecture",
        "supported_reasoning_levels",
        "reasoning_detection_source",
    ):
        assert field in DiscoveredModel.model_fields
        assert field in ModelPresetResponse.model_fields
