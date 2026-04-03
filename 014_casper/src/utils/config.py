"""Configuration loader for Casper Trading Bot."""

import json
import os
from dotenv import load_dotenv


_config_cache = {}


def reset_config_cache():
    """Reset cached config for testing."""
    global _config_cache
    _config_cache = {}


def load_env() -> dict:
    """Load .env file and return environment variables as dict."""
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    load_dotenv(env_path)
    return {
        "kis_app_key": os.getenv("KIS_APP_KEY", ""),
        "kis_app_secret": os.getenv("KIS_APP_SECRET", ""),
        "kis_account_no": os.getenv("KIS_ACCOUNT_NO", ""),
        "kis_account_product": os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01"),
        "kis_base_url": os.getenv("KIS_BASE_URL", ""),
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
        "trading_mode": os.getenv("TRADING_MODE", "paper"),
        "test_mode": os.getenv("TEST_MODE", "off").lower() == "on",
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "timezone": os.getenv("TIMEZONE", "US/Eastern"),
    }


def load_strategy_params() -> dict:
    """Load strategy parameters from JSON config."""
    global _config_cache
    if _config_cache:
        return _config_cache

    config_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "config", "strategy_params.json"
    )
    try:
        with open(config_path, "r") as f:
            _config_cache = json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"Config file not found: {config_path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Invalid JSON in config: {config_path}: {e}")
    return _config_cache


def get_kis_urls(trading_mode: str) -> dict:
    """Return KIS API URLs based on trading mode."""
    if trading_mode == "live":
        base = "https://openapi.koreainvestment.com:9443"
    else:
        base = "https://openapivts.koreainvestment.com:29443"
    return {
        "base": base,
        "token": f"{base}/oauth2/tokenP",
        "order": f"{base}/uapi/overseas-stock/v1/trading/order",
        "balance": f"{base}/uapi/overseas-stock/v1/trading/inquire-balance",
        "price": f"{base}/uapi/overseas-price/v1/quotations/price",
        "daily_price": f"{base}/uapi/overseas-price/v1/quotations/dailyprice",
    }
