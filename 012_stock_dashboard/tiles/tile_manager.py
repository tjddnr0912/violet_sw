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
        clients = set(self._clients)  # snapshot to avoid set mutation during iteration
        if not clients:
            return
        msg = json.dumps({"type": "tile_update", "tile_id": tile_id, "data": data})

        async def _send(ws: WebSocket):
            try:
                await ws.send_text(msg)
            except Exception:
                self.unsubscribe(ws)

        await asyncio.gather(*[_send(ws) for ws in clients])

    async def broadcast_raw(self, message: dict):
        """Send arbitrary message to all clients."""
        clients = set(self._clients)  # snapshot to avoid set mutation during iteration
        if not clients:
            return
        msg = json.dumps(message)

        async def _send(ws: WebSocket):
            try:
                await ws.send_text(msg)
            except Exception:
                self.unsubscribe(ws)

        await asyncio.gather(*[_send(ws) for ws in clients])
