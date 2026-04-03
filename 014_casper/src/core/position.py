"""Position management module.

Tracks open positions, monitors stop/target, handles BE-move and force-close.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.core.strategy import TradeSignal

logger = logging.getLogger("casper")


@dataclass
class Position:
    """Active trading position."""
    symbol: str
    direction: str          # "long"
    entry_price: float
    stop_loss: float
    take_profit: float
    shares: int
    risk_per_share: float
    commission_rate: float
    entry_time: str
    signal: TradeSignal

    # Mutable state
    original_stop: float = 0.0
    be_stop_moved: bool = False
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None

    def __post_init__(self):
        self.original_stop = self.stop_loss

    @property
    def breakeven_price(self) -> float:
        """Breakeven price including round-trip commission."""
        return self.entry_price * (1 + self.commission_rate * 2)

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    @property
    def gross_pnl(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def commission(self) -> float:
        if self.exit_price is None:
            return 0.0
        return (self.entry_price + self.exit_price) * self.shares * self.commission_rate

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.commission

    @property
    def r_multiple(self) -> float:
        total_risk = self.risk_per_share * self.shares
        if total_risk <= 0:
            return 0.0
        return self.net_pnl / total_risk

    @property
    def result(self) -> str:
        if self.exit_price is None:
            return "OPEN"
        if self.exit_reason == "take_profit":
            return "WIN"
        if self.net_pnl < -0.01:
            return "LOSS"
        return "BE"


def create_position(
    signal: TradeSignal,
    shares: int,
    commission_rate: float,
    entry_time: str,
) -> Position:
    """Create a new position from a trade signal."""
    pos = Position(
        symbol=signal.symbol,
        direction=signal.direction,
        entry_price=signal.entry_price,
        stop_loss=signal.stop_loss,
        take_profit=signal.take_profit,
        shares=shares,
        risk_per_share=signal.risk_per_share,
        commission_rate=commission_rate,
        entry_time=entry_time,
        signal=signal,
    )
    logger.info(
        f"POSITION OPENED: {pos.symbol} {pos.shares}shares @ ${pos.entry_price:.2f} "
        f"SL=${pos.stop_loss:.2f} TP=${pos.take_profit:.2f}"
    )
    return pos


def check_exit(position: Position, current_high: float, current_low: float, current_close: float) -> Optional[str]:
    """
    Check if position should be exited based on current bar.

    Args:
        position: Active position.
        current_high: Current bar high.
        current_low: Current bar low.
        current_close: Current bar close.

    Returns:
        Exit reason string, or None if no exit.
    """
    if not position.is_open:
        return None

    # Stop loss hit (Long: low <= stop)
    if current_low <= position.stop_loss:
        if position.be_stop_moved:
            return "be_stop"
        return "stop_loss"

    # Take profit hit (Long: high >= target)
    if current_high >= position.take_profit:
        return "take_profit"

    return None


def move_stop_to_breakeven(position: Position) -> None:
    """Move stop loss to breakeven price (including commission)."""
    if position.be_stop_moved:
        return

    be_price = position.breakeven_price
    if be_price > position.stop_loss:
        old_sl = position.stop_loss
        position.stop_loss = be_price
        position.be_stop_moved = True
        logger.info(
            f"BE MOVE: {position.symbol} SL ${old_sl:.2f} → ${be_price:.2f} (BE)"
        )


def close_position(position: Position, price: float, reason: str, time_str: str) -> None:
    """Close the position at given price."""
    position.exit_price = round(price, 2)
    position.exit_reason = reason
    position.exit_time = time_str
    logger.info(
        f"POSITION CLOSED: {position.symbol} @ ${price:.2f} "
        f"reason={reason} PnL=${position.net_pnl:+.2f} ({position.result})"
    )
