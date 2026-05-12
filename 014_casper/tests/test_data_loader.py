"""Tests for src.data.loader."""

from datetime import date

import pandas as pd
import pytest

from src.data.store import save_bars
from src.data.loader import load_range


def _bars(date_str, base=80.0):
    idx = pd.date_range(f"{date_str} 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[base]*3,"High":[base+0.5]*3,"Low":[base-0.5]*3,
         "Close":[base]*3,"Volume":[100]*3},
        index=idx,
    )


def test_load_range_concatenates_days_in_order(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-06", _bars("2026-05-06", 80.0), source="kis")
    save_bars(tmp_path, "TQQQ", "2026-05-07", _bars("2026-05-07", 81.0), source="kis")
    save_bars(tmp_path, "TQQQ", "2026-05-08", _bars("2026-05-08", 82.0), source="kis")
    df = load_range(tmp_path, "TQQQ", date(2026, 5, 6), date(2026, 5, 8))
    assert len(df) == 9
    assert df.iloc[0]["close"] == pytest.approx(80.0, rel=1e-4)
    assert df.iloc[-1]["close"] == pytest.approx(82.0, rel=1e-4)
    # Sorted ascending by timestamp
    assert (df["timestamp"].diff().dropna() > 0).all()


def test_load_range_returns_empty_when_no_files(tmp_path):
    df = load_range(tmp_path, "TQQQ", date(2026, 5, 6), date(2026, 5, 8))
    assert df.empty


def test_load_range_skips_non_trading_days_silently(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-07", _bars("2026-05-07"), source="kis")
    # 2026-05-09 = Sat, 2026-05-10 = Sun → no files expected
    df = load_range(tmp_path, "TQQQ", date(2026, 5, 7), date(2026, 5, 10))
    assert len(df) == 3
