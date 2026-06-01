"""RTH-retry for GEM/trend auto rebalances deferred by the ET-00:00 daily tick.

Bug: the daily multi-bucket tick fires on day-change (ET 00:00 = KST 13:00),
when the US market is closed. `_maybe_run_gem`/`_maybe_run_trend` defer
execution in that case, but — unlike the initial seed (`_seed_pending`) —
nothing retried them during RTH. A continuously-running bot therefore never
executed the monthly GEM/trend rebalance.

Fix contract: `_gem_pending` / `_trend_pending` are True iff an *auto*
rebalance is still due. They are armed on a market-closed defer and on
construction (restart robustness), and disarmed once execution makes the
scheduler stop returning "due". `_tick` retries the pending sleeve(s) the
moment `is_market_open()` becomes True.
"""
import types
from datetime import date, datetime

import src.bot as botmod
from src.core.trend import TrendSignal, TrendState
from src.core.gem import GemState


# ── trend helpers ──────────────────────────────────────────────────────────

def _make_trend_bot(monkeypatch, *, run, market_open, mode="auto",
                    execute_clears=True):
    """Minimal bot exercising _maybe_run_trend.

    execute_clears: when True the stubbed execute "succeeds" (scheduler stops
    reporting due afterwards, like a real state save); when False it simulates
    a partial failure (still due → pending must stay armed).
    """
    bot = botmod.CasperBot.__new__(botmod.CasperBot)
    bot.params = {"trend": {"mode": mode}}
    bot.env = {}
    bot._trend_state = TrendState()
    bot._trend_pending = None  # sentinel: impl must set this explicitly
    bot.notifier = types.SimpleNamespace(notify_trend_signal=lambda *a, **k: None)

    sched = {"run": run}
    sd = date(2026, 5, 29)
    monkeypatch.setattr(botmod.trend, "should_run_trend",
                        lambda state=None: (sched["run"], sd if sched["run"] else None))
    monkeypatch.setattr(botmod.trend, "compute_trend_signal",
                        lambda params=None: TrendSignal("2026-05-29", "TQQQ", 1.0,
                                                        True, 0.40, "t", {}))
    monkeypatch.setattr(botmod.time_utils, "is_market_open", lambda: market_open)

    calls = []

    def fake_exec(*a, **k):
        calls.append(a)
        if execute_clears:
            sched["run"] = False  # execution made the rebalance no longer due
    bot._execute_trend_rebalance = fake_exec
    return bot, calls


def test_trend_defer_arms_pending_when_market_closed(monkeypatch):
    bot, calls = _make_trend_bot(monkeypatch, run=True, market_open=False)
    bot._maybe_run_trend([], 4000.0, {}, "auto")
    assert calls == []                  # did not trade while market closed
    assert bot._trend_pending is True   # armed for the RTH retry


def test_trend_execute_disarms_pending_when_market_open(monkeypatch):
    bot, calls = _make_trend_bot(monkeypatch, run=True, market_open=True)
    bot._maybe_run_trend([], 4000.0, {}, "auto")
    assert len(calls) == 1              # executed
    assert bot._trend_pending is False  # no longer due → disarmed


def test_trend_partial_failure_keeps_pending(monkeypatch):
    bot, calls = _make_trend_bot(monkeypatch, run=True, market_open=True,
                                 execute_clears=False)
    bot._maybe_run_trend([], 4000.0, {}, "auto")
    assert len(calls) == 1              # attempted
    assert bot._trend_pending is True   # still due → keep retrying


def test_trend_alert_mode_does_not_arm(monkeypatch):
    bot, calls = _make_trend_bot(monkeypatch, run=True, market_open=False,
                                 mode="alert")
    bot._maybe_run_trend([], 4000.0, {}, "alert")
    assert calls == []
    assert bot._trend_pending is False


def test_trend_not_due_disarms(monkeypatch):
    bot, calls = _make_trend_bot(monkeypatch, run=False, market_open=True)
    bot._maybe_run_trend([], 4000.0, {}, "auto")
    assert calls == []
    assert bot._trend_pending is False


# ── gem helpers ────────────────────────────────────────────────────────────

def _make_gem_bot(monkeypatch, *, run, market_open, mode="auto"):
    bot = botmod.CasperBot.__new__(botmod.CasperBot)
    bot.params = {}
    bot.env = {}
    bot._gem_state = GemState()
    bot._gem_pending = None
    bot.notifier = types.SimpleNamespace(notify_gem_signal=lambda *a, **k: None)

    sched = {"run": run}
    sd = date(2026, 5, 29)
    monkeypatch.setattr(botmod, "should_run_gem",
                        lambda state=None: (sched["run"], sd if sched["run"] else None))
    monkeypatch.setattr(botmod, "compute_gem_signal",
                        lambda: types.SimpleNamespace(
                            signal_date="2026-05-29", target="VEU",
                            us_ret=0.0, exus_ret=0.0, bill_ret=0.0, reason="t"))
    monkeypatch.setattr(botmod.time_utils, "is_market_open", lambda: market_open)

    calls = []

    def fake_exec(*a, **k):
        calls.append(a)
        sched["run"] = False
    bot._execute_gem_rotation = fake_exec
    return bot, calls


def test_gem_defer_arms_pending_when_market_closed(monkeypatch):
    bot, calls = _make_gem_bot(monkeypatch, run=True, market_open=False)
    bot._maybe_run_gem([], 4000.0, {}, "auto")
    assert calls == []
    assert bot._gem_pending is True


def test_gem_execute_disarms_pending_when_market_open(monkeypatch):
    bot, calls = _make_gem_bot(monkeypatch, run=True, market_open=True)
    bot._maybe_run_gem([], 4000.0, {}, "auto")
    assert len(calls) == 1
    assert bot._gem_pending is False


# ── retry plumbing ───────────────────────────────────────────────────────────

def test_retry_deferred_rebalance_runs_only_pending_trend(monkeypatch):
    bot = botmod.CasperBot.__new__(botmod.CasperBot)
    bot.env = {"trend_mode": "auto", "gem_mode": "auto"}
    bot.params = {}
    bot._gem_pending = False
    bot._trend_pending = True
    bot._portfolio_state = None
    bot._fetch_full_portfolio_snapshot = lambda: (4000.0, {})
    monkeypatch.setattr(botmod, "evaluate_portfolio",
                        lambda total, holdings, state=None: ([], {}))
    seen = []
    bot._maybe_run_gem = lambda *a, **k: seen.append("gem")
    bot._maybe_run_trend = lambda *a, **k: seen.append("trend")

    bot._retry_deferred_rebalance()
    assert seen == ["trend"]            # gem not pending → skipped


def test_tick_triggers_retry_when_pending_and_market_open(monkeypatch):
    bot = botmod.CasperBot.__new__(botmod.CasperBot)
    bot.params = {"sleeve_engine": "trend"}   # _intraday_enabled() → False
    bot.today_date = "2026-06-01"
    bot._seed_pending = False
    bot._gem_pending = False
    bot._trend_pending = True
    monkeypatch.setattr(botmod.time_utils, "now_et",
                        lambda: datetime(2026, 6, 1, 10, 0))
    monkeypatch.setattr(botmod.time_utils, "is_market_open", lambda: True)
    fired = []
    bot._retry_deferred_rebalance = lambda: fired.append(True)

    bot._tick()
    assert fired == [True]


def test_tick_skips_retry_when_market_closed(monkeypatch):
    bot = botmod.CasperBot.__new__(botmod.CasperBot)
    bot.params = {"sleeve_engine": "trend"}
    bot.today_date = "2026-06-01"
    bot._seed_pending = False
    bot._gem_pending = True
    bot._trend_pending = True
    monkeypatch.setattr(botmod.time_utils, "now_et",
                        lambda: datetime(2026, 6, 1, 2, 0))
    monkeypatch.setattr(botmod.time_utils, "is_market_open", lambda: False)
    fired = []
    bot._retry_deferred_rebalance = lambda: fired.append(True)

    bot._tick()
    assert fired == []                  # closed → no retry
