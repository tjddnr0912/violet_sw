#!/usr/bin/env python3
"""Displacement filter — reject distribution + threshold sensitivity.

Two data sources, combinable:

  --source backtest   yfinance 60d 5m × {TQQQ, QQQ, SQQQ} → simulate every
                      ORB breakout + FVG candidate and evaluate the
                      displacement criteria. Records *every* candidate's
                      diagnostic (body, atr14, body_atr_ratio, wick_ratio)
                      regardless of pass/fail.
  --source live       Aggregate `data/ict_decisions/*.jsonl` displacement
                      events from the live bot. Captures every reject the
                      bot has seen in production.
  --source both       Union of the above.

Output:
  - Console histogram of body_atr_ratio (10 buckets in [0, 2])
  - Borderline analysis: counts of [0.85, 1.00) — would-pass if threshold
    were lowered from 1.0 to 0.85
  - `scripts/out/displacement_distribution_{source}.csv`  raw rows
  - `scripts/out/displacement_distribution_{source}.json` summary

The script is read-only — does NOT modify bot config or ICT thresholds.
Its purpose is to provide the data Plan-C ("threshold re-evaluation after
1-3 months of accumulation") will eventually use.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, time as dtime
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytz
import yfinance as yf

from src.core.orb import OpeningRange
from src.core.fvg import check_breakout_with_fvg, check_breakdown_with_fvg
from src.core.displacement import atr14, is_displacement
from src.core.sessions import killzone_for, KILLZONES


ET = pytz.timezone("US/Eastern")


# ───────────────────────── Record schema ─────────────────────────
@dataclass
class DispRecord:
    source: str            # "backtest" | "live"
    date: str              # YYYY-MM-DD
    bar_time: str          # ISO with offset
    symbol: str            # TQQQ / QQQ / SQQQ
    direction: str         # bull | bear
    killzone: Optional[str]    # AM_MACRO / AM_LATE / None
    body: float
    atr14: Optional[float]
    body_atr_ratio: Optional[float]
    wick_ratio: float
    passes_default: bool   # passes the current production threshold (1.0, 0.50, 1.5)
    notes: str = ""


# ───────────────────────── Backtest source ─────────────────────────
def fetch_5m(symbol: str) -> pd.DataFrame:
    df = yf.download(symbol, period="60d", interval="5m",
                     progress=False, auto_adjust=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df.index = df.index.tz_convert("US/Eastern")
    df["date"] = df.index.date
    return df


def compute_orb(day_df: pd.DataFrame) -> Optional[tuple]:
    """09:30~09:44 ET → (high, low)."""
    orb_bars = day_df.between_time("09:30", "09:44")
    if len(orb_bars) < 3:
        return None
    return float(orb_bars["High"].max()), float(orb_bars["Low"].min())


def evaluate_breakout(bars: pd.DataFrame, i: int, direction: str,
                      orb_high: float, orb_low: float,
                      atr_source: pd.DataFrame) -> Optional[DispRecord]:
    """For bar i, if it's an ORB breakout + has FVG, return a DispRecord
    capturing the displacement diagnostic. Returns None if not a candidate."""
    if direction == "bull":
        fvg = check_breakout_with_fvg(bars, orb_high, i, strict=True)
    else:
        fvg = check_breakdown_with_fvg(bars, orb_low, i, strict=True)
    if fvg is None:
        return None

    bar = bars.iloc[i]
    prev_window = bars.iloc[max(0, i - 5):i]
    atr_val = atr14(atr_source)
    body = abs(float(bar["Close"]) - float(bar["Open"]))
    total = float(bar["High"]) - float(bar["Low"])
    wick_ratio = (total - body) / total if total > 0 else 1.0
    body_atr_ratio = (body / atr_val) if atr_val else None

    passes_default = is_displacement(
        bar, prev_window, atr_value=atr_val,
        atr_mult=1.0, prev_mult=1.5, max_wick=0.50,
        direction=direction,
    )

    ts = bars.index[i]
    return DispRecord(
        source="backtest",
        date=str(ts.date()),
        bar_time=ts.isoformat(),
        symbol="",   # filled in by caller
        direction=direction,
        killzone=killzone_for(ts),
        body=round(body, 4),
        atr14=round(atr_val, 4) if atr_val else None,
        body_atr_ratio=round(body_atr_ratio, 4) if body_atr_ratio is not None else None,
        wick_ratio=round(wick_ratio, 4),
        passes_default=bool(passes_default),
    )


def collect_backtest(symbols=("TQQQ", "QQQ", "SQQQ"),
                     directions=("bull", "bear")) -> List[DispRecord]:
    print(f"[backtest] downloading 60d 5m × {len(symbols)} symbols …")
    data = {s: fetch_5m(s) for s in symbols}
    days = sorted(set.intersection(*[set(d["date"].unique()) for d in data.values()]))
    print(f"[backtest] common days: {len(days)}  range {days[0]} ~ {days[-1]}")

    records: List[DispRecord] = []
    for d in days:
        for sym in symbols:
            day_df = data[sym][data[sym]["date"] == d]
            if len(day_df) < 20:
                continue
            orb = compute_orb(day_df)
            if orb is None:
                continue
            orb_h, orb_l = orb
            post = day_df.between_time("09:45", "10:55")
            if len(post) < 4:
                continue
            # ATR source = full day (RTH) for stability
            for direction in directions:
                for i in range(1, len(post) - 1):
                    rec = evaluate_breakout(post, i, direction, orb_h, orb_l, day_df)
                    if rec is None:
                        continue
                    rec.symbol = sym
                    records.append(rec)
    print(f"[backtest] candidates evaluated: {len(records)}")
    return records


# ───────────────────────── Live source ─────────────────────────
def collect_live(jsonl_dir: Path = Path("data/ict_decisions"),
                 dedup: bool = True) -> List[DispRecord]:
    """Aggregate displacement_check events.

    dedup=True (default): same (symbol, bar_time, direction) is counted
    once even though the bot scans the same bar every ~15s. This gives
    the *unique candidate* count, which is what we want for distribution
    statistics. Set dedup=False to see raw tick frequency.
    """
    if not jsonl_dir.exists():
        print(f"[live] {jsonl_dir} not found — skipping")
        return []
    raw: List[DispRecord] = []
    files = sorted(jsonl_dir.glob("*.jsonl"))
    for p in files:
        with p.open() as f:
            for ln in f:
                try:
                    e = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                if e.get("event") != "displacement_check":
                    continue
                d = e.get("details", {}) or {}
                if "body_atr_ratio" not in d:
                    continue
                ts = e.get("bar_time", "")
                try:
                    date_str = ts.split("T", 1)[0]
                except Exception:
                    date_str = p.stem
                raw.append(DispRecord(
                    source="live",
                    date=date_str,
                    bar_time=ts,
                    symbol=e.get("symbol", ""),
                    direction=d.get("direction", ""),
                    killzone=killzone_for(pd.Timestamp(ts)) if ts else None,
                    body=float(d.get("body", 0) or 0),
                    atr14=float(d["atr14"]) if d.get("atr14") is not None else None,
                    body_atr_ratio=float(d["body_atr_ratio"]) if d.get("body_atr_ratio") is not None else None,
                    wick_ratio=float(d.get("wick_ratio", 0) or 0),
                    passes_default=bool(e.get("passed")),
                    notes=f"src={p.name}",
                ))
    print(f"[live] raw events: {len(raw)}  files: {len(files)}")
    if dedup:
        seen = {}
        for r in raw:
            key = (r.symbol, r.bar_time, r.direction)
            # Keep the first occurrence (earliest tick) — all values same anyway
            if key not in seen:
                seen[key] = r
        records = list(seen.values())
        print(f"[live] unique candidates (dedup): {len(records)}")
        return records
    return raw


# ───────────────────────── Analysis ─────────────────────────
BUCKETS = [
    ("[0.0, 0.5)",   0.0,  0.5),
    ("[0.5, 0.7)",   0.5,  0.7),
    ("[0.7, 0.85)",  0.7,  0.85),
    ("[0.85, 0.95)", 0.85, 0.95),
    ("[0.95, 1.0)",  0.95, 1.0),
    ("[1.0, 1.3)",   1.0,  1.3),
    ("[1.3, 1.5)",   1.3,  1.5),
    ("[1.5, 2.0)",   1.5,  2.0),
    ("[2.0, inf)",   2.0,  float("inf")),
]


def summarize(records: List[DispRecord]) -> dict:
    if not records:
        return {"n": 0, "buckets": {}, "borderline": {}, "wick_ok_in_borderline": 0}
    ratios = [r.body_atr_ratio for r in records if r.body_atr_ratio is not None]
    buckets = {}
    for label, lo, hi in BUCKETS:
        buckets[label] = sum(1 for r in ratios if lo <= r < hi)
    # Borderline = [0.85, 1.0) (would pass if threshold dropped to 0.85)
    borderline = [r for r in records if r.body_atr_ratio is not None
                  and 0.85 <= r.body_atr_ratio < 1.0]
    wick_ok = sum(1 for r in borderline if r.wick_ratio < 0.50)
    direction_split = {}
    for r in borderline:
        k = r.direction or "n/a"
        direction_split[k] = direction_split.get(k, 0) + 1
    kz_split = {}
    for r in borderline:
        k = r.killzone or "outside"
        kz_split[k] = kz_split.get(k, 0) + 1
    return {
        "n": len(records),
        "n_with_ratio": len(ratios),
        "mean_ratio": round(float(np.mean(ratios)), 3) if ratios else None,
        "median_ratio": round(float(np.median(ratios)), 3) if ratios else None,
        "p25_ratio": round(float(np.percentile(ratios, 25)), 3) if ratios else None,
        "p75_ratio": round(float(np.percentile(ratios, 75)), 3) if ratios else None,
        "buckets": buckets,
        "borderline_count": len(borderline),
        "borderline_wick_lt_50": wick_ok,
        "borderline_direction": direction_split,
        "borderline_killzone": kz_split,
    }


def print_report(records: List[DispRecord], source_label: str):
    summary = summarize(records)
    print()
    print(f"=== Displacement diagnostic — source: {source_label} ===")
    print(f"  total candidates : {summary.get('n', 0)}")
    if summary.get("n", 0) == 0:
        print("  (no data)")
        return summary
    print(f"  with body/ATR    : {summary['n_with_ratio']}")
    print(f"  ratio mean       : {summary['mean_ratio']}")
    print(f"  ratio median     : {summary['median_ratio']}")
    print(f"  ratio p25 / p75  : {summary['p25_ratio']} / {summary['p75_ratio']}")
    print()
    print(f"  Histogram (body/ATR):")
    max_bar = max(summary["buckets"].values()) if summary["buckets"] else 1
    bar_width = 40
    for label, _, _ in BUCKETS:
        n = summary["buckets"].get(label, 0)
        bar = "█" * int(n / max(max_bar, 1) * bar_width)
        marker = ""
        if label.startswith("[0.85, 0.95)") or label.startswith("[0.95, 1.0)"):
            marker = "  ← borderline"
        if label.startswith("[1.0, "):
            marker = "  ← current threshold"
        print(f"    {label:<14s} {n:>4d}  {bar}{marker}")
    print()
    print(f"  Borderline [0.85, 1.0):")
    print(f"    count                  : {summary['borderline_count']}")
    print(f"    with wick<50%          : {summary['borderline_wick_lt_50']}")
    print(f"    by direction           : {summary['borderline_direction']}")
    print(f"    by killzone            : {summary['borderline_killzone']}")
    return summary


# ───────────────────────── Main ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=("backtest", "live", "both"), default="both")
    ap.add_argument("--out-dir", default="scripts/out")
    args = ap.parse_args()

    bt: List[DispRecord] = []
    live: List[DispRecord] = []

    if args.source in ("backtest", "both"):
        bt = collect_backtest()
        print_report(bt, "backtest (yfinance 60d × 3 symbols × bull+bear)")
    if args.source in ("live", "both"):
        live = collect_live()
        print_report(live, "live (ict_decisions JSONL)")
    if args.source == "both":
        merged = bt + live
        print_report(merged, "combined")

    # Save raw + summary
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    chosen = {"backtest": bt, "live": live, "both": bt + live}[args.source]
    if chosen:
        df = pd.DataFrame([asdict(r) for r in chosen])
        csv_path = out_dir / f"displacement_distribution_{args.source}.csv"
        df.to_csv(csv_path, index=False)
        print(f"\n[main] wrote {csv_path} ({len(df)} rows)")

        summary_path = out_dir / f"displacement_distribution_{args.source}.json"
        summary_path.write_text(json.dumps({
            "args": vars(args),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "backtest_summary": summarize(bt) if bt else None,
            "live_summary": summarize(live) if live else None,
            "combined_summary": summarize(bt + live) if args.source == "both" else None,
        }, indent=2, default=str))
        print(f"[main] wrote {summary_path}")


if __name__ == "__main__":
    main()
