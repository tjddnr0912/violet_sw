"""Startup-banner sleeve-mode gating tests.

Bug fixed: the operator startup banner printed the legacy intraday-only
detail (Scan/FVG/R:R, ICT flags, KST trading window, Fine-tune ICT-trade
reminder) in BOTH sleeve modes, even though the banner itself says the
intraday ORB+FVG engine is "GATED OFF" in the default trend mode. The
detail now renders ONLY when sleeve_engine == "intraday"; trend mode shows
a live low-freq Trend status line instead.

Mirrors the _make_bot() construction used in tests/test_bot_advanced.py.
"""
import logging
from unittest.mock import patch

from src.bot import CasperBot

_ENV = {
    "kis_app_key": "", "kis_app_secret": "", "kis_account_no": "",
    "kis_account_product": "01", "kis_base_url": "",
    "telegram_bot_token": "", "telegram_chat_id": "",
    "trading_mode": "paper", "test_mode": False,
    "log_level": "WARNING", "timezone": "US/Eastern",
}


def _make_bot():
    with patch("src.bot.load_trades", return_value=[]):
        with patch("src.bot.load_env", return_value=_ENV):
            return CasperBot()


def _run_banner(sleeve_engine, extra_params=None):
    """Run run() far enough to emit the startup banner, capture casper logs.

    _tick is patched to raise KeyboardInterrupt so run() exits right after
    the banner; capital sync + telegram notifications + position-state save
    are patched to avoid any network / KIS / disk side effects.
    """
    bot = _make_bot()
    params = {"sleeve_engine": sleeve_engine}
    if extra_params:
        params.update(extra_params)
    bot.params = params

    records = []

    class _Cap(logging.Handler):
        def emit(self, rec):
            records.append(rec.getMessage())

    lg = logging.getLogger("casper")
    old_level = lg.level
    handler = _Cap()
    lg.addHandler(handler)
    lg.setLevel(logging.DEBUG)
    try:
        with patch.object(bot, "_tick", side_effect=KeyboardInterrupt()):
            with patch.object(bot, "_sync_capital", return_value=None):
                with patch.object(bot.notifier, "notify_bot_started", return_value=None):
                    with patch.object(bot.notifier, "notify_bot_stopped", return_value=None):
                        with patch.object(bot, "_save_position_state", return_value=None):
                            with patch("src.bot.time.sleep", return_value=None):
                                bot.run()
    except KeyboardInterrupt:
        pass
    finally:
        lg.removeHandler(handler)
        lg.setLevel(old_level)
    return "\n".join(records)


def test_trend_mode_hides_intraday_detail():
    """Trend mode must NOT print intraday-only lines describing a dormant engine."""
    text = _run_banner("trend")
    # Legacy intraday-only lines must be ABSENT.
    assert "ICT 매매" not in text
    assert "Fine-tune" not in text
    assert "매매 윈도우" not in text
    assert "Scan:" not in text
    # Trend status / sleeve label must be present.
    assert ("Trend 상태" in text) or ("Sleeve: TREND" in text)


def test_intraday_mode_keeps_legacy_detail():
    """Intraday mode is reversible: the legacy detail lines still appear."""
    # require_displacement=True makes the conditional "ICT :" line render a flag.
    text = _run_banner("intraday", {"entry": {"require_displacement": True}})
    assert "Sleeve: INTRADAY" in text
    assert "Fine-tune" in text
    assert "Scan:" in text
    assert "ICT :" in text
