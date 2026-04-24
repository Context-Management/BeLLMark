# backend/tests/test_discovery.py
import pytest


def test_humanize_model_id():
    """Should convert model IDs to human-friendly names."""
    from app.core.discovery import humanize_model_id
    assert humanize_model_id("gpt-4o") == "GPT-4o"
    assert humanize_model_id("claude-opus-4-6-20250619") == "Claude Opus 4.6"
    assert humanize_model_id("claude-sonnet-4-5-20250929") == "Claude Sonnet 4.5"
    assert humanize_model_id("gemini-2.5-pro") == "Gemini 2.5 Pro"
    assert humanize_model_id("deepseek-chat") == "DeepSeek Chat"
    assert humanize_model_id("deepseek-reasoner") == "DeepSeek Reasoner"


def test_detect_reasoning_openai():
    """OpenAI o-series and gpt-5 should be detected as reasoning."""
    from app.core.discovery import detect_reasoning_capability
    r = detect_reasoning_capability("o3-mini", "openai")
    assert r["is_reasoning"] is True
    assert r["reasoning_levels"] == ["low", "medium", "high", "xhigh"]
    r = detect_reasoning_capability("gpt-4o", "openai")
    assert r["is_reasoning"] is False
    assert r["reasoning_levels"] == []
    r = detect_reasoning_capability("gpt-5.2", "openai")
    assert r["is_reasoning"] is True
    assert r["reasoning_levels"] == ["low", "medium", "high", "xhigh"]


def test_detect_reasoning_anthropic():
    """All Claude 4+ models support extended thinking with multiple levels."""
    from app.core.discovery import detect_reasoning_capability
    r = detect_reasoning_capability("claude-opus-4-6-20250619", "anthropic")
    assert r["is_reasoning"] is True
    assert r["reasoning_level"] == "high"
    assert r["reasoning_levels"] == ["low", "medium", "high", "max"]
    r = detect_reasoning_capability("claude-opus-4-5-20251101", "anthropic")
    assert r["is_reasoning"] is True
    assert r["reasoning_levels"] == ["low", "medium", "high", "xhigh", "max"]
    r = detect_reasoning_capability("claude-sonnet-4-5-20250929", "anthropic")
    assert r["is_reasoning"] is True
    assert r["reasoning_level"] == "medium"
    assert r["reasoning_levels"] == ["low", "medium", "high", "xhigh", "max"]
    r = detect_reasoning_capability("claude-sonnet-4-20250514", "anthropic")
    assert r["is_reasoning"] is True
    r = detect_reasoning_capability("claude-haiku-4-5-20251001", "anthropic")
    assert r["is_reasoning"] is True
    assert r["reasoning_level"] == "low"
    assert r["reasoning_levels"] == ["low", "medium", "high"]
    # Claude 3.5 does not support thinking
    r = detect_reasoning_capability("claude-3-5-sonnet-20241022", "anthropic")
    assert r["is_reasoning"] is False
    assert r["reasoning_levels"] == []


def test_detect_reasoning_google():
    """Gemini 2.5+ and 3.x support thinking with levels."""
    from app.core.discovery import detect_reasoning_capability
    r = detect_reasoning_capability("gemini-2.5-pro-preview-06-05", "google")
    assert r["is_reasoning"] is True
    assert r["reasoning_levels"] == ["low", "medium", "high"]
    r = detect_reasoning_capability("gemini-1.5-flash", "google")
    assert r["is_reasoning"] is False
    assert r["reasoning_levels"] == []


def test_detect_reasoning_deepseek():
    """DeepSeek reasoner model is reasoning."""
    from app.core.discovery import detect_reasoning_capability
    r = detect_reasoning_capability("deepseek-reasoner", "deepseek")
    assert r["is_reasoning"] is True
    assert r["reasoning_level"] is None
    r = detect_reasoning_capability("deepseek-chat", "deepseek")
    assert r["is_reasoning"] is False


def test_detect_reasoning_grok():
    """Grok 4 is always reasoning (toggle), mini has levels."""
    from app.core.discovery import detect_reasoning_capability
    r = detect_reasoning_capability("grok-4", "grok")
    assert r["is_reasoning"] is True
    assert r["reasoning_levels"] == []  # toggle-only
    r = detect_reasoning_capability("grok-4.1-fast", "grok")
    assert r["is_reasoning"] is True
    assert r["reasoning_levels"] == []  # toggle-only
    r = detect_reasoning_capability("grok-3-mini", "grok")
    assert r["is_reasoning"] is True
    assert r["reasoning_levels"] == ["low", "medium", "high"]
    r = detect_reasoning_capability("grok-3", "grok")
    assert r["is_reasoning"] is False


def test_detect_reasoning_mistral():
    """Magistral models are reasoning."""
    from app.core.discovery import detect_reasoning_capability
    r = detect_reasoning_capability("magistral-medium", "mistral")
    assert r["is_reasoning"] is True
    r = detect_reasoning_capability("mistral-large", "mistral")
    assert r["is_reasoning"] is False


def test_detect_reasoning_kimi():
    """Kimi k2.5 supports thinking."""
    from app.core.discovery import detect_reasoning_capability
    r = detect_reasoning_capability("k2.5", "kimi")
    assert r["is_reasoning"] is True
    r = detect_reasoning_capability("moonshot-v1-8k", "kimi")
    assert r["is_reasoning"] is False


def test_lmstudio_v1_api_parsing():
    """Parse LM Studio /api/v1/models with yaml metadata for reasoning."""
    from app.core.discovery import _parse_lmstudio_api_v1
    yaml_meta = {
        "openai/gpt-oss-120b": {"reasoning": True, "vision": False},
        "google/gemma-3-27b": {"reasoning": None, "vision": True},
        "zai-org/glm-4.7-flash": {"reasoning": True, "vision": False},
    }
    data = {"models": [
        {"key": "openai/gpt-oss-120b", "type": "llm", "display_name": "GPT-OSS 120B",
         "architecture": "gpt-oss",
         "params_string": "120B",
         "selected_variant": "openai/gpt-oss-120b@mxfp4",
         "quantization": {"name": "MXFP4", "bits_per_weight": 4.0},
         "format": "gguf", "publisher": "openai",
         "capabilities": {"vision": False, "trained_for_tool_use": True},
         "max_context_length": 131072},
        {"key": "google/gemma-3-27b", "type": "vlm", "display_name": "Gemma 3 27B",
         "capabilities": {"vision": True, "trained_for_tool_use": False},
         "max_context_length": 131072},
        {"key": "zai-org/glm-4.7-flash", "type": "llm", "display_name": "GLM 4.7 Flash",
         "capabilities": {"vision": False, "trained_for_tool_use": True},
         "max_context_length": 202752},
        {"key": "text-embedding-nomic", "type": "embedding",
         "capabilities": {}, "max_context_length": 2048},
        {"key": "mistralai/mistral-small-3.2", "type": "llm", "display_name": "Mistral Small 3.2",
         "capabilities": {}, "max_context_length": 32768},
    ]}
    results = _parse_lmstudio_api_v1(data, "http://localhost:1234", yaml_meta)
    assert len(results) == 4  # embedding excluded
    # gpt-oss: reasoning=True from model.yaml
    gpt = next(r for r in results if "gpt-oss" in r["model_id"])
    assert gpt["is_reasoning"] is True
    assert gpt["name"] == "GPT-OSS 120B"  # display_name from API
    assert gpt["context_limit"] == 131072
    assert gpt["parameter_count"] == "120B"
    assert gpt["quantization_bits"] == 4.0
    assert gpt["selected_variant"] == "openai/gpt-oss-120b@mxfp4"
    assert gpt["model_architecture"] == "gpt-oss"
    assert gpt["supported_reasoning_levels"] == ["low", "medium", "high", "xhigh"]
    assert gpt["reasoning_detection_source"] == "api_architecture"
    # gemma: vision=True from API capabilities
    gemma = next(r for r in results if "gemma" in r["model_id"])
    assert gemma["supports_vision"] is True
    # glm: reasoning=True from model.yaml
    glm = next(r for r in results if "glm" in r["model_id"])
    assert glm["is_reasoning"] is True
    # mistral: no yaml, no keywords → not reasoning
    mistral = next(r for r in results if "mistral" in r["model_id"])
    assert mistral["is_reasoning"] is False
    assert mistral["supports_vision"] is None


def test_lmstudio_v0_parsing():
    """Parse LM Studio /api/v0/models with yaml metadata."""
    from app.core.discovery import _parse_lmstudio_v0
    yaml_meta = {"openai/gpt-oss-120b": {"reasoning": True, "vision": False}}
    data = {"data": [
        {"id": "openai/gpt-oss-120b", "type": "llm", "capabilities": ["tool_use"],
         "arch": "gpt-oss",
         "max_context_length": 131072},
        {"id": "google/gemma-3-27b", "type": "vlm", "capabilities": [],
         "max_context_length": 131072},
        {"id": "text-embedding-nomic", "type": "embedding",
         "capabilities": [], "max_context_length": 2048},
    ]}
    results = _parse_lmstudio_v0(data, "http://localhost:1234", yaml_meta)
    assert len(results) == 2  # embedding excluded
    gpt = next(r for r in results if "gpt-oss" in r["model_id"])
    assert gpt["is_reasoning"] is True  # from model.yaml
    assert gpt["model_architecture"] == "gpt-oss"
    gemma = next(r for r in results if "gemma" in r["model_id"])
    assert gemma["supports_vision"] is True  # from type=vlm


def test_lmstudio_keyword_fallback():
    """Without model.yaml, reasoning falls back to keyword matching."""
    from app.core.discovery import _resolve_reasoning
    yaml_meta = {}  # no yaml data
    assert _resolve_reasoning("qwen3-next-80b-a3b-thinking", yaml_meta) is True
    assert _resolve_reasoning("allenai/olmo-3-32b-think", yaml_meta) is True
    assert _resolve_reasoning("mistralai/mistral-small-3.2", yaml_meta) is False


def test_lmstudio_arch_detection_for_remote():
    """Architecture field detects reasoning on remote servers (no model.yaml)."""
    from app.core.discovery import _resolve_reasoning
    yaml_meta = {}  # empty — simulates remote server with no local yaml
    # gpt-oss arch → reasoning, even without keywords or yaml
    assert _resolve_reasoning("openai/gpt-oss-120b", yaml_meta, arch="gpt-oss") is True
    assert _resolve_reasoning("huizimao_gpt-oss-120b-uncensored", yaml_meta, arch="gpt-oss") is True
    # Same family can arrive from LM Studio as gpt_oss on MLX builds
    assert _resolve_reasoning("gpt-oss-120b-mlx-3", yaml_meta, arch="gpt_oss") is True
    # qwen35moe arch → reasoning (all Qwen3.5 MoE are hybrid thinkers)
    assert _resolve_reasoning("qwen3.5-122b-a10b", yaml_meta, arch="qwen35moe") is True
    assert _resolve_reasoning("qwen/qwen3.5-35b-a3b", yaml_meta, arch="qwen35moe") is True
    # Dense and MoE Qwen3.5 variants also emit thinking by default in LM Studio
    assert _resolve_reasoning("qwen3.5-27b@4bit", yaml_meta, arch="qwen3_5") is True
    assert _resolve_reasoning("qwen3.5-35b-a3b", yaml_meta, arch="qwen3_5_moe") is True
    # Other LM Studio reasoning families currently exposed on remote servers
    assert _resolve_reasoning("zai-org/glm-4.7-flash", yaml_meta, arch="glm4_moe_lite") is True
    assert _resolve_reasoning("nvidia/nemotron-3-nano", yaml_meta, arch="nemotron_h") is True
    assert _resolve_reasoning("nvidia/nemotron-3-super", yaml_meta, arch="nemotron_h_moe") is True
    # Non-reasoning arch → falls through to keywords
    assert _resolve_reasoning("mistralai/mistral-small-3.2", yaml_meta, arch="llama") is False
    # qwen3next is NOT a reasoning architecture (instruct/coder variants are non-reasoning)
    assert _resolve_reasoning("qwen/qwen3-coder-next", yaml_meta, arch="qwen3next") is False
    # No arch at all → keyword only
    assert _resolve_reasoning("deepseek-r1-distill", yaml_meta) is True


def test_lmstudio_yaml_overrides_arch():
    """model.yaml reasoning=False should override architecture detection."""
    from app.core.discovery import _resolve_reasoning
    yaml_meta = {"qwen/qwen3-next-80b": {"reasoning": False, "vision": False}}
    # Even if we pass an arch, yaml takes priority
    assert _resolve_reasoning("qwen3-next-80b-a3b-instruct", yaml_meta, arch="qwen3next") is False


def test_lmstudio_v1_remote_no_yaml():
    """v1 API parsing works for remote server (no yaml, uses arch)."""
    from app.core.discovery import _parse_lmstudio_api_v1
    yaml_meta = {}  # remote server — no local yaml files
    data = {"models": [
        {"key": "openai/gpt-oss-120b", "type": "llm", "display_name": "GPT-OSS 120B",
         "architecture": "gpt-oss", "capabilities": {"vision": False, "trained_for_tool_use": True},
         "max_context_length": 131072},
        {"key": "gpt-oss-120b-mlx-3", "type": "llm", "display_name": "GPT-OSS 120B 3",
         "architecture": "gpt_oss", "capabilities": {"vision": False, "trained_for_tool_use": True},
         "max_context_length": 131072},
        {"key": "qwen3.5-27b@4bit", "type": "vlm", "display_name": "Qwen3.5 27B",
         "architecture": "qwen3_5", "capabilities": {"vision": True, "trained_for_tool_use": True},
         "max_context_length": 262144},
        {"key": "nvidia/nemotron-3-nano", "type": "llm", "display_name": "Nemotron 3 Nano",
         "architecture": "nemotron_h", "capabilities": {"vision": False, "trained_for_tool_use": True},
         "max_context_length": 262144},
        {"key": "google/gemma-3-27b", "type": "vlm", "display_name": "Gemma 3 27B",
         "architecture": "gemma3", "capabilities": {"vision": True, "trained_for_tool_use": False},
         "max_context_length": 131072},
        {"key": "mistralai/mistral-small-3.2", "type": "llm", "display_name": "Mistral Small 3.2",
         "architecture": "llama", "capabilities": {}, "max_context_length": 32768},
    ]}
    results = _parse_lmstudio_api_v1(data, "http://mini.local:1234", yaml_meta)
    # gpt-oss detected as reasoning via architecture
    gpt = next(r for r in results if "gpt-oss" in r["model_id"])
    assert gpt["is_reasoning"] is True
    assert gpt["supported_reasoning_levels"] == ["low", "medium", "high", "xhigh"]
    gpt_mlx = next(r for r in results if r["model_id"] == "gpt-oss-120b-mlx-3")
    assert gpt_mlx["is_reasoning"] is True
    qwen = next(r for r in results if r["model_id"] == "qwen3.5-27b@4bit")
    assert qwen["is_reasoning"] is True
    nemotron = next(r for r in results if r["model_id"] == "nvidia/nemotron-3-nano")
    assert nemotron["is_reasoning"] is True
    # gemma detected as vision via API capabilities
    gemma = next(r for r in results if "gemma" in r["model_id"])
    assert gemma["supports_vision"] is True
    assert gemma["is_reasoning"] is False
    # mistral: not reasoning
    mistral = next(r for r in results if "mistral" in r["model_id"])
    assert mistral["is_reasoning"] is False


def test_openrouter_in_provider_urls():
    """OpenRouter should be registered in all provider URL maps."""
    from app.db.models import ProviderType
    from app.core.discovery import PROVIDER_LIST_URLS, PROVIDER_CHAT_URLS, PROVIDER_ENV_KEYS
    assert ProviderType.openrouter.value == "openrouter"
    assert ProviderType.openrouter in PROVIDER_LIST_URLS
    assert ProviderType.openrouter in PROVIDER_CHAT_URLS
    assert ProviderType.openrouter in PROVIDER_ENV_KEYS


def test_ollama_in_provider_urls():
    """Ollama should be registered in provider URL maps."""
    from app.db.models import ProviderType
    from app.core.discovery import PROVIDER_CHAT_URLS
    assert ProviderType.ollama.value == "ollama"
    assert ProviderType.ollama in PROVIDER_CHAT_URLS
    # Ollama should NOT require an API key env var


@pytest.mark.asyncio
async def test_discover_openrouter_parses_response():
    """OpenRouter discovery should parse model list with pricing and capabilities."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.core.discovery import discover_openrouter

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {
                "id": "anthropic/claude-sonnet-4-5",
                "name": "Claude Sonnet 4.5",
                "context_length": 200000,
                "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                "architecture": {
                    "modality": "text+image->text",
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                },
                "supported_parameters": ["temperature", "tools", "reasoning"],
            },
            {
                "id": "meta-llama/llama-3.1-8b-instruct",
                "name": "Llama 3.1 8B Instruct",
                "context_length": 131072,
                "pricing": {"prompt": "0.00000006", "completion": "0.00000006"},
                "architecture": {
                    "modality": "text->text",
                    "input_modalities": ["text"],
                    "output_modalities": ["text"],
                },
                "supported_parameters": ["temperature", "tools"],
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.discovery.httpx.AsyncClient", return_value=mock_client):
        results = await discover_openrouter(api_key="test-key")

    assert len(results) >= 2
    # First model: Claude Sonnet 4.5 with vision + pricing
    claude = next(r for r in results if r["model_id"] == "anthropic/claude-sonnet-4-5" and not r["is_reasoning"])
    assert claude["name"] == "Claude Sonnet 4.5"
    assert claude["supports_vision"] is True
    assert claude["context_limit"] == 200000
    assert claude["price_input"] == 3.0  # $0.000003 * 1M
    assert claude["price_output"] == 15.0
    assert claude["provider_default_url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert claude["price_source"] == "openrouter_api"
    assert claude["price_source_url"] == "https://openrouter.ai/api/v1/models"

    # Reasoning variant should also exist
    claude_r = next(r for r in results if r["model_id"] == "anthropic/claude-sonnet-4-5" and r["is_reasoning"])
    assert "[Reasoning]" in claude_r["name"]
    assert claude_r["price_input"] == 3.0  # Pricing preserved in variant

    # Second model: Llama text-only, no vision
    llama = next(r for r in results if r["model_id"] == "meta-llama/llama-3.1-8b-instruct")
    assert llama["supports_vision"] is None
    assert llama["price_input"] == pytest.approx(0.06, abs=0.01)


@pytest.mark.asyncio
async def test_discover_ollama_parses_tags():
    """Ollama discovery should parse /api/tags response with model metadata."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.core.discovery import discover_ollama

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "models": [
            {
                "name": "llama3.1:70b-instruct-q4_K_M",
                "modified_at": "2026-02-20T10:00:00Z",
                "size": 42000000000,
                "details": {
                    "format": "gguf",
                    "family": "llama",
                    "parameter_size": "70.6B",
                    "quantization_level": "Q4_K_M",
                },
            },
            {
                "name": "llava:13b",
                "modified_at": "2026-02-19T10:00:00Z",
                "size": 8000000000,
                "details": {
                    "format": "gguf",
                    "family": "llava",
                    "parameter_size": "13B",
                    "quantization_level": "Q4_0",
                },
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.discovery.httpx.AsyncClient", return_value=mock_client):
        results = await discover_ollama("http://localhost:11434")

    assert len(results) >= 2
    llama = next(r for r in results if "llama3.1" in r["model_id"])
    assert llama["model_id"] == "llama3.1:70b-instruct-q4_K_M"
    assert "70.6B" in llama["name"]
    assert "Q4_K_M" in llama["name"]
    assert llama["provider_default_url"] == "http://localhost:11434/v1/chat/completions"

    # llava is a vision model
    llava = next(r for r in results if "llava" in r["model_id"])
    assert llava["supports_vision"] is True


@pytest.mark.asyncio
async def test_discover_ollama_remote_url():
    """Ollama discovery should work with remote URLs (e.g. cachy.local:11434)."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.core.discovery import discover_ollama

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "models": [
            {
                "name": "qwen2.5:7b",
                "details": {"family": "qwen2", "parameter_size": "7B", "quantization_level": "Q4_0"},
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.discovery.httpx.AsyncClient", return_value=mock_client):
        results = await discover_ollama("http://cachy.local:11434")

    assert len(results) == 1
    # Chat URL should use the remote host, not localhost
    assert results[0]["provider_default_url"] == "http://cachy.local:11434/v1/chat/completions"

    # Verify the GET was made to the remote host
    mock_client.get.assert_called_once_with("http://cachy.local:11434/api/tags")


@pytest.mark.asyncio
async def test_discover_openai_compatible_enriches_catalog_prices():
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.core.discovery import discover_models
    from app.db.models import ProviderType

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"data": [{"id": "gpt-4.1"}]}

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.discovery.httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
        results = await discover_models(ProviderType.openai)

    base_variant = next(r for r in results if r["model_id"] == "gpt-4.1" and r["is_reasoning"] is False)
    assert base_variant["price_input"] == 2.0
    assert base_variant["price_output"] == 8.0
    assert base_variant["price_source"] == "catalog"
    assert base_variant["price_source_url"] == "https://developers.openai.com/api/docs/models/gpt-4.1"


@pytest.mark.asyncio
async def test_discover_lmstudio_uses_list_metadata_without_runtime_probe():
    """LM Studio discovery should stay read-only and avoid chat-completion probes."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.core.discovery import discover_lmstudio

    mock_list_response = MagicMock()
    mock_list_response.status_code = 200
    mock_list_response.raise_for_status = MagicMock()
    mock_list_response.json.return_value = {
        "models": [
            {
                "key": "openai/gpt-oss-20b",
                "type": "llm",
                "display_name": "GPT-OSS 20B",
                "architecture": "gpt-oss",
                "format": "gguf",
                "quantization": {"name": "Q4_K_M"},
                "capabilities": {"vision": False},
                "max_context_length": 131072,
            },
            {
                "key": "openai/gpt-oss-120b",
                "type": "llm",
                "display_name": "GPT-OSS 120B",
                "architecture": "gpt-oss",
                "format": "mlx",
                "quantization": {"name": "4bit"},
                "capabilities": {"vision": False},
                "max_context_length": 131072,
            },
        ]
    }
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_list_response)
    mock_client.post = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("app.core.discovery.httpx.AsyncClient", return_value=mock_client), \
         patch("app.core.discovery._load_lmstudio_model_yamls", return_value={}):
        results = await discover_lmstudio("http://localhost:1234")

    assert len(results) == 2
    assert {r["model_id"] for r in results} == {"openai/gpt-oss-20b", "openai/gpt-oss-120b"}
    mock_client.get.assert_called_once_with("http://localhost:1234/api/v1/models")
    mock_client.post.assert_not_awaited()
    assert [r["quantization"] for r in results] == ["Q4_K_M", "4bit"]
    assert [r["model_format"] for r in results] == ["GGUF", "MLX"]


def test_parse_lmstudio_quant_metadata_from_api_fields():
    """LM Studio /api/v1/models should prefer explicit API fields for quant/format/source."""
    from app.core.discovery import _parse_lmstudio_api_v1

    data = {"models": [
        # Model with explicit API quant fields (what LM Studio actually returns)
        {"key": "qwen3.5-27b", "type": "llm", "display_name": "Qwen3.5 27B",
         "quantization": {"name": "4bit", "bits_per_weight": 4},
         "format": "mlx", "publisher": "mlx-community"},
        # GGUF model with API fields
        {"key": "openai/gpt-oss-120b", "type": "llm", "display_name": "GPT-OSS 120B",
         "quantization": {"name": "MXFP4", "bits_per_weight": 4},
         "format": "gguf", "publisher": "lmstudio-community"},
        # MLX model where key has -mlx- but API also provides fields
        {"key": "gpt-oss-120b-mlx-3", "type": "llm", "display_name": "GPT-OSS 120B 3",
         "quantization": {"name": "3bit", "bits_per_weight": 3},
         "format": "mlx", "publisher": "MoringLabs"},
    ]}
    results = _parse_lmstudio_api_v1(data, "http://localhost:1234", {})

    # qwen3.5-27b: key has NO quant info, but API provides it
    assert results[0]["quantization"] == "4bit"
    assert results[0]["model_format"] == "MLX"
    assert results[0]["model_source"] == "mlx-community"

    # gpt-oss-120b: API provides MXFP4 (not parseable from key alone)
    assert results[1]["quantization"] == "MXFP4"
    assert results[1]["model_format"] == "GGUF"
    assert results[1]["model_source"] == "lmstudio-community"

    # gpt-oss-120b-mlx-3: API confirms what key parsing would also find
    assert results[2]["quantization"] == "3bit"
    assert results[2]["model_format"] == "MLX"
    assert results[2]["model_source"] == "MoringLabs"


def test_parse_lmstudio_quant_metadata_fallback():
    """When API doesn't provide quant fields, fall back to model_id parsing."""
    from app.core.discovery import _parse_lmstudio_api_v1

    data = {"models": [
        # No quantization/format/publisher fields — fall back to key parsing
        {"key": "mlx-community/qwen3.5-27b-4bit", "type": "llm", "display_name": "Qwen3.5 27B 4bit"},
        {"key": "lmstudio-community/Qwen3.5-GGUF/Qwen3.5-Q4_K_M", "type": "llm"},
        {"key": "MoringLabs/gpt-oss-120b-mlx-3", "type": "llm"},
    ]}
    results = _parse_lmstudio_api_v1(data, "http://localhost:1234", {})

    assert results[0]["quantization"] == "4bit"
    assert results[0]["model_format"] == "MLX"
    assert results[0]["model_source"] == "mlx-community"

    assert results[1]["quantization"] == "Q4_K_M"
    assert results[1]["model_format"] == "GGUF"
    assert results[1]["model_source"] == "lmstudio-community"

    assert results[2]["quantization"] == "3bit"
    assert results[2]["model_format"] == "MLX"
    assert results[2]["model_source"] == "MoringLabs"


def test_parse_lmstudio_v0_quant_metadata():
    """LM Studio /api/v0/models should use explicit API fields."""
    from app.core.discovery import _parse_lmstudio_v0

    data = {"data": [
        {"id": "qwen3.5-27b", "type": "llm",
         "quantization": "4bit", "compatibility_type": "mlx", "publisher": "mlx-community"},
    ]}
    results = _parse_lmstudio_v0(data, "http://localhost:1234", {})
    assert results[0]["quantization"] == "4bit"
    assert results[0]["model_format"] == "MLX"
    assert results[0]["model_source"] == "mlx-community"


def test_parse_lmstudio_v1_quant_metadata():
    """Bare /v1/models fallback should also extract quant metadata."""
    from app.core.discovery import _parse_lmstudio_v1

    data = {"data": [
        {"id": "lmstudio-community/Model-GGUF/Model-Q8_0"},
        {"id": "text-embedding-nomic-embed-text-v1.5"},
    ]}
    results = _parse_lmstudio_v1(data, "http://localhost:1234", {})
    assert len(results) == 1
    assert results[0]["quantization"] == "Q8_0"
    assert results[0]["model_format"] == "GGUF"
    assert results[0]["model_source"] == "lmstudio-community"
