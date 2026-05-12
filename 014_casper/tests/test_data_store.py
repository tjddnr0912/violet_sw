"""Tests for src.data.store (Parquet 5-min bar persistence)."""

import pandas as pd
import pytest

from src.data.store import (
    save_bars, load_bars, has_data, stats, _path_for,
)


def _sample_bars():
    idx = pd.date_range("2026-05-08 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {
            "Open":  [80.10, 80.50, 80.30],
            "High":  [80.55, 80.60, 80.40],
            "Low":   [80.05, 80.20, 80.15],
            "Close": [80.45, 80.40, 80.35],
            "Volume":[100000, 95000, 80000],
        },
        index=idx,
    )


def test_path_for_uses_underscore_for_caret(tmp_path):
    p = _path_for(tmp_path, "^VIX", "2026-05-08")
    assert "/_VIX/" in str(p)
    assert p.name == "2026-05-08.parquet"


def test_save_and_load_roundtrip(tmp_path):
    bars = _sample_bars()
    save_bars(tmp_path, "TQQQ", "2026-05-08", bars, source="kis")
    loaded = load_bars(tmp_path, "TQQQ", "2026-05-08")
    assert len(loaded) == 3
    assert loaded.iloc[0]["close"] == pytest.approx(80.45, rel=1e-4)
    assert all(loaded["source"] == "kis")


def test_save_is_atomic_no_tmp_leftover(tmp_path):
    bars = _sample_bars()
    save_bars(tmp_path, "TQQQ", "2026-05-08", bars, source="kis")
    leftovers = list(tmp_path.rglob("*.tmp"))
    assert leftovers == []


def test_save_overwrites_existing_same_day(tmp_path):
    bars1 = _sample_bars()
    save_bars(tmp_path, "TQQQ", "2026-05-08", bars1, source="yfinance")
    bars2 = bars1.copy()
    bars2.loc[bars2.index[0], "Close"] = 99.99
    save_bars(tmp_path, "TQQQ", "2026-05-08", bars2, source="kis")
    loaded = load_bars(tmp_path, "TQQQ", "2026-05-08")
    assert loaded.iloc[0]["close"] == pytest.approx(99.99, rel=1e-4)
    assert all(loaded["source"] == "kis")


def test_save_empty_returns_none(tmp_path):
    empty = pd.DataFrame()
    assert save_bars(tmp_path, "TQQQ", "2026-05-08", empty, source="kis") is None


def test_has_data_false_when_absent(tmp_path):
    assert has_data(tmp_path, "TQQQ", "2026-05-08") is False


def test_has_data_true_after_save(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-08", _sample_bars(), source="kis")
    assert has_data(tmp_path, "TQQQ", "2026-05-08") is True


def test_stats_reports_total_files_and_bytes(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-07", _sample_bars(), source="kis")
    save_bars(tmp_path, "QQQ", "2026-05-07", _sample_bars(), source="kis")
    s = stats(tmp_path)
    assert s["total_files"] == 2
    assert s["total_bytes"] > 0
    assert "TQQQ" in s["symbols"]
    assert "QQQ" in s["symbols"]
    assert s["symbols"]["TQQQ"]["days"] == 1


def test_stats_on_missing_dir():
    s = stats("/tmp/does_not_exist_marketdata_xxx")
    assert s == {"total_files": 0, "total_bytes": 0, "symbols": {}}


def test_load_bars_returns_none_when_missing(tmp_path):
    assert load_bars(tmp_path, "TQQQ", "2026-05-08") is None
