"""NQ futures 24h data via yfinance (ICT Phase 4 — Power of 3).

KIS Open API doesn't expose Nasdaq-100 e-mini (NQ) futures intraday.
yfinance provides ~60 days of 5-min NQ=F bars across the full 23-hour
session (Sun 18:00 ET ~ Fri 17:00 ET), which is enough for:

  - **Asia accumulation box** (18:00 ~ 00:00 ET prior day)
  - **Midnight Open** (00:00 ET — ICT True Open)
  - **London session** (02:00 ~ 05:00 ET)
  - **Pre-market** (06:00 ~ 09:30 ET)

These windows are unavailable from KIS RTH-only minute charts.
"""

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger("casper")


def fetch_nq_futures_5m(period: str = "60d") -> Optional[pd.DataFrame]:
    """Fetch NQ=F 5-min bars from yfinance (24h coverage).

    Returns DataFrame indexed in US/Eastern timezone, with columns
    Open/High/Low/Close/Volume. None on failure.
    """
    try:
        df = yf.download("NQ=F", period=period, interval="5m",
                         progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        if df.empty:
            return None
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC").tz_convert("US/Eastern")
        else:
            df.index = df.index.tz_convert("US/Eastern")
        return df
    except Exception as e:
        logger.warning(f"NQ futures fetch failed (non-fatal): {e}")
        return None


def asia_session_range(bars: pd.DataFrame, day) -> Optional[tuple[float, float]]:
    """Asia session high/low for the trading day `day` (ICT 18:00 prior ~ 00:00 day ET).

    Returns (high, low) or None if data is missing.
    """
    if bars is None or bars.empty:
        return None
    # Asia session spans the PREVIOUS calendar day 18:00 → THIS day 00:00 ET
    prev = pd.Timestamp(day) - pd.Timedelta(days=1)
    start = pd.Timestamp(prev.date()).tz_localize("US/Eastern") + pd.Timedelta(hours=18)
    end = pd.Timestamp(pd.Timestamp(day).date()).tz_localize("US/Eastern")  # 00:00 ET
    win = bars[(bars.index >= start) & (bars.index < end)]
    if win.empty:
        return None
    return float(win["High"].max()), float(win["Low"].min())


def london_session_range(bars: pd.DataFrame, day) -> Optional[tuple[float, float]]:
    """London Killzone 02:00 ~ 05:00 ET."""
    if bars is None or bars.empty:
        return None
    day = pd.Timestamp(day).date()
    start = pd.Timestamp(day).tz_localize("US/Eastern") + pd.Timedelta(hours=2)
    end = pd.Timestamp(day).tz_localize("US/Eastern") + pd.Timedelta(hours=5)
    win = bars[(bars.index >= start) & (bars.index < end)]
    if win.empty:
        return None
    return float(win["High"].max()), float(win["Low"].min())


def premarket_session_range(bars: pd.DataFrame, day) -> Optional[tuple[float, float]]:
    """Pre-market session 06:00 ~ 09:30 ET (just before RTH open).

    Strong liquidity reference because NY trader stops cluster here.
    """
    if bars is None or bars.empty:
        return None
    day = pd.Timestamp(day).date()
    start = pd.Timestamp(day).tz_localize("US/Eastern") + pd.Timedelta(hours=6)
    end = pd.Timestamp(day).tz_localize("US/Eastern") + pd.Timedelta(hours=9, minutes=30)
    win = bars[(bars.index >= start) & (bars.index < end)]
    if win.empty:
        return None
    return float(win["High"].max()), float(win["Low"].min())


def midnight_open_price(bars: pd.DataFrame, day) -> Optional[float]:
    """Return the Open of the 00:00 ET 5-min bar for the given day (ICT True Open)."""
    if bars is None or bars.empty:
        return None
    day = pd.Timestamp(day).date()
    target = pd.Timestamp(day).tz_localize("US/Eastern")  # 00:00 ET
    candidates = bars[(bars.index >= target) & (bars.index < target + pd.Timedelta(minutes=5))]
    if candidates.empty:
        return None
    return float(candidates["Open"].iloc[0])


def detect_judas_swing(bars: pd.DataFrame, day,
                       asia_range: Optional[tuple[float, float]] = None) -> Optional[str]:
    """Detect ICT Judas Swing: which side of Asia range was first breached
    *and reversed* during 00:00 ~ 09:30 ET.

    Returns:
      'bullish_judas'  — price first wicked BELOW Asia low then reversed up
      'bearish_judas'  — price first wicked ABOVE Asia high then reversed down
      None             — neither / inconclusive
    """
    if bars is None or bars.empty:
        return None
    if asia_range is None:
        asia_range = asia_session_range(bars, day)
        if asia_range is None:
            return None
    asia_h, asia_l = asia_range
    day = pd.Timestamp(day).date()
    start = pd.Timestamp(day).tz_localize("US/Eastern")
    end = pd.Timestamp(day).tz_localize("US/Eastern") + pd.Timedelta(hours=9, minutes=30)
    win = bars[(bars.index >= start) & (bars.index < end)]
    if win.empty:
        return None

    # Find first wick beyond either bound
    breached_low = win[win["Low"] < asia_l]
    breached_high = win[win["High"] > asia_h]
    if breached_low.empty and breached_high.empty:
        return None
    if breached_low.empty:
        first_high_time = breached_high.index[0]
        after = win[win.index > first_high_time]
        if not after.empty and after["Close"].iloc[-1] < asia_h:
            return "bearish_judas"
        return None
    if breached_high.empty:
        first_low_time = breached_low.index[0]
        after = win[win.index > first_low_time]
        if not after.empty and after["Close"].iloc[-1] > asia_l:
            return "bullish_judas"
        return None
    # Both breached — pick whichever happened first
    if breached_low.index[0] < breached_high.index[0]:
        after = win[win.index > breached_low.index[0]]
        if not after.empty and after["Close"].iloc[-1] > asia_l:
            return "bullish_judas"
    else:
        after = win[win.index > breached_high.index[0]]
        if not after.empty and after["Close"].iloc[-1] < asia_h:
            return "bearish_judas"
    return None
