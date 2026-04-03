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
        stats = {"total_trades": 5, "win_rate": 60.0, "total_pnl": 100.0, "profit_factor": 2.5}
        self.n.notify_daily_summary(stats)
        mock_send.assert_called_once()

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_error(self, mock_send):
        self.n.notify_error("Something broke")
        mock_send.assert_called_once()

    @patch.object(TelegramNotifier, "send", return_value=True)
    def test_notify_status(self, mock_send):
        self.n.notify_status("BOT STARTED", "live mode")
        mock_send.assert_called_once()
