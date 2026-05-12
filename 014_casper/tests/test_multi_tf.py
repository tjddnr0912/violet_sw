"""Tests for src.core.multi_tf."""

import pandas as pd
import pytest

from src.core.multi_tf import refine_stop_with_1min, best_stop


def _bars_1m(start_ts, prices_high, prices_low, n_min=15):
    """prices_high/low: lists of length n_min."""
    idx = pd.date_range(start_ts, periods=n_min, freq="1min", tz="US/Eastern")
    return pd.DataFrame({
        "Open":  prices_low,
        "High":  prices_high,
        "Low":   prices_low,
        "Close": prices_low,
    }, index=idx)


def test_refine_long_finds_min_low():
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    sig_t = start + pd.Timedelta(minutes=14)
    bars = _bars_1m(start, [101]*15, [99, 98, 97, 96, 95, 96, 97, 98, 99, 100, 99, 98, 99, 100, 101])
    out = refine_stop_with_1min(bars, sig_t, "bull", fallback_stop=90.0, lookback_min=15)
    assert out == 95


def test_refine_short_finds_max_high():
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    sig_t = start + pd.Timedelta(minutes=14)
    bars = _bars_1m(start, [99, 100, 102, 103, 105, 104, 103, 102, 101, 100, 99, 98, 99, 100, 101],
                   [97]*15)
    out = refine_stop_with_1min(bars, sig_t, "bear", fallback_stop=120.0, lookback_min=15)
    assert out == 105


def test_refine_fallback_when_no_data():
    sig_t = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    out = refine_stop_with_1min(None, sig_t, "bull", fallback_stop=95.0)
    assert out == 95.0


def test_refine_fallback_when_empty_window():
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    sig_t = start - pd.Timedelta(minutes=30)
    bars = _bars_1m(start, [100]*15, [99]*15)
    # cutoff is before our bar window
    out = refine_stop_with_1min(bars, sig_t, "bull", fallback_stop=42.0)
    assert out == 42.0


def test_best_stop_uses_1m_when_meets_min_risk():
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    sig_t = start + pd.Timedelta(minutes=14)
    bars = _bars_1m(start, [101]*15, [99, 98, 97, 96, 95, 96, 97, 98, 99, 100, 99, 98, 99, 100, 101])
    stop, src = best_stop(bars, sig_t, "bull", fallback_stop=90.0, entry_price=100.0, min_risk=0.10)
    assert src == "1m"
    assert stop == 95


def test_best_stop_falls_back_when_min_risk_violated():
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    sig_t = start + pd.Timedelta(minutes=14)
    # entry 100, refined low 99.99 → risk 0.01 < min_risk 0.10
    bars = _bars_1m(start, [100.5]*15, [99.99]*15)
    stop, src = best_stop(bars, sig_t, "bull", fallback_stop=99.0, entry_price=100.0, min_risk=0.10)
    assert src == "5m_fallback"
    assert stop == 99.0
