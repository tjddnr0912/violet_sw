"""Main loop must sleep on EVERY iteration, not just the error path.

Bug: in run() the `time.sleep(sleep_time)` lived inside the `except Exception`
block, so a normal (no-exception) tick re-entered `while True` with no sleep —
the loop busy-spun a full CPU core (~100%) whenever _tick() succeeded, which is
almost always. The loop body is extracted to `_loop_iteration()` so the sleep is
unconditional and the behavior is testable.
"""
import types

import pytest

import src.bot as botmod
from src.bot import BotState


def _make_bot():
    bot = botmod.CasperBot.__new__(botmod.CasperBot)
    bot.state = BotState.WAITING
    bot.notifier = types.SimpleNamespace(notify_error=lambda *a, **k: None)
    return bot


def test_loop_iteration_sleeps_on_normal_tick(monkeypatch):
    """THE fix: a successful tick must still sleep (was the busy-loop bug)."""
    bot = _make_bot()
    bot._tick = lambda: None                     # normal tick, no exception
    slept = []
    monkeypatch.setattr(botmod.time, "sleep", lambda s: slept.append(s))

    bot._loop_iteration()

    assert slept == [30]                         # idle 30s in non-position state


def test_loop_iteration_sleeps_shorter_when_position_open(monkeypatch):
    bot = _make_bot()
    bot.state = BotState.POSITION_OPEN
    bot._tick = lambda: None
    slept = []
    monkeypatch.setattr(botmod.time, "sleep", lambda s: slept.append(s))

    bot._loop_iteration()

    assert slept == [5]                          # tighter cadence while in a position


def test_loop_iteration_sleeps_after_tick_error(monkeypatch):
    """Error path still logs/notifies AND sleeps (regression guard)."""
    bot = _make_bot()
    notified = []
    bot.notifier = types.SimpleNamespace(notify_error=lambda m: notified.append(m))

    def boom():
        raise ValueError("boom")
    bot._tick = boom
    slept = []
    monkeypatch.setattr(botmod.time, "sleep", lambda s: slept.append(s))

    bot._loop_iteration()                        # must NOT raise

    assert slept == [30]
    assert len(notified) == 1


def test_loop_iteration_propagates_system_exit(monkeypatch):
    """SIGTERM/Ctrl-C: SystemExit/KeyboardInterrupt propagate for graceful shutdown."""
    bot = _make_bot()

    def boom():
        raise SystemExit(0)
    bot._tick = boom
    slept = []
    monkeypatch.setattr(botmod.time, "sleep", lambda s: slept.append(s))

    with pytest.raises(SystemExit):
        bot._loop_iteration()

    assert slept == []                           # no sleep on shutdown
