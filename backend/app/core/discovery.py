# backend/app/core/discovery.py
"""
Dynamic model discovery — query provider APIs for available models
and detect reasoning/vision capabilities.
"""
import os
import re
import httpx
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any


class DiscoveryError(Exception):
    """Raised when model discovery fails with a user-facing message."""
    pass

from app.db.models import ProviderType
from app.core.pricing_sync import enrich_discovered_pricing
from app.core.quant_parser import parse_quantization, parse_model_format, parse_model_source

logger = logging.getLogger(__name__)


# --- Provider default base URLs ---
PROVIDER_LIST_URLS = {
    ProviderType.openai: "https://api.openai.com/v1/models",
    ProviderType.anthropic: "https://api.anthropic.com/v1/models",
    ProviderType.google: "https://generativelanguage.googleapis.com/v1beta/models",
    ProviderType.mistral: "https://api.mistral.ai/v1/models",
    ProviderType.deepseek: "https://api.deepseek.com/v1/models",
    ProviderType.grok: "https://api.x.ai/v1/models",
    ProviderType.kimi: "https://api.moonshot.ai/v1/models",
    ProviderType.openrouter: "https://openrouter.ai/api/v1/models",
}

PROVIDER_CHAT_URLS = {
    ProviderType.lmstudio: "http://localhost:1234/v1/chat/completions",
    ProviderType.openai: "https://api.openai.com/v1/chat/completions",
    ProviderType.anthropic: "https://api.anthropic.com/v1/messages",
    ProviderType.google: "https://generativelanguage.googleapis.com/v1beta/models",
    ProviderType.mistral: "https://api.mistral.ai/v1/chat/completions",
    ProviderType.deepseek: "https://api.deepseek.com/v1/chat/completions",
    ProviderType.grok: "https://api.x.ai/v1/chat/completions",
    ProviderType.glm: "https://open.bigmodel.cn/api/paas/v4/chat/completions",
    ProviderType.kimi: "https://api.moonshot.ai/v1/chat/completions",
    ProviderType.openrouter: "https://openrouter.ai/api/v1/chat/completions",
    ProviderType.ollama: "http://localhost:11434/v1/chat/completions",
}

# --- ENV key names per provider ---
PROVIDER_ENV_KEYS = {
    ProviderType.openai: "OPENAI_API_KEY",
    ProviderType.anthropic: "ANTHROPIC_API_KEY",
    ProviderType.google: "GOOGLE_API_KEY",
    ProviderType.mistral: "MISTRAL_API_KEY",
    ProviderType.deepseek: "DEEPSEEK_API_KEY",
    ProviderType.grok: "GROK_API_KEY",
    ProviderType.glm: "GLM_API_KEY",
    ProviderType.kimi: "KIMI_API_KEY",
    ProviderType.openrouter: "OPENROUTER_API_KEY",
}


def humanize_model_id(model_id: str) -> str:
    """Convert a model ID string into a human-friendly display name."""
    name = model_id

    # Strip date suffixes like -20250619
    name = re.sub(r'-\d{8}$', '', name)

    # Claude models: claude-opus-4-6 -> Claude Opus 4.6
    m = re.match(r'claude-(\w+)-(\d+)-(\d+)', name)
    if m:
        variant, major, minor = m.group(1), m.group(2), m.group(3)
        return f"Claude {variant.title()} {major}.{minor}"

    # Gemini models: gemini-2.5-pro -> Gemini 2.5 Pro
    m = re.match(r'gemini-(\d+\.\d+)-(.+)', name)
    if m:
        version, variant = m.group(1), m.group(2)
        variant_parts = variant.split('-')
        return f"Gemini {version} {' '.join(p.title() for p in variant_parts)}"

    # GPT models: gpt-4o -> GPT-4o
    if name.startswith('gpt-'):
        return 'GPT-' + name[4:]

    # OpenAI o-series: o3-mini -> o3-mini
    if re.match(r'^o\d', name):
        return name

    # DeepSeek
    if name.startswith('deepseek-'):
        return 'DeepSeek ' + ' '.join(p.title() for p in name.replace('deepseek-', '').split('-'))

    # Grok
    if name.startswith('grok-'):
        return 'Grok ' + name.replace('grok-', '')

    # Mistral / Magistral
    if name.startswith('mistral-') or name.startswith('magistral-'):
        return ' '.join(p.title() for p in name.split('-'))

    # Default: title case with dashes as spaces
    return ' '.join(p.title() for p in name.split('-'))


def detect_reasoning_capability(model_id: str, provider: str) -> Dict[str, Any]:
    """
    Detect if a model supports reasoning/thinking mode and which levels it supports.

    Returns: {
        "is_reasoning": bool,
        "reasoning_levels": list[str],  # all supported levels (empty if toggle-only)
        "reasoning_level": str|None,    # default/recommended level (backwards compat)
    }
    """
    mid = model_id.lower()

    if provider == "openai":
        # o1, o3, o4 series and gpt-5* support reasoning_effort
        if re.match(r'^o[134]', mid) or 'gpt-5' in mid:
            # gpt-5.3-chat-latest only supports up to "medium"
            if '5.3-chat' in mid:
                return {"is_reasoning": True, "reasoning_levels": ["low", "medium"], "reasoning_level": "medium"}
            return {"is_reasoning": True, "reasoning_levels": ["low", "medium", "high", "xhigh"], "reasoning_level": "high"}
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    elif provider == "anthropic":
        # All Claude 4+ models support extended thinking
        if 'opus-4-6' in mid or 'opus-4.6' in mid or 'opus-4-7' in mid or 'opus-4.7' in mid:
            # Opus 4.6/4.7: adaptive thinking with effort levels
            return {"is_reasoning": True, "reasoning_levels": ["low", "medium", "high", "max"], "reasoning_level": "high"}
        if 'opus' in mid:
            return {"is_reasoning": True, "reasoning_levels": ["low", "medium", "high", "xhigh", "max"], "reasoning_level": "high"}
        if 'sonnet-4' in mid or 'sonnet-4.5' in mid:
            return {"is_reasoning": True, "reasoning_levels": ["low", "medium", "high", "xhigh", "max"], "reasoning_level": "medium"}
        if 'haiku-4' in mid or 'haiku-4.5' in mid:
            return {"is_reasoning": True, "reasoning_levels": ["low", "medium", "high"], "reasoning_level": "low"}
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    elif provider == "google":
        # Gemini 2.5+ and 3.x support thinkingConfig with budget
        m = re.search(r'gemini-(\d+)\.?(\d*)', mid)
        if m:
            major = int(m.group(1))
            minor = int(m.group(2)) if m.group(2) else 0
            if major >= 3 or (major == 2 and minor >= 5):
                return {"is_reasoning": True, "reasoning_levels": ["low", "medium", "high"], "reasoning_level": "medium"}
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    elif provider == "deepseek":
        # V4 models and Reasoner support thinking toggle, no granular levels
        if 'v4' in mid or 'reasoner' in mid:
            return {"is_reasoning": True, "reasoning_levels": [], "reasoning_level": None}
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    elif provider == "grok":
        # Grok 4 / 4.1: toggle only (reasoning.enabled)
        if 'grok-4' in mid and '4.1' not in mid and '4-1' not in mid:
            return {"is_reasoning": True, "reasoning_levels": [], "reasoning_level": None}
        if '4.1' in mid or '4-1' in mid:
            return {"is_reasoning": True, "reasoning_levels": [], "reasoning_level": None}
        # Grok mini: supports reasoning_effort with levels
        if 'mini' in mid:
            return {"is_reasoning": True, "reasoning_levels": ["low", "medium", "high"], "reasoning_level": "high"}
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    elif provider == "mistral":
        if 'magistral' in mid:
            return {"is_reasoning": True, "reasoning_levels": [], "reasoning_level": None}
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    elif provider == "glm":
        if 'glm-4.7' in mid or 'glm-4-7' in mid:
            return {"is_reasoning": True, "reasoning_levels": [], "reasoning_level": None}
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    elif provider == "kimi":
        if 'k2.5' in mid or 'k2-5' in mid:
            return {"is_reasoning": True, "reasoning_levels": [], "reasoning_level": None}
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    elif provider == "openrouter":
        # Reasoning detection happens in discover_openrouter via supported_parameters
        return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}

    return {"is_reasoning": False, "reasoning_levels": [], "reasoning_level": None}


def _detect_vision(model_id: str, provider: str) -> Optional[bool]:
    """Detect vision support from model ID patterns and provider documentation.

    Returns True (confirmed vision), False (confirmed no vision), or None (unknown).
    """
    mid = model_id.lower()

    if provider == "openai":
        # Verified against developers.openai.com/docs/models/<model> (2026-03)
        # NO vision: gpt-3.5-turbo*, gpt-4 (base, not turbo), o1-mini, o1-preview, o3-mini
        if mid.startswith('gpt-3.5') or mid == 'gpt-4' or mid.startswith('gpt-4-0'):
            return False
        if any(mid.startswith(p) for p in ['o1-mini', 'o1-preview', 'o3-mini']):
            return False
        # YES vision: gpt-4-turbo, gpt-4.1*, gpt-4.5*, gpt-4o*, gpt-5*, o1, o1-pro, o3, o3-pro, o4-mini
        if any(p in mid for p in ['gpt-4-turbo', 'gpt-4.1', 'gpt-4.5', '4o', 'gpt-5']):
            return True
        if re.match(r'^o[134]', mid):
            return True
        return None

    if provider == "anthropic":
        if any(v in mid for v in ['opus', 'sonnet', 'haiku']):
            return True
        return None

    if provider == "google":
        if 'gemini' in mid:
            return True
        return None

    if provider == "grok":
        # Verified against docs.x.ai/developers/models (2026-03)
        # Vision: grok-2-vision-*, grok-4-1-*, grok-4-*-fast-*
        if 'vision' in mid:
            return True
        if 'grok-4-1' in mid:
            return True
        if 'grok-4' in mid and 'fast' in mid:
            return True
        # Text-only: grok-3*, grok-4-0709, grok-2 (non-vision), grok-code-*
        if any(p in mid for p in ['grok-3', 'grok-2', 'grok-code']):
            return False
        if 'grok-4' in mid:
            return False  # grok-4-0709 (base) is text-only
        return None

    if provider == "mistral":
        # Verified against docs.mistral.ai/getting-started/models (2026-03)
        # Vision: pixtral-*, mistral-large (3+), mistral-medium (3.1+),
        #         mistral-small (3.2+), ministral-* (3 series)
        if any(v in mid for v in ['pixtral', 'mistral-large', 'mistral-medium',
                                   'mistral-small', 'ministral']):
            return True
        # Text-only: codestral, magistral, devstral
        if any(v in mid for v in ['codestral', 'magistral', 'devstral']):
            return False
        return None

    if provider == "deepseek":
        # Verified against api-docs.deepseek.com (2026-03)
        # deepseek-chat and deepseek-reasoner are text-only;
        # DeepSeek-VL2 is only available on third-party platforms
        if 'vl' in mid or 'vision' in mid:
            return True
        return False

    if provider == "kimi":
        # Verified against platform.moonshot.ai (2026-03)
        # K2.5 has native vision (MoonViT-3D encoder); K2 is text-only
        if 'k2.5' in mid or 'k2-5' in mid:
            return True
        # K2 and moonshot-v1 are text-only
        if 'k2' in mid or 'moonshot' in mid:
            return False
        return None

    # Generic fallback for other providers
    if 'vision' in mid:
        return True
    return None


# Known VLM (Vision Language Model) families for name-based detection.
# Used as a fallback when LM Studio API metadata and model.yaml are unavailable
# (e.g. remote servers, older LM Studio versions, bare /v1/models endpoint).
# Each entry is matched as a substring against the lowercased model ID.
_VLM_FAMILIES = (
    # Major VLM architectures
    'llava',        # LLaVA, LLaVA-OneVision, BakLLaVA (substring catches all)
    'moondream',    # Moondream 1/2
    'internvl',     # InternVL, InternVL2
    'cogvlm',       # CogVLM, CogVLM2
    'pixtral',      # Mistral Pixtral 12B/Large
    'paligemma',    # Google PaliGemma
    'idefics',      # HuggingFace IDEFICS 2/3
    'molmo',        # Allen AI Molmo
    'fuyu',         # Adept Fuyu
    'florence',     # Microsoft Florence 2
    'bunny',        # Bunny VLM
    'ovis',         # AIDC Ovis
    'mantis',       # Mantis VLM
    # Compound model names (VLM indicator embedded in name)
    'minicpm-v',    # MiniCPM-V 2.5/2.6
    'qwen2-vl',     # Qwen2-VL series
    'qwen-vl',      # Qwen-VL (legacy)
    'deepseek-vl',  # DeepSeek-VL, DeepSeek-VL2
    'glm-4v',       # Zhipu GLM-4V
    'nvlm',         # NVIDIA NVLM
    # Generic patterns (high-confidence indicators)
    'vision',       # Any model with "vision" in the name (e.g. phi-3.5-vision)
)


def _load_lmstudio_model_yamls() -> Dict[str, Dict]:
    """Read model.yaml files from LM Studio hub for authoritative metadata.

    Returns dict keyed by model directory name (e.g. 'openai/gpt-oss-120b')
    with 'reasoning' and 'vision' booleans from metadataOverrides.
    """
    import yaml
    from pathlib import Path

    hub = Path.home() / ".lmstudio" / "hub" / "models"
    result = {}
    if not hub.exists():
        return result

    for yaml_path in hub.rglob("model.yaml"):
        try:
            with open(yaml_path) as f:
                doc = yaml.safe_load(f)
            overrides = doc.get("metadataOverrides", {})
            # Key: relative path from hub/models/ minus /model.yaml
            rel = yaml_path.relative_to(hub).parent
            result[str(rel)] = {
                "reasoning": overrides.get("reasoning"),
                "vision": overrides.get("vision"),
            }
        except Exception:
            continue
    return result


async def discover_lmstudio(base_url: str) -> List[Dict]:
    """Discover models from an LM Studio server.

    Priority chain:
    1. /api/v1/models (richest: display_name, capabilities, params)
    2. /api/v0/models (type, capabilities array, context length)
    3. /v1/models (bare OpenAI-compatible fallback)

    Reasoning/vision are enriched from model.yaml files on disk when available.
    """
    api_base = re.sub(r'/v1/.*$', '', base_url.rstrip('/'))
    yaml_meta = _load_lmstudio_model_yamls()

    async with httpx.AsyncClient(timeout=15.0) as client:
        # Try v1 native API (richest)
        try:
            resp = await client.get(f"{api_base}/api/v1/models")
            resp.raise_for_status()
            data = resp.json()
            if "models" in data:
                results = _parse_lmstudio_api_v1(data, api_base, yaml_meta)
                # LM Link causes duplicate entries (same key, different quants from remote servers).
                # Deduplicate by model_id, keeping first occurrence.
                seen = set()
                deduped = []
                for r in results:
                    if r["model_id"] not in seen:
                        seen.add(r["model_id"])
                        deduped.append(r)
                return deduped
        except (httpx.HTTPStatusError, KeyError):
            pass

        # Try v0 native API
        try:
            resp = await client.get(f"{api_base}/api/v0/models")
            resp.raise_for_status()
            data = resp.json()
            return _parse_lmstudio_v0(data, api_base, yaml_meta)
        except (httpx.HTTPStatusError, KeyError):
            pass

        # Fallback: OpenAI-compatible
        resp = await client.get(f"{api_base}/v1/models")
        resp.raise_for_status()
        data = resp.json()
        return _parse_lmstudio_v1(data, api_base, yaml_meta)


# Architectures known to always support reasoning (from LM Studio model.yaml data).
# These are model families where reasoning is inherent to the architecture,
# not dependent on a specific variant name.
def _canonical_architecture(arch: Optional[str]) -> Optional[str]:
    """Normalize LM Studio architecture names across providers and formats."""
    if not arch:
        return None
    return re.sub(r"[^a-z0-9]+", "-", arch.lower()).strip("-")


_REASONING_ARCHITECTURES = frozenset({
    'gpt-oss',          # OpenAI GPT-OSS family (GGUF + MLX may differ in separator)
    'qwen35',           # Qwen3.5/3.6 dense (GGUF arch tag)
    'qwen35moe',        # Qwen3.5 122B A10B family
    'qwen3-5',          # Qwen3.5 dense hybrids (27B, distilled variants)
    'qwen3-5-moe',      # Qwen3.5 MoE hybrids (35B A3B)
    'qwen3_5',          # Qwen3.5/3.6 dense (MLX arch tag)
    'minimax-m2',       # MiniMax M2.x family
    'glm4-moe-lite',    # GLM 4.7 Flash
    'nemotron-h',       # Nemotron 3 Nano
    'nemotron-h-moe',   # Nemotron 3 Super
})

# Name keywords that indicate reasoning when architecture alone is ambiguous
_REASONING_KEYWORDS = ('thinking', 'reasoner', 'reasoning', 'think', 'r1')


def _resolve_reasoning_details(
    model_id: str,
    yaml_meta: Dict[str, Dict],
    arch: Optional[str] = None,
) -> Dict[str, Optional[str] | bool]:
    """Resolve LM Studio reasoning support and its strongest signal."""
    # 1. model.yaml (authoritative, localhost only)
    for key, meta in yaml_meta.items():
        if meta.get("reasoning") is not None:
            if model_id == key or model_id.startswith(key + "/"):
                return {
                    "is_reasoning": bool(meta["reasoning"]),
                    "reasoning_detection_source": "model_yaml",
                }
            yaml_last = key.split("/")[-1]
            model_last = model_id.split("/")[-1] if "/" in model_id else model_id
            if yaml_last == model_last:
                return {
                    "is_reasoning": bool(meta["reasoning"]),
                    "reasoning_detection_source": "model_yaml",
                }

    # 2. Architecture (works for remote — from /api/v0 or /api/v1)
    arch_key = _canonical_architecture(arch)
    if arch_key and arch_key in _REASONING_ARCHITECTURES:
        return {"is_reasoning": True, "reasoning_detection_source": "api_architecture"}

    # 2b. Architectures where only base (non-instruct) variants reason
    mid = model_id.lower()
    if arch_key == "gemma4" and not mid.rstrip("/").endswith("-it"):
        return {"is_reasoning": True, "reasoning_detection_source": "api_architecture"}

    # 3. Name keyword fallback
    if any(kw in mid for kw in _REASONING_KEYWORDS):
        return {"is_reasoning": True, "reasoning_detection_source": "name_heuristic"}

    return {"is_reasoning": False, "reasoning_detection_source": None}


def _resolve_reasoning(model_id: str, yaml_meta: Dict[str, Dict],
                       arch: Optional[str] = None) -> bool:
    """Resolve reasoning capability.

    Priority: model.yaml → architecture → name keywords.
    model.yaml is only available for localhost; arch + keywords work for remote.
    """
    return bool(_resolve_reasoning_details(model_id, yaml_meta, arch).get("is_reasoning"))


def resolve_lmstudio_reasoning_capability(model_id: str, architecture: Optional[str]) -> Dict[str, Any]:
    """Compute LM Studio reasoning metadata from architecture/model identity."""
    arch_key = _canonical_architecture(architecture)
    if arch_key == "gpt-oss":
        return {
            "is_reasoning": True,
            "supported_reasoning_levels": ["low", "medium", "high", "xhigh"],
            "default_reasoning_level": "high",
            "reasoning_detection_source": "api_architecture",
        }
    if arch_key and arch_key in _REASONING_ARCHITECTURES:
        return {
            "is_reasoning": True,
            "supported_reasoning_levels": None,
            "default_reasoning_level": None,
            "reasoning_detection_source": "api_architecture",
        }
    mid = model_id.lower()
    if arch_key == "gemma4" and not mid.rstrip("/").endswith("-it"):
        return {
            "is_reasoning": True,
            "supported_reasoning_levels": None,
            "default_reasoning_level": None,
            "reasoning_detection_source": "api_architecture",
        }
    if any(kw in mid for kw in _REASONING_KEYWORDS):
        return {
            "is_reasoning": True,
            "supported_reasoning_levels": None,
            "default_reasoning_level": None,
            "reasoning_detection_source": "name_heuristic",
        }
    return {
        "is_reasoning": False,
        "supported_reasoning_levels": None,
        "default_reasoning_level": None,
        "reasoning_detection_source": None,
    }


def _looks_like_embedding_model(model_id: str) -> bool:
    mid = model_id.lower()
    return "embedding" in mid or "embed-" in mid or mid.startswith("text-embed")


def _resolve_vision(model_id: str, model_type: Optional[str], yaml_meta: Dict[str, Dict]) -> Optional[bool]:
    """Resolve vision capability for LM Studio models.

    Priority chain:
    1. API model_type == "vlm" (from /api/v1 or /api/v0)
    2. model.yaml metadataOverrides.vision (localhost only)
    3. Known VLM family matching against _VLM_FAMILIES registry
    """
    # 1. API metadata (most authoritative)
    if model_type == "vlm":
        return True

    # 2. model.yaml (authoritative, localhost only)
    for key, meta in yaml_meta.items():
        if meta.get("vision") is not None:
            yaml_last = key.split("/")[-1]
            model_last = model_id.split("/")[-1] if "/" in model_id else model_id
            if model_id == key or yaml_last == model_last:
                return meta["vision"] or None  # False → None (unknown)

    # 3. Known VLM family registry (works for remote servers)
    mid = model_id.lower()
    if any(family in mid for family in _VLM_FAMILIES):
        return True

    return None


def _parse_lmstudio_api_v1(data: dict, api_base: str, yaml_meta: Dict[str, Dict]) -> List[Dict]:
    """Parse /api/v1/models response (richest: display_name, capabilities object)."""
    results = []
    for m in data.get("models", []):
        model_id = m.get("key", "")
        if not model_id:
            continue
        model_type = m.get("type", "llm")
        if model_type in {"embedding", "embeddings"}:
            continue

        caps = m.get("capabilities", {})
        reasoning = _resolve_reasoning_details(model_id, yaml_meta, arch=m.get("architecture"))
        lm_caps = resolve_lmstudio_reasoning_capability(model_id, m.get("architecture"))
        # Prefer explicit API fields for quant/format/source; fall back to parsing model_id
        quant_obj = m.get("quantization")
        api_quant = quant_obj.get("name") if isinstance(quant_obj, dict) else (quant_obj if isinstance(quant_obj, str) else None)
        api_format = (m.get("format") or "").upper() or None  # "gguf" → "GGUF", "mlx" → "MLX"
        api_publisher = m.get("publisher") or None

        source = api_publisher or parse_model_source(model_id)
        quant = api_quant or parse_quantization(model_id)
        fmt = api_format or parse_model_format(model_id, source=source, quantization=quant)
        results.append({
            "model_id": model_id,
            "name": m.get("display_name") or humanize_model_id(model_id.split("/")[-1] if "/" in model_id else model_id),
            "is_reasoning": reasoning["is_reasoning"],
            "reasoning_level": None,
            "supports_vision": True if caps.get("vision") else _resolve_vision(model_id, model_type, yaml_meta),
            "context_limit": m.get("max_context_length"),
            "provider_default_url": f"{api_base}/v1/chat/completions",
            "quantization": quant,
            "model_format": fmt,
            "model_source": source,
            "parameter_count": m.get("params_string"),
            "quantization_bits": quant_obj.get("bits_per_weight") if isinstance(quant_obj, dict) else None,
            "selected_variant": m.get("selected_variant"),
            "model_architecture": m.get("architecture"),
            "supported_reasoning_levels": lm_caps.get("supported_reasoning_levels"),
            "reasoning_detection_source": lm_caps.get("reasoning_detection_source")
            or reasoning.get("reasoning_detection_source"),
        })
    return results


def _parse_lmstudio_v0(data: dict, api_base: str, yaml_meta: Dict[str, Dict]) -> List[Dict]:
    """Parse /api/v0/models response."""
    results = []
    for m in data.get("data", []):
        model_id = m.get("id", "")
        if not model_id:
            continue
        model_type = m.get("type", "llm")
        if model_type in {"embedding", "embeddings"}:
            continue

        short_id = model_id.split("/")[-1] if "/" in model_id else model_id
        reasoning = _resolve_reasoning_details(model_id, yaml_meta, arch=m.get("arch"))
        lm_caps = resolve_lmstudio_reasoning_capability(model_id, m.get("arch"))
        # v0 has quantization as string and compatibility_type for format
        api_quant = m.get("quantization") or None
        api_format = (m.get("compatibility_type") or "").upper() or None
        api_publisher = m.get("publisher") or None

        source = api_publisher or parse_model_source(model_id)
        quant = api_quant or parse_quantization(model_id)
        fmt = api_format or parse_model_format(model_id, source=source, quantization=quant)
        results.append({
            "model_id": model_id,
            "name": humanize_model_id(short_id),
            "is_reasoning": reasoning["is_reasoning"],
            "reasoning_level": None,
            "supports_vision": _resolve_vision(model_id, model_type, yaml_meta),
            "context_limit": m.get("max_context_length"),
            "provider_default_url": f"{api_base}/v1/chat/completions",
            "quantization": quant,
            "model_format": fmt,
            "model_source": source,
            "parameter_count": None,
            "quantization_bits": None,
            "selected_variant": None,
            "model_architecture": m.get("arch"),
            "supported_reasoning_levels": lm_caps.get("supported_reasoning_levels"),
            "reasoning_detection_source": lm_caps.get("reasoning_detection_source")
            or reasoning.get("reasoning_detection_source"),
        })
    return results


def _parse_lmstudio_v1(data: dict, api_base: str, yaml_meta: Dict[str, Dict]) -> List[Dict]:
    """Parse bare /v1/models response (OpenAI-compatible fallback)."""
    results = []
    for m in data.get("data", []):
        model_id = m.get("id", "")
        if not model_id:
            continue
        if _looks_like_embedding_model(model_id):
            continue
        short_id = model_id.split("/")[-1] if "/" in model_id else model_id
        source = parse_model_source(model_id)
        quant = parse_quantization(model_id)
        fmt = parse_model_format(model_id, source=source, quantization=quant)
        results.append({
            "model_id": model_id,
            "name": humanize_model_id(short_id),
            "is_reasoning": _resolve_reasoning(model_id, yaml_meta),
            "reasoning_level": None,
            "supports_vision": _resolve_vision(model_id, None, yaml_meta),
            "context_limit": None,
            "provider_default_url": f"{api_base}/v1/chat/completions",
            "quantization": quant,
            "model_format": fmt,
            "model_source": source,
            "parameter_count": None,
            "quantization_bits": None,
            "selected_variant": None,
            "model_architecture": None,
            "supported_reasoning_levels": None,
            "reasoning_detection_source": None,
        })
    return results


async def discover_openai_compatible(
    provider: ProviderType,
    api_key: Optional[str] = None,
) -> List[Dict]:
    """Discover models from OpenAI-compatible /v1/models endpoints."""
    list_url = PROVIDER_LIST_URLS.get(provider)
    if not list_url:
        return []

    env_key = PROVIDER_ENV_KEYS.get(provider)
    key = api_key or (os.getenv(env_key) if env_key else None)
    if not key:
        return []

    headers = {"Authorization": f"Bearer {key}"}
    if provider == ProviderType.anthropic:
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(list_url, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    raw_models = data.get("data", []) if "data" in data else data.get("models", [])

    results = []
    chat_url = PROVIDER_CHAT_URLS.get(provider, "")
    provider_str = provider.value

    for m in raw_models:
        model_id = m.get("id", "") if isinstance(m, dict) else str(m)
        if not model_id:
            continue

        # Provider-specific filtering
        if provider == ProviderType.openai:
            if not any(model_id.startswith(p) for p in ['gpt-', 'o1', 'o3', 'o4', 'chatgpt-']):
                continue

        reasoning = detect_reasoning_capability(model_id, provider_str)
        vision = _detect_vision(model_id, provider_str)

        # Base variant (non-reasoning)
        results.append({
            "model_id": model_id,
            "name": humanize_model_id(model_id),
            "is_reasoning": False,
            "reasoning_level": None,
            "supports_vision": vision,
            "context_limit": None,
            "provider_default_url": chat_url,
        })

        # If model supports reasoning, offer variants for each level
        if reasoning["is_reasoning"]:
            levels = reasoning["reasoning_levels"]
            if levels:
                # Multiple granular levels available
                for level in levels:
                    results.append({
                        "model_id": model_id,
                        "name": f"{humanize_model_id(model_id)} [Reasoning ({level})]",
                        "is_reasoning": True,
                        "reasoning_level": level,
                        "supports_vision": vision,
                        "context_limit": None,
                        "provider_default_url": chat_url,
                    })
            else:
                # Toggle-only reasoning (no granular levels)
                results.append({
                    "model_id": model_id,
                    "name": f"{humanize_model_id(model_id)} [Reasoning]",
                    "is_reasoning": True,
                    "reasoning_level": None,
                    "supports_vision": vision,
                    "context_limit": None,
                    "provider_default_url": chat_url,
                })

    return results


async def discover_google(api_key: Optional[str] = None) -> List[Dict]:
    """Discover models from Google's model list API."""
    key = api_key or os.getenv("GOOGLE_API_KEY")
    if not key:
        return []

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()

    results = []
    for m in data.get("models", []):
        # Google returns name like "models/gemini-2.5-pro"
        full_name = m.get("name", "")
        model_id = full_name.replace("models/", "")
        if not model_id:
            continue

        # Only include models that support generateContent
        methods = m.get("supportedGenerationMethods", [])
        if "generateContent" not in methods:
            continue

        reasoning = detect_reasoning_capability(model_id, "google")
        vision = _detect_vision(model_id, "google")

        results.append({
            "model_id": model_id,
            "name": humanize_model_id(model_id),
            "is_reasoning": False,
            "reasoning_level": None,
            "supports_vision": vision,
            "context_limit": m.get("inputTokenLimit"),
            "provider_default_url": "https://generativelanguage.googleapis.com/v1beta/models",
        })

        if reasoning["is_reasoning"]:
            levels = reasoning["reasoning_levels"]
            if levels:
                for level in levels:
                    results.append({
                        "model_id": model_id,
                        "name": f"{humanize_model_id(model_id)} [Thinking ({level})]",
                        "is_reasoning": True,
                        "reasoning_level": level,
                        "supports_vision": vision,
                        "context_limit": m.get("inputTokenLimit"),
                        "provider_default_url": "https://generativelanguage.googleapis.com/v1beta/models",
                    })
            else:
                results.append({
                    "model_id": model_id,
                    "name": f"{humanize_model_id(model_id)} [Thinking]",
                    "is_reasoning": True,
                    "reasoning_level": None,
                    "supports_vision": vision,
                    "context_limit": m.get("inputTokenLimit"),
                    "provider_default_url": "https://generativelanguage.googleapis.com/v1beta/models",
                })

    return results


# GLM has no model list API — provide hardcoded list
# Verified against docs.z.ai (2026-03)
# GLM-4.7 thinking is toggle-only (no granular levels)
GLM_MODELS = [
    {"model_id": "glm-4.7", "name": "GLM-4.7", "is_reasoning": False, "reasoning_level": None, "supports_vision": False, "context_limit": None},
    {"model_id": "glm-4.7", "name": "GLM-4.7 [Thinking]", "is_reasoning": True, "reasoning_level": None, "supports_vision": False, "context_limit": None},
    {"model_id": "glm-4.7-flash", "name": "GLM-4.7 Flash", "is_reasoning": False, "reasoning_level": None, "supports_vision": False, "context_limit": None},
    {"model_id": "glm-4.6v", "name": "GLM-4.6V", "is_reasoning": False, "reasoning_level": None, "supports_vision": True, "context_limit": 128000},
    {"model_id": "glm-4.6v-flash", "name": "GLM-4.6V Flash", "is_reasoning": False, "reasoning_level": None, "supports_vision": True, "context_limit": 128000},
    {"model_id": "glm-4.5v", "name": "GLM-4.5V", "is_reasoning": False, "reasoning_level": None, "supports_vision": True, "context_limit": None},
    {"model_id": "glm-4.5-flash", "name": "GLM-4.5 Flash", "is_reasoning": False, "reasoning_level": None, "supports_vision": False, "context_limit": None},
]


async def discover_openrouter(api_key: Optional[str] = None) -> List[Dict]:
    """Discover models from OpenRouter's /v1/models endpoint.

    OpenRouter returns rich metadata including per-token pricing,
    context lengths, and modality info. We convert per-token prices
    to per-1M-token format to match BeLLMark's pricing convention.
    price_input and price_output are included so they persist when
    the user imports discovered models.
    """
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        return []

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        resp.raise_for_status()
        data = resp.json()

    results = []
    chat_url = "https://openrouter.ai/api/v1/chat/completions"

    for m in data.get("data", []):
        model_id = m.get("id", "")
        if not model_id:
            continue

        name = m.get("name", model_id)
        ctx = m.get("context_length")

        # Parse pricing: OpenRouter returns per-token strings, convert to per-1M
        pricing = m.get("pricing", {})
        try:
            price_input = float(pricing.get("prompt", "0")) * 1_000_000
        except (ValueError, TypeError):
            price_input = 0.0
        try:
            price_output = float(pricing.get("completion", "0")) * 1_000_000
        except (ValueError, TypeError):
            price_output = 0.0

        # Detect vision from architecture modality
        arch = m.get("architecture", {})
        input_modalities = arch.get("input_modalities", [])
        supports_vision = True if "image" in input_modalities else None

        # Detect reasoning from supported_parameters
        supported_params = m.get("supported_parameters", [])
        is_reasoning = "reasoning" in supported_params

        results.append({
            "model_id": model_id,
            "name": name,
            "is_reasoning": False,
            "reasoning_level": None,
            "supports_vision": supports_vision,
            "context_limit": ctx,
            "provider_default_url": chat_url,
            "price_input": price_input,
            "price_output": price_output,
            "price_source": "openrouter_api",
            "price_source_url": "https://openrouter.ai/api/v1/models",
            "price_checked_at": datetime.now(timezone.utc),
            "price_currency": "USD",
        })

        # If model supports reasoning, add a reasoning variant
        if is_reasoning:
            results.append({
                "model_id": model_id,
                "name": f"{name} [Reasoning]",
                "is_reasoning": True,
                "reasoning_level": None,
                "supports_vision": supports_vision,
                "context_limit": ctx,
                "provider_default_url": chat_url,
                "price_input": price_input,
                "price_output": price_output,
                "price_source": "openrouter_api",
                "price_source_url": "https://openrouter.ai/api/v1/models",
                "price_checked_at": datetime.now(timezone.utc),
                "price_currency": "USD",
            })

    return results


async def discover_ollama(base_url: str) -> List[Dict]:
    """Discover models from Ollama's native /api/tags endpoint.

    Uses the native API instead of /v1/models because it returns richer
    metadata: parameter size, quantization level, model family.
    Supports remote Ollama hosts (e.g. cachy.local:11434).
    """
    api_base = base_url.rstrip("/").replace("/v1/chat/completions", "").replace("/v1", "")
    chat_url = f"{api_base}/v1/chat/completions"

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{api_base}/api/tags")
        resp.raise_for_status()
        data = resp.json()

    results = []
    for m in data.get("models", []):
        model_id = m.get("name", "")
        if not model_id:
            continue

        details = m.get("details", {})
        param_size = details.get("parameter_size", "")
        quant = details.get("quantization_level", "")
        family = details.get("family", "").lower()

        # Build descriptive name: "Llama3.1 70.6B Q4_K_M"
        base_name = model_id.split(":")[0]
        name_parts = [humanize_model_id(base_name)]
        if param_size:
            name_parts.append(param_size)
        if quant:
            name_parts.append(quant)
        display_name = " ".join(name_parts)

        # Vision detection from family name
        vision_families = {"llava", "bakllava", "moondream", "llama-vision", "minicpm-v"}
        supports_vision = True if family in vision_families or "vision" in model_id.lower() else None

        # Reasoning detection from model name
        mid = model_id.lower()
        is_reasoning = any(kw in mid for kw in ("thinking", "reasoner", "reasoning", "think", "r1"))

        source = parse_model_source(model_id, is_ollama=True)
        quant_parsed = parse_quantization(model_id, explicit_quant=quant or None)
        results.append({
            "model_id": model_id,
            "name": display_name,
            "is_reasoning": is_reasoning,
            "reasoning_level": None,
            "supports_vision": supports_vision,
            "context_limit": None,
            "provider_default_url": chat_url,
            "quantization": quant_parsed,
            "model_format": "GGUF",
            "model_source": source,
        })

    return results


async def discover_models(
    provider: ProviderType,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> List[Dict]:
    """
    Main entry point: discover available models for a provider.

    Returns list of DiscoveredModel-compatible dicts.
    """
    try:
        if provider == ProviderType.lmstudio:
            url = base_url or "http://localhost:1234"
            return enrich_discovered_pricing(provider, await discover_lmstudio(url))

        elif provider == ProviderType.google:
            return enrich_discovered_pricing(provider, await discover_google(api_key))

        elif provider == ProviderType.glm:
            chat_url = PROVIDER_CHAT_URLS[ProviderType.glm]
            return enrich_discovered_pricing(
                provider,
                [{**m, "provider_default_url": chat_url} for m in GLM_MODELS],
            )

        elif provider == ProviderType.openrouter:
            return enrich_discovered_pricing(provider, await discover_openrouter(api_key))

        elif provider == ProviderType.ollama:
            url = base_url or "http://localhost:11434"
            return enrich_discovered_pricing(provider, await discover_ollama(url))

        else:
            return enrich_discovered_pricing(provider, await discover_openai_compatible(provider, api_key))

    except httpx.TimeoutException:
        logger.warning(f"Timeout discovering models for {provider}")
        raise DiscoveryError(f"Connection timed out reaching {provider.value} server. Is it running?")
    except httpx.ConnectError as e:
        logger.warning(f"Connection error discovering models for {provider}: {e}")
        raise DiscoveryError(f"Cannot connect to {provider.value} server. Is it running and accessible?")
    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP error discovering models for {provider}: {e.response.status_code}")
        raise DiscoveryError(f"{provider.value} server returned HTTP {e.response.status_code}")
    except DiscoveryError:
        raise
    except Exception as e:
        logger.warning(f"Error discovering models for {provider}: {e}")
        raise DiscoveryError(f"Failed to discover {provider.value} models: {e}")
