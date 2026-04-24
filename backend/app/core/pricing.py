# backend/app/core/pricing.py
"""
Pricing helpers for provider/model cost estimation.
Prices are per 1 million tokens (input, output) in USD unless the catalog
metadata says otherwise. The runtime only consumes input/output prices here.
"""

from app.core.pricing_catalog import DEFAULT_PRICE_PROVIDERS, MissingPricingError, resolve_catalog_price


def get_model_prices(provider: str, model_id: str) -> tuple[float, float]:
    """
    Get (input_price, output_price) per 1M tokens for a model.
    Hosted providers fail closed unless they have an exact catalog entry or
    explicit alias. Local providers and OpenRouter retain zero-cost defaults.
    """
    try:
        price = resolve_catalog_price(
            provider,
            model_id,
            allow_provider_default=provider.lower() in DEFAULT_PRICE_PROVIDERS,
        )
    except MissingPricingError:
        return (0.0, 0.0)
    return (price.input_price, price.output_price)


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    price_input: float,
    price_output: float,
) -> float:
    """Calculate cost in USD from token counts and prices per 1M tokens."""
    return (input_tokens * price_input + output_tokens * price_output) / 1_000_000


def estimate_token_split(total_tokens: int | None) -> tuple[int, int]:
    """Estimate input/output split for legacy rows that only stored total tokens."""
    total = max(int(total_tokens or 0), 0)
    input_tokens = int(total * 0.2)
    output_tokens = max(total - input_tokens, 0)
    return input_tokens, output_tokens


def calculate_usage_cost(
    input_tokens: int,
    output_tokens: int,
    price_input: float,
    price_output: float,
    cached_input_tokens: int = 0,
    cached_input_price: float | None = None,
) -> float:
    """Calculate cost from persisted usage fields, including cached prompt tokens."""
    input_total = max(int(input_tokens or 0), 0)
    output_total = max(int(output_tokens or 0), 0)
    cached_total = min(max(int(cached_input_tokens or 0), 0), input_total)
    uncached_total = max(input_total - cached_total, 0)
    cached_price = price_input if cached_input_price is None else cached_input_price
    return (
        uncached_total * price_input
        + cached_total * cached_price
        + output_total * price_output
    ) / 1_000_000


def calculate_model_cost(
    provider: str,
    model_id: str,
    price_input: float,
    price_output: float,
    *,
    total_tokens: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    cached_input_price: float | None = None,
) -> tuple[float, bool]:
    """Calculate model cost and report whether a legacy token split estimate was used."""
    input_total = input_tokens
    output_total = output_tokens
    used_estimate = False

    if input_total is None and output_total is None:
        input_total, output_total = estimate_token_split(total_tokens)
        used_estimate = bool(total_tokens)
    elif input_total is None:
        total = total_tokens if total_tokens is not None else output_total
        input_total = max(int((total or 0) - (output_total or 0)), 0)
    elif output_total is None:
        total = total_tokens if total_tokens is not None else input_total
        output_total = max(int((total or 0) - (input_total or 0)), 0)

    if cached_input_price is None:
        try:
            catalog_price = resolve_catalog_price(provider, model_id)
            cached_price = catalog_price.cached_input_price
        except MissingPricingError:
            cached_price = None
    else:
        cached_price = cached_input_price

    return (
        calculate_usage_cost(
            input_tokens=input_total or 0,
            output_tokens=output_total or 0,
            price_input=price_input,
            price_output=price_output,
            cached_input_tokens=cached_input_tokens or 0,
            cached_input_price=cached_price,
        ),
        used_estimate,
    )
