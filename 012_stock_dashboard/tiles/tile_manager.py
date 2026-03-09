"""DataStore + WebSocket broadcast manager."""

import asyncio
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class DataStore:
    """Thread-safe tile data store with WebSocket broadcasting."""

    def __init__(self):
        self._data: dict = {}
        self._lock = asyncio.Lock()
        self._clients: set[WebSocket] = set()

    async def update(self, tile_id: str, data: dict):
        """Update tile data and broadcast if changed."""
        async with self._lock:
            old = self._data.get(tile_id)
            self._data[tile_id] = data
        # Always broadcast (simplifies logic, small payload)
        await self.broadcast(tile_id, data)

    async def get_full_state(self) -> dict:
        async with self._lock:
            return dict(self._data)

    def subscribe(self, ws: WebSocket):
        self._clients.add(ws)
        logger.info(f"Client subscribed. Total: {len(self._clients)}")

    def unsubscribe(self, ws: WebSocket):
        self._clients.discard(ws)
        logger.info(f"Client unsubscribed. Total: {len(self._clients)}")

    async def broadcast(self, tile_id: str, data: dict):
        """Send update to all connected WebSocket clients."""
        if not self._clients:
            return
        msg = json.dumps({"type": "tile_update", "tile_id": tile_id, "data": data})
        disconnected = []
        for ws in self._clients:
            try:
                await ws.send_text(msg)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.unsubscribe(ws)

    async def broadcast_raw(self, message: dict):
        """Send arbitrary message to all clients."""
        if not self._clients:
            return
        msg = json.dumps(message)
        disconnected = []
        for ws in self._clients:
            try:
                await ws.send_text(msg)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.unsubscribe(ws)
