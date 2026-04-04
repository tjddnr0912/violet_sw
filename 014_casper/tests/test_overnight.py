"""Tests for overnight position protection and Gemini review fixes.

Checklist:
[1] _reset_day preserves unclosed position (O-3)
[2] _reset_day clears normally when no position (O-3)
[3] After-hours detection triggers limit sell attempt (O-1)
[4] Next-day open triggers immediate close (O-2)
[5] Exception sleep is 5s during POSITION_OPEN (G-5)
[6] Exception sleep is 30s during other states (G-5)
[7] ORB data failure retries once before DONE_TODAY (G-8)
[8] Fill price polling uses 5 attempts (G-6)
"""

import pytest
from datetime import datetime, time as dtime
from unittest.mock import patch, MagicMock, call
import pytz

from src.bot import CasperBot, BotState
from src.core.orb import OpeningRange
from src.core.fvg import FairValueGap
from src.core.strategy import TradeSignal
from src.core.position import create_position
from src.api.kis_client import KISClient
from src.api.kis_auth import KISAuth

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
        bot._position_state_file = str(tmp_path / "pos.json")
    return bot


def _make_signal():
    orb = OpeningRange(high=54.0, low=50.0, range_size=4.0, date="2026-04-06")
    fvg = FairValueGap(top=55.0, bottom=53.5, size=1.5, timestamp="09:50")
    return TradeSignal(
        symbol="TQQQ", direction="long",
        entry_price=54.25, stop_loss=52.0, take_profit=58.75,
        risk_per_share=2.25, rr_ratio=2.0, fvg=fvg, orb=orb,
        signal_time="2026-04-06 09:50",
    )


def _make_position():
    signal = _make_signal()
    return create_position(signal, 10, 0.0009, "09:55")


# ─── [1] _reset_day preserves unclosed position ───

class TestResetDayPreservesPosition:
    def test_unclosed_position_preserved(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.position = _make_position()
        bot.capital = 1500
        bot.state = BotState.POSITION_OPEN
        bot.today_date = "2026-04-06"

        bot._reset_day("2026-04-07")

        assert bot.position is not None
        assert bot.position.is_open
        assert bot.state == BotState.POSITION_OPEN
        assert bot.today_date == "2026-04-07"

    # ─── [2] Normal reset when no position ───

    def test_normal_reset_without_position(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.position = None
        bot.state = BotState.DONE_TODAY
        bot.today_date = "2026-04-06"

        bot._reset_day("2026-04-07")

        assert bot.position is None
        assert bot.state == BotState.WAITING

    def test_closed_position_resets_normally(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        pos = _make_position()
        pos.exit_price = 58.75
        pos.exit_reason = "take_profit"
        bot.position = pos  # Closed position
        bot.state = BotState.DONE_TODAY

        bot._reset_day("2026-04-07")

        assert bot.position is None  # Reset
        assert bot.state == BotState.WAITING


# ─── [3] After-hours triggers sell attempt ───

class TestAfterHoursSell:
    @patch("src.bot.time.sleep")
    @patch("src.bot.time_utils")
    @patch("src.bot.get_current_price", return_value=55.0)
    def test_after_hours_attempts_close(self, mock_price, mock_time, mock_sleep, tmp_path):
        mock_time.is_next_day_open.return_value = False
        mock_time.is_after_hours.return_value = True
        mock_time.is_weekday.return_value = True
        mock_time.now_et.return_value = MagicMock(strftime=MagicMock(return_value="16:30"))

        bot = _make_bot(tmp_path=tmp_path)
        bot.position = _make_position()
        bot.capital = 1500
        bot.state = BotState.POSITION_OPEN

        with patch("src.bot.save_trade"):
            bot._handle_position_open()

        # Should attempt to close
        assert not bot.position.is_open or bot.state == BotState.DONE_TODAY


# ─── [4] Next-day open triggers immediate close ───

class TestNextDayOpenClose:
    @patch("src.bot.time_utils")
    @patch("src.bot.get_current_price", return_value=53.0)
    def test_overnight_close_at_open(self, mock_price, mock_time, tmp_path):
        mock_time.is_next_day_open.return_value = True
        mock_time.now_et.return_value = MagicMock(strftime=MagicMock(return_value="09:31"))
        mock_time.get_week_number.return_value = 15

        bot = _make_bot(tmp_path=tmp_path)
        bot.position = _make_position()
        bot.capital = 1500
        bot.state = BotState.POSITION_OPEN

        with patch("src.bot.save_trade"):
            bot._handle_position_open()

        assert not bot.position.is_open
        assert bot.position.exit_reason == "overnight_force"


# ─── [5] Exception sleep 5s during POSITION_OPEN ───

class TestExceptionSleep:
    def test_short_sleep_during_position(self):
        bot = _make_bot()
        bot.state = BotState.POSITION_OPEN
        bot.position = _make_position()

        tick_count = 0
        def failing_tick():
            nonlocal tick_count
            tick_count += 1
            if tick_count == 1:
                raise ValueError("test")
            raise KeyboardInterrupt()

        bot._tick = failing_tick
        with patch("src.bot.time.sleep") as mock_sleep:
            bot.run()
            # First exception → sleep should be 5 (not 30)
            mock_sleep.assert_called_with(5)

    # ─── [6] Normal sleep during other states ───

    def test_normal_sleep_during_waiting(self):
        bot = _make_bot()
        bot.state = BotState.WAITING

        tick_count = 0
        def failing_tick():
            nonlocal tick_count
            tick_count += 1
            if tick_count == 1:
                raise ValueError("test")
            raise KeyboardInterrupt()

        bot._tick = failing_tick
        with patch("src.bot.time.sleep") as mock_sleep:
            bot.run()
            mock_sleep.assert_called_with(30)


# ─── [7] ORB data retry ───

class TestOrbRetry:
    @patch("src.bot.time.sleep")
    @patch("src.bot.get_avg_daily_range", return_value=4.0)
    @patch("src.bot.get_intraday_bars")
    @patch("src.bot.time_utils")
    def test_retries_once_on_failure(self, mock_time, mock_bars, mock_adr, mock_sleep):
        import pandas as pd
        mock_time.is_orb_forming.return_value = False

        # First call fails, second succeeds
        idx = pd.date_range("2026-04-06 09:30", periods=6, freq="5min", tz=ET)
        good_bars = pd.DataFrame({
            "Open": [50]*6, "High": [54]*6, "Low": [49]*6,
            "Close": [52]*6, "Volume": [1000]*6,
        }, index=idx)
        mock_bars.side_effect = [None, good_bars]

        from src.core.risk import TrendState
        bot = _make_bot()
        bot.state = BotState.ORB_FORMING
        bot.trend = TrendState("bull", 500, 490, "TQQQ")

        bot._handle_orb_forming()

        assert mock_bars.call_count == 2  # Called twice (retry)
        assert bot.orb is not None
        assert bot.state == BotState.SCANNING

    @patch("src.bot.time.sleep")
    @patch("src.bot.get_intraday_bars", return_value=None)
    @patch("src.bot.time_utils")
    def test_done_after_both_fail(self, mock_time, mock_bars, mock_sleep):
        mock_time.is_orb_forming.return_value = False

        from src.core.risk import TrendState
        bot = _make_bot()
        bot.state = BotState.ORB_FORMING
        bot.trend = TrendState("bull", 500, 490, "TQQQ")

        bot._handle_orb_forming()

        assert mock_bars.call_count == 2  # Tried twice
        assert bot.state == BotState.DONE_TODAY


# ─── [8] Fill price polling 5 attempts ───

class TestFillPricePolling:
    @patch.object(KISClient, "_request")
    def test_polls_5_times(self, mock_req):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")

        # Return empty output every time → should poll 5 times
        mock_req.return_value = {"output": []}

        result = client.get_us_filled_price("ORDER123", "TQQQ")
        assert result is None
        assert mock_req.call_count == 5
