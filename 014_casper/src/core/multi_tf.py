"""Multi-timeframe SL refinement (ICT Phase 4).

When enabled, the 5-min ORB+FVG strict signal is *located*, then a
1-min look-down zooms in to find a tighter stop-loss anchored to the
recent 1-min swing low (long) or high (short).

Why: 5-min `prev_candle.Low` can put SL 0.3~0.5% away from entry,
making R:R 1:3 difficult to reach within 90 min. The 1-min swing
inside the same FVG-creator bar is typically 30~60% closer, improving
TP-reach rate.

The module is entirely optional (config gate `entry.use_multi_tf_sl`).
Failure to obtain 1-min data falls back to the original 5-min SL.
"""

from typing import Optional, Tuple

import pandas as pd


def refine_stop_with_1min(
    bars_1m: Optional[pd.DataFrame],
    signal_time: pd.Timestamp,
    direction: str,
    fallback_stop: float,
    lookback_min: int = 15,
) -> float:
    """Find a tighter SL using 1-min bars in the window leading up to entry.

    Long: SL = min(Low) over the last `lookback_min` 1-min bars before signal_time.
    Short: SL = max(High) over the same window.

    Returns fallback_stop if 1-min data is unavailable or empty.
    """
    if bars_1m is None or len(bars_1m) == 0:
        return fallback_stop
    if not isinstance(signal_time, pd.Timestamp):
        return fallback_stop

    cutoff = signal_time - pd.Timedelta(minutes=lookback_min)
    win = bars_1m[(bars_1m.index >= cutoff) & (bars_1m.index <= signal_time)]
    if win.empty:
        return fallback_stop

    if direction == "bear":
        refined = float(win["High"].max())
        # Must be ABOVE entry, otherwise the refinement gives no protection
        # Caller verifies geometry against entry price; here we just return.
        return refined
    refined = float(win["Low"].min())
    return refined


def best_stop(
    bars_1m: Optional[pd.DataFrame],
    signal_time: pd.Timestamp,
    direction: str,
    fallback_stop: float,
    entry_price: float,
    min_risk: float = 0.10,
) -> Tuple[float, str]:
    """Pick whichever stop gives positive but minimum-acceptable risk.

    Returns (stop, source) where source is "1m" or "5m_fallback".
    If the 1-min refined stop violates the min_risk floor, fall back to 5-min.
    """
    refined = refine_stop_with_1min(bars_1m, signal_time, direction, fallback_stop)
    if direction == "bear":
        risk = refined - entry_price
    else:
        risk = entry_price - refined
    if risk >= min_risk and refined != fallback_stop:
        return refined, "1m"
    return fallback_stop, "5m_fallback"
