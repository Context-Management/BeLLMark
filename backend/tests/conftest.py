# backend/tests/conftest.py
import os
os.environ["BELLMARK_DISABLE_BACKGROUND_RUNS"] = "1"
os.environ.setdefault("BELLMARK_SECRET_KEY", "test-secret-key")
# Enable dev mode before app import so FastAPI constructor exposes docs endpoints
os.environ.setdefault("BELLMARK_DEV_MODE", "true")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import AsyncMock, patch

from app.main import app
from app.db.database import Base, get_db


@pytest.fixture(autouse=True)
def db_session():
    """Create a fresh in-memory database for every test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def benchmark_validation_default():
    """Default benchmark validation to no-op unless a test overrides it explicitly."""
    with patch("app.api.benchmarks.validate_run_local_presets", new=AsyncMock(return_value=[])):
        yield


@pytest.fixture(autouse=True)
def _reset_aggregate_leaderboard_cache():
    """The aggregate leaderboard endpoint caches its response in module-level
    state for performance. Across tests this cache would survive (each test gets
    a fresh in-memory DB but the same Python process), causing stale data from
    one test to be served to the next. Invalidate before each test."""
    from app.api.elo import invalidate_aggregate_leaderboard_cache
    invalidate_aggregate_leaderboard_cache()
    yield


@pytest.fixture()
def client(monkeypatch):
    """Provide a TestClient that uses the current test's DB override.

    Clears BELLMARK_API_KEY by default so tests start with auth disabled.
    Sets BELLMARK_DEV_MODE=true so the fail-closed middleware allows passthrough.
    Use monkeypatch.setenv("BELLMARK_API_KEY", ...) in the test to enable auth.
    """
    monkeypatch.delenv("BELLMARK_API_KEY", raising=False)
    monkeypatch.setenv("BELLMARK_DEV_MODE", "true")
    return TestClient(app)


@pytest.fixture()
def authenticated_client(monkeypatch):
    """Provide a TestClient with API key authentication enabled and headers set."""
    monkeypatch.setenv("BELLMARK_API_KEY", "test-api-key")
    monkeypatch.setenv("BELLMARK_DEV_MODE", "true")
    return TestClient(app, headers={"X-API-Key": "test-api-key"})
