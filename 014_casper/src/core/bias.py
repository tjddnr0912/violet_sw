"""Daily bias decision (ICT Daily Bias, Casper SMC 015).

Goes beyond the current 20-MA-only filter and scores multiple inputs:
  - PDH/PDL  (prior-day high/low)
  - PWH/PWL  (prior-week high/low — last 5 trading days)
  - MA20 / MA50 of daily close

A net positive score → bull bias, negative → bear, zero → neutral.

When `neutral_skip=True`, callers should treat a `neutral` result as
"no trade today" (avoids choppy / undecided regimes).
"""

from dataclasses import dataclass
from datetime import date as _date
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class DailyBias:
    direction: str        # "bull" | "bear" | "neutral"
    score: int
    components: dict      # diagnostic: which checks fired
    pdh: float
    pdl: float
    pwh: float
    pwl: float


def compute_daily_bias(
    daily_df: pd.DataFrame,
    as_of: Optional[_date] = None,
    use_ma20: bool = True,
    use_ma50: bool = True,
    use_pdh_pdl: bool = True,
    use_pwh_pwl: bool = True,
    judas_signal: Optional[str] = None,
) -> Optional[DailyBias]:
    """Compute the bias based on daily OHLC.

    Args:
        daily_df: DataFrame indexed by date with at least Close/High/Low.
                  The most recent row should NOT include the as_of date
                  (we look only at history strictly before today).
        as_of: optional cutoff date; rows with index.date >= as_of are excluded.
        use_*: enable/disable each component.

    Returns:
        DailyBias, or None if insufficient history (< 21 rows for MA20).
    """
    df = daily_df.copy()
    if as_of is not None:
        df = df[df.index.date < as_of]
    if len(df) < 21:
        return None

    last = df.iloc[-1]
    pdh = float(last["High"])
    pdl = float(last["Low"])
    close = float(last["Close"])

    # Prior-week high/low across the last 5 rows EXCLUDING today (= last row only? we already cut today)
    last5 = df.tail(5)
    pwh = float(last5["High"].max())
    pwl = float(last5["Low"].min())

    ma20 = float(df["Close"].rolling(20).mean().iloc[-1])
    ma50 = (
        float(df["Close"].rolling(50).mean().iloc[-1])
        if len(df) >= 50 else None
    )

    score = 0
    fired: dict[str, int] = {}

    if use_ma20:
        delta = 1 if close > ma20 else (-1 if close < ma20 else 0)
        score += delta
        fired["ma20"] = delta
    if use_ma50 and ma50 is not None:
        delta = 1 if close > ma50 else (-1 if close < ma50 else 0)
        score += delta
        fired["ma50"] = delta
    if use_pdh_pdl:
        # closing strength: above PDH = bullish continuation, below PDL = bearish
        if close > pdh:
            score += 1; fired["pdh"] = 1
        elif close < pdl:
            score -= 1; fired["pdl"] = -1
        else:
            fired["pdh_pdl"] = 0
    if use_pwh_pwl:
        if close > pwh:
            score += 1; fired["pwh"] = 1
        elif close < pwl:
            score -= 1; fired["pwl"] = -1
        else:
            fired["pwh_pwl"] = 0

    # ICT Phase 4: Power of 3 — Judas Swing reinforces directional bias
    if judas_signal == "bullish_judas":
        score += 1
        fired["judas"] = 1
    elif judas_signal == "bearish_judas":
        score -= 1
        fired["judas"] = -1

    if score > 0:
        direction = "bull"
    elif score < 0:
        direction = "bear"
    else:
        direction = "neutral"

    return DailyBias(
        direction=direction,
        score=score,
        components=fired,
        pdh=pdh, pdl=pdl, pwh=pwh, pwl=pwl,
    )
