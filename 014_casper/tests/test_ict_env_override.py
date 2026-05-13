"""Tests for ICT_* env-var overrides applied to load_strategy_params()."""

import json
import os
from pathlib import Path

import pytest

from src.utils.config import (
    load_strategy_params, reset_config_cache, _apply_ict_env_overrides,
)


def _baseline_params():
    return {
        "entry": {
            "killzone_filter_enabled": False,
            "allowed_killzones": ["AM_MACRO"],
            "require_displacement": False,
            "disp_atr_mult": 1.0,
            "disp_max_wick": 0.50,
            "disp_prev_mult": 1.5,
            "require_sweep_choch": False,
            "sweep_lookback": 6,
            "choch_lookback": 6,
            "sweep_min_breach_pct": 0.0005,
            "sweep_min_wick_ratio": 0.60,
            "bear_fvg_for_sqqq": False,
            "daily_bias_skip_neutral": False,
        }
    }


# ───────────── unit: _apply_ict_env_overrides ─────────────
def test_no_env_keeps_defaults(monkeypatch):
    for k in [
        "ICT_KILLZONE_ENABLED", "ICT_ALLOWED_KILLZONES",
        "ICT_REQUIRE_DISPLACEMENT", "ICT_DISP_ATR_MULT",
        "ICT_DISP_MAX_WICK", "ICT_DISP_PREV_MULT",
        "ICT_REQUIRE_SWEEP_CHOCH", "ICT_SWEEP_LOOKBACK",
        "ICT_CHOCH_LOOKBACK", "ICT_SWEEP_MIN_BREACH_PCT",
        "ICT_SWEEP_MIN_WICK_RATIO",
        "ICT_BEAR_FVG_FOR_SQQQ", "ICT_DAILY_BIAS_SKIP_NEUTRAL",
    ]:
        monkeypatch.delenv(k, raising=False)
    p = _apply_ict_env_overrides(_baseline_params())
    e = p["entry"]
    assert e["killzone_filter_enabled"] is False
    assert e["require_displacement"] is False
    assert e["require_sweep_choch"] is False


def test_env_on_toggles_killzone(monkeypatch):
    monkeypatch.setenv("ICT_KILLZONE_ENABLED", "on")
    p = _apply_ict_env_overrides(_baseline_params())
    assert p["entry"]["killzone_filter_enabled"] is True


def test_env_off_explicit(monkeypatch):
    monkeypatch.setenv("ICT_KILLZONE_ENABLED", "off")
    p = _baseline_params()
    p["entry"]["killzone_filter_enabled"] = True  # JSON says on
    p = _apply_ict_env_overrides(p)
    # env explicitly off → must win
    assert p["entry"]["killzone_filter_enabled"] is False


def test_env_allowed_killzones_csv(monkeypatch):
    monkeypatch.setenv("ICT_ALLOWED_KILLZONES", "AM_MACRO,AM_LATE")
    p = _apply_ict_env_overrides(_baseline_params())
    assert p["entry"]["allowed_killzones"] == ["AM_MACRO", "AM_LATE"]


def test_env_displacement_numeric(monkeypatch):
    monkeypatch.setenv("ICT_REQUIRE_DISPLACEMENT", "true")
    monkeypatch.setenv("ICT_DISP_ATR_MULT", "1.3")
    monkeypatch.setenv("ICT_DISP_MAX_WICK", "0.40")
    monkeypatch.setenv("ICT_DISP_PREV_MULT", "2.0")
    p = _apply_ict_env_overrides(_baseline_params())
    e = p["entry"]
    assert e["require_displacement"] is True
    assert e["disp_atr_mult"] == 1.3
    assert e["disp_max_wick"] == 0.40
    assert e["disp_prev_mult"] == 2.0


def test_env_sweep_choch(monkeypatch):
    monkeypatch.setenv("ICT_REQUIRE_SWEEP_CHOCH", "1")
    monkeypatch.setenv("ICT_SWEEP_LOOKBACK", "10")
    monkeypatch.setenv("ICT_CHOCH_LOOKBACK", "8")
    monkeypatch.setenv("ICT_SWEEP_MIN_BREACH_PCT", "0.001")
    monkeypatch.setenv("ICT_SWEEP_MIN_WICK_RATIO", "0.50")
    p = _apply_ict_env_overrides(_baseline_params())
    e = p["entry"]
    assert e["require_sweep_choch"] is True
    assert e["sweep_lookback"] == 10
    assert e["choch_lookback"] == 8
    assert e["sweep_min_breach_pct"] == 0.001
    assert e["sweep_min_wick_ratio"] == 0.50


def test_env_phase3_toggles(monkeypatch):
    monkeypatch.setenv("ICT_BEAR_FVG_FOR_SQQQ", "on")
    monkeypatch.setenv("ICT_DAILY_BIAS_SKIP_NEUTRAL", "on")
    p = _apply_ict_env_overrides(_baseline_params())
    assert p["entry"]["bear_fvg_for_sqqq"] is True
    assert p["entry"]["daily_bias_skip_neutral"] is True


# ───────────── P2: qqq_primary mode-level toggle ─────────────
def test_env_qqq_primary_on(monkeypatch):
    monkeypatch.setenv("ICT_QQQ_PRIMARY", "on")
    p = _apply_ict_env_overrides(_baseline_params())
    assert p["mode"]["qqq_primary"] is True


def test_env_qqq_primary_off_explicit(monkeypatch):
    monkeypatch.setenv("ICT_QQQ_PRIMARY", "off")
    p = _baseline_params()
    p["mode"] = {"qqq_primary": True}    # JSON enables it
    p = _apply_ict_env_overrides(p)
    assert p["mode"]["qqq_primary"] is False


def test_env_qqq_primary_unset_keeps_json(monkeypatch):
    monkeypatch.delenv("ICT_QQQ_PRIMARY", raising=False)
    p = _baseline_params()
    p["mode"] = {"qqq_primary": True}
    p = _apply_ict_env_overrides(p)
    assert p["mode"]["qqq_primary"] is True


# ───────────── M3 / M4: EQH/EQL + Session pools ─────────────
def test_env_eqh_eql_pools_on(monkeypatch):
    monkeypatch.setenv("ICT_USE_EQH_EQL_POOLS", "on")
    monkeypatch.setenv("ICT_EQH_EQL_PCT", "0.001")
    p = _apply_ict_env_overrides(_baseline_params())
    assert p["entry"]["use_eqh_eql_pools"] is True
    assert p["entry"]["eqh_eql_pct"] == 0.001


def test_env_session_pools_on(monkeypatch):
    monkeypatch.setenv("ICT_USE_SESSION_POOLS", "on")
    p = _apply_ict_env_overrides(_baseline_params())
    assert p["entry"]["use_session_pools"] is True


def test_env_pools_off_explicit(monkeypatch):
    monkeypatch.setenv("ICT_USE_EQH_EQL_POOLS", "off")
    monkeypatch.setenv("ICT_USE_SESSION_POOLS", "off")
    p = _baseline_params()
    p["entry"]["use_eqh_eql_pools"] = True
    p["entry"]["use_session_pools"] = True
    p = _apply_ict_env_overrides(p)
    assert p["entry"]["use_eqh_eql_pools"] is False
    assert p["entry"]["use_session_pools"] is False


# ───────── Day 1: premarket history (yfinance prepost) ─────────
def test_env_premkt_history_on(monkeypatch):
    monkeypatch.setenv("ICT_USE_PREMKT_HISTORY", "on")
    p = _apply_ict_env_overrides(_baseline_params())
    assert p["entry"]["use_premkt_history"] is True


def test_env_premkt_history_off_explicit(monkeypatch):
    monkeypatch.setenv("ICT_USE_PREMKT_HISTORY", "off")
    p = _baseline_params()
    p["entry"]["use_premkt_history"] = True
    p = _apply_ict_env_overrides(p)
    assert p["entry"]["use_premkt_history"] is False


# ───────── Day 3: PDH/PDL sweep pool ─────────
def test_env_pdh_pdl_pool_on(monkeypatch):
    monkeypatch.setenv("ICT_USE_PDH_PDL_POOL", "on")
    p = _apply_ict_env_overrides(_baseline_params())
    assert p["entry"]["use_pdh_pdl_pool"] is True


def test_env_pdh_pdl_pool_off_explicit(monkeypatch):
    monkeypatch.setenv("ICT_USE_PDH_PDL_POOL", "off")
    p = _baseline_params()
    p["entry"]["use_pdh_pdl_pool"] = True
    p = _apply_ict_env_overrides(p)
    assert p["entry"]["use_pdh_pdl_pool"] is False


# ───────────── integration: load_strategy_params end-to-end ─────────────
def test_load_strategy_params_respects_env(monkeypatch):
    reset_config_cache()
    monkeypatch.setenv("ICT_KILLZONE_ENABLED", "on")
    monkeypatch.setenv("ICT_REQUIRE_DISPLACEMENT", "on")
    params = load_strategy_params()
    assert params["entry"]["killzone_filter_enabled"] is True
    assert params["entry"]["require_displacement"] is True
    reset_config_cache()
