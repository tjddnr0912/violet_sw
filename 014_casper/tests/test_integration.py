"""Integration tests for the full Casper trading pipeline.

Tests the complete flow: ORB → FVG → Signal → Position → Close → Store.
"""

import json
import pytest
import pandas as pd
import pytz
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.core.orb import calculate_orb
from src.core.fvg import detect_bullish_fvg
from src.core.strategy import scan_for_signal, check_pullback
from src.core.position import create_position, check_exit, move_stop_to_breakeven, close_position
from src.core.risk import check_vix_filter, determine_trend, CircuitBreaker
from src.data.trade_store import save_trade, load_trades, trade_from_position, get_cumulative_stats
from src.bot import CasperBot, BotState

ET = pytz.timezone("US/Eastern")


def _make_day_bars():
    """Create a realistic day of 5-min bars with ORB breakout + FVG."""
    bars = []
    # ORB bars (09:30-09:44): H=54, L=50
    bars.append({"Open": 51, "High": 53, "Low": 50, "Close": 52, "Volume": 5000})
    bars.append({"Open": 52, "High": 54, "Low": 51, "Close": 53, "Volume": 4000})
    bars.append({"Open": 53, "High": 54, "Low": 52, "Close": 53, "Volume": 3000})
    # Post-ORB (09:45+): breakout + FVG at bar 2
    bars.append({"Open": 53, "High": 54, "Low": 52, "Close": 53.5, "Volume": 3000})  # 09:45
    bars.append({"Open": 53.5, "High": 57, "Low": 53.5, "Close": 56, "Volume": 8000})  # 09:50 breakout
    bars.append({"Open": 56, "High": 58, "Low": 55, "Close": 57, "Volume": 6000})  # 09:55
    bars.append({"Open": 57, "High": 59, "Low": 56, "Close": 58, "Volume": 4000})  # 10:00
    # Pullback
    bars.append({"Open": 58, "High": 58, "Low": 54, "Close": 55, "Volume": 5000})  # 10:05

    index = []
    times = [(9, 30), (9, 35), (9, 40), (9, 45), (9, 50), (9, 55), (10, 0), (10, 5)]
    for h, m in times:
        index.append(ET.localize(datetime(2026, 4, 6, h, m)))
    return pd.DataFrame(bars, index=index)


class TestFullPipeline:
    """Test complete ORB → FVG → Signal → Position → Close flow."""

    def test_orb_to_signal(self):
        """ORB calculation followed by signal detection."""
        day = _make_day_bars()

        # Step 1: Calculate ORB
        orb = calculate_orb(day)
        assert orb is not None
        assert orb.high == 54.0
        assert orb.low == 50.0

        # Step 2: Scan for signal in post-ORB bars
        post_orb = day.between_time("09:45", "10:55")
        signal = scan_for_signal(post_orb, orb, "TQQQ", rr_ratio=2.0, min_risk=0.10)
        assert signal is not None
        assert signal.symbol == "TQQQ"
        assert signal.direction == "long"

    def test_signal_to_position_to_close(self):
        """Signal → Position → Win scenario."""
        day = _make_day_bars()
        orb = calculate_orb(day)
        post_orb = day.between_time("09:45", "10:55")
        signal = scan_for_signal(post_orb, orb, "TQQQ", rr_ratio=2.0)

        # Step 3: Create position
        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        assert pos.is_open

        # Step 4: Check exit - no exit yet
        result = check_exit(pos, current_high=56.0, current_low=54.5, current_close=55.5)
        assert result is None

        # Step 5: Take profit hit
        result = check_exit(pos, current_high=pos.take_profit + 1, current_low=55.0, current_close=pos.take_profit)
        assert result == "take_profit"

        # Step 6: Close
        close_position(pos, pos.take_profit, "take_profit", "10:30")
        assert pos.result == "WIN"
        assert pos.net_pnl > 0

    def test_full_loss_scenario(self):
        """Full pipeline resulting in stop loss."""
        day = _make_day_bars()
        orb = calculate_orb(day)
        post_orb = day.between_time("09:45", "10:55")
        signal = scan_for_signal(post_orb, orb, "TQQQ", rr_ratio=2.0)

        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")

        # Price drops to stop
        result = check_exit(pos, current_high=pos.entry_price, current_low=pos.stop_loss - 0.5, current_close=pos.stop_loss)
        assert result == "stop_loss"

        close_position(pos, pos.stop_loss, "stop_loss", "10:15")
        assert pos.result == "LOSS"
        assert pos.net_pnl < 0

    def test_be_move_scenario(self):
        """11:00 AM breakeven stop move."""
        day = _make_day_bars()
        orb = calculate_orb(day)
        post_orb = day.between_time("09:45", "10:55")
        signal = scan_for_signal(post_orb, orb, "TQQQ", rr_ratio=2.0)

        pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
        original_sl = pos.stop_loss

        # Move to breakeven
        move_stop_to_breakeven(pos)
        assert pos.be_stop_moved
        assert pos.stop_loss > original_sl

        # BE stop hit
        result = check_exit(pos, current_high=pos.entry_price + 0.1,
                          current_low=pos.stop_loss - 0.1, current_close=pos.stop_loss)
        assert result == "be_stop"

        close_position(pos, pos.stop_loss, "be_stop", "11:15")
        assert pos.result == "BE"


class TestPipelineWithStore:
    """Test pipeline with trade storage."""

    def test_save_and_stats(self, tmp_path):
        """Full pipeline → save → stats."""
        with patch("src.data.trade_store.TRADES_DIR", str(tmp_path)):
            day = _make_day_bars()
            orb = calculate_orb(day)
            post_orb = day.between_time("09:45", "10:55")
            signal = scan_for_signal(post_orb, orb, "TQQQ", rr_ratio=2.0)
            pos = create_position(signal, shares=30, commission_rate=0.0009, entry_time="09:55")
            close_position(pos, pos.take_profit, "take_profit", "10:30")

            trade = trade_from_position(pos)
            trade["capital_after"] = 1500 + pos.net_pnl
            save_trade(trade)

            trades = load_trades()
            assert len(trades) == 1
            assert trades[0]["result"] == "WIN"

            stats = get_cumulative_stats(trades)
            assert stats["wins"] == 1
            assert stats["total_pnl"] > 0


class TestRiskIntegration:
    """Test risk filters in pipeline context."""

    def test_vix_blocks_trading(self):
        skip = check_vix_filter(35.0)
        assert skip is not None

    def test_circuit_breaker_blocks(self):
        cb = CircuitBreaker(max_consecutive_losses=3, max_weekly_loss_pct=50.0)
        cb.reset_if_new_week(1)
        for _ in range(3):
            cb.record_trade("LOSS", -10, 10000)
        assert cb.is_active

    def test_trend_determines_symbol(self):
        # Bull
        trend = determine_trend(500.0, 490.0)
        assert trend.symbol == "TQQQ"
        # Bear
        trend = determine_trend(480.0, 490.0)
        assert trend.symbol == "SQQQ"


class TestBotInit:
    """Test bot initialization."""

    @patch("src.bot.load_trades", return_value=[])
    @patch("src.bot.load_env", return_value={
        "kis_app_key": "", "kis_app_secret": "", "kis_account_no": "",
        "kis_account_product": "01", "kis_base_url": "",
        "telegram_bot_token": "", "telegram_chat_id": "",
        "trading_mode": "paper", "log_level": "WARNING", "timezone": "US/Eastern",
    })
    def test_bot_creates(self, mock_env, mock_trades):
        bot = CasperBot()
        assert bot.state == BotState.WAITING
        assert bot.position is None
