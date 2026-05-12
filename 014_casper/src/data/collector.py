"""Realtime bar collector — threaded queue + safe drop on overflow.

Designed for in-process use from src/bot.py. Safety contract:

  - submit() NEVER raises (queue-full → drop + warn, exceptions swallowed)
  - the background thread NEVER dies on save errors (caught + logged)
  - stop() joins with timeout, then returns regardless of state

This isolation is what lets the casper trading main loop call
collector.submit() without any try/except wrapping.
"""

import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from src.data.store import save_bars

logger = logging.getLogger("casper")


@dataclass
class _Job:
    symbol: str
    date_str: str
    bars: pd.DataFrame
    source: str


class BarCollector:
    """Background-thread Parquet writer."""

    def __init__(self, base_dir, queue_maxsize: int = 256):
        self.base_dir = Path(base_dir)
        self._q: "queue.Queue[_Job]" = queue.Queue(maxsize=queue_maxsize)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.dropped_count = 0
        self.saved_count = 0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="BarCollector", daemon=True
        )
        self._thread.start()
        logger.info("BarCollector: thread started")

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def submit(self, symbol: str, date_str: str, bars: pd.DataFrame, source: str) -> None:
        if bars is None or bars.empty:
            return
        try:
            self._q.put_nowait(_Job(symbol, date_str, bars, source))
        except queue.Full:
            self.dropped_count += 1
            logger.warning(f"BarCollector: queue full, dropped {symbol} {date_str}")
        except Exception as e:  # last-resort guard
            self.dropped_count += 1
            logger.warning(f"BarCollector: submit failed silently: {e}")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                save_bars(self.base_dir, job.symbol, job.date_str, job.bars, job.source)
                self.saved_count += 1
            except Exception as e:
                logger.warning(
                    f"BarCollector: save failed for {job.symbol} {job.date_str}: {e}"
                )

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            logger.info(
                f"BarCollector: stopped (saved={self.saved_count} dropped={self.dropped_count})"
            )
