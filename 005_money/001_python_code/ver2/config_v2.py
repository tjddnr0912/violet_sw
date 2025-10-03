"""
Version 2 Configuration - Multi-Timeframe Stability-Focused Strategy

This module contains configuration specific to Version 2 of the trading strategy,
which uses dual timeframe analysis (1D for regime, 4H for execution) with
score-based entry system and dynamic risk management.
"""

from typing import Dict, Any, List, Tuple


# Version Metadata
VERSION_METADATA = {
    "name": "ver2",
    "display_name": "Multi-Timeframe Stability Strategy",
    "description": "Dual timeframe strategy using daily EMA regime filter, 4H score-based entry (BB/RSI/StochRSI), and ATR-based Chandelier Exit for stable returns",
    "author": "Trading Bot Team",
    "date": "2025-10",
}


# Multi-Timeframe Configuration
TIMEFRAME_CONFIG = {
    # Primary execution timeframe (for entry/exit signals)
    'execution_interval': '4h',

    # Regime filter timeframe (for market trend analysis)
    'regime_interval': '24h',  # Bithumb API uses '24h' for daily candles, NOT '1d'

    # Data requirements
    'execution_candles': 200,  # Number of 4H candles to fetch
    'regime_candles': 250,     # Number of daily candles to fetch (need 200 for EMA)
}


# Market Regime Filter (Daily Timeframe)
REGIME_FILTER_CONFIG = {
    # EMA Golden Cross parameters
    'ema_fast': 50,   # 50-day EMA
    'ema_slow': 200,  # 200-day EMA

    # Regime classification
    'bullish_regime': 'ema50 > ema200',  # Golden Cross
    'bearish_regime': 'ema50 <= ema200', # Death Cross or neutral

    # Trading permission
    'allow_long_in_bullish': True,
    'allow_long_in_bearish': False,  # Only trade in bullish regime
    'allow_short': False,  # This strategy is long-only
}


# Entry Signal Scoring System (4H Timeframe)
ENTRY_SCORING_CONFIG = {
    # Minimum score required to enter position
    'min_entry_score': 3,

    # Score components
    'scoring_rules': {
        # Condition 1: Price touches Bollinger Band lower (+1 point)
        'bb_touch': {
            'enabled': True,
            'points': 1,
            'condition': 'low <= bb_lower',
        },

        # Condition 2: RSI oversold (+1 point)
        'rsi_oversold': {
            'enabled': True,
            'points': 1,
            'condition': 'rsi < 30',
        },

        # Condition 3: Stochastic RSI bullish cross below 20 (+2 points)
        'stoch_rsi_cross': {
            'enabled': True,
            'points': 2,
            'condition': 'stoch_k crosses above stoch_d AND stoch_k < 20 AND stoch_d < 20',
        },
    },
}


# Technical Indicators Configuration (4H Timeframe)
INDICATOR_CONFIG = {
    # Bollinger Bands (for entry and exit)
    'bb_period': 20,
    'bb_std': 2.0,

    # RSI (for entry confirmation)
    'rsi_period': 14,
    'rsi_oversold': 30,

    # Stochastic RSI (for timing)
    'stoch_rsi_period': 14,      # RSI period for Stochastic calculation
    'stoch_period': 14,           # Stochastic period
    'stoch_k_smooth': 3,          # %K smoothing
    'stoch_d_smooth': 3,          # %D smoothing
    'stoch_oversold': 20,

    # ATR (for stop-loss and volatility)
    'atr_period': 14,
    'chandelier_multiplier': 3.0,  # Chandelier Exit multiplier
}


# Position Management Configuration
POSITION_CONFIG = {
    # Entry strategy
    'initial_position_pct': 50,  # Enter with 50% of calculated size

    # Exit levels (percentage targets)
    'first_target_pct': 50,   # Exit 50% of position at BB mid
    'second_target_pct': 100, # Exit remaining at BB upper

    # Risk per trade (percentage of portfolio)
    'risk_per_trade_pct': 2.0,

    # Position sizing based on ATR
    'use_atr_sizing': True,
}


# Risk Management Configuration
RISK_CONFIG = {
    # Stop-loss configuration
    'stop_loss_type': 'chandelier',  # 'chandelier' or 'fixed'
    'chandelier_atr_multiplier': 3.0,
    'fixed_stop_loss_pct': 5.0,  # Fallback if Chandelier not available

    # Move stop to breakeven after first target
    'breakeven_after_first_target': True,

    # Daily limits
    'max_daily_loss_pct': 3.0,
    'max_consecutive_losses': 3,
    'max_daily_trades': 5,

    # Position limits
    'max_position_size_pct': 10.0,  # Max % of portfolio in single position
}


# Exit Signal Configuration (4H Timeframe)
EXIT_CONFIG = {
    # Partial exit targets
    'first_target': 'bb_middle',   # Exit 50% when price reaches BB middle
    'second_target': 'bb_upper',   # Exit 100% when price reaches BB upper

    # Stop-loss
    'stop_loss': 'chandelier_exit',  # ATR-based trailing stop

    # Trailing stop after breakeven
    'trail_after_breakeven': True,
}


# Chart Configuration
CHART_CONFIG = {
    'colors': {
        'candle_up': 'red',
        'candle_down': 'blue',
        'ema_fast': 'orange',
        'ema_slow': 'purple',
        'bb_band': 'gray',
        'bb_fill': 'lightgray',
        'rsi_line': 'purple',
        'rsi_oversold': 'blue',
        'stoch_k': 'blue',
        'stoch_d': 'orange',
    },

    # Chart indicators to display
    'show_indicators': {
        'ema': True,
        'bb': True,
        'rsi': True,
        'stoch_rsi': True,
        'atr': True,
    },
}


# Backtesting Configuration
BACKTESTING_CONFIG = {
    'initial_capital': 10000.0,  # USD
    'commission': 0.001,          # 0.1% per trade (0.05% entry + 0.05% exit)
    'slippage': 0.0005,          # 0.05% slippage
    'lookback_months': 10,       # 10 months of data
}


# ========== LIVE TRADING CONFIGURATION ==========

# Execution Mode Configuration
EXECUTION_CONFIG = {
    'mode': 'live',  # 'backtest' or 'live'
    'dry_run': False,     # Simulate trades without real execution
    'confirmation_required': True,  # Require confirmation before trades
}


# API Configuration (for live trading)
API_CONFIG = {
    'exchange': 'bithumb',
    'check_interval_seconds': 14400,  # 4 hours (4H timeframe)
    'rate_limit_seconds': 1.0,
    'timeout_seconds': 15,
}


# Trading Configuration (for live trading)
TRADING_CONFIG = {
    'symbol': 'BTC',  # Trading pair
    'trade_amount_krw': 50000,  # KRW amount per trade
    'min_trade_amount': 10000,  # Minimum trade size
    'trading_fee_rate': 0.0005,  # 0.05% fee
}


# Safety Configuration (for live trading)
SAFETY_CONFIG = {
    'dry_run': False,
    'emergency_stop': False,
    'max_daily_trades': 5,
    'max_consecutive_losses': 3,
    'max_daily_loss_pct': 3.0,
    'require_confirmation': True,
    'balance_check_interval': 30,  # minutes
}


# Schedule Configuration (for live trading)
SCHEDULE_CONFIG = {
    'check_interval_seconds': 14400,  # 4 hours (4H candle close)
    'check_interval_minutes': 240,    # 4 hours in minutes
    'daily_report_time': '23:59',
}


# Logging Configuration (for live trading)
LOGGING_CONFIG = {
    'log_dir': 'logs',
    'log_level': 'INFO',
    'transaction_log': True,
    'markdown_log': True,
}


def get_version_config(interval: str = '4h', mode: str = None) -> Dict[str, Any]:
    """
    Get version 2 configuration.

    Args:
        interval: Execution timeframe interval (default: '4h')
        mode: Execution mode ('backtest' or 'live', optional)

    Returns:
        Dictionary with all version 2 configuration sections
    """
    # Override execution interval if provided
    timeframe_config = TIMEFRAME_CONFIG.copy()
    if interval:
        timeframe_config['execution_interval'] = interval

    # Override execution mode if provided
    execution_config = EXECUTION_CONFIG.copy()
    if mode:
        execution_config['mode'] = mode

    return {
        'VERSION_METADATA': VERSION_METADATA,
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
        'TRADING_CONFIG': TRADING_CONFIG,
        'SAFETY_CONFIG': SAFETY_CONFIG,
        'SCHEDULE_CONFIG': SCHEDULE_CONFIG,
        'LOGGING_CONFIG': LOGGING_CONFIG,
    }


def validate_version_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate version 2 configuration.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []

    # Validate entry scoring
    if 'ENTRY_SCORING_CONFIG' in config:
        scoring = config['ENTRY_SCORING_CONFIG']
        min_score = scoring.get('min_entry_score', 3)

        # Calculate max possible score
        max_score = sum(
            rule['points']
            for rule in scoring.get('scoring_rules', {}).values()
            if rule.get('enabled', True)
        )

        if min_score > max_score:
            errors.append(f"min_entry_score ({min_score}) cannot exceed max possible score ({max_score})")

    # Validate position percentages
    if 'POSITION_CONFIG' in config:
        pos = config['POSITION_CONFIG']
        if not (0 < pos.get('initial_position_pct', 50) <= 100):
            errors.append("initial_position_pct must be between 0 and 100")
        if not (0 < pos.get('risk_per_trade_pct', 2.0) <= 10):
            errors.append("risk_per_trade_pct should be between 0 and 10")

    # Validate risk parameters
    if 'RISK_CONFIG' in config:
        risk = config['RISK_CONFIG']
        if risk.get('max_daily_loss_pct', 3.0) <= 0:
            errors.append("max_daily_loss_pct must be positive")
        if risk.get('max_consecutive_losses', 3) < 1:
            errors.append("max_consecutive_losses must be at least 1")

    # Validate EMA periods
    if 'REGIME_FILTER_CONFIG' in config:
        regime = config['REGIME_FILTER_CONFIG']
        if regime.get('ema_fast', 50) >= regime.get('ema_slow', 200):
            errors.append("ema_fast must be less than ema_slow")

    is_valid = len(errors) == 0
    return is_valid, errors
