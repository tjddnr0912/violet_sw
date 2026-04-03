"""Market data fetcher module.

Fetches VIX, QQQ daily (MA20), and intraday 5-min bars for TQQQ/SQQQ.
Uses yfinance for paper mode, KIS API for live mode.
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional, Tuple

import pandas as pd
import numpy as np
import yfinance as yf
import pytz

logger = logging.getLogger("casper")
ET = pytz.timezone("US/Eastern")

_YF_TIMEOUT = 30  # seconds


def _yf_with_timeout(func, *args, **kwargs):
    """Run a yfinance call with a timeout to prevent indefinite blocking."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func, *args, **kwargs)
        return future.result(timeout=_YF_TIMEOUT)


def _valid_price(value: float) -> bool:
    """Check if a price value is valid (finite, positive)."""
    return isinstance(value, (int, float)) and np.isfinite(value) and value > 0


def get_vix_close() -> Optional[float]:
    """Fetch latest VIX closing price."""
    try:
        vix = yf.Ticker("^VIX")
        hist = _yf_with_timeout(vix.history, period="5d", interval="1d")
        if hist.empty:
            logger.error("VIX: No data returned")
            return None
        close = float(hist["Close"].iloc[-1])
        if not _valid_price(close):
            logger.error(f"VIX: Invalid value {close}")
            return None
        logger.info(f"VIX: {close:.1f}")
        return close
    except (FuturesTimeout, Exception) as e:
        logger.error(f"VIX fetch error: {type(e).__name__}: {e}")
        return None


def get_qqq_trend_data(ma_period: int = 20) -> Tuple[Optional[float], Optional[float]]:
    """
    Fetch QQQ close and MA20 for trend determination.

    Returns:
        (qqq_close, qqq_ma20) or (None, None) on error.
    """
    try:
        qqq = yf.Ticker("QQQ")
        hist = _yf_with_timeout(qqq.history, period="3mo", interval="1d")
        if len(hist) < ma_period + 1:
            logger.error(f"QQQ: Not enough data ({len(hist)} bars, need {ma_period + 1})")
            return None, None

        close = float(hist["Close"].iloc[-1])
        ma = float(hist["Close"].rolling(ma_period).mean().iloc[-1])
        if not (_valid_price(close) and _valid_price(ma)):
            logger.error(f"QQQ: Invalid values close={close} ma={ma}")
            return None, None
        logger.info(f"QQQ: Close={close:.2f} MA{ma_period}={ma:.2f}")
        return close, ma
    except (FuturesTimeout, Exception) as e:
        logger.error(f"QQQ trend data error: {type(e).__name__}: {e}")
        return None, None


def get_intraday_bars(symbol: str, period: str = "1d", interval: str = "5m") -> Optional[pd.DataFrame]:
    """
    Fetch intraday 5-minute bars for given symbol.

    Args:
        symbol: Ticker symbol (TQQQ, SQQQ).
        period: yfinance period string.
        interval: Bar interval.

    Returns:
        DataFrame with OHLCV in ET timezone, or None on error.
    """
    try:
        ticker = yf.Ticker(symbol)
        df = _yf_with_timeout(ticker.history, period=period, interval=interval)
        if df.empty:
            logger.warning(f"{symbol}: No intraday data")
            return None

        df.index = df.index.tz_convert(ET)
        logger.debug(f"{symbol}: {len(df)} bars fetched ({df.index[0]} ~ {df.index[-1]})")
        return df
    except (FuturesTimeout, Exception) as e:
        logger.error(f"{symbol} intraday fetch error: {type(e).__name__}: {e}")
        return None


def get_avg_daily_range(symbol: str, days: int = 20) -> Optional[float]:
    """
    Calculate average daily High-Low range over N days.

    Args:
        symbol: Ticker symbol.
        days: Number of days for average.

    Returns:
        Average daily range in dollars, or None on error.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = _yf_with_timeout(ticker.history, period="3mo", interval="1d")
        if len(hist) < days:
            logger.warning(f"{symbol}: Not enough daily data ({len(hist)} < {days})")
            return None

        recent = hist.tail(days)
        adr = float((recent["High"] - recent["Low"]).mean())
        logger.debug(f"{symbol}: Avg Daily Range (ADR{days}) = ${adr:.2f}")
        return adr
    except (FuturesTimeout, Exception) as e:
        logger.error(f"{symbol} ADR error: {type(e).__name__}: {e}")
        return None


def get_current_price(symbol: str) -> Optional[float]:
    """
    Get latest price for a symbol.

    Args:
        symbol: Ticker symbol.

    Returns:
        Latest close price, or None on error.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = _yf_with_timeout(ticker.history, period="1d", interval="1m")
        if hist.empty:
            return None
        price = float(hist["Close"].iloc[-1])
        if not _valid_price(price):
            logger.error(f"{symbol}: Invalid price {price}")
            return None
        return price
    except (FuturesTimeout, Exception) as e:
        logger.error(f"{symbol} price error: {type(e).__name__}: {e}")
        return None
