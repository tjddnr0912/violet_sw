"""Telegram notification module.

Sends trade alerts, daily summaries, and error notifications.
Silently skips if token/chat_id not configured.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger("casper")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramNotifier:
    """Telegram bot notifier."""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        if not self.enabled:
            logger.info("Telegram: Not configured (notifications disabled)")

    def send(self, message: str) -> bool:
        """Send a message. Returns True on success."""
        if not self.enabled:
            return False
        try:
            url = TELEGRAM_API.format(token=self.bot_token)
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
            if resp.status_code == 200:
                return True
            logger.warning(f"Telegram: HTTP {resp.status_code}")
            return False
        except Exception as e:
            logger.warning(f"Telegram: Send failed: {e}")
            return False

    def notify_entry(self, symbol: str, price: float, shares: int,
                     stop: float, target: float, risk: float) -> None:
        """Notify trade entry."""
        msg = (
            f"<b>ENTRY</b> {symbol}\n"
            f"Price: ${price:.2f} x {shares}shares\n"
            f"Stop: ${stop:.2f} | Target: ${target:.2f}\n"
            f"Risk: ${risk:.2f}/share (R:R 1:2)"
        )
        self.send(msg)

    def notify_exit(self, symbol: str, entry: float, exit_price: float,
                    reason: str, net_pnl: float, result: str) -> None:
        """Notify trade exit."""
        emoji = {"WIN": "✅", "LOSS": "❌", "BE": "➖"}.get(result, "❓")
        msg = (
            f"{emoji} <b>EXIT</b> {symbol} ({reason})\n"
            f"Entry: ${entry:.2f} → Exit: ${exit_price:.2f}\n"
            f"P&L: ${net_pnl:+.2f} ({result})"
        )
        self.send(msg)

    def notify_skip(self, reason: str) -> None:
        """Notify trade skip."""
        self.send(f"⏭ <b>SKIP</b> {reason}")

    def notify_daily_summary(self, stats: dict) -> None:
        """Send daily summary."""
        msg = (
            f"📊 <b>Daily Summary</b>\n"
            f"Trades: {stats.get('total_trades', 0)} | "
            f"Win Rate: {stats.get('win_rate', 0):.1f}%\n"
            f"Total P&L: ${stats.get('total_pnl', 0):+.2f} | "
            f"PF: {stats.get('profit_factor', 0):.2f}"
        )
        self.send(msg)

    def notify_error(self, error: str) -> None:
        """Notify error."""
        self.send(f"🚨 <b>ERROR</b>\n{error}")

    def notify_status(self, state: str, detail: str = "") -> None:
        """Notify bot status change."""
        msg = f"🤖 <b>{state}</b>"
        if detail:
            msg += f"\n{detail}"
        self.send(msg)
