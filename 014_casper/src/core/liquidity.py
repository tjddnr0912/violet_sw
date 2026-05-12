"""ICT Liquidity Sweep + Change of Character (CHoCH) detection.

Per Casper SMC ICT Mastery 002 & 005:

* SWEEP (Liquidity Raid) — a bar's wick breaches a known liquidity
  level (PDH/PDL, swing high/low, EQH/EQL) but the close prints back
  inside. Identifies false breakouts that institutional flow uses to
  collect stops.

* CHoCH (Change of Character) — the FIRST close that breaks the most
  recent swing low (in a prior uptrend) or swing high (downtrend).
  Marks structural reversal. Distinct from BOS (same-direction
  continuation).

Both helpers are stateless: they take pre-computed swing points (from
src.core.swing) and a bar window, and return bool + diagnostic info.
"""

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from src.core.swing import SwingPoint, last_swing_before


@dataclass(frozen=True)
class SweepEvent:
    timestamp: pd.Timestamp
    level: float
    side: str          # "up" (swept above) or "down" (swept below)
    breach_pct: float  # how far past the level
    wick_ratio: float


def is_sweep_bar(
    bar: pd.Series,
    level: float,
    side: str = "up",
    min_breach_pct: float = 0.0005,
    min_wick_ratio: float = 0.60,
) -> bool:
    """Pin-bar wick breach + close back inside.

    Args:
        bar: Series with Open/High/Low/Close.
        level: the liquidity level being tested.
        side: "up" → bar.High should pierce above `level`, close back below.
              "down" → bar.Low pierces below, close back above.
        min_breach_pct: minimum pierce distance as fraction of `level`.
        min_wick_ratio: pin-bar requirement (wick / total range).

    Returns:
        True if all conditions met.
    """
    if level <= 0:
        return False
    h = float(bar["High"]); l = float(bar["Low"])
    o = float(bar["Open"]); c = float(bar["Close"])
    total = h - l
    if total <= 0:
        return False

    if side == "up":
        breach = (h - level) / level
        if breach < min_breach_pct:
            return False
        if c >= level:  # close did NOT come back inside
            return False
        wick = h - max(o, c)
    else:
        breach = (level - l) / level
        if breach < min_breach_pct:
            return False
        if c <= level:
            return False
        wick = min(o, c) - l

    wick_ratio = wick / total if total > 0 else 0
    return wick_ratio >= min_wick_ratio


def detect_recent_sweep(
    bars: pd.DataFrame,
    levels: List[float],
    side: str = "up",
    lookback: int = 6,
    min_breach_pct: float = 0.0005,
    min_wick_ratio: float = 0.60,
) -> Optional[SweepEvent]:
    """Scan the last `lookback` bars for a sweep of any of the given levels.

    Returns the most recent SweepEvent found, or None.
    """
    if not levels or len(bars) == 0:
        return None
    window = bars.tail(lookback)
    found: Optional[SweepEvent] = None
    for ts, row in window.iterrows():
        for lvl in levels:
            if is_sweep_bar(row, lvl, side=side,
                            min_breach_pct=min_breach_pct,
                            min_wick_ratio=min_wick_ratio):
                h = float(row["High"]); l = float(row["Low"])
                total = h - l
                if side == "up":
                    breach = (h - lvl) / lvl
                    wick = h - max(float(row["Open"]), float(row["Close"]))
                else:
                    breach = (lvl - l) / lvl
                    wick = min(float(row["Open"]), float(row["Close"])) - l
                wr = wick / total if total > 0 else 0
                found = SweepEvent(ts, lvl, side, breach, wr)
    return found


def detect_choch(
    bars: pd.DataFrame,
    swing_highs: List[SwingPoint],
    swing_lows: List[SwingPoint],
    direction: str = "bull",
    after_ts: Optional[pd.Timestamp] = None,
) -> Optional[pd.Timestamp]:
    """Return timestamp of the first CHoCH after `after_ts`, or None.

    direction='bull' (we want to enter bullish) → looks for a close that
    breaks ABOVE the most recent swing high before each bar (reversal
    from downtrend to uptrend).
    direction='bear' is the mirror.
    """
    if bars.empty:
        return None
    iter_bars = bars if after_ts is None else bars[bars.index > after_ts]
    for ts, row in iter_bars.iterrows():
        if direction == "bull":
            ref = last_swing_before(swing_highs, ts)
            if ref is not None and float(row["Close"]) > ref.price:
                return ts
        else:
            ref = last_swing_before(swing_lows, ts)
            if ref is not None and float(row["Close"]) < ref.price:
                return ts
    return None


def sweep_then_choch(
    bars: pd.DataFrame,
    levels_up: List[float],
    levels_down: List[float],
    swing_highs: List[SwingPoint],
    swing_lows: List[SwingPoint],
    direction: str = "bull",
    sweep_lookback: int = 6,
    choch_lookback: int = 6,
    min_breach_pct: float = 0.0005,
    min_wick_ratio: float = 0.60,
) -> bool:
    """Composite ICT trigger: sweep + CHoCH within the last few bars.

    For a bullish setup:
      1. recent SSL sweep (price wicked below a sell-side level then closed back up)
      2. then a CHoCH (close > prior swing high) in the bars that followed

    The two events must be ordered (sweep first, then CHoCH).
    """
    if direction == "bull":
        sweep = detect_recent_sweep(bars, levels_down, side="down",
                                    lookback=sweep_lookback,
                                    min_breach_pct=min_breach_pct,
                                    min_wick_ratio=min_wick_ratio)
        if sweep is None:
            return False
        after = bars[bars.index > sweep.timestamp].head(choch_lookback)
        return detect_choch(after, swing_highs, swing_lows,
                            direction="bull",
                            after_ts=sweep.timestamp) is not None
    else:
        sweep = detect_recent_sweep(bars, levels_up, side="up",
                                    lookback=sweep_lookback,
                                    min_breach_pct=min_breach_pct,
                                    min_wick_ratio=min_wick_ratio)
        if sweep is None:
            return False
        after = bars[bars.index > sweep.timestamp].head(choch_lookback)
        return detect_choch(after, swing_highs, swing_lows,
                            direction="bear",
                            after_ts=sweep.timestamp) is not None
