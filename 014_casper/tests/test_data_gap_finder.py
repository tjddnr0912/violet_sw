"""Tests for src.data.gap_finder."""

from datetime import date
import pandas as pd

from src.data.store import save_bars
from src.data.gap_finder import find_gaps


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
