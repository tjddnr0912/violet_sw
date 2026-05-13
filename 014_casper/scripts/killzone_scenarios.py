#!/usr/bin/env python3
"""Killzone / BE-shift scenario backtest.

Reuses helpers in intraday_backtest_compare.py to evaluate seven
configurations of the Casper strategy that only differ in:
  - which killzone(s) are allowed for the breakout candle
  - the RR ratio (single or split by killzone)
  - when (or whether) the BE shift triggers

All other rules (ORB+FVG strict, ATR/VIX filters, commission, slippage)
are identical to production. 60-day TQQQ 5-min dataset.

Output: scripts/out/killzone_scenarios.json + console table.
"""

import sys
import os
import json
from datetime import time as dtime
from dataclasses import asdict
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import scripts.intraday_backtest_compare as ic
from scripts.intraday_backtest_compare import (
    strat_casper,
    fetch_data,
    metrics,
    classify_day,
    INITIAL_CAPITAL,
    Sig,
    Trade,
)


# ─── Strategy variants ──────────────────────────────────────────────
def strat_BASE(day_df, ctx):
    """Production baseline: AM_MACRO only, RR=3."""
    return strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                        allowed_killzones={"AM_MACRO"})


def strat_A_extended_kz(day_df, ctx):
    """A: extend killzone to AM_MACRO + AM_LATE, RR=3."""
    return strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                        allowed_killzones={"AM_MACRO", "AM_LATE"})


def strat_B_split_rr(day_df, ctx):
    """B: AM_MACRO with RR=3 first, fallback AM_LATE with RR=2."""
    sig = strat_casper(day_df, ctx, rr_ratio=3.0, strict=True,
                       allowed_killzones={"AM_MACRO"})
    if sig is not None:
        return sig
    return strat_casper(day_df, ctx, rr_ratio=2.0, strict=True,
                        allowed_killzones={"AM_LATE"})


# C1, C2 use the same strategy code as BASE / A — only BE_MOVE_TIME is
# monkey-patched at the wrapper level (see run_one_scenario).
def strat_C1_kz_late_be(day_df, ctx):
    return strat_BASE(day_df, ctx)


def strat_C2_extended_late_be(day_df, ctx):
    return strat_A_extended_kz(day_df, ctx)


# D1, D2 use the same strategy code — BE shift is disabled via the
# `rr_be_move` flag of simulate_trade in a custom runner.
def strat_D1_no_be(day_df, ctx):
    return strat_BASE(day_df, ctx)


def strat_D2_no_be_extended(day_df, ctx):
    return strat_A_extended_kz(day_df, ctx)


# ─── Custom runner with BE_MOVE_TIME and rr_be_move overrides ────────
def run_scenario(name, sig_fn, days, data,
                 be_move_time=dtime(11, 0),
                 rr_be_move=True,
                 vix_filter=True):
    """Clone of intraday_backtest_compare.run_strategy that:
       (a) monkey-patches ic.BE_MOVE_TIME for the run,
       (b) forwards rr_be_move into simulate_trade.
    """
    # Save and override module-level constant
    saved_be = ic.BE_MOVE_TIME
    ic.BE_MOVE_TIME = be_move_time

    capital = INITIAL_CAPITAL
    trades: List[Trade] = []
    cap_history = [(days[0], capital)]
    skipped = {"vix": 0, "no_signal": 0, "no_data": 0}

    tqqq = data["tqqq"]
    tqqq_d = data["tqqq_d"]
    qqq_d = data["qqq_d"]
    vix_d = data["vix_d"]

    try:
        for d in days:
            ctx = {}
            if vix_filter:
                v = vix_d[vix_d.index.date <= d]
                if len(v) > 0:
                    vv = float(v.iloc[-1]["Close"])
                    if not (ic.VIX_LOW <= vv <= ic.VIX_HIGH):
                        skipped["vix"] += 1
                        continue

            recent_d = tqqq_d[tqqq_d.index.date <= d].tail(20)
            ctx["avg_dr"] = (
                float((recent_d["High"] - recent_d["Low"]).mean())
                if len(recent_d) >= 5 else 0
            )

            if len(recent_d) >= 8:
                ranges = (recent_d["High"] - recent_d["Low"]).values
                today_ranges = ranges[:-1][-7:]
                if len(today_ranges) >= 7:
                    ctx["is_nr7"] = bool(today_ranges[-1] == today_ranges.min())
                else:
                    ctx["is_nr7"] = False
                ctx["atr_daily"] = (
                    float(pd.Series(today_ranges).mean()) if len(today_ranges) > 0 else 0
                )
            else:
                ctx["is_nr7"] = False
                ctx["atr_daily"] = 0

            today_data = tqqq[tqqq["date"] == d]
            if len(today_data) == 0:
                skipped["no_data"] += 1
                continue
            ctx["today_open"] = float(today_data.iloc[0]["Open"])

            try:
                from src.core.bias import compute_daily_bias
                ctx["daily_bias"] = compute_daily_bias(qqq_d, as_of=d)
            except Exception:
                ctx["daily_bias"] = None

            sig = sig_fn(today_data, ctx)
            if sig is None:
                skipped["no_signal"] += 1
                continue

            trade = ic.simulate_trade(name, today_data, sig, capital,
                                       rr_be_move=rr_be_move)
            if trade is None:
                skipped["no_signal"] += 1
                continue
            capital += trade.net_pnl
            trades.append(trade)
            cap_history.append((d, capital))

    finally:
        ic.BE_MOVE_TIME = saved_be

    return trades, capital, cap_history, skipped


# ─── Scenario registry ──────────────────────────────────────────────
SCENARIOS = [
    # (name, sig_fn, be_move_time, rr_be_move, description)
    ("BASE",          strat_BASE,                dtime(11, 0),  True,
     "AM_MACRO only, RR=3, BE@11:00 — production baseline"),
    ("A_ExtKZ",       strat_A_extended_kz,       dtime(11, 0),  True,
     "AM_MACRO+AM_LATE, RR=3, BE@11:00 — killzone extended"),
    ("B_SplitRR",     strat_B_split_rr,          dtime(11, 0),  True,
     "AM_MACRO RR=3 / AM_LATE RR=2, BE@11:00 — split RR"),
    ("C1_BE1130",     strat_C1_kz_late_be,       dtime(11, 30), True,
     "AM_MACRO only, RR=3, BE@11:30 — late BE only"),
    ("C2_ExtKZ_1130", strat_C2_extended_late_be, dtime(11, 30), True,
     "AM_MACRO+AM_LATE, RR=3, BE@11:30 — late BE + extended KZ"),
    ("D1_NoBE",       strat_D1_no_be,            dtime(11, 0),  False,
     "AM_MACRO only, RR=3, BE OFF — no breakeven shift"),
    ("D2_ExtKZ_NoBE", strat_D2_no_be_extended,   dtime(11, 0),  False,
     "AM_MACRO+AM_LATE, RR=3, BE OFF — extended KZ + no BE"),
]


def split_trades_by_kz(trades):
    """Bucket trades by AM_MACRO vs AM_LATE based on entry hh:mm."""
    macro, late = [], []
    for t in trades:
        try:
            h, m = map(int, t.entry_t.split(":"))
            mins = h * 60 + m
            # AM_MACRO ends 10:10, AM_LATE 10:10~10:55
            if mins < 10 * 60 + 10:
                macro.append(t)
            else:
                late.append(t)
        except Exception:
            pass
    return macro, late


def kz_summary(trades):
    """Tiny per-killzone breakdown."""
    macro, late = split_trades_by_kz(trades)
    out = {}
    for label, tr in (("macro", macro), ("late", late)):
        n = len(tr)
        if n == 0:
            out[label] = {"n": 0, "wr": None, "avg_r": None, "ret_sum": 0.0}
            continue
        wins = sum(1 for t in tr if t.result == "WIN")
        out[label] = {
            "n": n,
            "wr": round(wins / n * 100, 1),
            "avg_r": round(sum(t.r_multiple for t in tr) / n, 2),
            "ret_sum": round(sum(t.net_pnl for t in tr), 2),
        }
    return out


def main():
    print("=" * 80)
    print("  Killzone / BE-shift Scenarios — 60d TQQQ, KIS 정밀 비용 모델")
    print("=" * 80)

    data = fetch_data()
    tqqq = data["tqqq"]
    qqq = data["qqq"]
    common_days = sorted(set(tqqq["date"].unique()) & set(qqq["date"].unique()))
    print(f"[main] common days: {len(common_days)}  "
          f"range {common_days[0]} ~ {common_days[-1]}")

    regime = {str(d): classify_day(qqq, data["qqq_d"], d) for d in common_days}
    counts = pd.Series(list(regime.values())).value_counts()
    print("  regime counts:", dict(counts))

    results = {}
    for name, sig_fn, be_time, rr_be, desc in SCENARIOS:
        print(f"\n[run] {name}: {desc}")
        print(f"      BE move @ {be_time}, rr_be_move={rr_be}")
        trades, final_cap, cap_hist, skipped = run_scenario(
            name, sig_fn, common_days, data,
            be_move_time=be_time, rr_be_move=rr_be,
        )
        m = metrics(trades, cap_hist, len(common_days), regime_map=regime)
        kz_break = kz_summary(trades)
        results[name] = {
            "desc": desc,
            "be_move_time": str(be_time),
            "rr_be_move": rr_be,
            "metrics": m,
            "trades": [asdict(t) for t in trades],
            "skipped": skipped,
            "kz_breakdown": kz_break,
        }
        print(f"      n={m['n_trades']:>2}  WR={m['win_rate']:>5.1f}%  "
              f"PF={m['profit_factor']:>5.2f}  Ret={m['total_return_pct']:>+6.2f}%  "
              f"MDD={m['max_dd_pct']:>+6.2f}%  AvgR={m['avg_r']:>+5.2f}")
        if kz_break["macro"]["n"] or kz_break["late"]["n"]:
            mc, lt = kz_break["macro"], kz_break["late"]
            print(f"      ├ AM_MACRO: n={mc['n']}  WR={mc['wr']}%  AvgR={mc['avg_r']}  Ret=${mc['ret_sum']}")
            print(f"      └ AM_LATE : n={lt['n']}  WR={lt['wr']}%  AvgR={lt['avg_r']}  Ret=${lt['ret_sum']}")

    # save JSON
    out_dir = os.path.join(os.path.dirname(__file__), "out")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "killzone_scenarios.json")
    with open(out_path, "w") as f:
        json.dump({
            "period_days": len(common_days),
            "regime_counts": dict(counts),
            "scenarios": results,
        }, f, indent=2, default=str)
    print(f"\n[main] saved → {out_path}")

    # ── Summary table ──
    print("\n" + "=" * 110)
    print("  SCENARIO COMPARISON")
    print("=" * 110)
    header = f"{'Scenario':<16s} {'BE':>5s} {'Trd':>4s} {'WR%':>6s} {'PF':>6s} {'Ret%':>7s} {'MDD%':>7s} {'AvgR':>6s} {'Hold':>6s}"
    print(header)
    print("-" * 110)
    for name, _, be_t, rr_be, _ in SCENARIOS:
        m = results[name]["metrics"]
        be_label = "off" if not rr_be else be_t.strftime("%H:%M")
        pf = m['profit_factor']
        pf_s = f"{pf:>5.2f}" if pf != float('inf') else "  inf"
        print(f"{name:<16s} {be_label:>5s} {m['n_trades']:>4d} "
              f"{m['win_rate']:>6.1f} {pf_s:>6s} "
              f"{m['total_return_pct']:>+7.2f} {m['max_dd_pct']:>+7.2f} "
              f"{m['avg_r']:>+6.2f} {m['avg_hold_min']:>6.1f}")

    # ── Killzone breakdown ──
    print("\n" + "=" * 110)
    print("  KILLZONE BREAKDOWN (per scenario)")
    print("=" * 110)
    print(f"{'Scenario':<16s} {'MACRO_n':>8s} {'MACRO_WR':>9s} {'MACRO_R':>8s} "
          f"{'LATE_n':>8s} {'LATE_WR':>9s} {'LATE_R':>8s}")
    print("-" * 80)
    for name, *_ in SCENARIOS:
        kz = results[name]["kz_breakdown"]
        mc, lt = kz["macro"], kz["late"]
        mc_wr = f"{mc['wr']}%" if mc["wr"] is not None else "  - "
        lt_wr = f"{lt['wr']}%" if lt["wr"] is not None else "  - "
        mc_r = f"{mc['avg_r']:+.2f}" if mc["avg_r"] is not None else "  - "
        lt_r = f"{lt['avg_r']:+.2f}" if lt["avg_r"] is not None else "  - "
        print(f"{name:<16s} {mc['n']:>8d} {mc_wr:>9s} {mc_r:>8s} "
              f"{lt['n']:>8d} {lt_wr:>9s} {lt_r:>8s}")

    return results


if __name__ == "__main__":
    main()
