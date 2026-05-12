"""Tests for src.core.swing."""

import pandas as pd
import pytest

from src.core.swing import (
    find_swing_highs, find_swing_lows, equal_levels,
    last_swing_before, SwingPoint,
)


def _bars(highs, lows, opens=None, closes=None):
    n = len(highs)
    idx = pd.date_range("2026-05-12 09:30", periods=n, freq="5min", tz="US/Eastern")
    df = pd.DataFrame({
        "Open":  opens if opens is not None else [(h + l) / 2 for h, l in zip(highs, lows)],
        "High":  highs,
        "Low":   lows,
        "Close": closes if closes is not None else [(h + l) / 2 for h, l in zip(highs, lows)],
    }, index=idx)
    return df


# ───────────── find_swing_highs ─────────────
def test_swing_high_simple_5bar_fractal():
    # bar 2 has the highest high in a 5-bar window
    bars = _bars(highs=[10, 11, 13, 11, 10], lows=[9, 9.5, 12, 9.5, 9])
    sh = find_swing_highs(bars, left=2, right=2)
    assert len(sh) == 1
    assert sh[0].price == 13


def test_swing_high_excludes_edges():
    # Bar 3 (price 14) is the only swing high. Bars 0/6 (edges) are not
    # considered (no room for left/right neighbors).
    bars = _bars(
        highs=[15, 11, 12, 14, 12, 11, 15],
        lows=[9, 9, 9, 9, 9, 9, 9],
    )
    sh = find_swing_highs(bars, left=2, right=2)
    assert len(sh) == 1
    assert sh[0].price == 14


def test_swing_high_returns_empty_when_not_enough_bars():
    bars = _bars(highs=[10, 11, 12], lows=[9, 9, 9])
    sh = find_swing_highs(bars, left=2, right=2)
    assert sh == []


def test_swing_high_left_strict_right_nonstrict():
    # Plateau handling: center == right neighbors but center > left neighbors
    bars = _bars(highs=[10, 11, 13, 13, 12, 11, 10],
                 lows=[9, 9, 9, 9, 9, 9, 9])
    sh = find_swing_highs(bars, left=2, right=2)
    # Position 2 (price 13): left [10,11] both <13 ✓, right [13,12] non-strict ≤13 ✓
    # Position 3 (price 13): left [11,13] not all strictly < → fails
    assert len(sh) == 1
    assert sh[0].price == 13


# ───────────── find_swing_lows ─────────────
def test_swing_low_simple_5bar():
    bars = _bars(highs=[12, 11, 10, 11, 12], lows=[11, 10, 8, 10, 11])
    sl = find_swing_lows(bars, left=2, right=2)
    assert len(sl) == 1
    assert sl[0].price == 8


def test_swing_low_returns_empty_when_no_pivot():
    # monotonically increasing
    bars = _bars(highs=[10, 11, 12, 13, 14], lows=[9, 10, 11, 12, 13])
    sl = find_swing_lows(bars, left=2, right=2)
    # Position 2 has Low 11 — but bars 0/1 have 9/10 (lower) → fails left rule
    assert sl == []


# ───────────── equal_levels ─────────────
def test_equal_levels_finds_eqh():
    # Two swing highs at 13 and 13.001 → within 0.05%
    bars = _bars(
        highs=[10, 11, 13, 11, 10, 11, 13.001, 11, 10],
        lows=[9, 9, 12, 9, 9, 9, 12, 9, 9],
    )
    sh = find_swing_highs(bars, left=2, right=2)
    assert len(sh) == 2
    pairs = equal_levels(sh, eq_pct=0.001)  # 0.1%
    assert len(pairs) == 1
    a, b = pairs[0]
    assert a.price == 13


def test_equal_levels_excludes_far_apart():
    bars = _bars(
        highs=[10, 11, 13.0, 11, 10, 11, 14.0, 11, 10],
        lows=[9, 9, 12, 9, 9, 9, 12, 9, 9],
    )
    sh = find_swing_highs(bars, left=2, right=2)
    assert len(sh) == 2
    pairs = equal_levels(sh, eq_pct=0.005)  # 0.5%
    assert pairs == []  # 13 vs 14 = 7.7%


# ───────────── last_swing_before ─────────────
def test_last_swing_before_returns_most_recent():
    bars = _bars(
        highs=[10, 11, 13, 11, 10, 11, 14, 11, 10],
        lows=[9, 9, 9, 9, 9, 9, 9, 9, 9],
    )
    sh = find_swing_highs(bars, left=2, right=2)
    assert len(sh) == 2
    # ts of the 2nd swing high
    last = last_swing_before(sh, sh[1].timestamp)
    assert last == sh[0]


def test_last_swing_before_returns_none_if_before_all():
    bars = _bars(highs=[10, 11, 13, 11, 10], lows=[9, 9, 9, 9, 9])
    sh = find_swing_highs(bars, left=2, right=2)
    assert len(sh) == 1
    earliest = sh[0].timestamp - pd.Timedelta(minutes=10)
    assert last_swing_before(sh, earliest) is None
