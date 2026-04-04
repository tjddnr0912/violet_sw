"""Tests for position restore with broker verification + KIS order price fix.

Checklist:
[1] Restore discards stale state when broker has no holdings
[2] Restore adjusts shares when broker qty differs from state
[3] Restore proceeds when broker confirms holding
[4] Restore proceeds when API unavailable (fallback to state file)
[5] Restore handles missing state file gracefully
[6] buy_market uses current price (not zero)
[7] sell_market uses current price (not zero)
[8] buy/sell return None when price unavailable
[9] get_us_holdings parses response correctly
[10] get_us_holdings returns empty list when no positions
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock

from src.bot import CasperBot, BotState
from src.api.kis_client import KISClient
from src.api.kis_auth import KISAuth
from src.api.kis_order import KISOrder


def _make_bot(tmp_path):
    env = {
        "kis_app_key": "k", "kis_app_secret": "s", "kis_account_no": "12345678",
        "kis_account_product": "01", "kis_base_url": "",
        "telegram_bot_token": "", "telegram_chat_id": "",
        "trading_mode": "paper", "test_mode": False,
        "log_level": "WARNING", "timezone": "US/Eastern",
    }
    with patch("src.bot.load_trades", return_value=[]):
        with patch("src.bot.load_env", return_value=env):
            bot = CasperBot()
    bot._position_state_file = str(tmp_path / "pos_state.json")
    bot.position = None
    bot.state = BotState.WAITING
    return bot


def _write_state(path, symbol="TQQQ", shares=10):
    state = {
        "symbol": symbol, "direction": "long",
        "entry_price": 54.25, "stop_loss": 52.0, "take_profit": 58.75,
        "shares": shares, "risk_per_share": 2.25,
        "commission_rate": 0.0009, "entry_time": "09:55",
        "original_stop": 52.0, "be_stop_moved": False, "capital": 500.0,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f)


# ─── [1] Discard stale state ───

class TestRestoreDiscardStale:
    def test_no_holdings_clears_state(self, tmp_path):
        bot = _make_bot(tmp_path)
        _write_state(bot._position_state_file)

        bot.kis_client.get_us_holdings = MagicMock(return_value=[])

        bot._restore_position()

        assert bot.position is None
        assert bot.state == BotState.WAITING
        assert not os.path.exists(bot._position_state_file)


# ─── [2] Adjust shares ───

class TestRestoreAdjustShares:
    def test_broker_qty_differs(self, tmp_path):
        bot = _make_bot(tmp_path)
        _write_state(bot._position_state_file, shares=10)

        bot.kis_client.get_us_holdings = MagicMock(
            return_value=[{"symbol": "TQQQ", "qty": 7, "avg_price": 54.0}]
        )

        bot._restore_position()

        assert bot.position is not None
        assert bot.position.shares == 7  # Adjusted to broker


# ─── [3] Broker confirms ───

class TestRestoreConfirmed:
    def test_holding_matches(self, tmp_path):
        bot = _make_bot(tmp_path)
        _write_state(bot._position_state_file, shares=10)

        bot.kis_client.get_us_holdings = MagicMock(
            return_value=[{"symbol": "TQQQ", "qty": 10, "avg_price": 54.25}]
        )

        bot._restore_position()

        assert bot.position is not None
        assert bot.position.shares == 10
        assert bot.state == BotState.POSITION_OPEN


# ─── [4] API unavailable → fallback ───

class TestRestoreApiFallback:
    def test_api_returns_none(self, tmp_path):
        bot = _make_bot(tmp_path)
        _write_state(bot._position_state_file)

        bot.kis_client.get_us_holdings = MagicMock(return_value=None)

        bot._restore_position()

        # Should still restore from state file
        assert bot.position is not None
        assert bot.position.symbol == "TQQQ"
        assert bot.state == BotState.POSITION_OPEN


# ─── [5] No state file ───

class TestRestoreNoFile:
    def test_no_file(self, tmp_path):
        bot = _make_bot(tmp_path)
        bot._restore_position()
        assert bot.position is None


# ─── [6] buy_market uses price ───

class TestBuyMarketPrice:
    def test_sends_nonzero_price(self):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")
        order = KISOrder(client, "live")

        with patch.object(client, "get_us_price", return_value={"price": 55.0}):
            with patch.object(client, "_request", return_value={"output": {"ODNO": "1"}}) as mock_req:
                order.buy_market("TQQQ", 5)
                _, kwargs = mock_req.call_args
                price_sent = float(kwargs["json_body"]["OVRS_ORD_UNPR"])
                assert price_sent > 0  # Not zero
                assert price_sent > 55.0  # Above current (buy slippage)


# ─── [7] sell_market uses price ───

class TestSellMarketPrice:
    def test_sends_nonzero_price(self):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")
        order = KISOrder(client, "live")

        with patch.object(client, "get_us_price", return_value={"price": 55.0}):
            with patch.object(client, "_request", return_value={"output": {"ODNO": "1"}}) as mock_req:
                order.sell_market("TQQQ", 5)
                _, kwargs = mock_req.call_args
                price_sent = float(kwargs["json_body"]["OVRS_ORD_UNPR"])
                assert price_sent > 0
                assert price_sent < 55.0  # Below current (sell slippage)


# ─── [8] No price → None ───

class TestOrderNoPrice:
    def test_buy_fails_without_price(self):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")
        order = KISOrder(client, "live")

        with patch.object(client, "get_us_price", return_value=None):
            assert order.buy_market("TQQQ", 5) is None

    def test_sell_fails_without_price(self):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")
        order = KISOrder(client, "live")

        with patch.object(client, "get_us_price", return_value=None):
            assert order.sell_market("TQQQ", 5) is None


# ─── [9] get_us_holdings parses ───

class TestGetUsHoldings:
    @patch.object(KISClient, "_request")
    def test_parses_holdings(self, mock_req):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")

        mock_req.return_value = {
            "output1": [
                {"ovrs_pdno": "TQQQ", "ovrs_cblc_qty": "10", "pchs_avg_pric": "54.25"},
                {"ovrs_pdno": "SQQQ", "ovrs_cblc_qty": "0", "pchs_avg_pric": "0"},
            ]
        }
        result = client.get_us_holdings()
        assert result is not None
        assert len(result) == 1  # SQQQ qty=0 excluded
        assert result[0]["symbol"] == "TQQQ"
        assert result[0]["qty"] == 10


# ─── [10] Empty holdings ───

class TestGetUsHoldingsEmpty:
    @patch.object(KISClient, "_request")
    def test_no_positions(self, mock_req):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")

        mock_req.return_value = {"output1": []}
        result = client.get_us_holdings()
        assert result == []

    @patch.object(KISClient, "_request")
    def test_api_failure(self, mock_req):
        auth = MagicMock(spec=KISAuth)
        auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                        "content-type": "application/json; charset=utf-8"}
        auth.base_url = "https://test.api.com"
        client = KISClient(auth, "12345678")

        mock_req.return_value = None
        assert client.get_us_holdings() is None
