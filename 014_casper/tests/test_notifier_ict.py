"""Tests for ICT info in TelegramNotifier output."""

from unittest.mock import patch

from src.telegram.notifier import TelegramNotifier


def _captured_send_text(mock_send):
    """Return the first positional argument passed to send (the text)."""
    assert mock_send.call_args is not None
    args, kwargs = mock_send.call_args
    return args[0] if args else kwargs.get("text", "")


# ───── notify_bot_started ─────
def setup_function(_):
    pass


@patch.object(TelegramNotifier, "send", return_value=True)
def test_bot_started_ict_off_renders_off(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_bot_started(
        "live", 1500.0,
        {"count": 0, "win_rate": 0, "pnl": 0},
        strategy_info={"dual_scan": True, "strict_fvg": True, "rr_ratio": 3.0},
    )
    text = _captured_send_text(mock_send)
    assert "ICT: off" in text


@patch.object(TelegramNotifier, "send", return_value=True)
def test_bot_started_ict_flags_render(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_bot_started(
        "live", 1500.0,
        {"count": 0, "win_rate": 0, "pnl": 0},
        strategy_info={
            "dual_scan": True, "strict_fvg": True, "rr_ratio": 3.0,
            "ict_killzone": True,
            "ict_allowed_killzones": ["AM_MACRO"],
            "ict_displacement": True,
            "ict_sweep_choch": True,
            "ict_daily_bias": True,
            "ict_bear_for_sqqq": True,
        },
    )
    text = _captured_send_text(mock_send)
    assert "ICT:" in text
    assert "KZ(AM_MACRO)" in text
    assert "Disp" in text
    assert "Sweep" in text
    assert "Bias" in text
    assert "QQQ→SQQQ" in text


@patch.object(TelegramNotifier, "send", return_value=True)
def test_bot_started_no_strategy_info_still_works(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_bot_started(
        "paper", 500.0,
        {"count": 0, "win_rate": 0, "pnl": 0},
    )
    text = _captured_send_text(mock_send)
    assert "BOT STARTED" in text
    # No ICT line at all when strategy_info absent
    assert "ICT" not in text


# ───── notify_signal ─────
@patch.object(TelegramNotifier, "send", return_value=True)
def test_signal_without_ict_meta_keeps_legacy_format(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_signal("TQQQ", 100.0, 99.5, 101.5, 3.0)
    text = _captured_send_text(mock_send)
    assert "SIGNAL" in text and "TQQQ" in text
    assert "ICT" not in text


@patch.object(TelegramNotifier, "send", return_value=True)
def test_signal_with_ict_meta_renders_killzone_filters_bias(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_signal(
        "TQQQ", 100.0, 99.5, 101.5, 3.0,
        ict_meta={
            "killzone": "AM_MACRO",
            "filters_active": ["killzone", "displacement", "sweep_choch"],
            "daily_bias_direction": "bull",
            "daily_bias_score": 3,
        },
    )
    text = _captured_send_text(mock_send)
    assert "KZ:AM_MACRO" in text
    assert "filters:killzone,displacement,sweep_choch" in text
    assert "bias:bull(+3)" in text


@patch.object(TelegramNotifier, "send", return_value=True)
def test_signal_with_partial_ict_meta(mock_send):
    n = TelegramNotifier("t", "c")
    n.notify_signal(
        "TQQQ", 100.0, 99.5, 101.5, 3.0,
        ict_meta={"killzone": None, "filters_active": ["killzone"]},
    )
    text = _captured_send_text(mock_send)
    # No KZ line when killzone is None, but filters present
    assert "KZ:" not in text
    assert "filters:killzone" in text
