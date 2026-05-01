"""Telegram notification module.

Sends trade alerts, status updates, and daily summaries.
Send-only — no inbound command handling.

Critical trade messages (entry/exit/order failure) that fail to send
because of a *network* issue while a trade is in progress are queued
and re-sent sequentially after the trade closes. Other failures are
silently dropped — never retried mid-trade. Network errors themselves
are *not* surfaced as Telegram messages (would just be noise).
"""

import logging
import time
from typing import Optional

import requests

logger = logging.getLogger("casper")

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
NETWORK_EXC = (requests.ConnectionError, requests.Timeout)
QUEUE_FLUSH_DELAY_SEC = 0.5


class TelegramNotifier:
    """Telegram bot notifier with deferred-retry queue for critical messages."""

    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        self._queue: list[str] = []
        self._in_trade: bool = False
        if not self.enabled:
            logger.info("Telegram: Not configured (notifications disabled)")

    # ── Trade lifecycle ─────────────────────────────────────────────────

    def begin_trade(self) -> None:
        """Mark a trade as in-progress.

        Critical messages whose send fails with a network error during this
        window are queued for flush at end_trade() instead of being retried
        immediately (which could compete with KIS calls for socket time).
        """
        self._in_trade = True

    def end_trade(self) -> None:
        """Trade ended — sequentially flush any queued critical messages."""
        self._in_trade = False
        if not self._queue:
            return
        logger.info(f"Telegram: flushing {len(self._queue)} deferred critical message(s)")
        for msg in list(self._queue):
            self._try_send(msg)  # best-effort; ignore result
            time.sleep(QUEUE_FLUSH_DELAY_SEC)
        self._queue.clear()

    # ── Send primitives ─────────────────────────────────────────────────

    def send(self, message: str, *, critical: bool = False) -> bool:
        """Send a message.

        Args:
            message: HTML-formatted body.
            critical: Trade-related message that must reach the operator.
                If sending fails with a network error while in-trade, the
                message is queued for end_trade() flush. Non-critical
                messages are silently dropped on any failure.

        Returns:
            True on confirmed delivery.
        """
        if not self.enabled:
            return False
        ok, network_err = self._try_send(message)
        if ok:
            return True
        if network_err and critical and self._in_trade:
            self._queue.append(message)
        # Network errors do not produce any Telegram-side message (per spec).
        return False

    def _try_send(self, message: str) -> tuple[bool, bool]:
        """Attempt one send. Returns (success, was_network_error)."""
        try:
            url = TELEGRAM_API.format(token=self.bot_token)
            resp = requests.post(url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10)
            if resp.status_code == 200:
                return True, False
            logger.warning(f"Telegram: HTTP {resp.status_code}")
            return False, False
        except NETWORK_EXC as e:
            logger.warning(f"Telegram: network error: {e}")
            return False, True
        except Exception as e:
            logger.warning(f"Telegram: send failed: {e}")
            return False, False

    # ── High-level notifications ────────────────────────────────────────

    def notify_bot_started(self, mode: str, capital: float, history: dict) -> None:
        msg = (
            f"🤖 <b>BOT STARTED</b>\n"
            f"Mode: {mode.upper()}\n"
            f"Capital: ${capital:.2f}\n"
            f"History: {history.get('count', 0)}T  "
            f"WR {history.get('win_rate', 0):.1f}%  "
            f"PnL ${history.get('pnl', 0):+.2f}"
        )
        self.send(msg)

    def notify_bot_stopped(self, reason: str = "Graceful shutdown") -> None:
        self.send(f"🛑 <b>BOT STOPPED</b>\n{reason}")

    def notify_pre_market(self, vix: float, qqq_close: float, qqq_ma20: float,
                          trend: str, symbol: str) -> None:
        emoji = "📈" if trend == "BULL" else "📉"
        msg = (
            f"{emoji} <b>PRE-MARKET</b>\n"
            f"VIX: {vix:.1f}\n"
            f"QQQ: {qqq_close:.2f} vs MA20 {qqq_ma20:.2f}\n"
            f"Trend: {trend} → {symbol}"
        )
        self.send(msg)

    def notify_orb(self, symbol: str, orb_high: float, orb_low: float,
                   orb_range: float) -> None:
        msg = (
            f"📊 <b>ORB</b> {symbol}\n"
            f"H ${orb_high:.2f}  L ${orb_low:.2f}  Range ${orb_range:.2f}"
        )
        self.send(msg)

    def notify_signal(self, symbol: str, entry: float, stop: float,
                      target: float, rr_ratio: float) -> None:
        msg = (
            f"🎯 <b>SIGNAL</b> {symbol}\n"
            f"Entry ${entry:.2f}  SL ${stop:.2f}  TP ${target:.2f}\n"
            f"R:R 1:{rr_ratio:.0f}"
        )
        self.send(msg)

    def notify_entry(self, symbol: str, price: float, shares: int,
                     stop: float, target: float, risk: float,
                     rr_ratio: float = 3.0) -> None:
        """Trade entry — critical (queued on network failure during trade)."""
        msg = (
            f"🟢 <b>ENTRY</b> {symbol}\n"
            f"${price:.2f} × {shares}sh = ${price * shares:.2f}\n"
            f"SL ${stop:.2f}  TP ${target:.2f}\n"
            f"Risk ${risk:.2f}/sh  R:R 1:{rr_ratio:.0f}"
        )
        self.send(msg, critical=True)

    def notify_be_move(self, symbol: str, old_sl: float, new_sl: float) -> None:
        msg = (
            f"🟡 <b>BE MOVE</b> {symbol}\n"
            f"SL ${old_sl:.2f} → ${new_sl:.2f}"
        )
        self.send(msg)

    def notify_exit(self, symbol: str, entry: float, exit_price: float,
                    reason: str, net_pnl: float, result: str) -> None:
        """Trade exit — critical (queued on network failure during trade)."""
        emoji = {"WIN": "✅", "LOSS": "❌", "BE": "➖"}.get(result, "❓")
        msg = (
            f"{emoji} <b>EXIT</b> {symbol} ({reason})\n"
            f"${entry:.2f} → ${exit_price:.2f}\n"
            f"Net P&L ${net_pnl:+.2f}  ({result})"
        )
        self.send(msg, critical=True)

    def notify_order_failed(self, symbol: str, side: str, qty: int, reason: str) -> None:
        """Order failure — critical."""
        msg = (
            f"🚨 <b>ORDER FAILED</b>\n"
            f"{side.upper()} {symbol} × {qty}\n"
            f"{reason}"
        )
        self.send(msg, critical=True)

    def notify_skip(self, reason: str) -> None:
        self.send(f"⏭ <b>SKIP</b> {reason}")

    def notify_daily_summary(self, today_trade: Optional[dict],
                             cumulative: dict, capital: float) -> None:
        """End-of-day comprehensive summary."""
        lines = ["📋 <b>DAILY SUMMARY</b>"]
        if today_trade:
            r = today_trade.get("result", "?")
            emoji = {"WIN": "✅", "LOSS": "❌", "BE": "➖"}.get(r, "❓")
            lines.append(
                f"{emoji} Today: {today_trade.get('symbol', '?')} "
                f"{today_trade.get('reason', '?')}  "
                f"P&L ${today_trade.get('net', 0):+.2f}  R={today_trade.get('r', 0):+.2f}"
            )
        else:
            lines.append("No trade today")
        lines.append(
            f"Capital: ${capital:.2f}\n"
            f"Cum: {cumulative.get('total', 0)}T  "
            f"WR {cumulative.get('wr', 0):.1f}%  "
            f"PF {cumulative.get('pf', 0):.2f}  "
            f"PnL ${cumulative.get('pnl', 0):+.2f}"
        )
        self.send("\n".join(lines))

    # ── Errors ──────────────────────────────────────────────────────────

    def notify_error(self, error: str) -> None:
        """Notify a non-network error.

        The caller is expected to filter network-class errors out before
        calling — see _is_network_error_text() helper for callers that
        receive raw error strings.
        """
        if _is_network_error_text(error):
            return  # Per spec: never alert on network errors
        self.send(f"🚨 <b>ERROR</b>\n{error}")


def _is_network_error_text(text: str) -> bool:
    """Heuristic: does this error message describe a network-layer failure?"""
    s = text.lower()
    needles = (
        "timeout", "timed out",
        "connection", "connect ",
        "read timed",
        "network", "unreachable",
        "ssl", "remote disconnect", "incomplete read",
        "max retries exceeded", "name resolution", "getaddrinfo",
    )
    return any(n in s for n in needles)
