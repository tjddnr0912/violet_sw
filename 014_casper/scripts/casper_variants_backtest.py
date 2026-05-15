#!/usr/bin/env python3
"""Casper variants comparison — 60d TQQQ + KIS cost model.

Each variant exercises a single modification from the Casper SMC
"reference implementation" (community-derived from his YouTube videos
and TradingView scripts). All other rules identical to current
production Scenario B baseline.

Variants:
  BASE_S_B       Scenario B production (15m ORB, SL=prev_low, RR=3/2)
  5m_ORB         5-minute Opening Range (vs 15m). Earlier start (09:35).
  30m_ORB        30-minute Opening Range. Later start (10:00).
  SL_midpoint    SL = ORB midpoint (community script standard)
  partial_TP     50% TP1@1.5R / 50% TP2@3R, move SL to ORB after TP1
  ADX_filter     + ADX(14) >= 25 required at breakout
  VWAP_4H        + 4H VWAP alignment (long above, short below)

Output:
  scripts/out/casper_variants_results.json (per-variant metrics)
  Console comparison table
"""

from __future__ import annotations

import os
import sys
import json
from dataclasses import dataclass, asdict, field
from datetime import time as dtime
from typing import Optional, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")


# ─── Constants (same as intraday_backtest_compare) ───
INITIAL_CAPITAL = 1500.0
BROKERAGE = 0.0025
SLIP_BUY = 0.0005
SLIP_TP = 0.0005
SLIP_STOP = 0.0010
SLIP_TIME = 0.0005
SEC_RATE_SELL = 0.0000278
TAF_PER_SHARE_SELL = 0.000166
MIN_RISK = 0.10
VIX_LOW, VIX_HIGH = 12.0, 30.0
BE_MOVE_TIME = dtime(11, 0)
FORCE_CLOSE_TIME = dtime(15, 50)


@dataclass
class Trade:
    variant: str
    date: str
    entry_t: str
    entry: float
    stop: float
    target: float
    exit_t: str
    exit_price: float
    exit_reason: str
    shares: int
    net_pnl: float
    r_multiple: float
    result: str


# ─── Data fetch ───
def fetch_data():
    print("[data] downloading 60d 5m + daily …")
    tqqq = yf.download("TQQQ", period="60d", interval="5m", progress=False, auto_adjust=False)
    qqq_d = yf.download("QQQ", period="6mo", interval="1d", progress=False, auto_adjust=False)
    vix_d = yf.download("^VIX", period="6mo", interval="1d", progress=False, auto_adjust=False)

    def flatten(df):
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = [c[0] for c in df.columns]
        return df

    tqqq, qqq_d, vix_d = flatten(tqqq), flatten(qqq_d), flatten(vix_d)
    tqqq.index = tqqq.index.tz_convert("US/Eastern")
    tqqq["date"] = tqqq.index.date
    qqq_d["MA20"] = qqq_d["Close"].rolling(20).mean()
    return {"tqqq": tqqq, "qqq_d": qqq_d, "vix_d": vix_d}


# ─── ORB + FVG helpers (parameterized by window) ───
def compute_orb(day_df: pd.DataFrame, window_min: int) -> Optional[tuple]:
    end_h, end_m = 9, 30 + window_min - 1
    end_t = dtime(end_h, end_m) if end_m < 60 else dtime(10, end_m - 60)
    o = day_df.between_time("09:30", end_t.strftime("%H:%M"))
    if len(o) < max(1, window_min // 5):
        return None
    return float(o["High"].max()), float(o["Low"].min())


def scan_start_time(window_min: int) -> dtime:
    """First bar AFTER ORB ends."""
    end_min = 30 + window_min
    return dtime(9 + end_min // 60, end_min % 60)


def detect_bullish_fvg(c1, c3) -> Optional[tuple]:
    if c1["High"] < c3["Low"]:
        return (c3["Low"], c1["High"])
    return None


def atr14(bars: pd.DataFrame) -> Optional[float]:
    if len(bars) < 15:
        return None
    h, l, pc = bars["High"], bars["Low"], bars["Close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    val = tr.rolling(14).mean().iloc[-1]
    return float(val) if not pd.isna(val) and val > 0 else None


def adx14(bars: pd.DataFrame) -> Optional[float]:
    if len(bars) < 30:
        return None
    h, l, c = bars["High"], bars["Low"], bars["Close"]
    up = h.diff()
    dn = -l.diff()
    plus_dm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=bars.index)
    minus_dm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=bars.index)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr_n = tr.ewm(alpha=1.0 / 14, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1.0 / 14, adjust=False).mean() / atr_n.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(alpha=1.0 / 14, adjust=False).mean() / atr_n.replace(0, np.nan)
    denom = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denom
    adx_val = dx.ewm(alpha=1.0 / 14, adjust=False).mean().iloc[-1]
    return float(adx_val) if not pd.isna(adx_val) else None


def vwap_4h(bars: pd.DataFrame, current_time) -> Optional[float]:
    """4-hour rolling VWAP up to current_time."""
    sub = bars.loc[:current_time].tail(48)  # 48 × 5m = 4h
    if len(sub) < 10:
        return None
    tp = (sub["High"] + sub["Low"] + sub["Close"]) / 3.0
    pv = (tp * sub["Volume"]).sum()
    vol = sub["Volume"].sum()
    return float(pv / vol) if vol > 0 else None


# ─── Signal generation (parameterized) ───
def find_signal(day_df: pd.DataFrame, ctx: dict, variant: dict) -> Optional[dict]:
    """Return a signal dict or None."""
    orb_window = variant["orb_window_min"]
    orb = compute_orb(day_df, orb_window)
    if orb is None:
        return None
    orb_h, orb_l = orb
    orb_mid = (orb_h + orb_l) / 2

    scan_start = scan_start_time(orb_window)
    post = day_df.between_time(scan_start.strftime("%H:%M"), "10:55")
    if len(post) < 4:
        return None

    atr_val = atr14(day_df)

    # iterate breakout candidates (bull only)
    for i in range(1, len(post) - 1):
        c = post.iloc[i]
        if not (c["Close"] > orb_h and c["Close"] > c["Open"]):
            continue
        # Strict (caspar): body straddles ORB
        if not (c["Open"] <= orb_h <= c["Close"]):
            continue

        # ADX filter
        if variant.get("require_adx"):
            adx_now = adx14(day_df.loc[:post.index[i]])
            if adx_now is None or adx_now < 25:
                continue

        # 4H VWAP filter
        if variant.get("require_vwap_alignment"):
            vwap = vwap_4h(day_df, post.index[i])
            if vwap is None or c["Close"] <= vwap:
                continue

        # Displacement (current bot's rule, kept)
        body = c["Close"] - c["Open"]
        total = c["High"] - c["Low"]
        wick = (total - body) / total if total > 0 else 1.0
        if wick >= 0.50:
            continue
        if atr_val and body < atr_val * 1.0:
            continue

        # FVG check (i-1, i+1)
        c_prev = post.iloc[i - 1]
        c_next = post.iloc[i + 1]
        fvg = detect_bullish_fvg(c_prev, c_next)
        if fvg is None:
            continue
        fvg_top, fvg_bot = fvg
        # Strict S2: FVG intersects ORB
        if not (fvg_bot <= orb_h <= fvg_top):
            continue

        entry = (fvg_top + fvg_bot) / 2

        # SL selection per variant
        if variant.get("sl_method") == "orb_midpoint":
            stop = orb_mid
        else:
            stop = float(c_prev["Low"])

        risk = entry - stop
        if risk < MIN_RISK:
            continue

        # RR (Scenario B equivalent — by killzone time)
        bar_time = post.index[i].time()
        if dtime(9, 30) <= bar_time < dtime(10, 10):
            rr = 3.0
            zone = "AM_MACRO"
        elif dtime(10, 10) <= bar_time < dtime(10, 55):
            rr = 2.0
            zone = "AM_LATE"
        else:
            continue

        target = entry + risk * rr

        # Wait for pullback into FVG
        after = day_df[day_df.index > post.index[i + 1]].between_time("09:45", "15:50")
        for j in range(len(after)):
            if after.iloc[j]["Low"] <= fvg_top:
                return {
                    "entry_time": after.index[j],
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "rr": rr,
                    "zone": zone,
                    "risk": risk,
                    "orb_high": orb_h,
                    "orb_mid": orb_mid,
                }
        return None
    return None


# ─── Trade simulation (parameterized for partial TP) ───
def simulate(sig: dict, day_df: pd.DataFrame, capital: float, variant: dict) -> Optional[Trade]:
    after = day_df[day_df.index >= sig["entry_time"]].between_time("09:45", "15:55")
    if len(after) == 0:
        return None
    eff_entry = sig["entry"] * (1 + SLIP_BUY)
    shares = int(capital / eff_entry)
    if shares < 1:
        return None
    risk_ps = eff_entry - sig["stop"]
    if risk_ps <= 0:
        return None
    be_price = eff_entry * (1 + BROKERAGE * 2 + SLIP_BUY + SLIP_TP)

    stop = sig["stop"]
    target = sig["target"]
    sl_moved = False
    partial_done = False

    # Partial TP setup
    use_partial = variant.get("partial_tp", False)
    tp1 = sig["entry"] + risk_ps * 1.5  # TP1 @ 1.5R
    tp2 = target                          # TP2 @ original RR
    partial_pnl = 0.0
    partial_shares = 0

    exit_price = None
    exit_time = None
    exit_reason = None

    for k in range(len(after)):
        bar = after.iloc[k]
        bt = after.index[k]
        ct = bt.time()

        # Partial TP logic
        if use_partial and not partial_done:
            if bar["High"] >= tp1:
                half = shares // 2
                if half > 0:
                    partial_eff = tp1 * (1 - SLIP_TP)
                    partial_pnl = (partial_eff - eff_entry) * half
                    partial_shares = half
                    partial_done = True
                    shares -= half
                    # After partial: move SL to ORB.high (community rule)
                    stop = max(stop, sig["orb_high"])

        # BE shift at 11:00 ET
        if ct >= BE_MOVE_TIME and not sl_moved:
            sl_moved = True
            stop = max(stop, be_price)

        if ct >= FORCE_CLOSE_TIME:
            exit_price = float(bar["Close"])
            exit_time = bt
            exit_reason = "time_force"
            break
        if bar["Low"] <= stop:
            exit_price = stop
            exit_time = bt
            exit_reason = "be_stop" if sl_moved else "stop_loss"
            break
        if bar["High"] >= target:
            exit_price = target
            exit_time = bt
            exit_reason = "take_profit"
            break

    if exit_price is None:
        exit_price = float(after.iloc[-1]["Close"])
        exit_time = after.index[-1]
        exit_reason = "eod"

    slip_exit = (SLIP_TP if exit_reason == "take_profit"
                 else SLIP_STOP if exit_reason in ("stop_loss", "be_stop")
                 else SLIP_TIME)
    eff_exit = exit_price * (1 - slip_exit)

    gross = (eff_exit - eff_entry) * shares
    if use_partial and partial_done:
        gross += partial_pnl
    total_shares = shares + partial_shares
    brokerage = (eff_entry * total_shares + eff_exit * shares + (tp1 * partial_shares if partial_done else 0)) * BROKERAGE
    sec_taf = (eff_exit * shares + (tp1 * partial_shares if partial_done else 0)) * SEC_RATE_SELL + total_shares * TAF_PER_SHARE_SELL
    comm = brokerage + sec_taf
    net = gross - comm
    r_mult = net / (risk_ps * total_shares) if risk_ps * total_shares > 0 else 0

    if exit_reason == "take_profit":
        result = "WIN"
    elif exit_reason in ("stop_loss", "be_stop"):
        result = "LOSS" if net < -0.01 else "BE"
    else:
        result = "WIN" if net > 0 else ("BE" if abs(net) < 0.5 else "LOSS")

    return Trade(
        variant=variant["name"],
        date=str(after.index[0].date()),
        entry_t=sig["entry_time"].strftime("%H:%M"),
        entry=round(eff_entry, 2),
        stop=round(sig["stop"], 2),
        target=round(target, 2),
        exit_t=exit_time.strftime("%H:%M"),
        exit_price=round(exit_price, 2),
        exit_reason=exit_reason,
        shares=total_shares,
        net_pnl=round(net, 2),
        r_multiple=round(r_mult, 2),
        result=result,
    )


# ─── Variants ───
VARIANTS = [
    {"name": "BASE_S_B",     "orb_window_min": 15, "sl_method": "prev_low",
     "partial_tp": False},
    {"name": "5m_ORB",       "orb_window_min": 5,  "sl_method": "prev_low",
     "partial_tp": False},
    {"name": "30m_ORB",      "orb_window_min": 30, "sl_method": "prev_low",
     "partial_tp": False},
    {"name": "SL_midpoint",  "orb_window_min": 15, "sl_method": "orb_midpoint",
     "partial_tp": False},
    {"name": "partial_TP",   "orb_window_min": 15, "sl_method": "prev_low",
     "partial_tp": True},
    {"name": "ADX_filter",   "orb_window_min": 15, "sl_method": "prev_low",
     "partial_tp": False, "require_adx": True},
    {"name": "VWAP_4H",      "orb_window_min": 15, "sl_method": "prev_low",
     "partial_tp": False, "require_vwap_alignment": True},
]


# ─── Runner ───
def run_variant(variant: dict, data: dict, days: list) -> dict:
    tqqq, qqq_d, vix_d = data["tqqq"], None, data["vix_d"]
    capital = INITIAL_CAPITAL
    trades: List[Trade] = []
    skipped = 0
    for d in days:
        # VIX filter (same as production)
        v = vix_d[vix_d.index.date <= d]
        if len(v) > 0:
            vv = float(v.iloc[-1]["Close"])
            if not (VIX_LOW <= vv <= VIX_HIGH):
                skipped += 1
                continue
        day_df = tqqq[tqqq["date"] == d]
        if len(day_df) < 20:
            continue
        sig = find_signal(day_df, {}, variant)
        if sig is None:
            continue
        trade = simulate(sig, day_df, capital, variant)
        if trade is None:
            continue
        capital += trade.net_pnl
        trades.append(trade)

    n = len(trades)
    if n == 0:
        return {"name": variant["name"], "n": 0, "wr": None, "pf": None,
                "total_ret_pct": 0.0, "trades": []}
    wins = sum(1 for t in trades if t.result == "WIN")
    losses = sum(1 for t in trades if t.result == "LOSS")
    win_sum = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    loss_sum = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    pf = win_sum / loss_sum if loss_sum > 0 else float("inf")
    final_cap = INITIAL_CAPITAL + sum(t.net_pnl for t in trades)
    total_ret = (final_cap - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    avg_r = float(np.mean([t.r_multiple for t in trades]))
    return {
        "name": variant["name"],
        "n": n,
        "wins": wins,
        "losses": losses,
        "wr": round(wins / n * 100, 1),
        "pf": round(pf, 2) if pf != float("inf") else None,
        "total_ret_pct": round(total_ret, 3),
        "avg_r": round(avg_r, 2),
        "trades": [asdict(t) for t in trades],
        "skipped_days": skipped,
    }


def main():
    data = fetch_data()
    days = sorted(data["tqqq"]["date"].unique())
    print(f"[main] common days: {len(days)}  range {days[0]} ~ {days[-1]}")

    results = []
    for v in VARIANTS:
        print(f"\n[run] {v['name']:<15s} window={v['orb_window_min']}m  sl={v['sl_method']}  "
              f"partial={v.get('partial_tp', False)}  adx={v.get('require_adx', False)}  "
              f"vwap={v.get('require_vwap_alignment', False)}")
        r = run_variant(v, data, days)
        results.append(r)
        if r["n"] == 0:
            print(f"      → 0 trades")
        else:
            print(f"      → n={r['n']}  WR={r['wr']}%  PF={r['pf']}  "
                  f"Ret={r['total_ret_pct']:+.2f}%  AvgR={r['avg_r']:+.2f}")

    # Summary table
    print("\n" + "=" * 88)
    print(f"{'Variant':<15s} {'Trd':>4s} {'WR%':>6s} {'PF':>6s} {'Ret%':>8s} {'AvgR':>6s} {'note':<30s}")
    print("-" * 88)
    for r in results:
        pf = r["pf"]
        pf_s = f"{pf:>5.2f}" if pf is not None else "  inf"
        print(f"{r['name']:<15s} {r['n']:>4d} "
              f"{r['wr']:>5.1f}{'' if r['wr'] is None else '%'} "
              f"{pf_s:>5s} "
              f"{r['total_ret_pct']:>+8.2f} "
              f"{r['avg_r']:>+6.2f}")

    out_path = os.path.join("scripts", "out", "casper_variants_results.json")
    with open(out_path, "w") as f:
        json.dump({"days": len(days), "results": results}, f, indent=2, default=str)
    print(f"\n[main] saved → {out_path}")


if __name__ == "__main__":
    main()
