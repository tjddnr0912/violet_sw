# Casper Low-Freq TQQQ Vol-Target Trend Sleeve — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 20% "Casper" bucket's intraday ORB+FVG engine with a low-frequency monthly "TQQQ Vol-Target 40%" trend sleeve (QQQ>200d SMA gate, exposure = min(1, 0.40/realized-vol)), keeping tier weights unchanged and preserving the old intraday code behind a config flag.

**Architecture:** Mirror the proven GEM 3-part pattern — a pure-logic module (`src/core/trend.py`) computes the signal with no I/O, the bot wires it into the daily multi-bucket tick (`_maybe_run_trend` + `_execute_trend_rebalance`), and a month-end+grace scheduler (`should_run_trend`) controls cadence. The `portfolio.py` tier table renames the `casper` bucket key to `trend`. A `config.sleeve_engine` flag (`"trend"` default, `"intraday"` = old Casper) gates the intraday state machine.

**Tech Stack:** Python 3.14, pandas, yfinance (daily, auto_adjust), pytest. KIS order/balance via existing `src/api`. Cost/whole-share semantics already validated by `scripts/strategy_zoo_backtest.py`.

**Spec:** `docs/superpowers/specs/2026-05-30-casper-lowfreq-trend-design.md`

---

### Task 1: `trend.py` — indicators + `compute_trend_signal` (pure logic)

**Files:**
- Create: `src/core/trend.py`
- Test: `tests/test_trend.py`

Design note: `compute_trend_signal` accepts an optional injected `data` dict `{symbol: DataFrame}` so unit/golden tests run offline and deterministically. When `data is None`, it downloads via yfinance (mirrors `gem.py`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trend.py
import math
import numpy as np
import pandas as pd
import pytest
from datetime import date
from src.core import trend


def _mk(prices, start="2024-01-01"):
    idx = pd.bdate_range(start=start, periods=len(prices))
    return pd.DataFrame({"Close": prices}, index=idx)


def _trend_data(qqq_prices, tqqq_prices):
    return {"QQQ": _mk(qqq_prices), "TQQQ": _mk(tqqq_prices)}


PARAMS = {"signal_symbol": "QQQ", "sma_period": 200, "asset": "TQQQ",
          "safe_asset": "BIL", "target_vol": 0.40, "vol_lookback": 20}


def test_regime_off_returns_safe_asset():
    # QQQ in a clear downtrend → last close below SMA200 → BIL, exposure 0.
    qqq = list(np.linspace(500, 300, 260))           # falling
    tqqq = list(np.linspace(80, 40, 260))
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data=_trend_data(qqq, tqqq))
    assert sig.regime is False
    assert sig.target_symbol == "BIL"
    assert sig.exposure == 0.0


def test_regime_on_returns_tqqq_with_capped_exposure():
    # QQQ uptrend → above SMA200. Low, steady vol → exposure caps at 1.0.
    qqq = list(np.linspace(300, 600, 260))           # rising
    tqqq = list(np.linspace(40, 120, 260))           # smooth rise = low daily vol
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data=_trend_data(qqq, tqqq))
    assert sig.regime is True
    assert sig.target_symbol == "TQQQ"
    assert 0.0 < sig.exposure <= 1.0


def test_high_vol_reduces_exposure_below_cap():
    # QQQ uptrend but TQQQ very choppy → realized vol high → exposure < 1.0.
    qqq = list(np.linspace(300, 600, 260))
    rng = np.random.default_rng(0)
    tqqq = list(100 + np.cumsum(rng.normal(0, 6, 260)))  # high-vol path
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data=_trend_data(qqq, tqqq))
    if sig.regime:               # uptrend may or may not hold given noise
        assert sig.exposure < 1.0


def test_missing_data_falls_back_to_safe_asset():
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data={"QQQ": _mk([1, 2, 3]), "TQQQ": _mk([1, 2])})
    assert sig.target_symbol == "BIL"
    assert sig.exposure == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_trend.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.core.trend'` (or `AttributeError`).

- [ ] **Step 3: Write minimal implementation**

```python
# src/core/trend.py
"""Low-frequency TQQQ Vol-Target trend sleeve — monthly signal.

Algorithm (matches scripts/strategy_zoo_backtest.make_voltarget_lev):
  regime = QQQ.close > SMA(QQQ.close, sma_period)
  if not regime:  target = safe_asset (BIL), exposure = 0
  else:           realized_vol = std(TQQQ daily returns, vol_lookback) * sqrt(252)
                  exposure = min(1.0, target_vol / realized_vol)
                  target = asset (TQQQ) at `exposure` of the sleeve, rest in safe_asset

Pure logic: no KIS calls. The bot wires compute_trend_signal() into kis_order.
State (last signal date + held asset + exposure) lives in data/trend_state.json.
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from src.utils import time_utils

logger = logging.getLogger("casper")

TREND_STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "trend_state.json"
)
GRACE_TRADING_DAYS = 3
TRADING_DAYS = 252

DEFAULT_PARAMS = {
    "signal_symbol": "QQQ", "sma_period": 200, "asset": "TQQQ",
    "safe_asset": "BIL", "target_vol": 0.40, "vol_lookback": 20,
}


@dataclass
class TrendSignal:
    signal_date: str
    target_symbol: str       # "TQQQ" | "BIL"
    exposure: float          # 0.0 .. 1.0 (fraction of the sleeve in `asset`)
    regime: bool             # QQQ > SMA200
    realized_vol: float      # annualized
    reason: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _download_daily(symbol: str, today: date, lookback_days: int) -> Optional[pd.DataFrame]:
    """yfinance daily Close frame (auto_adjust). Returns None on failure."""
    try:
        import yfinance as yf
    except Exception as e:                       # pragma: no cover
        logger.error(f"trend: yfinance import failed: {e}")
        return None
    start = today - timedelta(days=lookback_days)
    try:
        df = yf.download(symbol, start=start.isoformat(),
                         end=(today + timedelta(days=1)).isoformat(),
                         auto_adjust=True, progress=False, threads=False)
    except Exception as e:
        logger.error(f"trend: yfinance download {symbol} failed: {e}")
        return None
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Close"]]


def compute_trend_signal(today: Optional[date] = None,
                         params: Optional[dict] = None,
                         data: Optional[dict] = None) -> TrendSignal:
    """Compute the trend signal as of `today`'s close.

    `data` (optional): {symbol: DataFrame with 'Close'} for offline/testing.
    When None, downloads QQQ + TQQQ daily history via yfinance.
    Any data shortfall biases to the safe asset (defensive, like gem.py).
    """
    if today is None:
        today = time_utils.today_et()
    p = {**DEFAULT_PARAMS, **(params or {})}
    sig_sym, asset, safe = p["signal_symbol"], p["asset"], p["safe_asset"]
    sma_n, vol_n, tvol = int(p["sma_period"]), int(p["vol_lookback"]), float(p["target_vol"])

    def _close(sym: str) -> Optional[pd.Series]:
        if data is not None:
            df = data.get(sym)
        else:
            df = _download_daily(sym, today, lookback_days=int(sma_n * 1.8) + 60)
        if df is None or "Close" not in df.columns:
            return None
        s = df["Close"].dropna()
        return s if len(s) else None

    qqq = _close(sig_sym)
    tqqq = _close(asset)

    def _safe(reason: str) -> TrendSignal:
        return TrendSignal(today.isoformat(), safe, 0.0, False, float("nan"), reason, p)

    if qqq is None or len(qqq) < sma_n + 1:
        return _safe(f"insufficient {sig_sym} data → {safe}")
    if tqqq is None or len(tqqq) < vol_n + 1:
        return _safe(f"insufficient {asset} data → {safe}")

    sma = qqq.rolling(sma_n).mean().iloc[-1]
    last = float(qqq.iloc[-1])
    regime = bool(last > float(sma))
    if not regime:
        return TrendSignal(today.isoformat(), safe, 0.0, False, float("nan"),
                           f"{sig_sym} {last:.2f} <= SMA{sma_n} {float(sma):.2f} → {safe}", p)

    rv = float(tqqq.pct_change().rolling(vol_n).std().iloc[-1]) * math.sqrt(TRADING_DAYS)
    if not (rv > 0):
        return _safe(f"{asset} realized_vol unavailable → {safe}")
    exposure = min(1.0, tvol / rv)
    return TrendSignal(
        today.isoformat(), asset, round(exposure, 4), True, round(rv, 4),
        f"{sig_sym} > SMA{sma_n}; {asset} vol {rv:.2f} → exposure {exposure:.2f}", p,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_trend.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/core/trend.py tests/test_trend.py
git commit -m "Add trend.compute_trend_signal — TQQQ vol-target signal (pure logic)"
```

---

### Task 2: `trend.py` — `TrendState` + `should_run_trend` scheduler

**Files:**
- Modify: `src/core/trend.py`
- Test: `tests/test_trend.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_trend.py
from datetime import date as _date
import src.utils.time_utils as tu


def test_state_roundtrip(tmp_path):
    p = tmp_path / "trend_state.json"
    st = trend.TrendState(last_signal_date="2026-05-29",
                          current_holding="TQQQ", last_exposure=0.6)
    st.save(str(p))
    st2 = trend.TrendState.load(str(p))
    assert st2.current_holding == "TQQQ"
    assert st2.last_exposure == 0.6


def test_should_run_on_last_trading_day_of_month(monkeypatch):
    d = _date(2026, 5, 29)  # assume a month-end trading day
    monkeypatch.setattr(tu, "is_last_trading_day_of_month", lambda x: x == d)
    monkeypatch.setattr(tu, "was_last_trading_day_of_month_within",
                        lambda days_back, today: None)
    run, sd = trend.should_run_trend(today=d, state=trend.TrendState())
    assert run is True and sd == d


def test_should_not_run_when_already_done(monkeypatch):
    d = _date(2026, 5, 29)
    monkeypatch.setattr(tu, "is_last_trading_day_of_month", lambda x: x == d)
    st = trend.TrendState(last_signal_date=d.isoformat())
    run, sd = trend.should_run_trend(today=d, state=st)
    assert run is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_trend.py -q`
Expected: FAIL — `AttributeError: module 'src.core.trend' has no attribute 'TrendState'`.

- [ ] **Step 3: Write minimal implementation**

```python
# append to src/core/trend.py

@dataclass
class TrendState:
    last_signal_date: Optional[str] = None
    last_target: Optional[str] = None
    current_holding: Optional[str] = None
    last_exposure: float = 0.0

    @classmethod
    def load(cls, path: str = TREND_STATE_FILE) -> "TrendState":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r") as f:
                d = json.load(f)
            return cls(last_signal_date=d.get("last_signal_date"),
                       last_target=d.get("last_target"),
                       current_holding=d.get("current_holding"),
                       last_exposure=float(d.get("last_exposure", 0.0)))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"trend state load failed ({e}) — fresh")
            return cls()

    def save(self, path: str = TREND_STATE_FILE) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)


def should_run_trend(today: Optional[date] = None,
                     state: Optional[TrendState] = None) -> tuple[bool, Optional[date]]:
    """Month-end (+grace) rebalance schedule. Mirrors gem.should_run_gem."""
    if today is None:
        today = time_utils.today_et()
    if state is None:
        state = TrendState.load()
    if time_utils.is_last_trading_day_of_month(today):
        if state.last_signal_date == today.isoformat():
            return False, None
        return True, today
    missed = time_utils.was_last_trading_day_of_month_within(
        days_back=GRACE_TRADING_DAYS, today=today)
    if missed is None:
        return False, None
    if state.last_signal_date == missed.isoformat():
        return False, None
    return True, missed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_trend.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/core/trend.py tests/test_trend.py
git commit -m "Add TrendState + should_run_trend month-end scheduler"
```

---

### Task 3: Golden parity test — live signal matches the backtest harness

**Files:**
- Test: `tests/test_trend_parity.py`

Goal: prove `compute_trend_signal` reproduces `make_voltarget_lev`'s month-end decision on real cached data, so the live sleeve never silently drifts from the validated backtest.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trend_parity.py
import os, sys
import pandas as pd
import pytest
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
CACHE = os.path.join(SCRIPTS, "out", "zoo_data")

pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(CACHE, "TQQQ.parquet")),
    reason="requires cached zoo data (run scripts/strategy_zoo_backtest.py once)")


def _load(sym):
    df = pd.read_parquet(os.path.join(CACHE, f"{sym}.parquet"))
    df.index = pd.to_datetime(df.index)
    return df


def test_signal_matches_harness_on_month_ends():
    from src.core import trend
    qqq, tqqq = _load("QQQ"), _load("TQQQ")
    data_full = {"QQQ": qqq[["Close"]], "TQQQ": tqqq[["Close"]]}
    PARAMS = {"signal_symbol": "QQQ", "sma_period": 200, "asset": "TQQQ",
              "safe_asset": "BIL", "target_vol": 0.40, "vol_lookback": 20}
    # pick 6 month-end dates across 2018-2024
    idx = qqq.index
    me = idx.to_series().groupby([idx.year, idx.month]).max()
    sample = [d for d in me if 2018 <= d.year <= 2024][::12][:6]
    for d in sample:
        # feed only history up to and including d (no look-ahead)
        sub = {"QQQ": qqq.loc[:d, ["Close"]], "TQQQ": tqqq.loc[:d, ["Close"]]}
        sig = trend.compute_trend_signal(today=d.date(), params=PARAMS, data=sub)
        # harness logic, recomputed inline:
        sma = qqq["Close"].loc[:d].rolling(200).mean().iloc[-1]
        regime = qqq["Close"].loc[:d].iloc[-1] > sma
        assert sig.regime == bool(regime), f"{d}: regime mismatch"
        if regime:
            rv = tqqq["Close"].loc[:d].pct_change().rolling(20).std().iloc[-1] * (252 ** 0.5)
            assert abs(sig.exposure - min(1.0, 0.40 / rv)) < 1e-6, f"{d}: exposure mismatch"
        else:
            assert sig.target_symbol == "BIL"
```

- [ ] **Step 2: Run test to verify it fails / skips**

Run: `python3 -m pytest tests/test_trend_parity.py -q`
Expected: PASS if cached data present (Task 1 logic already matches the harness); if not present, SKIP. If it FAILS, the live formula diverged from the backtest — fix `compute_trend_signal` until it matches before continuing.

- [ ] **Step 3: Ensure cache exists, then run**

Run: `python3 scripts/strategy_zoo_backtest.py >/dev/null 2>&1; python3 -m pytest tests/test_trend_parity.py -q`
Expected: PASS (1 passed).

- [ ] **Step 4: Commit**

```bash
git add tests/test_trend_parity.py
git commit -m "Add golden parity test: live trend signal == backtest harness"
```

---

### Task 4: `portfolio.py` — rename `casper` bucket → `trend`

**Files:**
- Modify: `src/core/portfolio.py` (`tier_for_capital` 58-75, `BUCKET_DEFAULT_SYMBOL` 81-89, `_bucket_value` 273-306, `needs_rebalance` 360-368)
- Test: `tests/test_multi_bucket.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_multi_bucket.py
from src.core import portfolio as pf


def test_tier_uses_trend_not_casper():
    w = pf.tier_for_capital(4000)
    assert "trend" in w and "casper" not in w
    assert abs(w["trend"] - 0.20) < 1e-9
    w2 = pf.tier_for_capital(7000)
    assert "trend" in w2 and "casper" not in w2


def test_bucket_value_resolves_tqqq_or_bil():
    holdings = {"TQQQ": {"qty": 5, "value_usd": 400.0}}
    buckets, _ = pf.evaluate_portfolio(4000.0, holdings,
                                       state=pf.PortfolioState())
    trend_b = next(b for b in buckets if b.name == "trend")
    assert trend_b.current_symbol == "TQQQ"
    assert trend_b.current_value_usd == 400.0


def test_needs_rebalance_excludes_trend(monkeypatch):
    import src.utils.time_utils as tu
    monkeypatch.setattr(tu, "is_last_trading_day_of_quarter", lambda d: True)
    b = pf.Bucket(name="trend", target_weight=0.2, target_usd=800,
                  current_value_usd=1200)   # 50% drift
    assert pf.needs_rebalance([b], drift_threshold=0.10) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_multi_bucket.py -q -k "trend or tqqq"`
Expected: FAIL — `KeyError`/assertion: tier still has `casper`.

- [ ] **Step 3: Make the edits**

In `tier_for_capital()` replace every `"casper"` with `"trend"` (weights unchanged):
```python
    if total_usd < 5000:
        return {"spmo": 0.50, "gem": 0.30, "trend": 0.20}
    if total_usd < 10000:
        return {"spmo": 0.40, "mtum": 0.10, "qual": 0.10,
                "gem": 0.20, "trend": 0.20}
    return {"spmo": 0.30, "mtum": 0.10, "qual": 0.10,
            "clenow": 0.20, "tqqq_sma": 0.10,
            "gem": 0.15, "trend": 0.05}
```
In `BUCKET_DEFAULT_SYMBOL` remove the `"casper"` line and add:
```python
    "trend":    "TQQQ",      # alternates TQQQ / BIL (vol-target sleeve)
```
In `_bucket_value()` rename the `if name == "casper":` branch to `if name == "trend":` and change its symbol loop from `("TQQQ", "SQQQ")` to `("TQQQ", "BIL")`:
```python
        if name == "trend":
            for sym in ("TQQQ", "BIL"):
                h = holdings.get(sym, {})
                if h.get("qty", 0) > 0:
                    claimed_symbols.add(sym)
                    return float(h.get("value_usd", 0)), sym
            return 0.0, None
```
In `needs_rebalance()` change `if b.name in ("gem", "casper"):` to `if b.name in ("gem", "trend"):`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_multi_bucket.py -q`
Expected: PASS (existing tests + 3 new). If an existing test asserts `casper` membership, update it to `trend` (same weight).

- [ ] **Step 5: Commit**

```bash
git add src/core/portfolio.py tests/test_multi_bucket.py
git commit -m "Rename casper bucket -> trend (TQQQ/BIL vol-target sleeve)"
```

---

### Task 5: `config` — add `sleeve_engine` + `trend` block

**Files:**
- Modify: `config/strategy_params.json`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_config.py
from src.utils.config import load_strategy_params


def test_sleeve_engine_and_trend_params():
    p = load_strategy_params()
    assert p.get("sleeve_engine") in ("trend", "intraday")
    t = p.get("trend", {})
    assert t.get("asset") == "TQQQ"
    assert t.get("safe_asset") == "BIL"
    assert t.get("signal_symbol") == "QQQ"
    assert abs(float(t.get("target_vol")) - 0.40) < 1e-9
    assert int(t.get("sma_period")) == 200
    assert int(t.get("vol_lookback")) == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config.py -q -k sleeve`
Expected: FAIL — `sleeve_engine` / `trend` keys absent.

- [ ] **Step 3: Edit config**

Add to `config/strategy_params.json` (top level, after `"mode": {...}`):
```json
    "sleeve_engine": "trend",
    "trend": {
        "signal_symbol": "QQQ",
        "sma_period": 200,
        "asset": "TQQQ",
        "safe_asset": "BIL",
        "target_vol": 0.40,
        "vol_lookback": 20,
        "rebalance": "monthly",
        "mode": "auto"
    },
```
(Note: `load_strategy_params` caches — the test imports fresh per run, so no cache issue. If a `_config_cache` global persists across the suite, clear it in the test via `import src.utils.config as c; c._config_cache = None` before calling.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_config.py -q -k sleeve`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config/strategy_params.json tests/test_config.py
git commit -m "Add sleeve_engine flag + trend sleeve config block"
```

---

### Task 6: `notifier` — `notify_trend_signal` + `notify_trend_executed`

**Files:**
- Modify: `src/telegram/notifier.py` (after `notify_gem_executed`, ~546)
- Test: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_notifier.py
def test_notify_trend_signal_formats(monkeypatch):
    from src.telegram.notifier import TelegramNotifier
    sent = {}
    n = TelegramNotifier(token=None, chat_id=None)  # send-only, no-op transport
    monkeypatch.setattr(n, "_enqueue", lambda msg, **k: sent.setdefault("m", msg))
    n.notify_trend_signal("2026-05-29", "TQQQ", exposure=0.6, regime=True,
                          realized_vol=0.66, reason="QQQ>SMA200", mode="auto")
    assert "TQQQ" in sent["m"] and "60" in sent["m"].replace(".0", "")
```
(Adapt the transport stub to however `tests/test_notifier.py` already constructs a notifier; reuse its existing fixture/pattern rather than inventing one.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_notifier.py -q -k trend`
Expected: FAIL — `AttributeError: notify_trend_signal`.

- [ ] **Step 3: Implement (mirror `notify_gem_signal` 499-545)**

```python
    def notify_trend_signal(self, signal_date: str, target: str,
                            exposure: float, regime: bool,
                            realized_vol: float, reason: str,
                            mode: str = "auto") -> None:
        tag = "🔔 ALERT" if mode == "alert" else "🤖 AUTO"
        emoji = "📈" if target == "TQQQ" else "🛡️"
        msg = (
            f"{emoji} <b>Trend sleeve signal</b> ({tag})\n"
            f"날짜: {signal_date}\n"
            f"레짐: {'RISK-ON (QQQ>200d)' if regime else 'RISK-OFF'}\n"
            f"타깃: <b>{target}</b>  노출: {exposure*100:.0f}%\n"
            f"실현변동성: {realized_vol*100:.0f}%\n"
            f"사유: {reason}"
        )
        self._enqueue(msg)

    def notify_trend_executed(self, action: str, symbol: str,
                              qty: int, price: float, exposure: float) -> None:
        msg = (
            f"✅ <b>Trend 리밸런스</b>\n"
            f"{action} {symbol} × {qty} @ ${price:.2f}\n"
            f"sleeve 노출: {exposure*100:.0f}%"
        )
        self._enqueue(msg)
```
(If the notifier's internal send method is not named `_enqueue`, use the same method `notify_gem_signal` calls — match the existing code.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_notifier.py -q -k trend`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/telegram/notifier.py tests/test_notifier.py
git commit -m "Add trend sleeve telegram notifications"
```

---

### Task 7: bot wiring — `_maybe_run_trend` + `_execute_trend_rebalance`

**Files:**
- Modify: `src/bot.py` — import (`~59`), daily-tick caller (after `_maybe_run_gem(...)` ~2101), new methods after `_execute_gem_rotation` (~2400)
- Test: `tests/test_bot_advanced.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_bot_advanced.py
def test_execute_trend_rebalance_buys_tqqq(monkeypatch, tmp_path):
    """auto mode, RISK-ON, all cash -> buys whole-share TQQQ at exposure."""
    import src.bot as botmod
    from src.core.trend import TrendSignal
    bot = botmod.__new__(botmod.CasperBot)  # bypass __init__
    bot.params = {"order": {"buy_slippage_pct": 0.01},
                  "commission": {"rate_per_side": 0.0025}}
    bot._trend_state = __import__("src.core.trend", fromlist=["TrendState"]).TrendState()

    class FakeOrder:
        def __init__(s): s.calls = []
        def buy_market(s, sym, qty, exchange): s.calls.append(("buy", sym, qty)); return {"ok": True}
        def sell_market(s, sym, qty, exchange): s.calls.append(("sell", sym, qty)); return {"ok": True}
    class FakeClient:
        def get_us_price(s, sym, exchange): return {"price": 80.0}
        def get_us_balance(s): return {"available_cash": 800.0}
    bot.kis_order, bot.kis_client = FakeOrder(), FakeClient()

    class FakeNotifier:
        def notify_trend_executed(s, *a, **k): pass
        def notify_etf_rebalance(s, *a, **k): pass
    bot.notifier = FakeNotifier()

    sig = TrendSignal("2026-05-29", "TQQQ", exposure=1.0, regime=True,
                      realized_vol=0.40, reason="t", params={})
    monkeypatch.setattr(botmod.trend, "compute_trend_signal", lambda **k: sig)
    monkeypatch.setattr(botmod.time_utils, "is_market_open", lambda: True)

    # sleeve budget = total(4000) * 0.20 = 800 ; price 80 -> ~9 shares after cost
    bot._execute_trend_rebalance(sig, holdings={}, total=4000.0)
    assert any(c[0] == "buy" and c[1] == "TQQQ" for c in bot.kis_order.calls)
```
(Adjust import/fixture names to match how `tests/test_bot_advanced.py` already builds a bot — reuse that pattern; do not hand-roll if a fixture exists.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bot_advanced.py -q -k trend_rebalance`
Expected: FAIL — `AttributeError: _execute_trend_rebalance`.

- [ ] **Step 3: Implement (mirror `_maybe_run_gem` 2271-2313 + `_execute_gem_rotation` 2315-2400)**

Add import near line 59 (with the other `src.core` imports):
```python
from src.core import trend
```
Add `self._trend_state = trend.TrendState.load()` in `__init__` next to the GEM-state init.
In `_run_daily_multibucket_tick`, right after the `self._maybe_run_gem(...)` call (~2101):
```python
            trend_mode = self.params.get("trend", {}).get("mode", "auto")
            if self.params.get("sleeve_engine") == "trend":
                self._maybe_run_trend(buckets, total, holdings, trend_mode)
```
New methods after `_execute_gem_rotation`:
```python
    def _maybe_run_trend(self, buckets: list, total: float,
                         holdings: dict, mode: str) -> None:
        """Month-end trend-sleeve check. alert=notify only, auto=trade.
        Defers execution outside RTH (idempotent via last_signal_date)."""
        from src.core.trend import should_run_trend, compute_trend_signal
        run, signal_date = should_run_trend(state=self._trend_state)
        if not run or signal_date is None:
            return
        sig = compute_trend_signal(params=self.params.get("trend", {}))
        sig.signal_date = signal_date.isoformat()
        logger.info(f"Trend signal {sig.signal_date}: {sig.target_symbol} "
                    f"exposure={sig.exposure:.2f} regime={sig.regime} — {sig.reason}")
        self.notifier.notify_trend_signal(
            sig.signal_date, sig.target_symbol, sig.exposure, sig.regime,
            sig.realized_vol, sig.reason, mode=mode)
        if mode == "alert":
            return
        if not time_utils.is_market_open():
            logger.info("Trend auto: market closed — deferring to next RTH tick")
            return
        self._execute_trend_rebalance(sig, holdings, total)

    def _execute_trend_rebalance(self, sig, holdings: dict, total: float) -> None:
        """Reconcile the trend bucket to {TQQQ: exposure*sleeve, BIL: rest}.
        Whole-share, sell-then-buy. Sleeve size = total * tier weight['trend']."""
        weights = tier_for_capital(total)
        sleeve_w = weights.get("trend", 0.0)
        if sleeve_w <= 0:
            logger.info("Trend: weight=0 in current tier — skipping")
            return
        sleeve_usd = total * sleeve_w
        tqqq_usd = sig.exposure * sleeve_usd if sig.target_symbol == "TQQQ" else 0.0
        targets = {"TQQQ": tqqq_usd, "BIL": sleeve_usd - tqqq_usd}
        if not self.kis_order:
            logger.warning("Trend auto: kis_order unavailable — skipping")
            return
        buy_slip = self.params.get("order", {}).get("buy_slippage_pct", 0.01)
        comm = self.params.get("commission", {}).get("rate_per_side", 0.0025)

        # 1) Sell anything in TQQQ/BIL that exceeds its target (free cash first)
        for sym in ("TQQQ", "BIL"):
            held = holdings.get(sym, {})
            qty_held = int(held.get("qty", 0) or 0)
            if qty_held <= 0:
                continue
            px = self.kis_client.get_us_price(sym, exchange=exchange_for(sym)) or {}
            price = float(px.get("price", 0) or 0)
            if price <= 0:
                continue
            target_qty = int(targets[sym] / (price * (1 + buy_slip + comm)))
            if target_qty < qty_held:
                sell_qty = qty_held - target_qty
                if self.kis_order.sell_market(sym, sell_qty, exchange=exchange_for(sym)):
                    self.notifier.notify_etf_rebalance(
                        "sell", sym, sell_qty, price, "trend", "trend rebalance")
        time.sleep(2.0)
        # 2) Buy up to target for each (cash-constrained)
        bal = self.kis_client.get_us_balance() or {}
        cash = float(bal.get("available_cash", 0) or 0)
        for sym in ("TQQQ", "BIL"):
            if targets[sym] <= 0:
                continue
            held_qty = int(holdings.get(sym, {}).get("qty", 0) or 0)
            px = self.kis_client.get_us_price(sym, exchange=exchange_for(sym)) or {}
            price = float(px.get("price", 0) or 0)
            if price <= 0:
                continue
            eff = price * (1 + buy_slip + comm)
            want_qty = int(targets[sym] / eff)
            buy_qty = max(0, want_qty - held_qty)
            buy_qty = min(buy_qty, int(cash / eff))
            if buy_qty >= 1 and self.kis_order.buy_market(sym, buy_qty, exchange=exchange_for(sym)):
                cash -= buy_qty * eff
                self.notifier.notify_trend_executed("BUY", sym, buy_qty, price, sig.exposure)
        self._trend_state.last_signal_date = sig.signal_date
        self._trend_state.last_target = sig.target_symbol
        self._trend_state.current_holding = sig.target_symbol
        self._trend_state.last_exposure = sig.exposure
        self._trend_state.save()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_bot_advanced.py -q -k trend_rebalance`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot.py tests/test_bot_advanced.py
git commit -m "Wire trend sleeve into daily multibucket tick (_maybe_run_trend)"
```

---

### Task 8: bot main loop — gate intraday state machine on `sleeve_engine`

**Files:**
- Modify: `src/bot.py` — intraday entry. The state machine advances toward `ORB_FORMING`/`SCANNING` in the tick dispatcher (~744-760) and pre-market handler. Add a single early gate so `sleeve_engine != "intraday"` never enters ORB scanning.
- Test: `tests/test_bot_states.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_bot_states.py
def test_trend_engine_skips_intraday_scan(monkeypatch):
    """When sleeve_engine != 'intraday', the bot must not run ORB scanning."""
    import src.bot as botmod
    bot = botmod.__new__(botmod.CasperBot)
    bot.params = {"sleeve_engine": "trend"}
    assert bot._intraday_enabled() is False
    bot.params = {"sleeve_engine": "intraday"}
    assert bot._intraday_enabled() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_bot_states.py -q -k intraday_scan`
Expected: FAIL — `AttributeError: _intraday_enabled`.

- [ ] **Step 3: Implement the gate**

Add a small helper and consult it at the top of the intraday-advancing code paths:
```python
    def _intraday_enabled(self) -> bool:
        """The ORB+FVG intraday Casper engine runs only when explicitly selected.
        Default sleeve_engine='trend' runs the low-freq sleeve via the daily tick."""
        return self.params.get("sleeve_engine", "trend") == "intraday"
```
In the tick dispatcher where the state machine handles `PRE_MARKET`/`ORB_FORMING`/`SCANNING` (~744), wrap the intraday branch:
```python
        if not self._intraday_enabled():
            # Trend-sleeve mode: no intraday scanning. Daily multibucket tick
            # (which includes _maybe_run_trend) still runs on its own schedule.
            self.state = BotState.DONE_TODAY
            return
```
Place this guard before the `elif self.state == BotState.ORB_FORMING:` chain so the intraday path is skipped wholesale. The daily multibucket tick must remain reachable (it runs on its own scheduler call, not inside this intraday branch — verify it is invoked regardless of `BotState`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_bot_states.py -q -k intraday_scan`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bot.py tests/test_bot_states.py
git commit -m "Gate intraday ORB state machine behind sleeve_engine flag"
```

---

### Task 9: Guardrail docs (#3/#4) + CLAUDE.md update

**Files:**
- Modify: `config/strategy_params.json` (comment is not JSON-legal — add the policy to the spec/CLAUDE instead)
- Modify: `014_casper/CLAUDE.md` (핵심 정보 / 트러블슈팅)

- [ ] **Step 1: Add policy note to CLAUDE.md**

Append to the troubleshooting "함정" section:
```markdown
- **신규 고빈도 sleeve 추가 금지** → 0.25%/side에서 일일 매매는 비용=최종자산의 25~260%로 구조적 적자(증거: `docs/strategy/STRATEGY_ZOO_1000USD.md`). sleeve_engine은 'trend'(저빈도) 기본. 'intraday'(구 Casper)는 보존됐으나 비활성.
- **수수료 인하가 진짜 레버** → `commission.rate_per_side` 0.25%. KIS 우대 0.07~0.09% 적용 가능 시 고빈도 net 약 2배. 저빈도 trend sleeve에는 영향 미미.
```
Update the 핵심 정보 표 전략 row to note `sleeve_engine=trend` (TQQQ Vol-Target) 기본, intraday(ORB+FVG) optional.

- [ ] **Step 2: Commit**

```bash
git add 014_casper/CLAUDE.md
git commit -m "Document sleeve_engine policy + cost-frequency guardrail"
```

---

### Task 10: Full suite + TEST_MODE smoke + finalize

**Files:** none (verification)

- [ ] **Step 1: Run the full unit suite**

Run: `python3 -m pytest tests/ -q`
Expected: all pass (no regressions; existing `casper`-named tests updated to `trend` where they asserted bucket membership).

- [ ] **Step 2: TEST_MODE config smoke (no live orders)**

Run: `python3 -c "from src.core.trend import compute_trend_signal; print(compute_trend_signal())"`
Expected: prints a `TrendSignal(...)` with a real target/exposure (hits yfinance). If offline, prints the BIL fallback — acceptable.

- [ ] **Step 3: Confirm reversibility**

Set `config/strategy_params.json` `"sleeve_engine": "intraday"`, run `python3 -m pytest tests/test_bot_states.py -q -k intraday` → intraday path re-enabled. Restore to `"trend"`.

- [ ] **Step 4: Final commit + push branch**

```bash
git add -A
git commit -m "Finalize trend sleeve: full suite green, reversibility verified"
git push -u origin casper-lowfreq-trend
```
(Push only if the user asks; otherwise leave the branch local.)

---

## Self-Review (filled)

**Spec coverage:** §3.1 trend.py → Tasks 1-2; §3.2 _maybe_run_trend → Task 7; §3.3 portfolio rename → Task 4; §3.4 config → Task 5; §3.5 main-loop gate → Task 8; §5 tests → Tasks 1-3,6-8,10 (incl. golden parity Task 3); §6 scheduler shared-helper refactor → optional, deferred (not blocking); §7 backlog (daily-exit, tqqq_sma/clenow) → explicitly out of scope; guardrails #3/#4 → Task 9; #5 verification → Task 3 golden test. All spec sections mapped.

**Placeholder scan:** No TBD/TODO; all code blocks concrete. Test fixture/transport names flagged with "adapt to existing pattern" notes where the repo's exact fixture must be reused (test_notifier, test_bot_advanced) — engineer verifies the one method name (`_enqueue`) against the file.

**Type consistency:** `TrendSignal` fields (`target_symbol`, `exposure`, `regime`, `realized_vol`, `reason`, `signal_date`) used identically in Tasks 1, 3, 6, 7. `TrendState` (`last_signal_date`, `current_holding`, `last_exposure`) consistent Tasks 2, 7. Bucket key `"trend"` consistent Tasks 4, 7. `should_run_trend`/`compute_trend_signal` signatures match call sites.
