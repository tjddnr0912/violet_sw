"""Unit tests for multi-bucket portfolio (P0~P4).

Coverage:
  - Trading-day helpers (time_utils): last/first TDOM, grace window, Q-end
  - GEM signal scheduler (gem.py): canonical + grace + dedup
  - Portfolio tier (portfolio.py): tier_for_capital boundaries
  - Portfolio evaluation: drift, tier_changed detection
  - Needs-rebalance gating (Q-end only)
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from unittest.mock import patch

import pytest

from src.core.gem import (
    GemSignal,
    GemState,
    GEM_UNIVERSE,
    compute_gem_signal,
    should_run_gem,
)
from src.core.portfolio import (
    Bucket,
    PortfolioState,
    evaluate_portfolio,
    needs_initial_seed,
    needs_rebalance,
    tier_for_capital,
    tier_key,
)
from src.utils import time_utils


# ──────────────────────────────────────────────────────────────────────
# time_utils — calendar helpers used by the schedulers
# ──────────────────────────────────────────────────────────────────────


class TestTradingDayHelpers:
    def test_last_trading_day_basic(self):
        # May 2026: Memorial Day = May 25 (Mon), so last TDOM = May 29 (Fri).
        assert time_utils.get_last_trading_day_of_month(2026, 5) == date(2026, 5, 29)

    def test_last_trading_day_year_end(self):
        # Dec 31 2026 is a Thursday (no Christmas overflow into Dec 31).
        assert time_utils.get_last_trading_day_of_month(2026, 12) == date(2026, 12, 31)

    def test_last_trading_day_good_friday(self):
        # 2026-04-03 = Good Friday → last TDOM April = 2026-04-30 (Thu)
        assert time_utils.get_last_trading_day_of_month(2026, 4) == date(2026, 4, 30)

    def test_first_trading_day_after_new_year(self):
        # 2026-01-01 = NY day, 1/2 (Fri) is first trading day.
        assert time_utils.get_first_trading_day_of_month(2026, 1) == date(2026, 1, 2)

    def test_is_last_trading_day(self):
        assert time_utils.is_last_trading_day_of_month(date(2026, 5, 29)) is True
        assert time_utils.is_last_trading_day_of_month(date(2026, 5, 22)) is False
        # Memorial Day itself isn't a trading day → False
        assert time_utils.is_last_trading_day_of_month(date(2026, 5, 25)) is False

    def test_is_first_trading_day(self):
        assert time_utils.is_first_trading_day_of_month(date(2026, 6, 1)) is True
        assert time_utils.is_first_trading_day_of_month(date(2026, 6, 2)) is False

    def test_grace_window_captures_missed(self):
        # T+0 = May 29 → captures itself
        assert time_utils.was_last_trading_day_of_month_within(
            3, date(2026, 5, 29)
        ) == date(2026, 5, 29)
        # T+1 (Jun 1, Mon) → still captures May 29
        assert time_utils.was_last_trading_day_of_month_within(
            3, date(2026, 6, 1)
        ) == date(2026, 5, 29)
        # T+3 (Jun 3, Wed) → still captures
        assert time_utils.was_last_trading_day_of_month_within(
            3, date(2026, 6, 3)
        ) == date(2026, 5, 29)
        # T+5 (Jun 5, Fri) → out of grace
        assert time_utils.was_last_trading_day_of_month_within(
            3, date(2026, 6, 5)
        ) is None

    def test_quarter_end_detection(self):
        # Q1=Mar, Q2=Jun, Q3=Sep, Q4=Dec — last TDOM each
        assert time_utils.is_last_trading_day_of_quarter(date(2026, 3, 31)) is True
        assert time_utils.is_last_trading_day_of_quarter(date(2026, 6, 30)) is True
        assert time_utils.is_last_trading_day_of_quarter(date(2026, 9, 30)) is True
        assert time_utils.is_last_trading_day_of_quarter(date(2026, 12, 31)) is True
        # February last day is NOT a quarter end
        assert time_utils.is_last_trading_day_of_quarter(date(2026, 2, 27)) is False


# ──────────────────────────────────────────────────────────────────────
# GEM scheduler — should_run_gem
# ──────────────────────────────────────────────────────────────────────


class TestGemScheduler:
    def test_run_on_last_trading_day(self):
        state = GemState()
        run, sig_date = should_run_gem(date(2026, 5, 29), state)
        assert run is True
        assert sig_date == date(2026, 5, 29)

    def test_grace_window_jun1(self):
        state = GemState()
        run, sig_date = should_run_gem(date(2026, 6, 1), state)
        assert run is True
        assert sig_date == date(2026, 5, 29)

    def test_mid_month_noop(self):
        state = GemState()
        run, sig_date = should_run_gem(date(2026, 6, 15), state)
        assert run is False
        assert sig_date is None

    def test_dedup_prevents_double_execution(self):
        state = GemState(last_signal_date="2026-05-29", last_target="SPY")
        # Same date — no re-run
        run, _ = should_run_gem(date(2026, 5, 29), state)
        assert run is False
        # T+1 grace also de-duped
        run, _ = should_run_gem(date(2026, 6, 1), state)
        assert run is False

    def test_new_month_triggers(self):
        state = GemState(last_signal_date="2026-05-29", last_target="SPY")
        run, sig_date = should_run_gem(date(2026, 6, 30), state)
        assert run is True
        assert sig_date == date(2026, 6, 30)


# ──────────────────────────────────────────────────────────────────────
# Portfolio tier — auto-activation P4
# ──────────────────────────────────────────────────────────────────────


class TestPortfolioTier:
    def test_tier_below_3k_is_gem_only(self):
        w = tier_for_capital(1500)
        assert w == {"gem": 1.0}

    def test_tier_at_3k_boundary(self):
        # exactly $3,000 → 3-bucket tier
        w = tier_for_capital(3000)
        assert set(w.keys()) == {"spmo", "gem", "trend"}
        assert abs(sum(w.values()) - 1.0) < 1e-9

    def test_tier_at_5k_unlocks_mtum_qual(self):
        w = tier_for_capital(5000)
        assert "mtum" in w
        assert "qual" in w
        assert abs(sum(w.values()) - 1.0) < 1e-9

    def test_tier_at_10k_unlocks_clenow_tqqq_sma(self):
        w = tier_for_capital(10000)
        assert "clenow" in w
        assert "tqqq_sma" in w
        assert abs(sum(w.values()) - 1.0) < 1e-9

    def test_tier_boundaries_are_inclusive_below(self):
        # $4,999 still on the $3k tier
        assert "mtum" not in tier_for_capital(4999)
        # $9,999 still on the $5k tier
        assert "clenow" not in tier_for_capital(9999)


# ──────────────────────────────────────────────────────────────────────
# Portfolio evaluation + drift detection
# ──────────────────────────────────────────────────────────────────────


class TestPortfolioEvaluation:
    def test_evaluate_assigns_values_to_buckets(self):
        holdings = {
            "SPMO": {"qty": 12, "value_usd": 1450.0, "price": 120.83},
            "SPY":  {"qty": 1,  "value_usd": 580.0,  "price": 580.0},
            "TQQQ": {"qty": 7,  "value_usd": 560.0,  "price": 80.0},
        }
        total = 3000.0
        buckets, _ = evaluate_portfolio(
            total, holdings, today=date(2026, 6, 30)
        )
        names = {b.name: b for b in buckets}
        assert names["spmo"].current_value_usd == 1450.0
        assert names["spmo"].current_symbol == "SPMO"
        # GEM holds SPY in this snapshot
        assert names["gem"].current_value_usd == 580.0
        assert names["gem"].current_symbol == "SPY"
        # Trend bucket holds TQQQ
        assert names["trend"].current_value_usd == 560.0
        assert names["trend"].current_symbol == "TQQQ"

    def test_drift_pct_calculation(self):
        b = Bucket(name="spmo", target_weight=0.5, target_usd=1500,
                   current_value_usd=1650)
        assert abs(b.drift_pct - 0.10) < 1e-9

    def test_needs_rebalance_only_on_q_end(self):
        holdings = {"SPMO": {"qty": 30, "value_usd": 3000.0, "price": 100.0}}
        # SPMO at 100% drift+ (target 0.50 × 5000 = 2500, actual 3000 → +20%)
        buckets, _ = evaluate_portfolio(
            5000.0, holdings, today=date(2026, 6, 30)
        )
        # Q-end (Jun 30) → drift detected
        drifted = needs_rebalance(buckets, drift_threshold=0.10,
                                  today=date(2026, 6, 30))
        names = [b.name for b in drifted]
        assert "spmo" in names
        # Non-Q-end → no rebalance even if drifted
        drifted2 = needs_rebalance(buckets, drift_threshold=0.10,
                                   today=date(2026, 5, 15))
        assert drifted2 == []

    def test_needs_rebalance_excludes_gem_and_trend(self):
        # GEM/trend drift must be handled by their own schedulers,
        # not by the quarterly bucket-drift rebalancer.
        holdings = {"SPY": {"qty": 10, "value_usd": 5800.0, "price": 580.0}}
        buckets, _ = evaluate_portfolio(
            5000.0, holdings, today=date(2026, 6, 30)
        )
        drifted = needs_rebalance(buckets, drift_threshold=0.10,
                                  today=date(2026, 6, 30))
        names = [b.name for b in drifted]
        assert "gem" not in names
        assert "trend" not in names

    def test_tier_change_detected(self):
        state = PortfolioState(last_tier_key=tier_key(tier_for_capital(3000)))
        holdings = {}
        _, info = evaluate_portfolio(
            5100.0, holdings, state=state, today=date(2026, 6, 30)
        )
        assert info["tier_changed"] is True
        assert "mtum" in info["weights"]

    def test_tier_unchanged_when_still_in_band(self):
        state = PortfolioState(last_tier_key=tier_key(tier_for_capital(3000)))
        _, info = evaluate_portfolio(
            3500.0, {}, state=state, today=date(2026, 6, 30)
        )
        assert info["tier_changed"] is False


# ──────────────────────────────────────────────────────────────────────
# State persistence (gem + portfolio)
# ──────────────────────────────────────────────────────────────────────


class TestStatePersistence:
    def test_gem_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "gem_state.json")
            s = GemState(
                last_signal_date="2026-05-29",
                last_target="VEU",
                current_holding="VEU",
            )
            s.save(path)
            loaded = GemState.load(path)
            assert loaded.last_signal_date == "2026-05-29"
            assert loaded.last_target == "VEU"
            assert loaded.current_holding == "VEU"

    def test_gem_state_corrupted_file_returns_default(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "gem_state.json")
            with open(path, "w") as f:
                f.write("not valid json {")
            loaded = GemState.load(path)
            assert loaded.last_signal_date is None

    def test_portfolio_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "portfolio_state.json")
            s = PortfolioState(
                last_eval_date="2026-05-15",
                last_total_usd=3000.0,
                last_tier_key="gem=0.30,spmo=0.50,trend=0.20",
                buckets={"spmo": {"target_usd": 1500}},
                seeded_at="2026-05-15",
            )
            s.save(path)
            loaded = PortfolioState.load(path)
            assert loaded.last_total_usd == 3000.0
            assert loaded.last_tier_key == "gem=0.30,spmo=0.50,trend=0.20"
            assert loaded.seeded_at == "2026-05-15"


# ──────────────────────────────────────────────────────────────────────
# Initial seed — one-shot first-run allocation
# ──────────────────────────────────────────────────────────────────────


class TestInitialSeed:
    def test_seed_needed_when_100pct_cash(self):
        """Brand new account, $3,000 cash, no positions → seed fires."""
        state = PortfolioState()  # seeded_at=None
        assert needs_initial_seed(3000.0, holdings={}, state=state) is True

    def test_seed_needed_when_95pct_cash(self):
        """User has a small leftover position from elsewhere — still seed."""
        state = PortfolioState()
        holdings = {"AAPL": {"qty": 1, "value_usd": 100.0}}  # 3.3% of $3k
        assert needs_initial_seed(3000.0, holdings, state) is True

    def test_seed_skipped_when_already_invested(self):
        """User already has 50% in positions — assume they know what they're
        doing, do NOT auto-buy on top of that."""
        state = PortfolioState()
        holdings = {"SPY": {"qty": 3, "value_usd": 1500.0}}  # 50% of $3k
        assert needs_initial_seed(3000.0, holdings, state) is False

    def test_seed_skipped_after_first_run(self):
        """seeded_at is set → never re-seed, even from 100% cash."""
        state = PortfolioState(seeded_at="2026-05-15")
        assert needs_initial_seed(3000.0, holdings={}, state=state) is False

    def test_seed_skipped_for_tiny_account(self):
        """Account < $100 — too small to buy anything meaningful."""
        state = PortfolioState()
        assert needs_initial_seed(50.0, holdings={}, state=state) is False

    def test_seed_skipped_when_total_zero(self):
        state = PortfolioState()
        assert needs_initial_seed(0.0, holdings={}, state=state) is False


# ──────────────────────────────────────────────────────────────────────
# Trend bucket rename (was "casper") — TQQQ/BIL vol-target sleeve
# ──────────────────────────────────────────────────────────────────────

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


def test_bucket_value_sums_tqqq_and_bil_when_sleeve_split():
    # The vol-target trend sleeve co-holds TQQQ (asset, ~83%) + BIL (safe,
    # ~17%). The bucket value must SUM both legs and the label must name both
    # — the pre-fix first-match loop returned only TQQQ and silently hid the
    # BIL leg from the 13:00 portfolio summary.
    holdings = {
        "TQQQ": {"qty": 6, "value_usd": 524.0, "price": 87.34},
        "BIL":  {"qty": 1, "value_usd": 92.0,  "price": 92.0},
    }
    buckets, _ = pf.evaluate_portfolio(3000.0, holdings,
                                       state=pf.PortfolioState())
    trend_b = next(b for b in buckets if b.name == "trend")
    assert trend_b.current_value_usd == 616.0          # 524 + 92, not 524
    assert trend_b.current_symbol is not None
    assert "TQQQ" in trend_b.current_symbol
    assert "BIL" in trend_b.current_symbol


def test_bucket_value_shows_bil_when_only_safe_held():
    # Risk-off regime (exposure 0): the sleeve is 100% BIL. The summary must
    # show BIL, not blank, so a defensive sleeve is never invisible.
    holdings = {"BIL": {"qty": 7, "value_usd": 644.0, "price": 92.0}}
    buckets, _ = pf.evaluate_portfolio(3000.0, holdings,
                                       state=pf.PortfolioState())
    trend_b = next(b for b in buckets if b.name == "trend")
    assert trend_b.current_symbol == "BIL"
    assert trend_b.current_value_usd == 644.0


def test_needs_rebalance_excludes_trend(monkeypatch):
    import src.utils.time_utils as tu
    monkeypatch.setattr(tu, "is_last_trading_day_of_quarter", lambda d: True)
    b = pf.Bucket(name="trend", target_weight=0.2, target_usd=800,
                  current_value_usd=1200)   # 50% drift
    assert pf.needs_rebalance([b], drift_threshold=0.10) == []
