"""Tests for CasperBot state machine handlers."""

import json
import os
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from src.bot import CasperBot, BotState
from src.core.risk import TrendState
from src.core.orb import OpeningRange
from src.core.fvg import FairValueGap
from src.core.strategy import TradeSignal
from src.core.position import Position, create_position


def _make_bot(mock_env=None, tmp_path=None):
    """Create a CasperBot with mocked dependencies."""
    env = mock_env or {
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


def _make_signal():
    """Create a test TradeSignal."""
    orb = OpeningRange(high=54.0, low=50.0, range_size=4.0, date="2026-04-06")
    fvg = FairValueGap(top=55.0, bottom=53.5, size=1.5, timestamp="09:50")
    return TradeSignal(
        symbol="TQQQ", direction="long",
        entry_price=54.25, stop_loss=52.0, take_profit=58.75,
        risk_per_share=2.25, rr_ratio=2.0, fvg=fvg, orb=orb,
        signal_time="2026-04-06 09:50",
    )


class TestTransition:
    def test_transition_changes_state(self):
        bot = _make_bot()
        bot._transition(BotState.PRE_MARKET, "test")
        assert bot.state == BotState.PRE_MARKET

    def test_transition_logs_reason(self):
        bot = _make_bot()
        bot._transition(BotState.DONE_TODAY, "CB active")
        assert bot.state == BotState.DONE_TODAY


class TestResetDay:
    def test_resets_all_state(self):
        bot = _make_bot()
        bot.trend = TrendState("bull", 500, 490, "TQQQ")
        bot.orb = OpeningRange(54, 50, 4, "2026-04-06")
        bot.position = None  # No open position → normal reset
        bot.state = BotState.DONE_TODAY
        bot._done_today_logged = True

        bot._reset_day("2026-04-07")
        assert bot.today_date == "2026-04-07"
        assert bot.trend is None
        assert bot.orb is None
        assert bot.position is None
        assert bot.state == BotState.WAITING
        assert bot._done_today_logged is False


class TestHandleWaiting:
    @patch("src.bot.time_utils")
    def test_weekend_sleeps(self, mock_time):
        mock_time.is_weekday.return_value = False
        bot = _make_bot()
        with patch("src.bot.time.sleep") as mock_sleep:
            bot._handle_waiting()
            mock_sleep.assert_called_with(300)

    @patch("src.bot.time_utils")
    def test_transitions_to_pre_market(self, mock_time):
        mock_time.is_weekday.return_value = True
        mock_time.is_pre_market.return_value = True
        bot = _make_bot()
        bot._handle_waiting()
        assert bot.state == BotState.PRE_MARKET

    @patch("src.bot.time_utils")
    def test_transitions_to_orb_forming(self, mock_time):
        mock_time.is_weekday.return_value = True
        mock_time.is_pre_market.return_value = False
        mock_time.is_orb_forming.return_value = True
        bot = _make_bot()
        bot._handle_waiting()
        assert bot.state == BotState.ORB_FORMING


class TestHandleScanning:
    @patch("src.bot.time_utils")
    def test_no_trend_goes_to_done(self, mock_time):
        mock_time.is_scan_window.return_value = True
        bot = _make_bot()
        bot.state = BotState.SCANNING
        bot.trend = None
        bot._handle_scanning()
        assert bot.state == BotState.DONE_TODAY

    @patch("src.bot.time_utils")
    def test_scan_window_closed(self, mock_time):
        mock_time.is_scan_window.return_value = False
        bot = _make_bot()
        bot.state = BotState.SCANNING
        bot.trend = TrendState("bull", 500, 490, "TQQQ")
        bot._handle_scanning()
        assert bot.state == BotState.DONE_TODAY


class TestExecuteEntry:
    def test_test_mode_one_share(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.test_mode = True
        bot.signal = _make_signal()
        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()
        assert bot.position is not None
        assert bot.position.shares == 1
        assert bot.state == BotState.POSITION_OPEN

    def test_insufficient_capital(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.test_mode = False
        bot.capital = 10.0  # Not enough
        bot.signal = _make_signal()
        bot.signal = TradeSignal(
            symbol="TQQQ", direction="long",
            entry_price=54.25, stop_loss=52.0, take_profit=58.75,
            risk_per_share=2.25, rr_ratio=2.0,
            fvg=FairValueGap(top=55, bottom=53.5, size=1.5, timestamp=""),
            orb=OpeningRange(high=54, low=50, range_size=4, date=""),
            signal_time="",
        )
        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()
        assert bot.state == BotState.DONE_TODAY  # Insufficient capital

    def test_price_zero_uses_signal_price(self, tmp_path):
        """When get_current_price returns 0 (falsy), signal entry_price is used."""
        bot = _make_bot(tmp_path=tmp_path)
        bot.test_mode = False
        bot.capital = 1500
        bot.signal = _make_signal()  # entry_price=54.25
        with patch("src.bot.get_current_price", return_value=0):
            bot._execute_entry()
        # 0 is falsy → price stays as signal.entry_price (54.25)
        # shares = int(1500/54.25) = 27 → proceeds normally
        assert bot.position is not None
        assert bot.state == BotState.POSITION_OPEN


class TestHandlePositionOpen:
    def test_no_position_goes_to_done(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.state = BotState.POSITION_OPEN
        bot.position = None
        bot._handle_position_open()
        assert bot.state == BotState.DONE_TODAY

    @patch("src.bot.time_utils")
    @patch("src.bot.get_current_price", return_value=59.0)
    def test_take_profit_exit(self, mock_price, mock_time, tmp_path):
        mock_time.is_next_day_open.return_value = False
        mock_time.is_after_hours.return_value = False
        mock_time.is_past_be_time.return_value = False
        mock_time.is_force_close_time.return_value = False
        mock_time.now_et.return_value = MagicMock(
            strftime=MagicMock(return_value="10:30")
        )

        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:55")
        bot.capital = 1500
        bot.state = BotState.POSITION_OPEN
        # Force TP: high >= take_profit
        with patch("src.bot.get_current_price", return_value=bot.position.take_profit + 1):
            with patch("src.bot.save_trade"):
                bot._handle_position_open()
        assert bot.state == BotState.DONE_TODAY
        assert bot.position.result == "WIN"


class TestCloseAndRecord:
    @patch("src.bot.save_trade")
    @patch("src.bot.time_utils")
    def test_records_trade(self, mock_time, mock_save, tmp_path):
        mock_time.now_et.return_value = MagicMock(
            strftime=MagicMock(return_value="10:30")
        )
        mock_time.get_week_number.return_value = 14

        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:55")
        bot.capital = 1500

        bot._close_and_record(58.75, "take_profit")
        mock_save.assert_called_once()
        trade = mock_save.call_args[0][0]
        assert trade["result"] == "WIN"
        assert trade["capital_after"] is not None


class TestCloseAndRecordWithKIS:
    """Test fill price query after sell order."""

    @patch("src.bot.save_trade")
    @patch("src.bot.time_utils")
    def test_uses_fill_price_when_available(self, mock_time, mock_save, tmp_path):
        mock_time.now_et.return_value = MagicMock(
            strftime=MagicMock(return_value="10:30")
        )
        mock_time.get_week_number.return_value = 14

        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:55")
        bot.capital = 1500

        # Mock KIS order + client
        bot.kis_order = MagicMock()
        bot.kis_order.sell_market.return_value = {"order_no": "ORD123"}
        bot.kis_client = MagicMock()
        bot.kis_client.get_us_filled_price.return_value = 59.50  # Actual fill

        bot._close_and_record(58.75, "take_profit")  # Initial price estimate

        # Position should be closed at fill price, not the estimate
        assert bot.position.exit_price == 59.50
        mock_save.assert_called_once()

    @patch("src.bot.save_trade")
    @patch("src.bot.time_utils")
    def test_falls_back_when_fill_not_found(self, mock_time, mock_save, tmp_path):
        mock_time.now_et.return_value = MagicMock(
            strftime=MagicMock(return_value="10:30")
        )
        mock_time.get_week_number.return_value = 14

        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:55")
        bot.capital = 1500

        bot.kis_order = MagicMock()
        bot.kis_order.sell_market.return_value = {"order_no": "ORD456"}
        bot.kis_client = MagicMock()
        bot.kis_client.get_us_filled_price.return_value = None  # Not found

        bot._close_and_record(58.75, "take_profit")

        # Falls back to the estimated price
        assert bot.position.exit_price == 58.75


class TestDoneToday:
    @patch("src.bot.load_trades", return_value=[])
    def test_logs_only_once(self, mock_load):
        bot = _make_bot()
        bot.state = BotState.DONE_TODAY
        with patch("src.bot.time.sleep"):
            bot._handle_done_today()
            assert bot._done_today_logged is True
            bot._handle_done_today()
            # load_trades called only once (in first call)
            assert mock_load.call_count == 1


class TestPositionStatePersistence:
    def test_save_and_restore(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:55")
        bot.capital = 1500

        bot._save_position_state()
        assert os.path.exists(bot._position_state_file)

        # New bot instance restores position
        bot2 = _make_bot(tmp_path=tmp_path)
        bot2._position_state_file = bot._position_state_file
        bot2._restore_position()
        assert bot2.position is not None
        assert bot2.position.symbol == "TQQQ"
        assert bot2.position.entry_price == 54.25
        assert bot2.state == BotState.POSITION_OPEN

    def test_clear_position_state(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:55")
        bot._save_position_state()
        assert os.path.exists(bot._position_state_file)

        bot._clear_position_state()
        assert not os.path.exists(bot._position_state_file)

    def test_no_file_no_restore(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot._restore_position()
        assert bot.position is None

    def test_corrupt_file_handled(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        state_file = tmp_path / "pos_state.json"
        state_file.write_text("not json{{{")
        bot._position_state_file = str(state_file)
        bot._restore_position()  # Should not crash
        assert bot.position is None


class TestPartialFill:
    def test_partial_fill_retries_sell(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:50")
        bot.capital = 1000.0
        bot.trades_today = 0

        mock_order = MagicMock()
        mock_order.sell_market.return_value = {"order_no": "S001"}
        bot.kis_order = mock_order

        mock_client = MagicMock()
        mock_client.get_us_holdings.return_value = [
            {"symbol": "TQQQ", "qty": 3, "avg_price": 54.0}
        ]
        mock_client.get_us_filled_price.return_value = None
        mock_client.get_us_today_executions.return_value = []
        bot.kis_client = mock_client

        with patch("src.bot.load_trades", return_value=[]):
            bot._close_and_record(55.0, "take_profit")

        assert mock_order.sell_market.call_count == 2
        retry_call = mock_order.sell_market.call_args_list[1]
        assert retry_call[0] == ("TQQQ", 3)

    def test_full_fill_no_retry(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:50")
        bot.capital = 1000.0

        mock_order = MagicMock()
        mock_order.sell_market.return_value = {"order_no": "S002"}
        bot.kis_order = mock_order

        mock_client = MagicMock()
        mock_client.get_us_holdings.return_value = []
        mock_client.get_us_filled_price.return_value = None
        mock_client.get_us_today_executions.return_value = []
        bot.kis_client = mock_client

        with patch("src.bot.load_trades", return_value=[]):
            bot._close_and_record(55.0, "take_profit")

        assert mock_order.sell_market.call_count == 1


class TestCapitalFallback:
    def test_capital_zero_skips_trade(self, tmp_path):
        """When capital sync fails, bot should skip — not use $1500 default."""
        bot = _make_bot(tmp_path=tmp_path)
        bot.signal = _make_signal()
        bot.capital = 0.0
        bot.test_mode = False
        bot.trades_today = 0
        bot.kis_client = MagicMock()
        bot.kis_client.get_us_balance.return_value = None

        bot._execute_entry()

        assert bot.state == BotState.DONE_TODAY
        assert bot.position is None

    def test_capital_positive_proceeds(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.signal = _make_signal()
        bot.capital = 5000.0
        bot.test_mode = False
        bot.trades_today = 0
        bot.kis_order = None
        bot.kis_client = None

        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()

        assert bot.position is not None
        assert bot.state == BotState.POSITION_OPEN
