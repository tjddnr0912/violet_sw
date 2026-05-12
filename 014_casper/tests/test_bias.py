"""Tests for src.core.bias (Daily Bias)."""

from datetime import date, timedelta

import pandas as pd
import pytest

from src.core.bias import compute_daily_bias, DailyBias


def _build_daily(prices, end_date=date(2026, 5, 11)):
    """prices: list of Close values. High = Close+0.5, Low = Close-0.5."""
    n = len(prices)
    idx = pd.date_range(end=pd.Timestamp(end_date), periods=n, freq="B")
    df = pd.DataFrame({
        "Open":  prices,
        "High":  [p + 0.5 for p in prices],
        "Low":   [p - 0.5 for p in prices],
        "Close": prices,
    }, index=idx)
    return df


# ───── basic shape ─────
def test_bias_returns_none_when_insufficient_history():
    df = _build_daily(list(range(10)))
    assert compute_daily_bias(df) is None


def test_bias_returns_object_when_history_sufficient():
    df = _build_daily([100 + i for i in range(25)])
    bias = compute_daily_bias(df)
    assert isinstance(bias, DailyBias)
    assert bias.direction in ("bull", "bear", "neutral")


# ───── direction logic ─────
def test_bias_bull_in_strong_uptrend():
    # 25-day uptrend
    df = _build_daily([100 + i for i in range(25)])
    bias = compute_daily_bias(df)
    assert bias.direction == "bull"
    assert bias.score > 0


def test_bias_bear_in_strong_downtrend():
    df = _build_daily([200 - i for i in range(25)])
    bias = compute_daily_bias(df)
    assert bias.direction == "bear"
    assert bias.score < 0


def test_bias_neutral_in_choppy_range():
    # Tight oscillation around 100 — last close should be near MA20 and within PDH/PDL window
    seq = [100 + (i % 2) for i in range(25)]
    df = _build_daily(seq)
    bias = compute_daily_bias(df)
    # neutral OR very small score
    assert -1 <= bias.score <= 1


# ───── component toggles ─────
def test_bias_can_disable_components():
    df = _build_daily([100 + i for i in range(25)])
    full = compute_daily_bias(df)
    only_ma = compute_daily_bias(df, use_pdh_pdl=False, use_pwh_pwl=False, use_ma50=False)
    assert "pdh" not in only_ma.components and "pwh" not in only_ma.components
    assert full.score >= only_ma.score  # full enabled gives >= score (in bull case)


# ───── as_of cutoff ─────
def test_bias_excludes_rows_at_or_after_as_of():
    df = _build_daily([100 + i for i in range(30)], end_date=date(2026, 5, 14))
    # as_of = the most recent date in df → that row should be excluded
    as_of = df.index[-1].date()
    bias = compute_daily_bias(df, as_of=as_of)
    # Still must produce a result from prior 29 rows
    assert bias is not None
    # PDH should equal the High of the 2nd-to-last row in df
    expected_pdh = float(df.iloc[-2]["High"])
    assert bias.pdh == expected_pdh


# ───── PDH / PWH semantics ─────
def test_bias_pdh_equals_last_row_high():
    df = _build_daily([100 + i for i in range(25)])
    bias = compute_daily_bias(df)
    assert bias.pdh == float(df.iloc[-1]["High"])
    assert bias.pdl == float(df.iloc[-1]["Low"])


def test_bias_pwh_pwl_span_last_5_rows():
    df = _build_daily([100 + i for i in range(25)])
    bias = compute_daily_bias(df)
    last5 = df.tail(5)
    assert bias.pwh == float(last5["High"].max())
    assert bias.pwl == float(last5["Low"].min())
