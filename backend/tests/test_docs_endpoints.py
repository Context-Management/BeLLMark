"""Tests for FastAPI docs/OpenAPI endpoint visibility based on dev mode.

FastAPI sets docs_url, redoc_url, and openapi_url at app creation time,
so we cannot test them by toggling env vars on the shared `app` instance.
Instead we create minimal FastAPI apps with the same conditional logic
used in main.py and verify the behaviour.
"""
import os
import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _create_app(dev_mode: bool) -> FastAPI:
    """Create a minimal FastAPI app mimicking main.py's docs_url logic."""
    return FastAPI(
        title="BeLLMark-Test",
        docs_url="/docs" if dev_mode else None,
        redoc_url="/redoc" if dev_mode else None,
        openapi_url="/openapi.json" if dev_mode else None,
    )


class TestDocsDisabledInProduction:
    """When dev mode is OFF, /docs, /redoc, and /openapi.json must return 404."""

    @pytest.fixture()
    def prod_client(self):
        app = _create_app(dev_mode=False)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        return TestClient(app)

    def test_docs_returns_404(self, prod_client):
        response = prod_client.get("/docs")
        assert response.status_code == 404

    def test_redoc_returns_404(self, prod_client):
        response = prod_client.get("/redoc")
        assert response.status_code == 404

    def test_openapi_json_returns_404(self, prod_client):
        response = prod_client.get("/openapi.json")
        assert response.status_code == 404

    def test_health_still_works(self, prod_client):
        response = prod_client.get("/health")
        assert response.status_code == 200


class TestDocsEnabledInDevMode:
    """When dev mode is ON, /docs, /redoc, and /openapi.json must be accessible."""

    @pytest.fixture()
    def dev_client(self):
        app = _create_app(dev_mode=True)

        @app.get("/health")
        def health():
            return {"status": "ok"}

        return TestClient(app)

    def test_docs_returns_200(self, dev_client):
        response = dev_client.get("/docs")
        assert response.status_code == 200

    def test_redoc_returns_200(self, dev_client):
        response = dev_client.get("/redoc")
        assert response.status_code == 200

    def test_openapi_json_returns_200(self, dev_client):
        response = dev_client.get("/openapi.json")
        assert response.status_code == 200


class TestMainAppDocsIntegration:
    """Verify that the actual main.py app respects BELLMARK_DEV_MODE for docs.

    The conftest sets BELLMARK_DEV_MODE=true before the app module is imported,
    so the shared `app` instance should have docs enabled.
    """

    def test_shared_app_has_docs_in_dev_mode(self):
        """The test-suite app (imported with DEV_MODE=true) exposes docs."""
        from app.main import app as main_app
        # conftest.py sets BELLMARK_DEV_MODE=true at import time, but main.py's
        # FastAPI constructor runs once at module load. If the env was set before
        # import, docs should be available.
        # The env var is set in conftest.py before main.py is imported by test
        # infrastructure, so docs_url should be "/docs".
        assert main_app.docs_url == "/docs"
        assert main_app.redoc_url == "/redoc"
        assert main_app.openapi_url == "/openapi.json"

    def test_is_dev_mode_drives_constructor(self):
        """is_dev_mode() is the function used in main.py's FastAPI constructor."""
        from app.core.auth import is_dev_mode

        with patch.dict(os.environ, {"BELLMARK_DEV_MODE": "true"}):
            assert is_dev_mode() is True

        with patch.dict(os.environ, {}, clear=True):
            assert is_dev_mode() is False
