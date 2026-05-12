#!/usr/bin/env python3
"""Phase 1 precheck — verify 3 ICT hypotheses on actual trades WITHOUT touching prod code.

Hypotheses:
  H1 (Displacement):  진입 시각 5분봉이 body>=1.0*ATR(14) AND wick<0.50 AND range>=2.0*prev5_range_mean
                      를 만족할수록 승률이 더 높은가?
  H2 (Confluence):    진입가가 PDH/PDL/PWH/PWL의 0.5% 이내일수록 승률이 더 높은가?
  H3 (Killzone):      AM_MACRO (09:30-10:10) vs AM_LATE (10:10-10:55) 의 승률/PF 차이는?

Data sources (read-only):
  - data/trades/trades_2026.json     : actual trades (11 trades)
  - data/marketdata/{SYMBOL}/...     : 5min Parquet (KIS + yfinance backfill)
"""

import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.store import load_bars  # noqa: E402
from src.data.calendar import trading_days  # noqa: E402


BASE = ROOT / "data" / "marketdata"
TRADES_PATH = ROOT / "data" / "trades" / "trades_2026.json"


# ──────────────── data loading ───────────────────
def load_trades():
    with open(TRADES_PATH) as f:
        return json.load(f)


def load_intraday(symbol: str, day: date) -> pd.DataFrame | None:
    df = load_bars(BASE, symbol, day.isoformat())
    if df is None or df.empty:
        return None
    # Convert stored UTC ms timestamp to ET
    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True).dt.tz_convert("US/Eastern")
    df = df.set_index("ts").sort_index()
    return df


def load_daily(symbol: str, end_day: date, lookback: int = 30) -> pd.DataFrame:
    """Daily OHLC reconstructed from 5m bars (RTH only)."""
    rows = []
    for d in trading_days(end_day - timedelta(days=lookback + 10), end_day - timedelta(days=1)):
        df = load_intraday(symbol, d)
        if df is None or df.empty:
            continue
        rth = df.between_time("09:30", "15:59")
        if rth.empty:
            continue
        rows.append({
            "date": d,
            "high": float(rth["high"].max()),
            "low": float(rth["low"].min()),
            "close": float(rth["close"].iloc[-1]),
        })
    return pd.DataFrame(rows)


# ──────────────── indicators ───────────────────
def atr14_at(bars: pd.DataFrame, ts: pd.Timestamp, symbol: str | None = None) -> float:
    """ATR(14) on 5m bars up to (not including) ts.

    If today's bars have < 15 entries (e.g. trade at 09:50), include the
    previous 2 trading days' RTH 5m bars to get a stable ATR.
    """
    bars = bars[bars.index < ts]
    if len(bars) >= 15:
        h = bars["high"]; l = bars["low"]; pc = bars["close"].shift(1)
        tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
        return float(tr.rolling(14).mean().iloc[-1])

    # need history — pull previous 3 trading days for the same symbol
    if symbol is None:
        return float("nan")
    day = ts.date()
    prev_days = trading_days(day - timedelta(days=10), day - timedelta(days=1))[-3:]
    history = []
    for d in prev_days:
        df = load_intraday(symbol, d)
        if df is not None and not df.empty:
            history.append(df.between_time("09:30", "15:59"))
    history.append(bars)
    combined = pd.concat(history).sort_index() if history else bars
    if len(combined) < 15:
        return float("nan")
    h = combined["high"]; l = combined["low"]; pc = combined["close"].shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return float(tr.rolling(14).mean().iloc[-1])


def prev5_range_mean_at(bars: pd.DataFrame, ts: pd.Timestamp) -> float:
    bars = bars[bars.index < ts]
    if len(bars) < 5:
        return float("nan")
    last5 = bars.tail(5)
    return float((last5["high"] - last5["low"]).mean())


def find_bar(bars: pd.DataFrame, entry_time_str: str, trade_date: date):
    """Find the 5m bar that contains entry_time_str ('HH:MM')."""
    hh, mm = map(int, entry_time_str.split(":"))
    target = pd.Timestamp(trade_date.isoformat()).tz_localize("US/Eastern") + pd.Timedelta(hours=hh, minutes=mm)
    # bar with index == target (5m aligned) or the bar containing this time
    cand = bars[(bars.index <= target)]
    if cand.empty:
        return None
    return cand.iloc[-1], cand.index[-1]


# ──────────────── hypothesis 1: Displacement ───────────────────
def check_displacement(bar) -> dict:
    body = abs(float(bar["close"]) - float(bar["open"]))
    total = float(bar["high"]) - float(bar["low"])
    wick = total - body
    wick_ratio = wick / total if total > 0 else 1.0
    return {
        "body": body,
        "total": total,
        "wick_ratio": wick_ratio,
    }


# ──────────────── hypothesis 2: Confluence ───────────────────
def confluence_levels(daily: pd.DataFrame) -> dict:
    """PDH, PDL, PWH (week high), PWL (week low) from last available days."""
    if daily.empty:
        return {}
    pdh = float(daily["high"].iloc[-1])
    pdl = float(daily["low"].iloc[-1])
    last_week = daily.tail(5)
    pwh = float(last_week["high"].max())
    pwl = float(last_week["low"].min())
    return {"PDH": pdh, "PDL": pdl, "PWH": pwh, "PWL": pwl}


def confluence_score(entry_price: float, levels: dict, max_pct: float = 0.005) -> tuple[int, list[str]]:
    near = []
    for name, lvl in levels.items():
        if entry_price <= 0 or lvl <= 0:
            continue
        if abs(entry_price - lvl) / entry_price <= max_pct:
            near.append(name)
    return len(near), near


# ──────────────── hypothesis 3: Killzone ───────────────────
def killzone_for(entry_time_str: str) -> str:
    hh, mm = map(int, entry_time_str.split(":"))
    minute_of_day = hh * 60 + mm
    if 9 * 60 + 30 <= minute_of_day <= 10 * 60 + 10:
        return "AM_MACRO"
    if 10 * 60 + 10 < minute_of_day <= 10 * 60 + 55:
        return "AM_LATE"
    return "OUTSIDE"


# ──────────────── main analysis ───────────────────
def analyze_trade(t: dict) -> dict:
    sym = t["symbol"]
    day = date.fromisoformat(t["date"])
    entry_time = t["entry_time"]
    entry_price = float(t["entry_price"])
    result = t["result"]
    r_mult = float(t["r_multiple"])

    bars = load_intraday(sym, day)
    daily = load_daily(sym, day, lookback=30)

    out = {
        "date": t["date"], "sym": sym, "time": entry_time,
        "entry": entry_price, "result": result, "R": r_mult,
        "killzone": killzone_for(entry_time),
    }

    if bars is None:
        out["error"] = "no_intraday_data"
        return out

    bar_row = find_bar(bars, entry_time, day)
    if bar_row is None:
        out["error"] = "bar_not_found"
        return out
    bar, bar_ts = bar_row

    # ── DISPLACEMENT ──
    # 캐스퍼 진입은 'FVG 중간점에서 pullback' — 즉 진입봉은 작은 봉이 정상.
    # Displacement 검증의 올바른 대상은 ORB 직후 ~ 진입봉 이전 사이의
    # 가장 큰 양봉 (FVG를 만든 displacement candle) 이다.
    atr = atr14_at(bars, bar_ts, symbol=sym)

    orb_end = pd.Timestamp(day.isoformat()).tz_localize("US/Eastern") + pd.Timedelta(hours=9, minutes=45)
    pre_entry = bars[(bars.index >= orb_end) & (bars.index < bar_ts)]
    if pre_entry.empty:
        out["disp_bar_time"] = None
        out["disp_body/atr"] = None
        out["disp_wick%"] = None
        out["displacement"] = False
    else:
        # 가장 body가 큰 양봉 (TQQQ Long FVG 가정) 또는 음봉 (SQQQ Long의 경우 SQQQ 자체 가격이 오르는 양봉)
        # 캐스퍼는 Long-only, FVG는 Bullish FVG 만 — 따라서 양봉 중 body 최대
        bullish = pre_entry[pre_entry["close"] > pre_entry["open"]].copy()
        if bullish.empty:
            disp_bar = None
        else:
            bullish["body"] = (bullish["close"] - bullish["open"]).abs()
            disp_bar = bullish.loc[bullish["body"].idxmax()]
        if disp_bar is None:
            out["disp_bar_time"] = None
            out["disp_body/atr"] = None
            out["disp_wick%"] = None
            out["displacement"] = False
        else:
            d_info = check_displacement(disp_bar)
            d_body_atr = d_info["body"] / atr if atr and not np.isnan(atr) else float("nan")
            out["disp_bar_time"] = disp_bar.name.strftime("%H:%M")
            out["disp_body/atr"] = round(d_body_atr, 2) if not np.isnan(d_body_atr) else None
            out["disp_wick%"] = round(d_info["wick_ratio"] * 100, 1)
            out["displacement"] = (
                d_body_atr is not None and not np.isnan(d_body_atr) and d_body_atr >= 1.0
                and d_info["wick_ratio"] < 0.50
            )

    out["atr"] = round(atr, 3) if not np.isnan(atr) else None

    # Confluence
    levels = confluence_levels(daily)
    if levels:
        cs, near = confluence_score(entry_price, levels, max_pct=0.005)
        out["levels"] = levels
        out["confluence_score"] = cs
        out["near"] = ",".join(near) if near else "-"
    else:
        out["confluence_score"] = None
        out["near"] = "no_daily"

    return out


def aggregate(rows):
    df = pd.DataFrame(rows)
    return df


def wr_pf(df: pd.DataFrame):
    """Win rate and profit factor on R-multiples."""
    if df.empty:
        return None, None, 0, 0, 0
    wins_n = int((df["result"] == "WIN").sum())
    losses_n = int((df["result"] == "LOSS").sum())
    bes_n = int(df["result"].isin(["BE"]).sum())
    n = len(df)
    wr = wins_n / n * 100 if n else 0
    win_sum = df.loc[df["R"] > 0, "R"].sum()
    loss_sum = abs(df.loc[df["R"] < 0, "R"].sum())
    pf = (win_sum / loss_sum) if loss_sum > 0 else float("inf")
    return wr, pf, wins_n, losses_n, bes_n


def main():
    print("=" * 90)
    print("  Phase 1 Precheck — ICT Hypotheses on Actual Casper Trades")
    print("=" * 90)

    trades = load_trades()
    print(f"\nLoaded {len(trades)} trades from {TRADES_PATH.name}")

    rows = []
    for t in trades:
        rows.append(analyze_trade(t))

    df = aggregate(rows)

    # Save raw per-trade analysis
    out_dir = ROOT / "scripts" / "out"
    out_dir.mkdir(exist_ok=True)
    df.to_csv(out_dir / "phase1_precheck_raw.csv", index=False)
    print(f"\nSaved per-trade analysis → {out_dir / 'phase1_precheck_raw.csv'}")

    # ─── Per-trade table ───
    print("\n" + "─" * 90)
    print("  Per-trade analysis")
    print("─" * 90)
    cols = ["date", "sym", "time", "entry", "result", "R",
            "disp_bar_time", "disp_body/atr", "disp_wick%", "displacement",
            "confluence_score", "near", "killzone"]
    print(df[cols].to_string(index=False))

    # ─── H1 Displacement ───
    print("\n" + "═" * 90)
    print("  H1: DISPLACEMENT (body≥1.0×ATR AND wick<50% AND range≥2.0×prev5)")
    print("═" * 90)

    disp_yes = df[df["displacement"] == True]
    disp_no = df[df["displacement"] == False]
    for label, sub in [("Displacement ✅", disp_yes), ("Displacement ❌", disp_no)]:
        wr, pf, w, l, be = wr_pf(sub)
        if not sub.empty:
            avg_r = sub["R"].mean()
            print(f"  {label}: n={len(sub)}  W/L/BE={w}/{l}/{be}  WR={wr:.1f}%  PF={pf:.2f}  AvgR={avg_r:+.2f}")
        else:
            print(f"  {label}: n=0")

    # Looser/strict variants
    print("\n  파라미터 민감도 (displacement bar 대상):")
    df_d = df.dropna(subset=["disp_body/atr"])
    for body_thr in [0.5, 0.7, 1.0, 1.3, 1.5]:
        for wick_thr in [0.40, 0.50, 0.60]:
            sub = df_d[(df_d["disp_body/atr"] >= body_thr) & (df_d["disp_wick%"] / 100 < wick_thr)]
            if len(sub) > 0:
                wr, pf, w, l, be = wr_pf(sub)
                avg_r = sub["R"].mean()
                print(f"    body≥{body_thr}×ATR + wick<{int(wick_thr*100)}%: "
                      f"n={len(sub):>2}  W/L/BE={w}/{l}/{be}  WR={wr:>5.1f}%  PF={pf:>5.2f}  AvgR={avg_r:+.2f}")

    # ─── H2 Confluence ───
    print("\n" + "═" * 90)
    print("  H2: PDH/PDL/PWH/PWL CONFLUENCE (within 0.5% of entry price)")
    print("═" * 90)
    for score in sorted(df["confluence_score"].dropna().unique()):
        sub = df[df["confluence_score"] == score]
        wr, pf, w, l, be = wr_pf(sub)
        avg_r = sub["R"].mean()
        print(f"  score={int(score)}: n={len(sub)}  W/L/BE={w}/{l}/{be}  WR={wr:.1f}%  PF={pf:.2f}  AvgR={avg_r:+.2f}")

    # Wider band 1%
    print("\n  더 넓은 1% 밴드:")
    rows2 = []
    for t in trades:
        sym = t["symbol"]; day = date.fromisoformat(t["date"])
        daily = load_daily(sym, day, lookback=30)
        lvls = confluence_levels(daily)
        if not lvls:
            rows2.append({**t, "score1pct": None})
            continue
        cs, _ = confluence_score(float(t["entry_price"]), lvls, max_pct=0.01)
        rows2.append({**t, "score1pct": cs})
    df2 = pd.DataFrame(rows2)
    df2["R"] = df2["r_multiple"]
    for score in sorted(df2["score1pct"].dropna().unique()):
        sub = df2[df2["score1pct"] == score]
        wr, pf, w, l, be = wr_pf(sub)
        avg_r = sub["R"].mean()
        print(f"  score={int(score)} (1%): n={len(sub)}  W/L/BE={w}/{l}/{be}  WR={wr:.1f}%  PF={pf:.2f}  AvgR={avg_r:+.2f}")

    # ─── H3 Killzone ───
    print("\n" + "═" * 90)
    print("  H3: KILLZONE  (AM_MACRO 09:30-10:10  vs  AM_LATE 10:10-10:55)")
    print("═" * 90)
    for zone in ["AM_MACRO", "AM_LATE", "OUTSIDE"]:
        sub = df[df["killzone"] == zone]
        if sub.empty:
            print(f"  {zone}: (no trades)")
            continue
        wr, pf, w, l, be = wr_pf(sub)
        avg_r = sub["R"].mean()
        print(f"  {zone}: n={len(sub)}  W/L/BE={w}/{l}/{be}  WR={wr:.1f}%  PF={pf:.2f}  AvgR={avg_r:+.2f}")

    # ─── Combined filter recommendation ───
    print("\n" + "═" * 90)
    print("  COMBINED:  displacement ✅ AND killzone in {AM_MACRO}")
    print("═" * 90)
    sub = df[(df["displacement"] == True) & (df["killzone"] == "AM_MACRO")]
    if not sub.empty:
        wr, pf, w, l, be = wr_pf(sub)
        avg_r = sub["R"].mean()
        print(f"  n={len(sub)}  W/L/BE={w}/{l}/{be}  WR={wr:.1f}%  PF={pf:.2f}  AvgR={avg_r:+.2f}")
        print(sub[cols].to_string(index=False))
    else:
        print("  n=0 (no trades pass both filters)")


if __name__ == "__main__":
    main()
