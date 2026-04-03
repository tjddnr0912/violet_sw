"""Tests for risk management module."""

import pytest
from src.core.risk import check_vix_filter, determine_trend, CircuitBreaker


class TestVIXFilter:
    def test_normal_vix(self):
        assert check_vix_filter(20.0) is None

    def test_vix_too_low(self):
        result = check_vix_filter(10.0)
        assert result is not None
        assert "too low" in result

    def test_vix_too_high(self):
        result = check_vix_filter(35.0)
        assert result is not None
        assert "too high" in result

    def test_boundary_low(self):
        assert check_vix_filter(12.0) is None

    def test_boundary_high(self):
        assert check_vix_filter(30.0) is None


class TestDetermineTrend:
    def test_bull_trend(self):
        trend = determine_trend(qqq_close=500.0, qqq_ma20=490.0)
        assert trend.direction == "bull"
        assert trend.symbol == "TQQQ"

    def test_bear_trend(self):
        trend = determine_trend(qqq_close=480.0, qqq_ma20=490.0)
        assert trend.direction == "bear"
        assert trend.symbol == "SQQQ"

    def test_exact_equal_is_bear(self):
        trend = determine_trend(qqq_close=490.0, qqq_ma20=490.0)
        assert trend.direction == "bear"


class TestCircuitBreaker:
    def test_no_trigger(self):
        cb = CircuitBreaker(max_consecutive_losses=3)
        cb.reset_if_new_week(1)
        cb.record_trade("LOSS", -10, 1000)
        cb.record_trade("WIN", 20, 1010)
        assert cb.is_active is False

    def test_consecutive_losses_trigger(self):
        cb = CircuitBreaker(max_consecutive_losses=3)
        cb.reset_if_new_week(1)
        cb.record_trade("LOSS", -10, 1000)
        cb.record_trade("LOSS", -10, 990)
        assert cb.is_active is False
        cb.record_trade("LOSS", -10, 980)
        assert cb.is_active is True

    def test_win_resets_streak(self):
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=50.0)
        cb.reset_if_new_week(1)
        cb.record_trade("LOSS", -10, 10000)
        cb.record_trade("LOSS", -10, 9990)
        cb.record_trade("WIN", 20, 10010)
        cb.record_trade("LOSS", -10, 10000)
        assert cb.is_active is False

    def test_weekly_reset(self):
        cb = CircuitBreaker(max_consecutive_losses=3)
        cb.reset_if_new_week(1)
        cb.record_trade("LOSS", -10, 1000)
        cb.record_trade("LOSS", -10, 990)
        cb.record_trade("LOSS", -10, 980)
        assert cb.is_active is True

        cb.reset_if_new_week(2)  # New week
        assert cb.is_active is False

    def test_weekly_loss_pct_trigger(self):
        cb = CircuitBreaker(max_consecutive_losses=10, max_weekly_loss_pct=3.0)
        cb.reset_if_new_week(1)
        # Lose 3.1% of 1000
        cb.record_trade("LOSS", -31, 1000)
        assert cb.is_active is True

    def test_be_does_not_count_as_loss(self):
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=50.0)
        cb.reset_if_new_week(1)
        cb.record_trade("LOSS", -10, 10000)
        cb.record_trade("LOSS", -10, 9990)
        cb.record_trade("BE", 0, 9990)  # Resets streak
        cb.record_trade("LOSS", -10, 9980)
        assert cb.is_active is False
