# backend/app/ws/progress.py
import asyncio
from fastapi import WebSocket
from typing import Dict, Set

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, Set[WebSocket]] = {}  # run_id -> set of websockets
        self._locks: Dict[int, asyncio.Lock] = {}  # run_id -> lock

    def _get_lock(self, run_id: int) -> asyncio.Lock:
        """Get or create a lock for the given run_id."""
        if run_id not in self._locks:
            self._locks[run_id] = asyncio.Lock()
        return self._locks[run_id]

    async def connect(self, run_id: int, websocket: WebSocket, skip_accept: bool = False):
        if not skip_accept:
            await websocket.accept()
        lock = self._get_lock(run_id)
        async with lock:
            if run_id not in self.active_connections:
                self.active_connections[run_id] = set()
            self.active_connections[run_id].add(websocket)

    async def disconnect(self, run_id: int, websocket: WebSocket = None):
        lock = self._get_lock(run_id)
        async with lock:
            if run_id in self.active_connections:
                if websocket:
                    self.active_connections[run_id].discard(websocket)
                    if not self.active_connections[run_id]:
                        del self.active_connections[run_id]
                        # Clean up the lock for this run
                        if run_id in self._locks:
                            del self._locks[run_id]
                else:
                    del self.active_connections[run_id]
                    # Clean up the lock for this run
                    if run_id in self._locks:
                        del self._locks[run_id]

    async def send_progress(self, run_id: int, data: dict):
        # Snapshot connections under lock
        lock = self._get_lock(run_id)
        async with lock:
            if run_id not in self.active_connections:
                return
            # Create a snapshot of the current connections
            connections_snapshot = list(self.active_connections[run_id])

        # Send messages outside the lock to avoid blocking other operations
        dead_sockets = []
        for websocket in connections_snapshot:
            try:
                await websocket.send_json(data)
            except Exception:
                dead_sockets.append(websocket)

        # Prune dead connections under lock
        if dead_sockets:
            async with lock:
                if run_id in self.active_connections:
                    for ws in dead_sockets:
                        self.active_connections[run_id].discard(ws)
                    # Clean up empty run and its lock
                    if not self.active_connections[run_id]:
                        del self.active_connections[run_id]
                        if run_id in self._locks:
                            del self._locks[run_id]

    async def send_status(self, run_id: int, phase: str, progress: int):
        await self.send_progress(run_id, {
            "type": "status",
            "phase": phase,
            "progress": progress
        })

    async def send_generation(self, run_id: int, question_id: int, model_name: str,
                              status: str, tokens: int = None,
                              preview: str = None, error: str = None,
                              retry: int = None):
        await self.send_progress(run_id, {
            "type": "generation",
            "question_id": question_id,
            "model": model_name,
            "status": status,
            "tokens": tokens,
            "preview": preview[:150] if preview else None,
            "error": error,
            "retry": retry
        })

    async def send_judgment(self, run_id: int, question_id: int, judge_name: str,
                            status: str, winner: str = None,
                            scores: dict = None, error: str = None,
                            retry: int = None):
        await self.send_progress(run_id, {
            "type": "judgment",
            "question_id": question_id,
            "judge": judge_name,
            "status": status,
            "winner": winner,
            "scores": scores,
            "error": error,
            "retry": retry
        })

manager = ConnectionManager()
