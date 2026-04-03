"""Advanced bot tests: _tick(), _handle_pre_market(), _handle_orb_forming(), run()."""

import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, PropertyMock
import pytz

from src.bot import CasperBot, BotState
from src.core.risk import TrendState
from src.core.orb import OpeningRange

ET = pytz.timezone("US/Eastern")


def _make_bot(tmp_path=None):
    env = {
        "kis_app_key": "", "kis_app_secret": "", "kis_account_no": "",
        "kis_account_product": "01", "kis_base_url": "",
        "telegram_bot_token": "", "telegram_chat_id": "",
        "trading_mode": "paper", "test_mode": False,
        "log_level": "WARNING", "timezone": "US/Eastern",
    }
    with patch("src.bot.load_trades", return_value=[]):
        with patch("src.bot.load_env", return_value=env):
            bot = CasperBot()
    if tmp_path:
        bot._position_state_file = str(tmp_path / "pos_state.json")
    return bot


class TestTick:
    """Test _tick() dispatches to correct handler for each state."""

    @patch("src.bot.time_utils")
    def test_tick_dispatches_waiting(self, mock_time):
        mock_time.now_et.return_value = ET.localize(datetime(2026, 4, 6, 7, 0))
        bot = _make_bot()
        bot.today_date = "2026-04-06"
        bot.state = BotState.WAITING

        with patch.object(bot, "_handle_waiting") as mock_handler:
            bot._tick()
            mock_handler.assert_called_once()

    @patch("src.bot.time_utils")
    def test_tick_dispatches_pre_market(self, mock_time):
        mock_time.now_et.return_value = ET.localize(datetime(2026, 4, 6, 8, 30))
        bot = _make_bot()
        bot.today_date = "2026-04-06"
        bot.state = BotState.PRE_MARKET

        with patch.object(bot, "_handle_pre_market") as mock_handler:
            bot._tick()
            mock_handler.assert_called_once()

    @patch("src.bot.time_utils")
    def test_tick_dispatches_scanning(self, mock_time):
        mock_time.now_et.return_value = ET.localize(datetime(2026, 4, 6, 9, 50))
        bot = _make_bot()
        bot.today_date = "2026-04-06"
        bot.state = BotState.SCANNING

        with patch.object(bot, "_handle_scanning") as mock_handler:
            bot._tick()
            mock_handler.assert_called_once()

    @patch("src.bot.time.sleep")
    @patch("src.bot.time_utils")
    def test_tick_detects_day_change(self, mock_time, mock_sleep):
        mock_time.now_et.return_value = ET.localize(datetime(2026, 4, 7, 7, 0))
        mock_time.is_weekday.return_value = True
        mock_time.is_pre_market.return_value = False
        mock_time.is_orb_forming.return_value = False
        bot = _make_bot()
        bot.today_date = "2026-04-06"  # Yesterday
        bot.state = BotState.DONE_TODAY

        with patch.object(bot, "_reset_day", wraps=bot._reset_day) as mock_reset:
            bot._tick()
            mock_reset.assert_called_once_with("2026-04-07")


class TestHandlePreMarket:
    @patch("src.bot.time.sleep")
    @patch("src.bot.get_qqq_trend_data", return_value=(500.0, 490.0))
    @patch("src.bot.get_vix_close", return_value=20.0)
    @patch("src.bot.time_utils")
    def test_full_pre_market_flow(self, mock_time, mock_vix, mock_qqq, mock_sleep):
        mock_time.is_orb_forming.return_value = True
        bot = _make_bot()
        bot.state = BotState.PRE_MARKET

        bot._handle_pre_market()

        assert bot.trend is not None
        assert bot.trend.direction == "bull"
        assert bot.trend.symbol == "TQQQ"
        assert bot.state == BotState.ORB_FORMING

    @patch("src.bot.time.sleep")
    @patch("src.bot.get_vix_close", return_value=None)
    def test_vix_unavailable_retries(self, mock_vix, mock_sleep):
        bot = _make_bot()
        bot.state = BotState.PRE_MARKET
        bot._handle_pre_market()

        # VIX unavailable → stays in PRE_MARKET, sleeps 300s
        assert bot.state == BotState.PRE_MARKET
        mock_sleep.assert_called_with(300)

    @patch("src.bot.time.sleep")
    @patch("src.bot.get_vix_close", return_value=35.0)
    def test_vix_too_high_skips(self, mock_vix, mock_sleep):
        bot = _make_bot()
        bot.state = BotState.PRE_MARKET
        bot._handle_pre_market()
        assert bot.state == BotState.DONE_TODAY

    @patch("src.bot.time.sleep")
    @patch("src.bot.get_qqq_trend_data", return_value=(None, None))
    @patch("src.bot.get_vix_close", return_value=20.0)
    def test_qqq_unavailable_retries(self, mock_vix, mock_qqq, mock_sleep):
        bot = _make_bot()
        bot.state = BotState.PRE_MARKET
        bot._handle_pre_market()
        assert bot.state == BotState.PRE_MARKET
        mock_sleep.assert_called_with(300)

    def test_circuit_breaker_blocks(self):
        bot = _make_bot()
        bot.state = BotState.PRE_MARKET
        bot.circuit_breaker._active = True
        bot._handle_pre_market()
        assert bot.state == BotState.DONE_TODAY


class TestHandleOrbForming:
    @patch("src.bot.time.sleep")
    @patch("src.bot.time_utils")
    def test_no_trend_calls_pre_market(self, mock_time, mock_sleep):
        mock_time.is_orb_forming.return_value = True
        bot = _make_bot()
        bot.state = BotState.ORB_FORMING
        bot.trend = None

        with patch.object(bot, "_handle_pre_market") as mock_pm:
            bot._handle_orb_forming()
            mock_pm.assert_called_once()

    @patch("src.bot.time.sleep")
    @patch("src.bot.get_avg_daily_range", return_value=4.0)
    @patch("src.bot.get_intraday_bars")
    @patch("src.bot.time_utils")
    def test_orb_calculation_success(self, mock_time, mock_bars, mock_adr, mock_sleep):
        import pandas as pd
        mock_time.is_orb_forming.return_value = False

        # Create bars with ORB data
        idx = pd.date_range("2026-04-06 09:30", periods=6, freq="5min", tz=ET)
        bars = pd.DataFrame({
            "Open": [50, 51, 52, 53, 54, 55],
            "High": [52, 53, 54, 55, 56, 57],
            "Low":  [49, 50, 51, 52, 53, 54],
            "Close":[51, 52, 53, 54, 55, 56],
            "Volume":[1000]*6,
        }, index=idx)
        mock_bars.return_value = bars

        bot = _make_bot()
        bot.state = BotState.ORB_FORMING
        bot.trend = TrendState("bull", 500, 490, "TQQQ")

        bot._handle_orb_forming()

        assert bot.orb is not None
        assert bot.state == BotState.SCANNING

    @patch("src.bot.get_intraday_bars", return_value=None)
    @patch("src.bot.time_utils")
    def test_no_intraday_data(self, mock_time, mock_bars):
        mock_time.is_orb_forming.return_value = False
        bot = _make_bot()
        bot.state = BotState.ORB_FORMING
        bot.trend = TrendState("bull", 500, 490, "TQQQ")

        bot._handle_orb_forming()
        assert bot.state == BotState.DONE_TODAY


class TestRun:
    def test_run_catches_tick_exception(self):
        """run() should catch exceptions in _tick and continue."""
        bot = _make_bot()
        call_count = 0

        def mock_tick():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("test error")
            elif call_count == 2:
                raise KeyboardInterrupt()

        bot._tick = mock_tick
        with patch("src.bot.time.sleep"):
            bot.run()

        assert call_count == 2  # First tick errored, second raised KBI

    def test_run_handles_sigterm_via_system_exit(self):
        """run() should handle SystemExit from SIGTERM."""
        bot = _make_bot()

        def mock_tick():
            raise SystemExit(0)

        bot._tick = mock_tick
        bot.run()  # Should not raise


class TestSetupLogger:
    def test_logger_creates_handlers(self):
        """setup_logger creates console + file handlers."""
        from src.utils.logger import setup_logger
        import logging

        name = "test_casper_handlers_check"
        logger = logging.getLogger(name)
        logger.handlers.clear()

        # setup_logger will create file in project logs/app/
        result = setup_logger(name, "DEBUG")

        assert result.level == logging.DEBUG
        # Should have console handler + file handler = 2
        assert len(result.handlers) == 2
        handler_types = [type(h).__name__ for h in result.handlers]
        assert "StreamHandler" in handler_types
        assert "FileHandler" in handler_types

        # Cleanup
        for h in result.handlers[:]:
            h.close()
        result.handlers.clear()

    def test_idempotent(self):
        """Calling setup_logger twice returns same logger without adding handlers."""
        from src.utils.logger import setup_logger
        import logging

        name = "test_idempotent_logger_xyz"
        logger = logging.getLogger(name)
        logger.handlers.clear()

        l1 = setup_logger(name, "INFO")
        count = len(l1.handlers)
        l2 = setup_logger(name, "INFO")
        assert len(l2.handlers) == count
        assert l1 is l2

        # Cleanup
        for h in l1.handlers[:]:
            h.close()
        l1.handlers.clear()


import os
