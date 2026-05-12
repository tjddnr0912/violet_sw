"""Tests for src.data.gap_finder."""

from datetime import date
import pandas as pd

from src.data.store import save_bars, save_minute_bars
from src.data.gap_finder import find_gaps, find_minute_gaps


def _bars():
    idx = pd.date_range("2026-05-04 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[1,1,1],"High":[1,1,1],"Low":[1,1,1],"Close":[1,1,1],"Volume":[1,1,1]},
        index=idx,
    )


def test_find_gaps_returns_missing_trading_days(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-05", _bars(), source="kis")
    save_bars(tmp_path, "TQQQ", "2026-05-07", _bars(), source="kis")
    gaps = find_gaps(tmp_path, "TQQQ", date(2026, 5, 4), date(2026, 5, 8))
    # Trading days: 04 (Mon), 05 (Tue), 06 (Wed), 07 (Thu), 08 (Fri)
    # Stored: 05, 07. Missing: 04, 06, 08
    assert gaps == [date(2026, 5, 4), date(2026, 5, 6), date(2026, 5, 8)]


def test_find_gaps_excludes_weekends_and_holidays(tmp_path):
    # 2025-07-04 Fri is Independence Day (closed)
    # Range 2025-07-03 (Thu) ~ 2025-07-07 (Mon)
    gaps = find_gaps(tmp_path, "TQQQ", date(2025, 7, 3), date(2025, 7, 7))
    assert date(2025, 7, 4) not in gaps   # holiday
    assert date(2025, 7, 5) not in gaps   # Sat
    assert date(2025, 7, 6) not in gaps   # Sun
    assert sorted(gaps) == [date(2025, 7, 3), date(2025, 7, 7)]


def test_find_gaps_returns_empty_when_all_present(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-07", _bars(), source="kis")
    save_bars(tmp_path, "TQQQ", "2026-05-08", _bars(), source="kis")
    gaps = find_gaps(tmp_path, "TQQQ", date(2026, 5, 7), date(2026, 5, 8))
    assert gaps == []


# ───────────── M2: 1m partition gap finder ─────────────

def _bars_1m():
    idx = pd.date_range("2026-05-04 09:30", periods=10, freq="1min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[1]*10,"High":[1]*10,"Low":[1]*10,"Close":[1]*10,"Volume":[1]*10},
        index=idx,
    )


def test_find_minute_gaps_uses_1m_partition_independently(tmp_path):
    # Save only the 5m for 2026-05-05 but NOT the 1m → 1m gap present
    save_bars(tmp_path, "TQQQ", "2026-05-05", _bars(), source="kis")
    gaps = find_minute_gaps(tmp_path, "TQQQ", date(2026, 5, 4), date(2026, 5, 8))
    # All 5 trading days are missing 1m data (5m existence irrelevant)
    assert date(2026, 5, 4) in gaps
    assert date(2026, 5, 5) in gaps
    assert date(2026, 5, 6) in gaps


def test_find_minute_gaps_empty_when_all_1m_present(tmp_path):
    save_minute_bars(tmp_path, "TQQQ", "2026-05-07", _bars_1m(), source="kis")
    save_minute_bars(tmp_path, "TQQQ", "2026-05-08", _bars_1m(), source="kis")
    gaps = find_minute_gaps(tmp_path, "TQQQ", date(2026, 5, 7), date(2026, 5, 8))
    assert gaps == []
