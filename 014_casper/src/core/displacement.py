"""Displacement candle detection (ICT).

A 'displacement' is a strong directional candle that institutional flow
leaves behind. ICT teaching: a valid FVG must be CREATED by a
displacement candle — otherwise it is just a gap, low probability.

Algorithmic definition (Casper SMC 005, verified by phase-1 precheck):
  1. wick_ratio < max_wick           (body dominates the candle)
  2. body >= atr_mult * ATR(14)      (skipped if ATR unavailable)
  3. body >= prev_mult * mean(prev N candle bodies)

Returning False for any of these → not a displacement candle.

The module is dependency-free apart from pandas and is callable from
either live bot scan or backtest engine.
"""

from typing import Optional

import pandas as pd


def atr14(bars: pd.DataFrame) -> Optional[float]:
    """Simple ATR(14) from OHLC bars. Returns None when < 15 bars."""
    if bars is None or len(bars) < 15:
        return None
    h = bars["High"]
    l = bars["Low"]
    pc = bars["Close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    val = tr.rolling(14).mean().iloc[-1]
    if pd.isna(val) or val <= 0:
        return None
    return float(val)


def is_displacement(
    bar: pd.Series,
    prev_bars: Optional[pd.DataFrame] = None,
    atr_value: Optional[float] = None,
    atr_mult: float = 1.0,
    prev_mult: float = 1.5,
    max_wick: float = 0.50,
    direction: str = "bull",
) -> bool:
    """Decide whether a single candle is an ICT displacement candle.

    Args:
        bar: Series with Open/High/Low/Close (one 5-min bar).
        prev_bars: at least 3 bars immediately preceding `bar`. None disables that check.
        atr_value: pre-computed ATR(14). None disables the ATR check.
        atr_mult: minimum body-to-ATR multiple (default 1.0 — Casper SMC 005).
        prev_mult: minimum body relative to prev-bars body mean (default 1.5).
        max_wick: maximum allowed wick ratio (default 0.50).
        direction: 'bull' requires close>open, 'bear' requires close<open,
                   'either' allows both.

    Returns:
        True if all enabled checks pass.
    """
    o = float(bar["Open"])
    c = float(bar["Close"])
    h = float(bar["High"])
    l = float(bar["Low"])

    body = abs(c - o)
    total = h - l
    if total <= 0:
        return False
    wick_ratio = (total - body) / total

    if direction == "bull" and not (c > o):
        return False
    if direction == "bear" and not (c < o):
        return False

    if wick_ratio >= max_wick:
        return False

    # ATR check (best-effort)
    if atr_value is not None and atr_value > 0:
        if body < atr_value * atr_mult:
            return False

    # Relative to prev N bars (always available if prev_bars provided)
    if prev_bars is not None and len(prev_bars) >= 3:
        prev_body_mean = (prev_bars["Close"] - prev_bars["Open"]).abs().mean()
        if prev_body_mean > 0 and body < prev_body_mean * prev_mult:
            return False

    return True
