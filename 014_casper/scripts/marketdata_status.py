#!/usr/bin/env python3
"""Inspect collected marketdata (Parquet store) status.

Reports per-symbol file count, byte usage, and any recent gaps in the
NYSE trading calendar within the last 7 days.

Usage:
    python scripts/marketdata_status.py
    python scripts/marketdata_status.py --gap-check 30   # 30-day gap scan
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.data.store import stats
from src.data.gap_finder import find_gaps


DEFAULT_SYMBOLS = ["TQQQ", "QQQ", "SQQQ", "_VIX"]
DEFAULT_BASE = os.path.join(ROOT, "data", "marketdata")


def main():
    p = argparse.ArgumentParser(description="Marketdata store status")
    p.add_argument("--base", type=str, default=DEFAULT_BASE)
    p.add_argument("--gap-check", type=int, default=7,
                   help="Look back N days and list missing trading days (default 7)")
    args = p.parse_args()

    s = stats(args.base)
    print(f"Base:         {args.base}")
    print(f"Total files:  {s['total_files']}")
    print(f"Total bytes:  {s['total_bytes']:,}  "
          f"({s['total_bytes']/1024:.1f} KB / {s['total_bytes']/(1024*1024):.2f} MB)")
    print()
    print(f"{'Symbol':<8s} {'Days':>5s} {'Bytes':>10s}")
    print("-" * 30)
    for sym, info in s["symbols"].items():
        print(f"{sym:<8s} {info['days']:>5d} {info['bytes']:>10,}")

    if args.gap_check > 0:
        print()
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=args.gap_check)
        print(f"Gap check  {start} ~ {end}  ({args.gap_check} day(s) lookback):")
        # underlying symbol names use the canonical "^VIX" form for the
        # backfill / yfinance side; stats uses the on-disk "_VIX" form
        for sym_canonical, sym_disk in zip(
            ["TQQQ", "QQQ", "SQQQ", "^VIX"],
            ["TQQQ", "QQQ", "SQQQ", "_VIX"],
        ):
            gaps = find_gaps(args.base, sym_canonical, start, end)
            if not gaps:
                print(f"  {sym_disk:<8s} OK (no gaps)")
            else:
                print(f"  {sym_disk:<8s} {len(gaps)} gap(s): "
                      f"{', '.join(d.isoformat() for d in gaps)}")


if __name__ == "__main__":
    main()
