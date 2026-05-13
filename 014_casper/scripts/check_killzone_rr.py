#!/usr/bin/env python3
"""Smoke-check Scenario B: per-killzone RR resolution in scan_for_signal.

Usage:
    python scripts/check_killzone_rr.py macro     # asserts rr=3.0
    python scripts/check_killzone_rr.py late      # asserts rr=2.0
    python scripts/check_killzone_rr.py fallback  # rr_by_killzone=None → default 3.0

This is intentionally minimal — it constructs synthetic 5-min bars with a
clear bullish breakout candle whose timestamp lands in the requested
killzone, runs scan_for_signal, and verifies the emitted signal's
rr_ratio matches the Scenario B expectation. No KIS calls.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, time as dtime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytz

from src.core.orb import OpeningRange
from src.core.strategy import scan_for_signal


ET = pytz.timezone("US/Eastern")


def build_bars(breakout_hh: int, breakout_mm: int) -> pd.DataFrame:
    """Construct deterministic 5-min OHLCV with a strict-breakout candle
    + FVG geometry that scan_for_signal will accept.

    Layout (all bars at 5-min increments):
      i-1: low=99, high=100, close=99.5 (will be 'prev')
      i  : open=99.8, close=101.5 (strict breakout above ORB high 100)
      i+1: low=100.5, high=101.0  (creates bull FVG: c1.High 100 < c3.Low 100.5)
      pullback bars: gradually retrace into FVG zone
    """
    # All bars at ET-aware index
    today = datetime.now(ET).date()

    def at(h, m):
        return ET.localize(datetime.combine(today, dtime(h, m)))

    # Place i (breakout) at breakout_hh:breakout_mm
    rows = []
    # Bars before breakout in scan window (need ≥ 4 bars total)
    # First two pre-breakout bars
    rows.append((at(9, 45), 99.0, 99.5, 98.5, 99.2, 1000))
    rows.append((at(9, 50), 99.2, 99.6, 98.8, 99.3, 1000))
    # prev candle (i-1) just before breakout
    prev_t = at(breakout_hh, breakout_mm - 5) if breakout_mm >= 5 else at(breakout_hh - 1, 55)
    rows.append((prev_t, 99.5, 100.0, 99.0, 99.5, 1500))
    # breakout candle (i): close > ORB high 100
    rows.append((at(breakout_hh, breakout_mm), 99.8, 101.5, 99.8, 101.5, 2500))
    # next candle (i+1): creates Bull FVG since prev.High=100 < next.Low=100.5
    next_t = at(breakout_hh, breakout_mm + 5) if breakout_mm <= 50 else at(breakout_hh + 1, 0)
    rows.append((next_t, 101.0, 101.2, 100.5, 100.8, 1800))
    # pullback bar: low touches FVG midpoint ~100.25 to trigger entry
    pull_t = at(breakout_hh, breakout_mm + 10) if breakout_mm <= 45 else at(breakout_hh + 1, 5)
    rows.append((pull_t, 100.7, 100.9, 100.10, 100.40, 1600))

    df = pd.DataFrame(rows, columns=["ts", "Open", "High", "Low", "Close", "Volume"])
    df = df.set_index("ts").sort_index()
    return df


def run(scenario: str) -> int:
    if scenario == "macro":
        bars = build_bars(9, 55)  # breakout in AM_MACRO
        expected_rr = 3.0
        rr_by_kz = {"AM_MACRO": 3.0, "AM_LATE": 2.0}
    elif scenario == "late":
        bars = build_bars(10, 25)  # breakout in AM_LATE
        expected_rr = 2.0
        rr_by_kz = {"AM_MACRO": 3.0, "AM_LATE": 2.0}
    elif scenario == "fallback":
        bars = build_bars(9, 55)
        expected_rr = 3.0
        rr_by_kz = None
    else:
        print(f"unknown scenario: {scenario}", file=sys.stderr)
        return 2

    orb = OpeningRange(
        date=bars.index[0].date(),
        high=100.0, low=99.0, range_size=1.0,
    )

    sig = scan_for_signal(
        bars, orb, symbol="TQQQ",
        rr_ratio=3.0,
        min_risk=0.10,
        strict=False,  # relax — the synthetic body straddles 100 anyway
        allowed_killzones=["AM_MACRO", "AM_LATE"],
        rr_by_killzone=rr_by_kz,
    )

    if sig is None:
        print(f"[{scenario}] FAIL — scan returned None", file=sys.stderr)
        return 1

    actual = float(sig.rr_ratio)
    print(f"[{scenario}] rr={actual} (expected {expected_rr}, "
          f"entry=${sig.entry_price:.2f} stop=${sig.stop_loss:.2f} tp=${sig.take_profit:.2f})")
    if abs(actual - expected_rr) > 1e-6:
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: check_killzone_rr.py [macro|late|fallback]", file=sys.stderr)
        sys.exit(2)
    sys.exit(run(sys.argv[1]))
