"""Risk management module.

Implements VIX filter, trend filter, circuit breaker, and ORB size filter.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List
from datetime import date

logger = logging.getLogger("casper")


@dataclass
class TrendState:
    """Market trend determination."""
    direction: str   # "bull" or "bear"
    qqq_close: float
    qqq_ma20: float
    symbol: str      # TQQQ or SQQQ


@dataclass
class RiskFilters:
    """Result of pre-market risk checks."""
    can_trade: bool
    skip_reason: Optional[str] = None
    trend: Optional[TrendState] = None
    vix_value: Optional[float] = None


def check_vix_filter(vix_close: float, vix_low: float = 12.0, vix_high: float = 30.0) -> Optional[str]:
    """
    Check VIX filter. Returns skip reason or None.

    Args:
        vix_close: Latest VIX close.
        vix_low: Minimum VIX threshold.
        vix_high: Maximum VIX threshold.

    Returns:
        Skip reason string if filtered, None if OK.
    """
    if vix_close < vix_low:
        reason = f"VIX {vix_close:.1f} < {vix_low} (too low)"
        logger.info(f"RISK: {reason}")
        return reason
    if vix_close > vix_high:
        reason = f"VIX {vix_close:.1f} > {vix_high} (too high)"
        logger.info(f"RISK: {reason}")
        return reason
    logger.debug(f"RISK: VIX {vix_close:.1f} OK (range {vix_low}-{vix_high})")
    return None


def determine_trend(
    qqq_close: float,
    qqq_ma20: float,
    bull_symbol: str = "TQQQ",
    bear_symbol: str = "SQQQ",
) -> TrendState:
    """
    Determine market trend from QQQ vs 20MA.

    Args:
        qqq_close: QQQ previous close.
        qqq_ma20: QQQ 20-day moving average.
        bull_symbol: Symbol for bullish trades.
        bear_symbol: Symbol for bearish trades.

    Returns:
        TrendState with direction and trading symbol.
    """
    if qqq_close > qqq_ma20:
        direction = "bull"
        symbol = bull_symbol
    else:
        direction = "bear"
        symbol = bear_symbol

    logger.info(
        f"TREND: QQQ Close={qqq_close:.2f} MA20={qqq_ma20:.2f} "
        f"→ {direction.upper()} → {symbol}"
    )
    return TrendState(
        direction=direction,
        qqq_close=qqq_close,
        qqq_ma20=qqq_ma20,
        symbol=symbol,
    )


class CircuitBreaker:
    """Weekly circuit breaker tracking."""

    def __init__(self, max_consecutive_losses: int = 3, max_weekly_loss_pct: float = 3.0):
        self.max_consecutive_losses = max_consecutive_losses
        self.max_weekly_loss_pct = max_weekly_loss_pct
        self._consecutive_losses = 0
        self._weekly_loss = 0.0
        self._week_start_capital = 0.0
        self._current_week: Optional[int] = None
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def reset_if_new_week(self, week_number: int, capital: float = 0.0) -> None:
        """Reset circuit breaker on new week."""
        if self._current_week != week_number:
            if self._active:
                logger.info("CB: Reset for new week")
            self._current_week = week_number
            self._consecutive_losses = 0
            self._weekly_loss = 0.0
            self._week_start_capital = capital
            self._active = False

    def record_trade(self, result: str, net_pnl: float, capital: float) -> None:
        """
        Record trade result and check triggers.

        Args:
            result: "WIN", "LOSS", or "BE".
            net_pnl: Net P&L of the trade.
            capital: Current capital after trade.
        """
        if result == "LOSS":
            self._consecutive_losses += 1
            self._weekly_loss += abs(net_pnl)
            logger.debug(f"CB: Consecutive losses: {self._consecutive_losses}")
        else:
            self._consecutive_losses = 0

        # Check consecutive loss trigger
        if self._consecutive_losses >= self.max_consecutive_losses:
            self._active = True
            logger.warning(
                f"CB ACTIVE: {self._consecutive_losses} consecutive losses"
            )
            return

        # Check weekly loss trigger (based on week-start capital)
        base_capital = self._week_start_capital if self._week_start_capital > 0 else capital
        if base_capital > 0:
            loss_pct = (self._weekly_loss / base_capital) * 100
            if loss_pct >= self.max_weekly_loss_pct:
                self._active = True
                logger.warning(
                    f"CB ACTIVE: Weekly loss {loss_pct:.1f}% >= {self.max_weekly_loss_pct}%"
                )

    def correct_last_trade(self, old_result: str, old_pnl: float, actual_pnl: float) -> None:
        """Correct the last trade's impact on CB state after broker reconciliation.

        Args:
            old_result: Original result ("WIN", "LOSS", "BE").
            old_pnl: Originally recorded net PnL.
            actual_pnl: Actual net PnL from broker.
        """
        actual_result = "LOSS" if actual_pnl < -0.01 else ("WIN" if actual_pnl > 0.01 else "BE")

        # Reverse old impact
        if old_result == "LOSS":
            self._weekly_loss -= abs(old_pnl)
            if self._weekly_loss < 0:
                self._weekly_loss = 0.0
            self._consecutive_losses = max(0, self._consecutive_losses - 1)

        # Apply actual impact
        if actual_result == "LOSS":
            self._weekly_loss += abs(actual_pnl)
            self._consecutive_losses += 1
        elif actual_result in ("WIN", "BE"):
            # A WIN/BE always resets the streak (mirrors record_trade logic)
            self._consecutive_losses = 0

        # Re-evaluate CB activation
        triggered = False
        if self._consecutive_losses >= self.max_consecutive_losses:
            triggered = True
        base = self._week_start_capital if self._week_start_capital > 0 else 1.0
        if (self._weekly_loss / base) * 100 >= self.max_weekly_loss_pct:
            triggered = True
        self._active = triggered

        if not triggered and old_result != actual_result:
            logger.info(
                f"CB CORRECTED: {old_result} PnL=${old_pnl:+.2f} → "
                f"{actual_result} PnL=${actual_pnl:+.2f}"
            )

    def load_from_trades(self, trades: List[dict], current_week: int) -> None:
        """Restore CB state from historical trades for current week."""
        self._current_week = current_week
        self._consecutive_losses = 0
        self._weekly_loss = 0.0
        self._week_start_capital = 0.0
        self._active = False

        # Find week-start capital from the first trade of this week
        for t in trades:
            if t.get("week") == current_week:
                cap = t.get("capital_after", 0)
                pnl = t.get("net_pnl", 0)
                if cap > 0 and self._week_start_capital == 0:
                    self._week_start_capital = cap - pnl  # Capital before first trade
                break

        for t in trades:
            if t.get("week") == current_week:
                capital = t.get("capital_after", 0)
                if capital <= 0:
                    capital = t.get("capital", 0)
                if capital <= 0:
                    continue
                self.record_trade(t["result"], t["net_pnl"], capital)
