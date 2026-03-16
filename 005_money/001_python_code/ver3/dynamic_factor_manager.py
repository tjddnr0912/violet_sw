"""
Dynamic Factor Manager - Multi-Frequency Parameter Adjustment System

Manages dynamic factor calculations at different frequencies:
- Real-time: ATR-based stop-loss, position sizing multipliers
- 4-Hourly: RSI/Stochastic thresholds based on volatility
- Daily: Regime parameters, Bollinger Band settings
- Weekly: Entry score weights based on performance
- Monthly: Full parameter optimization (via monthly_optimizer.py)

Usage:
    from ver3.dynamic_factor_manager import get_dynamic_factor_manager

    factor_manager = get_dynamic_factor_manager(config, logger)
    realtime_factors = factor_manager.update_realtime_factors('BTC', atr, price)
    adjusted_config = factor_manager.get_adjusted_config(base_config)
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import threading
import copy
from pathlib import Path


class VolatilityLevel(Enum):
    """Volatility classification based on ATR%."""
    LOW = "low"           # ATR% < 1.5
    NORMAL = "normal"     # 1.5 <= ATR% < 3.0
    HIGH = "high"         # 3.0 <= ATR% < 5.0
    EXTREME = "extreme"   # ATR% >= 5.0


@dataclass
class DynamicFactors:
    """Container for all dynamic adjustment factors."""

    # Real-time factors (updated every analysis cycle)
    atr_stop_loss_multiplier: float = 1.0  # Multiplier applied to base Chandelier
    position_size_multiplier: float = 1.0  # Multiplier for position sizing
    volatility_level: str = "normal"
    current_atr_pct: float = 0.0

    # 4-hour factors (updated when ATR changes significantly)
    rsi_oversold_threshold: float = 30.0
    rsi_overbought_threshold: float = 70.0
    stoch_oversold_threshold: float = 20.0
    stoch_overbought_threshold: float = 80.0

    # Daily factors (updated on regime change or daily)
    market_regime: str = "unknown"
    bb_period: int = 20
    bb_std_multiplier: float = 2.0
    chandelier_base_multiplier: float = 3.0

    # Regime-specific strategy parameters
    entry_mode: str = "trend"  # trend, reversion, oscillation
    entry_threshold_modifier: float = 1.0
    stop_loss_modifier: float = 1.0
    take_profit_target: str = "bb_upper"  # bb_middle, bb_upper
    full_exit_at_first_target: bool = False  # True for bearish regime

    # Phase 1: Micro regime fields
    micro_regime: str = "micro_neutral"
    position_size_override: Optional[float] = None  # Composite strategy override
    extreme_oversold_required: bool = True
    bear_momentum_filter: bool = True
    rsi_convergence_score: float = 0.0

    # Weekly factors (updated based on performance)
    entry_weight_bb_touch: float = 1.0
    entry_weight_rsi_oversold: float = 1.0
    entry_weight_stoch_cross: float = 2.0
    min_entry_score: int = 2

    # Phase 2: VWAP/MACD weights
    entry_weight_vwap: float = 1.0
    entry_weight_macd: float = 1.0

    # Metadata
    last_realtime_update: Optional[str] = None
    last_4h_update: Optional[str] = None
    last_daily_update: Optional[str] = None
    last_weekly_update: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DynamicFactors':
        """Create from dictionary."""
        valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_fields)


class AdaptiveWeightEngine:
    """
    Calculates optimal indicator weights based on historical trade performance.

    Maintains per-regime weight tables with EMA smoothing so weights adapt
    gradually as new trade results arrive.  The engine is indicator-agnostic:
    it works with any set of condition names found in trade['entry_conditions'].

    Algorithm:
        raw_weight  = 0.5 + (win_rate - 0.5) * 2.0
        win_rate 0.30  ->  weight 0.60
        win_rate 0.50  ->  weight 1.00
        win_rate 0.75  ->  weight 1.50
        clamped     = clamp(raw_weight, weight_min, weight_max)
        smoothed    = smoothing * new + (1 - smoothing) * current

    Persistence:
        Weights are stored in logs/adaptive_weights_v3.json so they survive
        bot restarts.  Missing file -> default weight 1.0 for all indicators.
    """

    # Default weight when no historical data exists for an indicator
    _DEFAULT_WEIGHT = 1.0

    def __init__(self, config: Dict[str, Any], logger=None):
        """
        Args:
            config: Full bot config dict; reads ADAPTIVE_WEIGHT_CONFIG section.
            logger: TradingLogger instance (optional).
        """
        self._cfg = config.get('ADAPTIVE_WEIGHT_CONFIG', {})
        self.logger = logger

        # {regime_str: {indicator_name: weight_float}}
        self._weights_by_regime: Dict[str, Dict[str, float]] = {}
        # Global fallback when a regime has insufficient data
        self._global_weights: Dict[str, float] = {}

        weights_path = self._cfg.get('weights_file', 'logs/adaptive_weights_v3.json')
        self._weights_file = Path(weights_path)

        self._load_weights()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_weights(
        self,
        recent_trades: List[Dict[str, Any]],
        current_regime: Optional[str] = None
    ) -> Dict[str, float]:
        """
        Compute new weights from recent trade performance and persist them.

        Args:
            recent_trades: List of trade dicts.  Each must have:
                - 'entry_conditions': List[str]
                - 'profit_pct': float
                - 'regime': str  (optional, falls back to 'unknown')
            current_regime: When set, only compute weights for this regime.
                            When None, compute for all regimes present in trades.

        Returns:
            Dict of {indicator_name: weight} for current_regime (or global if
            current_regime is None or has too few trades).
        """
        if not recent_trades:
            return self.get_weights_for_regime(current_regime)

        weight_min = self._cfg.get('weight_min', 0.4)
        weight_max = self._cfg.get('weight_max', 2.0)
        smoothing = self._cfg.get('smoothing_factor', 0.3)
        min_trades = self._cfg.get('min_trades_per_regime', 5)

        # Collect all indicator names that appear in these trades
        all_indicators: set = set()
        for trade in recent_trades:
            all_indicators.update(trade.get('entry_conditions', []))

        # Determine which regimes to process
        if current_regime:
            regimes_to_process = [current_regime]
        else:
            regimes_to_process = list({t.get('regime', 'unknown') for t in recent_trades})

        # Update per-regime weights
        for regime in regimes_to_process:
            regime_trades = [t for t in recent_trades if t.get('regime', 'unknown') == regime]
            if len(regime_trades) < min_trades:
                # Not enough data for this regime; skip regime-specific update
                continue

            new_regime_weights = self._calc_weights_from_trades(
                regime_trades, all_indicators, weight_min, weight_max, smoothing,
                regime_key=regime
            )
            self._weights_by_regime[regime] = new_regime_weights

        # Always update global weights using all trades (for fallback)
        global_new = self._calc_weights_from_trades(
            recent_trades, all_indicators, weight_min, weight_max, smoothing,
            regime_key=None
        )
        self._global_weights = global_new

        self._save_weights()

        return self.get_weights_for_regime(current_regime)

    def get_weights_for_regime(self, regime: Optional[str]) -> Dict[str, float]:
        """
        Return the current weight dict for a regime.

        Falls back to global weights when regime has insufficient data,
        and falls back to empty dict (callers use _DEFAULT_WEIGHT=1.0) when
        global weights are also absent.

        Args:
            regime: Market regime string (e.g. 'bullish', 'bearish').
                    None -> return global weights.

        Returns:
            {indicator_name: weight_float}  (copy, safe to mutate)
        """
        if regime and regime in self._weights_by_regime:
            regime_weights = self._weights_by_regime[regime]
            if regime_weights:
                return dict(regime_weights)

        # Fall back to global
        if self._global_weights:
            return dict(self._global_weights)

        # Ultimate default: empty dict; callers must handle missing keys
        return {}

    def check_rapid_decay(
        self,
        recent_trades: List[Dict[str, Any]],
        indicator: str
    ) -> bool:
        """
        Detect whether an indicator triggered rapid-decay conditions.

        Rapid decay fires when the indicator appeared in N consecutive losing
        trades within the last K trades (configurable via ADAPTIVE_WEIGHT_CONFIG).

        Args:
            recent_trades: Trades sorted oldest-to-newest.
            indicator: Indicator name to check (e.g. 'bb_touch').

        Returns:
            True if rapid decay should be applied to this indicator.
        """
        lookback = self._cfg.get('rapid_decay_lookback', 5)
        threshold = self._cfg.get('rapid_decay_threshold', 3)

        # Consider only the most recent `lookback` trades that used this indicator
        relevant = [
            t for t in recent_trades
            if indicator in t.get('entry_conditions', [])
        ][-lookback:]

        if len(relevant) < threshold:
            return False

        # Count consecutive losses from the most recent trade backward
        consecutive_losses = 0
        for trade in reversed(relevant):
            if trade.get('profit_pct', 0.0) <= 0:
                consecutive_losses += 1
            else:
                break

        return consecutive_losses >= threshold

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calc_weights_from_trades(
        self,
        trades: List[Dict[str, Any]],
        indicators: set,
        weight_min: float,
        weight_max: float,
        smoothing: float,
        regime_key: Optional[str]
    ) -> Dict[str, float]:
        """
        Core weight calculation for a specific set of trades.

        Returns {indicator: smoothed_weight}.
        """
        rapid_decay_weight = self._cfg.get('rapid_decay_weight', 0.6)

        # Baseline weights for EMA smoothing
        if regime_key and regime_key in self._weights_by_regime:
            current_weights = self._weights_by_regime[regime_key]
        else:
            current_weights = self._global_weights

        new_weights: Dict[str, float] = {}

        for indicator in indicators:
            indicator_trades = [
                t for t in trades
                if indicator in t.get('entry_conditions', [])
            ]

            if not indicator_trades:
                # No data for this indicator; preserve existing or use default
                new_weights[indicator] = current_weights.get(indicator, self._DEFAULT_WEIGHT)
                continue

            wins = sum(1 for t in indicator_trades if t.get('profit_pct', 0.0) > 0)
            win_rate = wins / len(indicator_trades)

            # Check rapid decay before normal calculation
            if self.check_rapid_decay(trades, indicator):
                raw_weight = rapid_decay_weight
                if self.logger:
                    self.logger.logger.warning(
                        f"[AdaptiveWeight] Rapid decay triggered for '{indicator}' "
                        f"(regime={regime_key}), weight -> {rapid_decay_weight}"
                    )
            else:
                # Linear mapping: win_rate 0.5 -> 1.0; each 0.25 deviation -> +-0.5
                raw_weight = 0.5 + (win_rate - 0.5) * 2.0

            clamped = max(weight_min, min(weight_max, raw_weight))

            # EMA smoothing against the previous weight
            prev_weight = current_weights.get(indicator, self._DEFAULT_WEIGHT)
            smoothed = smoothing * clamped + (1.0 - smoothing) * prev_weight

            new_weights[indicator] = round(smoothed, 4)

        return new_weights

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_weights(self):
        """Load saved weights from JSON.  Silent on missing file."""
        try:
            if self._weights_file.exists():
                with open(self._weights_file, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                self._weights_by_regime = data.get('by_regime', {})
                self._global_weights = data.get('global', {})
                if self.logger:
                    self.logger.logger.info(
                        f"[AdaptiveWeight] Loaded weights from {self._weights_file}"
                    )
        except Exception as exc:
            if self.logger:
                self.logger.logger.warning(
                    f"[AdaptiveWeight] Could not load weights file: {exc}"
                )
            self._weights_by_regime = {}
            self._global_weights = {}

    def _save_weights(self):
        """Persist current weights to JSON."""
        try:
            self._weights_file.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                'by_regime': self._weights_by_regime,
                'global': self._global_weights,
                'saved_at': datetime.now().isoformat(),
            }
            with open(self._weights_file, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            if self.logger:
                self.logger.logger.warning(
                    f"[AdaptiveWeight] Could not save weights: {exc}"
                )


class DynamicFactorManager:
    """
    Manages dynamic factor calculations with multi-frequency updates.

    Thread-safe singleton pattern for global access across trading bot components.

    Update Frequencies:
    - Real-time (every analysis cycle): ATR-based stop-loss, position sizing
    - 4-Hourly: RSI/Stochastic thresholds when ATR changes >15%
    - Daily: Regime parameters, Bollinger Band settings
    - Weekly: Entry score weights based on trading performance
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Singleton pattern for global access."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(
        self,
        config: Dict[str, Any] = None,
        logger = None,
        factors_file: str = None
    ):
        """
        Initialize DynamicFactorManager.

        Args:
            config: Configuration dictionary with DYNAMIC_FACTOR_CONFIG section
            logger: TradingLogger instance for logging
            factors_file: Path to persist dynamic factors (default: logs/dynamic_factors_v3.json)
        """
        if self._initialized:
            return

        self.config = config or {}
        self.logger = logger
        self.factors = DynamicFactors()

        # Extract dynamic factor config
        self.dynamic_config = self.config.get('DYNAMIC_FACTOR_CONFIG', {})

        # State file for persistence
        log_dir = self.config.get('LOGGING_CONFIG', {}).get('log_dir', 'logs')
        self.factors_file = Path(factors_file or f'{log_dir}/dynamic_factors_v3.json')

        # Update tracking
        self._update_lock = threading.Lock()
        self._last_atr_values: Dict[str, float] = {}  # Per-coin ATR tracking

        # Phase 3: Adaptive weight engine (feature-flagged)
        self._adaptive_weight_engine: Optional[AdaptiveWeightEngine] = None
        self._performance_tracker = None  # Injected via set_performance_tracker()
        adaptive_cfg = self.config.get('ADAPTIVE_WEIGHT_CONFIG', {})
        if adaptive_cfg.get('enable_adaptive_weights', False):
            self._adaptive_weight_engine = AdaptiveWeightEngine(self.config, self.logger)

        # Load persisted factors
        self._load_factors()

        self._initialized = True

        if self.logger:
            self.logger.logger.info("DynamicFactorManager initialized")

    # ========================================
    # Real-Time Updates (Every Analysis Cycle)
    # ========================================

    def update_realtime_factors(
        self,
        coin: str,
        current_atr: float,
        current_price: float
    ) -> Dict[str, Any]:
        """
        Calculate real-time factors based on current ATR.

        Called every analysis cycle (15 minutes).

        Args:
            coin: Cryptocurrency symbol (e.g., 'BTC')
            current_atr: Current ATR value
            current_price: Current price

        Returns:
            Dict with stop_loss_multiplier, position_size_multiplier, volatility_level
        """
        with self._update_lock:
            # Calculate ATR percentage
            if current_price <= 0:
                atr_pct = 0.0
            else:
                atr_pct = (current_atr / current_price) * 100

            # Classify volatility level
            volatility_level = self._classify_volatility(atr_pct)
            self.factors.volatility_level = volatility_level.value
            self.factors.current_atr_pct = round(atr_pct, 3)

            # Dynamic Chandelier multiplier based on volatility
            self.factors.atr_stop_loss_multiplier = self._calc_stop_loss_multiplier(volatility_level)

            # Dynamic position size multiplier (inverse volatility)
            self.factors.position_size_multiplier = self._calc_position_size_multiplier(volatility_level)

            # Update metadata
            self.factors.last_realtime_update = datetime.now().isoformat()

            # Track ATR for 4H threshold check
            old_atr = self._last_atr_values.get(coin, atr_pct)
            self._last_atr_values[coin] = atr_pct

            # Check if 4H factors need update (ATR changed significantly)
            if self._should_update_4h_factors(old_atr, atr_pct):
                self.update_4h_factors(volatility_level)

            result = {
                'stop_loss_multiplier': self.factors.atr_stop_loss_multiplier,
                'position_size_multiplier': self.factors.position_size_multiplier,
                'volatility_level': self.factors.volatility_level,
                'atr_pct': atr_pct,
                'coin': coin
            }

            if self.logger:
                self.logger.logger.debug(
                    f"[DFM] Realtime update {coin}: ATR%={atr_pct:.2f}, "
                    f"Vol={volatility_level.value}, SL_mult={self.factors.atr_stop_loss_multiplier:.2f}"
                )

            return result

    def _classify_volatility(self, atr_pct: float) -> VolatilityLevel:
        """Classify ATR% into volatility levels."""
        thresholds = self.dynamic_config.get('volatility_levels', {
            'low': 1.5,
            'normal': 3.0,
            'high': 5.0,
        })

        if atr_pct < thresholds.get('low', 1.5):
            return VolatilityLevel.LOW
        elif atr_pct < thresholds.get('normal', 3.0):
            return VolatilityLevel.NORMAL
        elif atr_pct < thresholds.get('high', 5.0):
            return VolatilityLevel.HIGH
        else:
            return VolatilityLevel.EXTREME

    def _calc_stop_loss_multiplier(self, vol_level: VolatilityLevel) -> float:
        """
        Calculate stop-loss multiplier based on volatility.

        Low volatility: Tighter stops (0.8x)
        High volatility: Wider stops (1.5x)
        """
        multipliers = {
            VolatilityLevel.LOW: 0.8,
            VolatilityLevel.NORMAL: 1.0,
            VolatilityLevel.HIGH: 1.2,
            VolatilityLevel.EXTREME: 1.5,
        }
        return multipliers.get(vol_level, 1.0)

    def _calc_position_size_multiplier(self, vol_level: VolatilityLevel) -> float:
        """
        Calculate position size multiplier (inverse of volatility).

        Low volatility: Larger positions (1.2x)
        High volatility: Smaller positions (0.5x)
        """
        bounds = self.dynamic_config.get('position_size_multiplier_bounds', (0.3, 1.5))

        multipliers = {
            VolatilityLevel.LOW: min(1.2, bounds[1]),
            VolatilityLevel.NORMAL: 1.0,
            VolatilityLevel.HIGH: max(0.7, bounds[0]),
            VolatilityLevel.EXTREME: max(0.5, bounds[0]),
        }
        return multipliers.get(vol_level, 1.0)

    def _should_update_4h_factors(self, old_atr: float, new_atr: float) -> bool:
        """Check if 4H factors should be updated (ATR changed >15%)."""
        threshold = self.dynamic_config.get('4h_update_threshold_pct', 15.0)

        if old_atr == 0:
            return True

        change_pct = abs(new_atr - old_atr) / old_atr * 100
        return change_pct > threshold

    # ========================================
    # 4-Hour Updates (Volatility Threshold Changes)
    # ========================================

    def update_4h_factors(self, volatility_level: VolatilityLevel) -> Dict[str, float]:
        """
        Update indicator thresholds based on 4H volatility conditions.

        Called when ATR changes significantly (>15%) or every 4 hours.

        Args:
            volatility_level: Current volatility classification

        Returns:
            Dict with updated RSI/Stochastic thresholds
        """
        with self._update_lock:
            bounds = self.dynamic_config.get('rsi_threshold_bounds', (20, 40))

            # Adjust RSI thresholds based on volatility
            if volatility_level in [VolatilityLevel.HIGH, VolatilityLevel.EXTREME]:
                # Wider thresholds in high volatility (more extreme values needed)
                self.factors.rsi_oversold_threshold = max(bounds[0], 25.0)
                self.factors.rsi_overbought_threshold = 75.0
                self.factors.stoch_oversold_threshold = 15.0
                self.factors.stoch_overbought_threshold = 85.0
            elif volatility_level == VolatilityLevel.LOW:
                # Tighter thresholds in low volatility
                self.factors.rsi_oversold_threshold = min(bounds[1], 35.0)
                self.factors.rsi_overbought_threshold = 65.0
                self.factors.stoch_oversold_threshold = 25.0
                self.factors.stoch_overbought_threshold = 75.0
            else:
                # Default thresholds
                self.factors.rsi_oversold_threshold = 30.0
                self.factors.rsi_overbought_threshold = 70.0
                self.factors.stoch_oversold_threshold = 20.0
                self.factors.stoch_overbought_threshold = 80.0

            self.factors.last_4h_update = datetime.now().isoformat()
            self._save_factors()

            result = {
                'rsi_oversold': self.factors.rsi_oversold_threshold,
                'rsi_overbought': self.factors.rsi_overbought_threshold,
                'stoch_oversold': self.factors.stoch_oversold_threshold,
                'stoch_overbought': self.factors.stoch_overbought_threshold,
                'volatility_level': volatility_level.value
            }

            if self.logger:
                self.logger.logger.info(
                    f"[DFM] 4H factors updated: RSI<{self.factors.rsi_oversold_threshold}, "
                    f"Stoch<{self.factors.stoch_oversold_threshold} (vol={volatility_level.value})"
                )

            return result

    # ========================================
    # Daily Updates (Regime Changes)
    # ========================================

    def update_daily_factors(
        self,
        market_regime: str,
        ema_diff_pct: float = 0.0
    ) -> Dict[str, Any]:
        """
        Update regime-specific parameters.

        Called on regime change or daily at market close.

        Args:
            market_regime: Current market regime (strong_bullish, bullish, neutral, bearish, strong_bearish, ranging)
            ema_diff_pct: EMA50 - EMA200 difference as percentage

        Returns:
            Dict with updated regime parameters
        """
        with self._update_lock:
            self.factors.market_regime = market_regime

            # Get regime-specific strategy parameters
            strategy = self._get_regime_strategy(market_regime)

            self.factors.entry_mode = strategy['entry_mode']
            self.factors.entry_threshold_modifier = strategy['entry_threshold_modifier']
            self.factors.stop_loss_modifier = strategy['stop_loss_modifier']
            self.factors.take_profit_target = strategy['take_profit_target']
            self.factors.full_exit_at_first_target = strategy['full_exit_at_first_target']

            # Adjust Bollinger Band parameters based on regime
            if market_regime in ['bearish', 'strong_bearish']:
                # Wider bands for mean reversion in bear market
                self.factors.bb_period = 25
                self.factors.bb_std_multiplier = 2.5
                self.factors.chandelier_base_multiplier = 3.5
            elif market_regime == 'ranging':
                # Tighter bands for ranging market
                self.factors.bb_period = 15
                self.factors.bb_std_multiplier = 1.5
                self.factors.chandelier_base_multiplier = 2.5
            elif market_regime == 'strong_bullish':
                # Default with slightly wider targets
                self.factors.bb_period = 20
                self.factors.bb_std_multiplier = 2.0
                self.factors.chandelier_base_multiplier = 3.5
            else:
                # Default for bullish/neutral
                self.factors.bb_period = 20
                self.factors.bb_std_multiplier = 2.0
                self.factors.chandelier_base_multiplier = 3.0

            self.factors.last_daily_update = datetime.now().isoformat()
            self._save_factors()

            result = {
                'market_regime': self.factors.market_regime,
                'entry_mode': self.factors.entry_mode,
                'entry_threshold_modifier': self.factors.entry_threshold_modifier,
                'stop_loss_modifier': self.factors.stop_loss_modifier,
                'take_profit_target': self.factors.take_profit_target,
                'full_exit_at_first_target': self.factors.full_exit_at_first_target,
                'bb_period': self.factors.bb_period,
                'bb_std_multiplier': self.factors.bb_std_multiplier,
                'chandelier_base_multiplier': self.factors.chandelier_base_multiplier,
                'ema_diff_pct': ema_diff_pct
            }

            if self.logger:
                self.logger.logger.info(
                    f"[DFM] Daily factors updated: regime={market_regime}, "
                    f"mode={self.factors.entry_mode}, threshold_mod={self.factors.entry_threshold_modifier}x"
                )

            return result

    def _get_regime_strategy(self, regime: str) -> Dict[str, Any]:
        """
        Get strategy parameters for given regime.

        Returns dict with:
        - entry_mode: 'trend' | 'reversion' | 'oscillation'
        - entry_threshold_modifier: float (multiply base entry score)
        - stop_loss_modifier: float
        - take_profit_target: 'bb_middle' | 'bb_upper'
        - full_exit_at_first_target: bool
        """
        strategies = {
            'strong_bullish': {
                'entry_mode': 'trend',
                'entry_threshold_modifier': 0.8,  # Lower threshold (easier entry)
                'stop_loss_modifier': 1.2,        # Wider stops
                'take_profit_target': 'bb_upper',
                'full_exit_at_first_target': False,
            },
            'bullish': {
                'entry_mode': 'trend',
                'entry_threshold_modifier': 1.0,
                'stop_loss_modifier': 1.0,
                'take_profit_target': 'bb_upper',
                'full_exit_at_first_target': False,
            },
            'neutral': {
                'entry_mode': 'oscillation',
                'entry_threshold_modifier': 1.2,
                'stop_loss_modifier': 0.8,
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': False,
            },
            'bearish': {
                'entry_mode': 'reversion',
                'entry_threshold_modifier': 1.3,  # 완화: 1.5 → 1.3
                'stop_loss_modifier': 0.85,       # 여유 확보: 0.7 → 0.85
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': True,  # Full exit at BB middle
            },
            'strong_bearish': {
                'entry_mode': 'reversion',
                'entry_threshold_modifier': 1.5,  # 완화: 2.0 → 1.5
                'stop_loss_modifier': 0.8,        # 여유 확보: 0.5 → 0.8
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': True,
            },
            'ranging': {
                'entry_mode': 'oscillation',
                'entry_threshold_modifier': 1.0,
                'stop_loss_modifier': 0.6,        # Tight for oscillation
                'take_profit_target': 'bb_middle',
                'full_exit_at_first_target': False,
            },
        }

        return strategies.get(regime, strategies['neutral'])

    # ========================================
    # Weekly Updates (Performance-Based)
    # ========================================

    def set_performance_tracker(self, tracker) -> None:
        """
        Inject a PerformanceTracker instance for dependency injection.

        Called by the bot after both components are initialised so the
        AdaptiveWeightEngine can pull trade history without circular imports.

        Args:
            tracker: PerformanceTracker instance (or any object with
                     get_closed_trades(last_n) method).
        """
        self._performance_tracker = tracker

    def update_weekly_factors(
        self,
        win_rate: float,
        profit_factor: float,
        recent_trades: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Update entry weights based on weekly performance.

        When ADAPTIVE_WEIGHT_CONFIG['enable_adaptive_weights'] is True, weights
        are computed by AdaptiveWeightEngine using per-regime win-rate data.
        When False (default), the original hardcoded logic runs unchanged.

        Called weekly (Sunday) or after N trades.

        Args:
            win_rate: Recent win rate (0.0 - 1.0)
            profit_factor: Gross profit / Gross loss
            recent_trades: List of recent trade records with entry_conditions.
                           When None and adaptive mode is on, trades are fetched
                           from the injected PerformanceTracker automatically.

        Returns:
            Dict with updated entry weights
        """
        adaptive_cfg = self.config.get('ADAPTIVE_WEIGHT_CONFIG', {})
        use_adaptive = adaptive_cfg.get('enable_adaptive_weights', False)

        if use_adaptive and self._adaptive_weight_engine is not None:
            return self._adaptive_weekly_update(win_rate, profit_factor, recent_trades)
        else:
            return self._legacy_weekly_update(win_rate, profit_factor, recent_trades)

    def _adaptive_weekly_update(
        self,
        win_rate: float,
        profit_factor: float,
        recent_trades: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Adaptive weight update using AdaptiveWeightEngine.

        Fetches trade history from PerformanceTracker when recent_trades is not
        provided, then delegates weight computation to AdaptiveWeightEngine.
        Applies computed weights back to DynamicFactors for use by the strategy.

        Args:
            win_rate: Overall recent win rate.
            profit_factor: Gross profit / Gross loss ratio.
            recent_trades: Pre-fetched trades (optional).

        Returns:
            Dict with updated entry weights and metadata.
        """
        with self._update_lock:
            adaptive_cfg = self.config.get('ADAPTIVE_WEIGHT_CONFIG', {})
            lookback = adaptive_cfg.get('lookback_trades', 50)

            # Fetch trades from PerformanceTracker if not provided
            if recent_trades is None:
                if self._performance_tracker is not None:
                    try:
                        recent_trades = self._performance_tracker.get_closed_trades(last_n=lookback)
                    except Exception as exc:
                        if self.logger:
                            self.logger.logger.warning(
                                f"[DFM] Could not fetch trades from tracker: {exc}"
                            )
                        recent_trades = []
                else:
                    recent_trades = []

            # Determine current regime from factors
            current_regime = self.factors.market_regime if self.factors.market_regime != 'unknown' else None

            # Compute weights via AdaptiveWeightEngine
            new_weights = self._adaptive_weight_engine.compute_weights(
                recent_trades, current_regime=current_regime
            )

            # Apply computed weights to DynamicFactors
            # Fall back to 1.0 (DEFAULT_WEIGHT) when indicator not in new_weights
            default_w = AdaptiveWeightEngine._DEFAULT_WEIGHT
            self.factors.entry_weight_bb_touch = new_weights.get('bb_touch', default_w)
            self.factors.entry_weight_rsi_oversold = new_weights.get('rsi_oversold', default_w)
            self.factors.entry_weight_stoch_cross = new_weights.get('stoch_cross', default_w)

            # Adjust min entry score based on win rate (same logic as legacy)
            bounds = self.dynamic_config.get('min_entry_score_bounds', (1, 4))
            aggressive_threshold = self.dynamic_config.get('win_rate_aggressive_threshold', 0.6)
            conservative_threshold = self.dynamic_config.get('win_rate_conservative_threshold', 0.4)

            if win_rate < conservative_threshold:
                self.factors.min_entry_score = min(3, bounds[1])
            elif win_rate > aggressive_threshold:
                self.factors.min_entry_score = max(2, bounds[0])
            else:
                self.factors.min_entry_score = 2

            self.factors.last_weekly_update = datetime.now().isoformat()
            self._save_factors()

            result = {
                'entry_weight_bb_touch': self.factors.entry_weight_bb_touch,
                'entry_weight_rsi_oversold': self.factors.entry_weight_rsi_oversold,
                'entry_weight_stoch_cross': self.factors.entry_weight_stoch_cross,
                'min_entry_score': self.factors.min_entry_score,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'trades_analyzed': len(recent_trades),
                'mode': 'adaptive',
                'regime': current_regime,
            }

            if self.logger:
                self.logger.logger.info(
                    f"[DFM] Adaptive weekly update (regime={current_regime}): "
                    f"win_rate={win_rate:.1%}, min_score={self.factors.min_entry_score}, "
                    f"weights=[BB:{self.factors.entry_weight_bb_touch:.3f}, "
                    f"RSI:{self.factors.entry_weight_rsi_oversold:.3f}, "
                    f"Stoch:{self.factors.entry_weight_stoch_cross:.3f}]"
                )

            return result

    def _legacy_weekly_update(
        self,
        win_rate: float,
        profit_factor: float,
        recent_trades: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Original hardcoded weekly update logic (preserved exactly as-is).

        This method is called when enable_adaptive_weights is False (default).
        It must NOT be modified to preserve backward compatibility.

        Args:
            win_rate: Recent win rate (0.0 - 1.0)
            profit_factor: Gross profit / Gross loss
            recent_trades: List of recent trade records with entry_conditions

        Returns:
            Dict with updated entry weights
        """
        with self._update_lock:
            recent_trades = recent_trades or []

            # Analyze which entry conditions worked best
            if len(recent_trades) >= self.dynamic_config.get('min_trades_for_weekly_update', 5):
                bb_trades = [t for t in recent_trades if 'bb_touch' in t.get('entry_conditions', [])]
                rsi_trades = [t for t in recent_trades if 'rsi_oversold' in t.get('entry_conditions', [])]
                stoch_trades = [t for t in recent_trades if 'stoch_cross' in t.get('entry_conditions', [])]

                # Calculate success rates
                bb_wins = sum(1 for t in bb_trades if t.get('profit_krw', 0) > 0)
                rsi_wins = sum(1 for t in rsi_trades if t.get('profit_krw', 0) > 0)
                stoch_wins = sum(1 for t in stoch_trades if t.get('profit_krw', 0) > 0)

                bb_rate = bb_wins / len(bb_trades) if bb_trades else 0.5
                rsi_rate = rsi_wins / len(rsi_trades) if rsi_trades else 0.5
                stoch_rate = stoch_wins / len(stoch_trades) if stoch_trades else 0.5

                # Normalize weights (total ~4 points like original)
                total_rate = bb_rate + rsi_rate + stoch_rate
                if total_rate > 0:
                    base_total = 4.0  # Original total: bb(1) + rsi(1) + stoch(2)
                    self.factors.entry_weight_bb_touch = round(bb_rate / total_rate * base_total * 0.25, 1)
                    self.factors.entry_weight_rsi_oversold = round(rsi_rate / total_rate * base_total * 0.25, 1)
                    self.factors.entry_weight_stoch_cross = round(stoch_rate / total_rate * base_total * 0.5, 1)

                    # Ensure minimum weights
                    self.factors.entry_weight_bb_touch = max(0.5, self.factors.entry_weight_bb_touch)
                    self.factors.entry_weight_rsi_oversold = max(0.5, self.factors.entry_weight_rsi_oversold)
                    self.factors.entry_weight_stoch_cross = max(1.0, self.factors.entry_weight_stoch_cross)

            # Adjust min entry score based on win rate
            bounds = self.dynamic_config.get('min_entry_score_bounds', (1, 4))
            aggressive_threshold = self.dynamic_config.get('win_rate_aggressive_threshold', 0.6)
            conservative_threshold = self.dynamic_config.get('win_rate_conservative_threshold', 0.4)

            if win_rate < conservative_threshold:
                self.factors.min_entry_score = min(3, bounds[1])  # Be more selective
            elif win_rate > aggressive_threshold:
                self.factors.min_entry_score = max(2, bounds[0])  # Can be more aggressive
            else:
                self.factors.min_entry_score = 2  # Default

            self.factors.last_weekly_update = datetime.now().isoformat()
            self._save_factors()

            result = {
                'entry_weight_bb_touch': self.factors.entry_weight_bb_touch,
                'entry_weight_rsi_oversold': self.factors.entry_weight_rsi_oversold,
                'entry_weight_stoch_cross': self.factors.entry_weight_stoch_cross,
                'min_entry_score': self.factors.min_entry_score,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'trades_analyzed': len(recent_trades)
            }

            if self.logger:
                self.logger.logger.info(
                    f"[DFM] Weekly factors updated: win_rate={win_rate:.1%}, "
                    f"min_score={self.factors.min_entry_score}, "
                    f"weights=[BB:{self.factors.entry_weight_bb_touch}, "
                    f"RSI:{self.factors.entry_weight_rsi_oversold}, "
                    f"Stoch:{self.factors.entry_weight_stoch_cross}]"
                )

            return result

    # ========================================
    # Config Integration
    # ========================================

    def get_adjusted_config(self, base_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get configuration with dynamic factors applied.

        Args:
            base_config: Base configuration dictionary

        Returns:
            Configuration with dynamic adjustments applied
        """
        adjusted = copy.deepcopy(base_config)

        # Apply indicator adjustments
        if 'INDICATOR_CONFIG' in adjusted:
            indicator = adjusted['INDICATOR_CONFIG']

            # Dynamic RSI/Stoch thresholds
            indicator['rsi_oversold'] = self.factors.rsi_oversold_threshold
            indicator['stoch_oversold'] = self.factors.stoch_oversold_threshold

            # Dynamic Chandelier multiplier
            base_chandelier = indicator.get('chandelier_multiplier', 3.0)
            adjusted_chandelier = (
                self.factors.chandelier_base_multiplier *
                self.factors.atr_stop_loss_multiplier *
                self.factors.stop_loss_modifier
            )
            # Apply bounds
            bounds = self.dynamic_config.get('chandelier_multiplier_bounds', (2.0, 5.0))
            indicator['chandelier_multiplier'] = max(bounds[0], min(bounds[1], adjusted_chandelier))

            # Dynamic BB parameters
            indicator['bb_period'] = self.factors.bb_period
            indicator['bb_std'] = self.factors.bb_std_multiplier

        # Apply entry scoring adjustments
        if 'ENTRY_SCORING_CONFIG' in adjusted:
            entry = adjusted['ENTRY_SCORING_CONFIG']

            # Dynamic min entry score with regime modifier
            base_min_score = self.factors.min_entry_score
            adjusted_min_score = int(base_min_score * self.factors.entry_threshold_modifier)
            entry['min_entry_score'] = max(1, min(4, adjusted_min_score))

            # Dynamic scoring weights
            scoring_rules = entry.get('scoring_rules', {})
            if 'bb_touch' in scoring_rules:
                scoring_rules['bb_touch']['points'] = self.factors.entry_weight_bb_touch
            if 'rsi_oversold' in scoring_rules:
                scoring_rules['rsi_oversold']['points'] = self.factors.entry_weight_rsi_oversold
            if 'stoch_rsi_cross' in scoring_rules:
                scoring_rules['stoch_rsi_cross']['points'] = self.factors.entry_weight_stoch_cross

        # Apply position sizing adjustments
        if 'POSITION_SIZING_CONFIG' in adjusted:
            sizing = adjusted['POSITION_SIZING_CONFIG']
            base_amount = sizing.get('base_amount_krw', 50000)
            sizing['base_amount_krw'] = int(base_amount * self.factors.position_size_multiplier)

        # Apply exit config adjustments
        if 'EXIT_CONFIG' in adjusted:
            exit_config = adjusted['EXIT_CONFIG']

            # Set profit target based on regime
            exit_config['first_target'] = 'bb_middle'
            if self.factors.take_profit_target == 'bb_upper':
                exit_config['second_target'] = 'bb_upper'
            else:
                exit_config['second_target'] = 'bb_middle'

            # Full exit flag for bearish regime
            exit_config['full_exit_at_first_target'] = self.factors.full_exit_at_first_target

        # Add dynamic factors metadata
        adjusted['DYNAMIC_FACTORS'] = {
            'market_regime': self.factors.market_regime,
            'entry_mode': self.factors.entry_mode,
            'volatility_level': self.factors.volatility_level,
            'atr_pct': self.factors.current_atr_pct,
            'stop_loss_multiplier': self.factors.atr_stop_loss_multiplier,
            'position_size_multiplier': self.factors.position_size_multiplier,
            'entry_threshold_modifier': self.factors.entry_threshold_modifier,
            'last_update': self.factors.last_realtime_update,
        }

        return adjusted

    def get_current_factors(self) -> Dict[str, Any]:
        """
        Get current factor values for display/logging.

        Returns user-friendly format with:
        - entry_weights: Dict of condition weights
        - volatility_level: Current volatility classification
        - All other individual factors
        """
        factors_dict = self.factors.to_dict()

        # Add entry_weights as nested dict for convenience
        factors_dict['entry_weights'] = {
            'bb_touch': self.factors.entry_weight_bb_touch,
            'rsi_oversold': self.factors.entry_weight_rsi_oversold,
            'stoch_cross': self.factors.entry_weight_stoch_cross,
            # Phase 2: VWAP/MACD weights
            'vwap': self.factors.entry_weight_vwap,
            'macd': self.factors.entry_weight_macd,
        }

        # Add chandelier_multiplier_modifier for compatibility
        factors_dict['chandelier_multiplier_modifier'] = self.factors.atr_stop_loss_multiplier
        factors_dict['position_size_modifier'] = self.factors.position_size_multiplier

        return factors_dict

    def get_regime_info(self) -> Dict[str, Any]:
        """Get current regime and strategy info for display."""
        return {
            'market_regime': self.factors.market_regime,
            'entry_mode': self.factors.entry_mode,
            'volatility_level': self.factors.volatility_level,
            'entry_threshold_modifier': self.factors.entry_threshold_modifier,
            'stop_loss_modifier': self.factors.stop_loss_modifier,
            'take_profit_target': self.factors.take_profit_target,
            'full_exit_at_first_target': self.factors.full_exit_at_first_target,
        }

    # ========================================
    # Persistence
    # ========================================

    def _load_factors(self):
        """Load factors from file."""
        try:
            if self.factors_file.exists():
                with open(self.factors_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.factors = DynamicFactors.from_dict(data)
                if self.logger:
                    self.logger.logger.info(f"[DFM] Loaded factors from {self.factors_file}")
        except Exception as e:
            if self.logger:
                self.logger.log_error("Failed to load dynamic factors", e)
            # Use default factors
            self.factors = DynamicFactors()

    def _save_factors(self):
        """Save factors to file."""
        try:
            self.factors_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.factors_file, 'w', encoding='utf-8') as f:
                json.dump(self.factors.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            if self.logger:
                self.logger.log_error("Failed to save dynamic factors", e)

    def reset_factors(self):
        """Reset factors to defaults."""
        with self._update_lock:
            self.factors = DynamicFactors()
            self._last_atr_values.clear()
            self._save_factors()
            if self.logger:
                self.logger.logger.info("[DFM] Factors reset to defaults")

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (for testing)."""
        with cls._lock:
            cls._instance = None


# Factory function for easy access
_manager_instance: Optional[DynamicFactorManager] = None

def get_dynamic_factor_manager(
    config: Dict[str, Any] = None,
    logger = None
) -> DynamicFactorManager:
    """
    Factory function to get DynamicFactorManager singleton.

    Args:
        config: Configuration dictionary (only used on first call)
        logger: TradingLogger instance (only used on first call)

    Returns:
        DynamicFactorManager singleton instance
    """
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = DynamicFactorManager(config, logger)
    return _manager_instance


def reset_dynamic_factor_manager():
    """Reset the singleton instance (for testing)."""
    global _manager_instance
    DynamicFactorManager.reset_instance()
    _manager_instance = None
