"""Tests for position management module."""

import pytest
from src.core.position import (
    Position, create_position, check_exit,
    move_stop_to_breakeven, close_position,
    check_tp1_fill, apply_partial_fill,
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


def _make_signal_with_tp1():
    """Same as _make_signal but with tp1_price set (Scenario B + partial TP)."""
    fvg = FairValueGap(top=53.0, bottom=52.0, size=1.0, timestamp="2026-04-06 09:50")
    orb = OpeningRange(high=53.0, low=50.0, range_size=3.0, date="2026-04-06")
    # entry=52.50, stop=51.00, risk=1.50, RR=2 → TP2=55.50, TP1@1.5R=54.75
    return TradeSignal(
        symbol="TQQQ", direction="long",
        entry_price=52.50, stop_loss=51.00,
        take_profit=55.50, risk_per_share=1.50,
        rr_ratio=2.0, fvg=fvg, orb=orb,
        signal_time="2026-04-06 09:55",
        tp1_price=54.75,
    )


class TestPartialTP:
    """Scenario B + Partial TP path — TP1 fill, SL move, final close."""

    def test_partial_fields_initialized(self):
        sig = _make_signal_with_tp1()
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", tp1_close_pct=0.50,
                              orb_high=53.0)
        assert pos.tp1_price == 54.75
        assert pos.tp1_close_pct == 0.50
        assert pos.tp1_filled is False
        assert pos.partial_shares_initial == 20
        assert pos.partial_shares_closed == 0
        assert pos.orb_high == 53.0

    def test_check_tp1_fill_below_threshold(self):
        sig = _make_signal_with_tp1()
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", orb_high=53.0)
        # current high 54.74 just below TP1 54.75 → no fill
        assert check_tp1_fill(pos, 54.74) is False

    def test_check_tp1_fill_at_threshold(self):
        sig = _make_signal_with_tp1()
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", orb_high=53.0)
        assert check_tp1_fill(pos, 54.75) is True
        assert check_tp1_fill(pos, 55.00) is True

    def test_check_tp1_fill_skips_when_no_tp1(self):
        sig = _make_signal()  # no tp1_price
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", orb_high=53.0)
        # Even with high price, no TP1 → no fill
        assert check_tp1_fill(pos, 100.0) is False

    def test_apply_partial_fill_moves_sl_and_reduces_shares(self):
        sig = _make_signal_with_tp1()
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", tp1_close_pct=0.50,
                              orb_high=53.0)
        sold = apply_partial_fill(pos, fill_price=54.75, fill_time="10:10")
        assert sold == 10
        assert pos.tp1_filled is True
        assert pos.partial_shares_closed == 10
        assert pos.partial_exit_price == 54.75
        assert pos.shares == 10  # remaining
        assert pos.stop_loss == 53.0  # moved to ORB.high (was 51.00)

    def test_apply_partial_fill_idempotent(self):
        sig = _make_signal_with_tp1()
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", orb_high=53.0)
        apply_partial_fill(pos, 54.75, "10:10")
        second = apply_partial_fill(pos, 54.80, "10:15")
        assert second == 0  # second call is a no-op

    def test_apply_partial_fill_no_sl_move_when_orb_below_current_sl(self):
        sig = _make_signal_with_tp1()
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", orb_high=50.0)
        # ORB.high 50 < current SL 51 → SL should NOT move down
        apply_partial_fill(pos, 54.75, "10:10")
        assert pos.stop_loss == 51.00  # unchanged

    def test_net_pnl_combines_partial_and_final_legs(self):
        sig = _make_signal_with_tp1()
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", orb_high=53.0)
        # TP1: sell 10 sh @ 54.75 → partial gross = (54.75-52.50)×10 = 22.5
        apply_partial_fill(pos, 54.75, "10:10")
        # Final close: SL=ORB.high=53.0 hit → 10 sh @ 53.0
        close_position(pos, price=53.0, reason="stop_loss", time_str="11:30")
        # gross = 22.5 (partial) + (53.0-52.50)*10 = 22.5 + 5.0 = 27.5
        # commission ~ 0.25%×2 of legs
        assert pos.gross_pnl == pytest.approx(27.5, abs=0.01)
        assert pos.net_pnl > 0  # both legs positive

    def test_r_multiple_uses_initial_shares(self):
        sig = _make_signal_with_tp1()
        pos = create_position(sig, shares=20, commission_rate=0.0025,
                              entry_time="09:55", orb_high=53.0)
        apply_partial_fill(pos, 54.75, "10:10")
        close_position(pos, price=53.0, reason="stop_loss", time_str="11:30")
        # R denominator = 1.50 × 20 = 30 (using INITIAL shares)
        # Not 1.50 × 10 (post-partial). This keeps comparison consistent.
        expected_denom = 1.50 * 20
        assert pos.r_multiple == pytest.approx(pos.net_pnl / expected_denom, abs=0.01)
