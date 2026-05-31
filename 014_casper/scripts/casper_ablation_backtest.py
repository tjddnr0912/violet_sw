#!/usr/bin/env python3
"""Casper signal ABLATION — filter-by-filter funnel (self-contained).

User question (2026-05-30): early Casper used a LOOSER rule where ORB breakout
and FVG were NOT an AND condition (breakout in one bar, an FVG forming separately
was OK) — it traded more and won more. Quantify how trade count / net / win rate
move as we start from the loosest rule and add each filter one at a time.

Self-contained (own yfinance download + ORB/FVG/ATR + intraday simulator with the
KIS cost model) so it does NOT depend on the legacy casper_variants_backtest.py,
which breaks under pandas 3.0. Cost constants match that module exactly.

Data: yfinance 5-minute TQQQ bull-only, ~60 days (yfinance hard limit).
Caveat: 60-day single-regime, low statistical power. Measures the FUNNEL SHAPE
(frequency vs win-rate trade-off per filter), not a deployable edge. Heavy ICT
filters (sweep+CHoCH/OTE/unicorn/daily-bias) are NOT modeled — see
CASPER_IMPROVEMENT_STUDY §4 (sweep+CHoCH pass-rate 4.1% -> frequency ~ 0).
"""
from __future__ import annotations

import os
import sys
import json
from datetime import time as dtime

import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "out", "casper_ablation_results.json")

# KIS cost model (identical to casper_variants_backtest.py)
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
ORB_END = "09:45"           # 15-minute opening range
SCAN_START, SCAN_END = "09:45", "10:55"


def fetch():
    tqqq = yf.download("TQQQ", period="60d", interval="5m",
                       progress=False, auto_adjust=False)
    vix = yf.download("^VIX", period="6mo", interval="1d",
                      progress=False, auto_adjust=False)
    tqqq = tqqq.copy()
    if isinstance(tqqq.columns, pd.MultiIndex):
        tqqq.columns = tqqq.columns.get_level_values(0)
    vix = vix.copy()
    if isinstance(vix.columns, pd.MultiIndex):
        vix.columns = vix.columns.get_level_values(0)
    idx = pd.DatetimeIndex(tqqq.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    tqqq.index = idx.tz_convert("US/Eastern")
    vix.index = pd.DatetimeIndex(vix.index)
    return tqqq, vix


def atr14(bars):
    if len(bars) < 15:
        return None
    h, l, pc = bars["High"], bars["Low"], bars["Close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    v = tr.rolling(14).mean().iloc[-1]
    return float(v) if pd.notna(v) and v > 0 else None


def compute_orb(day_df):
    o = day_df.between_time("09:30", ORB_END)
    if len(o) < 2:
        return None
    return float(o["High"].max()), float(o["Low"].min())


def bullish_fvg(c1, c3):
    """3-candle bullish FVG: gap between c1.High and c3.Low. Returns (top,bot)."""
    if float(c1["High"]) < float(c3["Low"]):
        return float(c3["Low"]), float(c1["High"])
    return None


def find_signal(day_df, filters: set):
    orb = compute_orb(day_df)
    if orb is None:
        return None
    orb_h, orb_l = orb
    orb_mid = (orb_h + orb_l) / 2
    post = day_df.between_time(SCAN_START, SCAN_END)
    if len(post) < 4:
        return None
    atr_val = atr14(day_df)

    fvg_anywhere = False
    if "fvg_decoupled" in filters:
        for k in range(1, len(post) - 1):
            if bullish_fvg(post.iloc[k - 1], post.iloc[k + 1]) is not None:
                fvg_anywhere = True
                break

    for i in range(1, len(post) - 1):
        c = post.iloc[i]
        if not (float(c["Close"]) > orb_h and float(c["Close"]) > float(c["Open"])):
            continue
        if "straddle_strict" in filters and not (float(c["Open"]) <= orb_h <= float(c["Close"])):
            continue
        if "displacement" in filters:
            body = float(c["Close"]) - float(c["Open"])
            total = float(c["High"]) - float(c["Low"])
            wick = (total - body) / total if total > 0 else 1.0
            if wick >= 0.50:
                continue
            if atr_val and body < atr_val:
                continue

        fvg = None
        need_bar_fvg = bool({"fvg_and", "straddle_strict", "pullback"} & filters)
        if need_bar_fvg:
            fvg = bullish_fvg(post.iloc[i - 1], post.iloc[i + 1])
            if fvg is None:
                continue
            if "straddle_strict" in filters and not (fvg[1] <= orb_h <= fvg[0]):
                continue
        elif "fvg_decoupled" in filters and not fvg_anywhere:
            return None

        # loose_pullback: breakout happened; enter on a retrace into the FIRST
        # bullish FVG that forms anywhere from the breakout bar onward (decoupled,
        # no displacement/straddle). Closest to the early 'loose' bot the user recalls.
        if "loose_pullback" in filters:
            fvg2 = None
            for j in range(i, len(post) - 1):
                f = bullish_fvg(post.iloc[j - 1], post.iloc[j + 1])
                if f is not None:
                    fvg2 = (f, post.index[j + 1])
                    break
            if fvg2 is None:
                continue
            (ft, fb), anchor_t = fvg2
            entry = (ft + fb) / 2
            stop = fb            # FVG bottom as stop (loose SMC entry)
            risk = entry - stop
            if risk < MIN_RISK:
                continue
            bt = post.index[i].time()
            rr = 3.0 if dtime(9, 30) <= bt < dtime(10, 10) else (2.0 if bt < dtime(10, 55) else None)
            if rr is None:
                continue
            target = entry + risk * rr
            after = day_df[day_df.index > anchor_t].between_time("09:45", "15:50")
            for k2 in range(len(after)):
                if float(after.iloc[k2]["Low"]) <= ft:
                    return dict(entry_time=after.index[k2], entry=entry, stop=stop,
                                target=target, risk=risk, orb_high=orb_h)
            return None

        entry = ((fvg[0] + fvg[1]) / 2) if ("pullback" in filters and fvg) else float(c["Close"])
        stop = float(post.iloc[i - 1]["Low"])
        risk = entry - stop
        if risk < MIN_RISK:
            continue

        bt = post.index[i].time()
        if dtime(9, 30) <= bt < dtime(10, 10):
            rr = 3.0
        elif dtime(10, 10) <= bt < dtime(10, 55):
            rr = 2.0
        else:
            continue
        target = entry + risk * rr

        if "pullback" in filters and fvg:
            after = day_df[day_df.index > post.index[i + 1]].between_time("09:45", "15:50")
            for j in range(len(after)):
                if float(after.iloc[j]["Low"]) <= fvg[0]:
                    return dict(entry_time=after.index[j], entry=entry, stop=stop,
                                target=target, risk=risk, orb_high=orb_h)
            return None
        nxt = day_df[day_df.index > post.index[i]]
        if len(nxt) == 0:
            continue
        return dict(entry_time=nxt.index[0], entry=entry, stop=stop,
                    target=target, risk=risk, orb_high=orb_h)
    return None


def simulate(sig, day_df, capital=INITIAL_CAPITAL, partial=True):
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
    stop, target = sig["stop"], sig["target"]
    sl_moved = partial_done = False
    tp1 = sig["entry"] + risk_ps * 1.5
    partial_pnl = 0.0
    partial_shares = 0
    exit_price = exit_reason = None

    for k in range(len(after)):
        bar = after.iloc[k]
        ct = after.index[k].time()
        if partial and not partial_done and float(bar["High"]) >= tp1:
            half = shares // 2
            if half > 0:
                partial_pnl = (tp1 * (1 - SLIP_TP) - eff_entry) * half
                partial_shares = half
                partial_done = True
                shares -= half
                stop = max(stop, sig["orb_high"])
        if ct >= BE_MOVE_TIME and not sl_moved:
            sl_moved = True
            stop = max(stop, be_price)
        if ct >= FORCE_CLOSE_TIME:
            exit_price, exit_reason = float(bar["Close"]), "time_force"
            break
        if float(bar["Low"]) <= stop:
            exit_price, exit_reason = stop, ("be_stop" if sl_moved else "stop_loss")
            break
        if float(bar["High"]) >= target:
            exit_price, exit_reason = target, "take_profit"
            break
    if exit_price is None:
        exit_price, exit_reason = float(after.iloc[-1]["Close"]), "eod"

    slip = (SLIP_TP if exit_reason == "take_profit"
            else SLIP_STOP if exit_reason in ("stop_loss", "be_stop") else SLIP_TIME)
    eff_exit = exit_price * (1 - slip)
    gross = (eff_exit - eff_entry) * shares + (partial_pnl if partial_done else 0.0)
    total_sh = shares + partial_shares
    brokerage = (eff_entry * total_sh + eff_exit * shares
                 + (tp1 * partial_shares if partial_done else 0)) * BROKERAGE
    sec_taf = ((eff_exit * shares + (tp1 * partial_shares if partial_done else 0)) * SEC_RATE_SELL
               + total_sh * TAF_PER_SHARE_SELL)
    net = gross - brokerage - sec_taf
    return dict(date=str(after.index[0].date()), net=round(net, 2),
                reason=exit_reason, win=(net > 0))


LADDER = [
    ("R0 breakout-only (no FVG)",       set()),
    ("R1 +FVG decoupled (early loose)", {"fvg_decoupled"}),
    ("R1b loose-pullback (decoupled FVG entry)", {"loose_pullback"}),
    ("R2 +FVG on breakout bar (AND)",   {"fvg_and"}),
    ("R3 +displacement",                {"fvg_and", "displacement"}),
    ("R4 +straddle/strict FVG",         {"fvg_and", "displacement", "straddle_strict"}),
    ("R5 +pullback entry",              {"fvg_and", "displacement", "straddle_strict", "pullback"}),
    ("R6 +VIX gate [12,30]",            {"fvg_and", "displacement", "straddle_strict", "pullback", "_vix"}),
    ("R7 +ORB-width gate <=1.5ATR",     {"fvg_and", "displacement", "straddle_strict", "pullback", "_vix", "_orbw"}),
]


def run_rung(filters, tqqq, vix):
    use_vix = "_vix" in filters
    use_orbw = "_orbw" in filters
    sigf = {f for f in filters if not f.startswith("_")}
    trades = []
    for d, day_df in tqqq.groupby(tqqq.index.date):
        if len(day_df) < 20:
            continue
        if use_vix:
            v = vix[vix.index.date <= d]
            if len(v) and not (VIX_LOW <= float(v.iloc[-1]["Close"]) <= VIX_HIGH):
                continue
        if use_orbw:
            orb = compute_orb(day_df)
            a = atr14(day_df)
            if orb and a and (orb[0] - orb[1]) > 1.5 * a:
                continue
        sig = find_signal(day_df, sigf)
        if sig is None:
            continue
        tr = simulate(sig, day_df)
        if tr:
            trades.append(tr)
    return aggregate(trades)


def aggregate(trades):
    n = len(trades)
    if n == 0:
        return dict(n=0, win_rate_pct=None, net_usd=0.0, net_pct=0.0,
                    profit_factor=None, drop_top1=0.0, drop_top2=0.0, drop_top3=0.0,
                    by_month={})
    nets = [t["net"] for t in trades]
    wins = [x for x in nets if x > 0]
    ws = sum(wins)
    ls = -sum(x for x in nets if x <= 0)
    pf = (ws / ls) if ls > 0 else None
    srt = sorted(nets, reverse=True)
    tot = sum(nets)
    bym = {}
    for t in trades:
        bym.setdefault(t["date"][:7], 0.0)
        bym[t["date"][:7]] += t["net"]
    return dict(
        n=n, win_rate_pct=round(len(wins) / n * 100, 1),
        net_usd=round(tot, 2), net_pct=round(tot / INITIAL_CAPITAL * 100, 2),
        profit_factor=(round(pf, 2) if pf else None),
        drop_top1=round(tot - sum(srt[:1]), 2),
        drop_top2=round(tot - sum(srt[:2]), 2),
        drop_top3=round(tot - sum(srt[:3]), 2),
        by_month={k: round(v, 2) for k, v in sorted(bym.items())},
    )


def main():
    tqqq, vix = fetch()
    days = sorted(set(tqqq.index.date))
    rows = []
    print("=== CASPER ABLATION (TQQQ %dd 5m, $%.0f/trade, KIS 0.25%%/side) ==="
          % (len(days), INITIAL_CAPITAL))
    print("%-34s %4s %6s %9s %7s %7s %9s %9s %9s" %
          ("rung", "n", "WR%", "net$", "net%", "PF", "dropTop1", "dropTop2", "dropTop3"))
    for label, filters in LADDER:
        r = run_rung(filters, tqqq, vix)
        rows.append({"rung": label, **r})
        wr = "-" if r["win_rate_pct"] is None else "%.1f" % r["win_rate_pct"]
        pf = "-" if r["profit_factor"] is None else "%.2f" % r["profit_factor"]
        print("%-34s %4d %6s %9.2f %7.2f %7s %9.2f %9.2f %9.2f" %
              (label, r["n"], wr, r["net_usd"], r["net_pct"], pf,
               r["drop_top1"], r["drop_top2"], r["drop_top3"]))
    out = {"meta": {"symbol": "TQQQ", "trading_days": len(days),
                    "date_range": [str(days[0]), str(days[-1])],
                    "capital_per_trade": INITIAL_CAPITAL,
                    "cost_model": "KIS 0.25%/side + slip + SEC/TAF, partial-TP on",
                    "scope": "TQQQ bull-only 60d 5m; heavy ICT stack not modeled"},
           "rungs": rows}
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print("\n=== monthly net$ (R0, R1, R5) ===")
    for r in rows:
        if r["rung"][:2] in ("R0", "R1", "R5"):
            print("%-34s %s" % (r["rung"], r["by_month"]))
    print("\nWrote", OUT_JSON)


if __name__ == "__main__":
    main()
