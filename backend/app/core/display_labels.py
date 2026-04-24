"""Resolve unique display labels for model presets in a benchmark run."""
from collections import Counter
import re
from typing import Dict, List
from urllib.parse import urlparse


def _extract_host_label(base_url: str) -> str:
    """Extract short host label from base URL. e.g. 'http://cachy.local:1234/v1' → 'cachy'"""
    try:
        hostname = urlparse(base_url).hostname or ""
        # Strip .local suffix for brevity
        return hostname.replace(".local", "").split(".")[0] or hostname
    except Exception:
        return base_url


def _build_label(name: str, fmt: str, quant: str, host: str) -> str:
    """Build a display label: Name (FORMAT QUANT @ host)."""
    parts = []
    if fmt:
        parts.append(fmt)
    if quant:
        parts.append(quant)
    suffix = " ".join(parts)
    # Always include host — localhost/127.0.0.1 becomes "cachy" (this machine's name)
    host_label = host
    if host in ("localhost", "127.0.0", "127"):
        import socket
        host_label = socket.gethostname()
    if host_label:
        suffix = f"{suffix} @ {host_label}".strip() if suffix else f"@ {host_label}"
    if suffix:
        return f"{name} ({suffix})"
    return name


def _display_name(preset) -> str:
    """Decorate model names with reasoning markers when the preset is reasoning-capable."""
    name = preset.name
    if not getattr(preset, "is_reasoning", False):
        return name
    if re.search(r"(\[reasoning|\[thinking|\breasoning\b|\bthinking\b)", name, flags=re.IGNORECASE):
        return name
    level = getattr(preset, "reasoning_level", None)
    return f"{name} [Reasoning ({level})]" if level else f"{name} [Reasoning]"


def resolve_display_labels(presets: list) -> Dict[int, str]:
    """Map preset ID → unique display label for a set of presets.

    ALWAYS appends format/quant metadata when available.
    Adds host suffix only when needed to disambiguate same-name models.
    """
    if not presets:
        return {}

    labels: Dict[int, str] = {}
    for p in presets:
        name = _display_name(p)
        fmt = (p.model_format or "").upper()
        quant = p.quantization or ""
        host = _extract_host_label(p.base_url)

        # Include format + quant + host for local models (those with quant/format metadata)
        # Cloud models have no quant/format so they stay as bare names
        has_local_metadata = bool(fmt or quant)
        labels[p.id] = _build_label(name, fmt, quant, host if has_local_metadata else "")

    # Check for remaining collisions (same name + same quant + same format, different host)
    label_counts = Counter(labels.values())
    if any(c > 1 for c in label_counts.values()):
        for p in presets:
            if label_counts[labels[p.id]] > 1:
                fmt = (p.model_format or "").upper()
                quant = p.quantization or ""
                host = _extract_host_label(p.base_url)
                labels[p.id] = _build_label(_display_name(p), fmt, quant, host)

    # Final fallback: if still colliding, append preset ID
    label_counts = Counter(labels.values())
    if any(c > 1 for c in label_counts.values()):
        for p in presets:
            if label_counts[labels[p.id]] > 1:
                labels[p.id] = f"{labels[p.id]} #{p.id}"

    return labels
