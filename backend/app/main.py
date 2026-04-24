# backend/app/main.py
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import json
import os
import shutil
import asyncio
import logging
from typing import Dict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from alembic.config import Config
from alembic import command
from sqlalchemy import text, inspect

from app.db.database import engine, Base, SessionLocal, get_db
from app.db.models import BenchmarkRun, ModelPreset, RunStatus, SuiteGenerationJob, TaskStatus, Generation, Judgment
from app.core.crypto import is_legacy_ciphertext
from app.api.models import router as models_router
from app.api.benchmarks import router as benchmarks_router, resume_benchmark_task
from app.api.question_browser import router as question_browser_router
from app.api.questions import router as questions_router
from app.api.results import router as results_router
from app.api.criteria import router as criteria_router
from app.api.suites import router as suites_router
from app.api.attachments import router as attachments_router
from app.api.elo import router as elo_router
from app.api.concurrency import router as concurrency_router
from app.ws.progress import manager
from app.ws.suite_progress import suite_manager
from app.core.runner import active_runners
from app.core.suite_pipeline import active_suite_pipelines
from app.api.suites import (
    active_suite_pipeline_tasks,
    cancel_suite_generation_session,
    resume_suite_generation_task,
)

# Configure root logger so all modules' log messages reach stdout/journalctl
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

def _read_version() -> str:
    for path in [Path(__file__).resolve().parent.parent.parent / "VERSION", Path("/app/VERSION")]:
        if path.is_file():
            return path.read_text().strip()
    return "dev"

APP_VERSION = _read_version()

from app.core.auth import is_dev_mode as _is_dev_mode_startup

app = FastAPI(
    title="BeLLMark",
    version=APP_VERSION,
    docs_url="/docs" if _is_dev_mode_startup() else None,
    redoc_url="/redoc" if _is_dev_mode_startup() else None,
    openapi_url="/openapi.json" if _is_dev_mode_startup() else None,
)

# CORS: restrict to known origins (configurable via ALLOWED_ORIGINS env var).
#   Unset or sentinel → use localhost defaults.
#   Set-but-empty   → lock down (allow_origins=[]).
#   Any other value → comma-separated origin list.
# The sentinel (_CORS_UNSET_SENTINEL) lets docker-compose distinguish "host did
# not set this var" from "host explicitly set it to empty" using the portable
# `${ALLOWED_ORIGINS-<sentinel>}` (single-dash) expansion. See docker-compose.yml.
_default_origins = "http://localhost:5173,http://localhost:8000,http://localhost:3000"
_CORS_UNSET_SENTINEL = "__BELLMARK_DEFAULT_CORS__"
_raw_cors = os.getenv("ALLOWED_ORIGINS")
if _raw_cors is None or _raw_cors == _CORS_UNSET_SENTINEL:
    _raw_cors = _default_origins
ALLOWED_ORIGINS = [o.strip() for o in _raw_cors.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.core.auth import APIKeyMiddleware, verify_websocket_auth, is_dev_mode

app.add_middleware(APIKeyMiddleware)

app.include_router(models_router)
app.include_router(benchmarks_router)
app.include_router(question_browser_router)
app.include_router(questions_router)
app.include_router(results_router)
app.include_router(criteria_router)
app.include_router(suites_router)
app.include_router(attachments_router)
app.include_router(elo_router)
app.include_router(concurrency_router)

def _validate_config() -> tuple[list[str], bool]:
    """Validate configuration on startup. Returns (warnings, fatal)."""
    warnings = []
    fatal = False

    secret_key = os.getenv("BELLMARK_SECRET_KEY")
    if not secret_key:
        warnings.append(
            "FATAL: BELLMARK_SECRET_KEY environment variable is not set. "
            "API key encryption requires this key. Set it before starting BeLLMark. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )
        fatal = True
    elif len(secret_key) < 16:
        warnings.append(
            "WARNING: BELLMARK_SECRET_KEY is too short (< 16 chars). "
            "Use a longer key for security."
        )
    return warnings, fatal


def _check_legacy_keys(db) -> list[str]:
    """Check for model presets still using legacy fixed-salt encryption."""
    warnings = []
    secret_key = os.getenv("BELLMARK_SECRET_KEY")
    if not secret_key:
        return warnings  # Can't check without secret key

    presets = db.query(ModelPreset).filter(
        ModelPreset.api_key_encrypted.isnot(None)
    ).all()

    legacy_names = [
        p.name for p in presets
        if p.api_key_encrypted and is_legacy_ciphertext(p.api_key_encrypted)
    ]

    if legacy_names:
        warnings.append(
            f"WARNING: {len(legacy_names)} model preset(s) use legacy encryption "
            f"({', '.join(legacy_names)}). "
            f"API keys will fail to decrypt until migrated. "
            f"Run: cd backend && python -m app.core.crypto_migration"
        )

    return warnings


# Maximum number of rolling backups to keep
_MAX_BACKUPS = 5


def _resolve_db_path() -> Path:
    """Resolve the actual database file path from the engine URL."""
    url = str(engine.url)
    # sqlite:///./bellmark.db → ./bellmark.db (relative to CWD)
    if url.startswith("sqlite:///"):
        raw = url[len("sqlite:///"):]
        return Path(raw).resolve()
    return Path("bellmark.db").resolve()


def _backup_database(db_path: Path) -> Path | None:
    """Create a timestamped backup of the database before migration.

    Keeps up to _MAX_BACKUPS rolling backups, deleting the oldest.
    Returns the backup path, or None if the DB file doesn't exist or is empty.
    """
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None

    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{db_path.stem}_{timestamp}{db_path.suffix}"

    shutil.copy2(db_path, backup_path)

    # Also copy WAL/SHM if they exist (SQLite WAL mode)
    for suffix in ["-wal", "-shm"]:
        wal_file = db_path.parent / f"{db_path.name}{suffix}"
        if wal_file.exists():
            shutil.copy2(wal_file, backup_dir / f"{backup_path.name}{suffix}")

    logger.info(f"Database backup created: {backup_path}")
    print(f"[STARTUP] Database backup: {backup_path}")

    # Prune old backups (keep newest _MAX_BACKUPS)
    backups = sorted(backup_dir.glob(f"{db_path.stem}_*{db_path.suffix}"), reverse=True)
    for old_backup in backups[_MAX_BACKUPS:]:
        old_backup.unlink(missing_ok=True)
        # Clean up associated WAL/SHM backups
        for suffix in ["-wal", "-shm"]:
            associated = backup_dir / f"{old_backup.name}{suffix}"
            associated.unlink(missing_ok=True)

    return backup_path


def _count_rows(db_path: Path) -> int:
    """Count total data rows across key tables. Used for sanity checks."""
    import sqlite3
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    total = 0
    _ALLOWED_TABLES = {"benchmark_runs", "model_presets", "generations", "judgments"}
    for table in _ALLOWED_TABLES:
        try:
            total += conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608 — table name from hardcoded set above
        except sqlite3.OperationalError:
            pass  # Table doesn't exist yet
    conn.close()
    return total


def _safe_migrate(alembic_ini_path: Path) -> None:
    """Run Alembic migrations with backup and post-migration integrity check.

    Protection layers:
    1. Pre-migration backup (timestamped, rolling)
    2. Row count sanity check (abort if data vanishes)
    3. Full exception handling (restore from backup on failure)
    """
    db_path = _resolve_db_path()
    rows_before = _count_rows(db_path)
    backup_path = _backup_database(db_path)

    alembic_cfg = Config(str(alembic_ini_path))

    try:
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        logger.error(f"Migration FAILED: {e}")
        print(f"[STARTUP] Migration FAILED: {e}")
        if backup_path and backup_path.exists():
            logger.error(f"Restoring database from backup: {backup_path}")
            print(f"[STARTUP] RESTORING from backup: {backup_path}")
            shutil.copy2(backup_path, db_path)
            for suffix in ["-wal", "-shm"]:
                backup_wal = backup_path.parent / f"{backup_path.name}{suffix}"
                if backup_wal.exists():
                    shutil.copy2(backup_wal, db_path.parent / f"{db_path.name}{suffix}")
        raise

    # Post-migration sanity check: detect data loss
    rows_after = _count_rows(db_path)
    if rows_before > 10 and rows_after == 0:
        logger.critical(
            f"DATA LOSS DETECTED: {rows_before} rows before migration, "
            f"{rows_after} after. Restoring from backup."
        )
        print(
            f"[STARTUP] CRITICAL: Data loss detected! "
            f"{rows_before} rows → {rows_after} rows. Restoring backup."
        )
        if backup_path and backup_path.exists():
            shutil.copy2(backup_path, db_path)
            for suffix in ["-wal", "-shm"]:
                backup_wal = backup_path.parent / f"{backup_path.name}{suffix}"
                if backup_wal.exists():
                    shutil.copy2(backup_wal, db_path.parent / f"{db_path.name}{suffix}")
            raise RuntimeError(
                f"Migration caused data loss ({rows_before} → {rows_after} rows). "
                f"Database restored from {backup_path}. "
                f"Fix migration before restarting."
            )

    if rows_before > 0:
        logger.info(f"Migration OK: {rows_before} → {rows_after} rows")


# Create tables on startup and resume stuck benchmarks
@app.on_event("startup")
async def startup():
    # Skip database initialization during tests (test fixtures handle it)
    if os.getenv("BELLMARK_DISABLE_BACKGROUND_RUNS"):
        return

    # Validate configuration
    config_warnings, config_fatal = _validate_config()
    for w in config_warnings:
        logger.warning(w)
        print(f"[STARTUP] {w}")
    if config_fatal:
        import sys
        sys.exit(1)

    print("=" * 60)
    print("BeLLMark is free for personal and non-commercial use.")
    print("Commercial use requires a license: https://bellmark.ai/pricing")
    print("DO NOT expose BeLLMark to the public internet.")
    if os.getenv("BELLMARK_API_KEY"):
        print("API key authentication is ENABLED.")
    elif is_dev_mode():
        print("WARNING: Running in DEVELOPMENT MODE — API is open without authentication.")
        print("Set BELLMARK_API_KEY for production use.")
    else:
        logger.critical(
            "BELLMARK_API_KEY is not set and BELLMARK_DEV_MODE is not enabled. "
            "All /api/* requests will be rejected with 503. "
            "Set BELLMARK_API_KEY or BELLMARK_DEV_MODE=true to proceed."
        )
        print("CRITICAL: No API key set and dev mode is OFF — API will reject all requests.")
        print("Set BELLMARK_API_KEY or BELLMARK_DEV_MODE=true.")
    print("=" * 60)

    # Run Alembic migrations with automatic backup protection
    alembic_ini_path = Path(__file__).parent.parent / "alembic.ini"
    if alembic_ini_path.exists():
        _safe_migrate(alembic_ini_path)
    else:
        Base.metadata.create_all(bind=engine)

    # Check for legacy encrypted keys (must run after table creation)
    db = SessionLocal()
    try:
        legacy_warnings = _check_legacy_keys(db)
        for w in legacy_warnings:
            logger.warning(w)
            print(f"[STARTUP] {w}")
    finally:
        db.close()

    # Seed built-in benchmark suites (idempotent — skips existing by name)
    from scripts.seed_suites import seed_default_suites
    seed_default_suites()

    # Auto-resume benchmarks that were running when server stopped.
    # Include `pending` — a run stuck in pending with no active runner means
    # a crash happened after commit but before the background task started
    # (e.g. a rerun or resume that committed the reset but never kicked off).
    db = SessionLocal()
    try:
        stuck_runs = db.query(BenchmarkRun).filter(
            BenchmarkRun.status.in_([RunStatus.pending, RunStatus.running, RunStatus.summarizing])
        ).all()

        for run in stuck_runs:
            print(f"[STARTUP] Auto-resuming stuck benchmark run {run.id} (status={run.status.value}): {run.name}")

            # Reset any "running" items to "pending" (orphaned from crash)
            for question in run.questions:
                db.query(Generation).filter(
                    Generation.question_id == question.id,
                    Generation.status == TaskStatus.running
                ).update({Generation.status: TaskStatus.pending})

                db.query(Judgment).filter(
                    Judgment.question_id == question.id,
                    Judgment.status == TaskStatus.running
                ).update({Judgment.status: TaskStatus.pending})

            db.commit()

            # Schedule resume task
            asyncio.create_task(resume_benchmark_task(run.id))

        if stuck_runs:
            print(f"[STARTUP] Auto-resumed {len(stuck_runs)} stuck benchmark(s)")
    except Exception as e:
        print(f"[STARTUP] Error auto-resuming benchmarks: {e}")
    finally:
        db.close()

    # Auto-resume suite generation jobs that were running when the server stopped.
    #
    # A job older than SUITE_RESUME_MAX_AGE is treated as unrecoverable and force-cancelled
    # instead of being resumed. Without this cutoff, a job that never reached a terminal
    # state (e.g. process killed between `_save_suite` and `_persist_job_state(completed)`)
    # would be re-run on every subsequent restart, silently recreating the same PromptSuite
    # row each time and making "delete" appear to fail from the user's perspective.
    SUITE_RESUME_MAX_AGE = timedelta(hours=6)
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        running_suite_jobs = db.query(SuiteGenerationJob).filter(
            SuiteGenerationJob.status == RunStatus.running
        ).all()

        stuck_suite_jobs = []
        abandoned_suite_jobs = []
        for job in running_suite_jobs:
            # job.updated_at may be naive (SQLite stores as text) — coerce to UTC
            job_updated = job.updated_at
            if job_updated is not None and job_updated.tzinfo is None:
                job_updated = job_updated.replace(tzinfo=timezone.utc)
            age = now - job_updated if job_updated is not None else SUITE_RESUME_MAX_AGE + timedelta(seconds=1)
            if age > SUITE_RESUME_MAX_AGE:
                abandoned_suite_jobs.append((job, age))
            else:
                stuck_suite_jobs.append(job)

        for job, age in abandoned_suite_jobs:
            hours = age.total_seconds() / 3600
            print(f"[STARTUP] Force-cancelling abandoned suite job {job.session_id}: {job.name} (age {hours:.1f}h > {SUITE_RESUME_MAX_AGE.total_seconds() / 3600:.1f}h)")
            job.status = RunStatus.cancelled
            job.error = f"Auto-cancelled on startup: job exceeded resume window ({hours:.1f}h > {SUITE_RESUME_MAX_AGE.total_seconds() / 3600:.1f}h)"
            job.snapshot_payload = None
            job.checkpoint_payload = None
            job.completed_at = now
            job.updated_at = now
        if abandoned_suite_jobs:
            db.commit()

        for job in stuck_suite_jobs:
            print(f"[STARTUP] Auto-resuming stuck suite job {job.session_id}: {job.name}")
            asyncio.create_task(resume_suite_generation_task(job.id))

        if stuck_suite_jobs:
            print(f"[STARTUP] Auto-resumed {len(stuck_suite_jobs)} stuck suite job(s)")
    except Exception as e:
        print(f"[STARTUP] Error auto-resuming suite jobs: {e}")
    finally:
        db.close()

    # Pre-warm the aggregate leaderboard cache so the first Home page hit
    # after a restart doesn't pay the full compute cost (~180ms). Failure
    # here is non-fatal — we fall back to lazy compute on first request.
    db = SessionLocal()
    try:
        import time as _time
        from app.api.elo import _compute_aggregate_leaderboard
        import app.api.elo as _elo_module
        _t0 = _time.perf_counter()
        _elo_module._cached_aggregate_leaderboard = _compute_aggregate_leaderboard(db)
        print(f"[STARTUP] Aggregate leaderboard cache warmed in {(_time.perf_counter() - _t0) * 1000:.0f}ms")
    except Exception as e:
        print(f"[STARTUP] Aggregate leaderboard pre-warm failed (non-fatal): {e}")
    finally:
        db.close()

@app.on_event("shutdown")
async def shutdown():
    """Reset in-flight work to pending so startup auto-resume can recover it."""
    # Signal all active runners to stop
    for runner in list(active_runners.values()):
        if runner is not None:
            runner.cancel()

    # Cancel active suite generation pipelines
    for pipeline in list(active_suite_pipelines.values()):
        if pipeline is not None:
            pipeline.pause_for_resume()

    # Await tracked suite tasks briefly so they can checkpoint and exit.
    suite_tasks = list(active_suite_pipeline_tasks.values())
    if suite_tasks:
        try:
            await asyncio.wait_for(asyncio.gather(*suite_tasks, return_exceptions=True), timeout=5)
        except asyncio.TimeoutError:
            logger.warning("Shutdown: timed out waiting for suite jobs to pause; unfinished work will resume on startup")

    db = SessionLocal()
    try:
        stuck_runs = db.query(BenchmarkRun).filter(
            BenchmarkRun.status.in_([RunStatus.running, RunStatus.summarizing])
        ).all()

        for run in stuck_runs:
            for question in run.questions:
                db.query(Generation).filter(
                    Generation.question_id == question.id,
                    Generation.status == TaskStatus.running
                ).update({Generation.status: TaskStatus.pending})

                db.query(Judgment).filter(
                    Judgment.question_id == question.id,
                    Judgment.status == TaskStatus.running
                ).update({Judgment.status: TaskStatus.pending})

        if stuck_runs:
            db.commit()
            logger.info(f"Shutdown: reset running items for {len(stuck_runs)} run(s)")
    except Exception as e:
        logger.warning(f"Shutdown cleanup error: {e}")
    finally:
        db.close()

@app.get("/api/auth/check")
async def auth_check():
    """Check whether API key authentication is enabled."""
    from app.core.auth import _get_api_key
    return {"auth_required": _get_api_key() is not None, "dev_mode": is_dev_mode()}


@app.get("/health")
async def health():
    return {"status": "ok", "version": APP_VERSION}

@app.get("/api/health/live")
async def health_live():
    return {"status": "ok"}

@app.websocket("/ws/runs/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: int):
    # Verify API key via first-message auth frame (F-003 security)
    if not await verify_websocket_auth(websocket):
        return

    # Connection already accepted by verify_websocket_auth; register it.
    await manager.connect(run_id, websocket, skip_accept=True)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "cancel":
                # Cancel the active runner if it exists
                if run_id in active_runners:
                    runner = active_runners[run_id]
                    runner.cancel()

                # Update database status
                db = SessionLocal()
                try:
                    run = db.query(BenchmarkRun).filter(BenchmarkRun.id == run_id).first()
                    if run:
                        run.status = RunStatus.cancelled
                        db.commit()
                finally:
                    db.close()

                # Send confirmation
                await websocket.send_json({"type": "cancelled", "run_id": run_id})
    except WebSocketDisconnect:
        await manager.disconnect(run_id, websocket)

@app.websocket("/ws/suite-generate/{session_id}")
async def suite_generate_websocket(websocket: WebSocket, session_id: str):
    # Verify API key via first-message auth frame (F-003 security)
    if not await verify_websocket_auth(websocket):
        return

    # Connection already accepted by verify_websocket_auth
    pipeline = active_suite_pipelines.get(session_id)
    snapshot = pipeline.snapshot() if pipeline is not None else None
    if snapshot is None:
        db_gen_factory = app.dependency_overrides.get(get_db, get_db)
        db_gen = db_gen_factory()
        db = next(db_gen)
        try:
            job = (
                db.query(SuiteGenerationJob)
                .filter(
                    SuiteGenerationJob.session_id == session_id,
                    SuiteGenerationJob.status == RunStatus.running,
                )
                .first()
            )
            if job is not None:
                snapshot = job.snapshot_payload
        finally:
            try:
                next(db_gen)
            except StopIteration:
                pass
    if snapshot is None:
        await websocket.close(code=4404, reason="Suite generation session not found")
        return

    await suite_manager.connect_with_initial_message(
        session_id,
        websocket,
        {
            "type": "suite_progress",
            "snapshot": True,
            **snapshot,
        },
        skip_accept=True,
    )
    try:
        while True:
            try:
                data = await websocket.receive_json()
            except (ValueError, json.JSONDecodeError):
                continue
            if data.get("type") == "cancel":
                db_gen_factory = app.dependency_overrides.get(get_db, get_db)
                db_gen = db_gen_factory()
                db = next(db_gen)
                try:
                    cancelled = cancel_suite_generation_session(session_id, db)
                finally:
                    try:
                        next(db_gen)
                    except StopIteration:
                        pass
                if cancelled:
                    await websocket.send_json({"type": "cancelled", "session_id": session_id})
                else:
                    await websocket.close(code=4404, reason="Suite generation session not found")
                    return
    except WebSocketDisconnect:
        await suite_manager.disconnect(session_id, websocket)


# Mount frontend static files if dist exists (production mode)
# This MUST be at the end of the file (after all API routes and WebSocket routes)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException

frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
SPA_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

if frontend_dist.exists():
    # Serve static assets
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    # Serve index.html for SPA routes (catch-all route, must be registered LAST)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't intercept API or WebSocket routes
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            raise HTTPException(status_code=404)

        # Serve actual static files from dist/ if they exist (logos, favicons, etc.)
        static_file = frontend_dist / full_path
        if static_file.is_file() and not full_path.startswith("."):
            return FileResponse(static_file)

        # Serve index.html for all other routes (SPA client-side routing)
        index_file = frontend_dist / "index.html"
        if index_file.exists():
            return FileResponse(index_file, headers=SPA_NO_CACHE_HEADERS)
        raise HTTPException(status_code=404, detail="Frontend not built")
