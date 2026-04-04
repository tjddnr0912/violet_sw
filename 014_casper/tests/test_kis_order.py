"""Tests for KIS order execution module."""

import pytest
from unittest.mock import MagicMock, patch

from src.api.kis_order import KISOrder
from src.api.kis_client import KISClient
from src.api.kis_auth import KISAuth


@pytest.fixture
def mock_client():
    """Create a mock KISClient."""
    auth = MagicMock(spec=KISAuth)
    auth.headers = {"authorization": "Bearer test", "appkey": "k", "appsecret": "s",
                    "content-type": "application/json; charset=utf-8"}
    auth.base_url = "https://test.api.com"
    client = KISClient(auth, "12345678")
    return client


@pytest.fixture
def live_order(mock_client):
    return KISOrder(mock_client, "live")


@pytest.fixture
def paper_order(mock_client):
    return KISOrder(mock_client, "paper")


class TestKISOrderInit:
    def test_live_mode_tr_ids(self, live_order):
        assert live_order.buy_tr_id == "TTTT1002U"
        assert live_order.sell_tr_id == "TTTT1006U"

    def test_paper_mode_tr_ids(self, paper_order):
        assert paper_order.buy_tr_id == "VTTT1002U"
        assert paper_order.sell_tr_id == "VTTT1006U"


class TestPlaceOrder:
    def test_qty_less_than_1_rejected(self, live_order):
        result = live_order._place_order("TQQQ", 0, "buy", "NASD", 0, "00")
        assert result is None

    def test_negative_qty_rejected(self, live_order):
        result = live_order._place_order("TQQQ", -5, "buy", "NASD", 0, "00")
        assert result is None

    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "get_us_price", return_value={"price": 55.0})
    def test_buy_market_success(self, mock_price, mock_req, live_order):
        mock_req.return_value = {
            "output": {"ODNO": "00001234"},
            "rt_cd": "0",
        }
        result = live_order.buy_market("TQQQ", 10)
        assert result is not None
        assert result["order_no"] == "00001234"
        assert result["side"] == "buy"
        assert result["qty"] == 10

    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "get_us_price", return_value={"price": 55.0})
    def test_sell_market_success(self, mock_price, mock_req, live_order):
        mock_req.return_value = {
            "output": {"ODNO": "00005678"},
            "rt_cd": "0",
        }
        result = live_order.sell_market("TQQQ", 10)
        assert result is not None
        assert result["order_no"] == "00005678"
        assert result["side"] == "sell"

    @patch.object(KISClient, "get_us_price", return_value=None)
    def test_order_no_price(self, mock_price, live_order):
        """Market order fails if price unavailable."""
        result = live_order.buy_market("TQQQ", 10)
        assert result is None

    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "get_us_price", return_value={"price": 55.0})
    def test_order_api_failure(self, mock_price, mock_req, live_order):
        mock_req.return_value = None
        result = live_order.buy_market("TQQQ", 10)
        assert result is None

    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "get_us_price", return_value={"price": 55.0})
    def test_order_no_output(self, mock_price, mock_req, live_order):
        mock_req.return_value = {"rt_cd": "0"}
        result = live_order.buy_market("TQQQ", 10)
        assert result is None

    @patch.object(KISClient, "_request")
    def test_buy_limit(self, mock_req, live_order):
        mock_req.return_value = {
            "output": {"ODNO": "L001"},
            "rt_cd": "0",
        }
        result = live_order.buy_limit("TQQQ", 5, 50.0)
        assert result is not None
        assert result["order_no"] == "L001"

    @patch.object(KISClient, "_request")
    def test_sell_limit(self, mock_req, live_order):
        mock_req.return_value = {
            "output": {"ODNO": "L002"},
            "rt_cd": "0",
        }
        result = live_order.sell_limit("TQQQ", 5, 55.0)
        assert result is not None


class TestPlaceOrderBody:
    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "get_us_price", return_value={"price": 55.0})
    def test_market_order_uses_price(self, mock_price, mock_req, live_order):
        """Market order sends actual price (not 0) for KIS overseas."""
        mock_req.return_value = {"output": {"ODNO": "X"}, "rt_cd": "0"}
        live_order.buy_market("TQQQ", 3)
        _, kwargs = mock_req.call_args
        body = kwargs["json_body"]
        # Price should be ~55.0 * 1.005 = 55.28 (with slippage)
        assert float(body["OVRS_ORD_UNPR"]) > 0
        assert body["ORD_QTY"] == "3"

    @patch.object(KISClient, "_request")
    def test_limit_order_has_price(self, mock_req, live_order):
        mock_req.return_value = {"output": {"ODNO": "X"}, "rt_cd": "0"}
        live_order.buy_limit("TQQQ", 2, 45.50)
        _, kwargs = mock_req.call_args
        body = kwargs["json_body"]
        assert body["OVRS_ORD_UNPR"] == "45.5"

    @patch.object(KISClient, "_request")
    @patch.object(KISClient, "get_us_price", return_value={"price": 55.0})
    def test_sell_uses_sell_tr_id(self, mock_price, mock_req, live_order):
        mock_req.return_value = {"output": {"ODNO": "X"}, "rt_cd": "0"}
        live_order.sell_market("TQQQ", 1)
        _, kwargs = mock_req.call_args
        headers = kwargs["headers"]
        assert headers["tr_id"] == "TTTT1006U"
