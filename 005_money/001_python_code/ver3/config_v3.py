"""
Version 3 Configuration - Portfolio Multi-Coin Trading Strategy

This module contains configuration specific to Version 3, which extends Ver2
with multi-coin portfolio management capabilities.

Configuration Sections:
- PORTFOLIO_CONFIG: Multi-coin portfolio management settings
- Inherits all Ver2 settings (timeframe, indicators, risk management)
- Additional multi-coin specific parameters
"""

from typing import Dict, Any, List, Tuple

# Import base configuration (migrated from ver2 for independence)
from ver3.config_base import (
    AVAILABLE_COINS,
    POPULAR_COINS,
    TIMEFRAME_CONFIG as VER2_TIMEFRAME_CONFIG,
    REGIME_FILTER_CONFIG as VER2_REGIME_FILTER_CONFIG,
    ENTRY_SCORING_CONFIG as VER2_ENTRY_SCORING_CONFIG,
    INDICATOR_CONFIG as VER2_INDICATOR_CONFIG,
    POSITION_CONFIG as VER2_POSITION_CONFIG,
    RISK_CONFIG as VER2_RISK_CONFIG,
    EXIT_CONFIG as VER2_EXIT_CONFIG,
    CHART_CONFIG as VER2_CHART_CONFIG,
    BACKTESTING_CONFIG as VER2_BACKTESTING_CONFIG,
    API_CONFIG as VER2_API_CONFIG,
    SAFETY_CONFIG as VER2_SAFETY_CONFIG,
    SCHEDULE_CONFIG as VER2_SCHEDULE_CONFIG,
    LOGGING_CONFIG as VER2_LOGGING_CONFIG,
)


# ========== VERSION 3 METADATA ==========

VERSION_METADATA = {
    "name": "ver3",
    "display_name": "Portfolio Multi-Coin Strategy",
    "description": "Advanced multi-coin trading with portfolio management, parallel analysis, and coordinated risk controls",
    "author": "Claude AI Assistant",
    "date": "2025-10-08",
    "base_strategy": "ver2",
}


# ========== PORTFOLIO CONFIGURATION (Multi-Coin) ==========

PORTFOLIO_CONFIG = {
    # Position limits
    'max_positions': 2,              # Max simultaneous open positions across all coins
    'max_positions_per_coin': 1,     # Max positions per individual coin (always 1 for this strategy)

    # Risk management
    'max_portfolio_risk_pct': 6.0,   # 6% total portfolio risk limit
    'position_size_equal': True,     # Use equal sizing (True) vs. signal-strength weighted (False)
    'reserve_cash_pct': 0.20,        # Keep 20% cash reserve

    # Coin selection
    'default_coins': ['BTC', 'ETH', 'XRP'],  # Default active coins on startup
    'min_coins': 1,                  # Minimum coins to monitor
    'max_coins': 4,                  # Maximum coins to monitor (BTC, ETH, XRP, SOL)

    # Parallel analysis configuration
    'parallel_analysis': True,       # Enable parallel analysis with ThreadPoolExecutor
    'max_workers': 3,                # Thread pool size (should match default_coins length)
    'analysis_timeout': 30,          # Maximum seconds for parallel analysis

    # Entry prioritization
    'entry_priority': 'score',       # Prioritize by: 'score' | 'volatility' | 'volume'
    'coin_rank': {                   # Tie-breaker if scores equal (higher = better)
        'BTC': 4,
        'ETH': 3,
        'XRP': 2,
        'SOL': 1
    },

    # Correlation filtering (future enhancement)
    'check_correlation': False,      # Enable correlation checks
    'max_correlation': 0.7,          # Don't enter if correlation > 0.7 with existing position

    # Performance monitoring
    'track_portfolio_metrics': True,  # Track Sharpe ratio, max drawdown, etc.
}


# ========== PYRAMIDING CONFIGURATION ==========

PYRAMIDING_CONFIG = {
    'enabled': True,                     # Enable pyramiding (additional entries)
    'max_entries_per_coin': 3,           # Maximum pyramid entries per coin (1st + 2 pyramids)
    'min_score_for_pyramid': 3,          # Require score 3+ for additional entries
    'min_signal_strength_for_pyramid': 0.7,  # Require high signal strength (0-1)
    'position_size_multiplier': [1.0, 0.5, 0.25],  # 100%, 50%, 25% of base amount
    'min_price_increase_pct': 2.0,       # Only pyramid if price increased 2%+ from last entry
    'allow_pyramid_in_regime': ['bullish', 'neutral'],  # Only pyramid in these regimes
}


# ========== PER-COIN POSITION SIZING ==========

POSITION_SIZING_CONFIG = {
    'base_amount_krw': 50000,    # Base position size per coin
    'min_amount_krw': 10000,     # Minimum order (Bithumb limit)
    'max_amount_krw': 100000,    # Maximum per coin
    'use_atr_scaling': True,     # Scale position size based on ATR volatility
}


# ========== EXECUTION CONFIGURATION (Ver3 Override) ==========

EXECUTION_CONFIG = {
    'mode': 'live',                  # 'backtest' or 'live'
    'dry_run': False,                # Live trading mode (actual orders)
    'confirmation_required': False,  # Don't require confirmation (portfolio auto-decides)
    'thread_safe': True,             # Enable thread-safe execution
}


# ========== TRADING CONFIGURATION (Ver3 Multi-Coin) ==========

TRADING_CONFIG = {
    'symbols': ['BTC', 'ETH', 'XRP'],  # Active trading symbols (multi-coin)
    'available_symbols': AVAILABLE_COINS,  # List of all tradable coins
    'popular_symbols': POPULAR_COINS,      # Popular coins for quick selection
    'trade_amount_krw': 50000,       # KRW amount per trade (per coin)
    'min_trade_amount': 10000,       # Minimum trade size
    'trading_fee_rate': 0.0005,      # 0.05% fee
    'total_capital_krw': 1000000,    # Approximate total capital for risk calculations
}


# ========== SCHEDULE CONFIGURATION (Ver3 Override) ==========

SCHEDULE_CONFIG = {
    'check_interval_seconds': 300,   # 5 minutes (300 seconds) - optimized for 1H candle analysis
    'check_interval_minutes': 5,     # 5 minutes
    'daily_report_time': '23:59',
    'balance_check_interval': 30,    # minutes
}


# ========== LOGGING CONFIGURATION (Ver3 Override) ==========

LOGGING_CONFIG = {
    'log_dir': 'logs',
    'log_level': 'INFO',
    'transaction_log': True,
    'markdown_log': True,
    'portfolio_log': True,          # NEW: Log portfolio-level decisions
    'log_file_prefix': 'ver3',      # Ver3 specific log files
}


# ========== INHERITED CONFIGURATIONS FROM VER2 ==========

# These configurations are inherited from Ver2 and used by individual coin monitors
TIMEFRAME_CONFIG = VER2_TIMEFRAME_CONFIG.copy()
REGIME_FILTER_CONFIG = VER2_REGIME_FILTER_CONFIG.copy()
ENTRY_SCORING_CONFIG = VER2_ENTRY_SCORING_CONFIG.copy()
INDICATOR_CONFIG = VER2_INDICATOR_CONFIG.copy()
POSITION_CONFIG = VER2_POSITION_CONFIG.copy()
RISK_CONFIG = VER2_RISK_CONFIG.copy()
EXIT_CONFIG = VER2_EXIT_CONFIG.copy()
CHART_CONFIG = VER2_CHART_CONFIG.copy()
BACKTESTING_CONFIG = VER2_BACKTESTING_CONFIG.copy()
API_CONFIG = VER2_API_CONFIG.copy()
SAFETY_CONFIG = VER2_SAFETY_CONFIG.copy()

# ========== VER3 EXIT CONFIGURATION OVERRIDE ==========

# Override EXIT_CONFIG with dual profit-taking modes
EXIT_CONFIG['profit_target_mode'] = 'bb_based'  # 'bb_based' or 'percentage_based'
EXIT_CONFIG['tp1_percentage'] = 1.5  # First target percentage (only used in percentage mode)
EXIT_CONFIG['tp2_percentage'] = 2.5  # Second target percentage (only used in percentage mode)
EXIT_CONFIG['trail_after_breakeven'] = True  # Move stop to breakeven after first target hit
EXIT_CONFIG['full_exit_at_first_target'] = False  # Set True for bearish regime (dynamic)


# ========== DYNAMIC FACTOR CONFIGURATION ==========

DYNAMIC_FACTOR_CONFIG = {
    # Update frequency settings
    'realtime_update_enabled': True,        # Update ATR-based factors every cycle
    '4h_update_threshold_pct': 15.0,        # ATR change % to trigger 4H factor update
    'daily_update_time': '00:00',           # Daily factor update time
    'weekly_update_day': 6,                 # Sunday (0=Monday, 6=Sunday)

    # Factor bounds (prevent extreme values)
    'chandelier_multiplier_bounds': (2.0, 5.0),
    'position_size_multiplier_bounds': (0.3, 1.5),
    'rsi_threshold_bounds': (20, 40),
    'min_entry_score_bounds': (1, 4),

    # Volatility classification thresholds (ATR%)
    'volatility_levels': {
        'low': 1.5,      # ATR% < 1.5 = low volatility
        'normal': 3.0,   # ATR% < 3.0 = normal volatility
        'high': 5.0,     # ATR% < 5.0 = high volatility
        # Above 5.0 = extreme volatility
    },

    # Regime detection thresholds
    'ema_strong_threshold_pct': 5.0,   # EMA diff % for strong bullish/bearish
    'adx_trending_threshold': 25,       # ADX above this = trending market
    'adx_weak_threshold': 15,           # ADX below this = ranging market
    'neutral_zone_pct': 1.0,            # EMA diff within this = neutral
    'regime_hysteresis_count': 3,       # Consecutive readings for regime switch

    # Performance-based adjustment settings
    'min_trades_for_weekly_update': 5,  # Minimum trades before adjusting weights
    'win_rate_aggressive_threshold': 0.6,  # Above this = can be more aggressive
    'win_rate_conservative_threshold': 0.4,  # Below this = be more conservative

    # Factor persistence
    'factors_file': 'logs/dynamic_factors_v3.json',
    'performance_history_file': 'logs/performance_history_v3.json',
}


# ========== CONFIGURATION FUNCTIONS ==========

def get_version_config(interval: str = '1h', mode: str = None, coins: List[str] = None) -> Dict[str, Any]:
    """
    Get version 3 configuration.

    Args:
        interval: Execution timeframe interval (default: '1h')
        mode: Execution mode ('backtest' or 'live', optional)
        coins: List of coins to trade (optional, uses default if None)

    Returns:
        Dictionary with all version 3 configuration sections
    """
    # Override execution interval if provided
    timeframe_config = TIMEFRAME_CONFIG.copy()
    if interval:
        timeframe_config['execution_interval'] = interval

    # Override execution mode if provided
    execution_config = EXECUTION_CONFIG.copy()
    if mode:
        execution_config['mode'] = mode

    # Override trading symbols if provided
    trading_config = TRADING_CONFIG.copy()
    if coins:
        trading_config['symbols'] = coins

    # Portfolio config
    portfolio_config = PORTFOLIO_CONFIG.copy()
    if coins:
        portfolio_config['default_coins'] = coins
        portfolio_config['max_workers'] = min(len(coins), 4)  # Adjust worker count

    return {
        'VERSION_METADATA': VERSION_METADATA,
        'PORTFOLIO_CONFIG': portfolio_config,
        'PYRAMIDING_CONFIG': PYRAMIDING_CONFIG,
        'POSITION_SIZING_CONFIG': POSITION_SIZING_CONFIG,
        'TIMEFRAME_CONFIG': timeframe_config,
        'REGIME_FILTER_CONFIG': REGIME_FILTER_CONFIG,
        'ENTRY_SCORING_CONFIG': ENTRY_SCORING_CONFIG,
        'INDICATOR_CONFIG': INDICATOR_CONFIG,
        'POSITION_CONFIG': POSITION_CONFIG,
        'RISK_CONFIG': RISK_CONFIG,
        'EXIT_CONFIG': EXIT_CONFIG,
        'CHART_CONFIG': CHART_CONFIG,
        'BACKTESTING_CONFIG': BACKTESTING_CONFIG,
        'EXECUTION_CONFIG': execution_config,
        'API_CONFIG': API_CONFIG,
        'TRADING_CONFIG': trading_config,
        'SAFETY_CONFIG': SAFETY_CONFIG,
        'SCHEDULE_CONFIG': SCHEDULE_CONFIG,
        'LOGGING_CONFIG': LOGGING_CONFIG,
        'DYNAMIC_FACTOR_CONFIG': DYNAMIC_FACTOR_CONFIG,
    }


def validate_portfolio_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate version 3 portfolio configuration.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Validate portfolio config
    if 'PORTFOLIO_CONFIG' in config:
        portfolio = config['PORTFOLIO_CONFIG']

        # Check position limits
        max_pos = portfolio.get('max_positions', 2)
        if max_pos < 1 or max_pos > 10:
            errors.append(f"max_positions must be between 1 and 10 (got {max_pos})")

        # Check coin count
        default_coins = portfolio.get('default_coins', [])
        min_coins = portfolio.get('min_coins', 1)
        max_coins = portfolio.get('max_coins', 4)

        if len(default_coins) < min_coins:
            errors.append(f"default_coins ({len(default_coins)}) less than min_coins ({min_coins})")

        if len(default_coins) > max_coins:
            errors.append(f"default_coins ({len(default_coins)}) exceeds max_coins ({max_coins})")

        # Check risk percentage
        max_risk = portfolio.get('max_portfolio_risk_pct', 6.0)
        if max_risk <= 0 or max_risk > 20:
            errors.append(f"max_portfolio_risk_pct should be between 0 and 20 (got {max_risk})")

        # Check entry priority
        priority = portfolio.get('entry_priority', 'score')
        if priority not in ['score', 'volatility', 'volume']:
            errors.append(f"entry_priority must be 'score', 'volatility', or 'volume' (got '{priority}')")

    # Validate position sizing
    if 'POSITION_SIZING_CONFIG' in config:
        sizing = config['POSITION_SIZING_CONFIG']

        base = sizing.get('base_amount_krw', 50000)
        min_amt = sizing.get('min_amount_krw', 10000)
        max_amt = sizing.get('max_amount_krw', 100000)

        if base < min_amt:
            errors.append(f"base_amount_krw ({base}) less than min_amount_krw ({min_amt})")

        if base > max_amt:
            errors.append(f"base_amount_krw ({base}) exceeds max_amount_krw ({max_amt})")

    # Validate trading symbols
    if 'TRADING_CONFIG' in config:
        trading = config['TRADING_CONFIG']
        symbols = trading.get('symbols', [])

        if not symbols:
            errors.append("symbols list cannot be empty")

        # Check if symbols are valid
        available = trading.get('available_symbols', AVAILABLE_COINS)
        for symbol in symbols:
            if symbol not in available:
                errors.append(f"Symbol '{symbol}' not in available_symbols: {available}")

    is_valid = len(errors) == 0
    return is_valid, errors


def get_portfolio_config() -> Dict[str, Any]:
    """
    Get portfolio configuration.

    Returns:
        Portfolio configuration dictionary
    """
    return PORTFOLIO_CONFIG.copy()


def list_available_coins() -> List[str]:
    """
    Get list of available coins for multi-coin trading.

    Returns:
        List of cryptocurrency symbols
    """
    return AVAILABLE_COINS.copy()


def update_active_coins(coins: List[str]) -> Dict[str, Any]:
    """
    Update active trading coins.

    Args:
        coins: List of coin symbols to activate

    Returns:
        Updated PORTFOLIO_CONFIG

    Raises:
        ValueError: If any coin is not in AVAILABLE_COINS
    """
    for coin in coins:
        if coin not in AVAILABLE_COINS:
            raise ValueError(f"Coin '{coin}' not available. Available: {AVAILABLE_COINS}")

    if len(coins) < PORTFOLIO_CONFIG['min_coins']:
        raise ValueError(f"Must select at least {PORTFOLIO_CONFIG['min_coins']} coins")

    if len(coins) > PORTFOLIO_CONFIG['max_coins']:
        raise ValueError(f"Cannot select more than {PORTFOLIO_CONFIG['max_coins']} coins")

    PORTFOLIO_CONFIG['default_coins'] = coins
    PORTFOLIO_CONFIG['max_workers'] = min(len(coins), 4)

    return PORTFOLIO_CONFIG.copy()
