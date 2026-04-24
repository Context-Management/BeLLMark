# backend/app/api/models.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.db.models import ModelPreset, ReasoningLevel, ProviderType
from app.schemas.models import (
    ModelPresetCreate,
    ModelPresetResponse,
    ModelPresetUpdate,
    DiscoverModelsRequest,
    DiscoveredModel,
    ModelValidationResult,
    ValidateModelsRequest,
)
from app.core.crypto import encrypt_api_key
from app.core.generators import test_connection
from app.core.url_validation import validate_base_url
from app.core.model_validation import validate_local_presets
from app.core.discovery import (
    discover_models,
    detect_reasoning_capability,
    resolve_lmstudio_reasoning_capability,
    DiscoveryError,
)
from app.api.elo import invalidate_aggregate_leaderboard_cache
from app.core.pricing_sync import apply_catalog_pricing, apply_manual_pricing, clear_pricing

router = APIRouter(prefix="/api/models", tags=["models"])


def _backfill_catalog_pricing_if_needed(preset: ModelPreset) -> bool:
    """Backfill or refresh catalog pricing for non-manual presets."""
    if preset.price_source == "manual":
        return False
    before = (
        preset.price_input,
        preset.price_output,
        preset.price_source,
        preset.price_source_url,
        preset.price_checked_at,
        preset.price_currency,
    )
    if preset.price_source == "catalog":
        if not apply_catalog_pricing(preset):
            return False
    elif preset.price_input is None or preset.price_output is None:
        if not apply_catalog_pricing(preset):
            return False
    else:
        return False
    after = (
        preset.price_input,
        preset.price_output,
        preset.price_source,
        preset.price_source_url,
        preset.price_checked_at,
        preset.price_currency,
    )
    return after != before


def _backfill_openrouter_pricing_metadata_if_needed(preset: ModelPreset) -> bool:
    """Attach provenance to legacy OpenRouter rows that already store prices."""
    if preset.provider != ProviderType.openrouter:
        return False
    if preset.price_source == "manual" or preset.price_source is not None:
        return False
    if preset.price_input is None or preset.price_output is None:
        return False

    preset.price_source = "openrouter_api"
    preset.price_source_url = "https://openrouter.ai/api/v1/models"
    if preset.price_currency is None:
        preset.price_currency = "USD"
    return True

def _preset_to_response(preset: ModelPreset) -> ModelPresetResponse:
    """Convert DB model to response schema, handling vision support and reasoning boolean conversion."""
    supported_reasoning_levels = None
    reasoning_detection_source = preset.reasoning_detection_source
    if preset.provider == ProviderType.lmstudio:
        caps = resolve_lmstudio_reasoning_capability(
            preset.model_id,
            preset.model_architecture,
        )
        supported_reasoning_levels = caps.get("supported_reasoning_levels")
        reasoning_detection_source = caps.get("reasoning_detection_source") or reasoning_detection_source
    elif preset.is_reasoning:
        caps = detect_reasoning_capability(preset.model_id, preset.provider.value)
        supported_reasoning_levels = caps.get("reasoning_levels") or None

    return ModelPresetResponse(
        id=preset.id,
        name=preset.name,
        provider=preset.provider,
        base_url=preset.base_url,
        model_id=preset.model_id,
        has_api_key=preset.api_key_encrypted is not None,
        price_input=preset.price_input,
        price_output=preset.price_output,
        price_source=preset.price_source,
        price_source_url=preset.price_source_url,
        price_checked_at=preset.price_checked_at,
        price_currency=preset.price_currency,
        supports_vision=bool(preset.supports_vision) if preset.supports_vision is not None else None,
        context_limit=preset.context_limit,
        is_reasoning=bool(preset.is_reasoning),
        reasoning_level=preset.reasoning_level.value if preset.reasoning_level else None,
        custom_temperature=preset.custom_temperature,
        quantization=preset.quantization,
        model_format=preset.model_format,
        model_source=preset.model_source,
        parameter_count=preset.parameter_count,
        quantization_bits=preset.quantization_bits,
        selected_variant=preset.selected_variant,
        model_architecture=preset.model_architecture,
        supported_reasoning_levels=supported_reasoning_levels,
        reasoning_detection_source=reasoning_detection_source,
        created_at=preset.created_at
    )


def _normalize_deepseek_reasoner_preset(preset: ModelPreset) -> bool:
    """Force DeepSeek Reasoner presets to stay reasoning-capable."""
    if preset.provider == ProviderType.deepseek and "deepseek-reasoner" in preset.model_id.lower():
        changed = False
        if not preset.is_reasoning:
            preset.is_reasoning = 1
            changed = True
        if preset.reasoning_level is not None:
            preset.reasoning_level = None
            changed = True
        return changed
    return False

@router.get("/", response_model=List[ModelPresetResponse])
def list_models(
    limit: int = 500,
    offset: int = 0,
    include_archived: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(ModelPreset)
    if not include_archived:
        query = query.filter(ModelPreset.is_archived == 0)
    models = query.order_by(ModelPreset.created_at.desc()).offset(offset).limit(limit).all()
    updated = False
    for preset in models:
        if _backfill_catalog_pricing_if_needed(preset):
            updated = True
        if _backfill_openrouter_pricing_metadata_if_needed(preset):
            updated = True
    if updated:
        db.commit()
    return [_preset_to_response(m) for m in models]

@router.post("/", response_model=ModelPresetResponse)
def create_model(model: ModelPresetCreate, db: Session = Depends(get_db)):
    # Validate base_url against SSRF / key-exfiltration
    try:
        validated_url = validate_base_url(model.provider, model.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Encrypt API key before storing
    encrypted_key = encrypt_api_key(model.api_key) if model.api_key else None

    db_model = ModelPreset(
        name=model.name,
        provider=model.provider,
        base_url=validated_url,
        model_id=model.model_id,
        api_key_encrypted=encrypted_key,
        price_input=model.price_input,
        price_output=model.price_output,
        price_source=model.price_source,
        price_source_url=model.price_source_url,
        price_checked_at=model.price_checked_at,
        price_currency=model.price_currency,
        supports_vision=1 if model.supports_vision else (0 if model.supports_vision is False else None),
        context_limit=model.context_limit,
        is_reasoning=1 if model.is_reasoning else 0,
        reasoning_level=ReasoningLevel(model.reasoning_level) if model.reasoning_level else None,
        custom_temperature=model.custom_temperature,
        quantization=model.quantization,
        model_format=model.model_format,
        model_source=model.model_source,
        parameter_count=model.parameter_count,
        quantization_bits=model.quantization_bits,
        selected_variant=model.selected_variant,
        model_architecture=model.model_architecture,
        reasoning_detection_source=model.reasoning_detection_source,
    )
    if model.price_source or model.price_source_url or model.price_checked_at or model.price_currency:
        pass
    elif model.price_input is not None or model.price_output is not None:
        apply_manual_pricing(db_model)
    else:
        clear_pricing(db_model)
        apply_catalog_pricing(db_model)
    _normalize_deepseek_reasoner_preset(db_model)
    db.add(db_model)
    db.commit()
    db.refresh(db_model)
    return _preset_to_response(db_model)

@router.get("/{model_id}", response_model=ModelPresetResponse)
def get_model(model_id: int, db: Session = Depends(get_db)):
    model = db.query(ModelPreset).filter(ModelPreset.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    updated = False
    if _backfill_catalog_pricing_if_needed(model):
        updated = True
    if _backfill_openrouter_pricing_metadata_if_needed(model):
        updated = True
    if updated:
        db.commit()
        db.refresh(model)
    return _preset_to_response(model)

@router.delete("/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)):
    model = db.query(ModelPreset).filter(ModelPreset.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    model.is_archived = 1
    db.commit()
    # Archived models are filtered out of the aggregate leaderboard.
    invalidate_aggregate_leaderboard_cache()
    return {"status": "archived"}

@router.put("/{model_id}", response_model=ModelPresetResponse)
def update_model(model_id: int, model: ModelPresetUpdate, db: Session = Depends(get_db)):
    db_model = db.query(ModelPreset).filter(ModelPreset.id == model_id).first()
    if not db_model:
        raise HTTPException(status_code=404, detail="Model not found")

    if model.name is not None:
        db_model.name = model.name
    if model.provider is not None:
        db_model.provider = model.provider
    if model.base_url is not None:
        # Validate base_url against SSRF / key-exfiltration
        effective_provider = model.provider if model.provider is not None else db_model.provider
        try:
            db_model.base_url = validate_base_url(effective_provider, model.base_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if model.model_id is not None:
        db_model.model_id = model.model_id
    if model.api_key is not None:
        db_model.api_key_encrypted = encrypt_api_key(model.api_key) if model.api_key else None
    if model.price_input is not None:
        db_model.price_input = model.price_input
    if model.price_output is not None:
        db_model.price_output = model.price_output
    if model.price_source is not None:
        db_model.price_source = model.price_source
    if model.price_source_url is not None:
        db_model.price_source_url = model.price_source_url
    if model.price_checked_at is not None:
        db_model.price_checked_at = model.price_checked_at
    if model.price_currency is not None:
        db_model.price_currency = model.price_currency
    if model.supports_vision is not None:
        db_model.supports_vision = 1 if model.supports_vision else 0
    if model.context_limit is not None:
        db_model.context_limit = model.context_limit
    if model.is_reasoning is not None:
        db_model.is_reasoning = 1 if model.is_reasoning else 0
    if model.reasoning_level is not None:
        db_model.reasoning_level = ReasoningLevel(model.reasoning_level) if model.reasoning_level else None
    if model.custom_temperature is not None:
        db_model.custom_temperature = model.custom_temperature
    if model.quantization is not None:
        db_model.quantization = model.quantization
    if model.model_format is not None:
        db_model.model_format = model.model_format
    if model.model_source is not None:
        db_model.model_source = model.model_source
    if model.parameter_count is not None:
        db_model.parameter_count = model.parameter_count
    if model.quantization_bits is not None:
        db_model.quantization_bits = model.quantization_bits
    if model.selected_variant is not None:
        db_model.selected_variant = model.selected_variant
    if model.model_architecture is not None:
        db_model.model_architecture = model.model_architecture
    if model.reasoning_detection_source is not None:
        db_model.reasoning_detection_source = model.reasoning_detection_source

    if any(
        value is not None
        for value in (model.price_source, model.price_source_url, model.price_checked_at, model.price_currency)
    ):
        pass
    elif model.price_input is not None or model.price_output is not None:
        apply_manual_pricing(db_model)
    elif model.provider is not None or model.model_id is not None:
        clear_pricing(db_model)
        apply_catalog_pricing(db_model)

    _normalize_deepseek_reasoner_preset(db_model)

    db.commit()
    db.refresh(db_model)

    return _preset_to_response(db_model)

@router.post("/{model_id}/test")
async def test_model_connection(model_id: int, db: Session = Depends(get_db)):
    model = db.query(ModelPreset).filter(ModelPreset.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    result = await test_connection(model)

    if result["ok"]:
        return {"status": "ok", "message": "Connection successful", **result}
    else:
        return {"status": "error", "message": result.get("error", "Unknown error"), **result}


@router.post("/validate", response_model=List[ModelValidationResult])
async def validate_models(request: ValidateModelsRequest, db: Session = Depends(get_db)):
    if request.scope not in {"local", "specific_ids"}:
        raise HTTPException(status_code=400, detail="Unsupported validation scope")

    try:
        results = await validate_local_presets(
            db,
            request.scope,
            provider=request.provider,
            base_url=request.base_url,
            model_ids=request.model_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()
    return results


@router.post("/discover", response_model=List[DiscoveredModel])
async def discover_provider_models(request: DiscoverModelsRequest):
    """Discover available models from a provider's API."""
    from app.core.url_validation import validate_base_url
    try:
        validated_url = validate_base_url(request.provider, request.base_url)
        results = await discover_models(
            provider=request.provider,
            base_url=validated_url,
            api_key=request.api_key,
        )
        return [DiscoveredModel(**r) for r in results]
    except DiscoveryError as e:
        raise HTTPException(status_code=502, detail=str(e))
