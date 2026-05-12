"""Tests for src.data.collector (threaded BarCollector)."""

import time

import pandas as pd
import pytest

from src.data.collector import BarCollector
from src.data.store import has_data


def _bars():
    idx = pd.date_range("2026-05-08 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[80]*3,"High":[80.5]*3,"Low":[79.5]*3,"Close":[80]*3,"Volume":[100]*3},
        index=idx,
    )


def test_collector_writes_bars_to_store(tmp_path):
    c = BarCollector(base_dir=tmp_path)
    c.start()
    try:
        c.submit(symbol="TQQQ", date_str="2026-05-08", bars=_bars(), source="kis")
        # poll up to 2s for thread to drain queue
        for _ in range(20):
            if has_data(tmp_path, "TQQQ", "2026-05-08"):
                break
            time.sleep(0.1)
        assert has_data(tmp_path, "TQQQ", "2026-05-08")
        assert c.saved_count == 1
    finally:
        c.stop(timeout=2)


def test_collector_does_not_raise_when_save_fails(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise IOError("disk full")
    monkeypatch.setattr("src.data.collector.save_bars", boom)
    c = BarCollector(base_dir=tmp_path)
    c.start()
    try:
        c.submit(symbol="TQQQ", date_str="2026-05-08", bars=_bars(), source="kis")
        time.sleep(0.3)
        assert c.is_alive()  # thread survived the IOError
    finally:
        c.stop(timeout=2)


def test_collector_drops_silently_when_queue_full(tmp_path):
    # do NOT start thread → queue cannot drain → fills up
    c = BarCollector(base_dir=tmp_path, queue_maxsize=1)
    c.submit("TQQQ", "2026-05-08", _bars(), source="kis")  # fills slot
    c.submit("TQQQ", "2026-05-09", _bars(), source="kis")  # should drop
    assert c.dropped_count >= 1


def test_collector_submit_empty_is_noop(tmp_path):
    c = BarCollector(base_dir=tmp_path)
    c.submit("TQQQ", "2026-05-08", pd.DataFrame(), source="kis")
    # No file written, no queue growth
    assert c._q.qsize() == 0


def test_collector_stop_is_idempotent(tmp_path):
    c = BarCollector(base_dir=tmp_path)
    c.start()
    c.stop(timeout=1)
    c.stop(timeout=1)  # should not raise


def test_collector_start_is_idempotent(tmp_path):
    c = BarCollector(base_dir=tmp_path)
    c.start()
    t1 = c._thread
    c.start()  # second start is a no-op while alive
    t2 = c._thread
    assert t1 is t2
    c.stop(timeout=1)
