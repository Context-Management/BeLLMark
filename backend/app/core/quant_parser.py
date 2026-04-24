"""Parse quantization, format, and source metadata from model IDs."""
import re
from typing import Optional


# Quantization patterns in priority order
_QUANT_PATTERNS = [
    # GGUF standard: Q4_K_M, Q8_0, Q6_K, IQ4_XS
    (re.compile(r'((?:I?Q\d+_K_[SML]|I?Q\d+_K|I?Q\d+_\d|IQ\d+_[A-Z]+))'), None),
    # Bit-width: 4bit, 8bit, 3bit
    (re.compile(r'\b(\d+bit)\b'), None),
    # MLX trailing digit: -mlx-3 → 3bit
    (re.compile(r'-mlx-(\d+)(?:\b|$)'), lambda m: f"{m.group(1)}bit"),
    # Mixed/full precision
    (re.compile(r'\b(MXFP4|FP16|BF16|FP32)\b'), None),
    # GPTQ
    (re.compile(r'(GPTQ-Int\d)'), None),
    # AWQ
    (re.compile(r'\b(AWQ)\b'), None),
    # EXL2: exl2-4.0bpw → EXL2 4.0bpw
    (re.compile(r'(exl2-[\d.]+bpw)', re.IGNORECASE), lambda m: m.group(1).replace("exl2-", "EXL2 ").replace("Exl2-", "EXL2 ")),
]


def parse_quantization(model_id: str, *, explicit_quant: Optional[str] = None) -> Optional[str]:
    """Extract quantization string from a model ID.

    Args:
        model_id: The full model identifier (e.g. "mlx-community/qwen3.5-27b-4bit")
        explicit_quant: Explicit quant from provider (e.g. Ollama's quantization_level)

    Returns:
        Normalized quantization string or None if not detected.
    """
    if explicit_quant:
        return explicit_quant

    for pattern, transform in _QUANT_PATTERNS:
        match = pattern.search(model_id)
        if match:
            if transform:
                return transform(match)
            return match.group(1)
    return None


def parse_model_format(
    model_id: str,
    *,
    source: Optional[str] = None,
    quantization: Optional[str] = None,
    is_ollama: bool = False,
) -> Optional[str]:
    """Detect model format from model ID, source, and quantization.

    Priority order (first match wins):
    1. MLX (from source name or model key)
    2. GGUF (from path)
    3. GGUF (lmstudio-community default)
    4. Derived from quant string (GPTQ, AWQ, EXL2)
    5. Ollama → GGUF
    6. None
    """
    source_lower = (source or "").lower()
    model_id_lower = model_id.lower()

    # Priority 1: MLX from source or key
    if "mlx" in source_lower or "-mlx" in model_id_lower:
        return "MLX"

    # Priority 2: GGUF from path
    if "gguf" in model_id_lower:
        return "GGUF"

    # Priority 3: lmstudio-community default
    if source_lower == "lmstudio-community":
        return "GGUF"

    # Priority 4: Derived from quant string
    if quantization:
        quant_upper = quantization.upper()
        if "GPTQ" in quant_upper:
            return "GPTQ"
        if quant_upper == "AWQ":
            return "AWQ"
        if "EXL2" in quant_upper:
            return "EXL2"

    # Priority 5: Ollama is always GGUF
    if is_ollama:
        return "GGUF"

    return None


def parse_model_source(model_id: str, *, is_ollama: bool = False) -> Optional[str]:
    """Extract publisher/source from model ID path.

    For LM Studio: first segment before "/" (e.g. "mlx-community/model" → "mlx-community")
    For Ollama: namespace before "/" or "ollama" for bare library models.
    """
    if is_ollama:
        if "/" in model_id:
            return model_id.split("/")[0]
        return "ollama"

    if "/" in model_id:
        return model_id.split("/")[0]

    return None
