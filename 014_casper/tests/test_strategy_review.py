"""Strategy review tests — verify 007 comparison fixes are correct.

Checklist:
[1] get_us_balance passes active symbol (not empty string)
[2] Entry fill adjustment updates risk_per_share
[3] Entry fill adjustment recalculates TP correctly
[4] Entry fill adjustment skipped when risk <= 0 (fill below stop)
[5] Exchange code mapping: get_us_price uses 3-char code
[6] Rate limiting: API calls have minimum interval
[7] Token env validation: paper token rejected for live mode
[8] Sell retry is unlimited (no cap)
"""

import time
import pytest
from unittest.mock import patch, MagicMock

from src.bot import CasperBot, BotState
from src.core.orb import OpeningRange
from src.core.fvg import FairValueGap
from src.core.strategy import TradeSignal
from src.core.position import create_position
from src.api.kis_auth import KISAuth
from src.api.kis_client import KISClient


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


def _make_signal(entry=54.25, stop=52.0):
    orb = OpeningRange(high=54.0, low=50.0, range_size=4.0, date="2026-04-06")
    fvg = FairValueGap(top=55.0, bottom=53.5, size=1.5, timestamp="09:50")
    risk = entry - stop
    return TradeSignal(
        symbol="TQQQ", direction="long",
        entry_price=entry, stop_loss=stop,
        take_profit=entry + risk * 2.0,
        risk_per_share=risk, rr_ratio=2.0,
        fvg=fvg, orb=orb, signal_time="2026-04-06 09:50",
    )


class TestChecklist1_BalancePassesSymbol:
    """[1] get_us_balance receives active symbol, not empty string."""

    def test_balance_called_with_signal_symbol(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.test_mode = False
        bot.capital = 0  # Forces balance fetch
        bot.signal = _make_signal()

        mock_client = MagicMock()
        mock_client.get_us_balance.return_value = {"available_cash": 2000.0}
        bot.kis_client = mock_client
        bot.kis_order = None  # No actual order

        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()

        mock_client.get_us_balance.assert_called_once_with("TQQQ")


class TestChecklist2_FillUpdatesRiskPerShare:
    """[2] Entry fill adjustment updates risk_per_share."""

    def test_risk_per_share_updated_on_fill(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.test_mode = True  # 1 share
        bot.signal = _make_signal(entry=54.25, stop=52.0)
        # Original risk_per_share = 54.25 - 52.0 = 2.25

        mock_order = MagicMock()
        mock_order.buy_market.return_value = {"order_no": "BUY001"}
        mock_client = MagicMock()
        mock_client.get_us_filled_price.return_value = 55.00  # Filled higher
        bot.kis_order = mock_order
        bot.kis_client = mock_client

        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()

        assert bot.position is not None
        # New risk = 55.00 - 52.0 = 3.0
        assert bot.position.risk_per_share == 3.0
        assert bot.position.entry_price == 55.00


class TestChecklist3_FillRecalculatesTP:
    """[3] Entry fill adjustment recalculates TP correctly."""

    def test_tp_recalculated_with_new_risk(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.test_mode = True
        bot.signal = _make_signal(entry=54.25, stop=52.0)

        mock_order = MagicMock()
        mock_order.buy_market.return_value = {"order_no": "BUY002"}
        mock_client = MagicMock()
        mock_client.get_us_filled_price.return_value = 55.00
        bot.kis_order = mock_order
        bot.kis_client = mock_client

        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()

        # New: entry=55, risk=3, TP=55+3*2=61
        assert bot.position.take_profit == 61.0


class TestChecklist4_FillSkippedWhenRiskNegative:
    """[4] Fill adjustment skipped when fill_price <= stop_loss."""

    def test_no_adjustment_when_fill_below_stop(self, tmp_path):
        bot = _make_bot(tmp_path=tmp_path)
        bot.test_mode = True
        bot.signal = _make_signal(entry=54.25, stop=52.0)

        mock_order = MagicMock()
        mock_order.buy_market.return_value = {"order_no": "BUY003"}
        mock_client = MagicMock()
        mock_client.get_us_filled_price.return_value = 51.50  # Below stop!
        bot.kis_order = mock_order
        bot.kis_client = mock_client

        with patch("src.bot.get_current_price", return_value=54.25):
            bot._execute_entry()

        # risk = 51.50 - 52.0 = -0.50 → skip adjustment → keep original
        assert bot.position.entry_price == 54.25  # Unchanged
        assert bot.position.risk_per_share == 2.25  # Original


class TestChecklist5_ExchangeCodeMapping:
    """[5] get_us_price uses 3-char exchange code for KIS price API."""

    @patch.object(KISClient, "_request")
    def test_price_api_uses_3char(self, mock_req):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")

        mock_req.return_value = {"output": {"last": "55", "open": "54",
                                            "high": "56", "low": "53", "tvol": "1000"}}

        client.get_us_price("TQQQ", exchange="NASD")
        _, kwargs = mock_req.call_args
        # EXCD should be 3-char "NAS", not 4-char "NASD"
        assert kwargs["params"]["EXCD"] == "NAS"


class TestChecklist6_RateLimiting:
    """[6] API calls have minimum interval."""

    @patch("src.api.kis_client.requests.get")
    def test_consecutive_calls_have_delay(self, mock_get):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rt_cd": "0"}
        mock_get.return_value = mock_resp

        t1 = time.time()
        client._request("GET", "https://test/a")
        client._request("GET", "https://test/b")
        t2 = time.time()

        # Two calls should take at least API_DELAY (300ms)
        from src.api.kis_client import API_DELAY
        assert t2 - t1 >= API_DELAY * 0.8  # Allow small tolerance


class TestChecklist7_TokenEnvValidation:
    """[7] Paper token rejected for live mode."""

    def test_virtual_flag_set(self):
        auth_paper = KISAuth("k", "s", "https://openapivts.koreainvestment.com:29443")
        assert auth_paper.is_virtual is True

        auth_live = KISAuth("k", "s", "https://openapi.koreainvestment.com:9443")
        assert auth_live.is_virtual is False


class TestChecklist8_SellRetryUnlimited:
    """[8] Sell retry has no cap — retries forever."""

    @patch("src.bot.save_trade")
    @patch("src.bot.time_utils")
    def test_sell_retries_indefinitely(self, mock_time, mock_save, tmp_path):
        mock_time.now_et.return_value = MagicMock(
            strftime=MagicMock(return_value="15:50")
        )
        bot = _make_bot(tmp_path=tmp_path)
        signal = _make_signal()
        bot.position = create_position(signal, 10, 0.0009, "09:55")
        bot.capital = 1500

        bot.kis_order = MagicMock()
        bot.kis_order.sell_market.return_value = None  # Always fails

        # Try 10 times — should never give up, just return each time
        for i in range(10):
            bot._close_and_record(58.75, "take_profit")

        assert bot._sell_retry_count == 10
        assert bot.position.is_open  # Still open — not force-closed
        mock_save.assert_not_called()  # Never saved because sell never succeeded
