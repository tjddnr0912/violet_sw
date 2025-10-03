"""
Version 1 Configuration - Elite 8-Indicator Strategy

This module contains configuration specific to Version 1 of the trading strategy,
which uses 8 technical indicators with weighted signal combination.
"""

from typing import Dict, Any


# Version Metadata
VERSION_METADATA = {
    "name": "ver1",
    "display_name": "Elite 8-Indicator Strategy",
    "description": "Advanced strategy using 8 technical indicators (MA, RSI, BB, Volume, MACD, ATR, Stochastic, ADX) with weighted signal combination and market regime detection",
    "author": "Trading Bot Team",
    "date": "2025-10",
}


# Indicator Configuration
INDICATOR_CONFIG = {
    # Default candlestick interval
    'candlestick_interval': '1h',

    # Moving Averages
    'short_ma_window': 20,
    'long_ma_window': 50,

    # RSI
    'rsi_period': 14,
    'rsi_overbought': 70,
    'rsi_oversold': 30,
    'rsi_buy_threshold': 30,
    'rsi_sell_threshold': 70,

    # Bollinger Bands
    'bb_period': 20,
    'bb_std': 2.0,

    # MACD
    'macd_fast': 8,
    'macd_slow': 17,
    'macd_signal': 9,

    # ATR (Average True Range)
    'atr_period': 14,
    'atr_stop_multiplier': 2.0,
    'chandelier_atr_multiplier': 3.0,

    # Stochastic
    'stoch_k_period': 14,
    'stoch_d_period': 3,

    # ADX (Trend Strength)
    'adx_period': 14,
    'adx_trending_threshold': 25,
    'adx_ranging_threshold': 15,

    # Volume
    'volume_window': 20,
    'volume_threshold': 1.5,

    # Advanced features
    'pattern_detection_enabled': True,
    'divergence_lookback': 30,
    'divergence_detection_enabled': True,
    'bb_squeeze_threshold': 0.8,
    'bb_squeeze_lookback': 50,

    # Analysis period
    'analysis_period': 100,

    # Enabled indicators (for GUI control)
    'enabled_indicators': {
        'ma': True,
        'rsi': True,
        'bb': True,
        'volume': True,
        'macd': True,
        'atr': True,
        'stochastic': True,
        'adx': True,
    },
}


# Signal Weights Configuration
SIGNAL_WEIGHTS = {
    'macd': 0.35,
    'ma': 0.25,
    'rsi': 0.20,
    'bb': 0.10,
    'volume': 0.10,
    'pattern': 0.0,  # Candlestick patterns (optional, 0.10-0.15 recommended if enabled)
}


# Market Regime Configuration
REGIME_CONFIG = {
    'confidence_threshold': 0.6,
    'signal_threshold': 0.5,
}


# Risk Configuration
RISK_CONFIG = {
    'max_daily_loss_pct': 3.0,
    'max_consecutive_losses': 3,
    'max_daily_trades': 5,
    'position_risk_pct': 1.0,
}


# Interval Presets - Optimized parameters for different timeframes
INTERVAL_PRESETS = {
    '30m': {
        'short_ma_window': 20,
        'long_ma_window': 50,
        'rsi_period': 9,
        'bb_period': 20,
        'bb_std': 2.5,
        'macd_fast': 8,
        'macd_slow': 17,
        'macd_signal': 9,
        'atr_period': 14,
        'chandelier_atr_multiplier': 3.0,
        'stoch_k_period': 14,
        'stoch_d_period': 3,
        'adx_period': 14,
        'volume_window': 20,
        'divergence_lookback': 30,
        'bb_squeeze_threshold': 0.8,
        'analysis_period': 100,
    },
    '1h': {
        'short_ma_window': 20,
        'long_ma_window': 50,
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0,
        'macd_fast': 8,
        'macd_slow': 17,
        'macd_signal': 9,
        'atr_period': 14,
        'chandelier_atr_multiplier': 3.0,
        'stoch_k_period': 14,
        'stoch_d_period': 3,
        'adx_period': 14,
        'volume_window': 20,
        'divergence_lookback': 30,
        'bb_squeeze_threshold': 0.8,
        'analysis_period': 100,
    },
    '6h': {
        'short_ma_window': 10,
        'long_ma_window': 30,
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'atr_period': 14,
        'chandelier_atr_multiplier': 3.0,
        'stoch_k_period': 14,
        'stoch_d_period': 3,
        'adx_period': 14,
        'volume_window': 10,
        'divergence_lookback': 30,
        'bb_squeeze_threshold': 0.8,
        'analysis_period': 50,
    },
    '12h': {
        'short_ma_window': 7,
        'long_ma_window': 25,
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'atr_period': 14,
        'chandelier_atr_multiplier': 3.0,
        'stoch_k_period': 14,
        'stoch_d_period': 3,
        'adx_period': 14,
        'volume_window': 10,
        'divergence_lookback': 30,
        'bb_squeeze_threshold': 0.8,
        'analysis_period': 40,
    },
    '24h': {
        'short_ma_window': 5,
        'long_ma_window': 20,
        'rsi_period': 14,
        'bb_period': 20,
        'bb_std': 2.0,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'atr_period': 14,
        'chandelier_atr_multiplier': 3.0,
        'stoch_k_period': 14,
        'stoch_d_period': 3,
        'adx_period': 14,
        'volume_window': 10,
        'divergence_lookback': 30,
        'bb_squeeze_threshold': 0.8,
        'analysis_period': 30,
    },
}


# Chart Configuration
CHART_CONFIG = {
    'colors': {
        'candle_up': 'red',
        'candle_down': 'blue',
        'ma_short': 'orange',
        'ma_long': 'purple',
        'bb_band': 'gray',
        'bb_fill': 'gray',
        'rsi_line': 'purple',
        'rsi_overbought': 'red',
        'rsi_oversold': 'blue',
        'macd_line': 'blue',
        'macd_signal': 'red',
        'macd_histogram_pos': 'green',
        'macd_histogram_neg': 'red',
        'volume_up': 'red',
        'volume_down': 'blue',
    },
}


# Multi-Chart Configuration
MULTI_CHART_CONFIG = {
    'refresh_interval_seconds': 15,
    'cache_ttl_seconds': 15,
    'api_rate_limit_seconds': 1.0,
    'chart_width_pixels': 400,
    'chart_height_pixels': 600,
    'default_column1_interval': '1h',
    'available_intervals': ['30m', '1h', '6h', '12h', '24h'],
    'max_candles_per_chart': 200,
    'debounce_delay_ms': 200,
}


def get_version_config(interval: str = '1h') -> Dict[str, Any]:
    """
    Get version 1 configuration with interval-specific parameters.

    Args:
        interval: Candlestick interval (e.g., '1h', '30m')

    Returns:
        Dictionary with all version 1 configuration sections
    """
    # Get base indicator config
    indicator_config = INDICATOR_CONFIG.copy()

    # Override with interval-specific presets if available
    if interval in INTERVAL_PRESETS:
        indicator_config.update(INTERVAL_PRESETS[interval])

    # Add interval to indicator config
    indicator_config['candlestick_interval'] = interval

    return {
        'VERSION_METADATA': VERSION_METADATA,
        'INDICATOR_CONFIG': indicator_config,
        'SIGNAL_WEIGHTS': SIGNAL_WEIGHTS,
        'REGIME_CONFIG': REGIME_CONFIG,
        'RISK_CONFIG': RISK_CONFIG,
        'INTERVAL_PRESETS': INTERVAL_PRESETS,
        'CHART_CONFIG': CHART_CONFIG,
        'MULTI_CHART_CONFIG': MULTI_CHART_CONFIG,
    }


def validate_version_config(config: Dict[str, Any]) -> bool:
    """
    Validate version 1 configuration.

    Args:
        config: Configuration dictionary to validate

    Returns:
        True if valid, False otherwise
    """
    # Validate signal weights sum close to 1.0
    if 'SIGNAL_WEIGHTS' in config:
        weights = config['SIGNAL_WEIGHTS']
        total = sum(weights.values())
        if not (0.9 <= total <= 1.1):
            print(f"⚠️ Warning: Signal weights sum to {total:.2f}, expected ~1.0")
            return False

    # Validate threshold values are in valid ranges
    if 'REGIME_CONFIG' in config:
        regime = config['REGIME_CONFIG']
        if not (0.0 <= regime.get('confidence_threshold', 0.6) <= 1.0):
            print("❌ Error: confidence_threshold must be between 0.0 and 1.0")
            return False
        if not (-1.0 <= regime.get('signal_threshold', 0.5) <= 1.0):
            print("❌ Error: signal_threshold must be between -1.0 and 1.0")
            return False

    return True
