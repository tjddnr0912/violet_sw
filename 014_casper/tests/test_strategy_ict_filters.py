"""Tests for ICT Phase-1 filters added to scan_for_signal."""

import pandas as pd
import pytest

from src.core.orb import OpeningRange
from src.core.strategy import scan_for_signal


def _bar(t, o, h, l, c, v=1000):
    return {"time": t, "Open": o, "High": h, "Low": l, "Close": c, "Volume": v}


def _make_post_orb_with_breakout(breakout_minute: int, orb_high: float = 100.0):
    """Build a synthetic post-ORB DataFrame with a clean strict-FVG breakout.

    The breakout bar straddles ORB line (open<=orb_high<=close) and a
    bullish FVG forms across bars [i-1, i, i+1].

    breakout_minute: how many minutes after 09:30 the breakout candle is.
    """
    rows = []
    # 09:45 ~ 10:55 is the scan window. We need at least 4 bars.
    # We'll start at 09:45 and step 5min.
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    # Pre-breakout bars (small, near orb_high but below)
    for k in range(4):
        ts = start + pd.Timedelta(minutes=5 * k)
        rows.append({"time": ts, "Open": 99.5, "High": 99.8, "Low": 99.3, "Close": 99.6, "Volume": 1000})

    # i = idx of the breakout bar — we want it at start + breakout_minute - 15
    # Place breakout at position 4 (= 09:45 + 20min = 10:05)
    # but we honor breakout_minute by adjusting start of `rows`
    # For simplicity we just append in order:
    # bar i-1 (c1): high < orb_high → leaves a bullish FVG
    c1_ts = start + pd.Timedelta(minutes=5 * 4)
    rows.append({"time": c1_ts, "Open": 99.7, "High": 99.9, "Low": 99.5, "Close": 99.8, "Volume": 1000})

    # bar i (c2 = displacement / breakout)
    # body 1.0, wick small (Open 99.9, High 101.0, Low 99.85, Close 100.9)
    c2_ts = c1_ts + pd.Timedelta(minutes=5)
    # Override c2 timestamp to match breakout_minute (HH:MM ET)
    # breakout_minute: number of minutes past 09:30. e.g. 35 → 10:05
    abs_ts = pd.Timestamp("2026-05-12") + pd.Timedelta(hours=9, minutes=30 + breakout_minute)
    abs_ts = abs_ts.tz_localize("US/Eastern")
    c2_ts = abs_ts

    rows.append({"time": c2_ts, "Open": 99.9, "High": 101.0, "Low": 99.85, "Close": 100.9, "Volume": 2500})

    # bar i+1 (c3): Low > c1.High → strict bullish FVG. Low at 100.0, High 101.2
    c3_ts = c2_ts + pd.Timedelta(minutes=5)
    rows.append({"time": c3_ts, "Open": 100.5, "High": 101.2, "Low": 100.0, "Close": 101.0, "Volume": 1500})

    # follow-up bars for pullback into FVG
    for k in range(3):
        ts = c3_ts + pd.Timedelta(minutes=5 * (k + 1))
        # one bar dips into FVG to provide pullback
        rows.append({"time": ts, "Open": 100.8, "High": 101.0, "Low": 99.85, "Close": 100.5, "Volume": 1000})

    df = pd.DataFrame(rows).set_index("time")
    return df


def _orb():
    return OpeningRange(high=100.0, low=99.0, range_size=1.0, date="2026-05-12")


# ───── Killzone filter ─────
def test_killzone_filter_allows_am_macro_breakout():
    # breakout at 09:55 → AM_MACRO
    bars = _make_post_orb_with_breakout(breakout_minute=25)  # 09:55
    orb = _orb()
    sig = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True, allowed_killzones=["AM_MACRO"])
    assert sig is not None


def test_killzone_filter_rejects_late_breakout():
    # breakout at 10:30 → AM_LATE — should be rejected
    bars = _make_post_orb_with_breakout(breakout_minute=60)  # 10:30
    orb = _orb()
    sig = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True, allowed_killzones=["AM_MACRO"])
    assert sig is None


def test_killzone_filter_disabled_passes_all_times():
    bars = _make_post_orb_with_breakout(breakout_minute=60)  # 10:30
    orb = _orb()
    sig = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True, allowed_killzones=None)
    assert sig is not None


# ───── Displacement filter ─────
def test_displacement_filter_passes_strong_breakout():
    # Synthetic builder makes a body ~1.0, wick small breakout — passes
    bars = _make_post_orb_with_breakout(breakout_minute=25)
    orb = _orb()
    sig = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True, require_displacement=True,
                          disp_atr_mult=0.5,  # ATR may be small in synth data
                          disp_max_wick=0.50,
                          disp_prev_mult=2.0)
    assert sig is not None


def test_displacement_filter_rejects_weak_candle():
    # Use unrealistically high disp_prev_mult so the body-vs-prev-bars
    # relative check rejects the synthetic breakout. (ATR check would be
    # skipped here because the synthetic series is <15 bars long.)
    bars = _make_post_orb_with_breakout(breakout_minute=25)
    orb = _orb()
    sig = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True, require_displacement=True,
                          disp_prev_mult=20.0,  # body must be ≥20× prev mean
                          disp_max_wick=0.50)
    assert sig is None


def test_no_filters_passes_breakout():
    bars = _make_post_orb_with_breakout(breakout_minute=25)
    orb = _orb()
    sig = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True)
    assert sig is not None


# ───── Combined ─────
def test_combined_killzone_and_displacement_passes():
    bars = _make_post_orb_with_breakout(breakout_minute=30)  # 10:00 AM_MACRO
    orb = _orb()
    sig = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True,
                          allowed_killzones=["AM_MACRO"],
                          require_displacement=True,
                          disp_atr_mult=0.5,
                          disp_max_wick=0.50,
                          disp_prev_mult=2.0)
    assert sig is not None


def test_combined_filters_either_rejects_means_no_signal():
    # breakout 10:30 — fails killzone first
    bars = _make_post_orb_with_breakout(breakout_minute=60)
    orb = _orb()
    sig = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True,
                          allowed_killzones=["AM_MACRO"],
                          require_displacement=True,
                          disp_atr_mult=0.5)
    assert sig is None
