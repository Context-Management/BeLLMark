# backend/app/schemas/models.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.db.models import ProviderType

class ModelPresetCreate(BaseModel):
    name: str
    provider: ProviderType
    base_url: str
    model_id: str
    api_key: Optional[str] = None
    price_input: Optional[float] = None   # $/1M input tokens (null = use defaults)
    price_output: Optional[float] = None  # $/1M output tokens (null = use defaults)
    price_source: Optional[str] = None
    price_source_url: Optional[str] = None
    price_checked_at: Optional[datetime] = None
    price_currency: Optional[str] = None
    supports_vision: Optional[bool] = None  # Whether model supports image inputs
    context_limit: Optional[int] = None  # Max context window in tokens
    is_reasoning: bool = False
    reasoning_level: Optional[str] = None  # none, low, medium, high, xhigh
    custom_temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)  # 0.0-2.0, used when mode=custom
    quantization: Optional[str] = None
    model_format: Optional[str] = None
    model_source: Optional[str] = None
    parameter_count: Optional[str] = None
    quantization_bits: Optional[float] = None
    selected_variant: Optional[str] = None
    model_architecture: Optional[str] = None
    supported_reasoning_levels: Optional[List[str]] = None
    reasoning_detection_source: Optional[str] = None

class ModelPresetResponse(BaseModel):
    id: int
    name: str
    provider: ProviderType
    base_url: str
    model_id: str
    has_api_key: bool
    price_input: Optional[float] = None
    price_output: Optional[float] = None
    price_source: Optional[str] = None
    price_source_url: Optional[str] = None
    price_checked_at: Optional[datetime] = None
    price_currency: Optional[str] = None
    supports_vision: Optional[bool] = None
    context_limit: Optional[int] = None
    is_reasoning: bool
    reasoning_level: Optional[str]
    custom_temperature: Optional[float] = None
    quantization: Optional[str] = None
    model_format: Optional[str] = None
    model_source: Optional[str] = None
    parameter_count: Optional[str] = None
    quantization_bits: Optional[float] = None
    selected_variant: Optional[str] = None
    model_architecture: Optional[str] = None
    supported_reasoning_levels: Optional[List[str]] = None
    reasoning_detection_source: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ModelPresetUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[ProviderType] = None
    base_url: Optional[str] = None
    model_id: Optional[str] = None
    api_key: Optional[str] = None
    price_input: Optional[float] = None
    price_output: Optional[float] = None
    price_source: Optional[str] = None
    price_source_url: Optional[str] = None
    price_checked_at: Optional[datetime] = None
    price_currency: Optional[str] = None
    supports_vision: Optional[bool] = None
    context_limit: Optional[int] = None
    is_reasoning: Optional[bool] = None
    reasoning_level: Optional[str] = None
    custom_temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    quantization: Optional[str] = None
    model_format: Optional[str] = None
    model_source: Optional[str] = None
    parameter_count: Optional[str] = None
    quantization_bits: Optional[float] = None
    selected_variant: Optional[str] = None
    model_architecture: Optional[str] = None
    supported_reasoning_levels: Optional[List[str]] = None
    reasoning_detection_source: Optional[str] = None


class DiscoverModelsRequest(BaseModel):
    provider: ProviderType
    base_url: Optional[str] = None   # For LM Studio custom URLs
    api_key: Optional[str] = None    # Override .env key


class DiscoveredModel(BaseModel):
    model_id: str
    name: str                                  # Human-friendly display name
    is_reasoning: bool = False
    reasoning_level: Optional[str] = None      # Suggested default: none/low/medium/high
    supports_vision: Optional[bool] = None
    context_limit: Optional[int] = None
    provider_default_url: Optional[str] = None # Pre-filled base URL for this provider
    price_input: Optional[float] = None        # $/1M input tokens (from discovery)
    price_output: Optional[float] = None       # $/1M output tokens (from discovery)
    price_source: Optional[str] = None
    price_source_url: Optional[str] = None
    price_checked_at: Optional[datetime] = None
    price_currency: Optional[str] = None
    quantization: Optional[str] = None
    model_format: Optional[str] = None
    model_source: Optional[str] = None
    parameter_count: Optional[str] = None
    quantization_bits: Optional[float] = None
    selected_variant: Optional[str] = None
    model_architecture: Optional[str] = None
    supported_reasoning_levels: Optional[List[str]] = None
    reasoning_detection_source: Optional[str] = None


class ModelValidationResult(BaseModel):
    preset_id: int
    provider: str
    base_url: str
    status: str
    message: str
    live_match: Optional[DiscoveredModel] = None
    metadata_drift: List[str] = Field(default_factory=list)
    suggested_action: Optional[str] = None


class ValidateModelsRequest(BaseModel):
    scope: str = "local"
    provider: Optional[ProviderType] = None
    base_url: Optional[str] = None
    model_ids: Optional[List[int]] = None
