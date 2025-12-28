"""
Regime Detector - Enhanced Market Regime Classification

Provides dual-regime strategy support with 6 regime classifications:
- Strong Bullish: EMA50 > EMA200 by >5%, aggressive trend following
- Bullish: EMA50 > EMA200, standard trend following
- Neutral: EMAs close together, cautious approach
- Bearish: EMA50 < EMA200, mean reversion with strict entry
- Strong Bearish: EMA50 < EMA200 by >5%, extreme oversold only
- Ranging: Low ADX, oscillation-based strategy

Usage:
    from ver3.regime_detector import RegimeDetector, ExtendedRegime

    detector = RegimeDetector(config)
    regime, metadata = detector.detect_regime(daily_df, exec_df)
    strategy = detector.get_regime_strategy(regime)
"""

from typing import Dict, Any, Optional, Tuple
from enum import Enum
import pandas as pd
import numpy as np


class ExtendedRegime(Enum):
    """Extended market regime classification."""
    STRONG_BULLISH = "strong_bullish"   # EMA50 > EMA200 by >5%
    BULLISH = "bullish"                  # EMA50 > EMA200
    NEUTRAL = "neutral"                  # EMAs very close
    BEARISH = "bearish"                  # EMA50 < EMA200
    STRONG_BEARISH = "strong_bearish"   # EMA50 < EMA200 by >5%
    RANGING = "ranging"                  # Low ADX, price oscillating
    UNKNOWN = "unknown"                  # Insufficient data


class RegimeDetector:
    """
    Enhanced regime detection with multiple classification modes.

    Features:
    - EMA-based regime classification (50/200)
    - ADX trend strength measurement
    - Volatility regime detection
    - Mean reversion opportunity identification for bearish markets

    Attributes:
        config: Configuration dictionary
        ema_strong_threshold: % difference for strong regime classification
        adx_trending_threshold: ADX above this = trending market
        adx_weak_threshold: ADX below this = ranging market
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize RegimeDetector.

        Args:
            config: Configuration dictionary with DYNAMIC_FACTOR_CONFIG section
        """
        self.config = config
        dynamic_config = config.get('DYNAMIC_FACTOR_CONFIG', {})
        regime_config = config.get('REGIME_FILTER_CONFIG', {})

        # Regime thresholds
        self.ema_strong_threshold = dynamic_config.get('ema_strong_threshold_pct', 5.0)
        self.adx_trending_threshold = dynamic_config.get('adx_trending_threshold', 25)
        self.adx_weak_threshold = dynamic_config.get('adx_weak_threshold', 15)
        self.neutral_zone_pct = dynamic_config.get('neutral_zone_pct', 1.0)

        # EMA periods from regime config
        self.ema_fast_period = regime_config.get('ema_fast', 50)
        self.ema_slow_period = regime_config.get('ema_slow', 200)

        # Hysteresis: require N consecutive same-regime readings
        self._regime_history = []
        self._hysteresis_count = dynamic_config.get('regime_hysteresis_count', 3)

    def detect_regime(
        self,
        daily_df: pd.DataFrame,
        execution_df: pd.DataFrame = None
    ) -> Tuple[ExtendedRegime, Dict[str, Any]]:
        """
        Detect market regime from price data.

        Args:
            daily_df: Daily OHLCV data (minimum 200 candles for EMA200)
            execution_df: Optional 4H data for additional signals (ADX calculation)

        Returns:
            Tuple of (ExtendedRegime, metadata_dict)
        """
        if daily_df is None or len(daily_df) < 200:
            return ExtendedRegime.UNKNOWN, {'reason': 'Insufficient daily data (need 200+ candles)'}

        # Calculate EMAs if not present
        if 'ema_fast' not in daily_df.columns or 'ema_slow' not in daily_df.columns:
            daily_df = self._calculate_emas(daily_df)

        # Get latest values
        latest = daily_df.iloc[-1]
        ema_fast = latest.get('ema_fast', 0)
        ema_slow = latest.get('ema_slow', 0)

        if pd.isna(ema_fast) or pd.isna(ema_slow) or ema_slow == 0:
            return ExtendedRegime.UNKNOWN, {'reason': 'Invalid EMA values'}

        # Calculate EMA difference percentage
        ema_diff_pct = (ema_fast - ema_slow) / ema_slow * 100
        current_price = float(latest['close'])
        price_vs_ema_slow = (current_price - ema_slow) / ema_slow * 100

        # Calculate ADX for trend strength
        adx_value = 25.0  # Default neutral
        if execution_df is not None and len(execution_df) >= 28:
            adx_value = self._calculate_adx(execution_df)
        elif len(daily_df) >= 28:
            adx_value = self._calculate_adx(daily_df)

        # Build metadata
        metadata = {
            'ema_fast': round(ema_fast, 2),
            'ema_slow': round(ema_slow, 2),
            'ema_diff_pct': round(ema_diff_pct, 2),
            'current_price': current_price,
            'price_vs_ema_slow_pct': round(price_vs_ema_slow, 2),
            'adx': round(adx_value, 2),
        }

        # Determine regime
        regime = self._classify_regime(ema_diff_pct, adx_value)

        # Apply hysteresis
        regime = self._apply_hysteresis(regime)

        metadata['regime'] = regime.value
        metadata['regime_description'] = self._get_regime_description(regime)

        return regime, metadata

    def _classify_regime(self, ema_diff_pct: float, adx_value: float) -> ExtendedRegime:
        """Classify regime based on EMA difference and ADX."""
        # Ranging market (low ADX) takes priority
        if adx_value < self.adx_weak_threshold:
            return ExtendedRegime.RANGING

        # Neutral zone (EMAs very close)
        if abs(ema_diff_pct) < self.neutral_zone_pct:
            return ExtendedRegime.NEUTRAL

        # Strong Bullish
        if ema_diff_pct >= self.ema_strong_threshold:
            return ExtendedRegime.STRONG_BULLISH

        # Bullish
        if ema_diff_pct > 0:
            return ExtendedRegime.BULLISH

        # Strong Bearish
        if ema_diff_pct <= -self.ema_strong_threshold:
            return ExtendedRegime.STRONG_BEARISH

        # Bearish
        if ema_diff_pct < 0:
            return ExtendedRegime.BEARISH

        return ExtendedRegime.NEUTRAL

    def _apply_hysteresis(self, current_regime: ExtendedRegime) -> ExtendedRegime:
        """
        Apply hysteresis to prevent regime oscillation.

        Require N consecutive same-regime readings before switching.
        """
        self._regime_history.append(current_regime)

        # Keep only recent history
        if len(self._regime_history) > self._hysteresis_count:
            self._regime_history = self._regime_history[-self._hysteresis_count:]

        # Check if all recent readings are the same
        if len(self._regime_history) >= self._hysteresis_count:
            if all(r == current_regime for r in self._regime_history):
                return current_regime
            else:
                # Return previous stable regime if available
                return self._regime_history[0]

        return current_regime

    def _get_regime_description(self, regime: ExtendedRegime) -> str:
        """Get human-readable regime description."""
        descriptions = {
            ExtendedRegime.STRONG_BULLISH: "Strong uptrend (EMA50 >> EMA200)",
            ExtendedRegime.BULLISH: "Uptrend (EMA50 > EMA200)",
            ExtendedRegime.NEUTRAL: "Neutral (EMAs converging)",
            ExtendedRegime.BEARISH: "Downtrend (EMA50 < EMA200)",
            ExtendedRegime.STRONG_BEARISH: "Strong downtrend (EMA50 << EMA200)",
            ExtendedRegime.RANGING: "Ranging/Sideways (Low ADX)",
            ExtendedRegime.UNKNOWN: "Unknown (insufficient data)",
        }
        return descriptions.get(regime, "Unknown")

    def get_regime_strategy(self, regime: ExtendedRegime) -> Dict[str, Any]:
        """
        Get strategy parameters for given regime.

        Returns dict with:
        - allow_entry: bool - Whether to allow new entries
        - entry_mode: 'trend' | 'reversion' | 'oscillation'
        - entry_threshold_modifier: float - Multiply base entry score requirement
        - stop_loss_modifier: float - Multiply base stop-loss distance
        - take_profit_target: 'bb_middle' | 'bb_upper'
        - full_exit_at_first_target: bool - Exit 100% at first target (bearish)
        - description: str - Strategy description
        """
        strategies = {
            ExtendedRegime.STRONG_BULLISH: {
                'allow_entry': True,
                'entry_mode': 'trend',
                'entry_threshold_modifier': 0.8,
                'stop_loss_modifier': 1.2,
                'take_profit_target': 'bb_upper',
                'full_exit_at_first_target': False,
                'description': 'Aggressive trend following with wider targets',
            },
            ExtendedRegime.BULLISH: {
                'allow_entry': True,
                'entry_mode': 'trend',
                'entry_threshold_modifier': 1.0,
                'stop_loss_modifier': 1.0,
                'take_profit_target': 'bb_upper',
                'full_exit_at_first_target': False,
                'description': 'Standard trend following strategy',
            },
            ExtendedRegime.NEUTRAL: {
                'allow_entry': True,
                'entry_mode': 'oscillation',
                'entry_threshold_modifier': 1.2,
                'stop_loss_modifier': 0.8,
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': False,
                'description': 'Cautious oscillation trading',
            },
            ExtendedRegime.BEARISH: {
                'allow_entry': True,  # Allow mean reversion entries
                'entry_mode': 'reversion',
                'entry_threshold_modifier': 1.5,
                'stop_loss_modifier': 0.7,
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': True,  # Full exit at BB middle
                'description': 'Conservative mean reversion, tight stops, quick exits',
            },
            ExtendedRegime.STRONG_BEARISH: {
                'allow_entry': True,  # Only extreme oversold
                'entry_mode': 'reversion',
                'entry_threshold_modifier': 2.0,
                'stop_loss_modifier': 0.5,
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': True,
                'description': 'Extreme oversold entries only, very tight risk management',
            },
            ExtendedRegime.RANGING: {
                'allow_entry': True,
                'entry_mode': 'oscillation',
                'entry_threshold_modifier': 1.0,
                'stop_loss_modifier': 0.6,
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': False,
                'description': 'Range-bound oscillation trading',
            },
            ExtendedRegime.UNKNOWN: {
                'allow_entry': False,
                'entry_mode': 'none',
                'entry_threshold_modifier': 999,
                'stop_loss_modifier': 0.5,
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': True,
                'description': 'No trading - insufficient data',
            },
        }

        return strategies.get(regime, strategies[ExtendedRegime.UNKNOWN])

    def get_bearish_entry_conditions(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Get special entry conditions for bearish/mean reversion mode.

        For bearish regime, require extreme oversold conditions:
        - RSI < 20 (extreme oversold)
        - Price at or below BB lower - 1 std
        - Stochastic K < 10

        Args:
            df: DataFrame with calculated indicators

        Returns:
            Dict with condition checks and overall extreme_oversold flag
        """
        if df is None or len(df) < 2:
            return {'is_extreme_oversold': False, 'reason': 'Insufficient data'}

        latest = df.iloc[-1]

        rsi = latest.get('rsi', 50)
        stoch_k = latest.get('stoch_rsi_k', 50)
        bb_lower = latest.get('bb_lower', 0)
        bb_middle = latest.get('bb_middle', 0)
        current_price = float(latest.get('close', 0))

        # Calculate extreme lower band (middle - 3 std equivalent)
        if bb_middle > 0 and bb_lower > 0:
            bb_std = (bb_middle - bb_lower) / 2  # Approximate 1 std
            extreme_lower = bb_lower - bb_std
        else:
            extreme_lower = 0

        conditions = {
            'rsi_extreme': rsi < 20,
            'stoch_extreme': stoch_k < 10,
            'price_at_bb_lower': current_price <= bb_lower,
            'price_extreme_low': current_price <= extreme_lower,
            'current_rsi': round(rsi, 1),
            'current_stoch_k': round(stoch_k, 1),
            'current_price': current_price,
            'bb_lower': bb_lower,
            'extreme_lower': extreme_lower,
        }

        # For bearish regime entry: need at least 2 of 3 extreme conditions
        extreme_count = sum([
            conditions['rsi_extreme'],
            conditions['stoch_extreme'],
            conditions['price_at_bb_lower']
        ])

        conditions['is_extreme_oversold'] = extreme_count >= 2
        conditions['extreme_condition_count'] = extreme_count

        return conditions

    def is_entry_allowed(
        self,
        regime: ExtendedRegime,
        entry_score: int,
        df: pd.DataFrame = None
    ) -> Tuple[bool, str]:
        """
        Check if entry is allowed based on regime and score.

        Args:
            regime: Current market regime
            entry_score: Calculated entry score
            df: Optional DataFrame for extreme oversold check

        Returns:
            Tuple of (is_allowed, reason_string)
        """
        strategy = self.get_regime_strategy(regime)

        if not strategy['allow_entry']:
            return False, f"Entry not allowed in {regime.value} regime"

        # Get base min score from config
        base_min_score = self.config.get('ENTRY_SCORING_CONFIG', {}).get('min_entry_score', 2)

        # Apply regime modifier
        adjusted_min_score = int(base_min_score * strategy['entry_threshold_modifier'])
        adjusted_min_score = max(1, min(4, adjusted_min_score))

        if entry_score < adjusted_min_score:
            return False, f"Score {entry_score} below adjusted threshold {adjusted_min_score} ({regime.value})"

        # For bearish regimes, also check extreme oversold conditions
        if regime in [ExtendedRegime.BEARISH, ExtendedRegime.STRONG_BEARISH]:
            if df is not None:
                conditions = self.get_bearish_entry_conditions(df)
                if not conditions['is_extreme_oversold']:
                    return False, f"Not extreme oversold ({conditions['extreme_condition_count']}/3 conditions met)"

        return True, f"Entry allowed: score {entry_score} >= {adjusted_min_score} in {regime.value}"

    # ========================================
    # Technical Indicator Calculations
    # ========================================

    def _calculate_emas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate EMA 50 and 200."""
        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast_period, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow_period, adjust=False).mean()
        return df

    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> float:
        """
        Calculate Average Directional Index.

        ADX measures trend strength:
        - ADX < 15: Weak/No trend (ranging)
        - ADX 15-25: Weak trend
        - ADX 25-50: Strong trend
        - ADX > 50: Very strong trend
        """
        if df is None or len(df) < period * 2:
            return 25.0  # Default neutral

        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            # Calculate +DM and -DM
            plus_dm = np.zeros(len(df))
            minus_dm = np.zeros(len(df))

            for i in range(1, len(df)):
                up_move = high[i] - high[i-1]
                down_move = low[i-1] - low[i]

                if up_move > down_move and up_move > 0:
                    plus_dm[i] = up_move
                if down_move > up_move and down_move > 0:
                    minus_dm[i] = down_move

            # True Range
            tr = np.zeros(len(df))
            for i in range(1, len(df)):
                tr1 = high[i] - low[i]
                tr2 = abs(high[i] - close[i-1])
                tr3 = abs(low[i] - close[i-1])
                tr[i] = max(tr1, tr2, tr3)

            # Smoothed values using Wilder's smoothing
            atr = self._wilder_smooth(tr, period)
            plus_di = 100 * self._wilder_smooth(plus_dm, period) / np.where(atr > 0, atr, 1)
            minus_di = 100 * self._wilder_smooth(minus_dm, period) / np.where(atr > 0, atr, 1)

            # DX and ADX calculation
            di_sum = plus_di + minus_di
            di_diff = np.abs(plus_di - minus_di)
            dx = 100 * di_diff / np.where(di_sum > 0, di_sum, 1)
            adx = self._wilder_smooth(dx, period)

            # Return latest ADX value
            latest_adx = adx[-1]
            if np.isnan(latest_adx) or np.isinf(latest_adx):
                return 25.0
            return float(latest_adx)

        except Exception:
            return 25.0

    def _wilder_smooth(self, data: np.ndarray, period: int) -> np.ndarray:
        """Wilder's smoothing method (exponential moving average variant)."""
        result = np.zeros(len(data))
        result[:period] = np.nan

        # Initial value is simple average
        result[period-1] = np.mean(data[:period])

        # Wilder smoothing
        for i in range(period, len(data)):
            result[i] = result[i-1] + (data[i] - result[i-1]) / period

        return result

    def reset_history(self):
        """Reset regime history (for testing or restart)."""
        self._regime_history = []


# Convenience function for quick regime check
def detect_market_regime(
    daily_df: pd.DataFrame,
    config: Dict[str, Any] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Quick function to detect market regime.

    Args:
        daily_df: Daily OHLCV DataFrame
        config: Optional configuration dictionary

    Returns:
        Tuple of (regime_string, metadata_dict)
    """
    detector = RegimeDetector(config or {})
    regime, metadata = detector.detect_regime(daily_df)
    return regime.value, metadata
