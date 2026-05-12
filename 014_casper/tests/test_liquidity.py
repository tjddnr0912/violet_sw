"""Tests for src.core.liquidity (sweep + CHoCH)."""

import pandas as pd
import pytest

from src.core.swing import SwingPoint, find_swing_highs, find_swing_lows
from src.core.liquidity import (
    is_sweep_bar, detect_recent_sweep, detect_choch, sweep_then_choch,
    SweepEvent,
)


def _bar(o, h, l, c):
    return pd.Series({"Open": o, "High": h, "Low": l, "Close": c})


def _df(rows):
    """rows: list of (O, H, L, C). Index = 5min ascending."""
    idx = pd.date_range("2026-05-12 09:30", periods=len(rows), freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        rows, columns=["Open", "High", "Low", "Close"], index=idx,
    )


# ───────────── is_sweep_bar ─────────────
def test_sweep_up_wick_breach_close_back_inside():
    # level 100. High 100.15 (0.15% breach), Close 99.50 (back inside),
    # pin bar: wick = 100.15 - max(99.6, 99.50) = 0.55, total = 100.15 - 99.40 = 0.75
    # wick_ratio = 0.55 / 0.75 ≈ 73%
    bar = _bar(o=99.6, h=100.15, l=99.40, c=99.50)
    assert is_sweep_bar(bar, level=100.0, side="up",
                       min_breach_pct=0.0005, min_wick_ratio=0.60) is True


def test_sweep_up_close_above_level_rejected():
    # Close 100.10 — close is OUTSIDE level → not a sweep (continuation)
    bar = _bar(o=99.6, h=100.15, l=99.40, c=100.10)
    assert is_sweep_bar(bar, level=100.0, side="up") is False


def test_sweep_up_breach_too_small_rejected():
    # High only 100.02 — breach 0.02% < 0.05% threshold
    bar = _bar(o=99.6, h=100.02, l=99.40, c=99.50)
    assert is_sweep_bar(bar, level=100.0, side="up",
                       min_breach_pct=0.0005) is False


def test_sweep_up_no_pin_bar_rejected():
    # High 100.15 OK, Close 99.50 OK, but small wick (wick = 100.15-99.6 = 0.55, total = 0.75, ratio 73% — passes)
    # Try a fat-body bar that fails wick ratio
    # Open 99.6, Close 100 — wait close must be < level=100 → use 99.95
    # body = 99.95 - 99.6 = 0.35, range 0.55, wick = 100.15 - 99.95 = 0.20
    # wick_ratio = 0.20 / 0.55 ≈ 36% → fails 60% threshold
    bar = _bar(o=99.6, h=100.15, l=99.60, c=99.95)
    assert is_sweep_bar(bar, level=100.0, side="up",
                       min_wick_ratio=0.60) is False


def test_sweep_down_wick_breach_close_back_above():
    # level 99. Low 98.85 (0.15% breach below), Close 99.50, pin bar
    bar = _bar(o=99.5, h=99.55, l=98.85, c=99.50)
    # wick = min(99.5, 99.50) - 98.85 = 0.65, total = 99.55 - 98.85 = 0.70
    # wick_ratio ≈ 93%
    assert is_sweep_bar(bar, level=99.0, side="down",
                       min_breach_pct=0.0005, min_wick_ratio=0.60) is True


def test_sweep_zero_range_rejected():
    bar = _bar(o=100, h=100, l=100, c=100)
    assert is_sweep_bar(bar, level=100.0, side="up") is False


def test_sweep_invalid_level_rejected():
    bar = _bar(o=99.6, h=100.15, l=99.40, c=99.50)
    assert is_sweep_bar(bar, level=0.0, side="up") is False


# ───────────── detect_recent_sweep ─────────────
def test_detect_recent_sweep_finds_one_in_lookback():
    rows = [
        (99.5, 99.7, 99.3, 99.5),     # normal
        (99.5, 99.7, 99.3, 99.5),     # normal
        (99.5, 100.15, 99.4, 99.5),   # SWEEP @ level 100
        (99.5, 99.7, 99.3, 99.5),     # post-sweep
    ]
    df = _df(rows)
    ev = detect_recent_sweep(df, levels=[100.0], side="up",
                             lookback=6, min_breach_pct=0.0005,
                             min_wick_ratio=0.50)
    assert ev is not None
    assert ev.level == 100.0
    assert ev.side == "up"


def test_detect_recent_sweep_returns_none_when_no_sweep():
    rows = [
        (99.5, 99.7, 99.3, 99.5),
        (99.5, 99.7, 99.3, 99.5),
    ]
    df = _df(rows)
    ev = detect_recent_sweep(df, levels=[100.0], side="up")
    assert ev is None


def test_detect_recent_sweep_respects_lookback():
    # SWEEP is way back, beyond lookback
    rows = [(99.5, 100.15, 99.4, 99.5)] + [(99.5, 99.7, 99.3, 99.5)] * 8
    df = _df(rows)
    ev = detect_recent_sweep(df, levels=[100.0], side="up", lookback=5,
                             min_wick_ratio=0.50)
    assert ev is None


# ───────────── detect_choch ─────────────
def test_detect_choch_bull_first_close_above_swing_high():
    # Synthetic: swing high at index 2 = 13.0
    # bar 0,1,2,3,4 set up swing
    # bar 5,6 stay below 13
    # bar 7 closes at 13.5 → CHoCH
    rows = [
        (10, 10.5, 9.5, 10.2),   # 0
        (10.2, 11.0, 10.0, 11.0),# 1
        (11.0, 13.0, 10.8, 12.5),# 2  ← swing high candidate
        (12.5, 12.8, 11.5, 12.0),# 3
        (12.0, 12.5, 11.0, 11.5),# 4
        (11.5, 11.8, 11.0, 11.3),# 5
        (11.3, 11.6, 11.0, 11.5),# 6
        (11.5, 13.8, 11.4, 13.5),# 7 ← CHoCH close > 13
    ]
    df = _df(rows)
    sh = find_swing_highs(df.iloc[:7], left=2, right=2)  # only past bars
    assert len(sh) >= 1
    ts = detect_choch(df.iloc[7:8], swing_highs=sh, swing_lows=[],
                      direction="bull", after_ts=df.index[6])
    assert ts == df.index[7]


def test_detect_choch_bull_no_break_returns_none():
    rows = [
        (10, 10.5, 9.5, 10.2),
        (10.2, 11.0, 10.0, 11.0),
        (11.0, 13.0, 10.8, 12.5),
        (12.5, 12.8, 11.5, 12.0),
        (12.0, 12.5, 11.0, 11.5),
        (11.5, 11.8, 11.0, 11.3),  # never breaks 13
    ]
    df = _df(rows)
    sh = find_swing_highs(df.iloc[:5], left=2, right=2)
    ts = detect_choch(df.iloc[5:], swing_highs=sh, swing_lows=[],
                      direction="bull")
    assert ts is None


def test_detect_choch_bear_close_below_swing_low():
    rows = [
        (15, 15.2, 14.5, 14.8),   # 0
        (14.8, 14.9, 13.5, 13.8), # 1
        (13.8, 14.0, 11.0, 11.5), # 2  ← swing low 11.0
        (11.5, 12.5, 11.3, 12.3), # 3
        (12.3, 13.0, 11.8, 12.8), # 4
        (12.8, 13.0, 12.5, 12.8), # 5
        (12.8, 13.0, 10.5, 10.7), # 6 ← close < 11.0 → CHoCH (bear)
    ]
    df = _df(rows)
    sl = find_swing_lows(df.iloc[:5], left=2, right=2)
    assert len(sl) >= 1
    ts = detect_choch(df.iloc[6:7], swing_highs=[], swing_lows=sl,
                      direction="bear", after_ts=df.index[5])
    assert ts == df.index[6]


# ───────────── sweep_then_choch ─────────────
def test_sweep_then_choch_bull_composite():
    # Setup: build a synthetic sequence where:
    # - early bars create a swing high (we'll use a fixed level)
    # - SSL sweep occurs (price wicks below 99 then closes back above)
    # - subsequent bar closes above the swing high → CHoCH
    rows = [
        (100, 101, 99.8, 100.5),     # 0
        (100.5, 101.2, 99.9, 100.0), # 1
        (100.0, 102.0, 99.8, 101.5), # 2 ← swing high candidate (102.0)
        (101.5, 101.6, 100.0, 100.2),# 3
        (100.2, 100.4, 99.5, 99.8),  # 4
        (99.8, 99.9, 98.80, 99.50),  # 5 ← SSL sweep @ level 99 (low 98.80, close 99.50)
        (99.50, 102.5, 99.40, 102.3),# 6 ← CHoCH (close > 102.0)
    ]
    df = _df(rows)
    sh = find_swing_highs(df.iloc[:5], left=2, right=2)
    sl = find_swing_lows(df.iloc[:5], left=2, right=2)
    triggered = sweep_then_choch(
        df, levels_up=[], levels_down=[99.0],
        swing_highs=sh, swing_lows=sl,
        direction="bull", sweep_lookback=6, choch_lookback=4,
        min_breach_pct=0.0005, min_wick_ratio=0.50,
    )
    assert triggered is True


def test_sweep_then_choch_returns_false_when_no_sweep():
    rows = [(100, 101, 99.8, 100.5)] * 5
    df = _df(rows)
    triggered = sweep_then_choch(
        df, levels_up=[], levels_down=[99.0],
        swing_highs=[], swing_lows=[],
        direction="bull",
    )
    assert triggered is False
