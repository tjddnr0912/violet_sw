"""Tests for KIS authentication module."""

import json
import os
import pytest
import time
from unittest.mock import patch, MagicMock

from src.api.kis_auth import KISAuth, TOKEN_FILE


@pytest.fixture
def auth():
    return KISAuth("test_key", "test_secret", "https://test.api.com")


class TestKISAuthInit:
    def test_initial_state(self, auth):
        assert auth.app_key == "test_key"
        assert auth.app_secret == "test_secret"
        assert auth._token is None
        assert auth._token_expires == 0


class TestTokenProperty:
    @patch.object(KISAuth, "_request_new_token")
    @patch.object(KISAuth, "_load_cached_token", return_value=None)
    def test_requests_new_when_no_cache(self, mock_load, mock_req, auth):
        # auth starts with _token=None, _token_expires=0
        def set_token():
            auth._token = "fresh_token"
            auth._token_expires = time.time() + 3600

        mock_req.side_effect = set_token
        result = auth.token
        mock_req.assert_called_once()
        assert result == "fresh_token"

    def test_returns_cached_when_valid(self, auth):
        auth._token = "cached_token"
        auth._token_expires = time.time() + 3600
        assert auth.token == "cached_token"

    @patch.object(KISAuth, "_request_new_token")
    @patch.object(KISAuth, "_load_cached_token", return_value=None)
    def test_returns_empty_on_failure(self, mock_load, mock_req, auth):
        # _request_new_token doesn't set token (failure)
        result = auth.token
        assert result == ""

    def test_loads_from_file_when_expired_in_memory(self, auth):
        auth._token = "old"
        auth._token_expires = 0  # expired
        cached = {"token": "file_token", "expires": time.time() + 3600}
        with patch.object(auth, "_load_cached_token", return_value=cached):
            assert auth.token == "file_token"


class TestHeaders:
    def test_headers_contain_auth(self, auth):
        auth._token = "test123"
        auth._token_expires = time.time() + 3600
        hdrs = auth.headers
        assert hdrs["authorization"] == "Bearer test123"
        assert hdrs["appkey"] == "test_key"
        assert hdrs["appsecret"] == "test_secret"


class TestRequestNewToken:
    @patch("src.api.kis_auth.requests.post")
    def test_success(self, mock_post, auth):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "abc123"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        with patch.object(auth, "_save_cached_token"):
            auth._request_new_token()

        assert auth._token == "abc123"
        assert auth._token_expires > time.time()

    @patch("src.api.kis_auth.requests.post")
    def test_empty_token_rejected(self, mock_post, auth):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": ""}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        auth._request_new_token()
        assert auth._token is None  # Not set

    @patch("src.api.kis_auth.requests.post")
    def test_network_failure(self, mock_post, auth):
        mock_post.side_effect = Exception("Connection refused")
        auth._request_new_token()
        assert auth._token is None

    @patch("src.api.kis_auth.requests.post")
    def test_missing_access_token_key(self, mock_post, auth):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": "invalid_client"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        auth._request_new_token()
        assert auth._token is None


class TestCachedToken:
    def test_load_nonexistent(self, auth, tmp_path):
        with patch("src.api.kis_auth.TOKEN_FILE", str(tmp_path / "nofile.json")):
            assert auth._load_cached_token() is None

    def test_load_valid(self, auth, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text(json.dumps({"token": "t", "expires": 99999999999}))
        with patch("src.api.kis_auth.TOKEN_FILE", str(token_file)):
            result = auth._load_cached_token()
            assert result["token"] == "t"

    def test_load_corrupt(self, auth, tmp_path):
        token_file = tmp_path / "token.json"
        token_file.write_text("not json{{{")
        with patch("src.api.kis_auth.TOKEN_FILE", str(token_file)):
            assert auth._load_cached_token() is None

    def test_save_creates_file(self, auth, tmp_path):
        token_file = tmp_path / "config" / "token.json"
        auth._token = "save_test"
        auth._token_expires = 12345
        with patch("src.api.kis_auth.TOKEN_FILE", str(token_file)):
            auth._save_cached_token()
            assert token_file.exists()
            data = json.loads(token_file.read_text())
            assert data["token"] == "save_test"
