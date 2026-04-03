"""Opening Range Breakout (ORB) calculation module.

Computes the 15-minute Opening Range (9:30-9:45 ET) from 5-minute bars.
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

logger = logging.getLogger("casper")


@dataclass
class OpeningRange:
    """Opening Range data."""
    high: float
    low: float
    range_size: float
    date: str

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2


def calculate_orb(bars_5m: pd.DataFrame) -> Optional[OpeningRange]:
    """
    Calculate Opening Range from 5-minute bars.

    Args:
        bars_5m: DataFrame with OHLCV data, index in ET timezone.
                 Must contain columns: High, Low.

    Returns:
        OpeningRange if enough data, None otherwise.
    """
    if bars_5m.empty:
        logger.warning("ORB: No data provided")
        return None

    # Filter 9:30-9:44 ET (3 bars: 9:30, 9:35, 9:40)
    orb_bars = bars_5m.between_time("09:30", "09:44")

    if len(orb_bars) < 3:
        logger.warning(f"ORB: Only {len(orb_bars)} bars in range (need 3)")
        return None

    orb_high = orb_bars["High"].max()
    orb_low = orb_bars["Low"].min()
    orb_range = orb_high - orb_low

    if orb_range <= 0:
        logger.warning("ORB: Range is zero or negative")
        return None

    orb_date = orb_bars.index[0].strftime("%Y-%m-%d")
    orb = OpeningRange(high=orb_high, low=orb_low, range_size=orb_range, date=orb_date)
    logger.info(f"ORB: H={orb.high:.2f} L={orb.low:.2f} Range={orb.range_size:.2f}")
    return orb


def is_orb_too_wide(orb: OpeningRange, avg_daily_range: float, max_ratio: float = 1.5) -> bool:
    """
    Check if ORB range exceeds threshold relative to average daily range.

    Args:
        orb: Opening Range data.
        avg_daily_range: Average daily High-Low range (20-day).
        max_ratio: Maximum allowed ORB/ADR ratio.

    Returns:
        True if ORB is too wide.
    """
    if avg_daily_range <= 0:
        return False
    ratio = orb.range_size / avg_daily_range
    if ratio > max_ratio:
        logger.info(f"ORB: Too wide ({ratio:.2f}x ADR, max {max_ratio}x)")
        return True
    return False
