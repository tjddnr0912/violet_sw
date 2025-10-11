"""
Version 2 Strategy: Multi-Timeframe Stability-Focused Trading

This module implements a dual-timeframe trading strategy:
- Daily timeframe: EMA 50/200 Golden Cross for market regime filtering
- 4H timeframe: Score-based entry system with Bollinger Bands, RSI, and Stochastic RSI
- Risk management: ATR-based Chandelier Exit with split position management
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

# Import from lib structure
from lib.api.bithumb_api import get_candlestick, get_ticker
from lib.core.logger import TradingLogger
from lib.interfaces.version_interface import VersionInterface

# Import version 2 config
from .config_v2 import (
    get_version_config,
    validate_version_config,
    VERSION_METADATA,
)
from lib.core.config_common import merge_configs, get_common_config


class StrategyV2(VersionInterface):
    """
    Version 2: Multi-Timeframe Stability-Focused Strategy

    Strategy Logic:
    1. Market Regime Filter (Daily): Only trade when EMA50 > EMA200 (Golden Cross)
    2. Entry Scoring (4H): Score-based system (need 3+ points)
       - BB lower touch: +1
       - RSI < 30: +1
       - Stoch RSI bullish cross below 20: +2
    3. Position Management: Split entry (50%), partial exits at BB mid/upper
    4. Stop-Loss: ATR-based Chandelier Exit with breakeven adjustment
    """

    VERSION_NAME = VERSION_METADATA['name']
    VERSION_DISPLAY_NAME = VERSION_METADATA['display_name']
    VERSION_DESCRIPTION = VERSION_METADATA['description']
    VERSION_AUTHOR = VERSION_METADATA['author']
    VERSION_DATE = VERSION_METADATA['date']

    def __init__(self, config: Optional[Dict[str, Any]] = None, logger: Optional[TradingLogger] = None):
        """
        Initialize Version 2 Strategy.

        Args:
            config: Optional configuration overrides
            logger: Optional TradingLogger instance
        """
        # Merge configurations: common + version + override
        common = get_common_config()
        version = get_version_config()
        configs = [common, version]
        if config:
            configs.append(config)

        self.config = merge_configs(*configs)

        # Initialize logger
        if logger:
            self.logger = logger
        else:
            log_config = self.config.get('LOGGING_CONFIG', {})
            self.logger = TradingLogger(log_dir=log_config.get('log_dir', 'logs'))

        # Extract configuration sections
        self.timeframe_config = self.config.get('TIMEFRAME_CONFIG', {})
        self.regime_config = self.config.get('REGIME_FILTER_CONFIG', {})
        self.scoring_config = self.config.get('ENTRY_SCORING_CONFIG', {})
        self.indicator_config = self.config.get('INDICATOR_CONFIG', {})
        self.position_config = self.config.get('POSITION_CONFIG', {})
        self.risk_config = self.config.get('RISK_CONFIG', {})
        self.exit_config = self.config.get('EXIT_CONFIG', {})

        # Validate configuration
        is_valid, errors = validate_version_config(self.config)
        if not is_valid:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            self.logger.log_error("Strategy V2 initialization error", Exception(error_msg))
            raise ValueError(error_msg)

        self.logger.logger.info(f"Strategy V2 initialized: {self.VERSION_DISPLAY_NAME}")

    # ========================================
    # VersionInterface Implementation
    # ========================================

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config

    def get_indicator_names(self) -> List[str]:
        """Get list of indicator names used in this version."""
        return [
            'ema_fast',
            'ema_slow',
            'bb_upper',
            'bb_middle',
            'bb_lower',
            'rsi',
            'stoch_rsi_k',
            'stoch_rsi_d',
            'atr',
            'chandelier_stop',
        ]

    def get_supported_intervals(self) -> List[str]:
        """Get supported candlestick intervals."""
        return ['4h', '24h']  # Execution and regime timeframes (Bithumb uses '24h' not '1d')

    def validate_configuration(self) -> Tuple[bool, List[str]]:
        """Validate current configuration."""
        return validate_version_config(self.config)

    def get_chart_config(self) -> Dict[str, Any]:
        """Get chart configuration for GUI."""
        return self.config.get('CHART_CONFIG', {})

    def analyze_market(self, coin_symbol: str, interval: str = "4h", limit: int = 200) -> Dict[str, Any]:
        """
        Analyze market using dual timeframe strategy.

        Args:
            coin_symbol: Cryptocurrency symbol (e.g., 'BTC')
            interval: Execution timeframe (default: '4h')
            limit: Number of candles to analyze

        Returns:
            Dictionary containing analysis results
        """
        try:
            # Step 1: Fetch data for both timeframes
            regime_interval = self.timeframe_config.get('regime_interval', '24h')  # Bithumb uses '24h' not '1d'
            regime_limit = self.timeframe_config.get('regime_candles', 250)

            # Fetch daily data for regime filter
            regime_df = get_candlestick(coin_symbol, regime_interval)
            if regime_df is None or len(regime_df) < 200:
                return {
                    'action': 'HOLD',
                    'signal_strength': 0.0,
                    'reason': 'Insufficient daily data for regime analysis',
                    'market_regime': 'unknown',
                    'entry_score': 0,
                }

            # Fetch execution timeframe data
            exec_df = get_candlestick(coin_symbol, interval)
            if exec_df is None or len(exec_df) < 50:
                return {
                    'action': 'HOLD',
                    'signal_strength': 0.0,
                    'reason': 'Insufficient execution timeframe data',
                    'market_regime': 'unknown',
                    'entry_score': 0,
                }

            # Step 2: Determine market regime (Daily timeframe)
            regime_df = self._calculate_regime_indicators(regime_df)
            market_regime = self._determine_market_regime(regime_df)

            # Step 3: If not bullish regime, do not enter
            if market_regime != 'bullish':
                return {
                    'action': 'HOLD',
                    'signal_strength': 0.0,
                    'reason': f'Market regime is {market_regime}, only trading in bullish regime',
                    'market_regime': market_regime,
                    'entry_score': 0,
                    'regime_data': self._get_regime_data(regime_df),
                    'price_data': exec_df,
                }

            # Step 4: Calculate technical indicators (4H timeframe)
            exec_df = self._calculate_execution_indicators(exec_df)

            # Step 5: Calculate entry score
            entry_score, score_details = self._calculate_entry_score(exec_df)

            # Step 6: Determine action based on entry score
            min_score = self.scoring_config.get('min_entry_score', 3)

            if entry_score >= min_score:
                action = 'BUY'
                signal_strength = entry_score / 4.0  # Normalize to 0-1 (max score is 4)
                reason = f'Entry score {entry_score}/4 (min: {min_score}). {score_details}'
            else:
                action = 'HOLD'
                signal_strength = 0.0
                reason = f'Entry score {entry_score}/4 below threshold {min_score}. {score_details}'

            # Step 7: Calculate stop-loss and targets
            stop_loss_price = self._calculate_chandelier_stop(exec_df)
            target_prices = self._calculate_target_prices(exec_df)

            # Get current price
            current_price = float(exec_df['close'].iloc[-1])

            return {
                'action': action,
                'signal_strength': signal_strength,
                'reason': reason,
                'market_regime': market_regime,
                'entry_score': entry_score,
                'score_details': score_details,
                'current_price': current_price,
                'stop_loss_price': stop_loss_price,
                'target_prices': target_prices,
                'regime_data': self._get_regime_data(regime_df),
                'execution_data': self._get_execution_data(exec_df),
                'price_data': exec_df,
                'indicators': self._get_latest_indicators(exec_df),
            }

        except Exception as e:
            self.logger.log_error(f"Market analysis failed for {coin_symbol}", e)
            return {
                'action': 'HOLD',
                'signal_strength': 0.0,
                'reason': f'Analysis error: {str(e)}',
                'market_regime': 'error',
                'entry_score': 0,
            }

    # ========================================
    # Regime Filter (Daily Timeframe)
    # ========================================

    def _calculate_regime_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate regime filter indicators (Daily EMA 50/200)."""
        ema_fast = self.regime_config.get('ema_fast', 50)
        ema_slow = self.regime_config.get('ema_slow', 200)

        df['ema_fast'] = df['close'].ewm(span=ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=ema_slow, adjust=False).mean()

        return df

    def _determine_market_regime(self, df: pd.DataFrame) -> str:
        """
        Determine market regime based on EMA Golden/Death Cross.

        Returns:
            'bullish' if EMA50 > EMA200 (Golden Cross)
            'bearish' if EMA50 <= EMA200 (Death Cross)
        """
        if df is None or len(df) < 200:
            return 'unknown'

        latest_ema_fast = df['ema_fast'].iloc[-1]
        latest_ema_slow = df['ema_slow'].iloc[-1]

        if pd.isna(latest_ema_fast) or pd.isna(latest_ema_slow):
            return 'unknown'

        if latest_ema_fast > latest_ema_slow:
            return 'bullish'
        else:
            return 'bearish'

    def _get_regime_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract regime data for reporting."""
        if df is None or len(df) == 0:
            return {}

        return {
            'ema_fast': float(df['ema_fast'].iloc[-1]) if 'ema_fast' in df.columns else None,
            'ema_slow': float(df['ema_slow'].iloc[-1]) if 'ema_slow' in df.columns else None,
            'current_price': float(df['close'].iloc[-1]),
        }

    # ========================================
    # Execution Indicators (4H Timeframe)
    # ========================================

    def _calculate_execution_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all execution indicators for entry/exit signals."""
        # Bollinger Bands
        bb_period = self.indicator_config.get('bb_period', 20)
        bb_std = self.indicator_config.get('bb_std', 2.0)
        df['bb_middle'] = df['close'].rolling(window=bb_period).mean()
        bb_stddev = df['close'].rolling(window=bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_stddev * bb_std)
        df['bb_lower'] = df['bb_middle'] - (bb_stddev * bb_std)

        # RSI
        df['rsi'] = self._calculate_rsi(df, self.indicator_config.get('rsi_period', 14))

        # Stochastic RSI
        stoch_rsi_k, stoch_rsi_d = self._calculate_stochastic_rsi(
            df,
            rsi_period=self.indicator_config.get('stoch_rsi_period', 14),
            stoch_period=self.indicator_config.get('stoch_period', 14),
            k_smooth=self.indicator_config.get('stoch_k_smooth', 3),
            d_smooth=self.indicator_config.get('stoch_d_smooth', 3)
        )
        df['stoch_rsi_k'] = stoch_rsi_k
        df['stoch_rsi_d'] = stoch_rsi_d

        # ATR
        df['atr'] = self._calculate_atr(df, self.indicator_config.get('atr_period', 14))

        return df

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate RSI indicator."""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        # Prevent division by zero
        loss = loss.replace(0, 1e-10)
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        # Clip to valid range and fill NaN
        rsi = rsi.clip(0, 100).fillna(50)
        return rsi

    def _calculate_stochastic_rsi(
        self,
        df: pd.DataFrame,
        rsi_period: int = 14,
        stoch_period: int = 14,
        k_smooth: int = 3,
        d_smooth: int = 3
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Calculate Stochastic RSI indicator.

        Returns:
            Tuple of (%K, %D) series
        """
        # First calculate RSI
        rsi = self._calculate_rsi(df, rsi_period)

        # Calculate Stochastic of RSI
        rsi_min = rsi.rolling(window=stoch_period).min()
        rsi_max = rsi.rolling(window=stoch_period).max()

        # Prevent division by zero
        rsi_range = rsi_max - rsi_min
        rsi_range = rsi_range.replace(0, 1e-10)

        # %K line (raw stochastic)
        stoch_k = 100 * (rsi - rsi_min) / rsi_range

        # Smooth %K
        stoch_k = stoch_k.rolling(window=k_smooth).mean()

        # %D line (smoothed %K)
        stoch_d = stoch_k.rolling(window=d_smooth).mean()

        # Fill NaN and clip to 0-100
        stoch_k = stoch_k.clip(0, 100).fillna(50)
        stoch_d = stoch_d.clip(0, 100).fillna(50)

        return stoch_k, stoch_d

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range (ATR)."""
        high = df['high']
        low = df['low']
        close = df['close']

        # True Range components
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        # True Range is the max of the three
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # ATR is the rolling mean of True Range
        atr = tr.rolling(window=period).mean()
        return atr.fillna(0)

    # ========================================
    # Entry Scoring System
    # ========================================

    def _calculate_entry_score(self, df: pd.DataFrame) -> Tuple[int, str]:
        """
        Calculate entry score based on scoring rules.

        Returns:
            Tuple of (total_score, details_string)
            details_string format: "BB:1✓, RSI:0✗, Stoch:0✗" (shows points earned per criterion)
        """
        if df is None or len(df) < 2:
            return 0, "Insufficient data"

        score = 0
        details = []
        rules = self.scoring_config.get('scoring_rules', {})

        latest = df.iloc[-1]
        previous = df.iloc[-2]

        # Condition 1: BB lower touch (+1 point)
        if rules.get('bb_touch', {}).get('enabled', True):
            bb_points = rules['bb_touch']['points']
            if latest['low'] <= latest['bb_lower']:
                score += bb_points
                details.append(f"BB:{bb_points}✓")
            else:
                details.append(f"BB:0✗")

        # Condition 2: RSI oversold (+1 point)
        if rules.get('rsi_oversold', {}).get('enabled', True):
            rsi_points = rules['rsi_oversold']['points']
            rsi_threshold = self.indicator_config.get('rsi_oversold', 30)
            if latest['rsi'] < rsi_threshold:
                score += rsi_points
                details.append(f"RSI:{rsi_points}✓")
            else:
                details.append(f"RSI:0✗")

        # Condition 3: Stochastic RSI bullish cross below 20 (+2 points)
        if rules.get('stoch_rsi_cross', {}).get('enabled', True):
            stoch_points = rules['stoch_rsi_cross']['points']
            stoch_threshold = self.indicator_config.get('stoch_oversold', 20)

            # Check for bullish cross: %K crosses above %D
            k_cross_above = (
                previous['stoch_rsi_k'] <= previous['stoch_rsi_d'] and
                latest['stoch_rsi_k'] > latest['stoch_rsi_d']
            )

            # Both must be below threshold
            both_below_threshold = (
                latest['stoch_rsi_k'] < stoch_threshold and
                latest['stoch_rsi_d'] < stoch_threshold
            )

            if k_cross_above and both_below_threshold:
                score += stoch_points
                details.append(f"Stoch:{stoch_points}✓")
            else:
                details.append(f"Stoch:0✗")

        details_str = ", ".join(details)
        return score, details_str

    # ========================================
    # Stop-Loss and Targets
    # ========================================

    def _calculate_chandelier_stop(self, df: pd.DataFrame) -> float:
        """
        Calculate Chandelier Exit stop-loss price.

        Formula: Highest High - (ATR × Multiplier)
        """
        if df is None or len(df) < 14:
            return 0.0

        # Use ATR period to determine lookback for highest high
        atr_period = self.indicator_config.get('atr_period', 14)
        multiplier = self.indicator_config.get('chandelier_multiplier', 3.0)

        latest_atr = df['atr'].iloc[-1]
        highest_high = df['high'].iloc[-atr_period:].max()

        chandelier_stop = highest_high - (latest_atr * multiplier)
        return float(chandelier_stop)

    def _calculate_target_prices(self, df: pd.DataFrame, entry_price: Optional[float] = None) -> Dict[str, float]:
        """
        Calculate target prices for partial exits.

        Supports two modes:
        1. BB-based: Use Bollinger Band levels (middle, upper)
        2. Percentage-based: Use percentage gains from entry price

        Args:
            df: Price DataFrame with indicators
            entry_price: Entry price (required for percentage-based mode)

        Returns:
            Dictionary with first_target, second_target, stop_loss
        """
        if df is None or len(df) == 0:
            return {}

        latest = df.iloc[-1]
        current_price = float(latest['close'])

        # Get profit target mode from config
        profit_mode = self.exit_config.get('profit_target_mode', 'bb_based')

        if profit_mode == 'percentage_based':
            # Use percentage-based targets
            tp1_pct = self.exit_config.get('tp1_percentage', 1.5)
            tp2_pct = self.exit_config.get('tp2_percentage', 2.5)

            # Use entry_price if provided, otherwise use current price as fallback
            base_price = entry_price if entry_price is not None else current_price

            first_target = base_price * (1 + tp1_pct / 100.0)
            second_target = base_price * (1 + tp2_pct / 100.0)

            return {
                'first_target': float(first_target),
                'second_target': float(second_target),
                'stop_loss': self._calculate_chandelier_stop(df),
                'mode': 'percentage_based',
                'tp1_pct': tp1_pct,
                'tp2_pct': tp2_pct,
            }
        else:
            # Default: BB-based targets
            return {
                'first_target': float(latest['bb_middle']),   # Exit 50% at BB middle
                'second_target': float(latest['bb_upper']),   # Exit remaining at BB upper
                'stop_loss': self._calculate_chandelier_stop(df),
                'mode': 'bb_based',
            }

    # ========================================
    # Data Extraction
    # ========================================

    def _get_execution_data(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Extract execution timeframe data for reporting."""
        if df is None or len(df) == 0:
            return {}

        latest = df.iloc[-1]
        return {
            'bb_upper': float(latest['bb_upper']),
            'bb_middle': float(latest['bb_middle']),
            'bb_lower': float(latest['bb_lower']),
            'rsi': float(latest['rsi']),
            'stoch_rsi_k': float(latest['stoch_rsi_k']),
            'stoch_rsi_d': float(latest['stoch_rsi_d']),
            'atr': float(latest['atr']),
            'current_price': float(latest['close']),
        }

    def _get_latest_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        """Get latest indicator values for display."""
        if df is None or len(df) == 0:
            return {}

        latest = df.iloc[-1]
        return {
            indicator: float(latest.get(indicator, 0))
            for indicator in self.get_indicator_names()
            if indicator in latest.index
        }
