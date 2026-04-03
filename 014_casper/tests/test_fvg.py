"""Tests for FVG module."""

import pytest
import pandas as pd
import pytz
from datetime import datetime

from src.core.fvg import detect_bullish_fvg, check_breakout_with_fvg

ET = pytz.timezone("US/Eastern")


def _make_bars(data, start_hour=9, start_min=45):
    """Create test 5-min bar DataFrame."""
    index = []
    for i in range(len(data)):
        mins = start_min + i * 5
        h = start_hour + mins // 60
        m = mins % 60
        dt = ET.localize(datetime(2026, 4, 6, h, m))
        index.append(dt)
    return pd.DataFrame(data, index=index)


class TestDetectBullishFVG:
    def test_fvg_present(self):
        """c1.High(52) < c3.Low(53) → gap exists."""
        candles = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 52, "High": 56, "Low": 52, "Close": 55, "Volume": 2000},
            {"Open": 55, "High": 57, "Low": 53, "Close": 56, "Volume": 1500},
        ])
        fvg = detect_bullish_fvg(candles)
        assert fvg is not None
        assert fvg.bottom == 52.0  # c1.High
        assert fvg.top == 53.0     # c3.Low
        assert fvg.size == 1.0

    def test_no_fvg(self):
        """c1.High(52) >= c3.Low(51) → no gap."""
        candles = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 51, "High": 53, "Low": 50, "Close": 52, "Volume": 1000},
            {"Open": 52, "High": 54, "Low": 51, "Close": 53, "Volume": 1000},
        ])
        fvg = detect_bullish_fvg(candles)
        assert fvg is None

    def test_not_enough_candles(self):
        candles = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
        ])
        assert detect_bullish_fvg(candles) is None

    def test_fvg_mid(self):
        candles = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 52, "High": 56, "Low": 52, "Close": 55, "Volume": 2000},
            {"Open": 55, "High": 57, "Low": 54, "Close": 56, "Volume": 1500},
        ])
        fvg = detect_bullish_fvg(candles)
        assert fvg is not None
        assert fvg.mid == 53.0  # (52+54)/2


class TestBreakoutWithFVG:
    def test_breakout_with_fvg(self):
        """Bar closes above ORB high + FVG exists."""
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 52, "High": 56, "Low": 52, "Close": 55, "Volume": 2000},  # breakout
            {"Open": 55, "High": 57, "Low": 53, "Close": 56, "Volume": 1500},
        ])
        fvg = check_breakout_with_fvg(bars, orb_high=53.0, bar_index=1)
        assert fvg is not None

    def test_no_breakout(self):
        """Close below ORB high."""
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 51, "High": 53, "Low": 50, "Close": 52, "Volume": 1000},
            {"Open": 52, "High": 54, "Low": 51, "Close": 53, "Volume": 1000},
        ])
        fvg = check_breakout_with_fvg(bars, orb_high=55.0, bar_index=1)
        assert fvg is None

    def test_bearish_candle_no_breakout(self):
        """Close > ORB but bearish (close < open) → no signal."""
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 56, "High": 56, "Low": 54, "Close": 55, "Volume": 2000},  # bearish
            {"Open": 55, "High": 57, "Low": 53, "Close": 56, "Volume": 1500},
        ])
        fvg = check_breakout_with_fvg(bars, orb_high=53.0, bar_index=1)
        assert fvg is None  # close > open check fails

    def test_edge_bar_index(self):
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
        ])
        assert check_breakout_with_fvg(bars, orb_high=50.0, bar_index=0) is None
