# backend/app/ws/suite_progress.py
import asyncio
from fastapi import WebSocket
from typing import Dict, Set


class SuiteConnectionManager:
    """WebSocket connection manager keyed by str session_id (for suite generation)."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    async def connect(self, session_id: str, websocket: WebSocket, skip_accept: bool = False):
        if not skip_accept:
            await websocket.accept()
        lock = self._get_lock(session_id)
        async with lock:
            if session_id not in self.active_connections:
                self.active_connections[session_id] = set()
            self.active_connections[session_id].add(websocket)

    async def connect_with_initial_message(
        self,
        session_id: str,
        websocket: WebSocket,
        initial_message: dict,
        skip_accept: bool = False,
    ):
        if not skip_accept:
            await websocket.accept()
        lock = self._get_lock(session_id)
        async with lock:
            await websocket.send_json(initial_message)
            if session_id not in self.active_connections:
                self.active_connections[session_id] = set()
            self.active_connections[session_id].add(websocket)

    async def disconnect(self, session_id: str, websocket: WebSocket = None):
        lock = self._get_lock(session_id)
        async with lock:
            if session_id in self.active_connections:
                if websocket:
                    self.active_connections[session_id].discard(websocket)
                    if not self.active_connections[session_id]:
                        del self.active_connections[session_id]
                        if session_id in self._locks:
                            del self._locks[session_id]
                else:
                    del self.active_connections[session_id]
                    if session_id in self._locks:
                        del self._locks[session_id]

    async def send_progress(self, session_id: str, data: dict):
        lock = self._get_lock(session_id)
        async with lock:
            if session_id not in self.active_connections:
                return
            connections_snapshot = list(self.active_connections[session_id])

        dead_sockets = []
        for websocket in connections_snapshot:
            try:
                await websocket.send_json(data)
            except Exception:
                dead_sockets.append(websocket)

        if dead_sockets:
            async with lock:
                if session_id in self.active_connections:
                    for ws in dead_sockets:
                        self.active_connections[session_id].discard(ws)
                    if not self.active_connections[session_id]:
                        del self.active_connections[session_id]
                        if session_id in self._locks:
                            del self._locks[session_id]


suite_manager = SuiteConnectionManager()
