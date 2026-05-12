"""Tests for src.core.displacement."""

import pandas as pd
import pytest

from src.core.displacement import is_displacement, atr14


def _bar(o, h, l, c):
    return pd.Series({"Open": o, "High": h, "Low": l, "Close": c})


def _prev_bars(bodies):
    """Build a small prev_bars DataFrame from a list of body sizes."""
    rows = []
    base = 100.0
    for b in bodies:
        rows.append({"Open": base, "High": base + b + 0.05, "Low": base - 0.05, "Close": base + b})
        base += b
    return pd.DataFrame(rows)


# ───────────────── atr14 ─────────────────
def test_atr14_returns_none_when_insufficient_bars():
    df = pd.DataFrame({"High": [1], "Low": [0], "Close": [0.5]})
    assert atr14(df) is None


def test_atr14_computes_when_15_plus_bars():
    n = 20
    df = pd.DataFrame({
        "High":  [100 + i + 0.5 for i in range(n)],
        "Low":   [100 + i - 0.5 for i in range(n)],
        "Close": [100 + i for i in range(n)],
    })
    val = atr14(df)
    assert val is not None and val > 0
    # range is ~1.0 per bar, TR ≈ 1.0 so ATR ≈ 1.0
    assert 0.5 < val < 2.0


# ───────────────── is_displacement: body/wick rule ─────────────────
def test_strong_bull_displacement_passes():
    # body 0.9, total 1.0 → wick 10% — passes
    bar = _bar(100.0, 101.0, 99.95, 100.9)
    prev = _prev_bars([0.2, 0.3, 0.2, 0.25, 0.3])  # avg body 0.25, 1.5× = 0.375 < 0.9
    assert is_displacement(bar, prev, atr_value=None) is True


def test_wide_wick_rejected():
    # body 0.3, total 1.0 → wick 70% (>50%) — should fail
    bar = _bar(100.0, 100.7, 99.7, 100.3)
    prev = _prev_bars([0.1, 0.1, 0.1])
    assert is_displacement(bar, prev) is False


def test_bear_direction_filter():
    # body bullish but direction='bear' demanded
    bar = _bar(100.0, 101.0, 99.9, 100.9)
    prev = _prev_bars([0.1, 0.1, 0.1])
    assert is_displacement(bar, prev, direction="bear") is False


def test_bull_direction_filter_passes_bull_bar():
    bar = _bar(100.0, 101.0, 99.9, 100.9)
    prev = _prev_bars([0.1, 0.1, 0.1])
    assert is_displacement(bar, prev, direction="bull") is True


# ───────────────── ATR check ─────────────────
def test_atr_too_small_body_rejected():
    bar = _bar(100.0, 100.8, 99.9, 100.6)  # body 0.6, wick small
    # ATR 1.0, atr_mult 1.0 → require body ≥ 1.0 → 0.6 fails
    prev = _prev_bars([0.1, 0.1, 0.1])
    assert is_displacement(bar, prev, atr_value=1.0, atr_mult=1.0) is False


def test_atr_passes_when_body_large():
    bar = _bar(100.0, 101.5, 99.9, 101.4)  # body 1.4
    prev = _prev_bars([0.1, 0.1, 0.1])
    assert is_displacement(bar, prev, atr_value=1.0, atr_mult=1.0) is True


def test_atr_check_skipped_when_none():
    # body 0.5 — would fail body/ATR but ATR None → skipped, prev check passes
    bar = _bar(100.0, 100.6, 99.95, 100.5)
    prev = _prev_bars([0.05, 0.1, 0.08])  # avg ~0.08, 1.5× = 0.12 < 0.5 OK
    assert is_displacement(bar, prev, atr_value=None) is True


# ───────────────── prev_bars relative ─────────────────
def test_body_smaller_than_prev_mean_rejected():
    bar = _bar(100.0, 100.5, 99.95, 100.4)  # body 0.4
    prev = _prev_bars([0.5, 0.6, 0.5])  # avg 0.53, 1.5× = 0.8 > 0.4 → fail
    assert is_displacement(bar, prev, atr_value=None) is False


def test_prev_check_skipped_when_none():
    bar = _bar(100.0, 100.5, 99.95, 100.4)
    # No prev bars → skip relative check; wick OK and no ATR limit
    assert is_displacement(bar, None, atr_value=None) is True


def test_prev_check_skipped_when_fewer_than_3():
    bar = _bar(100.0, 100.5, 99.95, 100.4)
    prev_small = pd.DataFrame({"Open": [100, 100], "Close": [100.5, 100.5],
                               "High": [100.5, 100.5], "Low": [100, 100]})
    # Only 2 prev bars → check skipped
    assert is_displacement(bar, prev_small, atr_value=None) is True


# ───────────────── edge cases ─────────────────
def test_zero_range_bar_rejected():
    bar = _bar(100.0, 100.0, 100.0, 100.0)
    assert is_displacement(bar, None) is False


def test_combined_strict_thresholds():
    # body=1.4, ATR 1.0, prev mean 0.3 → both checks pass
    bar = _bar(100.0, 101.5, 99.95, 101.4)  # body 1.4, wick 0.1/1.55 = 6.5%
    prev = _prev_bars([0.3, 0.3, 0.3, 0.3])
    assert is_displacement(bar, prev, atr_value=1.0, atr_mult=1.3, max_wick=0.40) is True
