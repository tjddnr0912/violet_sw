"""Tests for src.core.breaker_block."""

import pandas as pd
import pytest

from src.core.breaker_block import (
    find_order_block, is_broken, to_breaker_block, is_unicorn,
    OrderBlock, BreakerBlock,
)


def _df(rows):
    idx = pd.date_range("2026-05-12 09:30", periods=len(rows), freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        rows, columns=["Open", "High", "Low", "Close"], index=idx,
    )


def test_find_order_block_bull_returns_last_bearish():
    # 4 bullish, then 1 bearish, then impulse at index 5
    rows = [
        (100, 101, 99, 100.5),    # bullish
        (100.5, 101.5, 99.5, 101),  # bullish
        (101, 102, 100, 101.5),    # bullish
        (101.5, 101.8, 100, 100.2),  # bearish ← this is the OB
        (100.2, 100.5, 99.5, 100),    # bearish (closer to impulse but we want LAST opposite)
        (100, 105, 99.5, 104.5),     # impulse up (index 5)
    ]
    df = _df(rows)
    ob = find_order_block(df, impulse_end_index=5, direction="bull", max_lookback=5)
    assert ob is not None
    # The LAST opposite (bearish) before impulse is index 4
    assert ob.timestamp == df.index[4]
    assert ob.direction == "bullish_OB"
    assert ob.top == 100.2  # open
    assert ob.bottom == 100.0  # close


def test_find_order_block_bear_returns_last_bullish():
    rows = [
        (105, 106, 104, 104.5),  # bearish
        (104.5, 105, 103, 103.5),  # bearish
        (103.5, 104, 103, 103.2),  # bearish
        (103.2, 105, 103, 104.5),  # bullish ← OB candidate
        (104.5, 105, 100, 100.5),  # impulse down (index 4)
    ]
    df = _df(rows)
    ob = find_order_block(df, impulse_end_index=4, direction="bear", max_lookback=5)
    assert ob is not None
    assert ob.timestamp == df.index[3]
    assert ob.direction == "bearish_OB"


def test_find_order_block_returns_none_when_no_opposite():
    rows = [(100, 101, 99, 100.5)] * 5 + [(100.5, 105, 100, 104.5)]
    df = _df(rows)
    # All bullish (open<close), no bearish OB available
    ob = find_order_block(df, impulse_end_index=5, direction="bull", max_lookback=5)
    assert ob is None


def test_is_broken_bullish_ob():
    ob = OrderBlock(pd.Timestamp("2026-05-12 09:50", tz="US/Eastern"),
                    top=100.0, bottom=99.0, direction="bullish_OB")
    rows = [(98, 99, 97, 97.5)]  # close below 99 = bottom
    df = _df(rows)
    assert is_broken(ob, df) is True


def test_is_broken_bullish_ob_intact():
    ob = OrderBlock(pd.Timestamp("2026-05-12 09:50", tz="US/Eastern"),
                    top=100.0, bottom=99.0, direction="bullish_OB")
    rows = [(99.5, 100.5, 99.2, 100)]  # close ABOVE bottom — intact
    df = _df(rows)
    assert is_broken(ob, df) is False


def test_to_breaker_block_conversion():
    ob = OrderBlock(pd.Timestamp("2026-05-12 09:50", tz="US/Eastern"),
                    top=100.0, bottom=99.0, direction="bullish_OB")
    rows = [(98, 99, 97, 97.5)]
    df = _df(rows)
    bb = to_breaker_block(ob, df)
    assert bb is not None
    assert bb.direction == "resistance"  # former bullish_OB acts as resistance after break
    assert bb.top == 100.0
    assert bb.bottom == 99.0


def test_to_breaker_block_returns_none_if_not_broken():
    ob = OrderBlock(pd.Timestamp("2026-05-12 09:50", tz="US/Eastern"),
                    top=100.0, bottom=99.0, direction="bullish_OB")
    rows = [(99.5, 100.5, 99.2, 100)]
    df = _df(rows)
    assert to_breaker_block(ob, df) is None


def test_is_unicorn_overlap():
    bb = BreakerBlock(pd.Timestamp("2026-05-12 09:55", tz="US/Eastern"),
                      top=100.0, bottom=99.0, direction="support",
                      parent_ob_timestamp=pd.Timestamp("2026-05-12 09:50", tz="US/Eastern"))
    assert is_unicorn(bb, fvg_top=99.8, fvg_bottom=99.2) is True


def test_is_unicorn_no_overlap():
    bb = BreakerBlock(pd.Timestamp("2026-05-12 09:55", tz="US/Eastern"),
                      top=100.0, bottom=99.0, direction="support",
                      parent_ob_timestamp=pd.Timestamp("2026-05-12 09:50", tz="US/Eastern"))
    assert is_unicorn(bb, fvg_top=102.0, fvg_bottom=101.5, tolerance_pct=0.0) is False
