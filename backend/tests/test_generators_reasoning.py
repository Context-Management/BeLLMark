import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.db.models import ModelPreset, ProviderType, ReasoningLevel

@pytest.mark.asyncio
async def test_openai_gpt52_reasoning_effort():
    """GPT-5.2 should use top-level reasoning_effort in Chat Completions API."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="GPT-5.2 High",
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-5.2",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "reasoning_effort" in call_json
        assert call_json["reasoning_effort"] == "high"
        # Temperature must be skipped when reasoning is enabled
        assert "temperature" not in call_json


@pytest.mark.asyncio
async def test_openai_o3_toplevel_reasoning_effort():
    """Pre-5.2 models (o3) should use top-level reasoning_effort."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="o3 High",
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="o3",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "reasoning_effort" in call_json
        assert call_json["reasoning_effort"] == "high"
        assert "reasoning" not in call_json
        assert "temperature" not in call_json


@pytest.mark.asyncio
async def test_openai_max_maps_to_xhigh():
    """OpenAI 'max' reasoning level should map to 'xhigh'."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="o4-mini Max",
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="o4-mini",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.max
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert call_json["reasoning_effort"] == "xhigh"


@pytest.mark.asyncio
async def test_openai_gpt5_base_no_temperature():
    """GPT-5 base model should never have temperature (even non-reasoning)."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="GPT-5",
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-5",
        is_reasoning=0,
        reasoning_level=None
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "temperature" not in call_json


@pytest.mark.asyncio
async def test_openai_o4_no_temperature():
    """o4 series should never have temperature."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="o4-mini",
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="o4-mini",
        is_reasoning=0,
        reasoning_level=None
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "temperature" not in call_json


@pytest.mark.asyncio
async def test_openai_gpt51_nonreasoning_has_temperature():
    """GPT-5.1 without reasoning should include temperature."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="GPT-5.1",
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-5.1",
        is_reasoning=0,
        reasoning_level=None
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "temperature" in call_json


@pytest.mark.asyncio
async def test_deepseek_thinking_mode():
    """DeepSeek requests should include thinking.type parameter."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=2,
        name="DeepSeek R1",
        provider=ProviderType.deepseek,
        base_url="https://api.deepseek.com/v1/chat/completions",
        model_id="deepseek-r1",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "thinking" in call_json
        assert call_json["thinking"]["type"] == "enabled"
        assert "temperature" not in call_json


@pytest.mark.asyncio
async def test_deepseek_reasoner_ignores_temperature_when_misconfigured():
    """deepseek-reasoner should stay in thinking mode even if the preset flag is wrong."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=2,
        name="DeepSeek Reasoner",
        provider=ProviderType.deepseek,
        base_url="https://api.deepseek.com/v1/chat/completions",
        model_id="deepseek-reasoner",
        is_reasoning=0,
        reasoning_level=None,
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert call_json["thinking"] == {"type": "enabled"}
        assert "temperature" not in call_json


@pytest.mark.asyncio
async def test_kimi_thinking_mode():
    """Kimi requests should include thinking.type parameter."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=3,
        name="Kimi k2.5",
        provider=ProviderType.kimi,
        base_url="https://api.moonshot.ai/v1/chat/completions",
        model_id="kimi-k2.5",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "thinking" in call_json
        assert call_json["thinking"]["type"] == "enabled"
        assert call_json["temperature"] == 1.0


@pytest.mark.asyncio
async def test_kimi_k25_instant_mode_sends_temperature():
    """Kimi K2.5 instant mode should still send the resolved temperature explicitly."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=3,
        name="Kimi k2.5 Instant",
        provider=ProviderType.kimi,
        base_url="https://api.moonshot.ai/v1/chat/completions",
        model_id="kimi-k2.5",
        is_reasoning=0,
        reasoning_level=None
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user", temperature=0.55)

        call_json = mock_client.post.call_args.kwargs["json"]
        assert call_json["thinking"] == {"type": "disabled"}
        assert call_json["temperature"] == 0.55


@pytest.mark.asyncio
async def test_openrouter_reasoning_uses_requested_effort():
    """OpenRouter should pass through the preset reasoning level, not hardcode high."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=4,
        name="OpenRouter Reasoning",
        provider=ProviderType.openrouter,
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model_id="z-ai/glm-5",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.medium,
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user", temperature=0.55)

        call_json = mock_client.post.call_args.kwargs["json"]
        assert call_json["reasoning"] == {"effort": "medium"}
        assert call_json["temperature"] == 0.55


@pytest.mark.asyncio
async def test_anthropic_opus46_adaptive_thinking():
    """Opus 4.6 should use adaptive thinking with effort via output_config."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=10,
        name="Claude Opus 4.6 (High Thinking)",
        provider=ProviderType.anthropic,
        base_url="https://api.anthropic.com/v1/messages",
        model_id="claude-opus-4-6",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [
                {"type": "thinking", "thinking": "Let me think..."},
                {"type": "text", "text": "The answer is 42."}
            ],
            "usage": {"input_tokens": 50, "output_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        # Claude 4.6 models use adaptive thinking (budget_tokens is deprecated)
        assert call_json["thinking"] == {"type": "adaptive"}
        assert call_json["output_config"] == {"effort": "high"}
        # Temperature must be 1 for thinking
        assert call_json["temperature"] == 1
        # Response should properly extract thinking vs text
        assert result["success"] is True
        assert result["content"] == "The answer is 42."
        assert result["raw_chars"] > result["answer_chars"]


@pytest.mark.asyncio
async def test_anthropic_sonnet45_manual_thinking():
    """Sonnet 4.5 should use manual thinking with budget_tokens."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=11,
        name="Claude Sonnet 4.5 (Medium Thinking)",
        provider=ProviderType.anthropic,
        base_url="https://api.anthropic.com/v1/messages",
        model_id="claude-sonnet-4-5-20250929",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.medium
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [
                {"type": "thinking", "thinking": "Reasoning..."},
                {"type": "text", "text": "Result."}
            ],
            "usage": {"input_tokens": 50, "output_tokens": 80}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        # Should use manual thinking with budget_tokens
        assert call_json["thinking"]["type"] == "enabled"
        assert call_json["thinking"]["budget_tokens"] == 16000
        assert "output_config" not in call_json
        assert result["success"] is True


@pytest.mark.asyncio
async def test_google_gemini3_thinking_config():
    """Gemini 3.x requests should use thinkingLevel + includeThoughts."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=4,
        name="Gemini 3 Pro",
        provider=ProviderType.google,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_id="gemini-3-pro",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [
                {"thought": True, "text": "Let me think..."},
                {"text": "The answer is 42."}
            ]}}],
            "usageMetadata": {"totalTokenCount": 150, "thoughtsTokenCount": 80, "candidatesTokenCount": 70}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        thinking_config = call_json["generationConfig"]["thinkingConfig"]
        assert thinking_config["includeThoughts"] is True
        assert thinking_config["thinkingLevel"] == "high"
        assert "thinkingBudget" not in thinking_config
        # Verify thinking/answer char split is computed
        assert result["raw_chars"] > result["answer_chars"]


@pytest.mark.asyncio
async def test_google_gemini25_thinking_config():
    """Gemini 2.5 requests should use thinkingBudget + includeThoughts."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=4,
        name="Gemini 2.5 Flash",
        provider=ProviderType.google,
        base_url="https://generativelanguage.googleapis.com/v1beta",
        model_id="gemini-2.5-flash-preview",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "test"}]}}],
            "usageMetadata": {"totalTokenCount": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        thinking_config = call_json["generationConfig"]["thinkingConfig"]
        assert thinking_config["includeThoughts"] is True
        assert thinking_config["thinkingBudget"] == 16384
        assert "thinkingLevel" not in thinking_config


@pytest.mark.asyncio
async def test_grok_41_reasoning_enabled():
    """Grok 4.1 Fast requests should include reasoning.enabled parameter."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=5,
        name="Grok 4.1 Fast",
        provider=ProviderType.grok,
        base_url="https://api.x.ai/v1/chat/completions",
        model_id="grok-4.1-fast",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "reasoning" in call_json
        assert call_json["reasoning"]["enabled"] is True


@pytest.mark.asyncio
async def test_non_reasoning_model():
    """Non-reasoning models should not include reasoning parameters."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=6,
        name="GPT-4",
        provider=ProviderType.openai,
        base_url="https://api.openai.com/v1/chat/completions",
        model_id="gpt-4",
        is_reasoning=0,
        reasoning_level=None
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "test"}}],
            "usage": {"total_tokens": 100}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        await generate(preset, "system", "user")

        call_json = mock_client.post.call_args.kwargs["json"]
        assert "reasoning" not in call_json


def test_adjust_chars_from_reasoning_tokens():
    """OpenAI/Grok reasoning_tokens in usage should adjust raw_chars for TokenBar."""
    from app.core.generators import _adjust_chars_from_reasoning_tokens

    # Simulate: answer is 1000 chars, 200 completion tokens, 150 are reasoning
    result = {"answer_chars": 1000, "raw_chars": 1000}
    data = {
        "usage": {
            "completion_tokens": 200,
            "completion_tokens_details": {"reasoning_tokens": 150}
        }
    }
    _adjust_chars_from_reasoning_tokens(result, data)
    # answer_tokens = 200 - 150 = 50
    # raw_chars = 1000 * 200 / 50 = 4000
    assert result["raw_chars"] == 4000
    assert result["answer_chars"] == 1000  # unchanged


def test_adjust_chars_no_reasoning_tokens():
    """No reasoning_tokens should leave raw_chars unchanged."""
    from app.core.generators import _adjust_chars_from_reasoning_tokens

    result = {"answer_chars": 500, "raw_chars": 500}
    data = {"usage": {"completion_tokens": 100}}
    _adjust_chars_from_reasoning_tokens(result, data)
    assert result["raw_chars"] == 500  # unchanged


def test_adjust_chars_zero_reasoning():
    """Zero reasoning_tokens should leave raw_chars unchanged."""
    from app.core.generators import _adjust_chars_from_reasoning_tokens

    result = {"answer_chars": 500, "raw_chars": 500}
    data = {
        "usage": {
            "completion_tokens": 100,
            "completion_tokens_details": {"reasoning_tokens": 0}
        }
    }
    _adjust_chars_from_reasoning_tokens(result, data)
    assert result["raw_chars"] == 500  # unchanged


def test_adjust_chars_ignores_impossible_answer_token_count():
    """Bogus reasoning token reports should not explode raw_chars."""
    from app.core.generators import _adjust_chars_from_reasoning_tokens

    result = {"answer_chars": 140059, "raw_chars": 140059}
    data = {
        "usage": {
            "completion_tokens": 65536,
            "completion_tokens_details": {"reasoning_tokens": 65535}
        }
    }

    _adjust_chars_from_reasoning_tokens(result, data)

    assert result["raw_chars"] == 140059


@pytest.mark.asyncio
async def test_anthropic_thinking_only_no_text_blocks():
    """When Anthropic returns only thinking blocks and no text blocks,
    result should have thinking_only=True and empty content."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="Sonnet 4.6 Reasoning",
        provider=ProviderType.anthropic,
        base_url="https://api.anthropic.com/v1/messages",
        model_id="claude-sonnet-4-6-20250514",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [
                {"type": "thinking", "thinking": "I need to think about this problem..."}
            ],
            "usage": {"input_tokens": 500, "output_tokens": 64000},
            "stop_reason": "end_turn"
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await generate(preset, "system", "user")

        assert result["success"] is True
        assert result["content"] == ""
        assert result["thinking_only"] is True


@pytest.mark.asyncio
async def test_anthropic_normal_thinking_plus_text():
    """When Anthropic returns both thinking and text blocks,
    thinking_only should be False (or absent)."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="Sonnet 4.6 Reasoning",
        provider=ProviderType.anthropic,
        base_url="https://api.anthropic.com/v1/messages",
        model_id="claude-sonnet-4-6-20250514",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "content": [
                {"type": "thinking", "thinking": "Let me think..."},
                {"type": "text", "text": "Here is the answer."}
            ],
            "usage": {"input_tokens": 500, "output_tokens": 1000},
            "stop_reason": "end_turn"
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await generate(preset, "system", "user")

        assert result["success"] is True
        assert result["content"] == "Here is the answer."
        assert result.get("thinking_only") is not True


@pytest.mark.asyncio
async def test_google_thinking_only_no_answer_parts():
    """When Gemini returns only thought parts and no answer parts,
    result should have thinking_only=True."""
    from app.core.generators import generate

    preset = ModelPreset(
        id=1,
        name="Gemini 2.5 Pro",
        provider=ProviderType.google,
        base_url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent",
        model_id="gemini-2.5-pro",
        is_reasoning=1,
        reasoning_level=ReasoningLevel.high
    )

    with patch('httpx.AsyncClient') as mock_client_class:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [
                        {"thought": True, "text": "Let me think about this coding problem..."}
                    ]
                },
                "finishReason": "MAX_TOKENS"
            }],
            "usageMetadata": {
                "promptTokenCount": 500,
                "candidatesTokenCount": 0,
                "thoughtsTokenCount": 60000,
                "totalTokenCount": 60500
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_response.status_code = 200
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await generate(preset, "system", "user")

        assert result["success"] is True
        assert result["content"] == ""
        assert result["thinking_only"] is True
