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


def _get_qqq_daily_df_kis(lookback: int) -> Optional[pd.DataFrame]:
    """Fetch QQQ daily OHLC DataFrame via KIS."""
    bars = _kis_client.get_us_daily_chart("QQQ", count=lookback)
    if not bars or len(bars) < 1:
        return None
    rows = []
    for b in bars:
        try:
            d = datetime.strptime(b["date"], "%Y%m%d").date()
            rows.append({
                "date": d,
                "Open":  float(b.get("open", b.get("close", 0))),
                "High":  float(b["high"]),
                "Low":   float(b["low"]),
                "Close": float(b["close"]),
                "Volume": int(b.get("volume", 0)),
            })
        except (KeyError, ValueError, TypeError):
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows).set_index("date").sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def _get_qqq_daily_df_yf(lookback: int) -> Optional[pd.DataFrame]:
    """Fetch QQQ daily OHLC DataFrame via yfinance."""
    qqq = yf.Ticker("QQQ")
    # request enough days; yfinance gives more than 'period' worth
    period = f"{max(lookback + 10, 90)}d"
    hist = _yf_with_timeout(qqq.history, period=period, interval="1d")
    if hist is None or hist.empty:
        return None
    df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.tail(lookback)


def get_qqq_daily_df(lookback: int = 60) -> Optional[pd.DataFrame]:
    """Return the most recent `lookback` QQQ daily bars.

    Used by daily-bias scoring (ICT Phase 3). Tries the on-disk store first,
    then KIS, then yfinance. Always writes fresh fetches back to the store.
    """
    return get_daily_df("QQQ", lookback=lookback)


def get_daily_df(symbol: str, lookback: int = 60) -> Optional[pd.DataFrame]:
    """Generic daily-bar accessor for ICT/strategy use.

    Order of preference:
      1. On-disk Parquet (data/marketdata/<sym>/daily/) — instant
      2. KIS daily chart (live fetch + write-back to store)
      3. yfinance (live fetch + write-back)

    Returns DataFrame with columns Open/High/Low/Close/Volume indexed by
    pandas DatetimeIndex (tz-naive), or None on failure.
    """
    import os
    from src.data.store import load_daily_range, save_daily_bars

    base = os.path.join(
        os.path.dirname(__file__), "..", "..", "data", "marketdata"
    )
    base = os.path.abspath(base)

    # 1. Try the store first
    try:
        stored = load_daily_range(base, symbol, lookback=lookback)
        if stored is not None and len(stored) >= max(20, int(lookback * 0.8)):
            # Translate to OHLCV column case
            df = pd.DataFrame({
                "Open":   stored["open"].values,
                "High":   stored["high"].values,
                "Low":    stored["low"].values,
                "Close":  stored["close"].values,
                "Volume": stored["volume"].values if "volume" in stored.columns else 0,
            }, index=stored.index)
            logger.debug(f"{symbol} daily: served from store ({len(df)} rows)")
            return df
    except Exception as e:
        logger.warning(f"{symbol} daily store read failed (non-fatal): {e}")

    # 2/3. Live fetch (KIS → yfinance), then persist
    try:
        if _kis_client:
            df = _get_daily_df_kis(symbol, lookback)
            if df is not None and not df.empty:
                _persist_daily(base, symbol, df, source="kis")
                return df
            logger.warning(f"{symbol} daily: KIS failed, falling back to yfinance")

        df = _yf_fetch_with_cache_recovery(
            lambda: _get_daily_df_yf(symbol, lookback), f"{symbol}-daily-df"
        )
        if df is not None and not df.empty:
            _persist_daily(base, symbol, df, source="yfinance")
        return df
    except (FuturesTimeout, Exception) as e:
        logger.error(f"{symbol} daily df error: {type(e).__name__}: {e}")
        return None


def _persist_daily(base: str, symbol: str, df: pd.DataFrame, source: str) -> None:
    """Best-effort write-back to the daily store. Failures are silent."""
    try:
        from src.data.store import save_daily_bars
        save_daily_bars(base, symbol, df, source=source)
    except Exception as e:
        logger.debug(f"{symbol} daily persist failed (non-fatal): {e}")


def _get_daily_df_kis(symbol: str, lookback: int) -> Optional[pd.DataFrame]:
    """Generic version of _get_qqq_daily_df_kis for any US stock symbol."""
    bars = _kis_client.get_us_daily_chart(symbol, count=lookback)
    if not bars or len(bars) < 1:
        return None
    rows = []
    for b in bars:
        try:
            d = datetime.strptime(b["date"], "%Y%m%d").date()
            rows.append({
                "date": d,
                "Open":  float(b.get("open", b.get("close", 0))),
                "High":  float(b["high"]),
                "Low":   float(b["low"]),
                "Close": float(b["close"]),
                "Volume": int(b.get("volume", 0)),
            })
        except (KeyError, ValueError, TypeError):
            continue
    if not rows:
        return None
    df = pd.DataFrame(rows).set_index("date").sort_index()
    df.index = pd.to_datetime(df.index)
    return df


def _get_daily_df_yf(symbol: str, lookback: int) -> Optional[pd.DataFrame]:
    """Generic version of _get_qqq_daily_df_yf for any symbol."""
    ticker = yf.Ticker(symbol)
    period = f"{max(lookback + 10, 90)}d"
    hist = _yf_with_timeout(ticker.history, period=period, interval="1d")
    if hist is None or hist.empty:
        return None
    df = hist[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df.tail(lookback)


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


def _get_intraday_yf(symbol: str, period: str, interval: str,
                     prepost: bool = False) -> Optional[pd.DataFrame]:
    """Fetch intraday bars from yfinance (fallback).

    prepost=True extends the window to include premarket (04:00 ET) and
    afterhours (16:00~20:00 ET). Default False keeps RTH-only behavior.
    """
    ticker = yf.Ticker(symbol)
    df = _yf_with_timeout(ticker.history,
                          period=period, interval=interval, prepost=prepost)
    if df.empty:
        return None
    df.index = df.index.tz_convert(ET)
    logger.debug(f"{symbol} (yf, prepost={prepost}): {len(df)} bars ({df.index[0]} ~ {df.index[-1]})")
    return df


def get_intraday_bars(symbol: str, period: str = "1d",
                      interval: str = "5m",
                      prepost: bool = False) -> Optional[pd.DataFrame]:
    """Fetch intraday bars. KIS → yfinance.

    When prepost=True, KIS is bypassed (KIS API only exposes RTH for US
    stocks) and yfinance with extended-hours coverage is used. This is
    the path used to backfill premarket swing-fractal history.
    """
    try:
        if _kis_client and not prepost:
            result = _get_intraday_kis(symbol, interval)
            if result is not None:
                return result
            logger.warning(f"{symbol}: KIS intraday failed, falling back to yfinance")
        return _yf_fetch_with_cache_recovery(
            lambda: _get_intraday_yf(symbol, period, interval, prepost=prepost),
            symbol,
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
