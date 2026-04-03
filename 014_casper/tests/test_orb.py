"""Tests for ORB module."""

import pytest
import pandas as pd
import pytz
from datetime import datetime

from src.core.orb import calculate_orb, is_orb_too_wide, OpeningRange

ET = pytz.timezone("US/Eastern")


def _make_bars(data, start_hour=9, start_min=30):
    """Create test 5-min bar DataFrame."""
    index = []
    for i in range(len(data)):
        mins = start_min + i * 5
        h = start_hour + mins // 60
        m = mins % 60
        dt = ET.localize(datetime(2026, 4, 6, h, m))
        index.append(dt)
    df = pd.DataFrame(data, index=index)
    return df


class TestCalculateORB:
    def test_basic_orb(self):
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 51, "High": 53, "Low": 50, "Close": 52, "Volume": 1000},
            {"Open": 52, "High": 54, "Low": 51, "Close": 53, "Volume": 1000},
        ])
        orb = calculate_orb(bars)
        assert orb is not None
        assert orb.high == 54.0
        assert orb.low == 49.0
        assert orb.range_size == 5.0

    def test_not_enough_bars(self):
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 49, "Close": 51, "Volume": 1000},
            {"Open": 51, "High": 53, "Low": 50, "Close": 52, "Volume": 1000},
        ])
        orb = calculate_orb(bars)
        assert orb is None

    def test_empty_dataframe(self):
        bars = pd.DataFrame()
        orb = calculate_orb(bars)
        assert orb is None

    def test_orb_mid(self):
        bars = _make_bars([
            {"Open": 50, "High": 52, "Low": 48, "Close": 51, "Volume": 1000},
            {"Open": 51, "High": 53, "Low": 50, "Close": 52, "Volume": 1000},
            {"Open": 52, "High": 54, "Low": 51, "Close": 53, "Volume": 1000},
        ])
        orb = calculate_orb(bars)
        assert orb.mid == 51.0  # (54+48)/2


class TestORBTooWide:
    def test_normal_range(self):
        orb = OpeningRange(high=52, low=50, range_size=2.0, date="2026-04-06")
        assert is_orb_too_wide(orb, avg_daily_range=3.0) is False

    def test_too_wide(self):
        orb = OpeningRange(high=55, low=50, range_size=5.0, date="2026-04-06")
        assert is_orb_too_wide(orb, avg_daily_range=3.0) is True  # 5/3 = 1.67 > 1.5

    def test_exact_boundary(self):
        orb = OpeningRange(high=54.5, low=50, range_size=4.5, date="2026-04-06")
        # 4.5 / 3.0 = 1.5 exactly, not > 1.5
        assert is_orb_too_wide(orb, avg_daily_range=3.0) is False

    def test_zero_adr(self):
        orb = OpeningRange(high=52, low=50, range_size=2.0, date="2026-04-06")
        assert is_orb_too_wide(orb, avg_daily_range=0) is False
