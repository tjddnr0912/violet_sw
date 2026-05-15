"""Antonacci Global Equities Momentum (GEM) — monthly dual-momentum signal.

Algorithm (book-exact, Antonacci 2014):
  At the close of the last NYSE trading day of every month:
    us_ret   = 12-month total return of SPY
    exus_ret = 12-month total return of VEU
    bill_ret = 12-month total return of BIL  (T-bill proxy)

    if max(us_ret, exus_ret) > bill_ret:
        target = "SPY" if us_ret > exus_ret else "VEU"
    else:
        target = "AGG"   # US aggregate bond fallback

Execution (this module):
  • Signal is *computed* on the last trading day's close (or on a grace
    day up to N trading days later if the bot was offline).
  • Execution is the *next* trading day's open — i.e. KIS market order
    at the start of the new month.
  • State (last signal date + currently-held asset) lives in
    `data/gem_state.json` so the scheduler can de-duplicate within
    the grace window and survive crashes.

This module is pure logic; it does NOT call KIS. The bot wires the
output of `compute_gem_signal()` into kis_order in P2.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from src.utils import time_utils

logger = logging.getLogger("casper")

# Default GEM universe — Antonacci's book exact tickers.
# VEU has long history (2007-), VXUS would work but trims to 2011-.
GEM_UNIVERSE = {
    "us":   "SPY",
    "exus": "VEU",
    "bond": "AGG",
    "bill": "BIL",
}

# Trading days per 12 months — used as the lookback offset.
TRADING_DAYS_12M = 252

# Grace window: if today is up to N trading days *after* the last trading
# day of the month, treat as a missed-rebalance situation and execute the
# signal anyway. 3 covers a long-weekend bot outage; the 4th day would
# already collide with the *next* month's signal so we stop.
GRACE_TRADING_DAYS = 3

GEM_STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "gem_state.json"
)


@dataclass
class GemSignal:
    """Result of a single GEM signal computation."""
    signal_date: str        # last trading day of month, ISO format
    target: str             # "SPY" | "VEU" | "AGG"
    us_ret: float           # SPY 12-month return
    exus_ret: float         # VEU 12-month return
    bill_ret: float         # BIL 12-month return
    reason: str             # human-readable explanation
    universe: dict          # snapshot of tickers used (audit trail)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GemState:
    """Persisted state across bot restarts.

    Two keys protect against double-execution and missed-rebalances:
      * last_signal_date — the signal_date the bot *executed* on (not
        merely computed). De-duplicates inside the grace window.
      * current_holding  — what the bot believes is held in the GEM
        bucket. Reconciled against KIS balance on each tick.
    """
    last_signal_date: Optional[str] = None
    last_target: Optional[str] = None
    current_holding: Optional[str] = None

    @classmethod
    def load(cls, path: str = GEM_STATE_FILE) -> "GemState":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return cls(
                last_signal_date=data.get("last_signal_date"),
                last_target=data.get("last_target"),
                current_holding=data.get("current_holding"),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"GEM state load failed ({e}) — starting fresh")
            return cls()

    def save(self, path: str = GEM_STATE_FILE) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)


# ─────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────


def _fetch_12m_returns(tickers: list[str], today: Optional[date] = None) -> dict[str, float]:
    """12-month total return for each ticker, via yfinance auto-adjust.

    Returns dict[ticker -> return_pct]. Missing tickers map to NaN.
    Total-return columns (auto_adjust=True) include reinvested dividends
    — required for VEU/AGG to be comparable to SPY.
    """
    if today is None:
        today = time_utils.today_et()
    # Fetch 420 calendar days back; covers 12 months + holidays + buffer.
    start = today - timedelta(days=420)
    try:
        df = yf.download(
            tickers,
            start=start.isoformat(),
            end=(today + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    except Exception as e:
        logger.error(f"GEM: yfinance download failed: {e}")
        return {t: float("nan") for t in tickers}

    # yfinance can return either a flat or MultiIndex df depending on
    # whether we passed 1 or many tickers; normalize to a Close-only frame.
    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0):
            close = df["Close"]
        else:
            logger.error("GEM: 'Close' column missing from yfinance response")
            return {t: float("nan") for t in tickers}
    else:
        close = df[["Close"]].rename(columns={"Close": tickers[0]})

    out: dict[str, float] = {}
    for t in tickers:
        if t not in close.columns:
            logger.warning(f"GEM: ticker {t} missing from yfinance response")
            out[t] = float("nan")
            continue
        series = close[t].dropna()
        if len(series) < TRADING_DAYS_12M + 1:
            logger.warning(
                f"GEM: {t} has only {len(series)} bars — short of 12M lookback"
            )
            # Use whatever we have — degraded but not broken.
            if len(series) < 30:
                out[t] = float("nan")
                continue
            ret = series.iloc[-1] / series.iloc[0] - 1
        else:
            ret = series.iloc[-1] / series.iloc[-TRADING_DAYS_12M - 1] - 1
        out[t] = float(ret)
    return out


def compute_gem_signal(today: Optional[date] = None,
                       universe: Optional[dict] = None) -> GemSignal:
    """Compute the GEM signal as if today's close were the signal date.

    Does NOT consult state file — that's the scheduler's job. Always
    returns *some* signal; if data is missing for SPY/VEU/BIL, biases
    toward AGG (safest fallback).
    """
    if today is None:
        today = time_utils.today_et()
    if universe is None:
        universe = GEM_UNIVERSE

    tickers = [universe["us"], universe["exus"], universe["bond"], universe["bill"]]
    rets = _fetch_12m_returns(tickers, today=today)
    us, exus, bill = rets[universe["us"]], rets[universe["exus"]], rets[universe["bill"]]

    # Defensive: if any of the three comparators is NaN, fall back to AGG.
    if any(pd.isna(x) for x in (us, exus, bill)):
        return GemSignal(
            signal_date=today.isoformat(),
            target=universe["bond"],
            us_ret=us if not pd.isna(us) else 0.0,
            exus_ret=exus if not pd.isna(exus) else 0.0,
            bill_ret=bill if not pd.isna(bill) else 0.0,
            reason="data_missing → fallback to bond",
            universe=universe,
        )

    if max(us, exus) > bill:
        if us > exus:
            target = universe["us"]
            reason = (
                f"US ({us*100:+.2f}%) > ExUS ({exus*100:+.2f}%) "
                f"and > BILL ({bill*100:+.2f}%)"
            )
        else:
            target = universe["exus"]
            reason = (
                f"ExUS ({exus*100:+.2f}%) > US ({us*100:+.2f}%) "
                f"and > BILL ({bill*100:+.2f}%)"
            )
    else:
        target = universe["bond"]
        reason = (
            f"Both US ({us*100:+.2f}%) and ExUS ({exus*100:+.2f}%) "
            f"≤ BILL ({bill*100:+.2f}%) → bond"
        )

    return GemSignal(
        signal_date=today.isoformat(),
        target=target,
        us_ret=us,
        exus_ret=exus,
        bill_ret=bill,
        reason=reason,
        universe=universe,
    )


# ─────────────────────────────────────────────────────────────────────
# Scheduler
# ─────────────────────────────────────────────────────────────────────


def should_run_gem(today: Optional[date] = None,
                   state: Optional[GemState] = None) -> tuple[bool, Optional[date]]:
    """Decide if GEM signal must be (re)evaluated today.

    Returns (run_now: bool, signal_date: Optional[date]).

    Rules:
      1. If today is the last trading day of the month → run with
         signal_date=today.  (Antonacci standard.)
      2. Else, if any of the last GRACE_TRADING_DAYS trading days WAS
         a last-trading-day-of-month AND we haven't yet executed for
         that date → run with that earlier date as signal_date.
      3. Else → no-op.

    The grace branch (#2) is what makes the bot resilient to crashes,
    network outages, public holidays, and starting up mid-month.
    """
    if today is None:
        today = time_utils.today_et()
    if state is None:
        state = GemState.load()

    # Case 1 — canonical: today IS the last trading day of the month.
    if time_utils.is_last_trading_day_of_month(today):
        if state.last_signal_date == today.isoformat():
            return False, None  # already done
        return True, today

    # Case 2 — late execution: look back up to GRACE_TRADING_DAYS.
    missed = time_utils.was_last_trading_day_of_month_within(
        days_back=GRACE_TRADING_DAYS, today=today
    )
    if missed is None:
        return False, None
    if state.last_signal_date == missed.isoformat():
        return False, None  # already executed for that month
    return True, missed
