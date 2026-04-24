"""Tests for API key authentication middleware."""
import pytest
from fastapi.testclient import TestClient


# ── Existing tests (dev mode enabled via client fixture) ──────────────────


def test_no_auth_when_key_not_set(client):
    """When BELLMARK_API_KEY is not set and dev mode is on, all routes should be accessible."""
    response = client.get("/api/models/")
    assert response.status_code == 200


def test_no_auth_write_allowed_when_key_not_set(client):
    """When BELLMARK_API_KEY is not set and dev mode is on, write operations should work."""
    response = client.post("/api/models/", json={
        "name": "Test",
        "provider": "lmstudio",
        "base_url": "http://localhost:1234",
        "model_id": "test-model",
    })
    # 200 or 201 — not 401 or 503
    assert response.status_code not in (401, 503)


def test_health_always_accessible(client, monkeypatch):
    """Health endpoint should never require auth."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    response = client.get("/health")
    assert response.status_code == 200


def test_auth_check_always_accessible(client, monkeypatch):
    """Auth check endpoint should never require auth."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    response = client.get("/api/auth/check")
    assert response.status_code == 200
    assert response.json()["auth_required"] is True


def test_auth_check_reports_no_auth(client, monkeypatch):
    """Auth check reports no auth when key is not set."""
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)
    response = client.get("/api/auth/check")
    assert response.status_code == 200
    assert response.json()["auth_required"] is False


def test_auth_check_includes_dev_mode(client, monkeypatch):
    """Auth check response includes dev_mode field."""
    monkeypatch.setenv("BELLMARK_DEV_MODE", "true")
    response = client.get("/api/auth/check")
    assert response.status_code == 200
    assert response.json()["dev_mode"] is True

    monkeypatch.delenv("BELLMARK_DEV_MODE", raising=False)
    response = client.get("/api/auth/check")
    assert response.json()["dev_mode"] is False


def test_unauthenticated_returns_401(client, monkeypatch):
    """When API key is set, unauthenticated /api/ requests return 401."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    response = client.get("/api/models/")
    assert response.status_code == 401


def test_wrong_key_returns_401(client, monkeypatch):
    """Wrong API key returns 401."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    response = client.get(
        "/api/models/",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_correct_key_returns_200(client, monkeypatch):
    """Correct API key allows access."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    response = client.get(
        "/api/models/",
        headers={"X-API-Key": "test-secret-key"},
    )
    assert response.status_code == 200


def test_websocket_no_auth_when_key_not_set(client):
    """WebSocket should connect without auth frame when no key is set and dev mode is on."""
    with client.websocket_connect("/ws/runs/999") as ws:
        pass  # Connection will close naturally


def test_websocket_rejected_without_auth_frame(client, monkeypatch):
    """WebSocket should be closed when key is set but no auth frame sent (timeout)."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    try:
        with client.websocket_connect("/ws/runs/999") as ws:
            # Don't send auth frame — server should close the connection
            data = ws.receive_json()
            pytest.fail("Should have been closed by server")
    except Exception:
        pass  # Expected — connection closed with 4001


def test_websocket_rejected_with_wrong_token(client, monkeypatch):
    """WebSocket should be closed when auth frame has wrong token."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    try:
        with client.websocket_connect("/ws/runs/999") as ws:
            ws.send_json({"type": "auth", "token": "wrong-key"})
            data = ws.receive_json()
            pytest.fail("Should have been closed by server")
    except Exception:
        pass  # Expected — connection closed with 4001


def test_websocket_accepted_with_correct_auth_frame(client, monkeypatch):
    """WebSocket should stay open with correct auth frame."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    with client.websocket_connect("/ws/runs/999") as ws:
        ws.send_json({"type": "auth", "token": "test-secret-key"})
        # Connection should stay open — no close exception


def test_authenticated_client_fixture(authenticated_client):
    """The authenticated_client fixture should pass auth automatically."""
    response = authenticated_client.get("/api/models/")
    assert response.status_code == 200


def test_suite_generation_websocket_rejected_without_auth_frame(client, monkeypatch):
    """Suite generation WebSocket should be closed when key is set but no auth frame sent."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    try:
        with client.websocket_connect("/ws/suite-generate/some-session-id") as ws:
            data = ws.receive_json()
            pytest.fail("Should have been closed by server")
    except Exception:
        pass  # Expected


def test_suite_generation_websocket_accepted_with_correct_auth_frame(client, monkeypatch):
    """Suite generation WebSocket should stay open with correct auth frame."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    with client.websocket_connect("/ws/suite-generate/some-session-id") as ws:
        ws.send_json({"type": "auth", "token": "test-secret-key"})
        # Server will close with 4404 (session not found) — but that's after successful auth
        pass


# ── Fail-closed tests (no dev mode, no API key) ──────────────────────────


def test_no_key_no_dev_mode_returns_503(client, monkeypatch):
    """Without dev mode and without API key, /api/* routes return 503."""
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)
    monkeypatch.delenv("BELLMARK_DEV_MODE", raising=False)
    response = client.get("/api/models/")
    assert response.status_code == 503
    assert "BELLMARK_API_KEY required" in response.json()["detail"]
    assert "BELLMARK_DEV_MODE" in response.json()["detail"]


def test_no_key_dev_mode_passes_through(client, monkeypatch):
    """With dev mode enabled and without API key, /api/* routes pass through."""
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)
    monkeypatch.setenv("BELLMARK_DEV_MODE", "true")
    response = client.get("/api/models/")
    assert response.status_code == 200


def test_no_key_dev_mode_variants(client, monkeypatch):
    """Dev mode accepts various truthy values: true, 1, yes (case-insensitive)."""
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)

    for value in ("true", "True", "TRUE", "1", "yes", "Yes", "YES"):
        monkeypatch.setenv("BELLMARK_DEV_MODE", value)
        response = client.get("/api/models/")
        assert response.status_code == 200, f"BELLMARK_DEV_MODE={value} should allow passthrough"


def test_no_key_dev_mode_false_returns_503(client, monkeypatch):
    """Dev mode with falsy values still returns 503."""
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)

    for value in ("false", "0", "no", ""):
        monkeypatch.setenv("BELLMARK_DEV_MODE", value)
        response = client.get("/api/models/")
        assert response.status_code == 503, f"BELLMARK_DEV_MODE={value!r} should block requests"


def test_api_key_set_overrides_dev_mode(client, monkeypatch):
    """When API key is set, auth enforcement works regardless of dev mode."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-secret-key")
    monkeypatch.setenv("BELLMARK_DEV_MODE", "true")

    # Without header: 401 (not 503, not 200)
    response = client.get("/api/models/")
    assert response.status_code == 401

    # With correct header: 200
    response = client.get("/api/models/", headers={"X-API-Key": "test-secret-key"})
    assert response.status_code == 200


def test_health_accessible_without_key_or_dev_mode(client, monkeypatch):
    """Health endpoint is accessible even when fail-closed is active."""
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)
    monkeypatch.delenv("BELLMARK_DEV_MODE", raising=False)
    response = client.get("/health")
    assert response.status_code == 200


def test_auth_check_accessible_without_key_or_dev_mode(client, monkeypatch):
    """Auth check endpoint is accessible even when fail-closed is active."""
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)
    monkeypatch.delenv("BELLMARK_DEV_MODE", raising=False)
    response = client.get("/api/auth/check")
    assert response.status_code == 200
    assert response.json()["auth_required"] is False
    assert response.json()["dev_mode"] is False


def test_websocket_rejected_without_key_or_dev_mode(client, monkeypatch):
    """WebSocket should be closed when no API key and no dev mode (fail-closed)."""
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)
    monkeypatch.delenv("BELLMARK_DEV_MODE", raising=False)
    try:
        with client.websocket_connect("/ws/runs/999") as ws:
            data = ws.receive_json()
            pytest.fail("Should have been closed by server")
    except Exception:
        pass  # Expected — connection closed with 4001


# ── is_dev_mode unit tests ───────────────────────────────────────────────


def test_is_dev_mode_function(monkeypatch):
    """is_dev_mode() correctly reads BELLMARK_DEV_MODE env var."""
    from app.core.auth import is_dev_mode

    monkeypatch.setenv("BELLMARK_DEV_MODE", "true")
    assert is_dev_mode() is True

    monkeypatch.setenv("BELLMARK_DEV_MODE", "1")
    assert is_dev_mode() is True

    monkeypatch.setenv("BELLMARK_DEV_MODE", "yes")
    assert is_dev_mode() is True

    monkeypatch.setenv("BELLMARK_DEV_MODE", "false")
    assert is_dev_mode() is False

    monkeypatch.delenv("BELLMARK_DEV_MODE", raising=False)
    assert is_dev_mode() is False
