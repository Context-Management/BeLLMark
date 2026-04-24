import pytest
from unittest.mock import MagicMock
from app.core.display_labels import resolve_display_labels


def _make_preset(
    id,
    name,
    quantization=None,
    model_format=None,
    model_source=None,
    base_url="http://localhost:1234/v1/chat/completions",
    is_reasoning=False,
    reasoning_level=None,
):
    """Create a mock ModelPreset."""
    p = MagicMock()
    p.id = id
    p.name = name
    p.quantization = quantization
    p.model_format = model_format
    p.model_source = model_source
    p.base_url = base_url
    p.is_reasoning = is_reasoning
    p.reasoning_level = reasoning_level
    return p


class TestResolveDisplayLabels:
    def test_cloud_models_no_metadata(self):
        """Cloud models with no quant/format get bare names."""
        presets = [
            _make_preset(1, "GPT-4o"),
            _make_preset(2, "Claude Opus 4.6"),
        ]
        result = resolve_display_labels(presets)
        assert result == {1: "GPT-4o", 2: "Claude Opus 4.6"}

    def test_always_shows_format_quant_and_host(self):
        """Every model with metadata gets format+quant+host label, even if unique."""
        import socket
        host = socket.gethostname()
        presets = [
            _make_preset(1, "GPT-OSS 120B", quantization="MXFP4", model_format="GGUF"),
            _make_preset(2, "Qwen3.5 27B", quantization="4bit", model_format="MLX"),
        ]
        result = resolve_display_labels(presets)
        assert result == {1: f"GPT-OSS 120B (GGUF MXFP4 @ {host})", 2: f"Qwen3.5 27B (MLX 4bit @ {host})"}

    def test_same_name_different_quant(self):
        """Same name, different quant — both get labels with host."""
        import socket
        host = socket.gethostname()
        presets = [
            _make_preset(1, "Qwen3.5 27B", quantization="4bit", model_format="MLX"),
            _make_preset(2, "Qwen3.5 27B", quantization="8bit", model_format="MLX"),
        ]
        result = resolve_display_labels(presets)
        assert result == {1: f"Qwen3.5 27B (MLX 4bit @ {host})", 2: f"Qwen3.5 27B (MLX 8bit @ {host})"}

    def test_same_name_same_quant_different_host(self):
        """Same name, same quant → host added to disambiguate."""
        presets = [
            _make_preset(1, "GPT-OSS 120B 3", quantization="3bit", model_format="MLX",
                         base_url="http://mini.local:1234/v1/chat/completions"),
            _make_preset(2, "GPT-OSS 120B 3", quantization="3bit", model_format="MLX",
                         base_url="http://workstation.local:1234/v1/chat/completions"),
        ]
        result = resolve_display_labels(presets)
        assert result == {
            1: "GPT-OSS 120B 3 (MLX 3bit @ mini)",
            2: "GPT-OSS 120B 3 (MLX 3bit @ workstation)",
        }

    def test_reasoning_preset_gets_reasoning_suffix_in_label(self):
        """Reasoning-capable local models should be labeled in benchmark displays."""
        import socket
        host = socket.gethostname()
        presets = [
            _make_preset(
                1,
                "GPT-OSS 120B",
                quantization="MXFP4",
                model_format="GGUF",
                is_reasoning=True,
            ),
        ]
        result = resolve_display_labels(presets)
        assert result == {1: f"GPT-OSS 120B [Reasoning] (GGUF MXFP4 @ {host})"}

    def test_existing_reasoning_name_is_not_duplicated(self):
        """Display labels should not append a second reasoning marker."""
        import socket
        host = socket.gethostname()
        presets = [
            _make_preset(
                1,
                "Claude Opus 4.6 [Reasoning (high)]",
                is_reasoning=True,
                reasoning_level="high",
            ),
        ]
        result = resolve_display_labels(presets)
        assert result == {1: f"Claude Opus 4.6 [Reasoning (high)]"}

    def test_fallback_to_preset_id(self):
        """All metadata identical → append preset ID."""
        presets = [
            _make_preset(1, "Qwen3.5 27B"),
            _make_preset(2, "Qwen3.5 27B"),
        ]
        result = resolve_display_labels(presets)
        assert result[1] != result[2]  # Must be different
        assert "#1" in result[1]
        assert "#2" in result[2]

    def test_reasoning_suffix_survives_collision_fallback(self):
        """Reasoning presets should keep their suffix even when fallback disambiguates."""
        presets = [
            _make_preset(1, "Qwen3.5 27B", is_reasoning=True),
            _make_preset(2, "Qwen3.5 27B", is_reasoning=True),
        ]
        result = resolve_display_labels(presets)
        assert "[Reasoning]" in result[1]
        assert "[Reasoning]" in result[2]
        assert result[1].endswith("#1")
        assert result[2].endswith("#2")

    def test_mixed_cloud_and_local(self):
        """Cloud models stay bare, local models always get labels."""
        import socket
        host = socket.gethostname()
        presets = [
            _make_preset(1, "Qwen3.5 27B", quantization="4bit", model_format="MLX"),
            _make_preset(2, "Qwen3.5 27B", quantization="8bit", model_format="MLX"),
            _make_preset(3, "GPT-4o"),
        ]
        result = resolve_display_labels(presets)
        assert result[1] == f"Qwen3.5 27B (MLX 4bit @ {host})"
        assert result[2] == f"Qwen3.5 27B (MLX 8bit @ {host})"
        assert result[3] == "GPT-4o"

    def test_quant_only_no_format(self):
        """Quant without format still shows with host."""
        import socket
        host = socket.gethostname()
        presets = [_make_preset(1, "Model", quantization="Q4_K_M")]
        result = resolve_display_labels(presets)
        assert result == {1: f"Model (Q4_K_M @ {host})"}

    def test_format_only_no_quant(self):
        """Format without quant still shows with host."""
        import socket
        host = socket.gethostname()
        presets = [_make_preset(1, "Model", model_format="GGUF")]
        result = resolve_display_labels(presets)
        assert result == {1: f"Model (GGUF @ {host})"}

    def test_empty_list(self):
        assert resolve_display_labels([]) == {}

    def test_single_preset(self):
        presets = [_make_preset(1, "GPT-4o")]
        assert resolve_display_labels(presets) == {1: "GPT-4o"}
