"""Tests for configuration module."""

import json
import os
import pytest
from unittest.mock import patch

from src.utils.config import load_strategy_params, load_env, get_kis_urls


class TestLoadStrategyParams:
    def test_loads_valid_config(self, tmp_path):
        config = {"entry": {"rr_ratio": 2.0}, "risk": {"circuit_breaker_losses": 3}}
        config_file = tmp_path / "strategy_params.json"
        config_file.write_text(json.dumps(config))

        import src.utils.config as cfg
        cfg._config_cache = {}  # Reset cache
        with patch.object(cfg, "_config_cache", {}):
            with patch("src.utils.config.os.path.dirname", return_value=str(tmp_path)):
                with patch("src.utils.config.os.path.join",
                           return_value=str(config_file)):
                    result = load_strategy_params()
                    assert result["entry"]["rr_ratio"] == 2.0

    def test_file_not_found_exits(self, tmp_path):
        import src.utils.config as cfg
        cfg._config_cache = {}
        with patch("src.utils.config.os.path.join",
                   return_value=str(tmp_path / "nonexistent.json")):
            with pytest.raises(SystemExit) as exc_info:
                load_strategy_params()
            assert "not found" in str(exc_info.value)

    def test_invalid_json_exits(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not valid json{{{")
        import src.utils.config as cfg
        cfg._config_cache = {}
        with patch("src.utils.config.os.path.join", return_value=str(bad_file)):
            with pytest.raises(SystemExit) as exc_info:
                load_strategy_params()
            assert "Invalid JSON" in str(exc_info.value)


class TestLoadEnv:
    @patch.dict(os.environ, {
        "KIS_APP_KEY": "mykey",
        "KIS_APP_SECRET": "mysecret",
        "KIS_ACCOUNT_NO": "12345678",
        "TRADING_MODE": "live",
        "TEST_MODE": "on",
    }, clear=False)
    @patch("src.utils.config.load_dotenv")
    def test_loads_env_values(self, mock_dotenv):
        env = load_env()
        assert env["kis_app_key"] == "mykey"
        assert env["trading_mode"] == "live"
        assert env["test_mode"] is True

    @patch.dict(os.environ, {}, clear=True)
    @patch("src.utils.config.load_dotenv")
    def test_defaults_when_missing(self, mock_dotenv):
        env = load_env()
        assert env["kis_app_key"] == ""
        assert env["trading_mode"] == "paper"
        assert env["test_mode"] is False


class TestGetKisUrls:
    def test_live_urls(self):
        urls = get_kis_urls("live")
        assert "openapi.koreainvestment.com" in urls["base"]
        assert "9443" in urls["base"]

    def test_paper_urls(self):
        urls = get_kis_urls("paper")
        assert "openapivts" in urls["base"]
        assert "29443" in urls["base"]

    def test_urls_contain_all_endpoints(self):
        urls = get_kis_urls("live")
        for key in ["base", "token", "order", "balance", "price", "daily_price"]:
            assert key in urls
