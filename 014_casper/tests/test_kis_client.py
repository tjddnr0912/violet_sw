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
    def test_uses_latest_when_no_exact_match(self, mock_req, client):
        mock_req.return_value = {
            "output": [
                {"odno": "other", "ft_ccld_unpr": "56.00"}
            ]
        }
        result = client.get_us_filled_price("123", "TQQQ")
        assert result == 56.0  # Falls back to first item

    @patch.object(KISClient, "_request")
    def test_zero_price_skipped(self, mock_req, client):
        mock_req.return_value = {
            "output": [
                {"odno": "123", "ft_ccld_unpr": "0"}
            ]
        }
        result = client.get_us_filled_price("123", "TQQQ")
        assert result is None


class TestGetUsBalance:
    @patch.object(KISClient, "_request")
    def test_success(self, mock_req, client):
        mock_req.return_value = {
            "output": {"ovrs_ord_psbl_amt": "5000.00", "frcr_pchs_amt1": "10000.00"}
        }
        result = client.get_us_balance()
        assert result is not None
        assert result["available_cash"] == 5000.0

    @patch.object(KISClient, "_request")
    def test_failure(self, mock_req, client):
        mock_req.return_value = None
        assert client.get_us_balance() is None
