import asyncio
from collections import defaultdict
from typing import Any, Iterable, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.discovery import DiscoveryError, discover_models
from app.db.models import ModelPreset, ProviderType
from app.schemas.models import DiscoveredModel, ModelValidationResult

LOCAL_PROVIDERS = {ProviderType.lmstudio, ProviderType.ollama}
DRIFT_FIELDS = ("quantization", "model_format", "parameter_count", "selected_variant", "context_limit")
SAFE_SYNC_FIELDS = ("context_limit", "selected_variant", "quantization_bits")
IDENTITY_FIELDS = ("name", "model_format", "quantization", "parameter_count")


def _as_discovered_model(model: dict[str, Any] | DiscoveredModel) -> DiscoveredModel:
    return model if isinstance(model, DiscoveredModel) else DiscoveredModel(**model)


async def _discover_local_inventory(provider: ProviderType, base_url: str) -> list[DiscoveredModel]:
    results = await asyncio.wait_for(
        discover_models(provider=provider, base_url=base_url),
        timeout=5.0,
    )
    return [_as_discovered_model(result) for result in results]


def _identity_match_score(preset: ModelPreset, live_match: DiscoveredModel) -> int:
    score = 0
    if preset.name and live_match.name and preset.name == live_match.name:
        score += 1
    if preset.model_format and live_match.model_format and preset.model_format == live_match.model_format:
        score += 1
    if preset.quantization and live_match.quantization and preset.quantization == live_match.quantization:
        score += 1
    if preset.parameter_count and live_match.parameter_count and preset.parameter_count == live_match.parameter_count:
        score += 1
    return score


def _identity_signal_count(preset: ModelPreset) -> int:
    return sum(1 for field in IDENTITY_FIELDS if getattr(preset, field, None))


def _metadata_drift(preset: ModelPreset, live_match: DiscoveredModel) -> list[str]:
    drift: list[str] = []
    for field in DRIFT_FIELDS:
        preset_value = getattr(preset, field, None)
        live_value = getattr(live_match, field, None)
        if preset_value is not None and live_value is not None and preset_value != live_value:
            drift.append(field)
    return drift


def sync_safe_metadata_fields(preset: ModelPreset, live_match: DiscoveredModel) -> bool:
    changed = False
    for field in SAFE_SYNC_FIELDS:
        live_value = getattr(live_match, field, None)
        if live_value is not None and getattr(preset, field, None) != live_value:
            setattr(preset, field, live_value)
            changed = True
    return changed


def classify_local_preset(
    preset: ModelPreset,
    discovered_models: list[dict[str, Any]] | list[DiscoveredModel],
    *,
    lm_link_ambiguous: bool = False,
) -> ModelValidationResult:
    live_models = [_as_discovered_model(model) for model in discovered_models]
    exact_match = next((model for model in live_models if model.model_id == preset.model_id), None)

    if lm_link_ambiguous:
        return ModelValidationResult(
            preset_id=preset.id,
            provider=preset.provider.value,
            base_url=preset.base_url,
            status="needs_probe",
            message="Inventory validation is ambiguous for this local server.",
            suggested_action="Use Test to confirm the exact preset.",
        )

    if exact_match:
        drift = _metadata_drift(preset, exact_match)
        if drift:
            return ModelValidationResult(
                preset_id=preset.id,
                provider=preset.provider.value,
                base_url=preset.base_url,
                status="available_metadata_drift",
                message="Model is available but metadata drift was detected.",
                live_match=exact_match,
                metadata_drift=drift,
                suggested_action="Review metadata drift",
            )
        return ModelValidationResult(
            preset_id=preset.id,
            provider=preset.provider.value,
            base_url=preset.base_url,
            status="available_exact",
            message="Exact local model match is available.",
            live_match=exact_match,
        )

    candidates = [model for model in live_models if _identity_match_score(preset, model) >= 3]
    if len(candidates) == 1:
        candidate = candidates[0]
        return ModelValidationResult(
            preset_id=preset.id,
            provider=preset.provider.value,
            base_url=preset.base_url,
            status="available_retarget_suggestion",
            message="A likely renamed local model was found.",
            live_match=candidate,
            suggested_action=f"Retarget to {candidate.model_id}",
        )
    if len(candidates) > 1:
        return ModelValidationResult(
            preset_id=preset.id,
            provider=preset.provider.value,
            base_url=preset.base_url,
            status="needs_probe",
            message="Multiple plausible live matches were found.",
            suggested_action="Use Test to confirm the exact preset.",
        )

    if _identity_signal_count(preset) < 3:
        return ModelValidationResult(
            preset_id=preset.id,
            provider=preset.provider.value,
            base_url=preset.base_url,
            status="needs_probe",
            message="Available metadata is too incomplete to classify this preset safely.",
            suggested_action="Use Test to confirm the exact preset.",
        )

    return ModelValidationResult(
        preset_id=preset.id,
        provider=preset.provider.value,
        base_url=preset.base_url,
        status="missing",
        message="No matching local model was found.",
        suggested_action="Archive missing local preset",
    )


def build_exact_test_result(
    preset: ModelPreset,
    test_connection_result: dict[str, Any],
    discovered_models: Optional[list[dict[str, Any]] | list[DiscoveredModel]] = None,
) -> dict[str, Any]:
    classification = None
    if discovered_models is not None:
        classification = classify_local_preset(preset, discovered_models)
    elif test_connection_result.get("resolved_model_id") == preset.model_id and preset.provider in LOCAL_PROVIDERS:
        classification = ModelValidationResult(
            preset_id=preset.id,
            provider=preset.provider.value,
            base_url=preset.base_url,
            status="available_exact",
            message="Exact local model match is available.",
        )

    live_match = classification.live_match if classification else None
    reasoning_levels = live_match.supported_reasoning_levels if live_match else None
    resolved_model_id = test_connection_result.get("resolved_model_id") or (live_match.model_id if live_match else None)

    payload = {
        "ok": bool(test_connection_result.get("ok")),
        "reachable": test_connection_result.get("reachable", bool(test_connection_result.get("ok"))),
        "provider": preset.provider.value,
        "base_url": preset.base_url,
        "model_id": preset.model_id,
        "resolved_model_id": resolved_model_id,
        "model_info": test_connection_result.get("model_info") or (live_match.model_dump() if live_match else None),
        "reasoning_supported_levels": test_connection_result.get("reasoning_supported_levels") or reasoning_levels,
        "validation_status": classification.status if classification else None,
        "validation_message": classification.message if classification else None,
        "live_match": live_match.model_dump() if live_match else None,
        "metadata_drift": classification.metadata_drift if classification else [],
        "suggested_action": classification.suggested_action if classification else None,
        "error": test_connection_result.get("error"),
    }
    if "models" in test_connection_result:
        payload["models"] = test_connection_result["models"]
    return payload


async def _validate_presets(presets: Iterable[ModelPreset]) -> list[ModelValidationResult]:
    grouped: dict[tuple[ProviderType, str], list[ModelPreset]] = defaultdict(list)
    for preset in presets:
        grouped[(preset.provider, preset.base_url)].append(preset)

    results: list[ModelValidationResult] = []
    for (provider, base_url), group_presets in grouped.items():
        try:
            discovered = await _discover_local_inventory(provider, base_url)
        except DiscoveryError as exc:
            status = "validation_failed" if str(exc).startswith("Failed to discover") else "server_unreachable"
            suggested_action = None if status == "validation_failed" else "Check that the local server is running."
            for preset in group_presets:
                results.append(
                    ModelValidationResult(
                        preset_id=preset.id,
                        provider=provider.value,
                        base_url=base_url,
                        status=status,
                        message=str(exc),
                        suggested_action=suggested_action,
                    )
                )
            continue
        except (asyncio.TimeoutError, httpx.HTTPError, httpx.ConnectError) as exc:
            for preset in group_presets:
                results.append(
                    ModelValidationResult(
                        preset_id=preset.id,
                        provider=provider.value,
                        base_url=base_url,
                        status="server_unreachable",
                        message=f"Local server is unreachable: {exc}",
                        suggested_action="Check that the local server is running.",
                    )
                )
            continue
        except Exception as exc:
            for preset in group_presets:
                results.append(
                    ModelValidationResult(
                        preset_id=preset.id,
                        provider=provider.value,
                        base_url=base_url,
                        status="validation_failed",
                        message=f"Validation failed: {exc}",
                    )
                )
            continue

        for preset in group_presets:
            try:
                result = classify_local_preset(preset, discovered)
                if result.status in {"available_exact", "available_metadata_drift"} and result.live_match:
                    sync_safe_metadata_fields(preset, result.live_match)
                results.append(result)
            except Exception as exc:
                results.append(
                    ModelValidationResult(
                        preset_id=preset.id,
                        provider=provider.value,
                        base_url=base_url,
                        status="validation_failed",
                        message=f"Validation failed: {exc}",
                    )
                )

    return results


async def validate_run_local_presets(db: Session, presets: list[ModelPreset]) -> list[ModelValidationResult]:
    local_presets = [
        preset for preset in presets
        if preset.provider in LOCAL_PROVIDERS and not preset.is_archived
    ]
    return await _validate_presets(local_presets)


async def validate_local_presets(
    db: Session,
    scope: str,
    provider: Optional[ProviderType] = None,
    base_url: Optional[str] = None,
    model_ids: Optional[list[int]] = None,
) -> list[ModelValidationResult]:
    query = db.query(ModelPreset).filter(ModelPreset.is_archived == 0)
    if scope == "local":
        query = query.filter(ModelPreset.provider.in_(LOCAL_PROVIDERS))
    elif scope == "specific_ids":
        if not model_ids:
            return []
        query = query.filter(ModelPreset.id.in_(model_ids))
    else:
        raise ValueError(f"Unsupported validation scope: {scope}")

    if provider is not None:
        query = query.filter(ModelPreset.provider == provider)
    if base_url is not None:
        query = query.filter(ModelPreset.base_url == base_url)

    presets = query.all()
    return await validate_run_local_presets(db, presets)
