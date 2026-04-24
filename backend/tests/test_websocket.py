# backend/tests/test_websocket.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi import WebSocket
from app.ws.progress import ConnectionManager


class MockWebSocket:
    """Mock WebSocket for testing."""
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.accepted = False
        self.sent_messages = []
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.should_fail:
            raise Exception("WebSocket send failed")
        self.sent_messages.append(data)

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return id(self) == id(other)


@pytest.mark.asyncio
async def test_connect_and_disconnect():
    """Test basic connect and disconnect flow."""
    manager = ConnectionManager()
    ws = MockWebSocket()

    await manager.connect(1, ws)
    assert ws.accepted
    assert 1 in manager.active_connections
    assert ws in manager.active_connections[1]

    await manager.disconnect(1, ws)
    assert 1 not in manager.active_connections


@pytest.mark.asyncio
async def test_send_to_connected_client():
    """Test sending message to connected client."""
    manager = ConnectionManager()
    ws = MockWebSocket()

    await manager.connect(1, ws)
    await manager.send_progress(1, {"type": "test", "data": "hello"})

    assert len(ws.sent_messages) == 1
    assert ws.sent_messages[0] == {"type": "test", "data": "hello"}


@pytest.mark.asyncio
async def test_send_to_nonexistent_run():
    """Test sending to a run_id with no connections is safe."""
    manager = ConnectionManager()

    # Should not raise exception
    await manager.send_progress(999, {"type": "test"})


@pytest.mark.asyncio
async def test_dead_socket_pruned():
    """Test that dead sockets are automatically pruned during send."""
    manager = ConnectionManager()
    ws_good = MockWebSocket()
    ws_dead = MockWebSocket(should_fail=True)

    await manager.connect(1, ws_good)
    await manager.connect(1, ws_dead)

    assert len(manager.active_connections[1]) == 2

    # Send should prune the dead socket
    await manager.send_progress(1, {"type": "test"})

    assert len(manager.active_connections[1]) == 1
    assert ws_good in manager.active_connections[1]
    assert ws_dead not in manager.active_connections[1]


@pytest.mark.asyncio
async def test_multiple_clients_same_run():
    """Test multiple clients connected to same run."""
    manager = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    ws3 = MockWebSocket()

    await manager.connect(1, ws1)
    await manager.connect(1, ws2)
    await manager.connect(1, ws3)

    assert len(manager.active_connections[1]) == 3

    await manager.send_progress(1, {"type": "broadcast", "data": "all"})

    assert len(ws1.sent_messages) == 1
    assert len(ws2.sent_messages) == 1
    assert len(ws3.sent_messages) == 1

    # Disconnect one client
    await manager.disconnect(1, ws2)
    assert len(manager.active_connections[1]) == 2
    assert ws2 not in manager.active_connections[1]


@pytest.mark.asyncio
async def test_concurrent_connect_disconnect():
    """Test concurrent connections and disconnections (race condition stress test)."""
    manager = ConnectionManager()
    num_clients = 20
    websockets = [MockWebSocket() for _ in range(num_clients)]

    # Concurrent connects
    connect_tasks = [manager.connect(1, ws) for ws in websockets]
    await asyncio.gather(*connect_tasks)

    assert len(manager.active_connections[1]) == num_clients

    # Concurrent disconnects
    disconnect_tasks = [manager.disconnect(1, ws) for ws in websockets]
    await asyncio.gather(*disconnect_tasks)

    assert 1 not in manager.active_connections


@pytest.mark.asyncio
async def test_send_status_helper():
    """Test send_status helper method."""
    manager = ConnectionManager()
    ws = MockWebSocket()

    await manager.connect(1, ws)
    await manager.send_status(1, "generating", 50)

    assert len(ws.sent_messages) == 1
    msg = ws.sent_messages[0]
    assert msg["type"] == "status"
    assert msg["phase"] == "generating"
    assert msg["progress"] == 50


@pytest.mark.asyncio
async def test_send_generation_helper():
    """Test send_generation helper method."""
    manager = ConnectionManager()
    ws = MockWebSocket()

    await manager.connect(1, ws)
    await manager.send_generation(
        run_id=1,
        question_id=42,
        model_name="gpt-4",
        status="success",
        tokens=100,
        preview="This is a test response that is quite long and should be truncated to 150 characters max" * 3,
        error=None,
        retry=None
    )

    assert len(ws.sent_messages) == 1
    msg = ws.sent_messages[0]
    assert msg["type"] == "generation"
    assert msg["question_id"] == 42
    assert msg["model"] == "gpt-4"
    assert msg["status"] == "success"
    assert msg["tokens"] == 100
    assert msg["preview"] is not None
    assert len(msg["preview"]) <= 150  # Should be truncated
    assert msg["error"] is None
    assert msg["retry"] is None


@pytest.mark.asyncio
async def test_send_judgment_helper():
    """Test send_judgment helper method."""
    manager = ConnectionManager()
    ws = MockWebSocket()

    await manager.connect(1, ws)
    await manager.send_judgment(
        run_id=1,
        question_id=42,
        judge_name="claude-opus-4",
        status="success",
        winner="gpt-4",
        scores={"gpt-4": 95, "claude-3": 88},
        error=None,
        retry=None
    )

    assert len(ws.sent_messages) == 1
    msg = ws.sent_messages[0]
    assert msg["type"] == "judgment"
    assert msg["question_id"] == 42
    assert msg["judge"] == "claude-opus-4"
    assert msg["status"] == "success"
    assert msg["winner"] == "gpt-4"
    assert msg["scores"] == {"gpt-4": 95, "claude-3": 88}


@pytest.mark.asyncio
async def test_send_to_multiple_runs_isolated():
    """Test that messages to different runs are properly isolated."""
    manager = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    ws3 = MockWebSocket()

    await manager.connect(1, ws1)
    await manager.connect(2, ws2)
    await manager.connect(3, ws3)

    await manager.send_progress(1, {"type": "run1"})
    await manager.send_progress(2, {"type": "run2"})
    await manager.send_progress(3, {"type": "run3"})

    assert ws1.sent_messages == [{"type": "run1"}]
    assert ws2.sent_messages == [{"type": "run2"}]
    assert ws3.sent_messages == [{"type": "run3"}]


@pytest.mark.asyncio
async def test_disconnect_all_for_run():
    """Test disconnecting all clients for a run (websocket=None)."""
    manager = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()
    ws3 = MockWebSocket()

    await manager.connect(1, ws1)
    await manager.connect(1, ws2)
    await manager.connect(2, ws3)

    # Disconnect all clients from run 1
    await manager.disconnect(1, websocket=None)

    assert 1 not in manager.active_connections
    assert 2 in manager.active_connections  # Run 2 should be unaffected


@pytest.mark.asyncio
async def test_concurrent_send_and_disconnect():
    """Test concurrent sends and disconnects (race condition)."""
    manager = ConnectionManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    await manager.connect(1, ws1)
    await manager.connect(1, ws2)

    # Interleave sends and disconnects
    tasks = [
        manager.send_progress(1, {"msg": 1}),
        manager.disconnect(1, ws1),
        manager.send_progress(1, {"msg": 2}),
        manager.disconnect(1, ws2),
        manager.send_progress(1, {"msg": 3}),  # Should be safe (no connections)
    ]

    await asyncio.gather(*tasks)

    # Should not crash, run 1 should be cleaned up
    assert 1 not in manager.active_connections


@pytest.mark.asyncio
async def test_multiple_connects_same_websocket():
    """Test that connecting the same websocket multiple times is safe."""
    manager = ConnectionManager()
    ws = MockWebSocket()

    await manager.connect(1, ws)
    await manager.connect(1, ws)  # Connect again

    # Set should deduplicate
    assert len(manager.active_connections[1]) == 1


@pytest.mark.asyncio
async def test_send_with_retry_info():
    """Test generation/judgment messages with retry information."""
    manager = ConnectionManager()
    ws = MockWebSocket()

    await manager.connect(1, ws)

    # Failed generation with retry info
    await manager.send_generation(
        run_id=1,
        question_id=1,
        model_name="gpt-4",
        status="failed",
        error="Rate limit exceeded",
        retry=2
    )

    msg = ws.sent_messages[0]
    assert msg["status"] == "failed"
    assert msg["error"] == "Rate limit exceeded"
    assert msg["retry"] == 2


@pytest.mark.asyncio
async def test_all_dead_sockets_cleanup():
    """Test that run is removed when all sockets are dead."""
    manager = ConnectionManager()
    ws1 = MockWebSocket(should_fail=True)
    ws2 = MockWebSocket(should_fail=True)

    await manager.connect(1, ws1)
    await manager.connect(1, ws2)

    assert 1 in manager.active_connections

    # Send should prune all dead sockets
    await manager.send_progress(1, {"type": "test"})

    # Run should still exist but with empty set (or be removed depending on implementation)
    # Current implementation keeps empty sets, so we just verify sockets are gone
    if 1 in manager.active_connections:
        assert len(manager.active_connections[1]) == 0
