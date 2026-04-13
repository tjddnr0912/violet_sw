#!/usr/bin/env python3
"""Reproduce a full CasperBot() init — same as run_bot.py does — and observe
the warm_up() HTTP behaviour with urllib3 debug tracing enabled.

This complements debug_kis_reproduce.py (which only runs the raw KIS client
loop). If THIS reproduces 500 while debug_kis_reproduce.py does not, the
culprit is something in the bot's wider import / init path (setup_logger,
yfinance import, market_data's set_kis_client, strategy_params load, ...).
"""
from __future__ import annotations

import logging
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# Crank urllib3 to DEBUG *before* any imports so the first call is traced.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-5s %(name)-25s | %(message)s",
)
logging.getLogger("urllib3.connectionpool").setLevel(logging.DEBUG)
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("peewee").setLevel(logging.WARNING)

print("=" * 70)
print("Full CasperBot() init reproduction")
print("=" * 70)

# This is identical to what run_bot.py main() does.
from src.bot import CasperBot  # noqa: E402

print("\n[init] Creating CasperBot() — warm_up runs inside _init_kis ...")
bot = CasperBot()
print("\n[init] Bot created.")
print(f"[init] bot.kis_client is None? {bot.kis_client is None}")
if bot.kis_client is not None:
    print(f"[init] bot.kis_client.base_url = {bot.kis_client.base_url}")

    # After warm_up has already tried — now poke the balance endpoint
    # directly with retry=False to see the current state.
    print("\n[post-init] Direct inquire-present-balance probe (retry=False):")
    import time
    for i in range(3):
        t = time.time()
        r = bot.kis_client.get_us_balance()
        print(f"  [{i+1}] {r}  ({time.time()-t:.2f}s)")
        time.sleep(2)
