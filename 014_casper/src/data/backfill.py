"""Backfill missing days via yfinance.

5-minute interval: ~60 day rolling window on yfinance.
1-minute interval: ~8 day rolling window (much stricter — see M2).
Older days are silently skipped (unrecoverable from this source).
"""

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import List

import pandas as pd
import yfinance as yf

from src.data.store import save_bars, save_minute_bars

logger = logging.getLogger("casper")

YF_RETENTION_DAYS = 60
YF_1M_RETENTION_DAYS = 8   # yfinance 1m interval limit
_INTER_REQUEST_SLEEP = 0.3


def _fetch_yf(symbol: str, day: date, interval: str = "5m") -> pd.DataFrame:
    """Fetch a single trading day of bars from yfinance.

    Args:
        interval: "5m" (default) or "1m". Both windowed to RTH 09:30~15:59 ET.

    Returns an empty DataFrame on any failure or out-of-range request.
    """
    try:
        end = day + timedelta(days=1)
        df = yf.download(
            symbol,
            start=day.isoformat(),
            end=end.isoformat(),
            interval=interval,
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
        logger.warning(f"yfinance {interval} fetch failed for {symbol} {day}: {e}")
        return pd.DataFrame()


def fill_gaps_from_yfinance(base, symbol: str, gaps: List[date]) -> int:
    """Fill given gaps using yfinance 5m. Returns count of days written.

    Days older than YF_RETENTION_DAYS are skipped (logged once).
    """
    today = datetime.now(timezone.utc).date()
    filled = 0
    for day in gaps:
        if (today - day).days > YF_RETENTION_DAYS:
            logger.info(f"backfill: {symbol} {day} unrecoverable (>{YF_RETENTION_DAYS}d)")
            continue
        df = _fetch_yf(symbol, day, interval="5m")
        if df.empty:
            continue
        save_bars(base, symbol, day.isoformat(), df, source="yfinance")
        filled += 1
        time.sleep(_INTER_REQUEST_SLEEP)
    return filled


def fill_minute_gaps_from_yfinance(base, symbol: str, gaps: List[date]) -> int:
    """Fill given gaps with yfinance 1m bars (8-day rolling window).

    Written to the 1m partition (base/<sym>/1m/<year>/<date>.parquet) so 5m
    data is untouched. Days older than YF_1M_RETENTION_DAYS are skipped.

    Returns count of days actually written.
    """
    today = datetime.now(timezone.utc).date()
    filled = 0
    for day in gaps:
        if (today - day).days > YF_1M_RETENTION_DAYS:
            logger.debug(
                f"1m backfill: {symbol} {day} unrecoverable "
                f"(>{YF_1M_RETENTION_DAYS}d, yfinance limit)"
            )
            continue
        df = _fetch_yf(symbol, day, interval="1m")
        if df.empty:
            continue
        save_minute_bars(base, symbol, day.isoformat(), df, source="yfinance")
        filled += 1
        time.sleep(_INTER_REQUEST_SLEEP)
    return filled
