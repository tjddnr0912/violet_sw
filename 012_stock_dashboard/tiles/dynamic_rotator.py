"""Dynamic tile FIFO queue with rotation and breaking news override."""

import asyncio
import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

ROTATION_INTERVAL = 15  # seconds
MAX_QUEUE_SIZE = 20
DYNAMIC_SLOTS = ["dynamic_1", "dynamic_2", "dynamic_3", "dynamic_4"]
BREAKING_HOLD_SECONDS = 60


class DynamicRotator:
    def __init__(self, data_store):
        self.data_store = data_store
        self._queue: deque = deque(maxlen=MAX_QUEUE_SIZE)
        self._current: dict[str, dict] = {}  # slot -> current item
        self._breaking_until: float = 0
        self._slot_index = 0
        self._initialized = False

    def push(self, item: dict, breaking: bool = False):
        """Add news item to queue. Breaking items get priority slot."""
        # Avoid duplicates
        existing_ids = {q.get("article_id") for q in self._queue}
        current_ids = {v.get("article_id") for v in self._current.values() if v}
        if item.get("article_id") in existing_ids | current_ids:
            return

        if breaking:
            item["breaking"] = True
            # Breaking: take first slot, push others down
            self._current["dynamic_1"] = item
            self._breaking_until = time.time() + BREAKING_HOLD_SECONDS
            asyncio.create_task(self._broadcast_slot("dynamic_1"))
        else:
            self._queue.appendleft(item)

        # On first batch, immediately fill all empty slots
        if not self._initialized:
            self._fill_empty_slots()

    def _fill_empty_slots(self):
        """Fill any empty dynamic slots from the queue."""
        for slot in DYNAMIC_SLOTS:
            if slot not in self._current and self._queue:
                self._current[slot] = self._queue.pop()
                asyncio.create_task(self._broadcast_slot(slot))
        if all(slot in self._current for slot in DYNAMIC_SLOTS):
            self._initialized = True

    def enrich(self, article_id: str, updates: dict):
        """Update an item in queue/current with AI summary data."""
        for item in self._queue:
            if item.get("article_id") == article_id:
                item.update(updates)
        for slot, item in self._current.items():
            if item and item.get("article_id") == article_id:
                item.update(updates)
                asyncio.create_task(self._broadcast_slot(slot))

    def promote_breaking(self, article_id: str):
        """Promote an article to breaking status."""
        for item in self._queue:
            if item.get("article_id") == article_id:
                item["breaking"] = True
                self._current["dynamic_1"] = item
                self._breaking_until = time.time() + BREAKING_HOLD_SECONDS
                asyncio.create_task(self._broadcast_slot("dynamic_1"))
                return

    async def rotation_loop(self):
        """Rotate dynamic tiles every ROTATION_INTERVAL seconds."""
        while True:
            await asyncio.sleep(ROTATION_INTERVAL)

            # Skip rotation during breaking news hold for slot 1
            if not self._queue:
                continue

            # Pick next slot to rotate (skip slot 1 during breaking hold)
            for _ in range(len(DYNAMIC_SLOTS)):
                slot = DYNAMIC_SLOTS[self._slot_index % len(DYNAMIC_SLOTS)]
                self._slot_index += 1
                if slot == "dynamic_1" and time.time() < self._breaking_until:
                    continue
                break

            if self._queue:
                item = self._queue.pop()
                self._current[slot] = item
                await self._broadcast_slot(slot)

    async def _broadcast_slot(self, slot: str):
        """Send update for a single dynamic slot."""
        item = self._current.get(slot)
        if item:
            await self.data_store.update(slot, item)
