"""
Base Configuration - Shared Trading Strategy Settings

This module contains the base configuration settings that are shared across
trading strategy versions. These settings define the core trading parameters
for the Bithumb cryptocurrency trading bot.

Migrated from ver2/config_v2.py for ver3 independence.
"""

from typing import Dict, Any, List


# ========== AVAILABLE COINS ==========
# Major cryptocurrencies with high liquidity on Bithumb (updated 2025-10)
# Reduced to 4 major coins for focused trading strategy
AVAILABLE_COINS = [
    'BTC',   # Bitcoin - Market leader, highest liquidity
    'ETH',   # Ethereum - Smart contract platform, 2nd largest
    'XRP',   # Ripple - High volume, fast payment network
    'SOL',   # Solana - Modern L1 blockchain, growing ecosystem
]

# Popular coins are the same as available (all 4 are major liquid assets)
POPULAR_COINS = AVAILABLE_COINS


# ========== TIMEFRAME CONFIGURATION ==========
# Multi-Timeframe Configuration
TIMEFRAME_CONFIG = {
    # Primary execution timeframe (for entry/exit signals)
    'execution_interval': '1h',  # Changed from 4h to 1h for better responsiveness in 24/7 crypto market

    # Regime filter timeframe (for market trend analysis)
    'regime_interval': '24h',  # Bithumb API uses '24h' for daily candles, NOT '1d'

    # Data requirements
    'execution_candles': 200,  # Number of 1H candles to fetch
    'regime_candles': 250,     # Number of daily candles to fetch (need 200 for EMA)
}


# ========== MULTI-TIMEFRAME REGIME CONFIGURATION ==========
# Phase 1: Macro (Daily) + Micro (1H) dual-layer regime system
MULTI_TF_REGIME_CONFIG = {
    'enable_multi_tf_regime': True,   # Phase 1 activated (2026-03-16)

    # Micro regime EMA periods (1H timeframe)
    'micro_ema_fast': 9,
    'micro_ema_slow': 21,
    'micro_slope_threshold': 0.05,   # EMA9 slope % for direction confirmation
    'micro_hysteresis_count': 2,     # Consecutive same-regime readings to confirm

    # RSI convergence (Multi-TF RSI)
    'rsi_convergence_enabled': True,
    'daily_rsi_oversold': 40,        # Daily RSI threshold for oversold zone
    'h1_rsi_oversold': 35,           # 1H RSI threshold for oversold zone
    'divergence_rsi_slope_min': 3.0, # Min 1H RSI increase for divergence detection

    # Composite strategy matrix overrides
    # Key: (macro_regime, micro_regime) -> strategy adjustments
    # Only bear-zone combos listed here; bull/neutral use macro defaults
    'composite_overrides': {
        # === Bearish macro + micro combos (핵심 개선 영역) ===
        ('bearish', 'micro_bullish'): {
            'entry_threshold_modifier': 1.1,
            'position_size_override': 0.6,
            'extreme_oversold_required': False,  # 핵심: 게이트 제거
            'bear_momentum_filter': False,        # 모멘텀 필터도 완화
        },
        ('bearish', 'micro_neutral'): {
            'entry_threshold_modifier': 1.3,
            'position_size_override': 0.5,
            'extreme_oversold_required': True,
            'bear_momentum_filter': True,
        },
        ('bearish', 'micro_bearish'): {
            'entry_threshold_modifier': 2.0,
            'position_size_override': 0.3,
            'extreme_oversold_required': True,
            'bear_momentum_filter': True,
        },
        # === Strong Bearish macro + micro combos ===
        ('strong_bearish', 'micro_bullish'): {
            'entry_threshold_modifier': 1.3,
            'position_size_override': 0.4,
            'extreme_oversold_required': True,
            'bear_momentum_filter': False,        # 반등 중이면 모멘텀 필터 비활성
        },
        ('strong_bearish', 'micro_neutral'): {
            'entry_threshold_modifier': 1.8,
            'position_size_override': 0.3,
            'extreme_oversold_required': True,
            'bear_momentum_filter': True,
        },
        ('strong_bearish', 'micro_bearish'): {
            'entry_threshold_modifier': 2.5,
            'position_size_override': 0.2,
            'extreme_oversold_required': True,
            'bear_momentum_filter': True,
        },
    },
}


# ========== REGIME FILTER CONFIGURATION ==========
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


# ========== ENTRY SCORING CONFIGURATION ==========
# Entry Signal Scoring System (4H Timeframe)
ENTRY_SCORING_CONFIG = {
    # Minimum score required to enter position
    'min_entry_score': 2,  # 3 -> 2

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

        # Condition 4: VWAP cross (+1 point) - Phase 2, gated by enable_vwap_macd
        'vwap_cross': {
            'enabled': True,
            'points': 1,
            'condition': 'price crosses above VWAP',
        },

        # Condition 5: MACD cross (+1 point) - Phase 2, gated by enable_vwap_macd
        'macd_cross': {
            'enabled': True,
            'points': 1,
            'condition': 'MACD crosses above signal line below zero',
        },
    },
}


# ========== INDICATOR CONFIGURATION ==========
# Technical Indicators Configuration (4H Timeframe)
INDICATOR_CONFIG = {
    # Bollinger Bands (for entry and exit)
    'bb_period': 20,
    'bb_std': 2.0,

    # RSI (for entry confirmation)
    'rsi_period': 14,
    'rsi_oversold': 35,  # 30 -> 35

    # Stochastic RSI (for timing)
    'stoch_rsi_period': 14,      # RSI period for Stochastic calculation
    'stoch_period': 14,           # Stochastic period
    'stoch_k_smooth': 3,          # %K smoothing
    'stoch_d_smooth': 3,          # %D smoothing
    'stoch_oversold': 20,

    # ATR (for stop-loss and volatility)
    'atr_period': 14,
    'chandelier_multiplier': 3.0,  # Chandelier Exit multiplier

    # VWAP (Phase 2)
    'vwap_period': 24,           # Rolling VWAP period (24 hours for 1H candles)
    'enable_vwap_macd': True,    # Phase 2 activated (2026-03-16)

    # MACD (Phase 2)
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
}


# ========== POSITION CONFIGURATION ==========
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


# ========== RISK CONFIGURATION ==========
# Risk Management Configuration
RISK_CONFIG = {
    # Stop-loss configuration
    'stop_loss_type': 'chandelier',  # 'chandelier' or 'fixed'
    'chandelier_atr_multiplier': 3.0,
    'fixed_stop_loss_pct': 5.0,  # Fallback if Chandelier not available

    # Move stop to breakeven after first target
    'breakeven_after_first_target': True,

    # Daily limits
    'max_daily_loss_pct': 2.0,
    'max_consecutive_losses': 2,
    'max_daily_trades': 5,

    # Position limits
    'max_position_size_pct': 10.0,  # Max % of portfolio in single position
}


# ========== EXIT CONFIGURATION ==========
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


# ========== CHART CONFIGURATION ==========
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


# ========== BACKTESTING CONFIGURATION ==========
# Backtesting Configuration
BACKTESTING_CONFIG = {
    'initial_capital': 10000.0,  # USD
    'commission': 0.001,          # 0.1% per trade (0.05% entry + 0.05% exit)
    'slippage': 0.0005,          # 0.05% slippage
    'lookback_months': 10,       # 10 months of data
}


# ========== API CONFIGURATION ==========
# API Configuration (for live trading)
API_CONFIG = {
    'exchange': 'bithumb',
    'check_interval_seconds': 14400,  # 4 hours (4H timeframe)
    'rate_limit_seconds': 1.0,
    'timeout_seconds': 15,
}


# ========== SAFETY CONFIGURATION ==========
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


# ========== SCHEDULE CONFIGURATION ==========
# Schedule Configuration (for live trading)
SCHEDULE_CONFIG = {
    'check_interval_seconds': 14400,  # 4 hours (4H candle close)
    'check_interval_minutes': 240,    # 4 hours in minutes
    'daily_report_time': '23:59',
}


# ========== LOGGING CONFIGURATION ==========
# Logging Configuration (for live trading)
LOGGING_CONFIG = {
    'log_dir': 'logs',
    'log_level': 'INFO',
    'transaction_log': True,
    'markdown_log': True,
}


# ========== ADAPTIVE WEIGHT CONFIGURATION ==========
# Phase 3: Performance-based indicator weight adjustment
ADAPTIVE_WEIGHT_CONFIG = {
    'enable_adaptive_weights': True,   # Phase 3 activated (2026-03-16)
    'lookback_trades': 50,             # Number of recent trades to analyze
    'min_trades_per_regime': 5,        # Min trades before adjusting regime-specific weights
    'weight_min': 0.4,                 # Minimum indicator weight
    'weight_max': 2.0,                 # Maximum indicator weight
    'smoothing_factor': 0.3,           # EMA smoothing (0.3 = 30% new + 70% old)
    'rapid_decay_threshold': 3,        # Consecutive failures to trigger rapid weight decay
    'rapid_decay_lookback': 5,         # Recent trades to check for rapid decay
    'rapid_decay_weight': 0.6,         # Weight to apply on rapid decay trigger
    'weights_file': 'logs/adaptive_weights_v3.json',
}


# ========== ORDERBOOK & VOLUME PROFILE CONFIGURATION ==========
# Phase 4: Real-time orderbook and historical volume analysis
ORDERBOOK_CONFIG = {
    'enable_orderbook_analysis': True,   # Phase 4-OB activated (2026-03-16)
    'enable_volume_profile': True,       # Phase 4-VP activated (2026-03-16)
    'orderbook_count': 30,               # Number of orderbook levels to fetch
    'analysis_range_pct': 5.0,           # Price range for bid/ask analysis (±5%)
    'wall_threshold_krw': {              # Min KRW value to consider as a wall (per coin)
        'BTC': 500_000_000,
        'ETH': 200_000_000,
        'XRP': 50_000_000,
        'SOL': 100_000_000,
    },
    'default_wall_threshold_krw': 100_000_000,
    'bid_ask_ratio_strong': 1.5,         # Strong buy pressure threshold
    'bid_ask_ratio_weak': 1.2,           # Weak buy pressure threshold
    # Volume Profile settings
    'vp_lookback': 50,                   # Number of 1H candles for VP
    'vp_num_bins': 30,                   # Price bins for VP
    'vp_value_area_pct': 0.70,           # Value Area percentage (70%)
    'vp_near_va_low_pct': 1.0,          # "Near VA Low" threshold (±1%)
}
