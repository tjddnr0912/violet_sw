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


def _bool_env(name: str, default: bool) -> bool:
    """Read a bool env var. 'on'/'true'/'1' → True, 'off'/'false'/'0' → False."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("on", "true", "1", "yes")


def _apply_ict_env_overrides(params: dict) -> dict:
    """Allow .env (ICT_*) to override config/strategy_params.json entry flags.

    Order of precedence (highest → lowest):
      1. ICT_* env variable
      2. config/strategy_params.json entry.*
      3. hard-coded default (false)

    Listed here so a deployer can flip ICT phases without editing JSON.
    """
    entry = params.setdefault("entry", {})

    # Phase 1
    if os.getenv("ICT_KILLZONE_ENABLED") is not None:
        entry["killzone_filter_enabled"] = _bool_env("ICT_KILLZONE_ENABLED", False)
    if os.getenv("ICT_ALLOWED_KILLZONES"):
        entry["allowed_killzones"] = [
            s.strip() for s in os.getenv("ICT_ALLOWED_KILLZONES").split(",") if s.strip()
        ]
    if os.getenv("ICT_REQUIRE_DISPLACEMENT") is not None:
        entry["require_displacement"] = _bool_env("ICT_REQUIRE_DISPLACEMENT", False)
    if os.getenv("ICT_DISP_ATR_MULT"):
        entry["disp_atr_mult"] = float(os.getenv("ICT_DISP_ATR_MULT"))
    if os.getenv("ICT_DISP_MAX_WICK"):
        entry["disp_max_wick"] = float(os.getenv("ICT_DISP_MAX_WICK"))
    if os.getenv("ICT_DISP_PREV_MULT"):
        entry["disp_prev_mult"] = float(os.getenv("ICT_DISP_PREV_MULT"))

    # Phase 2
    if os.getenv("ICT_REQUIRE_SWEEP_CHOCH") is not None:
        entry["require_sweep_choch"] = _bool_env("ICT_REQUIRE_SWEEP_CHOCH", False)
    if os.getenv("ICT_SWEEP_LOOKBACK"):
        entry["sweep_lookback"] = int(os.getenv("ICT_SWEEP_LOOKBACK"))
    if os.getenv("ICT_CHOCH_LOOKBACK"):
        entry["choch_lookback"] = int(os.getenv("ICT_CHOCH_LOOKBACK"))
    if os.getenv("ICT_SWEEP_MIN_BREACH_PCT"):
        entry["sweep_min_breach_pct"] = float(os.getenv("ICT_SWEEP_MIN_BREACH_PCT"))
    if os.getenv("ICT_SWEEP_MIN_WICK_RATIO"):
        entry["sweep_min_wick_ratio"] = float(os.getenv("ICT_SWEEP_MIN_WICK_RATIO"))

    # Phase 3 (module-only — bot integration deferred to separate plan)
    if os.getenv("ICT_BEAR_FVG_FOR_SQQQ") is not None:
        entry["bear_fvg_for_sqqq"] = _bool_env("ICT_BEAR_FVG_FOR_SQQQ", False)
    if os.getenv("ICT_DAILY_BIAS_SKIP_NEUTRAL") is not None:
        entry["daily_bias_skip_neutral"] = _bool_env(
            "ICT_DAILY_BIAS_SKIP_NEUTRAL", False
        )

    # Phase 4
    if os.getenv("ICT_USE_MULTI_TF_SL") is not None:
        entry["use_multi_tf_sl"] = _bool_env("ICT_USE_MULTI_TF_SL", False)
    if os.getenv("ICT_MTF_LOOKBACK_MIN"):
        entry["mtf_lookback_min"] = int(os.getenv("ICT_MTF_LOOKBACK_MIN"))
    if os.getenv("ICT_USE_OTE") is not None:
        entry["use_ote"] = _bool_env("ICT_USE_OTE", False)
    if os.getenv("ICT_FIB_LEVEL"):
        entry["ote_fib_level"] = float(os.getenv("ICT_FIB_LEVEL"))
    if os.getenv("ICT_REQUIRE_UNICORN") is not None:
        entry["require_unicorn"] = _bool_env("ICT_REQUIRE_UNICORN", False)
    if os.getenv("ICT_USE_POWER_OF_3") is not None:
        entry["use_power_of_3"] = _bool_env("ICT_USE_POWER_OF_3", False)
    if os.getenv("ICT_BULL_FVG_FOR_TQQQ") is not None:
        entry["bull_fvg_for_tqqq"] = _bool_env("ICT_BULL_FVG_FOR_TQQQ", False)

    # P2: QQQ primary signal source (mode-level toggle)
    if os.getenv("ICT_QQQ_PRIMARY") is not None:
        mode = params.setdefault("mode", {})
        mode["qqq_primary"] = _bool_env("ICT_QQQ_PRIMARY", False)

    # M3 — EQH/EQL pools
    if os.getenv("ICT_USE_EQH_EQL_POOLS") is not None:
        entry["use_eqh_eql_pools"] = _bool_env("ICT_USE_EQH_EQL_POOLS", False)
    if os.getenv("ICT_EQH_EQL_PCT"):
        entry["eqh_eql_pct"] = float(os.getenv("ICT_EQH_EQL_PCT"))

    # M4 — Session pools (Asia/London/Premarket)
    if os.getenv("ICT_USE_SESSION_POOLS") is not None:
        entry["use_session_pools"] = _bool_env("ICT_USE_SESSION_POOLS", False)

    # Day 1 — premarket history (yfinance prepost=True for swing fractal)
    if os.getenv("ICT_USE_PREMKT_HISTORY") is not None:
        entry["use_premkt_history"] = _bool_env("ICT_USE_PREMKT_HISTORY", False)

    # Day 3 — PDH/PDL injection into sweep pool
    if os.getenv("ICT_USE_PDH_PDL_POOL") is not None:
        entry["use_pdh_pdl_pool"] = _bool_env("ICT_USE_PDH_PDL_POOL", False)

    return params


def load_strategy_params() -> dict:
    """Load strategy parameters from JSON config + .env ICT_* overrides."""
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

    # Allow .env to override entry flags (ICT phases etc.)
    _config_cache = _apply_ict_env_overrides(_config_cache)

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
