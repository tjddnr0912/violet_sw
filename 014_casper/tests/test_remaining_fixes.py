"""Tests for remaining fix items: M-1, M-2, M-6, M-7, M-8, L-2, L-4, L-5."""

import json
import os
import pytest
from datetime import datetime, date, time as dtime
from unittest.mock import patch, MagicMock
import pytz

from src.utils.time_utils import (
    is_weekday, is_trading_day, is_market_open, _load_holidays,
    now_kst, today_et, get_week_number, ET, KST,
)
from src.core.position import Position, create_position
from src.core.risk import CircuitBreaker
from src.data.market_data import _yf_with_timeout
from src.utils.config import reset_config_cache


# ─── M-1: US Holiday Recognition ───

class TestUSHolidays:
    def test_holiday_is_not_trading_day(self, tmp_path):
        holidays_file = tmp_path / "us_holidays.json"
        holidays_file.write_text(json.dumps({
            "2026": ["2026-04-06"]
        }))
        import src.utils.time_utils as tu
        old_file = tu._HOLIDAYS_FILE
        old_holidays = tu._us_holidays
        tu._HOLIDAYS_FILE = str(holidays_file)
        tu._us_holidays = set()  # Reset cache

        try:
            # Monday April 6, 2026 10:00 ET — holiday
            mock_dt = ET.localize(datetime(2026, 4, 6, 10, 0))
            with patch("src.utils.time_utils.now_et", return_value=mock_dt):
                assert is_trading_day() is False
                assert is_weekday() is False  # is_weekday now uses is_trading_day
                assert is_market_open() is False
        finally:
            tu._HOLIDAYS_FILE = old_file
            tu._us_holidays = old_holidays

    def test_normal_weekday_is_trading_day(self, tmp_path):
        holidays_file = tmp_path / "us_holidays.json"
        holidays_file.write_text(json.dumps({"2026": ["2026-12-25"]}))
        import src.utils.time_utils as tu
        old_file = tu._HOLIDAYS_FILE
        old_holidays = tu._us_holidays
        tu._HOLIDAYS_FILE = str(holidays_file)
        tu._us_holidays = set()

        try:
            mock_dt = ET.localize(datetime(2026, 4, 7, 10, 0))  # Tuesday
            with patch("src.utils.time_utils.now_et", return_value=mock_dt):
                assert is_trading_day() is True
        finally:
            tu._HOLIDAYS_FILE = old_file
            tu._us_holidays = old_holidays

    def test_missing_holidays_file_falls_back(self):
        import src.utils.time_utils as tu
        old_file = tu._HOLIDAYS_FILE
        old_holidays = tu._us_holidays
        tu._HOLIDAYS_FILE = "/nonexistent/path.json"
        tu._us_holidays = set()

        try:
            mock_dt = ET.localize(datetime(2026, 4, 6, 10, 0))  # Monday
            with patch("src.utils.time_utils.now_et", return_value=mock_dt):
                assert is_trading_day() is True  # No holidays loaded → weekday only
        finally:
            tu._HOLIDAYS_FILE = old_file
            tu._us_holidays = old_holidays


# ─── M-2: yfinance timeout wrapper ───

class TestYfTimeout:
    def test_normal_call_works(self):
        result = _yf_with_timeout(lambda: 42)
        assert result == 42

    def test_timeout_raises(self):
        import time as time_mod
        def slow():
            time_mod.sleep(3)
            return 1

        from concurrent.futures import TimeoutError as FT
        from src.data import market_data
        old_timeout = market_data._YF_TIMEOUT
        market_data._YF_TIMEOUT = 0.2  # 200ms timeout

        try:
            with pytest.raises(FT):
                _yf_with_timeout(slow)
        finally:
            market_data._YF_TIMEOUT = old_timeout


# ─── M-6: Position size cap ───

class TestPositionSizeCap:
    @patch("src.bot.load_trades", return_value=[])
    @patch("src.bot.load_env", return_value={
        "kis_app_key": "", "kis_app_secret": "", "kis_account_no": "",
        "kis_account_product": "01", "kis_base_url": "",
        "telegram_bot_token": "", "telegram_chat_id": "",
        "trading_mode": "paper", "test_mode": False,
        "log_level": "WARNING", "timezone": "US/Eastern",
    })
    def test_shares_capped_by_max_shares(self, mock_env, mock_trades, tmp_path):
        from src.bot import CasperBot
        from src.core.orb import OpeningRange
        from src.core.fvg import FairValueGap
        from src.core.strategy import TradeSignal

        bot = CasperBot()
        bot._position_state_file = str(tmp_path / "pos.json")
        bot.capital = 100000  # Large capital
        bot.test_mode = False

        orb = OpeningRange(high=54, low=50, range_size=4, date="2026-04-06")
        fvg = FairValueGap(top=55, bottom=53.5, size=1.5, timestamp="")
        bot.signal = TradeSignal(
            symbol="TQQQ", direction="long",
            entry_price=50.0, stop_loss=48.0, take_profit=54.0,
            risk_per_share=2.0, rr_ratio=2.0, fvg=fvg, orb=orb,
            signal_time="",
        )

        with patch("src.bot.get_current_price", return_value=50.0):
            bot._execute_entry()

        # 100000/50 = 2000 shares, but capped at max_shares=200
        assert bot.position is not None
        assert bot.position.shares <= 200


# ─── M-7: Weekly loss uses week-start capital ───

class TestWeeklyLossCapital:
    def test_uses_week_start_capital(self):
        cb = CircuitBreaker(max_consecutive_losses=10, max_weekly_loss_pct=3.0)
        cb.reset_if_new_week(14, capital=1000.0)

        # Lose $25 from 1000 starting capital → 2.5% < 3% → not active
        cb.record_trade("LOSS", -25, 975)
        assert cb.is_active is False

        # Lose another $6 → total $31 → 3.1% of 1000 → active
        cb.record_trade("LOSS", -6, 969)
        assert cb.is_active is True

    def test_fallback_to_current_capital_when_no_start(self):
        cb = CircuitBreaker(max_consecutive_losses=10, max_weekly_loss_pct=3.0)
        cb.reset_if_new_week(14)  # No capital → _week_start_capital=0

        # Falls back to current capital
        cb.record_trade("LOSS", -31, 1000)
        assert cb.is_active is True


# ─── M-8: max_trades_per_day enforcement ───

class TestMaxTradesPerDay:
    @patch("src.bot.load_trades", return_value=[])
    @patch("src.bot.load_env", return_value={
        "kis_app_key": "", "kis_app_secret": "", "kis_account_no": "",
        "kis_account_product": "01", "kis_base_url": "",
        "telegram_bot_token": "", "telegram_chat_id": "",
        "trading_mode": "paper", "test_mode": False,
        "log_level": "WARNING", "timezone": "US/Eastern",
    })
    def test_blocks_after_max_trades(self, mock_env, mock_trades, tmp_path):
        from src.bot import CasperBot, BotState
        from src.core.orb import OpeningRange
        from src.core.fvg import FairValueGap
        from src.core.strategy import TradeSignal

        bot = CasperBot()
        bot._position_state_file = str(tmp_path / "pos.json")
        bot.trades_today = 1  # Already traded once
        bot.capital = 1500

        orb = OpeningRange(high=54, low=50, range_size=4, date="")
        fvg = FairValueGap(top=55, bottom=53.5, size=1.5, timestamp="")
        bot.signal = TradeSignal(
            symbol="TQQQ", direction="long",
            entry_price=54.25, stop_loss=52.0, take_profit=58.75,
            risk_per_share=2.25, rr_ratio=2.0, fvg=fvg, orb=orb,
            signal_time="",
        )

        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()

        assert bot.state == BotState.DONE_TODAY
        assert bot.position is None


# ─── L-2: Accurate BE price formula ───

class TestBreakevenPriceFormula:
    def test_be_price_covers_round_trip_commission(self):
        """Verify that selling at breakeven price produces zero or slightly positive net PnL."""
        from src.core.position import create_position, close_position
        from src.core.orb import OpeningRange
        from src.core.fvg import FairValueGap
        from src.core.strategy import TradeSignal

        orb = OpeningRange(high=54, low=50, range_size=4, date="")
        fvg = FairValueGap(top=55, bottom=53.5, size=1.5, timestamp="")
        signal = TradeSignal(
            symbol="TQQQ", direction="long",
            entry_price=50.0, stop_loss=48.0, take_profit=54.0,
            risk_per_share=2.0, rr_ratio=2.0, fvg=fvg, orb=orb,
            signal_time="",
        )
        pos = create_position(signal, shares=100, commission_rate=0.0009, entry_time="10:00")
        be = pos.breakeven_price

        # Close at breakeven price
        close_position(pos, be, "be_stop", "11:00")

        # Net PnL should be approximately zero (within rounding)
        assert abs(pos.net_pnl) < 0.02, f"net_pnl={pos.net_pnl} should be ~0 at BE price"


# ─── L-5: config cache reset ───

class TestConfigCacheReset:
    def test_reset_clears_cache(self):
        import src.utils.config as cfg
        cfg._config_cache = {"test": True}
        reset_config_cache()
        assert cfg._config_cache == {}


# ─── Untested time_utils wrappers ───

class TestTimeUtilWrappers:
    @patch("src.utils.time_utils.now_et")
    def test_now_kst(self, mock_now):
        # now_kst uses its own datetime.now(KST), not now_et
        result = now_kst()
        assert result.tzinfo is not None

    @patch("src.utils.time_utils.now_et")
    def test_today_et(self, mock_now):
        mock_now.return_value = ET.localize(datetime(2026, 4, 6, 10, 0))
        result = today_et()
        assert result == date(2026, 4, 6)

    @patch("src.utils.time_utils.now_et")
    def test_get_week_number(self, mock_now):
        mock_now.return_value = ET.localize(datetime(2026, 4, 6, 10, 0))
        wn = get_week_number()
        assert isinstance(wn, int)
        assert 1 <= wn <= 53
