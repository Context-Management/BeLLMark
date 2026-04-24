"""Per-provider concurrency defaults and resolution logic."""
from __future__ import annotations

import asyncio
import socket
from urllib.parse import urlparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

PROVIDER_DEFAULTS: dict[str, int] = {
    "anthropic": 3,
    "openai": 5,
    "google": 3,
    "mistral": 3,
    "deepseek": 5,
    "grok": 5,
    "glm": 2,
    "kimi": 1,
    "openrouter": 5,
    "lmstudio": 1,
    "ollama": 1,
}

LOCAL_PROVIDERS = {"lmstudio", "ollama"}

# Cache resolved IPs (shared with runner.py's existing cache)
_resolved_ip_cache: dict[str, str] = {}


async def _resolve_server_key(base_url: str, provider: str) -> str:
    """Resolve a local server base_url to a canonical key via DNS.
    Same logic as runner.py _resolve_lmstudio_server_key().
    """
    parsed = urlparse(base_url)
    hostname = parsed.hostname or parsed.netloc
    port = parsed.port or 1234
    cache_key = f"{hostname}:{port}"

    if cache_key not in _resolved_ip_cache:
        try:
            loop = asyncio.get_event_loop()
            infos = await loop.getaddrinfo(hostname, port, family=socket.AF_INET)
            ip = infos[0][4][0] if infos else hostname
            _resolved_ip_cache[cache_key] = f"{provider}_{ip}:{port}"
        except (socket.gaierror, OSError):
            _resolved_ip_cache[cache_key] = f"{provider}_{cache_key}"
    return _resolved_ip_cache[cache_key]


def resolve_concurrency_key_sync(provider: str, base_url: str | None) -> tuple[str, str | None]:
    """Synchronous key resolution (for API layer). Local providers use raw base_url as key."""
    if provider in LOCAL_PROVIDERS and base_url:
        return (provider, base_url)
    return (provider, None)


def resolve_concurrency_key(provider: str, base_url: str | None) -> tuple[str, str | None]:
    """Resolve concurrency key. For tests and sync code."""
    return resolve_concurrency_key_sync(provider, base_url)


async def resolve_concurrency_key_async(provider: str, base_url: str | None) -> tuple[str, str | None]:
    """Async key resolution with DNS lookup for local providers."""
    if provider in LOCAL_PROVIDERS and base_url:
        server_key = await _resolve_server_key(base_url, provider)
        return (provider, server_key)
    return (provider, None)


def get_effective_concurrency(db: "Session", provider: str, server_key: str | None) -> int:
    """Look up override from DB, fall back to provider default."""
    from app.db.models import ConcurrencySetting

    row = db.query(ConcurrencySetting).filter(
        ConcurrencySetting.provider == provider,
        ConcurrencySetting.server_key == server_key,
    ).first()

    if row:
        return row.max_concurrency
    return PROVIDER_DEFAULTS.get(provider, 3)
