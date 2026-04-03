"""Tests for time_utils module."""

import pytest
from datetime import datetime, time as dtime, date
from unittest.mock import patch
import pytz

from src.utils.time_utils import (
    now_et, today_et, current_time_et, is_weekday,
    is_market_open, is_pre_market, is_orb_forming, is_scan_window,
    is_past_be_time, is_force_close_time, get_week_number,
    seconds_until, format_et, ET,
)


def _mock_et(hour, minute, weekday=0):
    """Create a mock datetime in ET for testing."""
    # 2026-04-06 is Monday (weekday=0)
    base_date = date(2026, 4, 6 + weekday)
    dt = ET.localize(datetime(base_date.year, base_date.month, base_date.day, hour, minute))
    return dt


class TestTimeChecks:
    """Test time window checks."""

    @patch("src.utils.time_utils.now_et")
    def test_is_pre_market(self, mock_now):
        mock_now.return_value = _mock_et(8, 30)
        assert is_pre_market() is True

        mock_now.return_value = _mock_et(9, 30)
        assert is_pre_market() is False

        mock_now.return_value = _mock_et(7, 59)
        assert is_pre_market() is False

    @patch("src.utils.time_utils.now_et")
    def test_is_orb_forming(self, mock_now):
        mock_now.return_value = _mock_et(9, 30)
        assert is_orb_forming() is True

        mock_now.return_value = _mock_et(9, 44)
        assert is_orb_forming() is True

        mock_now.return_value = _mock_et(9, 45)
        assert is_orb_forming() is False

    @patch("src.utils.time_utils.now_et")
    def test_is_scan_window(self, mock_now):
        mock_now.return_value = _mock_et(9, 45)
        assert is_scan_window() is True

        mock_now.return_value = _mock_et(10, 55)
        assert is_scan_window() is True

        mock_now.return_value = _mock_et(10, 56)
        assert is_scan_window() is False

    @patch("src.utils.time_utils.now_et")
    def test_is_past_be_time(self, mock_now):
        mock_now.return_value = _mock_et(10, 59)
        assert is_past_be_time() is False

        mock_now.return_value = _mock_et(11, 0)
        assert is_past_be_time() is True

    @patch("src.utils.time_utils.now_et")
    def test_is_force_close_time(self, mock_now):
        mock_now.return_value = _mock_et(15, 49)
        assert is_force_close_time() is False

        mock_now.return_value = _mock_et(15, 50)
        assert is_force_close_time() is True

    @patch("src.utils.time_utils.now_et")
    def test_is_market_open(self, mock_now):
        mock_now.return_value = _mock_et(9, 30)
        assert is_market_open() is True

        mock_now.return_value = _mock_et(16, 1)
        assert is_market_open() is False

    @patch("src.utils.time_utils.now_et")
    def test_weekend_not_market(self, mock_now):
        # Saturday = weekday 5
        mock_now.return_value = _mock_et(10, 0, weekday=5)
        assert is_market_open() is False
        assert is_weekday() is False


class TestUtilFunctions:
    """Test utility functions."""

    def test_format_et(self):
        dt = ET.localize(datetime(2026, 4, 2, 9, 30, 0))
        assert format_et(dt) == "2026-04-02 09:30:00 ET"

    @patch("src.utils.time_utils.now_et")
    def test_seconds_until(self, mock_now):
        mock_now.return_value = _mock_et(9, 0)
        secs = seconds_until(dtime(9, 30))
        assert abs(secs - 1800) < 1  # 30 minutes = 1800 seconds

    @patch("src.utils.time_utils.now_et")
    def test_seconds_until_past(self, mock_now):
        mock_now.return_value = _mock_et(10, 0)
        secs = seconds_until(dtime(9, 30))
        assert secs < 0
