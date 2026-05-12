"""Backfill missing days via yfinance (60-day rolling window).

yfinance's 5-minute interval is limited to the last ~60 calendar days.
Anything older is silently skipped (unrecoverable from this source).
"""

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import List

import pandas as pd
import yfinance as yf

from src.data.store import save_bars

logger = logging.getLogger("casper")

YF_RETENTION_DAYS = 60
_INTER_REQUEST_SLEEP = 0.3


def _fetch_yf(symbol: str, day: date) -> pd.DataFrame:
    """Fetch a single trading day of 5-min bars from yfinance.

    Returns an empty DataFrame on any failure or out-of-range request.
    """
    try:
        end = day + timedelta(days=1)
        df = yf.download(
            symbol,
            start=day.isoformat(),
            end=end.isoformat(),
            interval="5m",
            progress=False,
            auto_adjust=False,
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        if df.empty:
            return df
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert("US/Eastern")
        else:
            df.index = df.index.tz_convert("US/Eastern")
        return df.between_time("09:30", "15:59")
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {symbol} {day}: {e}")
        return pd.DataFrame()


def fill_gaps_from_yfinance(base, symbol: str, gaps: List[date]) -> int:
    """Fill given gaps using yfinance. Returns count of days actually written.

    Days older than YF_RETENTION_DAYS are skipped (logged once).
    """
    today = datetime.now(timezone.utc).date()
    filled = 0
    for day in gaps:
        if (today - day).days > YF_RETENTION_DAYS:
            logger.info(f"backfill: {symbol} {day} unrecoverable (>{YF_RETENTION_DAYS}d)")
            continue
        df = _fetch_yf(symbol, day)
        if df.empty:
            continue
        save_bars(base, symbol, day.isoformat(), df, source="yfinance")
        filled += 1
        time.sleep(_INTER_REQUEST_SLEEP)
    return filled
