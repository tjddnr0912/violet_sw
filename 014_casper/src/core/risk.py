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
        self._current_week: Optional[int] = None
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def reset_if_new_week(self, week_number: int) -> None:
        """Reset circuit breaker on new week."""
        if self._current_week != week_number:
            if self._active:
                logger.info("CB: Reset for new week")
            self._current_week = week_number
            self._consecutive_losses = 0
            self._weekly_loss = 0.0
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

        # Check weekly loss trigger
        if capital > 0:
            loss_pct = (self._weekly_loss / capital) * 100
            if loss_pct >= self.max_weekly_loss_pct:
                self._active = True
                logger.warning(
                    f"CB ACTIVE: Weekly loss {loss_pct:.1f}% >= {self.max_weekly_loss_pct}%"
                )

    def load_from_trades(self, trades: List[dict], current_week: int) -> None:
        """Restore CB state from historical trades for current week."""
        self._current_week = current_week
        self._consecutive_losses = 0
        self._weekly_loss = 0.0
        self._active = False

        for t in trades:
            if t.get("week") == current_week:
                self.record_trade(t["result"], t["net_pnl"], t.get("capital", 1))
