"""Tests for CircuitBreaker.load_from_trades — crash recovery path."""

import pytest
from src.core.risk import CircuitBreaker


class TestLoadFromTrades:
    def test_empty_trades(self):
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=3.0)
        cb.load_from_trades([], current_week=14)
        assert cb.is_active is False
        assert cb._consecutive_losses == 0
        assert cb._weekly_loss == 0.0

    def test_restores_consecutive_losses(self):
        trades = [
            {"week": 14, "result": "LOSS", "net_pnl": -10, "capital_after": 1000},
            {"week": 14, "result": "LOSS", "net_pnl": -10, "capital_after": 990},
            {"week": 14, "result": "LOSS", "net_pnl": -10, "capital_after": 980},
        ]
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=50.0)
        cb.load_from_trades(trades, current_week=14)
        assert cb.is_active is True
        assert cb._consecutive_losses == 3

    def test_ignores_other_weeks(self):
        trades = [
            {"week": 13, "result": "LOSS", "net_pnl": -10, "capital_after": 1000},
            {"week": 13, "result": "LOSS", "net_pnl": -10, "capital_after": 990},
            {"week": 13, "result": "LOSS", "net_pnl": -10, "capital_after": 980},
            {"week": 14, "result": "WIN", "net_pnl": 20, "capital_after": 1020},
        ]
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=50.0)
        cb.load_from_trades(trades, current_week=14)
        assert cb.is_active is False
        assert cb._consecutive_losses == 0

    def test_win_resets_streak_in_restore(self):
        trades = [
            {"week": 14, "result": "LOSS", "net_pnl": -10, "capital_after": 1000},
            {"week": 14, "result": "LOSS", "net_pnl": -10, "capital_after": 990},
            {"week": 14, "result": "WIN", "net_pnl": 20, "capital_after": 1010},
            {"week": 14, "result": "LOSS", "net_pnl": -10, "capital_after": 1000},
        ]
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=50.0)
        cb.load_from_trades(trades, current_week=14)
        assert cb.is_active is False
        assert cb._consecutive_losses == 1

    def test_weekly_loss_trigger_from_restore(self):
        trades = [
            {"week": 14, "result": "LOSS", "net_pnl": -50, "capital_after": 1000},
        ]
        cb = CircuitBreaker(max_consecutive_losses=10, max_weekly_loss_pct=3.0)
        cb.load_from_trades(trades, current_week=14)
        assert cb.is_active is True

    def test_skips_trades_without_capital(self):
        """Trades with no capital_after are skipped (not using default 1)."""
        trades = [
            {"week": 14, "result": "LOSS", "net_pnl": -10},
            {"week": 14, "result": "LOSS", "net_pnl": -10},
            {"week": 14, "result": "LOSS", "net_pnl": -10},
        ]
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=3.0)
        cb.load_from_trades(trades, current_week=14)
        # No capital info → trades skipped → CB not active
        assert cb.is_active is False

    def test_mixed_capital_fields(self):
        """Trades with capital_after=0 but valid capital field."""
        trades = [
            {"week": 14, "result": "LOSS", "net_pnl": -50,
             "capital_after": 0, "capital": 1000},
        ]
        cb = CircuitBreaker(max_consecutive_losses=10, max_weekly_loss_pct=3.0)
        cb.load_from_trades(trades, current_week=14)
        assert cb.is_active is True

    def test_resets_state_before_loading(self):
        cb = CircuitBreaker(max_consecutive_losses=3)
        cb._active = True
        cb._consecutive_losses = 5
        cb._weekly_loss = 100
        cb.load_from_trades([], current_week=14)
        assert cb.is_active is False
        assert cb._consecutive_losses == 0
        assert cb._weekly_loss == 0.0
