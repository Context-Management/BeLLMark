# backend/tests/test_url_validation.py
"""Tests for SSRF prevention and provider-key exfiltration blocking."""

import os
from unittest.mock import patch, MagicMock
import pytest

from app.core.url_validation import (
    validate_base_url,
    is_canonical_url,
    CANONICAL_HOSTS,
    _is_private_network_host,
)
from app.db.models import ProviderType


# ---------------------------------------------------------------------------
# validate_base_url — canonical URLs pass
# ---------------------------------------------------------------------------

class TestValidateBaseUrl:
    """Tests for validate_base_url()."""

    def test_none_url_passes(self):
        """None means 'use default' and should always pass."""
        assert validate_base_url("openai", None) is None
        assert validate_base_url(ProviderType.anthropic, None) is None

    def test_empty_string_passes(self):
        assert validate_base_url("openai", "") == ""

    def test_canonical_openai(self):
        url = "https://api.openai.com/v1/chat/completions"
        assert validate_base_url("openai", url) == url

    def test_canonical_anthropic(self):
        url = "https://api.anthropic.com/v1/messages"
        assert validate_base_url("anthropic", url) == url

    def test_canonical_google(self):
        url = "https://generativelanguage.googleapis.com/v1beta/models"
        assert validate_base_url("google", url) == url

    def test_canonical_mistral(self):
        url = "https://api.mistral.ai/v1/chat/completions"
        assert validate_base_url("mistral", url) == url

    def test_canonical_deepseek(self):
        url = "https://api.deepseek.com/v1/chat/completions"
        assert validate_base_url("deepseek", url) == url

    def test_canonical_grok(self):
        url = "https://api.x.ai/v1/chat/completions"
        assert validate_base_url("grok", url) == url

    def test_canonical_glm(self):
        url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
        assert validate_base_url("glm", url) == url

    def test_canonical_kimi(self):
        url = "https://api.moonshot.ai/v1/chat/completions"
        assert validate_base_url("kimi", url) == url

    def test_canonical_openrouter(self):
        url = "https://openrouter.ai/api/v1/chat/completions"
        assert validate_base_url("openrouter", url) == url

    # -----------------------------------------------------------------------
    # Evil / non-canonical URLs rejected
    # -----------------------------------------------------------------------

    def test_evil_url_rejected_openai(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("openai", "https://evil.com/v1/chat/completions")

    def test_evil_url_rejected_anthropic(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("anthropic", "https://evil.com/v1/messages")

    def test_evil_url_rejected_google(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("google", "https://evil.com/v1beta/models")

    def test_evil_url_rejected_deepseek(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("deepseek", "https://evil.com/v1/chat/completions")

    def test_evil_url_rejected_mistral(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("mistral", "https://evil.com/v1/chat/completions")

    def test_evil_url_rejected_grok(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("grok", "https://evil.com/v1/chat/completions")

    def test_evil_url_rejected_glm(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("glm", "https://evil.com/api/paas/v4/chat/completions")

    def test_evil_url_rejected_kimi(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("kimi", "https://evil.com/v1/chat/completions")

    def test_evil_url_rejected_openrouter(self):
        with pytest.raises(ValueError, match="does not match"):
            validate_base_url("openrouter", "https://evil.com/api/v1/chat/completions")

    # -----------------------------------------------------------------------
    # HTTP scheme rejected for cloud providers
    # -----------------------------------------------------------------------

    def test_http_rejected_for_cloud_provider(self):
        with pytest.raises(ValueError, match="must use https"):
            validate_base_url("openai", "http://api.openai.com/v1/chat/completions")

    # -----------------------------------------------------------------------
    # Local providers (lmstudio, ollama) — localhost accepted
    # -----------------------------------------------------------------------

    def test_lmstudio_localhost_accepted(self):
        url = "http://localhost:1234/v1/chat/completions"
        assert validate_base_url("lmstudio", url) == url

    def test_lmstudio_127_accepted(self):
        url = "http://127.0.0.1:1234/v1/chat/completions"
        assert validate_base_url("lmstudio", url) == url

    def test_lmstudio_private_ip_accepted(self):
        url = "http://192.168.1.100:1234/v1/chat/completions"
        assert validate_base_url("lmstudio", url) == url

    def test_lmstudio_dot_local_accepted(self):
        url = "http://cachy.local:1234/v1/chat/completions"
        assert validate_base_url("lmstudio", url) == url

    def test_ollama_localhost_accepted(self):
        url = "http://localhost:11434/v1/chat/completions"
        assert validate_base_url("ollama", url) == url

    def test_lmstudio_public_ip_rejected(self):
        with pytest.raises(ValueError, match="private-network"):
            validate_base_url("lmstudio", "http://8.8.8.8:1234/v1/chat/completions")

    def test_lmstudio_external_host_rejected(self):
        with pytest.raises(ValueError, match="private-network"):
            validate_base_url("lmstudio", "http://evil.com:1234/v1/chat/completions")

    def test_ollama_external_host_rejected(self):
        with pytest.raises(ValueError, match="private-network"):
            validate_base_url("ollama", "http://evil.com:11434/v1/chat/completions")

    # -----------------------------------------------------------------------
    # Subdomain matching
    # -----------------------------------------------------------------------

    def test_openai_subdomain_accepted(self):
        url = "https://custom.openai.com/v1/chat/completions"
        assert validate_base_url("openai", url) == url

    # -----------------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------------

    def test_missing_scheme_rejected(self):
        with pytest.raises(ValueError, match="scheme and host"):
            validate_base_url("openai", "api.openai.com/v1/chat/completions")

    def test_provider_type_enum_works(self):
        url = "https://api.openai.com/v1/chat/completions"
        assert validate_base_url(ProviderType.openai, url) == url


# ---------------------------------------------------------------------------
# is_canonical_url
# ---------------------------------------------------------------------------

class TestIsCanonicalUrl:
    """Tests for is_canonical_url()."""

    def test_none_is_canonical(self):
        assert is_canonical_url("openai", None) is True

    def test_empty_is_canonical(self):
        assert is_canonical_url("openai", "") is True

    def test_real_openai_is_canonical(self):
        assert is_canonical_url("openai", "https://api.openai.com/v1/chat/completions") is True

    def test_evil_url_not_canonical(self):
        assert is_canonical_url("openai", "https://evil.com/v1/chat/completions") is False

    def test_http_not_canonical_for_cloud(self):
        assert is_canonical_url("openai", "http://api.openai.com/v1/chat/completions") is False

    def test_lmstudio_localhost_is_canonical(self):
        assert is_canonical_url("lmstudio", "http://localhost:1234/v1/chat/completions") is True

    def test_lmstudio_public_not_canonical(self):
        assert is_canonical_url("lmstudio", "http://evil.com:1234/v1/chat/completions") is False

    def test_ollama_localhost_is_canonical(self):
        assert is_canonical_url("ollama", "http://localhost:11434/v1/chat/completions") is True


# ---------------------------------------------------------------------------
# _is_private_network_host
# ---------------------------------------------------------------------------

class TestIsPrivateNetworkHost:
    def test_localhost(self):
        assert _is_private_network_host("localhost") is True

    def test_127_0_0_1(self):
        assert _is_private_network_host("127.0.0.1") is True

    def test_192_168(self):
        assert _is_private_network_host("192.168.1.100") is True

    def test_10_x(self):
        assert _is_private_network_host("10.0.0.1") is True

    def test_172_16(self):
        assert _is_private_network_host("172.16.0.1") is True

    def test_dot_local(self):
        assert _is_private_network_host("cachy.local") is True

    def test_public_ip(self):
        assert _is_private_network_host("8.8.8.8") is False

    def test_public_domain(self):
        assert _is_private_network_host("evil.com") is False

    def test_cgnat_ip_accepted(self):
        """RFC 6598 shared address space (Tailscale default) is private."""
        assert _is_private_network_host("100.75.83.124") is True

    def test_unqualified_name_resolving_to_private_accepted(self):
        """Single-label names (e.g. 'mini' via /etc/hosts) pass when the
        resolved address is private."""
        with patch(
            "app.core.url_validation.socket.gethostbyname",
            return_value="192.168.0.112",
        ):
            assert _is_private_network_host("mini") is True

    def test_unqualified_name_resolving_to_cgnat_accepted(self):
        """Tailscale MagicDNS-style resolution to 100.64/10 must pass."""
        with patch(
            "app.core.url_validation.socket.gethostbyname",
            return_value="100.75.83.124",
        ):
            assert _is_private_network_host("mini") is True

    def test_unqualified_name_resolving_to_public_rejected(self):
        """A non-local name that resolves to a public IP must still fail."""
        with patch(
            "app.core.url_validation.socket.gethostbyname",
            return_value="8.8.8.8",
        ):
            assert _is_private_network_host("evil-short") is False

    def test_unresolvable_name_rejected(self):
        """If the name doesn't resolve at all, reject conservatively."""
        with patch(
            "app.core.url_validation.socket.gethostbyname",
            side_effect=OSError("unknown host"),
        ):
            assert _is_private_network_host("definitely-not-a-host") is False

    def test_lmstudio_mini_hostname_accepted(self):
        """End-to-end: 'http://mini:1234' works when mini resolves privately."""
        with patch(
            "app.core.url_validation.socket.gethostbyname",
            return_value="192.168.0.112",
        ):
            url = "http://mini:1234/v1/chat/completions"
            assert validate_base_url("lmstudio", url) == url


# ---------------------------------------------------------------------------
# Key fallback denied for non-canonical URLs (integration-style)
# ---------------------------------------------------------------------------

class TestKeyFallbackDenied:
    """Verify _resolve_api_key blocks env key for non-canonical URLs."""

    def test_env_key_allowed_for_canonical_url(self):
        from app.core.generators import _resolve_api_key

        preset = MagicMock()
        preset.name = "Test OpenAI"
        preset.provider = ProviderType.openai
        preset.base_url = "https://api.openai.com/v1/chat/completions"
        preset.api_key_encrypted = None

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-123"}):
            key = _resolve_api_key(preset, "OPENAI_API_KEY")
            assert key == "sk-test-123"

    def test_env_key_allowed_for_none_url(self):
        from app.core.generators import _resolve_api_key

        preset = MagicMock()
        preset.name = "Test OpenAI"
        preset.provider = ProviderType.openai
        preset.base_url = None
        preset.api_key_encrypted = None

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-123"}):
            key = _resolve_api_key(preset, "OPENAI_API_KEY")
            assert key == "sk-test-123"

    def test_env_key_denied_for_custom_url(self):
        from app.core.generators import _resolve_api_key, GenerationError

        preset = MagicMock()
        preset.name = "Evil Preset"
        preset.provider = ProviderType.openai
        preset.base_url = "https://evil.com/v1/chat/completions"
        preset.api_key_encrypted = None

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-123"}):
            with pytest.raises(GenerationError, match="custom base_url"):
                _resolve_api_key(preset, "OPENAI_API_KEY")

    def test_preset_key_used_for_custom_url(self):
        """Per-preset key is always used, even with custom URL."""
        from app.core.generators import _resolve_api_key

        preset = MagicMock()
        preset.name = "Custom Preset"
        preset.provider = ProviderType.openai
        preset.base_url = "https://evil.com/v1/chat/completions"
        preset.api_key_encrypted = "encrypted-blob"

        with patch("app.core.generators.decrypt_api_key", return_value="sk-custom-456"):
            key = _resolve_api_key(preset, "OPENAI_API_KEY")
            assert key == "sk-custom-456"

    def test_lmstudio_localhost_no_key_ok(self):
        """LM Studio on localhost needs no API key."""
        from app.core.generators import _resolve_api_key

        preset = MagicMock()
        preset.name = "Local LM Studio"
        preset.provider = ProviderType.lmstudio
        preset.base_url = "http://localhost:1234/v1/chat/completions"
        preset.api_key_encrypted = None

        # LM Studio has no env key — should not raise
        key = _resolve_api_key(preset, "LMSTUDIO_API_KEY")
        assert key is None
