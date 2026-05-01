#!/usr/bin/env python3
"""
Telegram notifier smoke test
============================
Sends one message per notify_* method through the real Telegram API.
Each message body is tagged [test i/N] so the recipient can match what
arrived against the terminal report and identify any silent drops.

Two non-send tests are included:
  - notify_error with network-class text (expected: NOT sent — filter)
  - begin_trade / end_trade lifecycle (expected: queue flush works)

Run:
    cd 014_casper && python scripts/test_telegram_messages.py
"""

import os
import sys
import time
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.config import load_env
from src.telegram.notifier import TelegramNotifier


# ── Tagged notifier wrapper ────────────────────────────────────────

class TaggedNotifier(TelegramNotifier):
    """Prepends [test i/N] to every send for traceability on the Telegram
    side. Tracks the most recent send result so test-runner can assert
    success/failure without modifying notify_* signatures."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tag: str = ""
        self._last_success: object = None  # None = send not called; bool = result

    def set_tag(self, tag: str) -> None:
        self._tag = tag
        self._last_success = None  # reset before each test

    def send(self, message: str, *, critical: bool = False) -> bool:
        if self._tag:
            message = f"[{self._tag}] {message}"
        ok = super().send(message, critical=critical)
        self._last_success = ok
        return ok


# ── Test registry ──────────────────────────────────────────────────

TESTS: list[tuple[str, callable]] = []


def test(name: str):
    def deco(fn):
        TESTS.append((name, fn))
        return fn
    return deco


# ── Live Telegram send tests (one message each) ────────────────────

@test("notify_bot_started")
def t_bot_started(n: TaggedNotifier) -> bool:
    n.notify_bot_started("paper", 500.00, {"count": 0, "win_rate": 0, "pnl": 0})
    return n._last_success is True


@test("notify_pre_market")
def t_pre_market(n: TaggedNotifier) -> bool:
    n.notify_pre_market(vix=18.0, qqq_close=664.45, qqq_ma20=633.57,
                        trend="BULL", symbol="TQQQ")
    return n._last_success is True


@test("notify_orb")
def t_orb(n: TaggedNotifier) -> bool:
    n.notify_orb("TQQQ", orb_high=62.89, orb_low=61.45, orb_range=1.45)
    return n._last_success is True


@test("notify_signal")
def t_signal(n: TaggedNotifier) -> bool:
    n.notify_signal("TQQQ", entry=61.01, stop=60.67, target=62.04, rr_ratio=3.0)
    return n._last_success is True


@test("notify_entry (critical)")
def t_entry(n: TaggedNotifier) -> bool:
    n.notify_entry("TQQQ", price=61.01, shares=50, stop=60.67,
                   target=62.04, risk=0.34, rr_ratio=3.0)
    return n._last_success is True


@test("notify_be_move")
def t_be_move(n: TaggedNotifier) -> bool:
    n.notify_be_move("TQQQ", old_sl=60.67, new_sl=61.31)
    return n._last_success is True


@test("notify_exit (critical)")
def t_exit(n: TaggedNotifier) -> bool:
    n.notify_exit("TQQQ", entry=61.01, exit_price=62.04,
                  reason="take_profit", net_pnl=22.96, result="WIN")
    return n._last_success is True


@test("notify_order_failed (critical)")
def t_order_failed(n: TaggedNotifier) -> bool:
    n.notify_order_failed("TQQQ", side="buy", qty=50,
                          reason="KIS rejected: 주문가능금액 초과 (smoke test)")
    return n._last_success is True


@test("notify_skip")
def t_skip(n: TaggedNotifier) -> bool:
    n.notify_skip("ORB too wide (smoke test)")
    return n._last_success is True


@test("notify_error (business — should send)")
def t_error_business(n: TaggedNotifier) -> bool:
    n.notify_error("KIS rejected order: invalid symbol (smoke test)")
    return n._last_success is True


@test("notify_daily_summary")
def t_daily_summary(n: TaggedNotifier) -> bool:
    today_trade = {"symbol": "TQQQ", "result": "WIN", "reason": "take_profit",
                   "net": 22.96, "r": 2.0}
    cumulative = {"total": 8, "wr": 87.5, "pf": 5.20, "pnl": 51.62}
    n.notify_daily_summary(today_trade, cumulative, capital=551.62)
    return n._last_success is True


@test("notify_bot_stopped")
def t_bot_stopped(n: TaggedNotifier) -> bool:
    n.notify_bot_stopped("Smoke test complete")
    return n._last_success is True


# ── Behavior tests (no live send expected) ─────────────────────────

@test("notify_error (network-class — must drop)")
def t_error_network_filter(n: TaggedNotifier) -> bool:
    """Spec: network-class errors must NEVER produce a Telegram message."""
    n.notify_error("HTTPSConnectionPool: Read timed out (read timeout=10)")
    # Expected: send was NOT called → _last_success stays None.
    return n._last_success is None


@test("queue flush (begin_trade → fail → end_trade)")
def t_queue_flush(n: TaggedNotifier) -> bool:
    """Simulate a network error during a trade — message must queue and
    flush at end_trade(). No live send expected for this test."""
    n.begin_trade()
    # Force _try_send to return (False, True) = simulated network failure
    with patch.object(n, "_try_send", return_value=(False, True)):
        n.send("(internal queue test)", critical=True)
    queued_ok = len(n._queue) == 1
    # end_trade flushes — _try_send patched away by now, so the flush goes
    # through the real code path (which would normally try to send to TG).
    # We patch again to a no-op to keep the test silent on Telegram.
    with patch.object(n, "_try_send", return_value=(True, False)):
        n.end_trade()
    flushed_ok = len(n._queue) == 0 and not n._in_trade
    return queued_ok and flushed_ok


# ── Runner ─────────────────────────────────────────────────────────

DELAY_SEC = 1.0  # avoid Telegram per-chat rate limit


def main() -> int:
    env = load_env()
    token = env.get("telegram_bot_token", "")
    chat = env.get("telegram_chat_id", "")
    if not token or not chat:
        print("ERROR: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env")
        return 2

    n = TaggedNotifier(token, chat)
    if not n.enabled:
        print("ERROR: notifier disabled — credentials rejected")
        return 2

    total = len(TESTS)
    failures: list[str] = []

    # Suppress notifier's internal logger noise on stderr during smoke test
    import logging
    logging.getLogger("casper").setLevel(logging.ERROR)

    print(f"Running {total} Telegram notifier tests...\n")

    # Heads-up message so the recipient knows the next N messages are tests
    n.set_tag("smoke 0/0")
    n.send("🧪 <b>SMOKE TEST START</b>\n"
           f"Sending {total} test messages…")
    time.sleep(DELAY_SEC)

    for i, (name, fn) in enumerate(TESTS, start=1):
        tag = f"test {i}/{total}"
        n.set_tag(tag)
        try:
            ok = bool(fn(n))
        except Exception as e:
            ok = False
            err = f"  exception: {e}"
        else:
            err = ""
        status = "PASS" if ok else "FAIL"
        dots = "." * max(1, 40 - len(name))
        print(f"  [{i:2d}/{total}] {name} {dots} {status}{err}")
        if not ok:
            failures.append(f"{i}/{total} {name}")
        time.sleep(DELAY_SEC)

    n.set_tag("smoke done")
    if failures:
        body = ("⚠️ <b>SMOKE TEST DONE</b>\n"
                f"{total - len(failures)}/{total} passed\n"
                "Failures:\n  " + "\n  ".join(failures))
    else:
        body = ("✅ <b>SMOKE TEST DONE</b>\n"
                f"All {total}/{total} tests passed.")
    n.send(body)

    print()
    print(f"Result: {total - len(failures)}/{total} passed")
    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
