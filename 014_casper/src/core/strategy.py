"""Strategy engine: ORB + FVG + Pullback entry signal detection.

Combines ORB, FVG detection, and pullback confirmation into trade signals.
All entries are Long only (TQQQ or SQQQ).
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.core.orb import OpeningRange
from src.core.fvg import FairValueGap, check_breakout_with_fvg

logger = logging.getLogger("casper")


@dataclass
class TradeSignal:
    """Complete trade signal with entry, stop, and target."""
    symbol: str
    direction: str        # Always "long"
    entry_price: float    # FVG midpoint
    stop_loss: float      # Prior candle low
    take_profit: float    # Entry + risk * RR
    risk_per_share: float # Entry - Stop
    rr_ratio: float
    fvg: FairValueGap
    orb: OpeningRange
    signal_time: str


def scan_for_signal(
    bars_5m: pd.DataFrame,
    orb: OpeningRange,
    symbol: str,
    rr_ratio: float = 2.0,
    min_risk: float = 0.10,
    strict: bool = False,
) -> Optional[TradeSignal]:
    """
    Scan post-ORB 5-minute bars for a trade signal.

    Logic:
    1. For each bar, check if it breaks above ORB high (bullish breakout)
    2. Check if a Bullish FVG forms simultaneously
    3. Calculate entry (FVG mid), stop (prior candle low), target (R:R)
    4. Validate minimum risk

    Args:
        bars_5m: 5-min bars in the scan window (09:45-10:55 ET).
        orb: Opening Range for the day.
        symbol: Trading symbol (TQQQ or SQQQ).
        rr_ratio: Risk-reward ratio (default 2.0).
        min_risk: Minimum risk in dollars per share.

    Returns:
        TradeSignal if found, None otherwise.
    """
    if len(bars_5m) < 4:
        logger.debug("Strategy: Not enough bars for scanning")
        return None

    for i in range(1, len(bars_5m) - 1):
        fvg = check_breakout_with_fvg(bars_5m, orb.high, i, strict=strict)
        if fvg is None:
            continue

        # Entry at FVG midpoint (pullback target)
        entry_price = fvg.mid

        # Stop loss: prior candle (c1) low
        prev_candle = bars_5m.iloc[i - 1]
        stop_loss = prev_candle["Low"]

        # Risk calculation
        risk = entry_price - stop_loss
        if risk <= 0.01:
            logger.debug(f"Strategy: Negative/zero risk at bar {i}, skip")
            continue

        if risk < min_risk:
            logger.debug(f"Strategy: Risk ${risk:.2f} < min ${min_risk:.2f}, skip")
            continue

        take_profit = entry_price + (risk * rr_ratio)
        signal_time = bars_5m.index[i].strftime("%Y-%m-%d %H:%M")

        signal = TradeSignal(
            symbol=symbol,
            direction="long",
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            risk_per_share=round(risk, 2),
            rr_ratio=rr_ratio,
            fvg=fvg,
            orb=orb,
            signal_time=signal_time,
        )
        logger.info(
            f"SIGNAL: {symbol} Long @ {entry_price:.2f} "
            f"SL={stop_loss:.2f} TP={take_profit:.2f} "
            f"Risk=${risk:.2f} R:R=1:{rr_ratio}"
        )
        return signal

    logger.debug("Strategy: No signal found in scan window")
    return None


def check_pullback(
    bar: pd.Series, fvg: FairValueGap
) -> bool:
    """
    Check if a bar's low touches/enters the FVG zone (pullback).

    For Long entry: price dips into FVG top boundary.

    Args:
        bar: Single 5-min bar (Series with High, Low, Open, Close).
        fvg: The FVG zone to check against.

    Returns:
        True if pullback occurred.
    """
    return bar["Low"] <= fvg.top
