"""Tests for src.core.ote (Optimal Trade Entry)."""

import pytest

from src.core.ote import ote_entry_price, fvg_overlaps_ote


# ───── ote_entry_price ─────
def test_ote_bull_705():
    # impulse 100 → 110, fib 0.705 → entry = 110 - 0.705*10 = 102.95
    p = ote_entry_price(100.0, 110.0, direction="bull", fib_level=0.705)
    assert p == pytest.approx(102.95, rel=1e-3)


def test_ote_bull_618():
    p = ote_entry_price(100.0, 110.0, direction="bull", fib_level=0.618)
    assert p == pytest.approx(103.82, rel=1e-3)


def test_ote_bear_705():
    # bear: impulse high → low (100 → 90 conceptually, but we feed sorted)
    # entry = low + 0.705 * (high-low) = 100 + 0.705 * 10 = 107.05
    p = ote_entry_price(100.0, 110.0, direction="bear", fib_level=0.705)
    assert p == pytest.approx(107.05, rel=1e-3)


def test_ote_degenerate_returns_none():
    assert ote_entry_price(100.0, 100.0) is None
    assert ote_entry_price(100.0, 110.0, fib_level=0.0) is None
    assert ote_entry_price(100.0, 110.0, fib_level=1.0) is None
    assert ote_entry_price(100.0, 110.0, fib_level=1.5) is None


# ───── fvg_overlaps_ote ─────
def test_fvg_overlap_inside():
    assert fvg_overlaps_ote(fvg_top=104.0, fvg_bot=102.0, ote_price=103.0) is True


def test_fvg_overlap_at_boundary():
    assert fvg_overlaps_ote(fvg_top=104.0, fvg_bot=102.0, ote_price=104.0) is True
    assert fvg_overlaps_ote(fvg_top=104.0, fvg_bot=102.0, ote_price=102.0) is True


def test_fvg_overlap_outside_without_tolerance():
    assert fvg_overlaps_ote(
        fvg_top=104.0, fvg_bot=102.0, ote_price=100.0, tolerance_pct=0.0
    ) is False


def test_fvg_overlap_within_tolerance():
    # 0.2% of midpoint 103 = 0.206
    # 101.85 is 0.15 below 102 → within tolerance → True
    assert fvg_overlaps_ote(
        fvg_top=104.0, fvg_bot=102.0, ote_price=101.85, tolerance_pct=0.002
    ) is True
    # 101.50 is 0.50 below 102 → outside tolerance → False
    assert fvg_overlaps_ote(
        fvg_top=104.0, fvg_bot=102.0, ote_price=101.50, tolerance_pct=0.002
    ) is False


def test_fvg_overlap_handles_inverted_top_bot():
    # bearish FVG has top > bottom in the dataclass too (top=c1.Low, bot=c3.High)
    # so technically top can be > or < bottom. fvg_overlaps_ote sorts internally.
    assert fvg_overlaps_ote(fvg_top=102.0, fvg_bot=104.0, ote_price=103.0) is True
