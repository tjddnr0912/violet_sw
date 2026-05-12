"""Tests for Phase-3 direction='bear' support in scan_for_signal."""

import pandas as pd
import pytest

from src.core.orb import OpeningRange
from src.core.strategy import scan_for_signal


def _post_orb_bearish_setup():
    """Synthetic bearish breakdown of ORB low=99.0 with strict bearish FVG +
    a pullback that lifts price into the FVG zone (so caller has a fill).
    """
    rows = []
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")

    # pre-breakdown bars above ORB low
    for k in range(4):
        ts = start + pd.Timedelta(minutes=5 * k)
        rows.append({"time": ts, "Open": 99.6, "High": 99.8,
                     "Low": 99.4, "Close": 99.5, "Volume": 1000})

    # c1 (top of bearish FVG)
    c1 = start + pd.Timedelta(minutes=5 * 4)
    rows.append({"time": c1, "Open": 99.5, "High": 99.6,
                 "Low": 99.4, "Close": 99.45, "Volume": 1000})

    # c2 breakdown: straddles orb_low (Open above, Close below), bearish, body large
    c2 = c1 + pd.Timedelta(minutes=5)
    rows.append({"time": c2, "Open": 99.45, "High": 99.5,
                 "Low": 98.4, "Close": 98.5, "Volume": 2500})

    # c3 (high < c1.Low=99.4 → bearish FVG)
    c3 = c2 + pd.Timedelta(minutes=5)
    rows.append({"time": c3, "Open": 98.5, "High": 99.0,
                 "Low": 98.2, "Close": 98.4, "Volume": 1500})

    # follow-up: a bar that pulls price back UP into the FVG zone
    for k in range(3):
        ts = c3 + pd.Timedelta(minutes=5 * (k + 1))
        rows.append({"time": ts, "Open": 98.6, "High": 99.40,
                     "Low": 98.5, "Close": 99.0, "Volume": 1000})

    return pd.DataFrame(rows).set_index("time")


def _orb():
    return OpeningRange(high=100.0, low=99.0, range_size=1.0, date="2026-05-12")


def test_bearish_scan_emits_short_signal():
    bars = _post_orb_bearish_setup()
    sig = scan_for_signal(
        bars, _orb(), "TQQQ", rr_ratio=2.0, min_risk=0.05,
        strict=True, direction="bear",
    )
    assert sig is not None
    assert sig.direction == "short"
    assert sig.stop_loss > sig.entry_price > sig.take_profit


def test_bearish_scan_risk_target_geometry():
    bars = _post_orb_bearish_setup()
    sig = scan_for_signal(
        bars, _orb(), "TQQQ", rr_ratio=2.0, min_risk=0.05,
        strict=True, direction="bear",
    )
    assert sig is not None
    risk = sig.stop_loss - sig.entry_price
    reward = sig.entry_price - sig.take_profit
    assert reward == pytest.approx(risk * 2.0, abs=0.05)


def test_bull_direction_unchanged_default():
    # Make sure direction default remains 'bull' and existing bullish setup still emits long
    rows = []
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    for k in range(4):
        ts = start + pd.Timedelta(minutes=5 * k)
        rows.append({"time": ts, "Open": 99.5, "High": 99.8, "Low": 99.3, "Close": 99.6, "Volume": 1000})
    c1 = start + pd.Timedelta(minutes=20)
    rows.append({"time": c1, "Open": 99.7, "High": 99.9, "Low": 99.5, "Close": 99.8, "Volume": 1000})
    c2 = c1 + pd.Timedelta(minutes=5)
    rows.append({"time": c2, "Open": 99.9, "High": 101.0, "Low": 99.85, "Close": 100.9, "Volume": 2500})
    c3 = c2 + pd.Timedelta(minutes=5)
    rows.append({"time": c3, "Open": 100.5, "High": 101.2, "Low": 100.0, "Close": 101.0, "Volume": 1500})
    for k in range(3):
        rows.append({"time": c3 + pd.Timedelta(minutes=5 * (k + 1)),
                     "Open": 100.8, "High": 101.0, "Low": 99.85, "Close": 100.5, "Volume": 1000})
    bars = pd.DataFrame(rows).set_index("time")
    sig = scan_for_signal(bars, _orb(), "TQQQ", rr_ratio=2.0, min_risk=0.05, strict=True)
    assert sig is not None
    assert sig.direction == "long"
    assert sig.take_profit > sig.entry_price > sig.stop_loss


def test_bearish_scan_returns_none_when_no_breakdown():
    # Bullish session — no breakdown
    rows = []
    start = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    for k in range(6):
        ts = start + pd.Timedelta(minutes=5 * k)
        rows.append({"time": ts, "Open": 99.6 + k * 0.1, "High": 99.7 + k * 0.1,
                     "Low": 99.5 + k * 0.1, "Close": 99.65 + k * 0.1, "Volume": 1000})
    bars = pd.DataFrame(rows).set_index("time")
    sig = scan_for_signal(bars, _orb(), "TQQQ", rr_ratio=2.0, min_risk=0.05,
                          strict=True, direction="bear")
    assert sig is None
