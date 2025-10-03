# Temporary compatibility layer for config migration
# This file re-exports configurations from the new split structure
# to maintain backward compatibility during migration

import os
import sys
from pathlib import Path

# Add lib/ to path for imports
base_path = Path(__file__).parent
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

# Import common configurations
from lib.core.config_common import (
    API_CONFIG,
    LOGGING_CONFIG,
    GUI_CONFIG,
    SAFETY_CONFIG,
    EXECUTION_CONFIG,
    SCHEDULE_CONFIG,
    TRADING_CONFIG,
    merge_configs,
    get_common_config,
    validate_api_config,
    validate_common_config,
)

# Import version 1 configurations
from ver1.config_v1 import (
    VERSION_METADATA,
    INDICATOR_CONFIG,
    SIGNAL_WEIGHTS,
    REGIME_CONFIG,
    RISK_CONFIG,
    INTERVAL_PRESETS,
    CHART_CONFIG,
    MULTI_CHART_CONFIG,
    get_version_config,
    validate_version_config,
)

# Re-export API credentials for backward compatibility
BITHUMB_CONNECT_KEY = API_CONFIG['bithumb_connect_key']
BITHUMB_SECRET_KEY = API_CONFIG['bithumb_secret_key']

# Re-construct TRADING_CONFIG with EXECUTION_CONFIG keys for backward compatibility
# Merge execution parameters into trading config
TRADING_CONFIG_MERGED = TRADING_CONFIG.copy()
TRADING_CONFIG_MERGED['trade_amount_krw'] = EXECUTION_CONFIG['trade_amount_krw']
TRADING_CONFIG_MERGED['min_trade_amount'] = EXECUTION_CONFIG['min_trade_amount']
TRADING_CONFIG_MERGED['max_trade_amount'] = EXECUTION_CONFIG['max_trade_amount']
TRADING_CONFIG_MERGED['trading_fee_rate'] = EXECUTION_CONFIG['trading_fee_rate']

# Re-construct STRATEGY_CONFIG for backward compatibility
STRATEGY_CONFIG = INDICATOR_CONFIG.copy()
STRATEGY_CONFIG['signal_weights'] = SIGNAL_WEIGHTS
STRATEGY_CONFIG['confidence_threshold'] = REGIME_CONFIG['confidence_threshold']
STRATEGY_CONFIG['signal_threshold'] = REGIME_CONFIG['signal_threshold']
STRATEGY_CONFIG['max_daily_loss_pct'] = RISK_CONFIG['max_daily_loss_pct']
STRATEGY_CONFIG['max_consecutive_losses'] = RISK_CONFIG['max_consecutive_losses']
STRATEGY_CONFIG['max_daily_trades'] = RISK_CONFIG['max_daily_trades']
STRATEGY_CONFIG['position_risk_pct'] = RISK_CONFIG['position_risk_pct']
STRATEGY_CONFIG['interval_presets'] = INTERVAL_PRESETS
STRATEGY_CONFIG['multi_chart_config'] = MULTI_CHART_CONFIG


def validate_config() -> bool:
    """Validate configuration (backward compatibility)"""
    return validate_common_config()


def get_config():
    """Get all configuration (backward compatibility)"""
    return {
        'trading': TRADING_CONFIG_MERGED,  # Use merged config with execution params
        'strategy': STRATEGY_CONFIG,
        'schedule': SCHEDULE_CONFIG,
        'logging': LOGGING_CONFIG,
        'safety': SAFETY_CONFIG,
        'execution': EXECUTION_CONFIG,  # Also include execution separately for new code
        'api': {
            'connect_key': BITHUMB_CONNECT_KEY,
            'secret_key': BITHUMB_SECRET_KEY
        }
    }
