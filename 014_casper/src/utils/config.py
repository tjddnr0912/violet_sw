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
    """Load .env file and return environment variables as dict.

    ``override=True`` is deliberate: if the bot was launched via
    ``run_casper.sh`` which ``export``s values through a bash ``while
    read`` loop, any subtle parsing bug there (base64 secrets ending
    with ``=`` were once lost to ``IFS='='`` read) would otherwise shadow
    the correct value from the file. Treating the on-disk ``.env`` as
    the single source of truth makes the system robust to shell-side
    parsing regressions.
    """
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    load_dotenv(env_path, override=True)
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


def _validate_params(params: dict) -> None:
    """Validate strategy parameters at startup."""
    entry = params.get("entry", {})
    filters = params.get("filters", {})
    risk = params.get("risk", {})

    if entry.get("rr_ratio", 0) <= 0:
        raise ValueError(f"rr_ratio must be positive, got {entry.get('rr_ratio')}")
    if filters.get("vix_low", 0) >= filters.get("vix_high", 0):
        raise ValueError(
            f"vix_low ({filters.get('vix_low')}) must be < vix_high ({filters.get('vix_high')})"
        )
    if risk.get("max_shares", 0) <= 0:
        raise ValueError(f"max_shares must be positive, got {risk.get('max_shares')}")
    if risk.get("max_trades_per_day", 0) <= 0:
        raise ValueError(f"max_trades_per_day must be positive")


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
    _validate_params(_config_cache)
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
