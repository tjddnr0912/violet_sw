"""Tests for daily-bar persistence (added 2026-05-12)."""

from datetime import date, datetime
import pandas as pd
import pytest

from src.data.store import (
    save_daily_bars, load_daily_bars, load_daily_range, daily_last_date,
    _daily_path_for,
)


def _daily_df(start="2026-04-01", n=10, base=100.0):
    idx = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({
        "Open":  [base + i * 0.5 for i in range(n)],
        "High":  [base + i * 0.5 + 0.5 for i in range(n)],
        "Low":   [base + i * 0.5 - 0.5 for i in range(n)],
        "Close": [base + i * 0.5 + 0.2 for i in range(n)],
        "Volume":[1000 + i for i in range(n)],
    }, index=idx)


def test_daily_path_for_yearly_partition(tmp_path):
    p = _daily_path_for(tmp_path, "QQQ", 2026)
    assert p.name == "2026.parquet"
    assert "/QQQ/daily/" in str(p)


def test_save_and_load_single_year(tmp_path):
    bars = _daily_df("2026-04-01", n=10)
    paths = save_daily_bars(tmp_path, "QQQ", bars, source="kis")
    assert len(paths) == 1
    loaded = load_daily_bars(tmp_path, "QQQ", 2026)
    assert loaded is not None
    assert len(loaded) == 10
    assert loaded["close"].iloc[0] == pytest.approx(100.2, rel=1e-4)


def test_save_splits_multi_year(tmp_path):
    bars = _daily_df("2025-12-15", n=20)  # spans 2025 and 2026
    paths = save_daily_bars(tmp_path, "QQQ", bars, source="kis")
    assert len(paths) == 2
    assert load_daily_bars(tmp_path, "QQQ", 2025) is not None
    assert load_daily_bars(tmp_path, "QQQ", 2026) is not None


def test_save_merges_with_existing_dedup(tmp_path):
    first = _daily_df("2026-04-01", n=10, base=100.0)
    save_daily_bars(tmp_path, "QQQ", first)
    # Overlapping range with new values
    second = _daily_df("2026-04-08", n=10, base=200.0)
    save_daily_bars(tmp_path, "QQQ", second)
    loaded = load_daily_bars(tmp_path, "QQQ", 2026)
    # Combined dates: 04-01..04-21 (business days). De-duplicated.
    assert loaded.index.is_unique
    # Overlap rows should take the LATEST (second) value
    overlap_date = pd.Timestamp("2026-04-08")
    if overlap_date in loaded.index:
        assert loaded.loc[overlap_date, "close"] > 150.0  # from second batch


def test_load_daily_range_returns_tail(tmp_path):
    bars = _daily_df("2026-04-01", n=30)
    save_daily_bars(tmp_path, "QQQ", bars)
    out = load_daily_range(tmp_path, "QQQ", lookback=10)
    assert len(out) == 10


def test_load_daily_range_returns_none_when_empty(tmp_path):
    out = load_daily_range(tmp_path, "QQQ", lookback=10)
    assert out is None


def test_daily_last_date(tmp_path):
    bars = _daily_df("2026-04-01", n=5)
    save_daily_bars(tmp_path, "QQQ", bars)
    last = daily_last_date(tmp_path, "QQQ")
    assert last is not None
    assert "2026-" in last


def test_daily_last_date_returns_none_when_missing(tmp_path):
    assert daily_last_date(tmp_path, "QQQ") is None


def test_save_empty_returns_empty_list(tmp_path):
    assert save_daily_bars(tmp_path, "QQQ", pd.DataFrame()) == []


def test_save_atomic_no_tmp_leftover(tmp_path):
    bars = _daily_df("2026-04-01", n=5)
    save_daily_bars(tmp_path, "QQQ", bars)
    leftover = list(tmp_path.rglob("*.tmp"))
    assert leftover == []
