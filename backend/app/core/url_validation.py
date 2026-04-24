# backend/app/core/url_validation.py
"""
SSRF and provider-key exfiltration prevention.

Validates that model preset base_url values match the expected canonical hosts
for each provider.  Blocks server-held API key fallback when a custom
(non-canonical) base_url is configured, preventing an attacker from pointing
a preset at their own endpoint and capturing the operator's API key.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse
from typing import Optional

from app.db.models import ProviderType


# RFC 6598 shared address space — used by carrier-grade NAT and Tailscale's
# default tailnet range (100.64.0.0/10). Treated as "private" for SSRF
# purposes: addresses here are never routable on the public internet.
_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")


# ---------------------------------------------------------------------------
# Canonical host patterns per provider
# ---------------------------------------------------------------------------
# Each value is a set of *lowercase* host patterns.
# A pattern can be:
#   - An exact hostname: "api.openai.com"
#   - A suffix starting with ".": ".openai.com"  (matches any subdomain)
#
# Providers whose traffic normally stays on a private network (lmstudio,
# ollama) are NOT listed here — they are validated separately via
# _is_private_network_url().

CANONICAL_HOSTS: dict[str, set[str]] = {
    "anthropic": {"api.anthropic.com", ".anthropic.com"},
    "openai": {"api.openai.com", ".openai.com"},
    "google": {
        "generativelanguage.googleapis.com",
        ".googleapis.com",
    },
    "mistral": {"api.mistral.ai", ".mistral.ai"},
    "deepseek": {"api.deepseek.com", ".deepseek.com"},
    "grok": {"api.x.ai", ".x.ai"},
    "glm": {"open.bigmodel.cn", ".bigmodel.cn"},
    "kimi": {"api.moonshot.ai", ".moonshot.ai", "api.moonshot.cn", ".moonshot.cn"},
    "openrouter": {"openrouter.ai", ".openrouter.ai"},
}

# Providers that are expected to run on the local / private network.
_LOCAL_PROVIDERS: set[str] = {"lmstudio", "ollama"}

# Environment variable names keyed by provider value.
PROVIDER_ENV_KEYS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "grok": "GROK_API_KEY",
    "glm": "GLM_API_KEY",
    "kimi": "KIMI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _addr_is_private(addr: ipaddress._BaseAddress) -> bool:
    """Return True for loopback / RFC-1918 / link-local / CGNAT addresses."""
    if addr.is_loopback or addr.is_private or addr.is_link_local:
        return True
    if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT_NETWORK:
        return True
    return False


def _is_private_network_host(hostname: str) -> bool:
    """Return True if *hostname* is a loopback / private / link-local / CGNAT
    address, or resolves (via /etc/hosts, mDNS, or DNS) to one.

    ``.local`` names are accepted without resolution since mDNS lookups may
    not work in every execution context.
    """
    if hostname == "localhost" or hostname.startswith("localhost:"):
        return True

    # Strip port if present (``urlparse`` puts host:port in ``netloc`` but
    # we split it ourselves when calling this helper).
    host_only = hostname.split(":")[0]

    if host_only == "localhost":
        return True

    try:
        return _addr_is_private(ipaddress.ip_address(host_only))
    except ValueError:
        pass

    # Heuristic: common local mDNS names (.local)
    if host_only.endswith(".local"):
        return True

    # Resolve single-label / unqualified / MagicDNS names (e.g. ``mini``,
    # ``cachy``, Tailscale MagicDNS aliases) and accept only if the resolved
    # address is on a trusted private / CGNAT range. Public names resolve to
    # routable addresses and still fail this check.
    try:
        resolved = socket.gethostbyname(host_only)
    except OSError:
        return False
    try:
        return _addr_is_private(ipaddress.ip_address(resolved))
    except ValueError:
        return False


def _host_matches_patterns(hostname: str, patterns: set[str]) -> bool:
    """Check whether *hostname* matches any entry in *patterns*."""
    hostname = hostname.lower()
    for pat in patterns:
        if pat.startswith("."):
            # Suffix match (subdomain)
            if hostname == pat[1:] or hostname.endswith(pat):
                return True
        else:
            if hostname == pat:
                return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_base_url(provider: str | ProviderType, url: str | None) -> str | None:
    """Validate *url* for the given *provider*.

    Returns the (possibly unchanged) URL on success, or raises ``ValueError``
    with a human-readable message on failure.

    Rules:
    * ``None`` / empty string → allowed (use provider default).
    * ``lmstudio`` / ``ollama`` → must be http(s) with a private-network host.
    * All other providers → must be ``https`` and the host must match the
      provider's ``CANONICAL_HOSTS`` entry.
    """
    if not url:
        return url

    prov = provider.value if isinstance(provider, ProviderType) else str(provider)

    # --- Parse ---------------------------------------------------------------
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Malformed URL: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower()

    if not scheme or not hostname:
        raise ValueError(f"URL must include scheme and host (got {url!r})")

    # --- Local providers (lmstudio, ollama) ----------------------------------
    if prov in _LOCAL_PROVIDERS:
        if scheme not in ("http", "https"):
            raise ValueError(
                f"{prov} base_url must use http or https (got {scheme!r})"
            )
        if not _is_private_network_host(hostname):
            raise ValueError(
                f"{prov} base_url must point to localhost or a private-network "
                f"host (got {hostname!r})"
            )
        return url

    # --- Cloud providers -----------------------------------------------------
    if scheme != "https":
        raise ValueError(
            f"{prov} base_url must use https (got {scheme!r})"
        )

    patterns = CANONICAL_HOSTS.get(prov)
    if patterns and not _host_matches_patterns(hostname, patterns):
        raise ValueError(
            f"{prov} base_url host {hostname!r} does not match any known "
            f"canonical host for this provider. "
            f"Expected one of: {sorted(p.lstrip('.') for p in patterns)}"
        )

    return url


def is_canonical_url(provider: str | ProviderType, url: str | None) -> bool:
    """Return ``True`` if *url* is ``None`` (default endpoint) or matches the
    provider's canonical host pattern.

    Used at generation time to decide whether it is safe to fall back to the
    server-held environment API key.  A ``True`` return means the request will
    go to the real provider, so the key is safe to use.
    """
    if not url:
        return True

    prov = provider.value if isinstance(provider, ProviderType) else str(provider)

    # Local providers always target private networks — no key exfil risk.
    if prov in _LOCAL_PROVIDERS:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        return _is_private_network_host(hostname)

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()

    if scheme != "https":
        return False

    patterns = CANONICAL_HOSTS.get(prov)
    if not patterns:
        # Unknown provider with a URL — treat as non-canonical for safety.
        return False

    return _host_matches_patterns(hostname, patterns)
