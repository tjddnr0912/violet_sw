"""Tests for strategy engine module."""

import pytest
import pandas as pd
import pytz
from datetime import datetime

from src.core.strategy import scan_for_signal, check_pullback
from src.core.orb import OpeningRange
from src.core.fvg import FairValueGap

ET = pytz.timezone("US/Eastern")


def _make_bars(data, start_hour=9, start_min=45):
    index = []
    for i in range(len(data)):
        mins = start_min + i * 5
        h = start_hour + mins // 60
        m = mins % 60
        dt = ET.localize(datetime(2026, 4, 6, h, m))
        index.append(dt)
    return pd.DataFrame(data, index=index)


class TestScanForSignal:
    def test_signal_found(self):
        """Bars show breakout + FVG → signal returned."""
        orb = OpeningRange(high=53.0, low=50.0, range_size=3.0, date="2026-04-06")
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 52, "High": 56, "Low": 52, "Close": 55, "Volume": 2000},  # breakout > 53
            {"Open": 55, "High": 57, "Low": 53, "Close": 56, "Volume": 1500},
            {"Open": 56, "High": 58, "Low": 55, "Close": 57, "Volume": 1000},
        ])
        signal = scan_for_signal(bars, orb, "TQQQ", rr_ratio=2.0, min_risk=0.10)
        assert signal is not None
        assert signal.symbol == "TQQQ"
        assert signal.direction == "long"
        assert signal.entry_price == 52.50  # FVG mid (52+53)/2
        assert signal.stop_loss == 49.0     # prior candle low
        assert signal.risk_per_share == 3.50

    def test_no_signal_no_breakout(self):
        orb = OpeningRange(high=60.0, low=50.0, range_size=10.0, date="2026-04-06")
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 51, "High": 53, "Low": 50, "Close": 52, "Volume": 1000},
            {"Open": 52, "High": 54, "Low": 51, "Close": 53, "Volume": 1000},
            {"Open": 53, "High": 55, "Low": 52, "Close": 54, "Volume": 1000},
        ])
        signal = scan_for_signal(bars, orb, "TQQQ")
        assert signal is None

    def test_not_enough_bars(self):
        orb = OpeningRange(high=53.0, low=50.0, range_size=3.0, date="2026-04-06")
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
        ])
        signal = scan_for_signal(bars, orb, "TQQQ")
        assert signal is None

    def test_min_risk_filter(self):
        orb = OpeningRange(high=53.0, low=50.0, range_size=3.0, date="2026-04-06")
        # FVG with very small gap → risk too small
        bars = _make_bars([
            {"Open": 52.95, "High": 53.00, "Low": 52.90, "Close": 52.98, "Volume": 1000},
            {"Open": 53.00, "High": 54.00, "Low": 53.00, "Close": 53.50, "Volume": 2000},
            {"Open": 53.50, "High": 54.50, "Low": 53.01, "Close": 54.00, "Volume": 1500},
            {"Open": 54.00, "High": 55.00, "Low": 53.50, "Close": 54.50, "Volume": 1000},
        ])
        signal = scan_for_signal(bars, orb, "TQQQ", min_risk=5.0)
        assert signal is None


class TestCheckPullback:
    def test_pullback_occurs(self):
        fvg = FairValueGap(top=53.0, bottom=52.0, size=1.0, timestamp="09:50")
        bar = pd.Series({"High": 54.0, "Low": 52.5, "Open": 53.5, "Close": 53.0})
        assert check_pullback(bar, fvg) == True

    def test_no_pullback(self):
        fvg = FairValueGap(top=53.0, bottom=52.0, size=1.0, timestamp="09:50")
        bar = pd.Series({"High": 56.0, "Low": 54.0, "Open": 55.0, "Close": 55.5})
        assert check_pullback(bar, fvg) == False
