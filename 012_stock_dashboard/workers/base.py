"""Base worker with async loop, error handling, and retry backoff."""

import asyncio
import logging

logger = logging.getLogger(__name__)


class BaseWorker:
    def __init__(self, data_store, interval: int):
        self.data_store = data_store
        self.interval = interval
        self._base_interval = interval
        self._error_count = 0
        self._running = True

    async def run(self):
        """Main loop: tick → sleep → repeat."""
        name = self.__class__.__name__
        logger.info(f"{name} started (interval={self.interval}s)")
        while self._running:
            try:
                await self.tick()
                self._error_count = 0
                self.interval = self._base_interval
            except Exception as e:
                self._error_count += 1
                logger.error(f"{name} tick error ({self._error_count}): {e}")
                if self._error_count >= 5:
                    self.interval = min(self._base_interval * 2, 600)
                    logger.warning(f"{name} backing off to {self.interval}s")
            await asyncio.sleep(self.interval)

    async def tick(self):
        """Override in subclass."""
        raise NotImplementedError

    def stop(self):
        self._running = False
