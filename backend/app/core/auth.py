"""API key authentication middleware for BeLLMark.

When BELLMARK_API_KEY is set:
  - All /api/* routes require X-API-Key header
  - WebSocket requires auth via first-message JSON frame
  - /health and /api/auth/check remain unauthenticated

When BELLMARK_API_KEY is not set:
  - If BELLMARK_DEV_MODE=true: all routes are open (no authentication required)
  - Otherwise: /api/* routes return 503 (fail-closed)
"""
import asyncio
import json
import logging
import os
import hmac
import warnings

from fastapi import Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)


def _get_api_key() -> str | None:
    """Read the API key from environment. Returns None if not set."""
    key = os.getenv("BELLMARK_API_KEY", "").strip()
    return key if key else None


def is_dev_mode() -> bool:
    """Check whether development mode is enabled via BELLMARK_DEV_MODE."""
    return os.getenv("BELLMARK_DEV_MODE", "").lower() in ("true", "1", "yes")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces API key authentication on /api/* routes."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        api_key = _get_api_key()
        path = request.url.path

        # Skip auth for non-API routes, health check, and auth check
        if not path.startswith("/api/") or path == "/health" or path == "/api/auth/check":
            return await call_next(request)

        if api_key:
            # Key configured: require X-API-Key header
            provided_key = request.headers.get("X-API-Key", "")
            if not provided_key or not hmac.compare_digest(provided_key, api_key):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing API key. Set X-API-Key header."},
                )
        else:
            # No key configured: fail-closed unless dev mode is on
            if not is_dev_mode():
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "BELLMARK_API_KEY required. "
                        "Set BELLMARK_DEV_MODE=true for development."
                    },
                )

        return await call_next(request)


def verify_websocket_token(websocket: WebSocket) -> bool:
    """Verify WebSocket authentication via ?token= query parameter.

    .. deprecated::
        Use :func:`verify_websocket_auth` instead, which authenticates via
        a first-message JSON frame rather than exposing the token in the URL.

    Returns True if auth passes, False if it fails.
    When no BELLMARK_API_KEY is set and dev mode is on, always returns True.
    When no BELLMARK_API_KEY is set and dev mode is off, returns False.
    """
    warnings.warn(
        "verify_websocket_token is deprecated; use verify_websocket_auth instead",
        DeprecationWarning,
        stacklevel=2,
    )
    api_key = _get_api_key()
    if not api_key:
        return is_dev_mode()

    token = websocket.query_params.get("token", "")
    return bool(token) and hmac.compare_digest(token, api_key)


async def verify_websocket_auth(websocket: WebSocket) -> bool:
    """Verify WebSocket authentication via a first-message JSON auth frame.

    Protocol:
        1. Accept the WebSocket connection.
        2. If dev mode is on and no API key is configured, skip auth (return True).
        3. Otherwise, wait up to 5 seconds for a JSON message:
           ``{"type": "auth", "token": "<key>"}``
        4. Validate the token with constant-time comparison.
        5. On success return True; on timeout/invalid close with code 4001 and return False.
    """
    await websocket.accept()

    api_key = _get_api_key()
    if not api_key:
        if is_dev_mode():
            return True
        # No key and no dev mode: fail-closed
        await websocket.close(code=4001, reason="Authentication required")
        return False

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.warning("WebSocket auth timeout — no auth frame received within 5s")
        await websocket.close(code=4001, reason="Auth timeout")
        return False
    except Exception:
        # Connection closed or other error before auth
        return False

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        await websocket.close(code=4001, reason="Invalid auth frame")
        return False

    if not isinstance(data, dict) or data.get("type") != "auth":
        await websocket.close(code=4001, reason="Expected auth frame")
        return False

    token = data.get("token", "")
    if not isinstance(token, str) or not token:
        await websocket.close(code=4001, reason="Missing token")
        return False

    if not hmac.compare_digest(token, api_key):
        await websocket.close(code=4001, reason="Invalid API key")
        return False

    return True
