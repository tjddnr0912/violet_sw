"""
Position Manager - Version 2

This module manages the complete position lifecycle from entry to exit:
- Position size calculation (2% risk-based)
- Chandelier Exit trailing stop management
- Scaling exit logic (50% at first target, 50% at second target)
- Breakeven stop adjustment
- Exit condition monitoring

State Machine: INITIAL_ENTRY → FIRST_TARGET → RISK_FREE_RUNNER → EXIT
"""

import backtrader as bt
from typing import Dict, Any, Optional


class PositionManager:
    """
    Manages position lifecycle with asymmetric risk-reward scaling.

    This is the heart of the strategy's profitability. The scaling protocol
    creates POSITIVE ASYMMETRY:
    - Losing trades: -1.0R (stopped out early)
    - Small winners: +0.5R (first target hit, then breakeven)
    - Big winners: +1.125R (first target + trailing stop captures trend)

    The 2% risk per trade with 50% initial entry is textbook asymmetric
    risk management. This is NOT amateur hour.
    """

    def __init__(
        self,
        strategy: bt.Strategy,
        atr_multiplier: float,
        indicators,
        initial_pct: float = 0.50,
        first_exit_pct: float = 0.50
    ):
        """
        Initialize position manager.

        Args:
            strategy: Reference to main Backtrader strategy
            atr_multiplier: ATR multiplier for Chandelier Exit (3.0)
            indicators: IndicatorCalculator instance
            initial_pct: Initial entry percentage (default: 50%)
            first_exit_pct: First target exit percentage (default: 50%)
        """
        self.strategy = strategy
        self.atr_multiplier = atr_multiplier
        self.indicators = indicators
        self.initial_pct = initial_pct
        self.first_exit_pct = first_exit_pct

        # Position state tracking
        self.position_state: Optional[Dict[str, Any]] = None

    def calculate_entry_size(
        self,
        entry_price: float,
        atr: float,
        portfolio_value: float,
        risk_per_trade: float
    ) -> Dict[str, float]:
        """
        Calculate position size based on 2% portfolio risk.

        Master Position Sizing Formula:
        1. Calculate maximum risk per trade: portfolio_value × risk_per_trade
        2. Calculate initial stop distance: entry_price - (ATR × multiplier)
        3. Calculate risk per unit: entry_price - initial_stop
        4. Calculate full size: max_risk_usd / risk_per_unit
        5. Apply scaling entry: full_size × initial_pct

        Args:
            entry_price: Entry price for the trade
            atr: Current ATR value
            portfolio_value: Current portfolio value
            risk_per_trade: Risk percentage per trade (0.02 = 2%)

        Returns:
            Dictionary with entry_size, full_size, initial_stop, entry_price

        Raises:
            ValueError: If risk_per_unit is invalid (<=0)
        """
        # Step 1: Calculate maximum risk per trade
        max_risk_usd = portfolio_value * risk_per_trade

        # Step 2: Calculate initial stop distance
        initial_stop = entry_price - (atr * self.atr_multiplier)

        # Step 3: Calculate risk per unit
        risk_per_unit = entry_price - initial_stop

        # Validation: Prevent division by zero or negative risk
        if risk_per_unit <= 0:
            raise ValueError(
                f"Invalid risk_per_unit: {risk_per_unit:.2f} "
                f"(entry: {entry_price:.2f}, stop: {initial_stop:.2f})"
            )

        # Step 4: Calculate full position size
        full_size = max_risk_usd / risk_per_unit

        # Step 5: Apply 50% initial entry (probe position)
        entry_size = full_size * self.initial_pct

        return {
            'entry_price': entry_price,
            'entry_size': entry_size,
            'full_size': full_size,
            'initial_stop': initial_stop,
            'atr_at_entry': atr,
            'max_risk_usd': max_risk_usd,
        }

    def initialize_position(
        self,
        entry_price: float,
        entry_size: float,
        full_size: float,
        initial_stop: float,
        entry_score: int
    ) -> Dict[str, Any]:
        """
        Initialize position tracking dictionary after entry execution.

        Args:
            entry_price: Executed entry price
            entry_size: Executed entry size (50% of full)
            full_size: Calculated full position size
            initial_stop: Initial Chandelier stop price
            entry_score: Entry signal score (3-4)

        Returns:
            Position state dictionary
        """
        self.position_state = {
            'entry_time': self.strategy.data.datetime.datetime(0),
            'entry_price': entry_price,
            'full_size': full_size,
            'current_size': entry_size,
            'highest_high': self.strategy.data.high[0],
            'chandelier_stop': initial_stop,
            'first_target_hit': False,
            'breakeven_moved': False,
            'phase': 'INITIAL_ENTRY',
            'entry_score': entry_score,
        }

        print(f"✅ POSITION INITIALIZED:")
        print(f"   Entry: ${entry_price:.2f}, Size: {entry_size:.4f}")
        print(f"   Stop: ${initial_stop:.2f}, Score: {entry_score}/4")

        return self.position_state

    def manage_existing_position(self, data: bt.DataBase):
        """
        Manage active position - check exits and update stops.

        Execution Priority (evaluated in order):
        1. Chandelier stop hit → EXIT (stop loss or breakeven)
        2. BB Upper hit → EXIT (final target)
        3. BB Middle hit → SCALE OUT 50% and move to breakeven
        4. Update trailing stop upward only

        This order ensures stops are checked first (risk management priority).

        Args:
            data: Current 4H bar data
        """
        if not self.position_state:
            return

        current_high = data.high[0]
        current_low = data.low[0]
        current_atr = self.indicators.atr[0]

        # ===== Update Highest High for Chandelier Calculation =====
        if current_high > self.position_state['highest_high']:
            self.position_state['highest_high'] = current_high

        # ===== Recalculate Chandelier Stop (Only Moves Up) =====
        new_chandelier = self.position_state['highest_high'] - (current_atr * self.atr_multiplier)

        if new_chandelier > self.position_state['chandelier_stop']:
            old_stop = self.position_state['chandelier_stop']
            self.position_state['chandelier_stop'] = new_chandelier
            print(f"📈 STOP TRAILED: ${old_stop:.2f} → ${new_chandelier:.2f}")

        # ===== EXIT CHECK 1: Chandelier Stop Hit =====
        if current_low <= self.position_state['chandelier_stop']:
            self.strategy.close()
            exit_type = "BREAKEVEN" if self.position_state['breakeven_moved'] else "STOP_LOSS"
            print(f"❌ EXIT: {exit_type} at ${self.position_state['chandelier_stop']:.2f}")
            self.position_state = None
            return

        # ===== EXIT CHECK 2: Final Target (BB Upper) =====
        if current_high >= self.indicators.bb_upper[0]:
            self.strategy.close()
            print(f"🎯 EXIT: FINAL TARGET (BB Upper) at ${self.indicators.bb_upper[0]:.2f}")
            self.position_state = None
            return

        # ===== SCALING CHECK: First Target (BB Middle) =====
        if not self.position_state['first_target_hit']:
            if current_high >= self.indicators.bb_mid[0]:
                # Exit 50% of current position
                exit_size = self.strategy.position.size * self.first_exit_pct
                self.strategy.sell(size=exit_size)

                # Move stop to breakeven
                self.position_state['chandelier_stop'] = self.position_state['entry_price']
                self.position_state['first_target_hit'] = True
                self.position_state['breakeven_moved'] = True
                self.position_state['phase'] = 'RISK_FREE_RUNNER'

                print(f"🎯 FIRST TARGET: Sold {self.first_exit_pct*100:.0f}% at ${self.indicators.bb_mid[0]:.2f}")
                print(f"   Stop moved to BREAKEVEN: ${self.position_state['entry_price']:.2f}")

    def reset_position_state(self):
        """
        Reset position tracking after complete exit.

        This should be called after position closure to clean up state.
        """
        self.position_state = None

    def get_position_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current position information.

        Returns:
            Position state dictionary or None if no position
        """
        return self.position_state

    def calculate_unrealized_pnl(self, current_price: float) -> float:
        """
        Calculate unrealized P&L for current position.

        Args:
            current_price: Current market price

        Returns:
            Unrealized P&L in dollars
        """
        if not self.position_state:
            return 0.0

        entry_price = self.position_state['entry_price']
        current_size = self.position_state['current_size']

        pnl = (current_price - entry_price) * current_size
        return pnl

    def calculate_risk_reward_ratio(self) -> Dict[str, float]:
        """
        Calculate current risk-reward ratio.

        Returns:
            Dictionary with risk, reward, and R:R ratio
        """
        if not self.position_state:
            return {}

        entry_price = self.position_state['entry_price']
        stop_price = self.position_state['chandelier_stop']
        target1_price = self.indicators.bb_mid[0]
        target2_price = self.indicators.bb_upper[0]

        risk_per_unit = entry_price - stop_price
        reward1_per_unit = target1_price - entry_price
        reward2_per_unit = target2_price - entry_price

        return {
            'risk': risk_per_unit,
            'reward_target1': reward1_per_unit,
            'reward_target2': reward2_per_unit,
            'rr_ratio_target1': reward1_per_unit / risk_per_unit if risk_per_unit > 0 else 0,
            'rr_ratio_target2': reward2_per_unit / risk_per_unit if risk_per_unit > 0 else 0,
        }
