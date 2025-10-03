"""
Market Regime Filter - Version 2

This module implements the daily EMA Golden/Death Cross regime filter
to determine when the strategy should be active (bullish regime only).

Purpose:
- Filter trading opportunities to favorable market conditions
- Avoid catastrophic drawdown during bearish trends
- Implement hysteresis to prevent whipsaw during regime transitions
"""

import backtrader as bt
from typing import Literal


class RegimeFilter:
    """
    Market regime detector using Daily EMA crossover with hysteresis buffer.

    The regime filter is the FIRST line of defense in the strategy. It answers
    the question: "Is this a market environment where we want to trade?"

    Algorithm:
    1. Calculate EMA50 and EMA200 on daily timeframe
    2. Compare: If EMA50 > EMA200 → BULLISH (allow trading)
    3. Apply hysteresis buffer (2 bars confirmation) to prevent rapid switching
    4. If BEARISH: Block all new entries, only manage existing positions

    Professional Note:
    The 50/200 EMA crossover is a battle-tested regime filter used by institutional
    traders. It's not perfect, but it effectively reduces drawdown by 30-50%
    compared to always-on systems.
    """

    def __init__(
        self,
        data: bt.DataBase,
        ema_fast_period: int = 50,
        ema_slow_period: int = 200,
        confirmation_bars: int = 2
    ):
        """
        Initialize regime filter with EMA crossover parameters.

        Args:
            data: Backtrader daily data feed
            ema_fast_period: Fast EMA period (default: 50)
            ema_slow_period: Slow EMA period (default: 200)
            confirmation_bars: Number of bars to confirm regime change (hysteresis)
        """
        self.data = data
        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.confirmation_bars = confirmation_bars

        # Calculate EMAs using Backtrader indicators
        self.ema_fast = bt.indicators.EMA(
            data.close,
            period=ema_fast_period
        )
        self.ema_slow = bt.indicators.EMA(
            data.close,
            period=ema_slow_period
        )

        # State tracking for hysteresis
        self.current_regime = "NEUTRAL"  # Start in neutral state
        self.regime_change_count = 0

    def get_current_regime(self) -> Literal["BULLISH", "BEARISH", "NEUTRAL"]:
        """
        Determine current market regime with hysteresis buffer.

        The hysteresis buffer prevents rapid on/off switching during choppy
        crossover periods. A regime change requires confirmation for N consecutive
        bars before being accepted.

        Returns:
            Current regime status: "BULLISH", "BEARISH", or "NEUTRAL"

        Trading Permissions:
            BULLISH: New entries allowed, full position management
            BEARISH: New entries forbidden, exit-only mode
            NEUTRAL: Initial state before sufficient data
        """
        # Check if indicators are ready
        if len(self.ema_fast) < self.ema_slow_period:
            return "NEUTRAL"

        # Get latest EMA values
        ema_fast_val = self.ema_fast[0]
        ema_slow_val = self.ema_slow[0]

        # Determine raw regime from current EMA positions
        if ema_fast_val > ema_slow_val:
            raw_regime = "BULLISH"
        else:
            raw_regime = "BEARISH"

        # Apply hysteresis buffer to prevent whipsaw
        if raw_regime != self.current_regime:
            # Regime is trying to change
            self.regime_change_count += 1

            if self.regime_change_count >= self.confirmation_bars:
                # Change confirmed after N consecutive bars
                old_regime = self.current_regime
                self.current_regime = raw_regime
                self.regime_change_count = 0

                # Log regime change for debugging
                print(f"⚠️  REGIME CHANGE: {old_regime} → {self.current_regime}")
                print(f"   EMA50: {ema_fast_val:.2f}, EMA200: {ema_slow_val:.2f}")
            else:
                # Still waiting for confirmation
                pass
        else:
            # Regime aligns with current state, reset counter
            self.regime_change_count = 0

        return self.current_regime

    def is_bullish(self) -> bool:
        """
        Check if current regime is bullish (trading allowed).

        Returns:
            True if bullish regime, False otherwise
        """
        return self.get_current_regime() == "BULLISH"

    def is_bearish(self) -> bool:
        """
        Check if current regime is bearish (trading forbidden).

        Returns:
            True if bearish regime, False otherwise
        """
        return self.get_current_regime() == "BEARISH"

    def get_regime_data(self) -> dict:
        """
        Get current regime data for logging/reporting.

        Returns:
            Dictionary with regime status and EMA values
        """
        return {
            'regime': self.current_regime,
            'ema_fast': self.ema_fast[0] if len(self.ema_fast) > 0 else None,
            'ema_slow': self.ema_slow[0] if len(self.ema_slow) > 0 else None,
            'ema_fast_period': self.ema_fast_period,
            'ema_slow_period': self.ema_slow_period,
            'confirmation_pending': self.regime_change_count > 0,
            'bars_until_confirmation': max(0, self.confirmation_bars - self.regime_change_count)
        }

    def get_ema_distance(self) -> float:
        """
        Calculate distance between fast and slow EMA (as percentage).

        This can be used as a measure of trend strength.
        Positive values indicate bullish regime, negative indicate bearish.

        Returns:
            Percentage distance between EMAs
        """
        if len(self.ema_fast) < self.ema_slow_period:
            return 0.0

        ema_fast_val = self.ema_fast[0]
        ema_slow_val = self.ema_slow[0]

        if ema_slow_val == 0:
            return 0.0

        distance_pct = ((ema_fast_val - ema_slow_val) / ema_slow_val) * 100
        return distance_pct

    def is_ready(self) -> bool:
        """
        Check if regime filter has sufficient data.

        Returns:
            True if ready (EMA200 calculated), False otherwise
        """
        return len(self.ema_slow) >= self.ema_slow_period
