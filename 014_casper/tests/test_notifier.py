"""Tests for Telegram notifier module."""

import pytest
from unittest.mock import patch, MagicMock

from src.telegram.notifier import TelegramNotifier


class TestNotifierInit:
    def test_disabled_when_no_credentials(self):
        n = TelegramNotifier()
        assert n.enabled is False

    def test_disabled_when_empty_strings(self):
        n = TelegramNotifier("", "")
        assert n.enabled is False

    def test_enabled_with_credentials(self):
        n = TelegramNotifier("bot_token", "chat_id")
        assert n.enabled is True


class TestSend:
    def test_disabled_returns_false(self):
        n = TelegramNotifier()
        assert n.send("test") is False

    @patch("src.telegram.notifier.requests.post")
    def test_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        n = TelegramNotifier("token", "chat")
        assert n.send("hello") is True
        mock_post.assert_called_once()

    @patch("src.telegram.notifier.requests.post")
    def test_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_post.return_value = mock_resp

        n = TelegramNotifier("token", "chat")
        assert n.send("hello") is False

    @patch("src.telegram.notifier.requests.post")
    def test_network_error(self, mock_post):
        mock_post.side_effect = Exception("Connection timeout")
        n = TelegramNotifier("token", "chat")
        assert n.send("hello") is False


class TestNotifyMethods:
    """Verify notify methods don't crash and call send."""

    def setup_method(self):
        self.n = TelegramNotifier("token", "chat")

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_entry(self, mock_send):
        self.n.notify_entry("TQQQ", 55.0, 10, 53.0, 59.0, 2.0)
        mock_send.assert_called_once()
        assert "TQQQ" in mock_send.call_args[0][0]

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_exit(self, mock_send):
        self.n.notify_exit("TQQQ", 55.0, 59.0, "take_profit", 40.0, "WIN")
        mock_send.assert_called_once()
        assert "WIN" in mock_send.call_args[0][0] or "✅" in mock_send.call_args[0][0]

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_skip(self, mock_send):
        self.n.notify_skip("VIX too high")
        mock_send.assert_called_once()

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_daily_summary(self, mock_send):
        today = {"symbol": "TQQQ", "result": "WIN", "reason": "take_profit",
                 "net": 8.4, "r": 1.95}
        cumulative = {"total": 5, "wr": 60.0, "pf": 2.5, "pnl": 100.0}
        self.n.notify_daily_summary(today, cumulative, capital=580.42)
        mock_send.assert_called_once()

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_error(self, mock_send):
        self.n.notify_error("Something broke")
        mock_send.assert_called_once()

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_bot_started(self, mock_send):
        self.n.notify_bot_started(
            "live", 3128.22,
            {"count": 7, "win_rate": 85.7, "pnl": 28.66},
        )
        mock_send.assert_called_once()

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_bot_stopped(self, mock_send):
        self.n.notify_bot_stopped("Graceful shutdown")
        mock_send.assert_called_once()


class TestNetworkErrorFilter:
    """notify_error must drop network-class errors silently per spec."""

    def setup_method(self):
        self.n = TelegramNotifier("token", "chat")

    @patch.object(TelegramNotifier, "send")
    def test_drops_timeout(self, mock_send):
        self.n.notify_error("HTTPSConnectionPool: Read timed out (read timeout=10)")
        mock_send.assert_not_called()

    @patch.object(TelegramNotifier, "send")
    def test_drops_connection_error(self, mock_send):
        self.n.notify_error("ConnectionError: Max retries exceeded with url")
        mock_send.assert_not_called()

    @patch.object(TelegramNotifier, "send")
    def test_passes_business_error(self, mock_send):
        self.n.notify_error("KIS rejected: 주문가능금액 초과")
        mock_send.assert_called_once()


class TestCriticalQueue:
    """Critical messages with network errors during a trade are deferred."""

    def setup_method(self):
        self.n = TelegramNotifier("token", "chat")

    @patch.object(TelegramNotifier, "_try_send")
    def test_critical_network_error_during_trade_queues(self, mock_try):
        # Simulate a network error
        mock_try.return_value = (False, True)
        self.n.begin_trade()
        self.n.send("ENTRY message", critical=True)
        assert len(self.n._queue) == 1

    @patch.object(TelegramNotifier, "_try_send")
    def test_non_critical_network_error_drops_silently(self, mock_try):
        mock_try.return_value = (False, True)
        self.n.begin_trade()
        self.n.send("Pre-market info")  # not critical
        assert len(self.n._queue) == 0

    @patch.object(TelegramNotifier, "_try_send")
    def test_critical_outside_trade_does_not_queue(self, mock_try):
        mock_try.return_value = (False, True)
        # No begin_trade — _in_trade=False
        self.n.send("ENTRY", critical=True)
        assert len(self.n._queue) == 0

    @patch.object(TelegramNotifier, "_try_send")
    def test_end_trade_flushes_queue(self, mock_try):
        mock_try.return_value = (False, True)  # all sends fail
        self.n.begin_trade()
        self.n.send("msg1", critical=True)
        self.n.send("msg2", critical=True)
        assert len(self.n._queue) == 2
        # End trade — flush attempts (all fail in mock, but queue clears)
        self.n.end_trade()
        assert len(self.n._queue) == 0
        # _try_send called once for each queued message


class TestTrendNotifications:
    """Trend sleeve telegram notifications (mirror of the GEM methods)."""

    def setup_method(self):
        self.n = TelegramNotifier("token", "chat")

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_trend_signal(self, mock_send):
        self.n.notify_trend_signal(
            signal_date="2026-05-29", target="TQQQ", exposure=0.6,
            regime=True, realized_vol=0.66, reason="QQQ>SMA200", mode="auto",
        )
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]
        assert "TQQQ" in msg
        assert "60" in msg  # exposure 0.6 rendered as percent

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_trend_executed(self, mock_send):
        self.n.notify_trend_executed(
            action="BUY", symbol="TQQQ", qty=11, price=85.0, exposure=0.6,
        )
        mock_send.assert_called_once()
        msg = mock_send.call_args[0][0]
        assert "TQQQ" in msg
        assert "11" in msg
