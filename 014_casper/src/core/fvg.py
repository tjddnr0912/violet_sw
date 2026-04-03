"""Fair Value Gap (FVG) detection module.

Identifies Bullish FVG patterns from 3 consecutive candles.
Only bullish FVGs are used (Long-only strategy).
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger("casper")


@dataclass
class FairValueGap:
    """Fair Value Gap data."""
    top: float      # Upper edge (candle 3 low)
    bottom: float   # Lower edge (candle 1 high)
    size: float     # Gap size
    timestamp: str  # Formation time

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2


def detect_bullish_fvg(candles: pd.DataFrame) -> Optional[FairValueGap]:
    """
    Detect Bullish FVG from exactly 3 consecutive candles.

    Bullish FVG condition: candle[0].High < candle[2].Low
    This means there's a gap between candle 1's high and candle 3's low.

    Args:
        candles: DataFrame with exactly 3 rows (consecutive 5-min bars).
                 Must contain: High, Low columns.

    Returns:
        FairValueGap if detected, None otherwise.
    """
    if len(candles) < 3:
        return None

    c1 = candles.iloc[0]
    c3 = candles.iloc[2]

    if c1["High"] < c3["Low"]:
        fvg = FairValueGap(
            top=c3["Low"],
            bottom=c1["High"],
            size=c3["Low"] - c1["High"],
            timestamp=candles.index[1].strftime("%Y-%m-%d %H:%M"),
        )
        logger.debug(f"FVG: Bullish detected at {fvg.timestamp} "
                     f"[{fvg.bottom:.2f} ~ {fvg.top:.2f}] size={fvg.size:.2f}")
        return fvg

    return None


def check_breakout_with_fvg(
    bars: pd.DataFrame, orb_high: float, bar_index: int
) -> Optional[FairValueGap]:
    """
    Check if bar at bar_index shows ORB breakout AND has a bullish FVG.

    Breakout condition: Close > ORB high AND Close > Open (bullish candle).
    FVG checked on 3-candle window: [bar_index-1, bar_index, bar_index+1].

    Args:
        bars: DataFrame of 5-min bars (post-ORB window).
        orb_high: ORB high price.
        bar_index: Index of the candidate breakout bar.

    Returns:
        FairValueGap if breakout + FVG found, None otherwise.
    """
    if bar_index < 1 or bar_index + 1 >= len(bars):
        return None

    candle = bars.iloc[bar_index]

    # Check bullish breakout: close above ORB high + bullish candle
    if not (candle["Close"] > orb_high and candle["Close"] > candle["Open"]):
        return None

    # Check FVG on 3-candle window
    three = bars.iloc[bar_index - 1 : bar_index + 2]
    return detect_bullish_fvg(three)
