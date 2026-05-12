"""Tests for Bearish FVG detection + breakdown-with-FVG."""

import pandas as pd
import pytest

from src.core.fvg import (
    detect_bearish_fvg, check_breakdown_with_fvg,
    detect_bullish_fvg,  # ensure bullish still works
)


def _three_candles(c1_low, c2, c3_high):
    """Build a 3-bar DataFrame.

    c2 = dict with O/H/L/C of the middle bar.
    """
    idx = pd.date_range("2026-05-12 10:00", periods=3, freq="5min", tz="US/Eastern")
    rows = [
        {"Open": c1_low + 0.05, "High": c1_low + 0.20, "Low": c1_low, "Close": c1_low + 0.10},
        c2,
        {"Open": c3_high - 0.10, "High": c3_high, "Low": c3_high - 0.20, "Close": c3_high - 0.15},
    ]
    return pd.DataFrame(rows, index=idx)


# ───── detect_bearish_fvg ─────
def test_bearish_fvg_detected_when_gap_present():
    # c1.Low=100, c3.High=99 → gap [99, 100]
    bars = _three_candles(
        c1_low=100.0,
        c2={"Open": 100.5, "High": 100.6, "Low": 99.5, "Close": 99.6},
        c3_high=99.0,
    )
    fvg = detect_bearish_fvg(bars)
    assert fvg is not None
    assert fvg.top == 100.0
    assert fvg.bottom == 99.0
    assert fvg.size == pytest.approx(1.0)


def test_bearish_fvg_none_when_overlap():
    # c1.Low=99.5, c3.High=100.0 → overlap (no gap)
    bars = _three_candles(
        c1_low=99.5,
        c2={"Open": 100.0, "High": 100.2, "Low": 99.0, "Close": 99.1},
        c3_high=100.0,
    )
    fvg = detect_bearish_fvg(bars)
    assert fvg is None


def test_bearish_fvg_none_when_less_than_3_bars():
    idx = pd.date_range("2026-05-12 10:00", periods=2, freq="5min", tz="US/Eastern")
    df = pd.DataFrame({"Open": [100, 99], "High": [101, 100],
                       "Low": [99, 98], "Close": [99, 99]}, index=idx)
    assert detect_bearish_fvg(df) is None


def test_bearish_does_not_affect_bullish_detection():
    # Build a clean bullish FVG and ensure bullish still detects it
    idx = pd.date_range("2026-05-12 10:00", periods=3, freq="5min", tz="US/Eastern")
    df = pd.DataFrame([
        {"Open": 99.5, "High": 100.0, "Low": 99.3, "Close": 99.8},
        {"Open": 99.8, "High": 101.0, "Low": 99.85, "Close": 100.9},
        {"Open": 100.5, "High": 101.2, "Low": 100.5, "Close": 101.0},
    ], index=idx)
    assert detect_bearish_fvg(df) is None
    assert detect_bullish_fvg(df) is not None


# ───── check_breakdown_with_fvg ─────
def _post_orb_bearish(orb_low=99.0):
    """5 bars with a clean strict bearish breakdown at index 2.

    c1 sits above orb_low. c2 (breakdown candle) straddles orb_low and
    closes below. c3 leaves a bearish FVG between c1.Low and c3.High.
    """
    idx = pd.date_range("2026-05-12 09:45", periods=5, freq="5min", tz="US/Eastern")
    rows = [
        # bar 0
        {"Open": 99.6, "High": 99.8, "Low": 99.5, "Close": 99.7},
        # bar 1 = c1 (above orb_low, leaves c1.Low=99.5)
        {"Open": 99.7, "High": 99.9, "Low": 99.5, "Close": 99.6},
        # bar 2 = breakdown straddles orb_low=99.0 (open above, close below) — bearish
        {"Open": 99.6, "High": 99.7, "Low": 98.5, "Close": 98.6},
        # bar 3 = c3 (high < c1.Low=99.5 → bearish FVG)
        {"Open": 98.6, "High": 99.0, "Low": 98.3, "Close": 98.5},
        # bar 4 (continuation)
        {"Open": 98.5, "High": 98.7, "Low": 98.2, "Close": 98.4},
    ]
    return pd.DataFrame(rows, index=idx)


def test_check_breakdown_finds_bearish_fvg():
    bars = _post_orb_bearish(orb_low=99.0)
    fvg = check_breakdown_with_fvg(bars, orb_low=99.0, bar_index=2, strict=False)
    assert fvg is not None
    assert fvg.top == 99.5  # c1.Low
    assert fvg.bottom == 99.0  # c3.High


def test_check_breakdown_strict_requires_straddle():
    bars = _post_orb_bearish(orb_low=99.0)
    fvg = check_breakdown_with_fvg(bars, orb_low=99.0, bar_index=2, strict=True)
    assert fvg is not None
    # strict requires fvg.bottom <= orb_low <= fvg.top
    assert fvg.bottom <= 99.0 <= fvg.top


def test_check_breakdown_strict_rejects_close_above_orb():
    # Make c2 close ABOVE orb_low → not a breakdown
    bars = _post_orb_bearish(orb_low=99.0).copy()
    bars.iloc[2, bars.columns.get_loc("Close")] = 99.20  # close above orb_low
    fvg = check_breakdown_with_fvg(bars, orb_low=99.0, bar_index=2, strict=True)
    assert fvg is None


def test_check_breakdown_strict_rejects_when_fvg_misses_orb():
    # Build bars where FVG is well below orb_low (no straddle)
    idx = pd.date_range("2026-05-12 09:45", periods=5, freq="5min", tz="US/Eastern")
    rows = [
        {"Open": 99.6, "High": 99.8, "Low": 99.5, "Close": 99.7},
        # c1.Low at 98.5
        {"Open": 98.7, "High": 98.9, "Low": 98.5, "Close": 98.6},
        # breakdown bar — straddles orb_low ostensibly
        {"Open": 99.1, "High": 99.2, "Low": 98.0, "Close": 98.05},
        # c3.High at 98.0 → FVG [98.0, 98.5], orb_low 99 is OUTSIDE
        {"Open": 98.0, "High": 98.0, "Low": 97.5, "Close": 97.7},
        {"Open": 97.7, "High": 97.9, "Low": 97.4, "Close": 97.5},
    ]
    bars = pd.DataFrame(rows, index=idx)
    fvg = check_breakdown_with_fvg(bars, orb_low=99.0, bar_index=2, strict=True)
    assert fvg is None  # FVG doesn't span orb_low


def test_check_breakdown_returns_none_when_no_breakdown():
    # c2 is bullish (close > open) → not a breakdown
    bars = _post_orb_bearish(orb_low=99.0).copy()
    bars.iloc[2] = {"Open": 99.0, "High": 99.5, "Low": 98.9, "Close": 99.4}
    fvg = check_breakdown_with_fvg(bars, orb_low=99.0, bar_index=2, strict=False)
    assert fvg is None
