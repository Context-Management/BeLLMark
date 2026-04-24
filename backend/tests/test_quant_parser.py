import pytest
from app.core.quant_parser import parse_quantization, parse_model_format, parse_model_source


class TestParseQuantization:
    """Extract quantization from model ID strings."""

    def test_gguf_standard(self):
        assert parse_quantization("lmstudio-community/Qwen3.5-122b-a10b-GGUF/Qwen3.5-122b-a10b-Q4_K_M") == "Q4_K_M"
        assert parse_quantization("some-model-Q8_0") == "Q8_0"
        assert parse_quantization("model-IQ4_XS") == "IQ4_XS"
        assert parse_quantization("model-Q6_K") == "Q6_K"
        assert parse_quantization("model-Q4_K_S") == "Q4_K_S"

    def test_bit_width(self):
        assert parse_quantization("mlx-community/qwen3.5-27b-4bit") == "4bit"
        assert parse_quantization("some-model-8bit") == "8bit"
        assert parse_quantization("model-3bit-something") == "3bit"

    def test_mlx_trailing_digit(self):
        assert parse_quantization("MoringLabs/gpt-oss-120b-mlx-3") == "3bit"
        assert parse_quantization("publisher/model-mlx-4") == "4bit"

    def test_mixed_precision(self):
        assert parse_quantization("model-MXFP4") == "MXFP4"
        assert parse_quantization("model-FP16") == "FP16"
        assert parse_quantization("model-BF16") == "BF16"

    def test_gptq(self):
        assert parse_quantization("model-GPTQ-Int4") == "GPTQ-Int4"

    def test_awq(self):
        assert parse_quantization("model-AWQ-something") == "AWQ"

    def test_exl2(self):
        assert parse_quantization("model-exl2-4.0bpw") == "EXL2 4.0bpw"

    def test_no_match(self):
        assert parse_quantization("gpt-4o") is None
        assert parse_quantization("claude-opus-4-6") is None

    def test_ollama_explicit(self):
        """Ollama passes quant directly — parser should accept it as-is."""
        assert parse_quantization("anything", explicit_quant="Q4_K_M") == "Q4_K_M"


class TestParseModelFormat:
    """Detect model format from model ID and source."""

    def test_mlx_from_source(self):
        assert parse_model_format("model-id", source="mlx-community") == "MLX"

    def test_mlx_from_key(self):
        assert parse_model_format("MoringLabs/gpt-oss-120b-mlx-3") == "MLX"
        assert parse_model_format("publisher/model-mlx-4bit") == "MLX"

    def test_gguf_from_path(self):
        assert parse_model_format("lmstudio-community/Model-GGUF/Model-Q4_K_M") == "GGUF"

    def test_gguf_default_lmstudio(self):
        assert parse_model_format("lmstudio-community/Qwen3.5-27b", source="lmstudio-community") == "GGUF"

    def test_mlx_overrides_lmstudio_default(self):
        """MLX rule takes precedence over lmstudio-community GGUF default."""
        assert parse_model_format("lmstudio-community/model-mlx-4bit", source="lmstudio-community") == "MLX"

    def test_gptq_from_quant(self):
        assert parse_model_format("model", quantization="GPTQ-Int4") == "GPTQ"

    def test_awq_from_quant(self):
        assert parse_model_format("model", quantization="AWQ") == "AWQ"

    def test_exl2_from_quant(self):
        assert parse_model_format("model", quantization="EXL2 4.0bpw") == "EXL2"

    def test_cloud_returns_none(self):
        assert parse_model_format("gpt-4o") is None

    def test_ollama_always_gguf(self):
        assert parse_model_format("llama3:latest", is_ollama=True) == "GGUF"


class TestParseModelSource:
    """Extract publisher/source from model ID."""

    def test_lmstudio_path(self):
        assert parse_model_source("mlx-community/qwen3.5-27b-4bit") == "mlx-community"
        assert parse_model_source("lmstudio-community/Model-GGUF/Model-Q4_K_M") == "lmstudio-community"
        assert parse_model_source("MoringLabs/gpt-oss-120b-mlx-3") == "MoringLabs"
        assert parse_model_source("zootkitty/qwen3.5-27b-claude") == "zootkitty"

    def test_no_slash_returns_none(self):
        assert parse_model_source("gpt-4o") is None

    def test_ollama_bare_library(self):
        assert parse_model_source("llama3:latest", is_ollama=True) == "ollama"

    def test_ollama_namespaced(self):
        assert parse_model_source("library/llama3:latest", is_ollama=True) == "library"
