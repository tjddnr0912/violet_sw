"""Market data fetcher module.

Fetches VIX, QQQ daily (MA20), and intraday 5-min bars for TQQQ/SQQQ.
Data source priority: KIS API (primary) → yfinance (fallback).
VIX: yfinance only (KIS does not provide index data).
"""

import glob
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
import numpy as np
import yfinance as yf
import pytz

logger = logging.getLogger("casper")
ET = pytz.timezone("US/Eastern")

_YF_TIMEOUT = 30  # seconds
_yf_cache_reset_count = 0

# KIS client reference — set by bot.py at startup
_kis_client = None


def set_kis_client(client) -> None:
    """Inject KIS client for API-based data fetching."""
    global _kis_client
    _kis_client = client
    if client:
        logger.info("MarketData: KIS client configured (KIS primary, yfinance fallback)")
    else:
        logger.info("MarketData: No KIS client (yfinance only)")


_yf_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yf")


def _yf_with_timeout(func, *args, **kwargs):
    """Run a yfinance call with a timeout to prevent indefinite blocking."""
    future = _yf_executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=_YF_TIMEOUT)
    except FuturesTimeout:
        future.cancel()
        raise


def _reset_yf_cache() -> bool:
    """Delete corrupted yfinance SQLite cache files and reinitialize.

    Returns True if cache was reset successfully.
    """
    global _yf_cache_reset_count
    try:
        import platformdirs
        cache_dir = os.path.join(platformdirs.user_cache_dir(), "py-yfinance")
        if not os.path.isdir(cache_dir):
            return False

        # Delete all DB files (*.db, *.db-wal, *.db-shm)
        removed = []
        for pattern in ("*.db", "*.db-wal", "*.db-shm"):
            for f in glob.glob(os.path.join(cache_dir, pattern)):
                os.remove(f)
                removed.append(os.path.basename(f))

        if not removed:
            return False

        # Reset yfinance internal DB managers so they reinitialize
        from yfinance.cache import set_cache_location
        set_cache_location(cache_dir)

        _yf_cache_reset_count += 1
        logger.warning(f"yfinance cache reset #{_yf_cache_reset_count}: removed {removed}")
        return True
    except Exception as e:
        logger.error(f"yfinance cache reset failed: {e}")
        return False


def _is_sqlite_error(e: Exception) -> bool:
    """Check if exception is a SQLite OperationalError."""
    return "OperationalError" in type(e).__name__ or "unable to open database" in str(e)


def _valid_price(value: float) -> bool:
    """Check if a price value is valid (finite, positive)."""
    return isinstance(value, (int, float)) and np.isfinite(value) and value > 0


# ─── VIX (yfinance only — KIS does not provide index data) ───

def get_vix_close() -> Optional[float]:
    """Fetch latest VIX closing price. yfinance only."""
    return _yf_fetch_with_cache_recovery(_fetch_vix, "VIX")


def _fetch_vix() -> Optional[float]:
    """Internal VIX fetch."""
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


def _yf_fetch_with_cache_recovery(fetch_fn, label: str):
    """Run a yfinance fetch, resetting cache on SQLite errors."""
    try:
        return fetch_fn()
    except Exception as e:
        if _is_sqlite_error(e):
            logger.warning(f"{label}: SQLite error detected, resetting yfinance cache")
            if _reset_yf_cache():
                try:
                    return fetch_fn()
                except Exception as e2:
                    logger.error(f"{label} fetch error after cache reset: {type(e2).__name__}: {e2}")
                    return None
        logger.error(f"{label} fetch error: {type(e).__name__}: {e}")
        return None


# ─── QQQ Trend Data (KIS primary → yfinance fallback) ───

def _get_qqq_trend_kis(ma_period: int) -> Tuple[Optional[float], Optional[float]]:
    """Fetch QQQ trend data from KIS daily chart API."""
    bars = _kis_client.get_us_daily_chart("QQQ", count=ma_period + 10)
    if not bars or len(bars) < ma_period + 1:
        return None, None

    closes = [b["close"] for b in bars]
    close = closes[-1]
    ma = sum(closes[-ma_period:]) / ma_period

    if not (_valid_price(close) and _valid_price(ma)):
        return None, None

    logger.info(f"QQQ (KIS): Close={close:.2f} MA{ma_period}={ma:.2f}")
    return close, ma


def _get_qqq_trend_yf(ma_period: int) -> Tuple[Optional[float], Optional[float]]:
    """Fetch QQQ trend data from yfinance (fallback)."""
    qqq = yf.Ticker("QQQ")
    hist = _yf_with_timeout(qqq.history, period="3mo", interval="1d")
    if len(hist) < ma_period + 1:
        logger.error(f"QQQ (yf): Not enough data ({len(hist)} bars)")
        return None, None

    close = float(hist["Close"].iloc[-1])
    ma = float(hist["Close"].rolling(ma_period).mean().iloc[-1])
    if not (_valid_price(close) and _valid_price(ma)):
        return None, None

    logger.info(f"QQQ (yf): Close={close:.2f} MA{ma_period}={ma:.2f}")
    return close, ma


def get_qqq_trend_data(ma_period: int = 20) -> Tuple[Optional[float], Optional[float]]:
    """Fetch QQQ close and MA for trend determination. KIS → yfinance."""
    try:
        if _kis_client:
            result = _get_qqq_trend_kis(ma_period)
            if result[0] is not None:
                return result
            logger.warning("QQQ: KIS failed, falling back to yfinance")
        return _yf_fetch_with_cache_recovery(
            lambda: _get_qqq_trend_yf(ma_period), "QQQ"
        ) or (None, None)
    except (FuturesTimeout, Exception) as e:
        logger.error(f"QQQ trend data error: {type(e).__name__}: {e}")
        return None, None


# ─── Intraday Bars (KIS primary → yfinance fallback) ───

def _kis_bars_to_dataframe(bars: list) -> Optional[pd.DataFrame]:
    """Convert KIS minute chart bars to pandas DataFrame with ET timezone index."""
    if not bars:
        return None

    records = []
    for b in bars:
        try:
            date_str = b["date"]
            time_str = b["time"]
            if len(date_str) == 8 and len(time_str) >= 6:
                dt = datetime.strptime(f"{date_str}{time_str[:6]}", "%Y%m%d%H%M%S")
                dt = ET.localize(dt)
            else:
                continue
            records.append({
                "datetime": dt,
                "Open": b["open"],
                "High": b["high"],
                "Low": b["low"],
                "Close": b["close"],
                "Volume": b["volume"],
            })
        except (ValueError, KeyError):
            continue

    if not records:
        return None

    df = pd.DataFrame(records)
    df.set_index("datetime", inplace=True)
    df.sort_index(inplace=True)
    # Remove duplicates
    df = df[~df.index.duplicated(keep='last')]
    return df


def _get_intraday_kis(symbol: str, interval: str) -> Optional[pd.DataFrame]:
    """Fetch intraday bars from KIS API."""
    nmin = int(interval.replace("m", "")) if interval.endswith("m") else 5
    bars = _kis_client.get_us_minute_chart(symbol, nmin=nmin)
    if not bars:
        return None

    df = _kis_bars_to_dataframe(bars)
    if df is None or df.empty:
        return None

    logger.debug(f"{symbol} (KIS): {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")
    return df


def _get_intraday_yf(symbol: str, period: str, interval: str) -> Optional[pd.DataFrame]:
    """Fetch intraday bars from yfinance (fallback)."""
    ticker = yf.Ticker(symbol)
    df = _yf_with_timeout(ticker.history, period=period, interval=interval)
    if df.empty:
        return None
    df.index = df.index.tz_convert(ET)
    logger.debug(f"{symbol} (yf): {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")
    return df


def get_intraday_bars(symbol: str, period: str = "1d",
                      interval: str = "5m") -> Optional[pd.DataFrame]:
    """Fetch intraday bars. KIS → yfinance."""
    try:
        if _kis_client:
            result = _get_intraday_kis(symbol, interval)
            if result is not None:
                return result
            logger.warning(f"{symbol}: KIS intraday failed, falling back to yfinance")
        return _yf_fetch_with_cache_recovery(
            lambda: _get_intraday_yf(symbol, period, interval), symbol
        )
    except (FuturesTimeout, Exception) as e:
        logger.error(f"{symbol} intraday fetch error: {type(e).__name__}: {e}")
        return None


# ─── Average Daily Range (KIS primary → yfinance fallback) ───

def _get_adr_kis(symbol: str, days: int) -> Optional[float]:
    """Calculate ADR from KIS daily chart."""
    bars = _kis_client.get_us_daily_chart(symbol, count=days + 5)
    if not bars or len(bars) < days:
        return None

    recent = bars[-days:]
    ranges = [b["high"] - b["low"] for b in recent if b["high"] > 0 and b["low"] > 0]
    if not ranges:
        return None

    adr = sum(ranges) / len(ranges)
    logger.debug(f"{symbol} ADR (KIS): ${adr:.2f} ({len(ranges)}d)")
    return adr


def _get_adr_yf(symbol: str, days: int) -> Optional[float]:
    """Calculate ADR from yfinance (fallback)."""
    ticker = yf.Ticker(symbol)
    hist = _yf_with_timeout(ticker.history, period="3mo", interval="1d")
    if len(hist) < days:
        return None

    recent = hist.tail(days)
    adr = float((recent["High"] - recent["Low"]).mean())
    logger.debug(f"{symbol} ADR (yf): ${adr:.2f}")
    return adr


def get_avg_daily_range(symbol: str, days: int = 20) -> Optional[float]:
    """Calculate average daily range. KIS → yfinance."""
    try:
        if _kis_client:
            result = _get_adr_kis(symbol, days)
            if result is not None:
                return result
            logger.warning(f"{symbol}: KIS ADR failed, falling back to yfinance")
        return _yf_fetch_with_cache_recovery(
            lambda: _get_adr_yf(symbol, days), f"{symbol} ADR"
        )
    except (FuturesTimeout, Exception) as e:
        logger.error(f"{symbol} ADR error: {type(e).__name__}: {e}")
        return None


# ─── Current Price (KIS primary → yfinance fallback) ───

def _get_price_kis(symbol: str) -> Optional[float]:
    """Get current price from KIS API."""
    data = _kis_client.get_us_price(symbol)
    if data and _valid_price(data.get("price", 0)):
        return data["price"]
    return None


def _get_price_yf(symbol: str) -> Optional[float]:
    """Get current price from yfinance (fallback)."""
    ticker = yf.Ticker(symbol)
    hist = _yf_with_timeout(ticker.history, period="1d", interval="1m")
    if hist.empty:
        return None
    price = float(hist["Close"].iloc[-1])
    if not _valid_price(price):
        return None
    return price


def get_current_price(symbol: str) -> Optional[float]:
    """Get latest price. KIS → yfinance."""
    try:
        if _kis_client:
            result = _get_price_kis(symbol)
            if result is not None:
                return result
            logger.warning(f"{symbol}: KIS price failed, falling back to yfinance")
        return _yf_fetch_with_cache_recovery(
            lambda: _get_price_yf(symbol), f"{symbol} price"
        )
    except (FuturesTimeout, Exception) as e:
        logger.error(f"{symbol} price error: {type(e).__name__}: {e}")
        return None
