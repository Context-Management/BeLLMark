import os
from datetime import datetime, timezone

import pytest
from unittest.mock import MagicMock

def test_missing_secret_key_returns_fatal(monkeypatch):
    """_validate_config must return fatal=True when BELLMARK_SECRET_KEY is missing."""
    monkeypatch.delenv("BELLMARK_SECRET_KEY", raising=False)
    from app.main import _validate_config
    warnings, fatal = _validate_config()
    assert fatal is True
    assert any("FATAL" in w or "not set" in w for w in warnings)

def test_short_secret_key_warns(monkeypatch):
    """_validate_config warns on short keys but is not fatal."""
    monkeypatch.setenv("BELLMARK_SECRET_KEY", "short")
    from app.main import _validate_config
    warnings, fatal = _validate_config()
    assert fatal is False
    assert any("too short" in w for w in warnings)

def test_valid_secret_key_no_warnings(monkeypatch):
    """_validate_config returns no warnings for valid key."""
    monkeypatch.setenv("BELLMARK_SECRET_KEY", "a-valid-secret-key-that-is-long-enough")
    from app.main import _validate_config
    warnings, fatal = _validate_config()
    assert fatal is False
    assert len(warnings) == 0


@pytest.mark.asyncio
async def test_startup_does_not_schedule_lmstudio_quant_probe(monkeypatch):
    """Startup should not enqueue background LM Studio quant probing."""
    import sys
    from app import main

    monkeypatch.delenv("BELLMARK_DISABLE_BACKGROUND_RUNS", raising=False)
    monkeypatch.setattr(main, "_validate_config", lambda: ([], False))
    monkeypatch.setattr(main, "_safe_migrate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_check_legacy_keys", lambda _db: [])
    monkeypatch.setattr(main.Base.metadata, "create_all", lambda **_kwargs: None)
    monkeypatch.setattr(main.Path, "exists", lambda _self: False)

    fake_seed_module = MagicMock()
    fake_seed_module.seed_default_suites = lambda: None
    monkeypatch.setitem(sys.modules, "scripts.seed_suites", fake_seed_module)

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return []

    class FakeDB:
        def query(self, *_args, **_kwargs):
            return FakeQuery()

        def close(self):
            pass

    monkeypatch.setattr(main, "SessionLocal", lambda: FakeDB())

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return MagicMock()

    monkeypatch.setattr(main.asyncio, "create_task", fake_create_task)

    await main.startup()

    assert scheduled == []


@pytest.mark.asyncio
async def test_startup_auto_resumes_running_suite_jobs(monkeypatch):
    """Startup should schedule resume tasks for persisted running suite jobs."""
    import sys
    from app import main
    from app.db.models import RunStatus

    monkeypatch.delenv("BELLMARK_DISABLE_BACKGROUND_RUNS", raising=False)
    monkeypatch.setattr(main, "_validate_config", lambda: ([], False))
    monkeypatch.setattr(main, "_safe_migrate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main, "_check_legacy_keys", lambda _db: [])
    monkeypatch.setattr(main.Base.metadata, "create_all", lambda **_kwargs: None)
    monkeypatch.setattr(main.Path, "exists", lambda _self: False)

    fake_seed_module = MagicMock()
    fake_seed_module.seed_default_suites = lambda: None
    monkeypatch.setitem(sys.modules, "scripts.seed_suites", fake_seed_module)

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *_args, **_kwargs):
            return self

        def all(self):
            return self.rows

    class FakeDB:
        def __init__(self):
            self.calls = 0

        def query(self, model, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return FakeQuery([])
            if getattr(model, "__name__", "") == "SuiteGenerationJob":
                # updated_at must be a real datetime: startup computes
                # `age = now - job.updated_at` and compares to SUITE_RESUME_MAX_AGE.
                # A bare MagicMock here causes "MagicMock > timedelta" TypeError.
                # Use a NAIVE datetime — SQLite persists timestamps naive, so
                # production main.py:391 has a naive→UTC coercion branch that we
                # want this test to exercise. A tz-aware mock would skip that
                # branch and let a coercion regression slip through.
                fresh_job = MagicMock(
                    id=42,
                    session_id="suite-session",
                    name="Resumable Suite",
                    status=RunStatus.running,
                    updated_at=datetime.utcnow(),  # naive UTC, mirrors SQLite
                )
                return FakeQuery([fresh_job])
            return FakeQuery([])

        def close(self):
            pass

    fake_db = FakeDB()
    monkeypatch.setattr(main, "SessionLocal", lambda: fake_db)

    scheduled = []

    def fake_create_task(coro):
        scheduled.append(coro)
        coro.close()
        return MagicMock()

    monkeypatch.setattr(main.asyncio, "create_task", fake_create_task)

    await main.startup()

    assert len(scheduled) == 1
