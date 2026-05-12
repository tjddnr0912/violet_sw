"""Tests for src.data.futures (NQ=F 24h helpers)."""

from datetime import date

import pandas as pd
import pytest

from src.data.futures import (
    asia_session_range, london_session_range, midnight_open_price,
    detect_judas_swing,
)


def _synth_bars(day, prices_by_hour):
    """prices_by_hour: dict {hour:int → (open, high, low, close)} relative to ET."""
    rows = []
    idx = []
    base = pd.Timestamp(day).tz_localize("US/Eastern")
    # 24h span; 5-min cadence
    for hour in range(-6, 17):  # previous day 18:00 → this day 17:00
        ts = base + pd.Timedelta(hours=hour)
        ohlc = prices_by_hour.get(hour, (100.0, 100.2, 99.8, 100.0))
        for minute in range(0, 60, 5):
            idx.append(ts + pd.Timedelta(minutes=minute))
            rows.append(ohlc)
    df = pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"],
                      index=pd.DatetimeIndex(idx))
    df["Volume"] = 1000
    return df


def test_asia_range_uses_prev_18_to_00():
    bars = _synth_bars("2026-05-12", {
        -6: (100, 102, 98, 101),   # 18:00 prev day
        -3: (101, 105, 100, 104),  # 21:00 prev day  ← high here
        -1: (104, 105, 99, 100),   # 23:00 prev day
         0: (100, 100, 100, 100),  # 00:00 — NOT included (end-exclusive)
    })
    rng = asia_session_range(bars, "2026-05-12")
    assert rng is not None
    high, low = rng
    assert high == 105
    assert low == 98


def test_london_range_uses_02_to_05():
    bars = _synth_bars("2026-05-12", {
        2: (100, 103, 99, 100),
        3: (100, 108, 99, 100),  # 03:00 high
        4: (100, 105, 95, 100),  # 04:00 low
    })
    rng = london_session_range(bars, "2026-05-12")
    assert rng is not None
    h, l = rng
    assert h == 108
    assert l == 95


def test_midnight_open_returns_open_at_00_00_et():
    bars = _synth_bars("2026-05-12", {
        0: (123.45, 124, 123, 124),
    })
    # The 00:00~00:05 bar's Open is 123.45
    p = midnight_open_price(bars, "2026-05-12")
    assert p == pytest.approx(123.45, rel=1e-3)


def test_midnight_open_returns_none_when_missing():
    df = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    assert midnight_open_price(df, "2026-05-12") is None


def test_judas_swing_bullish_breach_low_then_reversal():
    bars = _synth_bars("2026-05-12", {
        -6: (100, 101, 99, 100),    # asia 18:00
        -3: (100, 102, 99, 101),    # asia high 102, low 99
        2:  (100, 100, 97, 98),     # london — wicks BELOW asia low 99
        3:  (98, 99, 98, 99),       # rebound
        9:  (99, 105, 99, 104),     # RTH — closes ABOVE asia low (reversal)
    })
    sig = detect_judas_swing(bars, "2026-05-12")
    assert sig == "bullish_judas"


def test_judas_swing_returns_none_when_no_breach():
    bars = _synth_bars("2026-05-12", {
        -6: (100, 102, 99, 101),
        -3: (100, 102, 99, 100),
        # All windows stay inside asia range — no breach
        2: (100, 101, 100, 100),
        3: (100, 101, 100, 100),
    })
    assert detect_judas_swing(bars, "2026-05-12") is None
