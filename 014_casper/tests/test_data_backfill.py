"""Tests for src.data.backfill.

yfinance is mocked so tests are deterministic and offline.
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd
import pytest

from src.data.backfill import fill_gaps_from_yfinance
from src.data.store import has_data


def _fake_yf_history(day: date):
    idx = pd.date_range(f"{day.isoformat()} 09:30", periods=78, freq="5min",
                        tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[80.0]*78, "High":[80.5]*78, "Low":[79.5]*78,
         "Close":[80.0]*78, "Volume":[1000]*78},
        index=idx,
    )


def test_fill_gaps_writes_parquet_for_each_gap(tmp_path):
    today = datetime.now(timezone.utc).date()
    g1 = today - timedelta(days=3)
    g2 = today - timedelta(days=4)
    gaps = [g1, g2]

    def fake(symbol, day):
        return _fake_yf_history(day)

    with patch("src.data.backfill._fetch_yf", side_effect=fake):
        filled = fill_gaps_from_yfinance(tmp_path, "TQQQ", gaps)

    assert filled == 2
    assert has_data(tmp_path, "TQQQ", g1.isoformat())
    assert has_data(tmp_path, "TQQQ", g2.isoformat())


def test_fill_gaps_skips_unrecoverable_days_beyond_60(tmp_path):
    old_day = (datetime.now(timezone.utc).date() - timedelta(days=120))
    gaps = [old_day]
    filled = fill_gaps_from_yfinance(tmp_path, "TQQQ", gaps)
    assert filled == 0
    assert not has_data(tmp_path, "TQQQ", old_day.isoformat())


def test_fill_gaps_handles_empty_response_silently(tmp_path):
    today = datetime.now(timezone.utc).date()
    g = today - timedelta(days=3)
    gaps = [g]
    with patch("src.data.backfill._fetch_yf", return_value=pd.DataFrame()):
        filled = fill_gaps_from_yfinance(tmp_path, "TQQQ", gaps)
    assert filled == 0
    assert not has_data(tmp_path, "TQQQ", g.isoformat())


def test_fill_gaps_handles_yf_exception_silently(tmp_path):
    today = datetime.now(timezone.utc).date()
    g = today - timedelta(days=3)
    gaps = [g]
    # _fetch_yf catches exceptions internally and returns empty df
    with patch("src.data.backfill._fetch_yf", return_value=pd.DataFrame()):
        filled = fill_gaps_from_yfinance(tmp_path, "TQQQ", gaps)
    assert filled == 0
