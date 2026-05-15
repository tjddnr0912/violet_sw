"""Tests for ICT-stage notifier methods added 2026-05-12."""

from unittest.mock import patch
from dataclasses import dataclass

from src.telegram.notifier import TelegramNotifier


def _captured(mock_send):
    args, _ = mock_send.call_args
    return args[0] if args else ""


@dataclass
class _StubBias:
    direction: str
    score: int
    components: dict
    pdh: float
    pdl: float
    pwh: float
    pwl: float


@dataclass
class _StubORB:
    high: float
    low: float
    range_size: float


@patch.object(TelegramNotifier, "send", return_value=True)
def test_daily_bias_bull(mock_send):
    n = TelegramNotifier("t", "c")
    bias = _StubBias("bull", 3, {"ma20": 1, "ma50": 1, "pdh": 1}, 500.0, 480.0, 505.0, 470.0)
    n.notify_daily_bias(bias)
    text = _captured(mock_send)
    assert "DAILY BIAS" in text
    assert "BULL" in text
    assert "+3" in text   # score rendered as "BULL   score +3"


@patch.object(TelegramNotifier, "send", return_value=True)
def test_daily_bias_neutral(mock_send):
    n = TelegramNotifier("t", "c")
    bias = _StubBias("neutral", 0, {}, 500.0, 480.0, 505.0, 470.0)
    n.notify_daily_bias(bias)
    text = _captured(mock_send)
    assert "NEUTRAL" in text
    assert "+0" in text   # neutral score


def test_daily_bias_none_does_not_send():
    n = TelegramNotifier("t", "c")
    with patch.object(TelegramNotifier, "send", return_value=True) as m:
        n.notify_daily_bias(None)
        assert not m.called


@patch.object(TelegramNotifier, "send", return_value=True)
def test_orb_summary_multi_symbol(mock_send):
    n = TelegramNotifier("t", "c")
    orbs = {
        "TQQQ": _StubORB(50.0, 49.0, 1.0),
        "SQQQ": _StubORB(28.0, 27.0, 1.0),
        "QQQ":  _StubORB(500.0, 498.0, 2.0),
    }
    n.notify_orb_summary(orbs)
    text = _captured(mock_send)
    assert "ORB Summary" in text   # new layout uses Title Case
    assert "TQQQ" in text and "SQQQ" in text and "QQQ" in text


def test_orb_summary_empty_does_not_send():
    n = TelegramNotifier("t", "c")
    with patch.object(TelegramNotifier, "send", return_value=True) as m:
        n.notify_orb_summary({})
        assert not m.called


@patch.object(TelegramNotifier, "send", return_value=True)
def test_scan_start_with_kz_and_window(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_scan_start(killzone_label="AM_MACRO", kst_window="KST 22:45~23:10")
    text = _captured(mock_send)
    assert "SCAN START" in text
    assert "AM_MACRO" in text
    assert "22:45" in text


@patch.object(TelegramNotifier, "send", return_value=True)
def test_setup_detected_bull(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_setup_detected(
        "TQQQ", "long", fvg_top=51.0, fvg_bot=50.5,
        filters_active=["killzone", "displacement"],
    )
    text = _captured(mock_send)
    assert "SETUP" in text and "TQQQ" in text
    assert "50.50" in text and "51.00" in text
    # New layout: ("Filters", "killzone, displacement") — comma-space joined
    assert "killzone, displacement" in text


@patch.object(TelegramNotifier, "send", return_value=True)
def test_setup_detected_short(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_setup_detected(
        "QQQ", "short", fvg_top=500.0, fvg_bot=498.5,
    )
    text = _captured(mock_send)
    # New layout renders Direction in upper-case
    assert "SHORT" in text


@patch.object(TelegramNotifier, "send", return_value=True)
def test_killzone_end_no_signal(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_killzone_end_no_signal()
    text = _captured(mock_send)
    assert "KILLZONE END" in text
    assert "AM_MACRO" in text


@patch.object(TelegramNotifier, "send", return_value=True)
def test_filter_reject(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_filter_reject("TQQQ", "displacement", "body 0.4 < 1.0×ATR")
    text = _captured(mock_send)
    assert "FILTER" in text and "displacement" in text
