from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class MissingPricingError(ValueError):
    """Raised when a hosted model has no exact or explicit catalog price."""


@dataclass(frozen=True)
class CatalogPrice:
    provider: str
    model_id: str
    input_price: float
    output_price: float
    cached_input_price: float | None
    currency: str
    pricing_mode: str
    source_url: str
    checked_at: str


@dataclass(frozen=True)
class AliasRule:
    provider: str
    pattern: str
    model_id: str
    match_type: str = "prefix"


CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "pricing_catalog.json"
DEFAULT_PRICE_PROVIDERS = frozenset({"lmstudio", "ollama", "openrouter"})


@lru_cache(maxsize=1)
def _load_catalog() -> dict:
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=1)
def _model_lookup() -> dict[tuple[str, str], CatalogPrice]:
    catalog = _load_catalog()
    models: dict[tuple[str, str], CatalogPrice] = {}
    for entry in catalog["models"]:
        price = CatalogPrice(
            provider=entry["provider"],
            model_id=entry["model_id"],
            input_price=entry["input_price"],
            output_price=entry["output_price"],
            cached_input_price=entry.get("cached_input_price"),
            currency=entry.get("currency", "USD"),
            pricing_mode=entry.get("pricing_mode", "flat"),
            source_url=entry["source_url"],
            checked_at=entry["checked_at"],
        )
        models[(price.provider, price.model_id)] = price
    return models


@lru_cache(maxsize=1)
def _alias_rules() -> tuple[AliasRule, ...]:
    catalog = _load_catalog()
    return tuple(
        AliasRule(
            provider=entry["provider"],
            pattern=entry["pattern"],
            model_id=entry["model_id"],
            match_type=entry.get("match_type", "prefix"),
        )
        for entry in catalog.get("aliases", [])
    )


@lru_cache(maxsize=1)
def _provider_defaults() -> dict[str, CatalogPrice]:
    catalog = _load_catalog()
    defaults: dict[str, CatalogPrice] = {}
    for provider, entry in catalog.get("provider_defaults", {}).items():
        if provider not in DEFAULT_PRICE_PROVIDERS:
            continue
        defaults[provider] = CatalogPrice(
            provider=provider,
            model_id="_default",
            input_price=entry["input_price"],
            output_price=entry["output_price"],
            cached_input_price=entry.get("cached_input_price"),
            currency=entry.get("currency", "USD"),
            pricing_mode=entry.get("pricing_mode", "flat"),
            source_url=entry["source_url"],
            checked_at=entry["checked_at"],
        )
    return defaults


def _resolve_alias(provider: str, model_id: str) -> CatalogPrice | None:
    rules = sorted(
        (rule for rule in _alias_rules() if rule.provider == provider),
        key=lambda rule: len(rule.pattern),
        reverse=True,
    )
    for rule in rules:
        if rule.match_type == "prefix" and model_id.startswith(rule.pattern):
            return _model_lookup().get((provider, rule.model_id))
        if rule.match_type == "exact" and model_id == rule.pattern:
            return _model_lookup().get((provider, rule.model_id))
    return None


def resolve_catalog_price(
    provider: str,
    model_id: str,
    require_exact: bool = False,
    allow_provider_default: bool = False,
) -> CatalogPrice:
    provider = provider.lower()
    exact = _model_lookup().get((provider, model_id))
    if exact is not None:
        return exact

    alias_match = _resolve_alias(provider, model_id)
    if alias_match is not None:
        return alias_match

    if require_exact:
        raise MissingPricingError(f"No catalog price for {provider}:{model_id}")

    if allow_provider_default and provider in DEFAULT_PRICE_PROVIDERS:
        default = _provider_defaults().get(provider)
        if default is not None:
            return default

    raise MissingPricingError(f"No catalog price for {provider}:{model_id}")
