# backend/tests/test_generators.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock, PropertyMock
from app.core.generators import (
    PROVIDER_TEMP_CONFIG,
    _clamp_reasoning_effort,
    normalize_temperature,
    resolve_temperature,
    strip_thinking_tags,
)
from app.db.models import ProviderType, ReasoningLevel, TemperatureMode


def test_strip_orphaned_closing_think_tag():
    """Test handling of orphaned </think> closing tag (Nemotron pattern)."""
    content = "Some reasoning here\n</think>\n**Real answer starts here**"
    result = strip_thinking_tags(content)
    assert result["content"] == "**Real answer starts here**"
    assert "</think>" not in result["content"]


def test_strip_multiple_orphaned_closing_tags():
    """Test multiple orphaned </think> tags - should keep only content after last one."""
    content = "First reasoning\n</think>\nMore reasoning\n</think>\nFinal answer"
    result = strip_thinking_tags(content)
    assert result["content"] == "Final answer"
    assert "</think>" not in result["content"]


def test_strip_orphaned_opening_think_tag():
    """Test handling of orphaned <think> opening tag."""
    content = "Normal content\n<think>\nThis should be removed"
    result = strip_thinking_tags(content)
    assert result["content"] == "Normal content"
    assert "<think>" not in result["content"]


def test_strip_paired_think_tags():
    """Test handling of properly paired <think>...</think> tags."""
    content = "<think>Internal reasoning</think>Final answer"
    result = strip_thinking_tags(content)
    assert result["content"] == "Final answer"
    assert "<think>" not in result["content"]
    assert "</think>" not in result["content"]


def test_strip_multiple_paired_think_tags():
    """Test multiple paired tags."""
    content = "<think>First thought</think>Answer<think>Second thought</think> continues"
    result = strip_thinking_tags(content)
    assert result["content"] == "Answer continues"


def test_strip_preserves_normal_content():
    """Test that normal content without tags is preserved."""
    content = "This is normal content"
    result = strip_thinking_tags(content)
    assert result["content"] == "This is normal content"


def test_strip_preserves_content_with_similar_words():
    """Test that words containing 'think' are preserved."""
    content = "I think this is thoughtful thinking"
    result = strip_thinking_tags(content)
    assert result["content"] == "I think this is thoughtful thinking"


def test_strip_handles_empty_string():
    """Test empty string input."""
    result = strip_thinking_tags("")
    assert result["content"] == ""
    assert result["raw_chars"] == 0
    assert result["answer_chars"] == 0


def test_strip_handles_none():
    """Test None input."""
    result = strip_thinking_tags(None)
    assert result["content"] == ""
    assert result["raw_chars"] == 0
    assert result["answer_chars"] == 0


def test_strip_case_insensitive():
    """Test case-insensitive tag matching."""
    content = "<THINK>Uppercase thinking</THINK>Answer"
    result = strip_thinking_tags(content)
    assert result["content"] == "Answer"


def test_strip_handles_whitespace_around_tags():
    """Test whitespace handling around tags."""
    content = "  <think>Internal</think>  Answer here  "
    result = strip_thinking_tags(content)
    assert "Answer here" in result["content"]
    assert "<think>" not in result["content"]


def test_strip_returns_char_counts():
    """Test that raw_chars and answer_chars are correctly computed."""
    content = "<think>Hidden reasoning</think>Visible answer"
    result = strip_thinking_tags(content)
    assert result["raw_chars"] == len(content)
    assert result["answer_chars"] == len(result["content"])
    assert result["raw_chars"] > result["answer_chars"]


def test_openrouter_provider_in_temp_config():
    """OpenRouter should be in the temperature config map."""
    assert ProviderType.openrouter in PROVIDER_TEMP_CONFIG
    config = PROVIDER_TEMP_CONFIG[ProviderType.openrouter]
    assert config["range"] == (0.0, 2.0)


def test_normalize_temperature_uses_full_range_for_deepseek():
    """DeepSeek should stay on the full 0-2 normalization scale."""
    assert normalize_temperature(0.7, ProviderType.deepseek) == 0.7


def test_deepseek_provider_temp_config_matches_docs():
    """DeepSeek provider config should match the documented 0-2 range and default."""
    config = PROVIDER_TEMP_CONFIG[ProviderType.deepseek]
    assert config["range"] == (0.0, 2.0)
    assert config["default"] == 1.0


def test_provider_default_prefers_kimi_model_specific_temperature():
    """Provider defaults should still use the Kimi K2.5 model-specific recommendation."""
    preset = _make_preset(
        ProviderType.kimi,
        model_id="kimi-k2.5",
        is_reasoning=1,
    )

    assert resolve_temperature(preset, TemperatureMode.provider_default, 0.7) == 1.0


def test_sync_lmstudio_preset_metadata_canonicalizes_resolved_model_id():
    """LM Studio sync should replace stale bare IDs with the resolved runtime model."""
    from app.core.generators import sync_lmstudio_preset_metadata

    preset = _make_preset(
        ProviderType.lmstudio,
        model_id="qwen3.5-27b",
        base_url="http://mini.local:1234/v1/chat/completions",
    )
    preset.quantization = "4bit"
    preset.model_format = "MLX"

    changed = sync_lmstudio_preset_metadata(
        preset,
        resolved_model_id="qwen3.5-27b@8bit",
        probed_quant="8bit",
        raw_format="safetensors",
    )

    assert changed is True
    assert preset.model_id == "qwen3.5-27b@8bit"
    assert preset.quantization == "8bit"
    assert preset.model_format == "MLX"


def test_sync_lmstudio_preset_metadata_noop_when_metadata_matches():
    """LM Studio sync should be a no-op when the preset already matches runtime metadata."""
    from app.core.generators import sync_lmstudio_preset_metadata

    preset = _make_preset(
        ProviderType.lmstudio,
        model_id="qwen3.5-27b@8bit",
        base_url="http://mini.local:1234/v1/chat/completions",
    )
    preset.quantization = "8bit"
    preset.model_format = "MLX"

    changed = sync_lmstudio_preset_metadata(
        preset,
        resolved_model_id="qwen3.5-27b@8bit",
        probed_quant="8bit",
        raw_format="safetensors",
    )

    assert changed is False


def test_sync_lmstudio_preset_metadata_updates_reasoning_flag():
    """LM Studio sync should update reasoning metadata from live discovery."""
    from app.core.generators import sync_lmstudio_preset_metadata

    preset = _make_preset(
        ProviderType.lmstudio,
        model_id="gpt-oss-120b-mlx-3",
        base_url="http://mini.local:1234/v1/chat/completions",
        is_reasoning=0,
    )
    preset.quantization = "3bit"
    preset.model_format = "MLX"

    changed = sync_lmstudio_preset_metadata(
        preset,
        resolved_model_id="gpt-oss-120b-mlx-3",
        probed_quant="3bit",
        raw_format="safetensors",
        discovered_reasoning=True,
    )

    assert changed is True
    assert preset.is_reasoning == 1


def _make_preset(provider, model_id="test-model", api_key_encrypted=None,
                 is_reasoning=0, reasoning_level=None, base_url=None):
    """Create a mock ModelPreset."""
    preset = MagicMock()
    preset.provider = provider
    preset.model_id = model_id
    preset.api_key_encrypted = api_key_encrypted
    preset.is_reasoning = is_reasoning
    preset.reasoning_level = reasoning_level
    preset.base_url = base_url
    preset.supports_vision = None
    preset.custom_temperature = None
    preset.supported_reasoning_levels = None
    return preset


@pytest.mark.asyncio
async def test_openrouter_generate_success():
    """OpenRouter generate should send correct headers and parse response."""
    from app.core.generators import generate

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Hello world"}}],
        "usage": {"total_tokens": 42},
        "model": "meta-llama/llama-3.1-8b-instruct",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.openrouter,
        model_id="meta-llama/llama-3.1-8b-instruct",
        base_url="https://openrouter.ai/api/v1/chat/completions",
    )

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-test"}):
        result = await generate(preset, "You are helpful.", "Hi", temperature=0.7)

    assert result["success"] is True
    assert result["content"] == "Hello world"
    assert result["tokens"] == 42

    # Verify headers include BeLLMark attribution
    call_kwargs = mock_client.post.call_args
    headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers", {})
    assert headers.get("HTTP-Referer") == "https://bellmark.ai"
    assert headers.get("X-Title") == "BeLLMark"


@pytest.mark.asyncio
async def test_openai_generate_persists_usage_breakdown():
    """OpenAI usage should be normalized into input/output/cached/reasoning fields."""
    from app.core.generators import generate

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Done"}}],
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 30,
            "total_tokens": 150,
            "prompt_tokens_details": {"cached_tokens": 20},
            "completion_tokens_details": {"reasoning_tokens": 12},
        },
        "model": "gpt-4.1",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.openai,
        model_id="gpt-4.1",
        base_url="https://api.openai.com/v1/chat/completions",
    )

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
        result = await generate(preset, "sys", "hi", temperature=0.7)

    assert result["success"] is True
    assert result["tokens"] == 150
    assert result["input_tokens"] == 120
    assert result["output_tokens"] == 30
    assert result["cached_input_tokens"] == 20
    assert result["reasoning_tokens"] == 12


@pytest.mark.asyncio
async def test_anthropic_generate_persists_usage_breakdown():
    """Anthropic usage should be normalized into input/output fields."""
    from app.core.generators import generate

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "content": [{"type": "text", "text": "Done"}],
        "usage": {
            "input_tokens": 80,
            "output_tokens": 40,
            "cache_read_input_tokens": 10,
        },
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.anthropic,
        model_id="claude-sonnet-4-6",
        base_url="https://api.anthropic.com/v1/messages",
    )

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
        result = await generate(preset, "sys", "hi", temperature=0.7)

    assert result["success"] is True
    assert result["tokens"] == 120
    assert result["input_tokens"] == 80
    assert result["output_tokens"] == 40
    assert result["cached_input_tokens"] == 10


@pytest.mark.asyncio
async def test_kimi_generate_persists_usage_breakdown():
    """Kimi usage should be normalized into input/output/reasoning fields."""
    from app.core.generators import generate

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Done"}}],
        "usage": {
            "input_tokens": 50,
            "output_tokens": 80,
            "total_tokens": 130,
            "completion_tokens_details": {"reasoning_tokens": 20},
        },
        "model": "kimi-k2.5",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.kimi,
        model_id="kimi-k2.5",
        base_url="https://api.moonshot.ai/v1/chat/completions",
        is_reasoning=True,
    )

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"KIMI_API_KEY": "sk-kimi-test"}):
        result = await generate(preset, "sys", "hi", temperature=1.0)

    assert result["success"] is True
    assert result["tokens"] == 130
    assert result["input_tokens"] == 50
    assert result["output_tokens"] == 80
    assert result["reasoning_tokens"] == 20


@pytest.mark.asyncio
async def test_openrouter_generate_http_error():
    """OpenRouter generate should handle HTTP errors gracefully."""
    from app.core.generators import generate
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "401", request=MagicMock(), response=mock_response
    )

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.openrouter,
        base_url="https://openrouter.ai/api/v1/chat/completions",
    )

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"OPENROUTER_API_KEY": "bad-key"}):
        result = await generate(preset, "sys", "hi")

    assert result["success"] is False
    assert "401" in result["error"]


@pytest.mark.asyncio
async def test_openrouter_test_connection_success():
    """OpenRouter test_connection should check /v1/models."""
    from app.core.generators import test_connection

    mock_response = MagicMock()
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(ProviderType.openrouter)

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client), \
         patch.dict("os.environ", {"OPENROUTER_API_KEY": "sk-or-test"}):
        result = await test_connection(preset)

    assert result["ok"] is True


@pytest.mark.asyncio
async def test_openrouter_test_connection_no_key():
    """OpenRouter test_connection should fail gracefully without API key."""
    from app.core.generators import test_connection

    preset = _make_preset(ProviderType.openrouter)

    with patch.dict("os.environ", {}, clear=True):
        result = await test_connection(preset)

    assert result["ok"] is False
    assert "API key" in result["error"]


@pytest.mark.asyncio
async def test_ollama_generate_success():
    """Ollama generate should send no auth headers and parse response."""
    from app.core.generators import generate

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Ollama says hi"}}],
        "usage": {"total_tokens": 15},
        "model": "llama3.1:8b",
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.ollama,
        model_id="llama3.1:8b",
        base_url="http://cachy.local:11434/v1/chat/completions",
    )

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client):
        result = await generate(preset, "You are helpful.", "Hi", temperature=0.7)

    assert result["success"] is True
    assert result["content"] == "Ollama says hi"
    assert result["tokens"] == 15

    # Verify no Authorization header was sent (Ollama is local, no auth)
    call_kwargs = mock_client.post.call_args
    headers = call_kwargs.kwargs.get("headers", {})
    assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_ollama_generate_timeout():
    """Ollama generate should handle connection timeout."""
    from app.core.generators import generate
    import httpx

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.ollama,
        base_url="http://localhost:11434/v1/chat/completions",
    )

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client):
        result = await generate(preset, "sys", "hi")

    assert result["success"] is False
    assert "timed out" in result["error"].lower()


@pytest.mark.asyncio
async def test_ollama_test_connection_success():
    """Ollama test_connection should return richer exact-check data."""
    from app.core.generators import test_connection

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"model": "llama3.1:8b"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.ollama,
        model_id="llama3.1:8b",
        base_url="http://cachy.local:11434/v1/chat/completions",
    )

    with patch(
        "app.core.generators.discover_models",
        new=AsyncMock(return_value=[{"model_id": "llama3.1:8b", "name": "Llama 3.1 8B"}]),
    ), patch("app.core.generators.httpx.AsyncClient", return_value=mock_client):
        result = await test_connection(preset)

    assert result["ok"] is True
    assert result["resolved_model_id"] == "llama3.1:8b"
    assert result["validation_status"] == "available_exact"
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_ollama_test_connection_offline():
    """Ollama test_connection should handle server being offline."""
    from app.core.generators import test_connection
    import httpx

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.ollama,
        base_url="http://localhost:11434/v1/chat/completions",
    )

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client):
        result = await test_connection(preset)

    assert result["ok"] is False
    assert "connect" in result["error"].lower()


@pytest.mark.asyncio
async def test_lmstudio_generate_sends_reasoning_effort_when_levels_are_known():
    """LM Studio generation should forward reasoning_effort for level-aware models."""
    from app.core.generators import generate

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "OK"}}],
        "usage": {"total_tokens": 9},
        "model": "openai/gpt-oss-120b",
        "model_info": {"quant": "MXFP4", "format": "gguf"},
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.lmstudio,
        model_id="openai/gpt-oss-120b",
        base_url="http://localhost:1234/v1/chat/completions",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high,
    )
    preset.supported_reasoning_levels = ["low", "medium", "high", "xhigh"]
    preset.model_architecture = "gpt-oss"

    with patch("app.core.generators.httpx.AsyncClient", return_value=mock_client):
        result = await generate(preset, "You are helpful.", "Hi", temperature=0.7)

    assert result["success"] is True
    request_json = mock_client.post.call_args.kwargs["json"]
    assert request_json["reasoning_effort"] == "high"


@pytest.mark.asyncio
async def test_lmstudio_generate_omits_reasoning_effort_when_levels_are_unknown():
    """LM Studio generation should skip reasoning_effort without a known level list."""
    from app.core.generators import generate

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "OK"}}],
        "usage": {"total_tokens": 9},
        "model": "openai/gpt-oss-120b",
        "model_info": {"quant": "MXFP4", "format": "gguf"},
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    preset = _make_preset(
        ProviderType.lmstudio,
        model_id="openai/gpt-oss-120b",
        base_url="http://localhost:1234/v1/chat/completions",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high,
    )
    preset.supported_reasoning_levels = None
    preset.model_architecture = "gpt-oss"

    with patch("app.core.generators.resolve_lmstudio_reasoning_capability", return_value={"supported_reasoning_levels": []}), \
         patch("app.core.generators.httpx.AsyncClient", return_value=mock_client):
        result = await generate(preset, "You are helpful.", "Hi", temperature=0.7)

    assert result["success"] is True
    request_json = mock_client.post.call_args.kwargs["json"]
    assert "reasoning_effort" not in request_json


def test_clamp_reasoning_effort_uses_supported_levels_when_provided():
    """Reasoning effort clamping should respect an explicit supported-level list."""
    assert _clamp_reasoning_effort("xhigh", "openai/gpt-oss-120b", "lmstudio", supported_levels=["low", "medium", "high"]) == "high"
