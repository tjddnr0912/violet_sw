"""Integration tests for CasperBot's collector hooks.

We instantiate CasperBot via __new__ to bypass real init (KIS auth etc.)
and exercise only the data-collector methods.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from src.bot import CasperBot


def _bars():
    idx = pd.date_range("2026-05-08 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[80]*3,"High":[80.5]*3,"Low":[79.5]*3,"Close":[80]*3,"Volume":[100]*3},
        index=idx,
    )


def test_collector_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_COLLECTION", raising=False)
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(str(tmp_path))
    assert bot.collector is None


def test_collector_enabled_when_env_on(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "on")
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(str(tmp_path))
    assert bot.collector is not None
    assert bot.collector.is_alive()
    bot.collector.stop(timeout=2)


def test_record_bars_noop_when_collector_none():
    bot = CasperBot.__new__(CasperBot)
    bot.collector = None
    # Must not raise
    bot._record_bars("TQQQ", _bars())


def test_record_bars_submits_to_collector(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "on")
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(str(tmp_path))
    try:
        bot._record_bars("TQQQ", _bars())
        # poll up to 2s for collector thread to drain
        import time
        from src.data.store import has_data
        for _ in range(20):
            if has_data(tmp_path, "TQQQ", "2026-05-08"):
                break
            time.sleep(0.1)
        assert has_data(tmp_path, "TQQQ", "2026-05-08")
    finally:
        bot.collector.stop(timeout=2)


def test_record_bars_empty_is_silent(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "on")
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(str(tmp_path))
    try:
        bot._record_bars("TQQQ", pd.DataFrame())  # empty
        # Nothing should be queued
        assert bot.collector._q.qsize() == 0
    finally:
        bot.collector.stop(timeout=2)


def test_cold_start_backfill_skipped_when_collector_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "off")
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(str(tmp_path))
    assert bot.collector is None
    with patch("src.data.backfill.fill_gaps_from_yfinance") as mock_fill:
        bot._cold_start_backfill(str(tmp_path), symbols=["TQQQ"])
    assert not mock_fill.called


def test_cold_start_backfill_runs_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "on")
    monkeypatch.setenv("DATA_COLLECTION_BACKFILL", "on")
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(str(tmp_path))
    try:
        with patch("src.data.backfill.fill_gaps_from_yfinance", return_value=0) as mock_fill:
            bot._cold_start_backfill(str(tmp_path), symbols=["TQQQ"])
        assert mock_fill.called
    finally:
        bot.collector.stop(timeout=2)


def test_cold_start_backfill_skipped_by_explicit_flag(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "on")
    monkeypatch.setenv("DATA_COLLECTION_BACKFILL", "off")
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(str(tmp_path))
    try:
        with patch("src.data.backfill.fill_gaps_from_yfinance") as mock_fill:
            bot._cold_start_backfill(str(tmp_path), symbols=["TQQQ"])
        assert not mock_fill.called
    finally:
        bot.collector.stop(timeout=2)
