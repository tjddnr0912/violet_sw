"""
Risk Manager - Version 2

This module implements risk management guardrails and circuit breakers to
protect capital during adverse conditions.

Risk Controls:
- Consecutive loss circuit breaker
- Daily loss limit
- Maximum daily trades
- Position size validation
"""

from typing import Dict, Any


class RiskManager:
    """
    Risk management guardrails and circuit breakers.

    Purpose: Prevent catastrophic losses through systematic risk controls.

    The risk manager acts as a GATEKEEPER - it has veto power over all trades.
    Even if entry signals are perfect, the risk manager can block trades if
    risk conditions are exceeded.

    Professional Note:
    Most amateur traders focus on entry signals and ignore risk management.
    This is backwards. Risk management is MORE important than entry signals.
    You can have mediocre entries and still be profitable with excellent
    risk management, but you CANNOT have excellent entries and survive with
    poor risk management.
    """

    def __init__(
        self,
        max_consecutive_losses: int = 5,
        max_daily_loss_pct: float = 0.05,
        max_daily_trades: int = 2
    ):
        """
        Initialize risk manager with risk limits.

        Args:
            max_consecutive_losses: Maximum consecutive losses before circuit breaker (default: 5)
            max_daily_loss_pct: Maximum daily loss as percentage of portfolio (default: 0.05 = 5%)
            max_daily_trades: Maximum number of trades allowed per day (default: 2)
        """
        self.max_consecutive_losses = max_consecutive_losses
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_daily_trades = max_daily_trades

    def validate_entry(
        self,
        consecutive_losses: int,
        daily_pnl: float,
        portfolio_value: float,
        daily_trade_count: int = 0
    ) -> bool:
        """
        Validate if entry is allowed under current risk constraints.

        This method is called AFTER entry signals are confirmed but BEFORE
        order execution. It acts as the final gatekeeper.

        Args:
            consecutive_losses: Number of consecutive losing trades
            daily_pnl: Today's profit/loss in dollars
            portfolio_value: Current portfolio value
            daily_trade_count: Number of trades executed today

        Returns:
            True if entry approved, False if rejected

        Rejection Reasons:
        1. Consecutive loss circuit breaker triggered
        2. Daily loss limit exceeded
        3. Maximum daily trades reached
        """
        # ===== CHECK 1: Consecutive Loss Circuit Breaker =====
        if consecutive_losses >= self.max_consecutive_losses:
            print(f"⛔ RISK MANAGER: Entry REJECTED")
            print(f"   Reason: Consecutive loss circuit breaker triggered")
            print(f"   Losses: {consecutive_losses} (Max: {self.max_consecutive_losses})")
            print(f"   Action: Stop trading until reset")
            return False

        # ===== CHECK 2: Daily Loss Limit =====
        daily_loss_pct = daily_pnl / portfolio_value if portfolio_value > 0 else 0

        if daily_loss_pct <= -self.max_daily_loss_pct:
            print(f"⛔ RISK MANAGER: Entry REJECTED")
            print(f"   Reason: Daily loss limit exceeded")
            print(f"   Daily Loss: {daily_loss_pct:.2%} (Max: {self.max_daily_loss_pct:.2%})")
            print(f"   Daily P&L: ${daily_pnl:.2f}")
            print(f"   Action: No more trades today")
            return False

        # ===== CHECK 3: Maximum Daily Trades =====
        if daily_trade_count >= self.max_daily_trades:
            print(f"⛔ RISK MANAGER: Entry REJECTED")
            print(f"   Reason: Maximum daily trades reached")
            print(f"   Trades Today: {daily_trade_count} (Max: {self.max_daily_trades})")
            print(f"   Action: No more trades today")
            return False

        # All checks passed
        return True

    def validate_position_size(
        self,
        position_size: float,
        portfolio_value: float,
        max_position_pct: float = 0.10
    ) -> bool:
        """
        Validate if position size is within acceptable limits.

        Args:
            position_size: Proposed position size in dollars
            portfolio_value: Current portfolio value
            max_position_pct: Maximum position size as percentage of portfolio

        Returns:
            True if position size is acceptable, False otherwise
        """
        if portfolio_value <= 0:
            return False

        position_pct = position_size / portfolio_value

        if position_pct > max_position_pct:
            print(f"⚠️  RISK MANAGER: Position size warning")
            print(f"   Position: {position_pct:.2%} of portfolio (Max: {max_position_pct:.2%})")
            return False

        return True

    def calculate_risk_metrics(
        self,
        consecutive_losses: int,
        daily_pnl: float,
        portfolio_value: float,
        daily_trade_count: int
    ) -> Dict[str, Any]:
        """
        Calculate current risk metrics and status.

        Returns:
            Dictionary with risk metrics and status
        """
        daily_loss_pct = daily_pnl / portfolio_value if portfolio_value > 0 else 0

        return {
            'consecutive_losses': consecutive_losses,
            'max_consecutive_losses': self.max_consecutive_losses,
            'circuit_breaker_triggered': consecutive_losses >= self.max_consecutive_losses,
            'daily_pnl': daily_pnl,
            'daily_loss_pct': daily_loss_pct,
            'max_daily_loss_pct': self.max_daily_loss_pct,
            'daily_loss_limit_exceeded': daily_loss_pct <= -self.max_daily_loss_pct,
            'daily_trade_count': daily_trade_count,
            'max_daily_trades': self.max_daily_trades,
            'daily_trade_limit_reached': daily_trade_count >= self.max_daily_trades,
            'can_trade': self.validate_entry(
                consecutive_losses,
                daily_pnl,
                portfolio_value,
                daily_trade_count
            ),
        }

    def reset_daily_counters(self) -> None:
        """
        Reset daily counters at start of new trading day.

        Note: This should be called by the strategy at the start of each day.
        In backtesting, this is handled by tracking the date change.
        """
        # This is a placeholder - actual reset is handled by strategy
        # which tracks daily_pnl and daily_trade_count
        pass

    def should_emergency_stop(
        self,
        portfolio_value: float,
        initial_capital: float,
        max_drawdown_pct: float = 0.25
    ) -> bool:
        """
        Check if emergency stop should be triggered due to excessive drawdown.

        This is the NUCLEAR OPTION - complete halt of trading.

        Args:
            portfolio_value: Current portfolio value
            initial_capital: Initial capital
            max_drawdown_pct: Maximum acceptable drawdown (default: 0.25 = 25%)

        Returns:
            True if emergency stop should be triggered
        """
        if initial_capital <= 0:
            return False

        current_drawdown = (initial_capital - portfolio_value) / initial_capital

        if current_drawdown >= max_drawdown_pct:
            print(f"🚨 EMERGENCY STOP TRIGGERED")
            print(f"   Drawdown: {current_drawdown:.2%} (Max: {max_drawdown_pct:.2%})")
            print(f"   Initial Capital: ${initial_capital:.2f}")
            print(f"   Current Value: ${portfolio_value:.2f}")
            print(f"   Loss: ${initial_capital - portfolio_value:.2f}")
            print(f"   ACTION: All trading halted")
            return True

        return False

    def get_risk_status_report(
        self,
        consecutive_losses: int,
        daily_pnl: float,
        portfolio_value: float,
        daily_trade_count: int
    ) -> str:
        """
        Generate human-readable risk status report.

        Returns:
            Formatted risk status string
        """
        metrics = self.calculate_risk_metrics(
            consecutive_losses,
            daily_pnl,
            portfolio_value,
            daily_trade_count
        )

        status = "✅ NORMAL" if metrics['can_trade'] else "🚫 TRADING BLOCKED"

        report = f"""
╔════════════════════════════════════════════════════════╗
║            RISK MANAGER STATUS: {status}             ║
╠════════════════════════════════════════════════════════╣
║ Consecutive Losses: {consecutive_losses}/{self.max_consecutive_losses}
║ Circuit Breaker: {'TRIGGERED ⛔' if metrics['circuit_breaker_triggered'] else 'Normal ✅'}
║
║ Daily P&L: ${daily_pnl:.2f}
║ Daily Loss %: {metrics['daily_loss_pct']:.2%}
║ Max Daily Loss: {self.max_daily_loss_pct:.2%}
║ Daily Loss Limit: {'EXCEEDED ⛔' if metrics['daily_loss_limit_exceeded'] else 'Normal ✅'}
║
║ Trades Today: {daily_trade_count}/{self.max_daily_trades}
║ Daily Trade Limit: {'REACHED ⛔' if metrics['daily_trade_limit_reached'] else 'Normal ✅'}
╚════════════════════════════════════════════════════════╝
        """

        return report
