# backend/tests/test_suite_websocket.py
"""Tests for suite generation WebSocket lifecycle and SuiteConnectionManager."""
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# SuiteConnectionManager unit tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suite_manager_connect_send_disconnect():
    """Test the SuiteConnectionManager independently."""
    from app.ws.suite_progress import SuiteConnectionManager

    manager = SuiteConnectionManager()
    session_id = "test-session-abc"

    # Create a mock WebSocket
    mock_ws = MagicMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock()

    # Connect
    await manager.connect(session_id, mock_ws)
    assert session_id in manager.active_connections
    assert mock_ws in manager.active_connections[session_id]
    mock_ws.accept.assert_awaited_once()

    # Send progress
    await manager.send_progress(session_id, {"type": "suite_progress", "phase": "generate"})
    mock_ws.send_json.assert_awaited_once_with({"type": "suite_progress", "phase": "generate"})

    # Disconnect
    await manager.disconnect(session_id, mock_ws)
    assert session_id not in manager.active_connections


@pytest.mark.asyncio
async def test_suite_manager_send_to_no_connections():
    """send_progress on an unknown session_id should be a no-op."""
    from app.ws.suite_progress import SuiteConnectionManager

    manager = SuiteConnectionManager()
    # Should not raise
    await manager.send_progress("nonexistent-session", {"type": "ping"})


@pytest.mark.asyncio
async def test_suite_manager_disconnect_removes_dead_sockets():
    """Dead sockets during send_progress should be pruned."""
    from app.ws.suite_progress import SuiteConnectionManager

    manager = SuiteConnectionManager()
    session_id = "dead-socket-session"

    mock_ws = MagicMock()
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock(side_effect=Exception("broken pipe"))

    await manager.connect(session_id, mock_ws)
    # This should not raise, and should prune the dead socket
    await manager.send_progress(session_id, {"type": "test"})
    # After pruning, session should be gone
    assert session_id not in manager.active_connections


# ---------------------------------------------------------------------------
# Cancel message integration test
# ---------------------------------------------------------------------------

def test_cancel_message_marks_pipeline_cancelled(client, monkeypatch):
    """Connect WS, send cancel, verify pipeline._cancelled == True."""
    from app.core.suite_pipeline import active_suite_pipelines, SuitePipeline, PipelineConfig
    from app.db.models import ModelPreset, ProviderType

    session_id = "cancel-test-session"

    # Create a minimal mock pipeline and register it
    mock_preset = MagicMock(spec=ModelPreset)
    mock_preset.name = "test-gen"
    mock_preset.model_id = "test/model"

    pipeline = SuitePipeline(
        session_id=session_id,
        generator_preset=mock_preset,
        reviewer_presets=[],
        name="Test Suite",
        topic="Testing",
        count=5,
        config=PipelineConfig(),
        suite_manager=None,
    )
    active_suite_pipelines[session_id] = pipeline

    try:
        with client.websocket_connect(f"/ws/suite-generate/{session_id}") as ws:
            initial = ws.receive_json()
            assert initial["type"] == "suite_progress"
            assert initial.get("snapshot") is True
            ws.send_json({"type": "cancel"})
            ack = ws.receive_json()
            assert ack["type"] == "cancelled"
            assert ack["session_id"] == session_id

        # After disconnect, pipeline should be marked cancelled
        assert pipeline._cancelled is True
    finally:
        active_suite_pipelines.pop(session_id, None)


def test_cancel_message_cancels_active_task_and_marks_job_cancelled(client):
    """WebSocket cancel should stop the active suite task and mark the durable job cancelled."""
    from app.api.suites import active_suite_pipeline_tasks
    from app.core.suite_pipeline import active_suite_pipelines
    from app.db.database import get_db
    from app.db.models import RunStatus, SuiteGenerationJob

    class DummyTask:
        def __init__(self) -> None:
            self.cancel_called = False

        def cancel(self) -> None:
            self.cancel_called = True

    session_id = "cancel-durable-job"
    pipeline = MagicMock()
    pipeline.cancel = MagicMock()
    pipeline.snapshot.return_value = {
        "session_id": session_id,
        "name": "Cancelable Suite",
        "topic": "Cancel test",
        "phase": "merge",
        "phase_index": 2,
        "total_phases": 5,
        "phases": ["generate", "review", "merge", "synthesize", "save"],
        "batch": 1,
        "total_batches": 1,
        "overall_percent": 65,
        "call_started_at": None,
        "model": "Editor",
        "reviewers_status": None,
        "questions_generated": 1,
        "questions_reviewed": 1,
        "questions_merged": 0,
        "question_count": 1,
        "completed_generation_batches": 1,
        "active_generation_batches": 0,
        "active_generation_calls": [],
        "active_review_batches": [],
        "generator": "Generator",
        "generators": ["Generator"],
        "editor": "Editor",
        "reviewers": ["Reviewer"],
        "difficulty": "balanced",
        "categories": [],
        "generate_answers": True,
        "criteria_depth": "basic",
        "coverage_mode": "none",
        "required_leaf_count": 0,
        "covered_leaf_count": 0,
        "missing_leaf_count": 0,
        "duplicate_cluster_count": 0,
        "replacement_count": 0,
        "elapsed_seconds": 0,
        "recent_log": [],
    }
    task = DummyTask()
    active_suite_pipelines[session_id] = pipeline
    active_suite_pipeline_tasks[session_id] = task

    db = next(client.app.dependency_overrides[get_db]())
    try:
        job = SuiteGenerationJob(
            session_id=session_id,
            status=RunStatus.running,
            name="Cancelable Suite",
            topic="Cancel test",
            count=1,
            generator_model_ids=[1],
            editor_model_id=1,
            reviewer_model_ids=[2],
            pipeline_config={
                "difficulty": "balanced",
                "categories": [],
                "generate_answers": True,
                "criteria_depth": "basic",
                "generation_concurrency": 5,
                "review_batch_concurrency": 5,
            },
            coverage_mode="none",
            coverage_spec=None,
            max_topics_per_question=1,
            context_attachment_id=None,
            phase="merge",
            snapshot_payload=pipeline.snapshot.return_value,
            checkpoint_payload={},
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    try:
        with client.websocket_connect(f"/ws/suite-generate/{session_id}") as ws:
            initial = ws.receive_json()
            assert initial["type"] == "suite_progress"
            ws.send_json({"type": "cancel"})
            ack = ws.receive_json()
            assert ack["type"] == "cancelled"
            assert ack["session_id"] == session_id

        db = next(client.app.dependency_overrides[get_db]())
        try:
            refreshed = (
                db.query(SuiteGenerationJob)
                .filter(SuiteGenerationJob.session_id == session_id)
                .first()
            )
            assert refreshed is not None
            assert refreshed.status == RunStatus.cancelled
            assert refreshed.error == "Cancelled by user"
        finally:
            db.close()

        pipeline.cancel.assert_called_once()
        assert task.cancel_called is True
    finally:
        active_suite_pipelines.pop(session_id, None)
        active_suite_pipeline_tasks.pop(session_id, None)


# ---------------------------------------------------------------------------
# Full integration: POST v2 → connect WS → verify session_id and connection
# ---------------------------------------------------------------------------

def test_generate_suite_v2_websocket_completion_flow(client, monkeypatch):
    """Full integration: POST v2 → connect WS → verify the session WS endpoint is reachable."""
    from app.core.suite_pipeline import active_suite_pipelines
    from app.db.models import PromptSuite, PromptSuiteItem

    # Create a model preset in the test DB
    model_res = client.post("/api/models/", json={
        "name": "Gen Model",
        "provider": "lmstudio",
        "base_url": "http://localhost:1234/v1/chat/completions",
        "model_id": "test/gen-model",
    })
    assert model_res.status_code == 200
    model_id = model_res.json()["id"]

    # Mock the pipeline run to be a long-running no-op (never completes during test)
    # so we can test the WS connection itself without timing issues
    pipeline_started = []

    async def fake_run(self):
        pipeline_started.append(self.session_id)
        # Simulate being cancelled immediately
        raise asyncio.CancelledError()

    with patch("app.core.suite_pipeline.SuitePipeline.run", fake_run):
        # Start generation
        v2_res = client.post("/api/suites/generate-v2", json={
            "name": "WS Flow Suite",
            "topic": "Testing websocket flow",
            "count": 3,
            "generator_model_id": model_id,
        })
        assert v2_res.status_code == 200
        data = v2_res.json()
        assert "session_id" in data
        session_id = data["session_id"]
        assert isinstance(session_id, str)
        assert len(session_id) > 0

        # Verify the WebSocket endpoint is reachable for the session
        with client.websocket_connect(f"/ws/suite-generate/{session_id}") as ws:
            # Successfully connected — endpoint is wired up correctly
            # Send a non-cancel message (just a ping-like payload)
            ws.send_json({"type": "ping"})
            # Disconnect cleanly by exiting the context manager

    # Cleanup
    active_suite_pipelines.pop(session_id, None)


def test_websocket_reconnect_uses_persisted_suite_job_snapshot(client):
    """When no live pipeline exists, WS reconnect should hydrate from persisted suite job state."""
    from app.db.database import get_db
    from app.db.models import RunStatus, SuiteGenerationJob

    db = next(client.app.dependency_overrides[get_db]())
    try:
        job = SuiteGenerationJob(
            session_id="persisted-suite-session",
            status=RunStatus.running,
            name="Persisted Suite",
            topic="Reconnect",
            count=10,
            generator_model_ids=[1],
            editor_model_id=1,
            reviewer_model_ids=[2],
            pipeline_config={
                "difficulty": "balanced",
                "categories": [],
                "generate_answers": True,
                "criteria_depth": "basic",
                "generation_concurrency": 5,
                "review_batch_concurrency": 5,
            },
            coverage_mode="none",
            coverage_spec=None,
            max_topics_per_question=1,
            context_attachment_id=None,
            phase="review",
            snapshot_payload={
                "session_id": "persisted-suite-session",
                "name": "Persisted Suite",
                "topic": "Reconnect",
                "phase": "review",
                "phase_index": 1,
                "total_phases": 5,
                "phases": ["generate", "review", "merge", "synthesize", "save"],
                "batch": 1,
                "total_batches": 2,
                "overall_percent": 45,
                "call_started_at": None,
                "model": None,
                "reviewers_status": None,
                "questions_generated": 10,
                "questions_reviewed": 5,
                "questions_merged": 0,
                "question_count": 10,
                "completed_generation_batches": 2,
                "active_generation_batches": 0,
                "active_generation_calls": [],
                "active_review_batches": [
                    {
                        "task_id": "review-batch-2",
                        "batch_index": 2,
                        "total_batches": 2,
                        "started_at": 1774882000,
                        "detail": "Review batch 2/2",
                        "reviewers_status": [
                            {"model": "Reviewer", "status": "working", "started_at": 1774882000},
                        ],
                    },
                ],
                "generator": "Generator",
                "generators": ["Generator"],
                "editor": "Editor",
                "reviewers": ["Reviewer"],
                "difficulty": "balanced",
                "categories": [],
                "generate_answers": True,
                "criteria_depth": "basic",
                "coverage_mode": "none",
                "required_leaf_count": 0,
                "covered_leaf_count": 0,
                "missing_leaf_count": 0,
                "duplicate_cluster_count": 0,
                "replacement_count": 0,
                "elapsed_seconds": 30,
                "recent_log": [],
            },
            checkpoint_payload={},
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    with client.websocket_connect("/ws/suite-generate/persisted-suite-session") as ws:
        initial = ws.receive_json()
        assert initial["type"] == "suite_progress"
        assert initial["snapshot"] is True
        assert initial["session_id"] == "persisted-suite-session"
        assert initial["active_review_batches"][0]["batch_index"] == 2
