"""
Common Configuration - Shared across all trading strategy versions

This module contains configuration settings that are common to all strategy versions,
including API credentials, logging, safety, and execution parameters.
"""

import os
from typing import Dict, Any


# API Configuration
API_CONFIG = {
    'bithumb_connect_key': os.getenv("BITHUMB_CONNECT_KEY", "YOUR_CONNECT_KEY"),
    'bithumb_secret_key': os.getenv("BITHUMB_SECRET_KEY", "YOUR_SECRET_KEY"),
}

# Logging Configuration
LOGGING_CONFIG = {
    'log_level': 'INFO',
    'log_dir': 'logs',
    'max_log_files': 30,
    'enable_console_log': True,
    'enable_file_log': True,
    'console_level': 'INFO',  # Can be overridden to DEBUG
}

# GUI Configuration
GUI_CONFIG = {
    'window_title': 'Cryptocurrency Trading Bot',
    'window_width': 1400,
    'window_height': 900,
    'theme': 'default',
    'update_interval_ms': 1000,  # GUI refresh interval
}

# Safety Configuration
SAFETY_CONFIG = {
    'dry_run': False,  # Simulation mode (no real trades)
    'test_mode': False,  # Test mode (no transaction logging)
    'max_daily_trades': 10,  # Maximum trades per day
    'emergency_stop': False,  # Emergency stop flag
    'balance_check_interval': 60,  # Balance check interval (minutes)
}

# Execution Configuration
EXECUTION_CONFIG = {
    'default_symbol': 'BTC',  # Default trading pair
    'default_interval': '1h',  # Default candlestick interval
    'trade_amount_krw': 10000,  # Trade amount in KRW
    'min_trade_amount': 5000,  # Minimum trade amount
    'max_trade_amount': 100000,  # Maximum trade amount
    'trading_fee_rate': 0.0025,  # Trading fee rate (0.25%)
    'check_interval_minutes': 15,  # Market check interval (minutes)
}

# Schedule Configuration
SCHEDULE_CONFIG = {
    'check_interval_minutes': 15,  # Market check interval (minutes)
    'daily_check_time': '09:05',  # Daily check time
    'enable_night_trading': False,  # Night trading enabled
    'night_start_hour': 22,  # Night trading start hour
    'night_end_hour': 6,  # Night trading end hour

    # Interval-based check periods (minutes)
    'interval_check_periods': {
        '30m': 10,
        '1h': 15,
        '6h': 60,
        '12h': 120,
        '24h': 240,
    }
}

# Trading Configuration (common parameters)
TRADING_CONFIG = {
    'target_ticker': 'BTC',
    'stop_loss_percent': 5.0,
    'take_profit_percent': 10.0,
}


def merge_configs(*configs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge multiple configuration dictionaries.

    Later configs override earlier ones. Nested dicts are merged recursively.

    Args:
        *configs: Variable number of configuration dictionaries

    Returns:
        Merged configuration dictionary
    """
    def deep_merge(base: dict, override: dict) -> dict:
        """Recursively merge override into base."""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    merged = {}
    for config in configs:
        merged = deep_merge(merged, config)
    return merged


def get_common_config() -> Dict[str, Any]:
    """
    Get all common configuration as a single dictionary.

    Returns:
        Dictionary with all common configuration sections
    """
    return {
        'API_CONFIG': API_CONFIG,
        'LOGGING_CONFIG': LOGGING_CONFIG,
        'GUI_CONFIG': GUI_CONFIG,
        'SAFETY_CONFIG': SAFETY_CONFIG,
        'EXECUTION_CONFIG': EXECUTION_CONFIG,
        'SCHEDULE_CONFIG': SCHEDULE_CONFIG,
        'TRADING_CONFIG': TRADING_CONFIG,
    }


def validate_api_config(dry_run: bool = False) -> bool:
    """
    Validate API configuration.

    Args:
        dry_run: Whether running in dry-run mode

    Returns:
        True if valid, False otherwise
    """
    connect_key = API_CONFIG['bithumb_connect_key']
    secret_key = API_CONFIG['bithumb_secret_key']

    if connect_key == "YOUR_CONNECT_KEY" or secret_key == "YOUR_SECRET_KEY":
        if dry_run:
            print("⚠️ Warning: API keys not set. Running in dry-run mode.")
            return True
        else:
            print("❌ Error: API keys required for live trading mode.")
            print("   Set environment variables or enable dry_run mode.")
            return False

    return True


def validate_common_config() -> bool:
    """
    Validate common configuration settings.

    Returns:
        True if all common configs are valid
    """
    # Validate API config
    dry_run = SAFETY_CONFIG.get('dry_run', False)
    if not validate_api_config(dry_run):
        return False

    # Validate trade amounts
    if EXECUTION_CONFIG['trade_amount_krw'] < EXECUTION_CONFIG['min_trade_amount']:
        print("⚠️ Warning: Trade amount below minimum.")
        return False

    return True
