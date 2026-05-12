"""ICT swing-point fractal detection.

A 'strong' swing high requires the candle's High to be the maximum among
itself and N candles on each side (default N=2 → 5-bar fractal, Casper
SMC 005). Symmetric definition for swing lows.

Also exposes Equal Highs/Lows (EQH/EQL) — pairs of swing points whose
prices differ by ≤ eq_pct (default 0.05%).
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional

import pandas as pd


@dataclass(frozen=True)
class SwingPoint:
    timestamp: pd.Timestamp
    price: float
    kind: str  # "high" or "low"


def find_swing_highs(bars: pd.DataFrame, left: int = 2, right: int = 2) -> List[SwingPoint]:
    """Return list of swing-high SwingPoint, in chronological order.

    A swing high at index i requires bars.High[i] > all High in
    [i-left, i-1] and ≥ all High in [i+1, i+right]. (Strict on left,
    non-strict on right — handles plateaus deterministically.)
    """
    if len(bars) < left + right + 1:
        return []
    out: List[SwingPoint] = []
    H = bars["High"].values
    idx = bars.index
    for i in range(left, len(bars) - right):
        center = H[i]
        if all(center > H[j] for j in range(i - left, i)) and \
           all(center >= H[j] for j in range(i + 1, i + right + 1)):
            out.append(SwingPoint(idx[i], float(center), "high"))
    return out


def find_swing_lows(bars: pd.DataFrame, left: int = 2, right: int = 2) -> List[SwingPoint]:
    if len(bars) < left + right + 1:
        return []
    out: List[SwingPoint] = []
    L = bars["Low"].values
    idx = bars.index
    for i in range(left, len(bars) - right):
        center = L[i]
        if all(center < L[j] for j in range(i - left, i)) and \
           all(center <= L[j] for j in range(i + 1, i + right + 1)):
            out.append(SwingPoint(idx[i], float(center), "low"))
    return out


def equal_levels(points: List[SwingPoint], eq_pct: float = 0.0005) -> List[Tuple[SwingPoint, SwingPoint]]:
    """Find pairs of swing points where prices differ by ≤ eq_pct.

    Returns list of (earlier, later) pairs sorted by the later timestamp.
    """
    pairs: List[Tuple[SwingPoint, SwingPoint]] = []
    n = len(points)
    for i in range(n):
        a = points[i]
        for j in range(i + 1, n):
            b = points[j]
            if a.price <= 0:
                continue
            if abs(a.price - b.price) / a.price <= eq_pct:
                pairs.append((a, b))
    return pairs


def last_swing_before(points: List[SwingPoint], ts: pd.Timestamp) -> Optional[SwingPoint]:
    """Return the most recent swing point strictly before ts, or None."""
    eligible = [p for p in points if p.timestamp < ts]
    return eligible[-1] if eligible else None
