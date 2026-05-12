#!/usr/bin/env python3
"""Manually backfill 5-min bars from yfinance for given symbols.

Usage:
    python scripts/backfill_marketdata.py
        # default symbols (TQQQ QQQ SQQQ ^VIX), last 60 days
    python scripts/backfill_marketdata.py --symbols TQQQ QQQ
        # subset of symbols
    python scripts/backfill_marketdata.py --days 30
        # last 30 days
    python scripts/backfill_marketdata.py --start 2026-04-01 --end 2026-05-08
        # explicit date range
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.data.gap_finder import find_gaps
from src.data.backfill import fill_gaps_from_yfinance


DEFAULT_SYMBOLS = ["TQQQ", "QQQ", "SQQQ", "^VIX"]
DEFAULT_BASE = os.path.join(ROOT, "data", "marketdata")


def main():
    p = argparse.ArgumentParser(description="Backfill 5-min market data via yfinance")
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    p.add_argument("--end", type=str, default=None, help="YYYY-MM-DD")
    p.add_argument("--base", type=str, default=DEFAULT_BASE)
    args = p.parse_args()

    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    else:
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=args.days)

    print(f"[backfill] range {start} ~ {end}  symbols={args.symbols}")
    os.makedirs(args.base, exist_ok=True)

    total_filled = 0
    for sym in args.symbols:
        gaps = find_gaps(args.base, sym, start, end)
        if not gaps:
            print(f"  {sym}: no gaps")
            continue
        print(f"  {sym}: filling {len(gaps)} gaps …")
        filled = fill_gaps_from_yfinance(args.base, sym, gaps)
        print(f"    → wrote {filled}/{len(gaps)} days")
        total_filled += filled

    print(f"[backfill] done  total_filled={total_filled}")


if __name__ == "__main__":
    main()
