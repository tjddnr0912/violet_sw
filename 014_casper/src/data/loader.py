"""Unified data load API for backtests / analysis."""

from datetime import date

import pandas as pd

from src.data.store import load_bars
from src.data.calendar import trading_days


def load_range(base, symbol: str, start: date, end: date) -> pd.DataFrame:
    """Load and concatenate bars for [start, end] (trading days only).

    Missing days are skipped silently. Returns an empty DataFrame when
    nothing is stored. The result is sorted by timestamp ascending.
    """
    parts = []
    for d in trading_days(start, end):
        df = load_bars(base, symbol, d.isoformat())
        if df is not None and not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
