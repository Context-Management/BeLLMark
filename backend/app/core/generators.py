# backend/app/core/generators.py
import asyncio
import httpx
import json
import logging
import os
import re
import time
from typing import Optional, List, Dict, Any
from app.db.models import ModelPreset, ProviderType, ReasoningLevel, TemperatureMode
from app.core.crypto import decrypt_api_key
from app.core.attachments import build_multimodal_content
from app.core.url_validation import is_canonical_url
from app.core.discovery import (
    detect_reasoning_capability,
    discover_models,
    resolve_lmstudio_reasoning_capability,
    DiscoveryError,
)
from app.core.model_validation import build_exact_test_result

logger = logging.getLogger(__name__)


class GenerationError(Exception):
    """Raised when generation cannot proceed (e.g. missing API key for custom URL)."""


def _resolve_api_key(
    preset: "ModelPreset",
    env_var: str,
) -> str | None:
    """Return the effective API key for *preset*.

    Priority:
    1. Per-preset encrypted key (always used when present).
    2. Server environment variable — **only** if the preset's ``base_url``
       points to the provider's canonical endpoint (or is ``None``).
    3. ``None`` if neither is available.

    Raises ``GenerationError`` when a custom (non-canonical) base_url is set
    and the preset has no stored API key, which would otherwise cause the
    server's own key to be sent to an untrusted endpoint.
    """
    decrypted = decrypt_api_key(preset.api_key_encrypted) if preset.api_key_encrypted else None
    if decrypted:
        return decrypted

    if is_canonical_url(preset.provider, preset.base_url):
        return os.getenv(env_var)

    # Custom URL with no per-preset key → block to prevent key exfiltration.
    raise GenerationError(
        f"Model '{preset.name}' uses a custom base_url ({preset.base_url}) "
        f"but has no stored API key. Server environment keys are not sent to "
        f"non-canonical endpoints. Please add an API key to this model preset."
    )

# Ordered reasoning effort levels (lowest to highest) for clamping
_EFFORT_ORDER = ["low", "medium", "high", "xhigh"]


def _clamp_reasoning_effort(
    level: str,
    model_id: str,
    provider: str,
    supported_levels: Optional[List[str]] = None,
) -> str:
    """Clamp reasoning effort to the model's max supported level."""
    supported = supported_levels
    if supported is None:
        caps = detect_reasoning_capability(model_id, provider)
        supported = caps.get("reasoning_levels", [])
    if not supported or level in supported:
        return level
    # Find the highest supported level that doesn't exceed the requested one
    req_idx = _EFFORT_ORDER.index(level) if level in _EFFORT_ORDER else len(_EFFORT_ORDER)
    for lvl in reversed(_EFFORT_ORDER[:req_idx + 1]):
        if lvl in supported:
            logger.warning("Clamped reasoning_effort '%s' -> '%s' for %s", level, lvl, model_id)
            return lvl
    # Fallback: use the model's max supported level
    return supported[-1]


# Provider temperature configurations based on official documentation
# Range: (min, max) - determines semantic scaling
# Default: recommended default value (used as fallback when no model-specific default exists)
PROVIDER_TEMP_CONFIG = {
    ProviderType.openai: {"range": (0.0, 2.0), "default": 0.7},
    ProviderType.anthropic: {"range": (0.0, 1.0), "default": 1.0},  # Anthropic default is 1.0; locked at 1.0 for thinking
    ProviderType.google: {"range": (0.0, 2.0), "default": 1.0},
    ProviderType.grok: {"range": (0.0, 1.0), "default": 0.7},
    ProviderType.deepseek: {"range": (0.0, 2.0), "default": 1.0},
    ProviderType.mistral: {"range": (0.0, 2.0), "default": 0.7},
    ProviderType.glm: {"range": (0.0, 1.0), "default": 1.0},
    ProviderType.kimi: {"range": (0.0, 1.0), "default": 0.6},
    ProviderType.lmstudio: {"range": (0.0, 2.0), "default": 0.7},  # Fallback; prefer MODEL_TEMP_DEFAULTS
    ProviderType.openrouter: {"range": (0.0, 2.0), "default": 0.7},  # Fallback; prefer MODEL_TEMP_DEFAULTS
    ProviderType.ollama: {"range": (0.0, 2.0), "default": 0.7},
}

# Per-model recommended temperatures from official model cards / HuggingFace docs.
# Each entry: (model_id_substring, reasoning_temp, non_reasoning_temp)
# - reasoning_temp: used when preset.is_reasoning is True
# - non_reasoning_temp: used when preset.is_reasoning is False
# Matched in order; first match wins. Use lowercase substrings.
MODEL_TEMP_DEFAULTS: list[tuple[str, float, float]] = [
    # GPT-OSS (OpenAI open-source) — T=1.0 for all modes
    ("gpt-oss", 1.0, 1.0),
    # Kimi K2.5 — T=1.0 for reasoning and instant modes
    ("kimi-k2.5", 1.0, 1.0),
    # MiniMax M2.5 — T=1.0, P=0.95, K=40
    ("minimax-m2", 1.0, 1.0),
    ("minimax/minimax-m2", 1.0, 1.0),
    # Nemotron 3 Super — T=1.0 for all modes
    ("nemotron-3-super", 1.0, 1.0),
    ("nemotron-super", 1.0, 1.0),
    # Nemotron 3 Nano — T=1.0 reasoning ON, T=0.6 reasoning OFF
    ("nemotron-3-nano", 1.0, 0.6),
    ("nemotron-nano", 1.0, 0.6),
    # Qwen3.5 122B A10B — T=0.6 thinking, T=0.7 non-thinking
    ("qwen3.5-122b", 0.6, 0.7),
    # Qwen3.5 27B dense — T=1.0 thinking, T=0.7 non-thinking
    ("qwen3.5-27b", 1.0, 0.7),
    # Qwen3.5 35B A3B — T=1.0 thinking, T=0.7 non-thinking
    ("qwen3.5-35b", 1.0, 0.7),
    # Qwen3.5 397B (OpenRouter) — T=0.6 thinking, T=0.7 non-thinking
    ("qwen3.5-397b", 0.6, 0.7),
    # Qwen3 Next Thinking — T=0.6
    ("qwen3-next", 0.6, 0.7),
    # Qwen3 Coder — T=0.7 (instruct only, no thinking)
    ("qwen3-coder", 0.7, 0.7),
    # Qwen3 Max Thinking (OpenRouter) — T=0.6 thinking
    ("qwen3-max", 0.6, 0.7),
    # GLM-4.6V Flash — T=0.8 (vision model, unusual params)
    ("glm-4.6v", 0.8, 0.8),
    # GLM-4.7 / GLM-4.7 Flash — T=1.0
    ("glm-4.7", 1.0, 1.0),
    # GLM-5 (OpenRouter) — T=1.0 reasoning, T=0.7 general
    ("glm-5", 1.0, 0.7),
    # Seed 1.6 (ByteDance) — T=0.2 official default
    ("seed-1.6", 0.2, 0.2),
    # MiMo-V2-Flash (Xiaomi) — T=0.8 general, T=0.3 agentic
    ("mimo-v2", 0.8, 0.8),
    # Gemma 3 — T=1.0, P=0.95, K=64
    ("gemma-3", 1.0, 1.0),
    ("gemma3", 1.0, 1.0),
    # Phi-4-reasoning — T=0.8
    ("phi-4", 0.8, 0.8),
    # DeepSeek R1 distilled — T=0.6
    ("r1-distill", 0.6, 0.6),
    # QwQ — T=0.6
    ("qwq", 0.6, 0.6),
]


def get_model_recommended_temperature(model_id: str, is_reasoning: bool) -> Optional[float]:
    """Look up the officially recommended temperature for a model by matching model_id patterns."""
    model_lower = model_id.lower()
    for pattern, reasoning_temp, non_reasoning_temp in MODEL_TEMP_DEFAULTS:
        if pattern in model_lower:
            return reasoning_temp if is_reasoning else non_reasoning_temp
    return None


def normalize_temperature(base_temp: float, provider: ProviderType) -> float:
    """
    Normalize temperature to achieve semantically equivalent behavior across providers.

    Uses OpenAI's 0-2 range as the reference scale. A base_temp of 0.7 on this scale
    represents "moderate creativity" and is mapped to equivalent values on other scales.

    For providers with 0-1 range (Anthropic, Grok, GLM, Kimi):
        normalized = base_temp / 2  (so 0.7 -> 0.35)

    For providers with 0-2 range (OpenAI, Google, Mistral, LM Studio):
        normalized = base_temp (unchanged)
    """
    config = PROVIDER_TEMP_CONFIG.get(provider, {"range": (0.0, 2.0)})
    max_temp = config["range"][1]

    if max_temp <= 1.0:
        # Half-range providers: scale down to maintain semantic equivalence
        return min(base_temp / 2, max_temp)
    else:
        # Full-range providers: use as-is
        return min(base_temp, max_temp)


def get_provider_default_temperature(provider: ProviderType) -> float:
    """Get the recommended default temperature for a provider."""
    config = PROVIDER_TEMP_CONFIG.get(provider, {"default": 0.7})
    return config["default"]


def resolve_temperature(
    preset: ModelPreset,
    mode: TemperatureMode,
    base_temperature: float = 0.7
) -> float:
    """
    Resolve the effective temperature for a generation request.

    Priority: custom_temperature (user override) > model-specific default > provider default > normalized.

    Args:
        preset: Model preset with provider info and optional custom_temperature
        mode: Temperature mode (normalized, provider_default, custom)
        base_temperature: Base temperature value (used for normalized mode)

    Returns:
        The temperature value to use for the API request
    """
    if mode == TemperatureMode.custom:
        if preset.custom_temperature is not None:
            return preset.custom_temperature
        # Fallback to model-specific default, then normalized
        model_temp = get_model_recommended_temperature(preset.model_id, bool(preset.is_reasoning))
        if model_temp is not None:
            return model_temp
        return normalize_temperature(base_temperature, preset.provider)

    elif mode == TemperatureMode.provider_default:
        # Model-specific defaults take precedence over flat provider defaults
        model_temp = get_model_recommended_temperature(preset.model_id, bool(preset.is_reasoning))
        if model_temp is not None:
            return model_temp
        return get_provider_default_temperature(preset.provider)

    elif mode == TemperatureMode.normalized:
        return normalize_temperature(base_temperature, preset.provider)

    # Fallback
    return base_temperature


def strip_thinking_tags(content: str) -> dict:
    """
    Remove thinking/reasoning tags from model output.

    Handles two tag formats:
    A. Standard: <think>...</think>  (DeepSeek R1, QwQ, Nemotron, etc.)
    B. Pipe-delimited: <|think|>...<|end|>  (Solar Open 100B, etc.)

    For each format, handles:
    1. Paired tags - removes entire thinking block
    2. Orphaned closing tag - removes everything before it
    3. Orphaned opening tag - removes everything after it

    Returns:
        {
            "content": str - cleaned content,
            "raw_chars": int - character count before stripping,
            "answer_chars": int - character count after stripping
        }
    """
    if not content:
        return {"content": content or "", "raw_chars": 0, "answer_chars": 0}

    raw_chars = len(content)

    # === Format A: <think>...</think> ===

    # Remove paired <think>...</think> blocks
    cleaned = re.sub(r'<think>[\s\S]*?</think>\s*', ' ', content, flags=re.IGNORECASE)

    # Handle orphaned </think> closing tag - keep only content after the last one
    if '</think>' in cleaned.lower():
        parts = re.split(r'</think>\s*', cleaned, flags=re.IGNORECASE)
        cleaned = parts[-1] if parts else cleaned

    # Handle orphaned <think> opening tag - remove everything after it
    if '<think>' in cleaned.lower():
        parts = re.split(r'<think>[\s\S]*', cleaned, flags=re.IGNORECASE)
        cleaned = parts[0] if parts else cleaned

    # === Format B: <|think|>...<|end|> (Solar, etc.) ===

    # Remove paired <|think|>...<|end|> blocks (with optional role tags after <|end|>)
    cleaned = re.sub(r'<\|think\|>[\s\S]*?<\|end\|>\s*(?:<\|begin\|>assistant<\|content\|>\s*)?', ' ', cleaned, flags=re.IGNORECASE)

    # Handle orphaned <|end|> closing tag - keep only content after the last one
    if '<|end|>' in cleaned.lower():
        parts = re.split(r'<\|end\|>\s*(?:<\|begin\|>assistant<\|content\|>\s*)?', cleaned, flags=re.IGNORECASE)
        cleaned = parts[-1] if parts else cleaned

    # Handle orphaned <|think|> opening tag - remove everything after it
    if '<|think|>' in cleaned.lower():
        parts = re.split(r'<\|think\|>[\s\S]*', cleaned, flags=re.IGNORECASE)
        cleaned = parts[0] if parts else cleaned

    # Strip any remaining leaked tokenizer special tokens
    cleaned = re.sub(r'<\|(?:begin|end|content|im_start|im_end|eot_id)\|>', '', cleaned)

    # Clean up multiple spaces (but preserve newlines)
    cleaned = re.sub(r'[^\S\n]+', ' ', cleaned)  # Collapse spaces/tabs but not newlines
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)  # Max 2 consecutive newlines
    cleaned = cleaned.strip()

    return {"content": cleaned, "raw_chars": raw_chars, "answer_chars": len(cleaned)}


def extract_response_content(message: dict) -> dict:
    """
    Extract content from an OpenAI-compatible message, handling both:
    1. Separate reasoning fields (reasoning_content, reasoning) - GPT-OSS, DeepSeek R1, etc.
    2. Inline thinking tags (<think>, <|think|>) - Solar, QwQ via LM Studio, etc.

    Returns:
        {
            "content": str - cleaned answer text,
            "raw_chars": int - total chars (reasoning + answer),
            "answer_chars": int - answer-only chars
        }
    """
    content = message.get("content", "") or ""
    reasoning = message.get("reasoning_content", "") or message.get("reasoning", "") or ""

    if reasoning:
        # Model returned thinking in a separate field
        answer = content.strip() if content.strip() else reasoning.strip()
        raw_total = reasoning + content
        return {
            "content": answer,
            "raw_chars": len(raw_total),
            "answer_chars": len(answer)
        }
    else:
        # Check for inline thinking tags
        return strip_thinking_tags(content)


def _adjust_chars_from_reasoning_tokens(result: dict, data: dict):
    """
    For providers that hide reasoning content (OpenAI, Grok), adjust raw_chars
    using the reasoning_tokens count from usage so the frontend TokenBar shows
    the correct thinking/answer split.
    """
    usage = data.get("usage", {})
    completion_details = usage.get("completion_tokens_details", {})
    reasoning_tokens = completion_details.get("reasoning_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    if reasoning_tokens and completion_tokens and reasoning_tokens > 0:
        answer_tokens = completion_tokens - reasoning_tokens
        if answer_tokens > 0:
            answer_chars = result.get("answer_chars", 0) or 0
            # Guard against provider reports that leave effectively no answer tokens
            # for a large visible answer. Those values can explode raw_chars and
            # poison the aggregate TokenBar split.
            if answer_chars > 0 and (answer_chars / answer_tokens) > 20:
                return
            # Scale raw_chars so that raw/answer ratio matches token ratio
            result["raw_chars"] = int(answer_chars * completion_tokens / answer_tokens)


def _coerce_usage_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _store_usage(
    result: dict,
    *,
    input_tokens=None,
    output_tokens=None,
    total_tokens=None,
    cached_input_tokens=None,
    reasoning_tokens=None,
):
    input_value = _coerce_usage_int(input_tokens)
    output_value = _coerce_usage_int(output_tokens)
    total_value = _coerce_usage_int(total_tokens)
    cached_value = _coerce_usage_int(cached_input_tokens)
    reasoning_value = _coerce_usage_int(reasoning_tokens)

    if input_value is not None:
        result["input_tokens"] = input_value
    if output_value is not None:
        result["output_tokens"] = output_value
    if cached_value is not None:
        result["cached_input_tokens"] = cached_value
    if reasoning_value is not None:
        result["reasoning_tokens"] = reasoning_value

    if total_value is None and input_value is not None and output_value is not None:
        total_value = input_value + output_value
    if total_value is not None:
        result["tokens"] = total_value


def _store_openai_compatible_usage(result: dict, data: dict):
    usage = data.get("usage", {}) or {}
    prompt_details = usage.get("prompt_tokens_details", {}) or {}
    completion_details = usage.get("completion_tokens_details", {}) or {}
    _store_usage(
        result,
        input_tokens=usage.get("input_tokens", usage.get("prompt_tokens")),
        output_tokens=usage.get("output_tokens", usage.get("completion_tokens")),
        total_tokens=usage.get("total_tokens"),
        cached_input_tokens=usage.get("cached_input_tokens", prompt_details.get("cached_tokens")),
        reasoning_tokens=usage.get("reasoning_tokens", completion_details.get("reasoning_tokens")),
    )


def _store_anthropic_usage(result: dict, data: dict):
    usage = data.get("usage", {}) or {}
    _store_usage(
        result,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=None,
        cached_input_tokens=usage.get("cache_read_input_tokens"),
    )


def _store_google_usage(result: dict, data: dict):
    usage = data.get("usageMetadata", {}) or {}
    prompt_tokens = usage.get("promptTokenCount")
    candidate_tokens = usage.get("candidatesTokenCount")
    thought_tokens = usage.get("thoughtsTokenCount")
    output_tokens = None
    if candidate_tokens is not None:
        output_tokens = candidate_tokens + (thought_tokens or 0)
    _store_usage(
        result,
        input_tokens=prompt_tokens,
        output_tokens=output_tokens,
        total_tokens=usage.get("totalTokenCount"),
        cached_input_tokens=usage.get("cachedContentTokenCount"),
        reasoning_tokens=thought_tokens,
    )


def _normalize_lmstudio_format(raw_format: Optional[str]) -> Optional[str]:
    if raw_format == "safetensors":
        return "MLX"
    if raw_format == "gguf":
        return "GGUF"
    return None


def sync_lmstudio_preset_metadata(
    preset: ModelPreset,
    *,
    resolved_model_id: Optional[str] = None,
    probed_quant: Optional[str] = None,
    raw_format: Optional[str] = None,
    discovered_reasoning: Optional[bool] = None,
) -> bool:
    """Sync preset metadata to what LM Studio actually resolved at runtime."""
    changed = False

    if resolved_model_id and resolved_model_id != preset.model_id:
        preset.model_id = resolved_model_id
        changed = True

    if probed_quant and probed_quant != preset.quantization:
        preset.quantization = probed_quant
        changed = True

    fmt = _normalize_lmstudio_format(raw_format)
    if fmt and fmt != preset.model_format:
        preset.model_format = fmt
        changed = True

    if discovered_reasoning is not None and bool(preset.is_reasoning) != discovered_reasoning:
        preset.is_reasoning = 1 if discovered_reasoning else 0
        if not discovered_reasoning:
            preset.reasoning_level = None
        changed = True

    return changed


# Module-level state: tracks which model WE loaded on each server
# Key = "host:port", Value = model_id we last loaded there
_server_loaded_model: Dict[str, str] = {}


async def _probe_and_update_quant(client: httpx.AsyncClient, api_base: str, server: str, model_id: str):
    """Probe actual quant of a loaded model via v0 chat completion and update the DB preset."""
    try:
        resp = await client.post(
            f"{api_base}/api/v0/chat/completions",
            json={"model": model_id, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
            timeout=15.0,
        )
        if resp.status_code != 200:
            return
        data = resp.json()
        model_info = data.get("model_info", {})
        probed_quant = model_info.get("quant")
        resolved_model_id = data.get("model")
        raw_format = model_info.get("format")
        if not probed_quant and not resolved_model_id:
            return

        # Update preset in DB if quant differs
        from app.db.database import SessionLocal
        from app.db.models import ModelPreset
        db = SessionLocal()
        try:
            presets = db.query(ModelPreset).filter(
                ModelPreset.model_id == model_id,
                ModelPreset.base_url.like(f"%{server}%"),
            ).all()
            for p in presets:
                before_model_id = p.model_id
                before_quant = p.quantization
                changed = sync_lmstudio_preset_metadata(
                    p,
                    resolved_model_id=resolved_model_id,
                    probed_quant=probed_quant,
                    raw_format=raw_format,
                )
                if changed:
                    print(
                        f"[LM Studio {server}] Metadata fix: {p.name} "
                        f"model_id={before_model_id}→{p.model_id} quant={before_quant}→{p.quantization}"
                    )
                    db.commit()
        finally:
            db.close()
    except Exception:
        pass  # Non-critical — don't break model loading


async def _list_loaded_instance_ids(client: httpx.AsyncClient, api_base: str) -> set[str]:
    """Return the set of instance_ids currently loaded on the LM Studio server.

    NOTE: With LM Link active, this returns models from ALL clustered servers,
    not just the one we hit. We still use it for "model X gone" verification
    because if X is gone cluster-wide, it's definitely gone locally too.
    """
    resp = await client.get(f"{api_base}/api/v1/models")
    resp.raise_for_status()
    out: set[str] = set()
    for m in resp.json().get("models", []):
        for inst in m.get("loaded_instances") or []:
            iid = inst.get("id")
            if iid:
                out.add(iid)
    return out


async def _unload_instance(
    client: httpx.AsyncClient, api_base: str, server: str, instance_id: str
) -> bool:
    """Unload a specific instance and verify it's actually gone.

    Returns True if the instance is no longer loaded after the call.
    Raises RuntimeError on unexpected failures (so the caller can abort
    instead of triggering a JIT load on top of stale memory).

    Treats 404 ("not loaded") as success — the model is already gone.
    """
    try:
        resp = await client.post(
            f"{api_base}/api/v1/models/unload",
            json={"instance_id": instance_id},
        )
    except httpx.RequestError as e:
        raise RuntimeError(
            f"[LM Studio {server}] Network error unloading '{instance_id}': {e}"
        ) from e

    if resp.status_code == 404:
        # Already not loaded — fine
        print(f"[LM Studio {server}] '{instance_id}' was not loaded (404, treating as unloaded)")
    elif 200 <= resp.status_code < 300:
        pass  # Success path; verify below
    else:
        body = resp.text[:300]
        raise RuntimeError(
            f"[LM Studio {server}] Unload '{instance_id}' failed: HTTP {resp.status_code} {body}"
        )

    # Verify the model is actually gone before claiming success.
    # LM Studio sometimes accepts the unload but takes a moment to free memory.
    # Poll for up to 30s — long enough to free a 50GB MLX/GGUF model.
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            loaded = await _list_loaded_instance_ids(client, api_base)
        except Exception as e:
            print(f"[LM Studio {server}] Verify-unload list call failed: {e}")
            await asyncio.sleep(0.5)
            continue
        if instance_id not in loaded:
            print(f"[LM Studio {server}] Verified '{instance_id}' unloaded")
            return True
        await asyncio.sleep(0.5)

    raise RuntimeError(
        f"[LM Studio {server}] Unload '{instance_id}' returned OK but instance "
        f"is still listed as loaded after 30s — refusing to load next model on top of it"
    )


async def _evict_external_models(
    client: httpx.AsyncClient,
    api_base: str,
    server: str,
    target_model_id: str,
) -> None:
    """Unload any model on the cluster that bellmark did not load itself.

    'Owned by bellmark' = either the current load target, or something this
    process tracked loading on any server (``_server_loaded_model.values()``).
    Anything else — manual ``lms load``, LM Studio GUI loads, third-party
    clients — is considered external and gets evicted before we trigger the
    next JIT load. Without this, the new model would stack on top of stale
    server state and risk OOM (the same shape as the Run 113 incident).

    With LM Link clustering, ``/api/v1/models`` returns instances from every
    connected server. We send the unload via this server's API and trust
    LM Link to route it to whichever host actually holds the instance.
    Cross-server blast radius is intentional here: a clean slate is more
    valuable than preserving someone else's manually-loaded model.

    Raises RuntimeError if any external model could not be evicted, so the
    caller aborts instead of loading on top of unknown state.
    """
    try:
        loaded = await _list_loaded_instance_ids(client, api_base)
    except Exception as e:
        # Don't block the run on a failed scan — log and proceed.
        print(f"[LM Studio {server}] External-model scan failed (skipping eviction): {e}")
        return

    bellmark_owned = set(_server_loaded_model.values()) | {target_model_id}
    external = sorted(loaded - bellmark_owned)

    if not external:
        return

    print(
        f"[LM Studio {server}] Found {len(external)} externally-loaded model(s) "
        f"not tracked by bellmark: {external} — evicting cluster-wide via LM Link"
    )

    failed: list[str] = []
    for ext_id in external:
        try:
            await _unload_instance(client, api_base, server, ext_id)
        except RuntimeError as e:
            print(f"[LM Studio {server}] Failed to evict external '{ext_id}': {e}")
            failed.append(ext_id)

    if failed:
        raise RuntimeError(
            f"[LM Studio {server}] Could not evict external model(s) {failed} — "
            f"refusing to load '{target_model_id}' on top of unknown server state. "
            f"Manually unload them ('lms unload <id>') and retry."
        )

    # Brief settle so the kernel can reclaim freed pages before the next load.
    await asyncio.sleep(2.0)


async def ensure_lmstudio_model(base_url: str, model_id: str):
    """Ensure only the needed model is loaded, unloading the previous one first.

    LM Link routes /api/v1/models/unload to whichever server has the model,
    so cross-server unload works correctly. We use self-tracking to know what
    bellmark itself loaded, plus an aggressive eviction pass that catches
    models loaded by anything else (manual `lms load`, LM Studio GUI, other
    clients on the cluster).

    Strategy:
    1. If we already loaded this model (tracked), skip
    2. Unload the previously tracked model and VERIFY it's gone before continuing
       (otherwise JIT-loading the next big model on top of stale memory can OOM
       the whole machine — see Run 113 / 2026-04-07 incident)
    3. On cold start (no tracking), unload the target model_id as safety
       (prevents ":2" duplicate if it was already loaded from before restart)
    4. Evict any externally-loaded models that bellmark doesn't own — anything
       not in ``_server_loaded_model.values()`` and not the target. Aborts
       loudly if eviction fails so we never load on top of unknown state.
    5. JIT loads the target model on the first generate() call
    """
    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    server = parsed.netloc
    api_base = f"{parsed.scheme}://{parsed.netloc}"

    current = _server_loaded_model.get(server)

    if current == model_id:
        print(f"[LM Studio {server}] '{model_id}' already active (skipping)")
        return

    # Connectivity check — retry on transient failures.
    # LM Link cluster routing occasionally throws a 500 mid-request when
    # multiple clients hit the cluster simultaneously (observed during
    # parallel cachy/mini model switches in Run 113). One bad poll should
    # not kill an entire model's worth of generation work, so we retry
    # with backoff before giving up.
    last_err: Optional[Exception] = None
    for attempt, delay in enumerate((0.0, 1.0, 2.0, 4.0), start=1):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{api_base}/api/v1/models")
                resp.raise_for_status()
            last_err = None
            break
        except Exception as e:
            last_err = e
            print(
                f"[LM Studio {server}] Connectivity check attempt {attempt}/4 failed: {e}"
            )
    if last_err is not None:
        print(f"[LM Studio {server}] Server unreachable after retries: {last_err}")
        raise RuntimeError(f"LM Studio server unreachable at {server}: {last_err}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        if current:
            # Warm state: unload what we previously loaded and verify it's gone
            print(f"[LM Studio {server}] Unloading '{current}' before '{model_id}'")
            await _unload_instance(client, api_base, server, current)
            # Brief settle so the kernel can reclaim freed pages before JIT load
            await asyncio.sleep(2.0)
        else:
            # Cold start: unload target model_id to prevent duplicate on load
            print(f"[LM Studio {server}] Cold start — clearing '{model_id}' if loaded")
            try:
                await _unload_instance(client, api_base, server, model_id)
            except RuntimeError as e:
                # Cold-start clearing is best-effort. If the target wasn't loaded
                # we'll get a 404 (handled inside). If something else went wrong
                # we still want to proceed — log and continue.
                print(f"[LM Studio {server}] Cold-start clear non-fatal: {e}")
            await asyncio.sleep(1.0)

        # Defense in depth: evict any model bellmark didn't load itself
        # (manual `lms load`, LM Studio GUI, other clients on the cluster).
        # This is the only protection against stacking the next JIT load on
        # top of an externally-loaded model that bellmark has no record of.
        await _evict_external_models(client, api_base, server, model_id)

    print(f"[LM Studio {server}] Ready for '{model_id}' (JIT will load on first request)")
    _server_loaded_model[server] = model_id


async def generate(
    preset: ModelPreset,
    system_prompt: str,
    user_prompt: str,
    timeout: float = 300.0,
    temperature: float = 0.8,
    attachments: Optional[List[Dict[str, Any]]] = None,  # [{storage_path, mime_type, filename}]
    json_mode: bool = False  # Request JSON output (adds responseMimeType for Google, etc.)
) -> dict:
    # Extended timeouts for heavy workloads
    if preset.provider == ProviderType.lmstudio:
        timeout = 1800.0  # 30 minutes for local models
    elif preset.is_reasoning:
        timeout = 1800.0  # 30 minutes for reasoning models
    """
    Generate content from any supported LLM provider.

    If attachments are provided, builds multimodal content appropriate
    for the provider.

    Returns:
        {
            "success": bool,
            "content": str (if success),
            "tokens": int (if available),
            "error": str (if failed)
        }
    """
    result = {"success": False}

    # Build content (text or multimodal)
    if attachments:
        user_content, estimated_tokens = build_multimodal_content(
            user_prompt,
            attachments,
            preset.provider.value,
            preset.supports_vision if hasattr(preset, 'supports_vision') else None
        )
    else:
        user_content = user_prompt
        estimated_tokens = len(user_prompt) // 4

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            if preset.provider == ProviderType.anthropic:
                api_key = _resolve_api_key(preset, "ANTHROPIC_API_KEY")
                start = time.perf_counter()

                # Opus 4.6+ supports 128K output tokens
                max_tokens = 128000 if ("opus-4-6" in preset.model_id or "opus-4-7" in preset.model_id) else 64000

                request_json: dict = {
                    "model": preset.model_id,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_content}]
                }

                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                }

                # Add extended thinking for reasoning models
                if preset.is_reasoning and preset.reasoning_level:
                    is_opus_adaptive = any(tag in preset.model_id for tag in ("opus-4-6", "opus-4.6", "opus-4-7", "opus-4.7"))
                    is_sonnet_adaptive = any(tag in preset.model_id for tag in ("sonnet-4-6", "sonnet-4.6", "sonnet-4-7", "sonnet-4.7"))
                    if is_opus_adaptive or is_sonnet_adaptive:
                        # Claude 4.6+ models: use adaptive thinking (budget_tokens is deprecated).
                        # Effort is set via output_config, not inside the thinking object.
                        request_json["thinking"] = {"type": "adaptive"}
                        level = preset.reasoning_level.value
                        # Map our levels to Anthropic effort values (low/medium/high/max).
                        # "max" is Opus-only; "xhigh" maps to "high" for Anthropic.
                        effort_map = {"low": "low", "medium": "medium", "high": "high", "xhigh": "high", "max": "max"}
                        effort = effort_map.get(level, "high")
                        if effort == "max" and not is_opus_adaptive:
                            effort = "high"
                        request_json["output_config"] = {"effort": effort}
                    else:
                        # Older Claude models: use manual thinking with budget_tokens
                        budget_map = {"low": 4096, "medium": 16000, "high": 32000, "xhigh": 64000, "max": 100000}
                        request_json["thinking"] = {
                            "type": "enabled",
                            "budget_tokens": budget_map.get(preset.reasoning_level.value, 16000)
                        }
                    # Temperature must be 1 for extended thinking
                    request_json["temperature"] = 1
                else:
                    request_json["temperature"] = temperature

                response = await client.post(
                    preset.base_url,
                    headers=headers,
                    json=request_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True

                # Extract text + thinking content blocks
                # Accumulate all blocks (there may be multiple thinking/text blocks)
                text_parts = []
                thinking_parts = []
                for block in data.get("content", []):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "thinking":
                        thinking_parts.append(block.get("thinking", ""))
                    elif block.get("type") == "redacted_thinking":
                        # Redacted thinking: count data length as proxy for thinking chars
                        thinking_parts.append(block.get("data", ""))
                text_content = "\n\n".join(text_parts) if text_parts else ""
                thinking_content = "\n\n".join(thinking_parts) if thinking_parts else ""

                if thinking_content:
                    result["content"] = text_content.strip()
                    result["raw_chars"] = len(thinking_content + text_content)
                    result["answer_chars"] = len(text_content.strip())
                    # Store full content (thinking + answer) as fallback for JSON extraction
                    result["full_content"] = (thinking_content + "\n" + text_content).strip()
                    # Flag thinking-only responses (model spent all tokens reasoning, no answer)
                    if not text_content.strip():
                        result["thinking_only"] = True
                else:
                    stripped = strip_thinking_tags(text_content)
                    result["content"] = stripped["content"]
                    result["raw_chars"] = stripped["raw_chars"]
                    result["answer_chars"] = stripped["answer_chars"]
                _store_anthropic_usage(result, data)
                result["latency_ms"] = latency_ms

                # Adjust raw_chars using output_tokens for accurate thinking/answer split.
                # Content-block-based char counts are unreliable when thinking is redacted
                # (base64 encrypted data length ≠ actual thinking text length).
                if preset.is_reasoning:
                    output_tokens = data.get("usage", {}).get("output_tokens", 0)
                    answer_chars = result["answer_chars"]
                    if output_tokens > 0 and answer_chars > 0:
                        est_answer_tokens = answer_chars / 4
                        if output_tokens > est_answer_tokens * 1.3:
                            estimated_raw = int(answer_chars * output_tokens / est_answer_tokens)
                            # Use the larger of char-based vs token-based estimate
                            # (char-based is accurate for visible thinking, token-based for redacted)
                            if estimated_raw > result["raw_chars"]:
                                result["raw_chars"] = estimated_raw

            elif preset.provider == ProviderType.openai:
                api_key = _resolve_api_key(preset, "OPENAI_API_KEY")
                start = time.perf_counter()
                request_json: dict = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                }
                # Temperature support varies by model:
                # - o-series (o1, o3, o4): never support temperature
                # - gpt-5 / gpt-5-mini / gpt-5-nano / gpt-5-pro: never support temperature
                # - gpt-5.1, gpt-5.2: support temperature ONLY when not reasoning
                # - gpt-4o, gpt-4: always support temperature
                model_lower = preset.model_id.lower()
                is_o_series = bool(re.match(r'^o\d', model_lower))
                # gpt-5 base/mini/nano/pro are pre-5.1 models that never support temperature
                # gpt-5.x-chat-latest aliases also reject custom temperature
                is_gpt5_always_reasoning = (
                    'gpt-5' in model_lower
                    and '5.1' not in model_lower
                    and '5.2' not in model_lower
                )
                is_chat_latest = 'chat-latest' in model_lower
                skip_temp = preset.is_reasoning or is_o_series or is_gpt5_always_reasoning or is_chat_latest
                if not skip_temp:
                    request_json["temperature"] = temperature
                # Add reasoning effort for reasoning models
                # Chat Completions API uses top-level "reasoning_effort" for ALL models
                if preset.is_reasoning and preset.reasoning_level:
                    level = preset.reasoning_level.value
                    # OpenAI doesn't have "max" — map to "xhigh"
                    if level == "max":
                        level = "xhigh"
                    level = _clamp_reasoning_effort(level, preset.model_id, "openai")
                    request_json["reasoning_effort"] = level
                response = await client.post(
                    preset.base_url,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True
                extracted = extract_response_content(data["choices"][0]["message"])
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")

                # OpenAI hides reasoning content but reports reasoning_tokens in usage
                _adjust_chars_from_reasoning_tokens(result, data)

                # Fallback: if reasoning model but _adjust_chars didn't help
                # (no reasoning_tokens in response), estimate from completion_tokens
                if preset.is_reasoning and result["raw_chars"] == result["answer_chars"]:
                    completion_tokens = data.get("usage", {}).get("completion_tokens", 0)
                    answer_chars = result["answer_chars"]
                    if completion_tokens > 0 and answer_chars > 0:
                        est_answer_tokens = answer_chars / 4
                        if completion_tokens > est_answer_tokens * 1.3:
                            result["raw_chars"] = int(answer_chars * completion_tokens / est_answer_tokens)

            elif preset.provider == ProviderType.google:
                api_key = _resolve_api_key(preset, "GOOGLE_API_KEY")
                # Construct proper endpoint: base/models/{model_id}:generateContent
                google_url = f"https://generativelanguage.googleapis.com/v1beta/models/{preset.model_id}:generateContent"
                start = time.perf_counter()

                # Build Google-specific content (combine system prompt with user content)
                if isinstance(user_content, list):
                    # Multimodal content - prepend system prompt to first text part
                    google_parts = []
                    for i, part in enumerate(user_content):
                        if i == 0 and part.get("type") == "text":
                            google_parts.append({"text": f"{system_prompt}\n\n{part['text']}"})
                        elif part.get("type") == "text":
                            google_parts.append({"text": part["text"]})
                        elif part.get("type") == "image_url":
                            # Extract base64 data from data URL
                            url = part["image_url"]
                            if url.startswith("data:"):
                                # Format: data:image/png;base64,<data>
                                parts = url.split(",", 1)
                                if len(parts) == 2:
                                    mime_type = parts[0].split(":")[1].split(";")[0]
                                    google_parts.append({
                                        "inline_data": {
                                            "mime_type": mime_type,
                                            "data": parts[1]
                                        }
                                    })
                else:
                    # Text-only content
                    google_parts = [{"text": f"{system_prompt}\n\n{user_content}"}]

                generation_config: dict = {"temperature": temperature, "maxOutputTokens": 8192}

                # Add thinking config for Gemini reasoning models (inside generationConfig)
                if preset.is_reasoning and preset.reasoning_level:
                    # Detect Gemini major version from model_id
                    _m = re.search(r'gemini-(\d+)', preset.model_id)
                    gemini_major = int(_m.group(1)) if _m else 2

                    thinking_config: dict = {"includeThoughts": True}

                    if gemini_major >= 3:
                        # Gemini 3.x uses thinkingLevel (string)
                        level_map = {"low": "low", "medium": "medium", "high": "high"}
                        thinking_config["thinkingLevel"] = level_map.get(preset.reasoning_level.value, "medium")
                        generation_config["maxOutputTokens"] = 16384
                    else:
                        # Gemini 2.5 uses thinkingBudget (integer token count)
                        budget_map = {"low": 1024, "medium": 4096, "high": 16384}
                        thinking_budget = budget_map.get(preset.reasoning_level.value, 4096)
                        thinking_config["thinkingBudget"] = thinking_budget
                        generation_config["maxOutputTokens"] = thinking_budget + 8192

                    generation_config["thinkingConfig"] = thinking_config

                # Request JSON output when json_mode is enabled
                # Gemini 2.5+ and 3.x support responseMimeType alongside thinkingConfig
                if json_mode:
                    generation_config["responseMimeType"] = "application/json"

                request_body: dict = {
                    "contents": [
                        {"role": "user", "parts": google_parts}
                    ],
                    "generationConfig": generation_config
                }
                response = await client.post(
                    f"{google_url}?key={api_key}",
                    headers={"Content-Type": "application/json"},
                    json=request_body
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True

                # Check for blocked/empty candidates
                candidates = data.get("candidates", [])
                if not candidates:
                    block_reason = data.get("promptFeedback", {}).get("blockReason", "unknown")
                    result["success"] = False
                    result["error"] = f"Gemini returned no candidates (blockReason: {block_reason})"
                    logger.error(f"Gemini no candidates: {json.dumps(data)[:1000]}")
                    return result

                finish_reason = candidates[0].get("finishReason", "")
                if finish_reason not in ("STOP", "MAX_TOKENS", ""):
                    logger.warning(f"Gemini finishReason: {finish_reason}")

                # Gemini thinking models return multiple parts:
                # [{"thought": true, "text": "..."}, {"text": "..."}]
                parts = candidates[0].get("content", {}).get("parts", [])
                thinking_text = ""
                answer_text = ""
                for part in parts:
                    if part.get("thought"):
                        thinking_text += part.get("text", "")
                    else:
                        answer_text += part.get("text", "")

                if thinking_text:
                    result["content"] = answer_text.strip()
                    result["raw_chars"] = len(thinking_text + answer_text)
                    result["answer_chars"] = len(answer_text.strip())
                    # Store full content (thinking + answer) as fallback for JSON extraction
                    result["full_content"] = (thinking_text + "\n" + answer_text).strip()
                    # Flag thinking-only responses (model spent all tokens reasoning, no answer)
                    if not answer_text.strip():
                        result["thinking_only"] = True
                else:
                    # No thinking parts — fall back to tag stripping
                    stripped = strip_thinking_tags(answer_text)
                    result["content"] = stripped["content"]
                    result["raw_chars"] = stripped["raw_chars"]
                    result["answer_chars"] = stripped["answer_chars"]

                usage_meta = data.get("usageMetadata", {})
                _store_google_usage(result, data)

                # Fallback: if thought parts were absent but usageMetadata reports
                # thoughtsTokenCount, use the token ratio to infer the char split
                # (analogous to _adjust_chars_from_reasoning_tokens for OpenAI/Grok)
                # Use a tolerance of 200 chars to account for strip_thinking_tags whitespace
                char_diff = abs(result["raw_chars"] - result["answer_chars"])
                if not thinking_text and char_diff < 200:
                    thoughts_tokens = usage_meta.get("thoughtsTokenCount", 0)
                    candidates_tokens = usage_meta.get("candidatesTokenCount", 0)
                    if thoughts_tokens and candidates_tokens and thoughts_tokens > 0:
                        total_output = thoughts_tokens + candidates_tokens
                        result["raw_chars"] = int(result["answer_chars"] * total_output / candidates_tokens)
                result["latency_ms"] = latency_ms

            elif preset.provider == ProviderType.lmstudio:
                # Use /api/v0/chat/completions for richer response (model_info with quant)
                v0_url = preset.base_url.replace("/v1/chat/completions", "/api/v0/chat/completions")
                start = time.perf_counter()
                request_json = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": temperature,
                }
                lm_caps = resolve_lmstudio_reasoning_capability(
                    preset.model_id,
                    getattr(preset, "model_architecture", None),
                )
                levels = (
                    getattr(preset, "supported_reasoning_levels", None)
                    or lm_caps.get("supported_reasoning_levels")
                    or []
                )
                if preset.is_reasoning and preset.reasoning_level and levels:
                    level = preset.reasoning_level.value if hasattr(preset.reasoning_level, "value") else preset.reasoning_level
                    request_json["reasoning_effort"] = _clamp_reasoning_effort(
                        level,
                        preset.model_id,
                        "lmstudio",
                        supported_levels=levels,
                    )
                response = await client.post(
                    v0_url,
                    json=request_json,
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                message = data["choices"][0]["message"]
                extracted = extract_response_content(message)
                result["success"] = True
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")

                # Auto-fix metadata from what LM Studio actually resolved at runtime.
                model_info = data.get("model_info", {})
                try:
                    from app.db.database import SessionLocal as _SL
                    _db = _SL()
                    _p = _db.query(ModelPreset).filter(ModelPreset.id == preset.id).first()
                    if _p and sync_lmstudio_preset_metadata(
                        _p,
                        resolved_model_id=result["model_version"],
                        probed_quant=model_info.get("quant"),
                        raw_format=model_info.get("format"),
                    ):
                        print(f"[LM Studio sync] {_p.name}: model_id={preset.model_id} -> {_p.model_id}")
                        _db.commit()
                    _db.close()
                except Exception:
                    pass

            elif preset.provider == ProviderType.mistral:
                api_key = _resolve_api_key(preset, "MISTRAL_API_KEY")
                start = time.perf_counter()
                mistral_json = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": temperature
                }
                # Magistral reasoning models use prompt_mode parameter
                # prompt_mode: "reasoning" (default for magistral) or null (disable reasoning)
                if "magistral" in preset.model_id.lower():
                    if not preset.is_reasoning:
                        mistral_json["prompt_mode"] = None  # Disable reasoning
                    else:
                        mistral_json["max_tokens"] = 40960  # Required for reasoning to bound output
                response = await client.post(
                    preset.base_url or "https://api.mistral.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=mistral_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True
                extracted = extract_response_content(data["choices"][0]["message"])
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")

            elif preset.provider == ProviderType.deepseek:
                api_key = _resolve_api_key(preset, "DEEPSEEK_API_KEY")
                start = time.perf_counter()
                model_lower = preset.model_id.lower()
                is_reasoner_model = "deepseek-reasoner" in model_lower
                request_json = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ]
                }
                # Add thinking mode for reasoning models
                # NOTE: temperature, top_p, presence_penalty, frequency_penalty NOT supported in thinking mode
                if preset.is_reasoning or is_reasoner_model:
                    request_json["thinking"] = {"type": "enabled"}
                else:
                    request_json["temperature"] = temperature
                response = await client.post(
                    preset.base_url or "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True
                extracted = extract_response_content(data["choices"][0]["message"])
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")

            elif preset.provider == ProviderType.grok:
                api_key = _resolve_api_key(preset, "GROK_API_KEY")
                start = time.perf_counter()
                model_id = preset.model_id.lower()
                request_json = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ]
                }
                # Grok 4 always reasons at max capacity - no params supported
                # Grok 4.1 Fast uses reasoning: {enabled: true/false}
                # Grok 3 Mini uses reasoning_effort: "low" | "high"
                if "grok-4" in model_id and "4.1" not in model_id and "4-1" not in model_id:
                    # Grok 4 - no temperature, no reasoning params (always max reasoning)
                    pass
                elif "4.1" in model_id or "4-1" in model_id:
                    # Grok 4.1 Fast - supports reasoning toggle and temperature
                    request_json["temperature"] = temperature
                    if preset.is_reasoning:
                        request_json["reasoning"] = {"enabled": True}
                elif "mini" in model_id:
                    # Grok 3 Mini - supports reasoning_effort
                    request_json["temperature"] = temperature
                    if preset.is_reasoning and preset.reasoning_level:
                        request_json["reasoning_effort"] = preset.reasoning_level.value
                else:
                    # Other Grok models (grok-3, etc.)
                    request_json["temperature"] = temperature
                response = await client.post(
                    preset.base_url or "https://api.x.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=request_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True
                extracted = extract_response_content(data["choices"][0]["message"])
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")
                # Grok 4/4.1 hide reasoning content but may report reasoning_tokens
                _adjust_chars_from_reasoning_tokens(result, data)

            elif preset.provider == ProviderType.glm:
                api_key = _resolve_api_key(preset, "GLM_API_KEY")
                start = time.perf_counter()
                glm_json = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": temperature
                }
                # GLM-4.7 supports thinking mode via thinking: {type: "enabled" | "disabled"}
                if preset.is_reasoning:
                    glm_json["thinking"] = {"type": "enabled"}
                response = await client.post(
                    preset.base_url or "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=glm_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True
                extracted = extract_response_content(data["choices"][0]["message"])
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")

            elif preset.provider == ProviderType.kimi:
                api_key = _resolve_api_key(preset, "KIMI_API_KEY")
                start = time.perf_counter()
                kimi_json = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ]
                }
                # Add thinking mode for reasoning models
                # Thinking mode recommends temperature=1.0, instant mode recommends 0.6
                if preset.is_reasoning:
                    kimi_json["thinking"] = {"type": "enabled"}
                    kimi_json["temperature"] = 1.0  # Required for thinking mode
                else:
                    kimi_json["thinking"] = {"type": "disabled"}
                    kimi_json["temperature"] = temperature
                response = await client.post(
                    preset.base_url or "https://api.moonshot.ai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json=kimi_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True
                extracted = extract_response_content(data["choices"][0]["message"])
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")
                _adjust_chars_from_reasoning_tokens(result, data)

            elif preset.provider == ProviderType.openrouter:
                api_key = _resolve_api_key(preset, "OPENROUTER_API_KEY")
                start = time.perf_counter()
                request_json = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": temperature
                }
                # OpenRouter routes to the underlying provider's reasoning implementation
                if preset.is_reasoning:
                    level = preset.reasoning_level.value if preset.reasoning_level else "high"
                    request_json["reasoning"] = {"effort": level}
                response = await client.post(
                    preset.base_url or "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://bellmark.ai",
                        "X-Title": "BeLLMark",
                    },
                    json=request_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                result["success"] = True
                extracted = extract_response_content(data["choices"][0]["message"])
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")
                _adjust_chars_from_reasoning_tokens(result, data)

            elif preset.provider == ProviderType.ollama:
                start = time.perf_counter()
                request_json = {
                    "model": preset.model_id,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": temperature
                }
                response = await client.post(
                    preset.base_url or "http://localhost:11434/v1/chat/completions",
                    json=request_json
                )
                response.raise_for_status()
                latency_ms = int((time.perf_counter() - start) * 1000)
                data = response.json()
                message = data["choices"][0]["message"]
                extracted = extract_response_content(message)
                result["success"] = True
                result["content"] = extracted["content"]
                result["raw_chars"] = extracted["raw_chars"]
                result["answer_chars"] = extracted["answer_chars"]
                _store_openai_compatible_usage(result, data)
                result["latency_ms"] = latency_ms
                result["model_version"] = data.get("model")

    except asyncio.CancelledError:
        raise  # Never swallow — let the runner handle DB state
    except httpx.TimeoutException:
        result["error"] = f"Request timed out after {timeout}s"
    except httpx.HTTPStatusError as e:
        result["error"] = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


async def test_connection(preset: ModelPreset) -> dict:
    """Test if a model preset can connect successfully with a minimal request."""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if preset.provider == ProviderType.lmstudio:
                try:
                    discovered = await discover_models(provider=preset.provider, base_url=preset.base_url)
                except DiscoveryError as exc:
                    return {
                        "ok": False,
                        "reachable": False,
                        "provider": preset.provider.value,
                        "base_url": preset.base_url,
                        "model_id": preset.model_id,
                        "error": str(exc),
                    }

                request_json = {
                    "model": preset.model_id,
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_tokens": 1,
                }
                lm_caps = resolve_lmstudio_reasoning_capability(
                    preset.model_id,
                    getattr(preset, "model_architecture", None),
                )
                levels = lm_caps.get("supported_reasoning_levels") or []
                if preset.is_reasoning and preset.reasoning_level and levels:
                    level = preset.reasoning_level.value if hasattr(preset.reasoning_level, "value") else preset.reasoning_level
                    request_json["reasoning_effort"] = _clamp_reasoning_effort(
                        level,
                        preset.model_id,
                        "lmstudio",
                        supported_levels=levels,
                    )

                v0_url = preset.base_url.replace("/v1/chat/completions", "/api/v0/chat/completions")
                try:
                    response = await client.post(v0_url, json=request_json)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    return build_exact_test_result(
                        preset,
                        {
                            "ok": False,
                            "reachable": True,
                            "error": str(exc),
                            "reasoning_supported_levels": levels or None,
                        },
                        discovered,
                    )

                data = response.json()
                return build_exact_test_result(
                    preset,
                    {
                        "ok": True,
                        "reachable": True,
                        "resolved_model_id": data.get("model"),
                        "model_info": data.get("model_info"),
                        "reasoning_supported_levels": levels or None,
                    },
                    discovered,
                )

            elif preset.provider == ProviderType.anthropic:
                key = _resolve_api_key(preset, "ANTHROPIC_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                # Make minimal request
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": preset.model_id,
                        "max_tokens": 5,
                        "messages": [{"role": "user", "content": "Hi"}]
                    }
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 401:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.openai:
                key = _resolve_api_key(preset, "OPENAI_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 401:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.google:
                key = _resolve_api_key(preset, "GOOGLE_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                response = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 400:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.mistral:
                key = _resolve_api_key(preset, "MISTRAL_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                response = await client.get(
                    "https://api.mistral.ai/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 401:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.deepseek:
                key = _resolve_api_key(preset, "DEEPSEEK_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                response = await client.get(
                    "https://api.deepseek.com/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 401:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.grok:
                key = _resolve_api_key(preset, "GROK_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                response = await client.get(
                    "https://api.x.ai/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 401:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.glm:
                key = _resolve_api_key(preset, "GLM_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                # GLM uses a minimal chat request for testing
                response = await client.post(
                    "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": preset.model_id or "glm-4-flash",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 5
                    }
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 401:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.kimi:
                key = _resolve_api_key(preset, "KIMI_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                response = await client.get(
                    "https://api.moonshot.ai/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 401:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.openrouter:
                key = _resolve_api_key(preset, "OPENROUTER_API_KEY")
                if not key:
                    return {"ok": False, "error": "No API key configured"}
                response = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {key}"}
                )
                if response.status_code == 200:
                    return {"ok": True}
                elif response.status_code == 401:
                    return {"ok": False, "error": "Invalid API key"}
                else:
                    return {"ok": False, "error": f"HTTP {response.status_code}"}

            elif preset.provider == ProviderType.ollama:
                try:
                    discovered = await discover_models(provider=preset.provider, base_url=preset.base_url)
                except DiscoveryError as exc:
                    return {
                        "ok": False,
                        "reachable": False,
                        "provider": preset.provider.value,
                        "base_url": preset.base_url,
                        "model_id": preset.model_id,
                        "error": str(exc),
                    }

                try:
                    response = await client.post(
                        preset.base_url,
                        json={
                            "model": preset.model_id,
                            "messages": [{"role": "user", "content": "Hi"}],
                            "max_tokens": 1,
                        },
                    )
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    return build_exact_test_result(
                        preset,
                        {"ok": False, "reachable": True, "error": str(exc)},
                        discovered,
                    )

                data = response.json()
                return build_exact_test_result(
                    preset,
                    {
                        "ok": True,
                        "reachable": True,
                        "resolved_model_id": data.get("model"),
                        "model_info": {"model": data.get("model")},
                    },
                    discovered,
                )

    except GenerationError as e:
        return {"ok": False, "error": str(e)}
    except ValueError as e:
        return {"ok": False, "error": f"API key decryption failed: {e}"}
    except httpx.TimeoutException:
        return {"ok": False, "error": "Connection timed out"}
    except httpx.ConnectError:
        return {"ok": False, "error": "Could not connect to server"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": False, "error": "Unknown provider"}
