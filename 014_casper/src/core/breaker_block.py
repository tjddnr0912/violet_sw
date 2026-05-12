"""Order Block (OB) → Breaker Block conversion (ICT Phase 4).

Definitions (ICT primer):

- **Order Block (OB)**: the LAST OPPOSITE candle before a strong impulse.
  For a bullish impulse, the OB is the last bearish candle. Its body is
  the "demand zone" where institutional buying is suspected.

- **Breaker Block**: an OB whose zone has been broken by price (one swing
  failed in its direction). When price comes back to the broken zone, it
  becomes a reversal level — supply turns into demand (or vice versa).

- **Unicorn pattern (ICT)**: a Breaker Block + FVG overlap. Strongest
  reversal setup ICT teaches.

This module is stateless: feed a 5-min bar series and a known swing
direction, get back zones (top/bottom). The signal layer combines
these with FVG to detect Unicorn entries.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class OrderBlock:
    timestamp: pd.Timestamp
    top: float
    bottom: float
    direction: str  # 'bullish_OB' (last bearish before up impulse) or 'bearish_OB'


@dataclass(frozen=True)
class BreakerBlock:
    timestamp: pd.Timestamp
    top: float
    bottom: float
    direction: str  # role after break: 'support' (former bearish OB broken upward)
                    # or 'resistance' (former bullish OB broken downward)
    parent_ob_timestamp: pd.Timestamp


def find_order_block(
    bars: pd.DataFrame,
    impulse_end_index: int,
    direction: str = "bull",
    max_lookback: int = 10,
) -> Optional[OrderBlock]:
    """Find the last OPPOSITE candle before an impulse.

    Args:
        bars: 5-min OHLC dataframe.
        impulse_end_index: index of the displacement / impulse bar.
        direction: 'bull' (look for last bearish before up impulse)
                   or 'bear' (look for last bullish before down impulse).
        max_lookback: how many bars before impulse_end_index to scan.

    Returns:
        OrderBlock or None.
    """
    if impulse_end_index < 1 or impulse_end_index >= len(bars):
        return None
    start = max(0, impulse_end_index - max_lookback)
    for i in range(impulse_end_index - 1, start - 1, -1):
        bar = bars.iloc[i]
        is_bearish = bar["Close"] < bar["Open"]
        if direction == "bull" and is_bearish:
            return OrderBlock(
                timestamp=bars.index[i],
                top=float(bar["Open"]),
                bottom=float(bar["Close"]),
                direction="bullish_OB",
            )
        if direction == "bear" and not is_bearish:
            return OrderBlock(
                timestamp=bars.index[i],
                top=float(bar["Close"]),
                bottom=float(bar["Open"]),
                direction="bearish_OB",
            )
    return None


def is_broken(ob: OrderBlock, bars_after: pd.DataFrame) -> bool:
    """True if price has fully traded through the OB after the impulse.

    For a bullish_OB (formed before an up move): broken if price closes BELOW
    the OB bottom in any of the following bars (i.e. failed support).
    For bearish_OB: broken if price closes ABOVE the OB top.
    """
    if bars_after is None or bars_after.empty:
        return False
    if ob.direction == "bullish_OB":
        return bool((bars_after["Close"] < ob.bottom).any())
    return bool((bars_after["Close"] > ob.top).any())


def to_breaker_block(ob: OrderBlock, bars_after: pd.DataFrame) -> Optional[BreakerBlock]:
    """Convert OB to Breaker after confirming break."""
    if not is_broken(ob, bars_after):
        return None
    role = "resistance" if ob.direction == "bullish_OB" else "support"
    return BreakerBlock(
        timestamp=bars_after.index[-1],
        top=ob.top,
        bottom=ob.bottom,
        direction=role,
        parent_ob_timestamp=ob.timestamp,
    )


def is_unicorn(breaker: BreakerBlock, fvg_top: float, fvg_bottom: float,
               tolerance_pct: float = 0.002) -> bool:
    """True if Breaker zone overlaps with an FVG zone (the "Unicorn pattern").

    Both inputs are zones (top, bottom); we test interval overlap.
    """
    b_low = min(breaker.top, breaker.bottom)
    b_high = max(breaker.top, breaker.bottom)
    f_low = min(fvg_top, fvg_bottom)
    f_high = max(fvg_top, fvg_bottom)
    mid = (b_low + b_high + f_low + f_high) / 4.0
    tol = mid * tolerance_pct
    return not (b_high + tol < f_low or f_high + tol < b_low)
