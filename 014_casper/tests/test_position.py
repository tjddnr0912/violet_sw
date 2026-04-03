"""Tests for position management module."""

import pytest
from src.core.position import (
    Position, create_position, check_exit,
    move_stop_to_breakeven, close_position,
)
from src.core.strategy import TradeSignal
from src.core.orb import OpeningRange
from src.core.fvg import FairValueGap


def _make_signal():
    fvg = FairValueGap(top=53.0, bottom=52.0, size=1.0, timestamp="2026-04-06 09:50")
    orb = OpeningRange(high=53.0, low=50.0, range_size=3.0, date="2026-04-06")
    return TradeSignal(
        symbol="TQQQ", direction="long",
        entry_price=52.50, stop_loss=51.00,
        take_profit=55.50, risk_per_share=1.50,
        rr_ratio=2.0, fvg=fvg, orb=orb,
        signal_time="2026-04-06 09:55",
    )


class TestCreatePosition:
    def test_basic(self):
        signal = _make_signal()
        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        assert pos.symbol == "TQQQ"
        assert pos.shares == 30
        assert pos.is_open is True
        assert pos.original_stop == 51.00

    def test_breakeven_price(self):
        signal = _make_signal()
        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        # BE = 52.50 * (1 + 0.0018) = 52.5945
        assert abs(pos.breakeven_price - 52.5945) < 0.001


class TestCheckExit:
    def _get_position(self):
        signal = _make_signal()
        return create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")

    def test_stop_loss_hit(self):
        pos = self._get_position()
        result = check_exit(pos, current_high=53.0, current_low=50.50, current_close=51.0)
        assert result == "stop_loss"

    def test_take_profit_hit(self):
        pos = self._get_position()
        result = check_exit(pos, current_high=56.0, current_low=53.0, current_close=55.5)
        assert result == "take_profit"

    def test_no_exit(self):
        pos = self._get_position()
        result = check_exit(pos, current_high=53.0, current_low=52.0, current_close=52.5)
        assert result is None

    def test_be_stop_hit(self):
        pos = self._get_position()
        move_stop_to_breakeven(pos)
        result = check_exit(pos, current_high=53.0, current_low=52.0, current_close=52.3)
        assert result == "be_stop"


class TestMoveStopToBE:
    def test_move(self):
        signal = _make_signal()
        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        assert pos.be_stop_moved is False
        move_stop_to_breakeven(pos)
        assert pos.be_stop_moved is True
        assert pos.stop_loss > pos.original_stop

    def test_no_double_move(self):
        signal = _make_signal()
        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        move_stop_to_breakeven(pos)
        sl_after_first = pos.stop_loss
        move_stop_to_breakeven(pos)
        assert pos.stop_loss == sl_after_first


class TestClosePosition:
    def test_close_win(self):
        signal = _make_signal()
        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        close_position(pos, price=55.50, reason="take_profit", time_str="10:20")
        assert pos.is_open is False
        assert pos.result == "WIN"
        assert pos.net_pnl > 0

    def test_close_loss(self):
        signal = _make_signal()
        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        close_position(pos, price=51.00, reason="stop_loss", time_str="10:10")
        assert pos.result == "LOSS"
        assert pos.net_pnl < 0

    def test_r_multiple(self):
        signal = _make_signal()
        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        close_position(pos, price=55.50, reason="take_profit", time_str="10:20")
        # Gross: (55.50 - 52.50) * 30 = 90.0
        # Comm: (52.50 + 55.50) * 30 * 0.0009 = 2.916
        # Net: 90.0 - 2.916 = 87.084
        # Risk: 1.50 * 30 = 45.0
        # R: 87.084 / 45.0 = 1.935
        assert pos.r_multiple > 1.5
