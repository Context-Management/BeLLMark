from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.pricing_catalog import MissingPricingError, resolve_catalog_price
from app.db.models import ProviderType


def _parse_checked_at(value: str) -> datetime:
    if "T" in value:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = datetime.fromisoformat(f"{value}T00:00:00+00:00")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _provider_value(provider: ProviderType | str) -> str:
    return provider.value if isinstance(provider, ProviderType) else str(provider)


def apply_catalog_pricing(model: Any) -> bool:
    """Populate pricing fields from the built-in catalog when available."""
    provider = _provider_value(model.provider)
    try:
        price = resolve_catalog_price(provider, model.model_id)
    except MissingPricingError:
        return False

    model.price_input = price.input_price
    model.price_output = price.output_price
    model.price_source = "catalog"
    model.price_source_url = price.source_url
    model.price_checked_at = _parse_checked_at(price.checked_at)
    model.price_currency = price.currency
    return True


def clear_pricing(model: Any) -> None:
    """Remove pricing fields when no trusted price is available."""
    model.price_input = None
    model.price_output = None
    model.price_source = None
    model.price_source_url = None
    model.price_checked_at = None
    model.price_currency = None


def apply_manual_pricing(model: Any) -> None:
    """Mark explicit user-supplied prices as manual overrides."""
    model.price_source = "manual"
    model.price_source_url = None
    model.price_checked_at = None
    model.price_currency = "USD"


def enrich_discovered_pricing(provider: ProviderType | str, models: list[dict]) -> list[dict]:
    """Attach price/provenance metadata to discovered models when a trusted source exists."""
    provider_value = _provider_value(provider)
    enriched: list[dict] = []
    checked_at = datetime.now(timezone.utc)

    for model in models:
        item = dict(model)

        if item.get("price_input") is not None and item.get("price_output") is not None:
            item.setdefault("price_source", "openrouter_api" if provider_value == "openrouter" else "provider_api")
            if provider_value == "openrouter":
                item.setdefault("price_source_url", "https://openrouter.ai/api/v1/models")
                item.setdefault("price_currency", "USD")
                item.setdefault("price_checked_at", checked_at)
            enriched.append(item)
            continue

        try:
            price = resolve_catalog_price(provider_value, item["model_id"])
        except MissingPricingError:
            enriched.append(item)
            continue

        item["price_input"] = price.input_price
        item["price_output"] = price.output_price
        item["price_source"] = "catalog"
        item["price_source_url"] = price.source_url
        item["price_checked_at"] = _parse_checked_at(price.checked_at)
        item["price_currency"] = price.currency
        enriched.append(item)

    return enriched
