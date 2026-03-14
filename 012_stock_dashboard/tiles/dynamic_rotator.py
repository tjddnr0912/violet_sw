"""Dynamic tile FIFO queue with rotation - compact 2x2 news layout."""

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

ROTATION_INTERVAL = 15  # seconds
MAX_QUEUE_SIZE = 20
DISPLAY_SLOTS = 4  # 2x2 grid items
TILE_ID = "news_compact"
BREAKING_HOLD_SECONDS = 60


class DynamicRotator:
    def __init__(self, data_store):
        self.data_store = data_store
        self._queue: deque = deque(maxlen=MAX_QUEUE_SIZE)
        self._current: list[dict] = []  # up to DISPLAY_SLOTS items
        self._breaking_until: float = 0
        self._initialized = False

    def push(self, item: dict, breaking: bool = False):
        """Add news item to queue. Breaking items get priority."""
        existing_ids = {q.get("article_id") for q in self._queue}
        current_ids = {v.get("article_id") for v in self._current if v}
        if item.get("article_id") in existing_ids | current_ids:
            return

        if breaking:
            item["breaking"] = True
            # Breaking: insert at position 0, push others down
            self._current.insert(0, item)
            if len(self._current) > DISPLAY_SLOTS:
                self._current = self._current[:DISPLAY_SLOTS]
            self._breaking_until = time.time() + BREAKING_HOLD_SECONDS
            asyncio.create_task(self._broadcast_all())
        else:
            self._queue.appendleft(item)

        # On first batch, immediately fill slots
        if not self._initialized:
            self._fill_slots()

    def _fill_slots(self):
        """Fill display slots from the queue."""
        while len(self._current) < DISPLAY_SLOTS and self._queue:
            self._current.append(self._queue.pop())
        if len(self._current) >= DISPLAY_SLOTS:
            self._initialized = True
            asyncio.create_task(self._broadcast_all())

    def enrich(self, article_id: str, updates: dict):
        """Update an item in queue/current with AI summary data."""
        for item in self._queue:
            if item.get("article_id") == article_id:
                item.update(updates)
        changed = False
        for item in self._current:
            if item and item.get("article_id") == article_id:
                item.update(updates)
                changed = True
        if changed:
            asyncio.create_task(self._broadcast_all())

    def promote_breaking(self, article_id: str):
        """Promote an article to breaking status."""
        target = None
        for item in self._queue:
            if item.get("article_id") == article_id:
                target = item
                break
        if target is None:
            return
        self._queue.remove(target)
        target["breaking"] = True
        self._current.insert(0, target)
        if len(self._current) > DISPLAY_SLOTS:
            self._current = self._current[:DISPLAY_SLOTS]
        self._breaking_until = time.time() + BREAKING_HOLD_SECONDS
        asyncio.create_task(self._broadcast_all())

    async def rotation_loop(self):
        """Rotate one item every ROTATION_INTERVAL seconds."""
        while True:
            await asyncio.sleep(ROTATION_INTERVAL)
            if not self._queue:
                continue

            # During breaking hold, don't rotate slot 0
            start_idx = 1 if time.time() < self._breaking_until else 0

            if self._queue and len(self._current) > start_idx:
                # Rotate: remove oldest non-breaking, add new from queue
                item = self._queue.pop()
                # Remove last item and prepend new after breaking slot
                if len(self._current) >= DISPLAY_SLOTS:
                    self._current.pop()
                self._current.insert(start_idx, item)
                await self._broadcast_all()

    async def _broadcast_all(self):
        """Send all current items as a single tile update."""
        items = [item for item in self._current if item]
        await self.data_store.update(TILE_ID, {"items": items})
