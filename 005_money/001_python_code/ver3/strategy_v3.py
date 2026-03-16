"""
Version 3 Strategy: Multi-Timeframe Stability-Focused Trading with Dynamic Factors

This module implements a dual-timeframe trading strategy with dynamic factor adjustment:
- Daily timeframe: Extended regime detection (6 regimes including bearish mean reversion)
- 4H timeframe: Score-based entry system with dynamic weights
- Risk management: ATR-based dynamic stop-loss with regime-specific adjustments
- Dynamic factors: Real-time, 4H, Daily, Weekly parameter adjustments
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime

# Import from lib structure
from lib.api.bithumb_api import get_candlestick, get_ticker
from lib.core.logger import TradingLogger
from lib.interfaces.version_interface import VersionInterface

# Import version 3 config
from .config_v3 import (
    get_version_config,
    VERSION_METADATA,
)
from lib.core.config_common import merge_configs, get_common_config

# Import dynamic factor system
from .dynamic_factor_manager import get_dynamic_factor_manager, DynamicFactorManager
from .regime_detector import RegimeDetector, ExtendedRegime, MicroRegime


class StrategyV3(VersionInterface):
    """
    Version 3: Multi-Timeframe Strategy with Dynamic Factor Adjustment

    Strategy Logic:
    1. Market Regime Detection (Daily): Extended 6-regime classification
       - Strong Bullish, Bullish, Neutral, Bearish, Strong Bearish, Ranging
    2. Entry Scoring (4H): Dynamic weight-based system
       - BB lower touch: dynamic weight
       - RSI oversold: dynamic weight with dynamic threshold
       - Stoch RSI cross: dynamic weight with dynamic threshold
    3. Regime-Specific Strategy:
       - Bullish: Trend following with BB Upper targets
       - Bearish: Mean reversion with BB Middle targets and full exit
       - Ranging: Oscillation trading with tight stops
    4. Dynamic Factors: ATR-based position sizing and stop-loss adjustments
    """

    VERSION_NAME = VERSION_METADATA['name']
    VERSION_DISPLAY_NAME = VERSION_METADATA['display_name']
    VERSION_DESCRIPTION = VERSION_METADATA['description']
    VERSION_AUTHOR = VERSION_METADATA['author']
    VERSION_DATE = VERSION_METADATA['date']

    def __init__(self, config: Optional[Dict[str, Any]] = None, logger: Optional[TradingLogger] = None):
        """
        Initialize Version 3 Strategy with Dynamic Factors.

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

        # Initialize dynamic factor system
        self.factor_manager = get_dynamic_factor_manager(self.config, self.logger)
        self.regime_detector = RegimeDetector(self.config)

        # Cache for current regime strategy
        self._current_regime = ExtendedRegime.UNKNOWN
        self._current_regime_strategy = {}

        self.logger.logger.info(f"Strategy V3 initialized: {self.VERSION_DISPLAY_NAME}")
        self.logger.logger.info(f"  Dynamic factors enabled: True")

    # ========================================
    # VersionInterface Implementation
    # ========================================

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config

    def get_indicator_names(self) -> List[str]:
        """Get list of indicator names used in this version."""
        base_indicators = [
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

        # Phase 2: Add VWAP/MACD when feature flag is enabled
        enable_vwap_macd = self.indicator_config.get('enable_vwap_macd', False)
        if enable_vwap_macd:
            base_indicators.extend(['vwap', 'macd', 'macd_signal', 'macd_hist'])

        return base_indicators

    def get_supported_intervals(self) -> List[str]:
        """Get supported candlestick intervals."""
        return ['1h', '24h']  # Execution and regime timeframes (Bithumb uses '24h' not '1d')

    def validate_configuration(self) -> Tuple[bool, List[str]]:
        """Validate current configuration."""
        # Configuration validation is handled in config_v3.py
        return True, []

    def get_chart_config(self) -> Dict[str, Any]:
        """Get chart configuration for GUI."""
        return self.config.get('CHART_CONFIG', {})

    def analyze_market(self, coin_symbol: str, interval: str = "1h", limit: int = 200) -> Dict[str, Any]:
        """
        Analyze market using dual timeframe strategy with dynamic factors.

        Args:
            coin_symbol: Cryptocurrency symbol (e.g., 'BTC')
            interval: Execution timeframe (default: '1h')
            limit: Number of candles to analyze

        Returns:
            Dictionary containing analysis results with dynamic factor adjustments
        """
        try:
            # Step 1: Fetch data for both timeframes
            regime_interval = self.timeframe_config.get('regime_interval', '24h')

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

            # Step 2: Calculate technical indicators (4H timeframe)
            exec_df = self._calculate_execution_indicators(exec_df)

            # Step 3: Apply dynamic factors based on ATR
            current_atr = float(exec_df['atr'].iloc[-1])
            current_price = float(exec_df['close'].iloc[-1])
            dynamic_factors = self.factor_manager.update_realtime_factors(
                coin_symbol, current_atr, current_price
            )

            # Step 4: Detect extended market regime (6 regimes)
            regime_df = self._calculate_regime_indicators(regime_df)
            extended_regime, regime_metadata = self.regime_detector.detect_regime(
                regime_df, exec_df, coin=coin_symbol
            )
            self._current_regime = extended_regime
            market_regime = extended_regime.value

            # Step 4b: Phase 1 - Detect micro regime and build composite strategy
            multi_tf_config = self.config.get('MULTI_TF_REGIME_CONFIG', {})
            use_multi_tf = multi_tf_config.get('enable_multi_tf_regime', False)

            micro_regime = MicroRegime.MICRO_NEUTRAL
            micro_metadata = {}
            rsi_convergence_score = 0.0
            rsi_convergence_details = {}

            if use_multi_tf:
                micro_regime, micro_metadata = self.regime_detector.detect_micro_regime(
                    exec_df, coin=coin_symbol
                )
                regime_strategy = self.regime_detector.get_composite_strategy(
                    extended_regime, micro_regime
                )
                rsi_convergence_score, rsi_convergence_details = (
                    self.regime_detector.calc_rsi_convergence(regime_df, exec_df)
                )
                regime_metadata['micro_regime'] = micro_regime.value
                regime_metadata['micro_metadata'] = micro_metadata
                regime_metadata['rsi_convergence'] = rsi_convergence_details

                self.logger.logger.info(
                    f"[MTF] {coin_symbol}: macro={market_regime} micro={micro_regime.value} "
                    f"modifier={regime_strategy['entry_threshold_modifier']:.1f} "
                    f"extreme_os={regime_strategy.get('extreme_oversold_required', True)} "
                    f"rsi_conv={rsi_convergence_score:.1f}"
                )
            else:
                # Feature flag OFF: use original macro-only strategy
                regime_strategy = self.regime_detector.get_regime_strategy(extended_regime)

            self._current_regime_strategy = regime_strategy

            # Update daily factors if regime changed
            self.factor_manager.update_daily_factors(
                market_regime,
                regime_metadata.get('ema_diff_pct', 0.0)
            )

            # Step 6: Check if entry is allowed for this regime
            if not regime_strategy['allow_entry']:
                return {
                    'action': 'HOLD',
                    'signal_strength': 0.0,
                    'reason': f'Entry not allowed in {market_regime} regime',
                    'market_regime': market_regime,
                    'entry_score': 0,
                    'current_price': current_price,
                    'regime_data': self._get_regime_data(regime_df),
                    'regime_metadata': regime_metadata,
                    'dynamic_factors': dynamic_factors,
                    'price_data': exec_df,
                }

            # Step 7a: Crash detection (always active in bear regimes)
            if extended_regime in [ExtendedRegime.BEARISH, ExtendedRegime.STRONG_BEARISH]:
                crash_conditions = self.regime_detector.detect_crash_conditions(exec_df)
                if crash_conditions.get('is_crash', False):
                    return {
                        'action': 'HOLD',
                        'signal_strength': 0.0,
                        'reason': f'🚨 Crash detected: {crash_conditions["conditions_met"]}/3 conditions '
                                  f'(price {crash_conditions["price_change_pct"]:+.1f}%)',
                        'market_regime': market_regime,
                        'entry_score': 0,
                        'current_price': current_price,
                        'crash_conditions': crash_conditions,
                        'regime_data': self._get_regime_data(regime_df),
                        'regime_metadata': regime_metadata,
                        'dynamic_factors': dynamic_factors,
                        'price_data': exec_df,
                    }

            # Step 7b: Momentum filter (controlled by composite strategy)
            apply_momentum_filter = regime_strategy.get('bear_momentum_filter', True)
            if extended_regime in [ExtendedRegime.BEARISH, ExtendedRegime.STRONG_BEARISH]:
                if apply_momentum_filter:
                    momentum_blocked, momentum_reason = self._check_bear_momentum_filter(exec_df)
                    if momentum_blocked:
                        return {
                            'action': 'HOLD',
                            'signal_strength': 0.0,
                            'reason': f'Momentum filter: {momentum_reason}',
                            'market_regime': market_regime,
                            'entry_score': 0,
                            'current_price': current_price,
                            'regime_data': self._get_regime_data(regime_df),
                            'regime_metadata': regime_metadata,
                            'dynamic_factors': dynamic_factors,
                            'price_data': exec_df,
                        }

            # Step 8: Calculate entry score with dynamic weights
            entry_score, score_details = self._calculate_entry_score_dynamic(exec_df)

            # Phase 1: Add RSI convergence bonus to entry score
            if use_multi_tf and rsi_convergence_score > 0:
                entry_score += rsi_convergence_score
                score_details += f", RSI conv +{rsi_convergence_score:.1f}"

            # Step 8b: Apply regime-specific entry threshold modifier
            base_min_score = self.scoring_config.get('min_entry_score', 2)
            adjusted_min_score = max(1, min(4, int(
                base_min_score * regime_strategy['entry_threshold_modifier']
            )))

            # Step 9: For bearish regimes, check extreme oversold (controlled by composite)
            require_extreme_os = regime_strategy.get('extreme_oversold_required', True)
            if extended_regime in [ExtendedRegime.BEARISH, ExtendedRegime.STRONG_BEARISH]:
                if require_extreme_os:
                    bearish_conditions = self.regime_detector.get_bearish_entry_conditions(exec_df)
                    if not bearish_conditions.get('is_extreme_oversold', False):
                        return {
                            'action': 'HOLD',
                            'signal_strength': 0.0,
                            'reason': f'Not extreme oversold for {market_regime} entry. '
                                      f'({bearish_conditions.get("extreme_condition_count", 0)}/3 conditions)',
                            'market_regime': market_regime,
                            'entry_score': entry_score,
                            'score_details': score_details,
                            'current_price': current_price,
                            'regime_data': self._get_regime_data(regime_df),
                            'regime_metadata': regime_metadata,
                            'bearish_conditions': bearish_conditions,
                            'dynamic_factors': dynamic_factors,
                            'price_data': exec_df,
                        }

            # Step 10: Determine action based on adjusted entry score
            # Phase 2: max score is 6.0 when VWAP/MACD is enabled, else 4.0
            enable_vwap_macd = self.indicator_config.get('enable_vwap_macd', False)
            max_score = 6.0 if enable_vwap_macd else 4.0

            if entry_score >= adjusted_min_score:
                action = 'BUY'
                signal_strength = min(1.0, entry_score / max_score)
                regime_label = market_regime
                if use_multi_tf:
                    regime_label = f"{market_regime}+{micro_regime.value}"
                reason = (f'Entry score {entry_score:.1f}/{max_score:.0f} >= {adjusted_min_score} '
                         f'({regime_label} regime). {score_details}')
            else:
                action = 'HOLD'
                signal_strength = 0.0
                regime_label = market_regime
                if use_multi_tf:
                    regime_label = f"{market_regime}+{micro_regime.value}"
                reason = (f'Entry score {entry_score:.1f}/{max_score:.0f} < {adjusted_min_score} '
                         f'({regime_label} regime). {score_details}')

            # Step 11: Calculate stop-loss with dynamic multiplier
            stop_loss_price = self._calculate_chandelier_stop_dynamic(exec_df, regime_strategy)

            # Step 12: Calculate targets based on regime
            target_prices = self._calculate_target_prices_dynamic(exec_df, regime_strategy)

            # Step 13: Get bearish conditions for all regimes (for display purposes)
            bearish_conditions = self.regime_detector.get_bearish_entry_conditions(exec_df)

            result = {
                'action': action,
                'signal_strength': signal_strength,
                'reason': reason,
                'market_regime': market_regime,
                'extended_regime': extended_regime.value,
                'entry_score': entry_score,
                'adjusted_min_score': adjusted_min_score,
                'score_details': score_details,
                'current_price': current_price,
                'stop_loss_price': stop_loss_price,
                'target_prices': target_prices,
                'regime_data': self._get_regime_data(regime_df),
                'regime_metadata': regime_metadata,
                'regime_strategy': regime_strategy,
                'execution_data': self._get_execution_data(exec_df),
                'dynamic_factors': dynamic_factors,
                'price_data': exec_df,
                'indicators': self._get_latest_indicators(exec_df),
                'entry_conditions': self._get_entry_conditions(entry_score, exec_df),
                'bearish_conditions': bearish_conditions,
            }

            # Phase 1: Add composite regime info to result
            if use_multi_tf:
                result['micro_regime'] = micro_regime.value
                result['micro_metadata'] = micro_metadata
                result['rsi_convergence'] = rsi_convergence_details
                result['position_size_override'] = regime_strategy.get('position_size_override')

            # Phase 4: Orderbook confirmation (only when BUY signal fires)
            orderbook_config = self.config.get('ORDERBOOK_CONFIG', {})
            if result['action'] == 'BUY' and orderbook_config.get('enable_orderbook_analysis', False):
                try:
                    from lib.api.bithumb_api import get_orderbook
                    ob_count = orderbook_config.get('orderbook_count', 30)
                    orderbook = get_orderbook(coin_symbol, ob_count)
                    if orderbook is not None:
                        ob_signal = self._analyze_orderbook(orderbook, current_price, coin_symbol)
                        result['orderbook_signal'] = ob_signal

                        if 'error' not in ob_signal:
                            # Block entry: strong ask wall without offsetting bid support
                            if ob_signal.get('large_ask_wall') and not ob_signal.get('large_bid_wall'):
                                result['action'] = 'HOLD'
                                result['signal_strength'] = 0.0
                                ratio = ob_signal.get('bid_ask_ratio', 1.0)
                                block_reason = (
                                    f'Orderbook blocked: ask wall detected '
                                    f'(ratio {ratio:.2f})'
                                )
                                result['reason'] = block_reason
                                self.logger.logger.info(
                                    f"[OB] {coin_symbol}: BUY blocked - {block_reason}"
                                )
                            # Strengthen signal: strong buy pressure confirms entry
                            elif (ob_signal.get('bid_ask_ratio', 1.0) >
                                  orderbook_config.get('bid_ask_ratio_strong', 1.5)):
                                ob_ratio = ob_signal['bid_ask_ratio']
                                result['signal_strength'] = min(
                                    1.0, result['signal_strength'] * 1.2
                                )
                                result['reason'] += (
                                    f' | OB confirmed (ratio {ob_ratio:.1f}x)'
                                )
                                self.logger.logger.info(
                                    f"[OB] {coin_symbol}: BUY confirmed by orderbook "
                                    f"(ratio {ob_ratio:.1f}x)"
                                )
                    else:
                        self.logger.logger.debug(
                            f"[OB] {coin_symbol}: orderbook unavailable, skipping confirmation"
                        )
                except Exception as ob_err:
                    self.logger.logger.warning(
                        f"[OB] {coin_symbol}: orderbook check failed: {ob_err}"
                    )

            # Phase 4: Volume Profile (reference metadata, does not modify score)
            if orderbook_config.get('enable_volume_profile', False):
                vp_signal = self._calculate_volume_profile(exec_df)
                result['volume_profile'] = vp_signal
                if 'error' not in vp_signal:
                    self.logger.logger.debug(
                        f"[VP] {coin_symbol}: POC={vp_signal['poc_price']:,.0f} "
                        f"VA=[{vp_signal['va_low']:,.0f}, {vp_signal['va_high']:,.0f}] "
                        f"near_va_low={vp_signal['near_va_low']} "
                        f"vs_poc={vp_signal['price_vs_poc_pct']:+.1f}%"
                    )

            return result

        except Exception as e:
            self.logger.log_error(f"Market analysis failed for {coin_symbol}", e)
            import traceback
            self.logger.logger.error(traceback.format_exc())
            return {
                'action': 'HOLD',
                'signal_strength': 0.0,
                'reason': f'Analysis error: {str(e)}',
                'market_regime': 'error',
                'entry_score': 0,
            }

    def _get_entry_conditions(self, score: float, df: pd.DataFrame) -> List[str]:
        """Extract which entry conditions were met for performance tracking."""
        if df is None or len(df) < 2:
            return []

        conditions = []
        latest = df.iloc[-1]
        previous = df.iloc[-2]

        # Get dynamic thresholds
        factors = self.factor_manager.get_current_factors()
        rsi_threshold = factors.get('rsi_oversold_threshold', 30)
        stoch_threshold = factors.get('stoch_oversold_threshold', 20)

        # Check BB touch
        if latest['low'] <= latest['bb_lower']:
            conditions.append('bb_touch')

        # Check RSI oversold
        if latest['rsi'] < rsi_threshold:
            conditions.append('rsi_oversold')

        # Check Stoch cross
        k_cross = (previous['stoch_rsi_k'] <= previous['stoch_rsi_d'] and
                   latest['stoch_rsi_k'] > latest['stoch_rsi_d'])
        both_low = (latest['stoch_rsi_k'] < stoch_threshold and
                    latest['stoch_rsi_d'] < stoch_threshold)
        if k_cross and both_low:
            conditions.append('stoch_cross')

        # Phase 2: VWAP and MACD conditions (only when feature flag is enabled)
        enable_vwap_macd = self.indicator_config.get('enable_vwap_macd', False)
        if enable_vwap_macd and len(df) >= 2:
            # Check VWAP cross (price crossed above VWAP)
            if 'vwap' in df.columns and 'vwap' in latest.index:
                price_now = float(latest['close'])
                price_prev = float(previous['close'])
                vwap_now = float(latest['vwap'])
                vwap_prev = float(previous['vwap'])
                if price_prev <= vwap_prev and price_now > vwap_now:
                    conditions.append('vwap_cross')

            # Check MACD cross (MACD crossed above signal below zero)
            if 'macd' in df.columns and 'macd_signal' in df.columns:
                macd_now = float(latest['macd'])
                macd_prev = float(previous['macd'])
                sig_now = float(latest['macd_signal'])
                sig_prev = float(previous['macd_signal'])
                if (macd_prev <= sig_prev and macd_now > sig_now and
                        macd_now < 0 and sig_now < 0):
                    conditions.append('macd_cross')

        return conditions

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

        # Phase 2: VWAP and MACD (only when feature flag is enabled)
        enable_vwap_macd = self.indicator_config.get('enable_vwap_macd', False)
        if enable_vwap_macd:
            vwap_period = self.indicator_config.get('vwap_period', 24)
            df['vwap'] = self._calculate_vwap(df, vwap_period)

            macd_line, signal_line, histogram = self._calculate_macd(
                df,
                fast=self.indicator_config.get('macd_fast', 12),
                slow=self.indicator_config.get('macd_slow', 26),
                signal=self.indicator_config.get('macd_signal', 9),
            )
            df['macd'] = macd_line
            df['macd_signal'] = signal_line
            df['macd_hist'] = histogram

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

    def _calculate_vwap(self, df: pd.DataFrame, period: int = 24) -> pd.Series:
        """
        Calculate rolling VWAP (Volume Weighted Average Price).

        Formula: rolling_sum(TP * Volume) / rolling_sum(Volume)
        TP (Typical Price) = (high + low + close) / 3

        Args:
            df: Price DataFrame with 'high', 'low', 'close', 'volume' columns
            period: Rolling window in bars (default 24 for 24-hour rolling on 1H candles)

        Returns:
            pd.Series of VWAP values; NaN where rolling window is incomplete
        """
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        tp_vol = typical_price * df['volume']
        vwap = tp_vol.rolling(window=period).sum() / df['volume'].rolling(window=period).sum()
        return vwap.fillna(typical_price)  # Fallback to TP when volume data is sparse

    def _calculate_macd(
        self,
        df: pd.DataFrame,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence/Divergence).

        Args:
            df: Price DataFrame with 'close' column
            fast: Fast EMA period (default 12)
            slow: Slow EMA period (default 26)
            signal: Signal line EMA period (default 9)

        Returns:
            Tuple of (macd_line, signal_line, histogram) as pd.Series
        """
        ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
        ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    # ========================================
    # Entry Scoring System
    # ========================================

    def _calculate_entry_score(self, df: pd.DataFrame) -> Tuple[int, str]:
        """
        Calculate entry score based on scoring rules.

        Returns:
            Tuple of (total_score, details_string)
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
            if latest['low'] <= latest['bb_lower']:
                score += rules['bb_touch']['points']
                details.append("BB touch ✓")
            else:
                details.append("BB touch ✗")

        # Condition 2: RSI oversold (+1 point)
        if rules.get('rsi_oversold', {}).get('enabled', True):
            rsi_threshold = self.indicator_config.get('rsi_oversold', 30)
            if latest['rsi'] < rsi_threshold:
                score += rules['rsi_oversold']['points']
                details.append(f"RSI<{rsi_threshold} ✓")
            else:
                details.append(f"RSI<{rsi_threshold} ✗")

        # Condition 3: Stochastic RSI bullish cross below 20 (+2 points)
        if rules.get('stoch_rsi_cross', {}).get('enabled', True):
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
                score += rules['stoch_rsi_cross']['points']
                details.append(f"Stoch cross<{stoch_threshold} ✓")
            else:
                details.append(f"Stoch cross<{stoch_threshold} ✗")

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

    # ========================================
    # Dynamic Factor Methods
    # ========================================

    def _calculate_entry_score_dynamic(self, df: pd.DataFrame) -> Tuple[float, str]:
        """
        Calculate entry score with dynamic weights from factor manager.

        Dynamic weights adjust based on:
        - Recent performance (weekly update)
        - Market volatility (realtime)
        - Per-condition win rates

        Returns:
            Tuple of (weighted_score, details_string)
        """
        if df is None or len(df) < 2:
            return 0.0, "Insufficient data"

        # Get current dynamic factors
        factors = self.factor_manager.get_current_factors()
        dynamic_weights = factors.get('entry_weights', {
            'bb_touch': 1.0,
            'rsi_oversold': 1.0,
            'stoch_cross': 2.0,
        })

        # Get dynamic thresholds
        rsi_threshold = factors.get('rsi_oversold_threshold', 30)
        stoch_threshold = factors.get('stoch_oversold_threshold', 20)

        score = 0.0
        details = []
        rules = self.scoring_config.get('scoring_rules', {})

        latest = df.iloc[-1]
        previous = df.iloc[-2]

        # Condition 1: BB lower touch (dynamic weight)
        if rules.get('bb_touch', {}).get('enabled', True):
            base_points = rules['bb_touch'].get('points', 1)
            weight = dynamic_weights.get('bb_touch', 1.0)

            if latest['low'] <= latest['bb_lower']:
                score += base_points * weight
                details.append(f"BB touch ✓ ({weight:.1f}x)")
            else:
                details.append("BB touch ✗")

        # Condition 2: RSI oversold with dynamic threshold (+dynamic weight)
        if rules.get('rsi_oversold', {}).get('enabled', True):
            base_points = rules['rsi_oversold'].get('points', 1)
            weight = dynamic_weights.get('rsi_oversold', 1.0)

            if latest['rsi'] < rsi_threshold:
                score += base_points * weight
                details.append(f"RSI<{rsi_threshold:.0f} ✓ ({weight:.1f}x)")
            else:
                details.append(f"RSI<{rsi_threshold:.0f} ✗")

        # Condition 3: Stochastic RSI bullish cross with dynamic threshold (+dynamic weight)
        if rules.get('stoch_rsi_cross', {}).get('enabled', True):
            base_points = rules['stoch_rsi_cross'].get('points', 2)
            weight = dynamic_weights.get('stoch_cross', 1.0)

            # Check for bullish cross: %K crosses above %D
            k_cross_above = (
                previous['stoch_rsi_k'] <= previous['stoch_rsi_d'] and
                latest['stoch_rsi_k'] > latest['stoch_rsi_d']
            )

            # Both must be below dynamic threshold
            both_below_threshold = (
                latest['stoch_rsi_k'] < stoch_threshold and
                latest['stoch_rsi_d'] < stoch_threshold
            )

            if k_cross_above and both_below_threshold:
                score += base_points * weight
                details.append(f"Stoch cross<{stoch_threshold:.0f} ✓ ({weight:.1f}x)")
            else:
                details.append(f"Stoch cross<{stoch_threshold:.0f} ✗")

        # === Bonus Signals (for higher score differentiation) ===

        # Bonus 1: Deep BB penetration (price > 1% below BB lower)
        if latest['bb_lower'] > 0:
            bb_penetration_pct = ((latest['bb_lower'] - float(latest['close'])) / latest['bb_lower']) * 100
            if bb_penetration_pct > 1.0:
                score += 0.5
                details.append(f"Deep BB -{bb_penetration_pct:.1f}% ✓")

        # Bonus 2: Bullish RSI divergence (price lower low, RSI higher low)
        if len(df) >= 10:
            # Compare current vs 5-candle-ago trough
            price_now = float(latest['close'])
            rsi_now = float(latest['rsi'])
            lookback = df.iloc[-10:-3]  # Look for prior trough
            if len(lookback) > 0:
                price_prev_low = float(lookback['close'].min())
                rsi_at_prev_low = float(lookback.loc[lookback['close'].idxmin(), 'rsi'])
                if price_now < price_prev_low and rsi_now > rsi_at_prev_low:
                    score += 1.0
                    details.append("RSI divergence ✓")

        # Bonus 3: Volume confirmation (bullish candle with above-average volume)
        if float(latest['close']) > float(latest['open']):  # Bullish candle
            vol_avg = float(df['volume'].iloc[-20:].mean()) if len(df) >= 20 else float(df['volume'].mean())
            if vol_avg > 0 and float(latest['volume']) > vol_avg * 1.5:
                score += 0.5
                details.append("Vol confirm ✓")

        # === Phase 2: VWAP and MACD signals (gated by enable_vwap_macd feature flag) ===
        enable_vwap_macd = self.indicator_config.get('enable_vwap_macd', False)
        if enable_vwap_macd and len(df) >= 2:
            vwap_weight = dynamic_weights.get('vwap', 1.0)
            macd_weight = dynamic_weights.get('macd', 1.0)

            # --- VWAP scoring ---
            # Requires 'vwap' column (added by _calculate_execution_indicators when flag is ON)
            if 'vwap' in df.columns and 'vwap' in latest.index:
                current_price_val = float(latest['close'])
                prev_price_val = float(previous['close'])
                current_vwap = float(latest['vwap'])
                prev_vwap = float(previous['vwap'])

                # Full score: price crosses above VWAP (previous below, current above)
                price_crossed_above_vwap = (
                    prev_price_val <= prev_vwap and
                    current_price_val > current_vwap
                )
                # Partial score: price is below VWAP but within 2% and RSI is oversold
                price_near_vwap_oversold = (
                    current_price_val <= current_vwap and
                    current_vwap > 0 and
                    ((current_vwap - current_price_val) / current_vwap * 100) <= 2.0 and
                    float(latest['rsi']) < 35
                )

                if price_crossed_above_vwap:
                    score += 1.0 * vwap_weight
                    details.append(f"VWAP cross ✓ ({vwap_weight:.1f}x)")
                elif price_near_vwap_oversold:
                    score += 0.5 * vwap_weight
                    details.append(f"VWAP near OS ✓ ({vwap_weight:.1f}x)")
                else:
                    details.append("VWAP ✗")

            # --- MACD scoring ---
            # Requires 'macd', 'macd_signal', 'macd_hist' columns
            if ('macd' in df.columns and 'macd_signal' in df.columns and
                    'macd_hist' in df.columns):
                current_macd = float(latest['macd'])
                prev_macd = float(previous['macd'])
                current_sig = float(latest['macd_signal'])
                prev_sig = float(previous['macd_signal'])
                current_hist = float(latest['macd_hist'])
                prev_hist = float(previous['macd_hist'])

                # Full score (1.0x): MACD crosses above signal while both below zero
                macd_crossed_above_signal = prev_macd <= prev_sig and current_macd > current_sig
                both_below_zero = current_macd < 0 and current_sig < 0

                # Strong score (0.7x): MACD crosses above signal while crossing from negative to positive
                macd_cross_at_zero = (
                    macd_crossed_above_signal and
                    current_macd >= 0 and prev_macd < 0
                )

                # Partial score (0.5x): MACD histogram turning up (increasing) while below zero
                hist_turning_up = (
                    current_hist > prev_hist and
                    current_hist < 0 and prev_hist < 0 and
                    current_macd < 0
                )

                if macd_crossed_above_signal and both_below_zero:
                    score += 1.0 * macd_weight
                    details.append(f"MACD cross<0 ✓ ({macd_weight:.1f}x)")
                elif macd_cross_at_zero:
                    score += 0.7 * macd_weight
                    details.append(f"MACD cross~0 ✓ ({macd_weight:.1f}x)")
                elif hist_turning_up:
                    score += 0.5 * macd_weight
                    details.append(f"MACD hist up ✓ ({macd_weight:.1f}x)")
                else:
                    details.append("MACD ✗")

        details_str = ", ".join(details)
        return score, details_str

    def _calculate_chandelier_stop_dynamic(
        self,
        df: pd.DataFrame,
        regime_strategy: Dict[str, Any]
    ) -> float:
        """
        Calculate Chandelier Exit stop-loss with regime-specific adjustments.

        Regime adjustments:
        - Bullish: Wider stops (1.0-1.2x multiplier)
        - Bearish: Tighter stops (0.5-0.7x multiplier)
        - Ranging: Tight stops (0.6x multiplier)

        Formula: Highest High - (ATR × Base Multiplier × Regime Modifier × Dynamic Factor)

        Args:
            df: Price DataFrame with ATR calculated
            regime_strategy: Regime-specific strategy parameters

        Returns:
            Stop-loss price
        """
        if df is None or len(df) < 14:
            return 0.0

        # Get current dynamic factors
        factors = self.factor_manager.get_current_factors()

        # Base chandelier multiplier from config
        base_multiplier = self.indicator_config.get('chandelier_multiplier', 3.0)

        # Dynamic multiplier adjustment (from ATR-based volatility)
        dynamic_multiplier = factors.get('chandelier_multiplier_modifier', 1.0)

        # Regime-specific stop-loss modifier
        regime_stop_modifier = regime_strategy.get('stop_loss_modifier', 1.0)

        # Calculate final multiplier
        final_multiplier = base_multiplier * dynamic_multiplier * regime_stop_modifier

        # Clamp to reasonable bounds
        bounds = self.config.get('DYNAMIC_FACTOR_CONFIG', {}).get(
            'chandelier_multiplier_bounds', (2.0, 5.0)
        )
        final_multiplier = max(bounds[0], min(bounds[1], final_multiplier))

        # Calculate stop price
        atr_period = self.indicator_config.get('atr_period', 14)
        latest_atr = df['atr'].iloc[-1]
        highest_high = df['high'].iloc[-atr_period:].max()

        chandelier_stop = highest_high - (latest_atr * final_multiplier)

        self.logger.logger.debug(
            f"Chandelier stop: base={base_multiplier:.1f}, "
            f"dynamic={dynamic_multiplier:.2f}, regime={regime_stop_modifier:.2f}, "
            f"final={final_multiplier:.2f}, price={chandelier_stop:.0f}"
        )

        return float(chandelier_stop)

    def _calculate_target_prices_dynamic(
        self,
        df: pd.DataFrame,
        regime_strategy: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate target prices with regime-specific adjustments.

        Regime-based targets:
        - Bullish/Strong Bullish: BB Middle (TP1) → BB Upper (TP2)
        - Neutral: BB Middle only, partial exit
        - Bearish/Strong Bearish: BB Middle only, FULL EXIT (conservative)
        - Ranging: BB Middle only

        Args:
            df: Price DataFrame with Bollinger Bands
            regime_strategy: Regime-specific parameters

        Returns:
            Dictionary with target prices and exit strategy
        """
        if df is None or len(df) == 0:
            return {}

        latest = df.iloc[-1]
        current_price = float(latest['close'])
        bb_middle = float(latest['bb_middle'])
        bb_upper = float(latest['bb_upper'])

        # Get regime-specific profit target setting
        profit_target = regime_strategy.get('profit_target', 'bb_middle_upper')
        full_exit_at_first = regime_strategy.get('full_exit_at_first_target', False)

        # Also check config for bearish override
        if self.exit_config.get('full_exit_at_first_target', False):
            full_exit_at_first = True

        # Calculate stop-loss using dynamic method
        stop_loss = self._calculate_chandelier_stop_dynamic(df, regime_strategy)

        if profit_target == 'bb_upper_only':
            # Strong bullish: aggressive target
            return {
                'first_target': bb_upper,
                'second_target': bb_upper * 1.01,  # Slight buffer above upper
                'stop_loss': stop_loss,
                'mode': 'bb_upper_only',
                'full_exit_at_first': False,
                'exit_strategy': 'Trail stop after first target',
            }

        elif profit_target == 'bb_middle_upper':
            # Bullish: Standard dual target
            return {
                'first_target': bb_middle,
                'second_target': bb_upper,
                'stop_loss': stop_loss,
                'mode': 'bb_middle_upper',
                'full_exit_at_first': False,
                'exit_strategy': 'Exit 50% at BB middle, trail remaining to BB upper',
            }

        elif profit_target == 'bb_middle_only':
            # Bearish/Ranging: Conservative single target
            return {
                'first_target': bb_middle,
                'second_target': bb_middle,  # Same as first (full exit)
                'stop_loss': stop_loss,
                'mode': 'bb_middle_only',
                'full_exit_at_first': full_exit_at_first,
                'exit_strategy': 'FULL EXIT at BB middle (conservative bear market)',
            }

        else:
            # Default fallback
            return {
                'first_target': bb_middle,
                'second_target': bb_upper,
                'stop_loss': stop_loss,
                'mode': 'default',
                'full_exit_at_first': False,
                'exit_strategy': 'Standard dual target',
            }

    def _check_bear_momentum_filter(self, df: pd.DataFrame) -> Tuple[bool, str]:
        """
        Check momentum conditions that should block bearish entries.

        Blocks entry if any of:
        1. Last 3 candles making consecutive lower lows (falling knife)
        2. RSI trending down over last 3 candles (not stabilizing)
        3. Sell volume increasing (down candles with rising volume)

        Returns:
            Tuple of (is_blocked, reason_string)
        """
        if df is None or len(df) < 4:
            return False, ""

        recent = df.iloc[-4:]  # 4 candles for 3-period comparison

        # Check 1: Consecutive lower lows
        lows = recent['low'].values
        lower_lows = all(lows[i] < lows[i-1] for i in range(1, len(lows)))
        if lower_lows:
            return True, f"Falling knife: 3 consecutive lower lows"

        # Check 2: RSI trending down
        rsis = recent['rsi'].values[-3:]  # last 3
        rsi_declining = all(rsis[i] < rsis[i-1] for i in range(1, len(rsis)))
        if rsi_declining:
            return True, f"RSI declining: {rsis[-1]:.0f} < {rsis[-2]:.0f} < {rsis[-3]:.0f}"

        # Check 3: Sell volume increasing (down candles with rising volume)
        down_candles = recent.iloc[-3:]
        down_mask = down_candles['close'] < down_candles['open']
        if down_mask.sum() >= 2:  # At least 2 of 3 are down candles
            down_volumes = down_candles.loc[down_mask, 'volume'].values
            if len(down_volumes) >= 2 and all(
                down_volumes[i] > down_volumes[i-1] for i in range(1, len(down_volumes))
            ):
                return True, "Increasing sell volume on down candles"

        return False, ""

    # ========================================
    # Phase 4: Orderbook Analysis
    # ========================================

    def _analyze_orderbook(
        self,
        orderbook_data: Dict[str, Any],
        current_price: float,
        coin: str,
    ) -> Dict[str, Any]:
        """
        Analyze orderbook depth to assess buy/sell pressure near current price.

        Calculates bid and ask volume (in KRW) within analysis_range_pct of
        current price, detects large walls, and returns a signal dict.

        Args:
            orderbook_data: Raw orderbook dict from get_orderbook() with 'bids'/'asks'
            current_price: Latest close price
            coin: Coin symbol (e.g., 'BTC') for wall threshold lookup

        Returns:
            Dict with keys:
                bid_volume_krw, ask_volume_krw, bid_ask_ratio, net_pressure,
                large_bid_wall, large_ask_wall, wall_details, signal_label
        """
        try:
            ob_config = self.config.get('ORDERBOOK_CONFIG', {})
            analysis_range_pct = ob_config.get('analysis_range_pct', 5.0)
            wall_thresholds = ob_config.get('wall_threshold_krw', {})
            wall_threshold = wall_thresholds.get(
                coin, ob_config.get('default_wall_threshold_krw', 100_000_000)
            )
            ratio_strong = ob_config.get('bid_ask_ratio_strong', 1.5)
            ratio_weak = ob_config.get('bid_ask_ratio_weak', 1.2)

            if current_price <= 0:
                return {'error': 'Invalid current_price'}

            price_lo = current_price * (1 - analysis_range_pct / 100.0)
            price_hi = current_price * (1 + analysis_range_pct / 100.0)

            bid_volume_krw = 0.0
            ask_volume_krw = 0.0
            large_bid_wall = False
            large_ask_wall = False
            wall_details: List[str] = []

            # Process bids (buy side) - bids are sorted high→low by exchange
            bids = orderbook_data.get('bids', [])
            for level in bids:
                price = float(level.get('price', 0))
                qty = float(level.get('quantity', 0))
                if price <= 0 or qty <= 0:
                    continue
                if price < price_lo:
                    break  # below range; remaining bids are further out
                if price <= current_price:
                    level_krw = price * qty
                    bid_volume_krw += level_krw
                    if level_krw >= wall_threshold:
                        large_bid_wall = True
                        wall_details.append(
                            f"BidWall @{price:,.0f} = {level_krw / 1_000_000:.0f}M KRW"
                        )

            # Process asks (sell side) - asks are sorted low→high by exchange
            asks = orderbook_data.get('asks', [])
            for level in asks:
                price = float(level.get('price', 0))
                qty = float(level.get('quantity', 0))
                if price <= 0 or qty <= 0:
                    continue
                if price > price_hi:
                    break  # above range; remaining asks are further out
                if price >= current_price:
                    level_krw = price * qty
                    ask_volume_krw += level_krw
                    if level_krw >= wall_threshold:
                        large_ask_wall = True
                        wall_details.append(
                            f"AskWall @{price:,.0f} = {level_krw / 1_000_000:.0f}M KRW"
                        )

            # Bid/ask ratio (avoid division by zero)
            if ask_volume_krw > 0:
                bid_ask_ratio = bid_volume_krw / ask_volume_krw
            elif bid_volume_krw > 0:
                bid_ask_ratio = ratio_strong * 2  # All bids, no asks
            else:
                bid_ask_ratio = 1.0

            net_pressure = bid_volume_krw - ask_volume_krw

            # Signal label
            if bid_ask_ratio >= ratio_strong:
                signal_label = 'strong_buy_pressure'
            elif bid_ask_ratio >= ratio_weak:
                signal_label = 'buy_pressure'
            elif bid_ask_ratio <= (1.0 / ratio_strong):
                signal_label = 'strong_sell_pressure'
            elif bid_ask_ratio <= (1.0 / ratio_weak):
                signal_label = 'sell_pressure'
            else:
                signal_label = 'neutral'

            return {
                'bid_volume_krw': bid_volume_krw,
                'ask_volume_krw': ask_volume_krw,
                'bid_ask_ratio': bid_ask_ratio,
                'net_pressure': net_pressure,
                'large_bid_wall': large_bid_wall,
                'large_ask_wall': large_ask_wall,
                'wall_details': wall_details,
                'signal_label': signal_label,
                'analysis_range_pct': analysis_range_pct,
            }

        except Exception as e:
            self.logger.logger.warning(f"Orderbook analysis error for {coin}: {e}")
            return {'error': str(e)}

    # ========================================
    # Phase 4: Volume Profile
    # ========================================

    def _calculate_volume_profile(self, exec_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate Volume Profile from recent OHLCV candles.

        Uses Price Range Volume Profile: distributes each candle's volume uniformly
        across the candle's high-low range, then bins into vp_num_bins price bins.

        Identifies:
        - POC (Point of Control): price bin with highest total volume
        - Value Area High/Low: range containing vp_value_area_pct of total volume
        - near_va_low: whether current price is within vp_near_va_low_pct % of VA Low

        Args:
            exec_df: DataFrame with 'open','high','low','close','volume' columns

        Returns:
            Dict with keys:
                poc_price, va_high, va_low, current_price,
                near_va_low (bool), price_vs_poc_pct (float),
                bins (list of dicts), error (str, only on failure)
        """
        try:
            ob_config = self.config.get('ORDERBOOK_CONFIG', {})
            lookback = ob_config.get('vp_lookback', 50)
            num_bins = ob_config.get('vp_num_bins', 30)
            va_pct = ob_config.get('vp_value_area_pct', 0.70)
            near_va_low_pct = ob_config.get('vp_near_va_low_pct', 1.0)

            if exec_df is None or len(exec_df) < 10:
                return {'error': 'Insufficient data for Volume Profile'}

            df = exec_df.iloc[-lookback:].copy()

            total_volume = float(df['volume'].sum())
            if total_volume <= 0:
                return {'error': 'Zero volume in lookback window'}

            price_min = float(df['low'].min())
            price_max = float(df['high'].max())

            current_price = float(df['close'].iloc[-1])

            # Edge case: flat price range
            if price_max <= price_min:
                return {
                    'poc_price': current_price,
                    'va_high': current_price,
                    'va_low': current_price,
                    'current_price': current_price,
                    'near_va_low': True,
                    'price_vs_poc_pct': 0.0,
                    'bins': [],
                    'error': 'Flat price range',
                }

            bin_size = (price_max - price_min) / num_bins
            bin_volumes = np.zeros(num_bins)

            for _, row in df.iterrows():
                candle_low = float(row['low'])
                candle_high = float(row['high'])
                candle_volume = float(row['volume'])

                if candle_high <= candle_low or candle_volume <= 0:
                    continue

                candle_range = candle_high - candle_low

                # Distribute volume proportionally across overlapping bins
                for i in range(num_bins):
                    bin_lo = price_min + i * bin_size
                    bin_hi = bin_lo + bin_size
                    overlap_lo = max(candle_low, bin_lo)
                    overlap_hi = min(candle_high, bin_hi)
                    if overlap_hi > overlap_lo:
                        overlap_fraction = (overlap_hi - overlap_lo) / candle_range
                        bin_volumes[i] += candle_volume * overlap_fraction

            # POC: bin with maximum volume
            poc_bin_idx = int(np.argmax(bin_volumes))
            poc_price = price_min + (poc_bin_idx + 0.5) * bin_size

            # Value Area: accumulate highest-volume bins until va_pct of total volume
            total_vol = bin_volumes.sum()
            if total_vol <= 0:
                return {'error': 'All bins have zero volume after distribution'}

            target_va_vol = total_vol * va_pct
            sorted_indices = np.argsort(bin_volumes)[::-1]
            accumulated_vol = 0.0
            va_bin_indices = []
            for idx in sorted_indices:
                va_bin_indices.append(int(idx))
                accumulated_vol += bin_volumes[idx]
                if accumulated_vol >= target_va_vol:
                    break

            va_low_bin = min(va_bin_indices)
            va_high_bin = max(va_bin_indices)
            va_low = price_min + va_low_bin * bin_size
            va_high = price_min + (va_high_bin + 1) * bin_size

            # near VA Low: current price within near_va_low_pct % of VA Low
            near_va_low = abs(current_price - va_low) / va_low * 100 <= near_va_low_pct

            price_vs_poc_pct = (current_price - poc_price) / poc_price * 100

            bins = [
                {
                    'price_lo': price_min + i * bin_size,
                    'price_hi': price_min + (i + 1) * bin_size,
                    'volume': float(bin_volumes[i]),
                    'is_poc': i == poc_bin_idx,
                    'in_va': i in va_bin_indices,
                }
                for i in range(num_bins)
            ]

            return {
                'poc_price': poc_price,
                'va_high': va_high,
                'va_low': va_low,
                'current_price': current_price,
                'near_va_low': near_va_low,
                'price_vs_poc_pct': price_vs_poc_pct,
                'bins': bins,
            }

        except Exception as e:
            self.logger.logger.warning(f"Volume Profile calculation error: {e}")
            return {'error': str(e)}

    # ========================================
    # Version Interface Methods
    # ========================================

    def get_strategy_description(self) -> str:
        """Return strategy description."""
        return self.VERSION_DESCRIPTION

    def get_version_info(self) -> Dict[str, Any]:
        """Return version metadata."""
        return {
            'name': self.VERSION_NAME,
            'display_name': self.VERSION_DISPLAY_NAME,
            'description': self.VERSION_DESCRIPTION,
            'author': self.VERSION_AUTHOR,
            'date': self.VERSION_DATE,
            'features': [
                'Multi-coin portfolio trading',
                'Dual timeframe analysis (Daily + 4H)',
                'Extended 6-regime detection',
                'Dynamic factor adjustment',
                'Bearish mean reversion strategy',
                'ATR-based position sizing',
                'Performance-based weekly optimization',
            ],
        }
