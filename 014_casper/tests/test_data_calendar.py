"""Tests for src.data.calendar."""

from datetime import date

from src.data.calendar import trading_days, is_trading_day, early_close_minutes


def test_trading_days_excludes_weekends():
    days = trading_days(date(2026, 5, 4), date(2026, 5, 10))
    # 2026-05-04 Mon, 05-05 Tue, 06 Wed, 07 Thu, 08 Fri — 5 days
    assert len(days) == 5
    assert date(2026, 5, 9) not in days
    assert date(2026, 5, 10) not in days


def test_trading_days_excludes_holidays_independence():
    # 2025-07-04 Friday = US Independence Day → closed
    days = trading_days(date(2025, 6, 30), date(2025, 7, 4))
    assert date(2025, 7, 4) not in days


def test_is_trading_day_true_for_weekday():
    assert is_trading_day(date(2026, 5, 7)) is True   # Thursday


def test_is_trading_day_false_for_weekend():
    assert is_trading_day(date(2026, 5, 10)) is False  # Sunday


def test_early_close_thanksgiving():
    # Day after Thanksgiving (Black Friday) — 13:00 ET close
    minutes = early_close_minutes(date(2025, 11, 28))
    assert minutes == 13 * 60


def test_early_close_normal_day_is_16():
    minutes = early_close_minutes(date(2026, 5, 7))
    assert minutes == 16 * 60
