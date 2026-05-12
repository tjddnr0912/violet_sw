"""Tests for src.core.exec_mapper."""

import pytest

from src.core.strategy import TradeSignal
from src.core.exec_mapper import (
    remap_qqq_to_tqqq_long, remap_qqq_bear_to_sqqq_long,
    _effective_leverage,
)
from src.core.fvg import FairValueGap
from src.core.orb import OpeningRange


def _qqq_bull_signal(entry=500.0, stop=499.0, target=502.0):
    return TradeSignal(
        symbol="QQQ", direction="long",
        entry_price=entry, stop_loss=stop, take_profit=target,
        risk_per_share=entry - stop, rr_ratio=2.0,
        fvg=FairValueGap(top=entry + 0.5, bottom=entry - 0.5, size=1.0,
                         timestamp="2026-05-12 10:00"),
        orb=OpeningRange(high=entry, low=stop, range_size=entry - stop,
                         date="2026-05-12"),
        signal_time="2026-05-12 10:00",
    )


def _qqq_bear_signal(entry=500.0, stop=502.0, target=496.0):
    # bear geometry: stop > entry > target
    return TradeSignal(
        symbol="QQQ", direction="short",
        entry_price=entry, stop_loss=stop, take_profit=target,
        risk_per_share=stop - entry, rr_ratio=2.0,
        fvg=FairValueGap(top=entry + 0.5, bottom=entry - 0.5, size=1.0,
                         timestamp="2026-05-12 10:00"),
        orb=OpeningRange(high=stop, low=target, range_size=stop - target,
                         date="2026-05-12"),
        signal_time="2026-05-12 10:00",
    )


# ───── remap_qqq_to_tqqq_long ─────
def test_tqqq_remap_basic_geometry():
    sig = _qqq_bull_signal(entry=500.0, stop=499.0, target=502.0)
    # QQQ risk pct = 0.2%, TP pct = 0.4%
    out = remap_qqq_to_tqqq_long(sig, tqqq_current_price=100.0)
    assert out is not None
    assert out.symbol == "TQQQ"
    assert out.direction == "long"
    assert out.entry_price == 100.0
    # effective leverage = 3 * 0.95 = 2.85
    lev = _effective_leverage()
    expected_stop = round(100.0 * (1 - lev * 0.002), 2)
    expected_tp = round(100.0 * (1 + lev * 0.004), 2)
    assert out.stop_loss == expected_stop
    assert out.take_profit == expected_tp


def test_tqqq_remap_preserves_rr_ratio():
    sig = _qqq_bull_signal(entry=500.0, stop=499.0, target=502.0)
    out = remap_qqq_to_tqqq_long(sig, tqqq_current_price=100.0)
    assert out.rr_ratio == sig.rr_ratio


def test_tqqq_remap_rejects_none_input():
    assert remap_qqq_to_tqqq_long(None, 100.0) is None


def test_tqqq_remap_rejects_zero_price():
    sig = _qqq_bull_signal()
    assert remap_qqq_to_tqqq_long(sig, 0.0) is None
    assert remap_qqq_to_tqqq_long(sig, -1.0) is None


def test_tqqq_remap_rejects_short_signal():
    sig = _qqq_bear_signal()
    assert remap_qqq_to_tqqq_long(sig, 100.0) is None


# ───── remap_qqq_bear_to_sqqq_long ─────
def test_sqqq_remap_basic_geometry():
    sig = _qqq_bear_signal(entry=500.0, stop=502.0, target=496.0)
    # QQQ risk pct = 0.4%, TP pct = 0.8%
    out = remap_qqq_bear_to_sqqq_long(sig, sqqq_current_price=50.0)
    assert out is not None
    assert out.symbol == "SQQQ"
    assert out.direction == "long"  # SQQQ Long mapping
    lev = _effective_leverage()
    expected_stop = round(50.0 * (1 - lev * 0.004), 2)
    expected_tp = round(50.0 * (1 + lev * 0.008), 2)
    assert out.stop_loss == expected_stop
    assert out.take_profit == expected_tp


def test_sqqq_remap_target_above_entry_stop_below():
    sig = _qqq_bear_signal()
    out = remap_qqq_bear_to_sqqq_long(sig, sqqq_current_price=50.0)
    # Long SQQQ: TP > entry > SL
    assert out.take_profit > out.entry_price > out.stop_loss


def test_sqqq_remap_rejects_bull_signal():
    sig = _qqq_bull_signal()
    assert remap_qqq_bear_to_sqqq_long(sig, 50.0) is None


def test_sqqq_remap_rejects_none_input():
    assert remap_qqq_bear_to_sqqq_long(None, 50.0) is None


def test_sqqq_remap_rejects_invalid_price():
    sig = _qqq_bear_signal()
    assert remap_qqq_bear_to_sqqq_long(sig, 0.0) is None


# ───── leverage constant ─────
def test_effective_leverage_below_3x():
    assert 2.5 < _effective_leverage() < 3.0
