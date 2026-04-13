"""Tests for KIS REST API client."""

import pytest
from unittest.mock import MagicMock, patch

import requests

from src.api.kis_auth import KISAuth
from src.api.kis_client import KISClient


@pytest.fixture
def client():
    auth = MagicMock(spec=KISAuth)
    auth.headers = {"authorization": "Bearer t", "appkey": "k", "appsecret": "s",
                    "content-type": "application/json; charset=utf-8"}
    auth.base_url = "https://test.api.com"
    return KISClient(auth, "12345678")


class TestRequest:
    @patch("src.api.kis_client.requests.get")
    def test_success(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rt_cd": "0", "data": "ok"}
        mock_get.return_value = mock_resp

        result = client._request("GET", "https://test.api.com/test")
        assert result["rt_cd"] == "0"

    @patch("src.api.kis_client.requests.get")
    def test_api_error_code(self, mock_get, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rt_cd": "1", "msg1": "Fail"}
        mock_get.return_value = mock_resp

        result = client._request("GET", "https://test.api.com/test")
        assert result is None

    @patch("src.api.kis_client.requests.get")
    def test_retry_on_http_error(self, mock_get, client):
        fail = MagicMock()
        fail.status_code = 500
        ok = MagicMock()
        ok.status_code = 200
        ok.json.return_value = {"rt_cd": "0"}
        mock_get.side_effect = [fail, ok]

        result = client._request("GET", "https://test.api.com/test")
        assert result is not None
        assert mock_get.call_count == 2

    @patch("src.api.kis_client.requests.get")
    def test_retry_on_network_error(self, mock_get, client):
        mock_get.side_effect = requests.RequestException("timeout")

        result = client._request("GET", "https://test.api.com/test")
        assert result is None
        assert mock_get.call_count == 3  # MAX_RETRIES

    @patch("src.api.kis_client.requests.post")
    def test_no_retry_when_disabled(self, mock_post, client):
        """POST with retry=False should attempt only once."""
        mock_post.side_effect = requests.RequestException("timeout")

        result = client._request("POST", "https://test.api.com/order",
                                 json_body={}, retry=False)
        assert result is None
        assert mock_post.call_count == 1  # No retry

    @patch("src.api.kis_client.requests.post")
    def test_post_request(self, mock_post, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"rt_cd": "0", "output": {"ODNO": "1"}}
        mock_post.return_value = mock_resp

        result = client._request("POST", "https://test.api.com/order",
                                 json_body={"key": "val"})
        assert result is not None


class TestGetUsPrice:
    @patch.object(KISClient, "_request")
    def test_success(self, mock_req, client):
        mock_req.return_value = {
            "output": {"last": "55.50", "open": "54.0", "high": "56.0",
                       "low": "53.5", "tvol": "1000000"}
        }
        result = client.get_us_price("TQQQ")
        assert result is not None
        assert result["price"] == 55.5
        assert result["volume"] == 1000000

    @patch.object(KISClient, "_request")
    def test_empty_string_values(self, mock_req, client):
        mock_req.return_value = {
            "output": {"last": "", "open": "", "high": "", "low": "", "tvol": ""}
        }
        result = client.get_us_price("TQQQ")
        assert result is not None
        assert result["price"] == 0  # "" or 0 → 0

    @patch.object(KISClient, "_request")
    def test_api_failure(self, mock_req, client):
        mock_req.return_value = None
        result = client.get_us_price("TQQQ")
        assert result is None

    @patch.object(KISClient, "_request")
    def test_no_output_key(self, mock_req, client):
        mock_req.return_value = {"rt_cd": "0"}
        result = client.get_us_price("TQQQ")
        assert result is None


class TestGetUsFilledPrice:
    @patch.object(KISClient, "_request")
    def test_finds_fill_price(self, mock_req, client):
        mock_req.return_value = {
            "output": [
                {"odno": "123", "ft_ccld_unpr": "55.25"}
            ]
        }
        result = client.get_us_filled_price("123", "TQQQ")
        assert result == 55.25

    @patch.object(KISClient, "_request")
    def test_not_found_returns_none(self, mock_req, client):
        mock_req.return_value = {
            "output": []
        }
        result = client.get_us_filled_price("999", "TQQQ")
        assert result is None

    @patch.object(KISClient, "_request")
    def test_api_failure_returns_none(self, mock_req, client):
        mock_req.return_value = None
        result = client.get_us_filled_price("123", "TQQQ")
        assert result is None

    @patch.object(KISClient, "_request")
    def test_no_match_returns_none(self, mock_req, client):
        """When order_no doesn't match any item, returns None (no unsafe fallback)."""
        mock_req.return_value = {
            "output": [
                {"odno": "other", "ft_ccld_unpr": "56.00"}
            ]
        }
        result = client.get_us_filled_price("123", "TQQQ")
        assert result is None

    @patch.object(KISClient, "_request")
    def test_zero_price_skipped(self, mock_req, client):
        mock_req.return_value = {
            "output": [
                {"odno": "123", "ft_ccld_unpr": "0"}
            ]
        }
        result = client.get_us_filled_price("123", "TQQQ")
        assert result is None


class TestGetUsMinuteChart:
    @patch.object(KISClient, "_request")
    def test_success(self, mock_req, client):
        mock_req.return_value = {
            "output2": [
                {"xymd": "20260406", "xhms": "094500", "open": "55", "high": "56",
                 "low": "54", "last": "55.5", "evol": "10000"},
                {"xymd": "20260406", "xhms": "094000", "open": "54", "high": "55",
                 "low": "53", "last": "54.5", "evol": "8000"},
            ]
        }
        result = client.get_us_minute_chart("TQQQ", nmin=5)
        assert result is not None
        assert len(result) == 2
        # Should be reversed to ascending order
        assert result[0]["time"] == "094000"
        assert result[1]["time"] == "094500"

    @patch.object(KISClient, "_request")
    def test_api_failure(self, mock_req, client):
        mock_req.return_value = None
        assert client.get_us_minute_chart("TQQQ") is None

    @patch.object(KISClient, "_request")
    def test_empty_bars(self, mock_req, client):
        mock_req.return_value = {"output2": []}
        assert client.get_us_minute_chart("TQQQ") is None

    @patch.object(KISClient, "_request")
    def test_skips_zero_close(self, mock_req, client):
        mock_req.return_value = {
            "output2": [
                {"xymd": "20260406", "xhms": "094000", "open": "0", "high": "0",
                 "low": "0", "last": "0", "evol": "0"},
                {"xymd": "20260406", "xhms": "094500", "open": "55", "high": "56",
                 "low": "54", "last": "55.5", "evol": "1000"},
            ]
        }
        result = client.get_us_minute_chart("TQQQ")
        assert result is not None
        assert len(result) == 1


class TestGetUsDailyChart:
    @patch.object(KISClient, "_request")
    def test_success(self, mock_req, client):
        mock_req.return_value = {
            "output2": [
                {"xymd": "20260402", "open": "52", "high": "54",
                 "low": "51", "clos": "53", "tvol": "5000000"},
                {"xymd": "20260401", "open": "50", "high": "53",
                 "low": "49", "clos": "52", "tvol": "4000000"},
            ]
        }
        result = client.get_us_daily_chart("TQQQ", count=2)
        assert result is not None
        assert len(result) == 2
        # Reversed to ascending
        assert result[0]["date"] == "20260401"

    @patch.object(KISClient, "_request")
    def test_api_failure(self, mock_req, client):
        mock_req.return_value = None
        assert client.get_us_daily_chart("TQQQ") is None

    @patch.object(KISClient, "_request")
    def test_trims_to_count(self, mock_req, client):
        mock_req.return_value = {
            "output2": [
                {"xymd": f"2026040{i}", "open": "50", "high": "54",
                 "low": "49", "clos": "52", "tvol": "1000"}
                for i in range(5, 0, -1)
            ]
        }
        result = client.get_us_daily_chart("TQQQ", count=3)
        assert result is not None
        assert len(result) == 3


class TestGetUsBalance:
    @patch.object(KISClient, "_request")
    def test_success_no_symbol_uses_present_balance(self, mock_req, client):
        # No symbol → inquire-present-balance, USD row's drawable amount.
        mock_req.return_value = {
            "output2": [
                {"crcy_cd": "KRW", "frcr_drwg_psbl_amt_1": "0"},
                {"crcy_cd": "USD", "frcr_drwg_psbl_amt_1": "5000.00"},
            ]
        }
        result = client.get_us_balance()
        assert result == {"available_cash": 5000.0}

    @patch.object(KISClient, "_request")
    def test_success_with_symbol_uses_psamount(self, mock_req, client):
        # symbol + unit_price → inquire-psamount path, returns max_qty too.
        mock_req.return_value = {
            "output": {"ovrs_ord_psbl_amt": "660.20", "max_ord_psbl_qty": "13"}
        }
        result = client.get_us_balance(symbol="TQQQ", unit_price=49.03)
        assert result == {"available_cash": 660.20, "max_qty": 13}

    def test_symbol_without_price_rejected(self, client):
        assert client.get_us_balance(symbol="TQQQ") is None

    @patch.object(KISClient, "_request")
    def test_failure(self, mock_req, client):
        mock_req.return_value = None
        assert client.get_us_balance() is None

    @patch.object(KISClient, "_request")
    def test_no_usd_row(self, mock_req, client):
        mock_req.return_value = {"output2": [{"crcy_cd": "KRW"}]}
        assert client.get_us_balance() is None


class TestWarmUp:
    @pytest.fixture(autouse=True)
    def _restore_real_warm_up(self, monkeypatch):
        # conftest autouse stubs out warm_up for everyone else; these tests
        # actually need to exercise the real polling loop.
        monkeypatch.setattr(KISClient, "warm_up", KISClient._original_warm_up)

    @patch.object(KISClient, "_request")
    def test_success_first_try(self, mock_req, client):
        mock_req.return_value = {"rt_cd": "0", "output": {"last": "400"}}
        assert client.warm_up(max_secs=30, poll_interval=1) is True
        assert mock_req.call_count == 1

    @patch("src.api.kis_client.time.sleep")
    @patch.object(KISClient, "_request")
    def test_success_after_cold_attempts(self, mock_req, mock_sleep, client):
        # First two attempts cold (None), third succeeds
        mock_req.side_effect = [None, None, {"rt_cd": "0"}]
        assert client.warm_up(max_secs=60, poll_interval=10) is True
        assert mock_req.call_count == 3

    @patch("src.api.kis_client.time.sleep")
    @patch.object(KISClient, "_request")
    def test_timeout_returns_false(self, mock_req, mock_sleep, client):
        mock_req.return_value = None  # always cold
        assert client.warm_up(max_secs=5, poll_interval=2) is False
        # Should not internally retry — retry=False passed through
        for call in mock_req.call_args_list:
            assert call.kwargs.get("retry") is False
