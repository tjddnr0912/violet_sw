"""Extended tests for trade_store — trade_from_position and atomic save."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from src.core.orb import OpeningRange
from src.core.fvg import FairValueGap
from src.core.strategy import TradeSignal
from src.core.position import create_position, close_position
from src.data.trade_store import trade_from_position, save_trade, load_trades


def _make_closed_position():
    """Create a closed Position for testing."""
    orb = OpeningRange(high=54.0, low=50.0, range_size=4.0, date="2026-04-06")
    fvg = FairValueGap(top=55.0, bottom=53.5, size=1.5, timestamp="09:50")
    signal = TradeSignal(
        symbol="TQQQ", direction="long",
        entry_price=54.25, stop_loss=52.0, take_profit=58.75,
        risk_per_share=2.25, rr_ratio=2.0, fvg=fvg, orb=orb,
        signal_time="2026-04-06 09:50",
    )
    pos = create_position(signal, 10, 0.0009, "09:55")
    close_position(pos, 58.75, "take_profit", "10:30")
    return pos


class TestTradeFromPosition:
    def test_fields_are_correct(self):
        pos = _make_closed_position()
        trade = trade_from_position(pos)

        assert trade["symbol"] == "TQQQ"
        assert trade["direction"] == "long"
        assert trade["entry_price"] == 54.25
        assert trade["exit_price"] == 58.75
        assert trade["exit_reason"] == "take_profit"
        assert trade["result"] == "WIN"
        assert trade["shares"] == 10

    def test_trend_field_is_direction(self):
        """Bug fix: trend should be direction, not ORB date."""
        pos = _make_closed_position()
        trade = trade_from_position(pos)
        assert trade["trend"] == "long"
        assert trade["trend"] != pos.signal.orb.date

    def test_orb_and_fvg_data_preserved(self):
        pos = _make_closed_position()
        trade = trade_from_position(pos)
        assert trade["orb_high"] == 54.0
        assert trade["orb_low"] == 50.0
        assert trade["fvg_top"] == 55.0
        assert trade["fvg_bottom"] == 53.5

    def test_pnl_fields(self):
        pos = _make_closed_position()
        trade = trade_from_position(pos)
        assert trade["gross_pnl"] > 0
        assert trade["commission"] > 0
        assert trade["net_pnl"] > 0
        assert trade["r_multiple"] > 0

    def test_capital_after_is_none(self):
        """capital_after is None; set by bot after calling."""
        pos = _make_closed_position()
        trade = trade_from_position(pos)
        assert trade["capital_after"] is None


class TestAtomicSave:
    def test_save_is_atomic(self, tmp_path):
        """Verify atomic save doesn't leave .tmp files."""
        with patch("src.data.trade_store.TRADES_DIR", str(tmp_path)):
            save_trade({"result": "WIN", "net_pnl": 10}, 2026)
            # No .tmp file should remain
            files = os.listdir(tmp_path)
            assert not any(f.endswith(".tmp") for f in files)
            assert "trades_2026.json" in files

    def test_save_multiple_atomic(self, tmp_path):
        """Multiple saves produce valid JSON."""
        with patch("src.data.trade_store.TRADES_DIR", str(tmp_path)):
            for i in range(5):
                save_trade({"result": "WIN", "net_pnl": i * 10}, 2026)
            trades = load_trades(2026)
            assert len(trades) == 5
