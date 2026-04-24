import pytest

from app.core.pricing import get_model_prices
from app.core.pricing_catalog import MissingPricingError, resolve_catalog_price


def test_resolve_catalog_price_requires_exact_current_entries():
    gpt41 = resolve_catalog_price("openai", "gpt-4.1")
    assert gpt41.input_price == 2.0
    assert gpt41.output_price == 8.0

    gemini_lite = resolve_catalog_price("google", "gemini-3.1-flash-lite-preview")
    assert gemini_lite.input_price == 0.10
    assert gemini_lite.output_price == 0.40


def test_resolve_catalog_price_rejects_unknown_hosted_models_when_exact_required():
    with pytest.raises(MissingPricingError):
        resolve_catalog_price("openai", "gpt-made-up-2026", require_exact=True)


def test_resolve_catalog_price_for_mistral_large_latest_uses_current_rate():
    price = resolve_catalog_price("mistral", "mistral-large-latest")
    assert price.input_price == 0.5
    assert price.output_price == 1.5


def test_resolve_catalog_price_uses_current_glm_entries():
    glm47 = resolve_catalog_price("glm", "glm-4.7")
    assert glm47.input_price == 2.0
    assert glm47.output_price == 8.0
    assert glm47.currency == "RMB"

    glm47_flash = resolve_catalog_price("glm", "glm-4.7-flash")
    assert glm47_flash.input_price == 0.0
    assert glm47_flash.output_price == 0.0
    assert glm47_flash.pricing_mode == "free"

    glm46v_flash = resolve_catalog_price("glm", "glm-4.6v-flash")
    assert glm46v_flash.input_price == 0.0
    assert glm46v_flash.output_price == 0.0
    assert glm46v_flash.pricing_mode == "free"

    assert get_model_prices("glm", "glm-4.7") == (2.0, 8.0)


def test_resolve_catalog_price_rejects_unknown_glm_models_when_exact_required():
    with pytest.raises(MissingPricingError):
        resolve_catalog_price("glm", "glm-made-up-2026", require_exact=True)
