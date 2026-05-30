"""Tests for configuration module."""

import json
import os
import pytest
from unittest.mock import patch

from src.utils.config import load_strategy_params, load_env, get_kis_urls


class TestLoadStrategyParams:
    def test_loads_valid_config(self, tmp_path):
        config = {"entry": {"rr_ratio": 2.0}, "filters": {"vix_low": 12, "vix_high": 30},
                  "risk": {"circuit_breaker_losses": 3, "max_shares": 200, "max_trades_per_day": 1}}
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


class TestParamsValidation:
    def test_valid_config_passes(self):
        from src.utils.config import _validate_params
        params = {
            "symbols": {"bull": "TQQQ", "bear": "SQQQ", "trend_filter": "QQQ"},
            "entry": {"rr_ratio": 2.0, "min_risk_dollar": 0.10},
            "filters": {"vix_low": 12.0, "vix_high": 30.0, "ma_period": 20, "orb_atr_max_ratio": 1.5},
            "risk": {"max_shares": 200, "max_trades_per_day": 1, "circuit_breaker_losses": 3,
                     "max_weekly_loss_pct": 3.0, "max_position_pct": 1.0},
            "commission": {"rate_per_side": 0.0009},
        }
        _validate_params(params)  # Should not raise

    def test_negative_rr_ratio_fails(self):
        from src.utils.config import _validate_params
        params = {"entry": {"rr_ratio": -1.0, "min_risk_dollar": 0.10},
                  "filters": {"vix_low": 12, "vix_high": 30},
                  "risk": {"max_shares": 200, "max_trades_per_day": 1},
                  "commission": {"rate_per_side": 0.0009}}
        with pytest.raises(ValueError, match="rr_ratio"):
            _validate_params(params)

    def test_vix_range_inverted_fails(self):
        from src.utils.config import _validate_params
        params = {"entry": {"rr_ratio": 2.0, "min_risk_dollar": 0.10},
                  "filters": {"vix_low": 50, "vix_high": 10},
                  "risk": {"max_shares": 200, "max_trades_per_day": 1},
                  "commission": {"rate_per_side": 0.0009}}
        with pytest.raises(ValueError, match="vix"):
            _validate_params(params)

    def test_zero_max_shares_fails(self):
        from src.utils.config import _validate_params
        params = {"entry": {"rr_ratio": 2.0, "min_risk_dollar": 0.10},
                  "filters": {"vix_low": 12, "vix_high": 30},
                  "risk": {"max_shares": 0, "max_trades_per_day": 1},
                  "commission": {"rate_per_side": 0.0009}}
        with pytest.raises(ValueError, match="max_shares"):
            _validate_params(params)


def test_sleeve_engine_and_trend_params():
    import src.utils.config as _cfg
    _cfg._config_cache = None  # bypass module-level cache if present
    p = load_strategy_params()
    assert p.get("sleeve_engine") in ("trend", "intraday")
    t = p.get("trend", {})
    assert t.get("asset") == "TQQQ"
    assert t.get("safe_asset") == "BIL"
    assert t.get("signal_symbol") == "QQQ"
    assert abs(float(t.get("target_vol")) - 0.40) < 1e-9
    assert int(t.get("sma_period")) == 200
    assert int(t.get("vol_lookback")) == 20
