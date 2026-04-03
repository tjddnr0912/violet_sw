#!/usr/bin/env python3
"""
Casper Trading Bot - Entry Point
=================================
TQQQ/SQQQ Long-Only ORB+FVG Strategy

Usage:
    python run_bot.py           # Start the bot
    python run_bot.py --status  # Show cumulative stats

Environment:
    Set TRADING_MODE in .env:
      - "paper"  : Paper trading (모의투자)
      - "live"   : Live trading (실거래)
"""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.data.trade_store import load_trades, get_cumulative_stats


def show_status():
    """Print cumulative trading statistics."""
    trades = load_trades()
    stats = get_cumulative_stats(trades)
    print("=" * 40)
    print("  Casper Bot - Cumulative Stats")
    print("=" * 40)
    print(f"  Total Trades: {stats['total_trades']}")
    print(f"  Wins: {stats['wins']} | Losses: {stats['losses']} | BE: {stats['bes']}")
    print(f"  Win Rate: {stats['win_rate']}%")
    print(f"  Total P&L: ${stats['total_pnl']:+.2f}")
    print(f"  Profit Factor: {stats['profit_factor']}")
    print("=" * 40)


def main():
    if "--status" in sys.argv:
        show_status()
        return

    from src.bot import CasperBot
    bot = CasperBot()
    bot.run()


if __name__ == "__main__":
    main()
