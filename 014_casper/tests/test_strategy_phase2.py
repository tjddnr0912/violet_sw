"""Tests for ICT Phase-2 sweep+CHoCH gate in scan_for_signal."""

import pandas as pd
import pytest

from src.core.orb import OpeningRange
from src.core.strategy import scan_for_signal


def _make_breakout_only_session():
    """Synthetic ORB+FVG breakout WITHOUT any prior sweep or CHoCH.

    A simple bullish breakout above orb_high=100 with FVG intersecting
    the ORB line. Bars do not include any pin-bar sweeps below ORB low.
    """
    rows = []
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    # Pre-breakout: stable below ORB high
    for k in range(4):
        ts = start + pd.Timedelta(minutes=5 * k)
        rows.append({"time": ts, "Open": 99.5, "High": 99.8,
                     "Low": 99.3, "Close": 99.6, "Volume": 1000})
    # c1
    c1 = start + pd.Timedelta(minutes=5 * 4)
    rows.append({"time": c1, "Open": 99.7, "High": 99.9, "Low": 99.5, "Close": 99.8, "Volume": 1000})
    # c2 breakout
    c2 = c1 + pd.Timedelta(minutes=5)
    rows.append({"time": c2, "Open": 99.9, "High": 101.0, "Low": 99.85, "Close": 100.9, "Volume": 2500})
    # c3
    c3 = c2 + pd.Timedelta(minutes=5)
    rows.append({"time": c3, "Open": 100.5, "High": 101.2, "Low": 100.0, "Close": 101.0, "Volume": 1500})
    # pullback bars
    for k in range(3):
        ts = c3 + pd.Timedelta(minutes=5 * (k + 1))
        rows.append({"time": ts, "Open": 100.8, "High": 101.0, "Low": 99.85, "Close": 100.5, "Volume": 1000})
    return pd.DataFrame(rows).set_index("time")


def _make_sweep_then_breakout_session():
    """Session with: bullish swing high → SSL sweep below ORB low → CHoCH
    above swing high → breakout + FVG.

    Used to verify Phase-2 sweep+CHoCH gate fires.
    """
    rows = []
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")

    # ── early stretch: builds a "prior swing high" around 100.6 ──
    pattern = [
        (99.5, 99.7, 99.3, 99.4),     # 09:45  bar 0
        (99.4, 99.6, 99.2, 99.3),     # 09:50  bar 1
        (99.3, 100.6, 99.2, 100.4),   # 09:55  bar 2  ← swing high candidate (high=100.6)
        (100.4, 100.5, 99.8, 99.9),   # 10:00  bar 3
        (99.9, 100.0, 99.5, 99.6),    # 10:05  bar 4
        # SSL sweep below ORB low (orb_low=99.0): pin bar
        (99.6, 99.7, 98.80, 99.50),   # 10:10  bar 5  ← sweep (low 98.80 below 99 level, close 99.5)
        # CHoCH bar — closes above prior swing high 100.6
        (99.50, 101.8, 99.40, 101.5), # 10:15  bar 6  ← CHoCH (close > 100.6)
        # Continuation: another bullish bar straddles ORB line creating FVG
        (101.5, 101.6, 99.95, 100.5), # 10:20  bar 7  -- c1 (low above orb high? need 99 instead)
    ]
    # Construct timestamps
    for i, (o, h, l, c) in enumerate(pattern):
        ts = start + pd.Timedelta(minutes=5 * i)
        rows.append({"time": ts, "Open": o, "High": h, "Low": l, "Close": c, "Volume": 1000})

    # Add a clean ORB+FVG strict pattern AFTER the sweep+CHoCH happened.
    next_start = start + pd.Timedelta(minutes=5 * len(pattern))
    # c1 below ORB high
    rows.append({"time": next_start, "Open": 99.7, "High": 99.9, "Low": 99.5, "Close": 99.8, "Volume": 1000})
    # c2 displacement straddling ORB
    rows.append({"time": next_start + pd.Timedelta(minutes=5),
                 "Open": 99.9, "High": 101.0, "Low": 99.85, "Close": 100.9, "Volume": 2500})
    # c3 leaves FVG
    rows.append({"time": next_start + pd.Timedelta(minutes=10),
                 "Open": 100.5, "High": 101.2, "Low": 100.0, "Close": 101.0, "Volume": 1500})
    # pullback bars
    for k in range(3):
        rows.append({"time": next_start + pd.Timedelta(minutes=15 + 5 * k),
                     "Open": 100.8, "High": 101.0, "Low": 99.85, "Close": 100.5, "Volume": 1000})

    return pd.DataFrame(rows).set_index("time")


def _orb():
    return OpeningRange(high=100.0, low=99.0, range_size=1.0, date="2026-05-12")


def test_phase2_gate_disabled_acts_as_phase1():
    bars = _make_breakout_only_session()
    sig = scan_for_signal(bars, _orb(), "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True, require_sweep_choch=False)
    assert sig is not None


def test_phase2_gate_rejects_breakout_without_prior_sweep():
    bars = _make_breakout_only_session()
    sig = scan_for_signal(bars, _orb(), "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True, require_sweep_choch=True,
                          sweep_lookback=12, choch_lookback=12,
                          sweep_min_wick_ratio=0.50)
    assert sig is None


def test_phase2_gate_allows_when_sweep_choch_precede_breakout():
    bars = _make_sweep_then_breakout_session()
    sig = scan_for_signal(
        bars, _orb(), "TQQQ", rr_ratio=2.0, min_risk=0.05,
        strict=True, require_sweep_choch=True,
        sweep_lookback=12, choch_lookback=12,
        sweep_min_breach_pct=0.0005, sweep_min_wick_ratio=0.50,
    )
    assert sig is not None
