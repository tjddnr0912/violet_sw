#!/usr/bin/env python3
"""Phase 5.0 — Range Expansion data analysis (read-only).

Question: For each historical Casper trade (live + 60d backtest), was the
prevailing 1H or 4H expansion direction *aligned* with the trade's
direction? This is the prerequisite check before deciding whether to
build a Range Expansion filter (Phase 5.1+).

Sources:
  - Live trades: data/trades/trades_2026.json (current 11 entries)
  - Backtest candidates: rerun scan logic on 60d yfinance (≤ 4 typical)

For each trade or candidate:
  fetch 1H bars covering the prior 12 hours
  fetch 4H bars covering the prior 48 hours
  detect most recent expansion candle in each timeframe
  classify alignment: aligned / misaligned / no-expansion

Output:
  scripts/out/range_expansion_analysis.{json,csv}
  Console report with per-trade verdict + aggregate alignment rate
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytz
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")


ET = pytz.timezone("US/Eastern")


# ─── Expansion candle definition ─────────────────────────────────
def _eval_candle(candle, prev_window, min_body_range_ratio, min_body_avg_ratio, max_wick):
    """Return diagnostic dict if `candle` qualifies as expansion, else None."""
    body = abs(float(candle["Close"]) - float(candle["Open"]))
    total = float(candle["High"]) - float(candle["Low"])
    if total <= 0:
        return None
    wick_ratio = (total - body) / total
    if wick_ratio >= max_wick:
        return None
    range_high = float(prev_window["Close"].max())
    range_low = float(prev_window["Close"].min())
    range_size = range_high - range_low
    if range_size <= 0:
        return None
    if body < range_size * min_body_range_ratio:
        return None
    avg_body = (prev_window["Close"] - prev_window["Open"]).abs().mean()
    if avg_body > 0 and body < avg_body * min_body_avg_ratio:
        return None
    direction = "bull" if float(candle["Close"]) > float(candle["Open"]) else "bear"
    return {
        "direction": direction,
        "body": round(body, 4),
        "range_size": round(range_size, 4),
        "body_range_ratio": round(body / range_size, 3),
        "avg_body": round(float(avg_body), 4),
        "body_avg_ratio": round(body / avg_body, 3) if avg_body > 0 else None,
        "wick_ratio": round(wick_ratio, 3),
    }


def detect_expansion(
    bars: pd.DataFrame,
    range_period: int = 10,
    min_body_range_ratio: float = 1.5,
    min_body_avg_ratio: float = 2.0,
    max_wick: float = 0.40,
) -> Optional[dict]:
    """Find the *most recent* expansion candle by scanning bars backward.

    For each position i (from latest backward), the candle is evaluated
    against the `range_period` candles preceding it. The first qualifying
    candle (newest) is returned.
    """
    if bars is None or len(bars) < range_period + 2:
        return None
    # Scan from newest to oldest, requiring `range_period` prior candles
    for i in range(len(bars) - 1, range_period - 1, -1):
        candle = bars.iloc[i]
        prev_window = bars.iloc[i - range_period:i]
        result = _eval_candle(candle, prev_window,
                              min_body_range_ratio, min_body_avg_ratio, max_wick)
        if result is not None:
            result["candle_time"] = str(bars.index[i])
            result["bars_ago"] = len(bars) - 1 - i
            return result
    return None


# ─── Data fetch helpers ───────────────────────────────────────────
def fetch_htf(symbol: str, interval: str = "1h", period: str = "60d") -> pd.DataFrame:
    """Fetch HTF bars from yfinance and normalise to ET tz."""
    df = yf.download(symbol, period=period, interval=interval,
                     progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = [c[0] for c in df.columns]
    if df.empty:
        return df
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df.index = df.index.tz_convert(ET)
    return df


def bars_before(df: pd.DataFrame, ts: pd.Timestamp, n_bars: int = 14) -> pd.DataFrame:
    """Return the most recent `n_bars` rows of `df` strictly before `ts`.

    Wall-clock hours are unreliable because RTH skips overnight + weekend.
    We instead grab the last N bars by index — guarantees sufficient data
    for range/expansion detection regardless of when the trade fired.
    """
    if df.empty:
        return df
    cutoff = ts.tz_convert(ET) if ts.tzinfo else ET.localize(ts)
    sub = df[df.index < cutoff]
    return sub.tail(n_bars)


# ─── Trade source loaders ─────────────────────────────────────────
@dataclass
class TradeRow:
    source: str
    date: str          # YYYY-MM-DD (ET)
    symbol: str
    direction: str     # bull | bear (mapped from long/short)
    entry_time_iso: str
    note: str = ""


def load_live_trades(path: str = "data/trades/trades_2026.json") -> List[TradeRow]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    rows: List[TradeRow] = []
    for t in data:
        if not isinstance(t, dict):
            continue
        sym = t.get("symbol", "?")
        date = t.get("date", "")
        entry_t = t.get("entry_t") or t.get("entry_time", "")
        side = t.get("direction") or t.get("side", "long")
        # All live trades so far are "long" — map to bull. If short → bear.
        direction = "bear" if side == "short" else "bull"
        # Build ET timestamp for HTF query
        try:
            entry_dt = ET.localize(datetime.fromisoformat(f"{date}T{entry_t}:00"))
        except Exception:
            try:
                entry_dt = ET.localize(datetime.strptime(date, "%Y-%m-%d"))
            except Exception:
                continue
        rows.append(TradeRow(
            source="live",
            date=date,
            symbol=sym,
            direction=direction,
            entry_time_iso=entry_dt.isoformat(),
            note=f"R={t.get('r_multiple')}",
        ))
    return rows


def load_backtest_candidates(symbols=("TQQQ",)) -> List[TradeRow]:
    """Re-run the strategy on 60d yfinance to identify backtest candidates."""
    rows: List[TradeRow] = []
    for sym in symbols:
        df = yf.download(sym, period="60d", interval="5m",
                         progress=False, auto_adjust=False)
        if isinstance(df.columns, pd.MultiIndex):
            df = df.copy()
            df.columns = [c[0] for c in df.columns]
        if df.empty:
            continue
        df.index = df.index.tz_convert(ET)
        df["date"] = df.index.date
        for d in sorted(set(df["date"])):
            day_df = df[df["date"] == d]
            if len(day_df) < 20:
                continue
            orb = day_df.between_time("09:30", "09:44")
            if len(orb) < 3:
                continue
            orb_high = float(orb["High"].max())
            post = day_df.between_time("09:45", "10:55")
            if len(post) < 4:
                continue
            for i in range(1, len(post) - 1):
                c = post.iloc[i]
                if not (c["Close"] > orb_high and c["Close"] > c["Open"]):
                    continue
                if not (c["Open"] <= orb_high <= c["Close"]):
                    continue
                # Bullish FVG (c_prev.High < c_next.Low)
                c_prev = post.iloc[i - 1]
                c_next = post.iloc[i + 1]
                if c_prev["High"] >= c_next["Low"]:
                    continue
                if not (c_prev["High"] <= orb_high <= c_next["Low"]):
                    continue
                ts = post.index[i]
                rows.append(TradeRow(
                    source="backtest",
                    date=str(d),
                    symbol=sym,
                    direction="bull",
                    entry_time_iso=ts.isoformat(),
                    note="5m ORB+FVG strict candidate",
                ))
                break  # one per day
    return rows


# ─── Per-trade alignment check ────────────────────────────────────
@dataclass
class AlignmentResult:
    source: str
    date: str
    symbol: str
    direction: str
    entry_time_iso: str
    note: str
    expansion_1h: Optional[dict]
    expansion_4h: Optional[dict]
    aligned_1h: Optional[bool]
    aligned_4h: Optional[bool]


def analyze_trade(t: TradeRow, htf_1h: pd.DataFrame, htf_4h: pd.DataFrame) -> AlignmentResult:
    """For one trade, check 1H and 4H expansion alignment."""
    try:
        ts = pd.Timestamp(t.entry_time_iso)
    except Exception:
        return AlignmentResult(
            source=t.source, date=t.date, symbol=t.symbol,
            direction=t.direction, entry_time_iso=t.entry_time_iso,
            note=t.note, expansion_1h=None, expansion_4h=None,
            aligned_1h=None, aligned_4h=None,
        )
    # Lookback window for finding the most recent expansion. Larger
    # window → more chance of catching one. Casper teaching: "look at
    # the dominant move of the last few sessions."
    sub_1h = bars_before(htf_1h, ts, n_bars=40)   # ~6 RTH days
    exp_1h = detect_expansion(sub_1h, range_period=10)
    aligned_1h = (exp_1h["direction"] == t.direction) if exp_1h else None

    sub_4h = bars_before(htf_4h, ts, n_bars=30)   # ~15 RTH days
    exp_4h = detect_expansion(sub_4h, range_period=8)
    aligned_4h = (exp_4h["direction"] == t.direction) if exp_4h else None

    return AlignmentResult(
        source=t.source, date=t.date, symbol=t.symbol,
        direction=t.direction, entry_time_iso=t.entry_time_iso,
        note=t.note, expansion_1h=exp_1h, expansion_4h=exp_4h,
        aligned_1h=aligned_1h, aligned_4h=aligned_4h,
    )


# ─── Main ─────────────────────────────────────────────────────────
def summarize(results: List[AlignmentResult]) -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0}

    def count(field):
        a = sum(1 for r in results if getattr(r, field) is True)
        m = sum(1 for r in results if getattr(r, field) is False)
        z = sum(1 for r in results if getattr(r, field) is None)
        return {"aligned": a, "misaligned": m, "no_expansion": z}

    return {
        "n": n,
        "1h": count("aligned_1h"),
        "4h": count("aligned_4h"),
    }


def main():
    print("=" * 80)
    print("  Phase 5.0 — Range Expansion data analysis")
    print("=" * 80)

    # 1. load trades
    live = load_live_trades()
    print(f"[trades] live: {len(live)}")
    print(f"[trades] (also re-running 60d backtest to identify candidates)")
    backtest = load_backtest_candidates()
    print(f"[trades] backtest candidates: {len(backtest)}")

    all_trades = live + backtest
    if not all_trades:
        print("No trades to analyze.")
        return

    # 2. fetch HTF data (use QQQ as the HTF reference for all — best proxy
    # since TQQQ tracks NDX 3x and HTF direction is the same; matches the
    # Casper "QQQ chart as signal source" philosophy)
    print("\n[data] fetching HTF — QQQ 1h + 4h (60d) …")
    htf_1h = fetch_htf("QQQ", interval="1h", period="60d")
    htf_4h = fetch_htf("QQQ", interval="4h", period="60d")
    print(f"[data] 1h bars: {len(htf_1h)}  4h bars: {len(htf_4h)}")

    # 3. analyze
    results = []
    for t in all_trades:
        r = analyze_trade(t, htf_1h, htf_4h)
        results.append(r)

    # 4. print
    print("\n" + "─" * 88)
    print(f"{'Source':<10s} {'Date':<12s} {'Sym':<5s} {'Dir':<5s} {'Entry':<22s} "
          f"{'1H exp':<12s} {'1H aln':<7s} {'4H exp':<12s} {'4H aln':<7s}")
    print("─" * 88)
    for r in results:
        e1 = r.expansion_1h["direction"] if r.expansion_1h else "—"
        e4 = r.expansion_4h["direction"] if r.expansion_4h else "—"
        a1 = ("✓" if r.aligned_1h else ("✗" if r.aligned_1h is False else "—"))
        a4 = ("✓" if r.aligned_4h else ("✗" if r.aligned_4h is False else "—"))
        print(f"{r.source:<10s} {r.date:<12s} {r.symbol:<5s} {r.direction:<5s} "
              f"{r.entry_time_iso[:19]:<22s} {e1:<12s} {a1:<7s} {e4:<12s} {a4:<7s}")

    # 5. summary
    print("\n" + "─" * 88)
    summary = summarize(results)
    print(f"{'Total trades':<25s}: {summary['n']}")
    for tf in ("1h", "4h"):
        s = summary[tf]
        denom = max(s["aligned"] + s["misaligned"], 1)
        rate = s["aligned"] / denom * 100
        print(f"{'  ' + tf + ' aligned':<25s}: {s['aligned']} / "
              f"{s['aligned'] + s['misaligned']} ({rate:.1f}%)  "
              f"[no_exp: {s['no_expansion']}]")

    # 6. interpretation guidance
    print("\n" + "─" * 88)
    print("INTERPRETATION GUIDE:")
    print("  - aligned ≥ 70%  → Range Expansion would have REJECTED few trades;")
    print("                     consider Phase 5.1 build (filter complements existing rules)")
    print("  - aligned ≈ 50%  → no signal; expansion direction is essentially random")
    print("                     wrt Casper setup direction → skip Phase 5")
    print("  - aligned ≤ 30%  → COUNTER-correlation; trades fade expansion direction")
    print("                     → invert filter or reject")
    print("  - n < 10         → sample too small for any verdict; postpone")

    # 7. save
    out_dir = Path("scripts/out")
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(r) for r in results]).to_csv(
        out_dir / "range_expansion_analysis.csv", index=False
    )
    with open(out_dir / "range_expansion_analysis.json", "w") as f:
        json.dump({
            "summary": summary,
            "results": [asdict(r) for r in results],
        }, f, indent=2, default=str)
    print(f"\n[main] saved → scripts/out/range_expansion_analysis.{{csv,json}}")


if __name__ == "__main__":
    main()
