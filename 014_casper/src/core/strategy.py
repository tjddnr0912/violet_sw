"""Strategy engine: ORB + FVG + Pullback entry signal detection.

Combines ORB, FVG detection, and pullback confirmation into trade signals.
All entries are Long only (TQQQ or SQQQ).

ICT Phase 1 additions (env-gated, default OFF):
  - Killzone filter: only emit signals whose pullback time falls in an
    allowed killzone (e.g. ["AM_MACRO"]).
  - Displacement filter: require the breakout candle that created the
    FVG to be an ICT displacement candle (body/ATR, wick ratio).
"""

import logging
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from src.core.orb import OpeningRange
from src.core.fvg import (
    FairValueGap, check_breakout_with_fvg, check_breakdown_with_fvg,
)
from src.core.sessions import in_allowed_killzones
from src.core.displacement import is_displacement, atr14
from src.core.swing import find_swing_highs, find_swing_lows
from src.core.liquidity import sweep_then_choch
from src.data.ict_log import record as _log_decision

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
    allowed_killzones: Optional[list] = None,
    require_displacement: bool = False,
    disp_atr_mult: float = 1.0,
    disp_max_wick: float = 0.50,
    disp_prev_mult: float = 1.5,
    history_bars: Optional[pd.DataFrame] = None,
    require_sweep_choch: bool = False,
    sweep_lookback: int = 6,
    choch_lookback: int = 6,
    sweep_min_breach_pct: float = 0.0005,
    sweep_min_wick_ratio: float = 0.60,
    direction: str = "bull",
    bars_1m: Optional[pd.DataFrame] = None,
    use_multi_tf_sl: bool = False,
    mtf_lookback_min: int = 15,
    use_ote: bool = False,
    ote_fib_level: float = 0.705,
    require_unicorn: bool = False,
) -> Optional[TradeSignal]:
    """
    Scan post-ORB 5-minute bars for a trade signal.

    Logic:
    1. For each bar, check if it breaks above ORB high (bullish breakout)
    2. Check if a Bullish FVG forms simultaneously
    3. Calculate entry (FVG mid), stop (prior candle low), target (R:R)
    4. Validate minimum risk
    5. (Optional) reject if FVG-creating candle is not a displacement candle
    6. (Optional) reject if breakout candle time is outside allowed killzones

    Args:
        bars_5m: 5-min bars in the scan window (09:45-10:55 ET).
        orb: Opening Range for the day.
        symbol: Trading symbol (TQQQ or SQQQ).
        rr_ratio: Risk-reward ratio (default 2.0).
        min_risk: Minimum risk in dollars per share.
        strict: enforce FVG-intersects-ORB-line rule.
        allowed_killzones: list of killzone names (e.g. ["AM_MACRO"]).
                           None/empty = no filter.
        require_displacement: require breakout candle = displacement candle.
        disp_atr_mult: body must be ≥ disp_atr_mult * ATR(14).
        disp_max_wick: wick ratio strict-less-than.
        disp_prev_mult: body must be ≥ prev_mult * mean(prev N bodies).
        history_bars: longer bar history for ATR(14). If None, falls back
                      to bars_5m alone (may have NaN ATR early in the session).

    Returns:
        TradeSignal if found, None otherwise.
    """
    if len(bars_5m) < 4:
        logger.debug("Strategy: Not enough bars for scanning")
        return None

    # Pre-compute ATR(14) once using the longest available bar series
    atr_source = history_bars if history_bars is not None else bars_5m
    atr_value = atr14(atr_source)

    # Pre-compute swing points for sweep + CHoCH (Phase 2). Use the
    # longer history if available — otherwise just the scan window.
    swing_source = history_bars if history_bars is not None else bars_5m
    if require_sweep_choch:
        swing_highs = find_swing_highs(swing_source, left=2, right=2)
        swing_lows  = find_swing_lows(swing_source, left=2, right=2)
        # liquidity levels: ORB high/low + last few swing extremes
        levels_up = [orb.high] + [p.price for p in swing_highs[-5:]]
        levels_down = [orb.low] + [p.price for p in swing_lows[-5:]]
    else:
        swing_highs = swing_lows = []
        levels_up = levels_down = []

    for i in range(1, len(bars_5m) - 1):
        # Direction-aware breakout/breakdown detection.
        if direction == "bear":
            fvg = check_breakdown_with_fvg(bars_5m, orb.low, i, strict=strict)
        else:
            fvg = check_breakout_with_fvg(bars_5m, orb.high, i, strict=strict)
        if fvg is None:
            continue

        # ── Killzone filter (applied to breakout candle time) ──
        if allowed_killzones:
            if not in_allowed_killzones(bars_5m.index[i], allowed_killzones):
                logger.debug(
                    f"Strategy: bar {i} ({bars_5m.index[i]}) outside allowed "
                    f"killzones {allowed_killzones}, skip"
                )
                _log_decision(
                    event="killzone_check", symbol=symbol,
                    bar_time=bars_5m.index[i], passed=False,
                    reason=f"outside {allowed_killzones}",
                    details={"direction": direction},
                )
                continue
            _log_decision(
                event="killzone_check", symbol=symbol,
                bar_time=bars_5m.index[i], passed=True,
                details={"allowed": list(allowed_killzones), "direction": direction},
            )

        # ── Displacement filter (applied to breakout candle = FVG creator) ──
        if require_displacement:
            breakout = bars_5m.iloc[i]
            prev_window = bars_5m.iloc[max(0, i - 5):i]
            disp_ok = is_displacement(
                breakout, prev_window,
                atr_value=atr_value,
                atr_mult=disp_atr_mult,
                prev_mult=disp_prev_mult,
                max_wick=disp_max_wick,
                direction=direction,
            )
            # Compute diagnostics regardless of pass/fail for the log
            body = abs(float(breakout["Close"]) - float(breakout["Open"]))
            total = float(breakout["High"]) - float(breakout["Low"])
            wick_ratio = (total - body) / total if total > 0 else None
            disp_details = {
                "body": round(body, 4),
                "atr14": round(atr_value, 4) if atr_value else None,
                "body_atr_ratio": round(body / atr_value, 3) if atr_value else None,
                "wick_ratio": round(wick_ratio, 3) if wick_ratio is not None else None,
                "direction": direction,
            }
            if not disp_ok:
                logger.debug(
                    f"Strategy: bar {i} fails displacement check "
                    f"(atr_mult={disp_atr_mult}, wick<{disp_max_wick}), skip"
                )
                _log_decision(
                    event="displacement_check", symbol=symbol,
                    bar_time=bars_5m.index[i], passed=False,
                    reason="threshold", details=disp_details,
                )
                continue
            _log_decision(
                event="displacement_check", symbol=symbol,
                bar_time=bars_5m.index[i], passed=True,
                details=disp_details,
            )

        # ── Liquidity Sweep + CHoCH gate (Phase 2) ──
        if require_sweep_choch:
            window_until_breakout = swing_source.loc[:bars_5m.index[i]]
            sweep_ok = sweep_then_choch(
                window_until_breakout,
                levels_up=levels_up, levels_down=levels_down,
                swing_highs=swing_highs, swing_lows=swing_lows,
                direction=direction,
                sweep_lookback=sweep_lookback,
                choch_lookback=choch_lookback,
                min_breach_pct=sweep_min_breach_pct,
                min_wick_ratio=sweep_min_wick_ratio,
            )
            if not sweep_ok:
                logger.debug(
                    f"Strategy: bar {i} no sweep+CHoCH precursor, skip"
                )
                _log_decision(
                    event="sweep_choch_check", symbol=symbol,
                    bar_time=bars_5m.index[i], passed=False,
                    reason="no sweep then CHoCH precursor",
                    details={"direction": direction,
                              "sweep_lookback": sweep_lookback,
                              "choch_lookback": choch_lookback},
                )
                continue
            _log_decision(
                event="sweep_choch_check", symbol=symbol,
                bar_time=bars_5m.index[i], passed=True,
                details={"direction": direction},
            )

        prev_candle = bars_5m.iloc[i - 1]
        breakout_candle = bars_5m.iloc[i]
        entry_price = fvg.mid

        # ── ICT Phase 4: Unicorn pattern (Breaker + FVG overlap) ──
        if require_unicorn:
            try:
                from src.core.breaker_block import (
                    find_order_block, to_breaker_block, is_unicorn,
                )
                ob = find_order_block(
                    bars_5m, impulse_end_index=i,
                    direction=direction, max_lookback=10,
                )
                if ob is None:
                    _log_decision(event="unicorn_check", symbol=symbol,
                                   bar_time=bars_5m.index[i], passed=False,
                                   reason="no order block",
                                   details={"direction": direction})
                    continue
                bb = to_breaker_block(ob, bars_5m.iloc[i:])
                if bb is None:
                    _log_decision(event="unicorn_check", symbol=symbol,
                                   bar_time=bars_5m.index[i], passed=False,
                                   reason="OB not broken (not a breaker)",
                                   details={"direction": direction,
                                             "ob_top": ob.top, "ob_bot": ob.bottom})
                    continue
                if not is_unicorn(bb, fvg.top, fvg.bottom):
                    _log_decision(event="unicorn_check", symbol=symbol,
                                   bar_time=bars_5m.index[i], passed=False,
                                   reason="no Breaker-FVG overlap",
                                   details={"bb_top": bb.top, "bb_bot": bb.bottom,
                                             "fvg_top": fvg.top, "fvg_bot": fvg.bottom})
                    continue
                _log_decision(event="unicorn_check", symbol=symbol,
                               bar_time=bars_5m.index[i], passed=True,
                               details={"bb_top": bb.top, "bb_bot": bb.bottom,
                                         "fvg_top": fvg.top, "fvg_bot": fvg.bottom})
            except Exception as e:
                logger.debug(f"Strategy: Unicorn check skipped ({e})")
                _log_decision(event="unicorn_check", symbol=symbol,
                               bar_time=bars_5m.index[i], passed=None,
                               reason=f"exception: {e}")

        # ── ICT Phase 4: OTE entry refinement ──
        # Replace FVG-mid entry with Fibonacci 0.705 of the impulse swing,
        # but only when OTE price *overlaps* the FVG zone.
        if use_ote:
            try:
                from src.core.ote import ote_entry_price, fvg_overlaps_ote
                # Impulse swing for bullish setup: prev_low → breakout_high
                if direction == "bear":
                    impulse_low = float(breakout_candle["Low"])
                    impulse_high = float(prev_candle["High"])
                else:
                    impulse_low = float(prev_candle["Low"])
                    impulse_high = float(breakout_candle["High"])
                ote_price = ote_entry_price(
                    impulse_low, impulse_high,
                    direction=direction, fib_level=ote_fib_level,
                )
                if ote_price and fvg_overlaps_ote(fvg.top, fvg.bottom, ote_price):
                    _log_decision(event="ote_apply", symbol=symbol,
                                   bar_time=bars_5m.index[i], passed=True,
                                   details={"from": round(entry_price, 4),
                                             "to": round(ote_price, 4),
                                             "fib": ote_fib_level})
                    entry_price = ote_price
                else:
                    _log_decision(event="ote_apply", symbol=symbol,
                                   bar_time=bars_5m.index[i], passed=False,
                                   reason="OTE outside FVG zone",
                                   details={"ote_price": round(ote_price or 0, 4),
                                             "fvg_top": fvg.top, "fvg_bot": fvg.bottom})
            except Exception as e:
                logger.debug(f"Strategy: OTE refinement skipped ({e})")
                _log_decision(event="ote_apply", symbol=symbol,
                               bar_time=bars_5m.index[i], passed=None,
                               reason=f"exception: {e}")

        if direction == "bear":
            stop_loss = float(prev_candle["High"])
        else:
            stop_loss = float(prev_candle["Low"])

        # Multi-TF refinement: zoom into 1-min bars before signal_time
        # to derive a tighter, swing-based SL. Falls back to 5-min on any miss.
        if use_multi_tf_sl and bars_1m is not None:
            try:
                from src.core.multi_tf import best_stop
                refined_stop, src = best_stop(
                    bars_1m, bars_5m.index[i], direction,
                    fallback_stop=stop_loss,
                    entry_price=entry_price,
                    min_risk=min_risk,
                )
                if src == "1m":
                    _log_decision(event="mtf_sl_apply", symbol=symbol,
                                   bar_time=bars_5m.index[i], passed=True,
                                   details={"from_5m": round(stop_loss, 4),
                                             "to_1m": round(refined_stop, 4),
                                             "direction": direction})
                else:
                    _log_decision(event="mtf_sl_apply", symbol=symbol,
                                   bar_time=bars_5m.index[i], passed=False,
                                   reason="1m refinement below min_risk",
                                   details={"fallback": round(stop_loss, 4)})
                stop_loss = refined_stop
            except Exception as e:
                logger.debug(f"Strategy: MTF refinement skipped ({e})")
                _log_decision(event="mtf_sl_apply", symbol=symbol,
                               bar_time=bars_5m.index[i], passed=None,
                               reason=f"exception: {e}")

        if direction == "bear":
            risk = stop_loss - entry_price
            tp_direction = -1
        else:
            risk = entry_price - stop_loss
            tp_direction = +1

        if risk <= 0.01:
            logger.debug(f"Strategy: Negative/zero risk at bar {i}, skip")
            continue

        if risk < min_risk:
            logger.debug(f"Strategy: Risk ${risk:.2f} < min ${min_risk:.2f}, skip")
            continue

        take_profit = entry_price + tp_direction * (risk * rr_ratio)
        signal_time = bars_5m.index[i].strftime("%Y-%m-%d %H:%M")

        signal = TradeSignal(
            symbol=symbol,
            direction="long" if direction == "bull" else "short",
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
            f"SIGNAL: {symbol} {signal.direction} @ {entry_price:.2f} "
            f"SL={stop_loss:.2f} TP={take_profit:.2f} "
            f"Risk=${risk:.2f} R:R=1:{rr_ratio}"
        )
        _log_decision(event="signal_emit", symbol=symbol,
                       bar_time=bars_5m.index[i], passed=True,
                       details={"direction": signal.direction,
                                 "entry": round(entry_price, 4),
                                 "stop": round(stop_loss, 4),
                                 "target": round(take_profit, 4),
                                 "risk": round(risk, 4),
                                 "rr": rr_ratio,
                                 "filters": {
                                     "killzone": bool(allowed_killzones),
                                     "displacement": require_displacement,
                                     "sweep_choch": require_sweep_choch,
                                     "unicorn": require_unicorn,
                                     "ote": use_ote,
                                     "mtf_sl": use_multi_tf_sl,
                                 }})
        return signal

    logger.debug("Strategy: No signal found in scan window")
    return None


def check_pullback(
    bar: pd.Series, fvg: FairValueGap, direction: str = "bull",
) -> bool:
    """
    Check if a bar enters the FVG zone (pullback).

    For Long (direction='bull'): the bar's Low must dip to/below FVG top.
    For Short (direction='bear'): the bar's High must rise to/above FVG bottom
    (the lower of the bearish-FVG envelope, since for bearish FVGs we name
    top=c1.Low and bottom=c3.High → bottom is the *lower* of the two).

    Args:
        bar: Single 5-min bar (Series with High, Low, Open, Close).
        fvg: The FVG zone to check against.
        direction: 'bull' (default) or 'bear'.

    Returns:
        True if pullback occurred.
    """
    if direction == "bear":
        return bar["High"] >= fvg.bottom
    return bar["Low"] <= fvg.top
