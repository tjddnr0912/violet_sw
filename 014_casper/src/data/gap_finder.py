"""Detect missing trading days in the Parquet store."""

from datetime import date
from typing import List

from src.data.calendar import trading_days
from src.data.store import has_data, has_minute_data


def find_gaps(base, symbol: str, start: date, end: date) -> List[date]:
    """Return sorted trading days in [start, end] missing a 5m parquet."""
    expected = trading_days(start, end)
    return [d for d in expected if not has_data(base, symbol, d.isoformat())]


def find_minute_gaps(base, symbol: str, start: date, end: date) -> List[date]:
    """Return sorted trading days in [start, end] missing a 1m parquet."""
    expected = trading_days(start, end)
    return [d for d in expected if not has_minute_data(base, symbol, d.isoformat())]
