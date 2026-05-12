"""ICT Phase-3 signal-to-execution price mapper.

Casper SMC ICT recommends extracting signals from the *underlying*
(QQQ) chart but executing trades on the leveraged ETF (TQQQ for bullish,
SQQQ for bearish-as-Long). This module performs that mapping.

Assumption (intraday-only, RTH 09:30–15:50): TQQQ ≈ +3× QQQ and
SQQQ ≈ −3× QQQ per Casper Long-only environment. Path-dependency
(decay, daily-rebal) is small within a 1-day window.
"""

from dataclasses import replace
from typing import Optional

from src.core.strategy import TradeSignal


LEVERAGE_FACTOR = 3.0
# Leveraged ETFs typically slip ~0.5% off perfect 3× due to fees/decay;
# this constant adjusts the SL/TP envelope so we don't over-shoot.
LEVERAGE_SLIPPAGE = 0.05  # 5% relative haircut on the leverage factor


def _effective_leverage() -> float:
    return LEVERAGE_FACTOR * (1.0 - LEVERAGE_SLIPPAGE)


def remap_qqq_bull_to_tqqq_long(
    qqq_signal: TradeSignal,
    tqqq_current_price: float,
    exec_symbol: str = "TQQQ",
) -> Optional[TradeSignal]:
    """Alias used by bot.py when bull_fvg_for_tqqq is enabled (symmetric to
    remap_qqq_bear_to_sqqq_long).
    """
    return remap_qqq_to_tqqq_long(qqq_signal, tqqq_current_price, exec_symbol)


def remap_qqq_to_tqqq_long(
    qqq_signal: TradeSignal,
    tqqq_current_price: float,
    exec_symbol: str = "TQQQ",
) -> Optional[TradeSignal]:
    """Convert a QQQ bullish TradeSignal to a TQQQ Long TradeSignal.

    QQQ rises X% from entry to TP  ⇒ TQQQ rises ≈ 3×X% from current price.
    QQQ falls Y% from entry to SL  ⇒ TQQQ falls ≈ 3×Y%.

    Returns None if the input is invalid or risk becomes non-positive.
    """
    if qqq_signal is None or qqq_signal.direction != "long":
        return None
    if tqqq_current_price <= 0:
        return None

    qqq_entry = qqq_signal.entry_price
    if qqq_entry <= 0:
        return None

    # QQQ percentage moves (entry → SL is downward for Long; entry → TP is upward)
    qqq_risk_pct = (qqq_entry - qqq_signal.stop_loss) / qqq_entry
    qqq_tp_pct = (qqq_signal.take_profit - qqq_entry) / qqq_entry

    lev = _effective_leverage()
    tqqq_entry = tqqq_current_price
    tqqq_stop = tqqq_entry * (1.0 - lev * qqq_risk_pct)
    tqqq_tp = tqqq_entry * (1.0 + lev * qqq_tp_pct)
    risk_ps = tqqq_entry - tqqq_stop

    if risk_ps <= 0:
        return None

    return replace(
        qqq_signal,
        symbol=exec_symbol,
        direction="long",
        entry_price=round(tqqq_entry, 2),
        stop_loss=round(tqqq_stop, 2),
        take_profit=round(tqqq_tp, 2),
        risk_per_share=round(risk_ps, 2),
    )


def remap_qqq_bear_to_sqqq_long(
    qqq_signal: TradeSignal,
    sqqq_current_price: float,
    exec_symbol: str = "SQQQ",
) -> Optional[TradeSignal]:
    """Convert a QQQ BEARISH (short) TradeSignal to an SQQQ Long signal.

    Inverse 3× mapping:
      QQQ rises X% (signal failure)  ⇒ SQQQ falls ≈ 3×X% → SQQQ stop below entry.
      QQQ falls Y% (signal success)  ⇒ SQQQ rises ≈ 3×Y% → SQQQ TP above entry.

    Bear QQQ signal geometry (set by scan_for_signal in bear mode):
      stop_loss > entry_price > take_profit
    """
    if qqq_signal is None or qqq_signal.direction not in ("short", "bear"):
        return None
    if sqqq_current_price <= 0:
        return None

    qqq_entry = qqq_signal.entry_price
    if qqq_entry <= 0:
        return None

    qqq_risk_pct = (qqq_signal.stop_loss - qqq_entry) / qqq_entry   # >0
    qqq_tp_pct = (qqq_entry - qqq_signal.take_profit) / qqq_entry    # >0

    lev = _effective_leverage()
    sqqq_entry = sqqq_current_price
    sqqq_stop = sqqq_entry * (1.0 - lev * qqq_risk_pct)
    sqqq_tp = sqqq_entry * (1.0 + lev * qqq_tp_pct)
    risk_ps = sqqq_entry - sqqq_stop

    if risk_ps <= 0:
        return None

    return replace(
        qqq_signal,
        symbol=exec_symbol,
        direction="long",
        entry_price=round(sqqq_entry, 2),
        stop_loss=round(sqqq_stop, 2),
        take_profit=round(sqqq_tp, 2),
        risk_per_share=round(risk_ps, 2),
    )
