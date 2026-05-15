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

    # ── Partial TP support ──────────────────────────────────────────
    # Filled by bot._enter_position when entry.partial_tp_enabled=True.
    # `tp1_price` is the first take-profit level (e.g. entry + risk*1.5).
    # When the bot detects the bar reaching tp1_price, it sells
    # `partial_shares_initial * tp1_close_pct` shares (computed once at
    # entry), records the partial fill on this position, moves SL to
    # `orb_high` (or BE if higher), and continues monitoring the rest
    # until take_profit / stop_loss / force_close.
    tp1_price: Optional[float] = None
    tp1_close_pct: float = 0.50
    tp1_filled: bool = False
    partial_shares_initial: int = 0  # snapshot of shares at entry
    partial_shares_closed: int = 0   # shares closed at TP1
    partial_exit_price: Optional[float] = None
    partial_exit_time: Optional[str] = None
    orb_high: Optional[float] = None  # used to move SL after TP1

    def __post_init__(self):
        self.original_stop = self.stop_loss
        if self.partial_shares_initial == 0:
            self.partial_shares_initial = self.shares

    @property
    def breakeven_price(self) -> float:
        """Breakeven price including round-trip commission.

        For a long position: exit_price must cover both entry and exit commissions.
        entry_cost = entry_price * shares * (1 + rate)
        exit_revenue = exit_price * shares * (1 - rate)
        BE when exit_revenue = entry_cost → exit_price = entry_price * (1+rate)/(1-rate)
        """
        r = self.commission_rate
        return self.entry_price * (1 + r) / (1 - r)

    @property
    def is_open(self) -> bool:
        return self.exit_price is None

    @property
    def gross_pnl(self) -> float:
        """Total gross PnL = (partial leg, if any) + (final leg).

        - partial leg: `partial_shares_closed × (partial_exit_price - entry_price)`
        - final leg : `shares × (exit_price - entry_price)` (when closed)
        `shares` already represents the *remaining* size after TP1 fill,
        so summing both is correct without double counting.
        """
        partial_gross = 0.0
        if self.partial_exit_price is not None and self.partial_shares_closed > 0:
            partial_gross = (
                (self.partial_exit_price - self.entry_price)
                * self.partial_shares_closed
            )
        if self.exit_price is None:
            return partial_gross
        final_gross = (self.exit_price - self.entry_price) * self.shares
        return partial_gross + final_gross

    @property
    def commission(self) -> float:
        """Round-trip commission across BOTH legs (entry split between legs).

        Approximation: charge entry commission on each share once (buy side),
        and sell commission on the appropriate exit price for each leg.
        """
        r = self.commission_rate
        total_initial = self.partial_shares_initial or self.shares
        if total_initial <= 0:
            return 0.0
        # Buy-side commission charged on the entire initial position once.
        buy_comm = self.entry_price * total_initial * r
        # Sell-side: partial leg + final leg
        partial_sell_comm = 0.0
        if self.partial_exit_price is not None and self.partial_shares_closed > 0:
            partial_sell_comm = (
                self.partial_exit_price * self.partial_shares_closed * r
            )
        if self.exit_price is None:
            return buy_comm + partial_sell_comm
        final_sell_comm = self.exit_price * self.shares * r
        return buy_comm + partial_sell_comm + final_sell_comm

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.commission

    @property
    def r_multiple(self) -> float:
        # Risk denominator = original (full) shares × risk_per_share, not the
        # post-partial remaining size. This keeps R-multiple comparable to
        # legacy single-TP trades regardless of partial fill.
        total_initial = self.partial_shares_initial or self.shares
        total_risk = self.risk_per_share * total_initial
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
    tp1_close_pct: float = 0.50,
    orb_high: Optional[float] = None,
) -> Position:
    """Create a new position from a trade signal.

    `signal.tp1_price` (when non-None) and `orb_high` enable the partial
    TP path. Leaving either at default disables partial TP for this trade.
    """
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
        tp1_price=getattr(signal, "tp1_price", None),
        tp1_close_pct=tp1_close_pct,
        partial_shares_initial=shares,
        orb_high=orb_high,
    )
    tp1_info = ""
    if pos.tp1_price is not None:
        tp1_info = f" TP1=${pos.tp1_price:.2f} ({int(pos.tp1_close_pct*100)}%)"
    logger.info(
        f"POSITION OPENED: {pos.symbol} {pos.shares}shares @ ${pos.entry_price:.2f} "
        f"SL=${pos.stop_loss:.2f}{tp1_info} TP=${pos.take_profit:.2f}"
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


def check_tp1_fill(position: Position, current_high: float) -> bool:
    """True when partial-TP1 should fire (long: bar.High ≥ tp1_price)."""
    if position.tp1_price is None or position.tp1_filled:
        return False
    if not position.is_open:
        return False
    return current_high >= position.tp1_price


def apply_partial_fill(position: Position, fill_price: float, fill_time: str) -> int:
    """Mark TP1 as filled, record partial sale, return shares sold.

    Mutates the position: records partial_exit_price/time/shares, reduces
    `shares` to the remainder, and (when orb_high known) moves SL to
    max(current_sl, orb_high). Does NOT execute any broker order — caller
    must place the sell order first and pass the actual fill price here.
    """
    if position.tp1_filled or position.tp1_price is None:
        return 0
    sold = int(round(position.partial_shares_initial * position.tp1_close_pct))
    if sold <= 0:
        return 0
    sold = min(sold, position.shares)
    position.partial_shares_closed = sold
    position.partial_exit_price = round(fill_price, 2)
    position.partial_exit_time = fill_time
    position.shares -= sold
    position.tp1_filled = True

    # Move SL to ORB.high (free trade) if higher than current SL.
    if position.orb_high is not None and position.orb_high > position.stop_loss:
        old_sl = position.stop_loss
        position.stop_loss = round(position.orb_high, 2)
        logger.info(
            f"TP1 FILL: SL ${old_sl:.2f} → ${position.stop_loss:.2f} (ORB.high)"
        )

    logger.info(
        f"PARTIAL CLOSE: {position.symbol} {sold}sh @ ${fill_price:.2f} "
        f"(TP1, remaining {position.shares}sh)"
    )
    return sold


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
