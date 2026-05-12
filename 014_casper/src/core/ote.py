"""Optimal Trade Entry (OTE) — Fibonacci-based entry refinement (ICT Phase 4).

ICT recommends entering at the 0.618 / 0.705 / 0.79 retracement of the
*impulse swing* that created the FVG. Compared to the FVG-midpoint
entry the bot currently uses, OTE typically gives ~0.1~0.3% better
fill on TQQQ — useful for tight R:R 1:3 setups.

Geometry (long setup):
    impulse: swing_low_before_breakout  →  swing_high_after_breakout
    OTE entry zone = swing_low + (high - low) × (1 - fib)
    e.g. fib=0.705 → entry = high - 0.705 × (high - low)

For short (bear) setups the geometry is mirrored.

The module is optional (`entry.use_ote=true`); when disabled, the
original FVG mid is used.
"""

from typing import Optional


def ote_entry_price(
    impulse_low: float,
    impulse_high: float,
    direction: str = "bull",
    fib_level: float = 0.705,
) -> Optional[float]:
    """Return the OTE entry price for the impulse swing.

    Args:
        impulse_low: lowest price of the impulse swing
        impulse_high: highest price of the impulse swing
        direction: 'bull' (long) or 'bear' (short)
        fib_level: retracement (0.5 ~ 0.79 typical)

    Returns:
        Suggested entry price, or None if the impulse is degenerate.
    """
    if impulse_high <= impulse_low or fib_level <= 0 or fib_level >= 1:
        return None
    span = impulse_high - impulse_low
    if direction == "bear":
        return impulse_low + fib_level * span
    return impulse_high - fib_level * span


def fvg_overlaps_ote(
    fvg_top: float, fvg_bot: float,
    ote_price: float,
    tolerance_pct: float = 0.002,
) -> bool:
    """True if the OTE price lies inside the FVG zone (or within tolerance).

    Used to decide whether to *substitute* the FVG-mid entry with OTE:
    only when the two zones overlap — otherwise stick with FVG-mid.
    """
    low = min(fvg_top, fvg_bot)
    high = max(fvg_top, fvg_bot)
    tol = (high + low) / 2 * tolerance_pct
    return (low - tol) <= ote_price <= (high + tol)
