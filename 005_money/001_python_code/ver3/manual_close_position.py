#!/usr/bin/env python3
"""
Manual Position Closer for Ver3

Quick tool to manually close positions when needed.
Useful for:
- Closing positions before changing coin list
- Emergency exits
- Testing position cleanup

Usage:
    python manual_close_position.py             # Interactive mode
    python manual_close_position.py SOL         # Close specific coin
    python manual_close_position.py --all       # Close all positions
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add parent directory to path
base_path = Path(__file__).parent.parent
sys.path.insert(0, str(base_path))

from lib.api.bithumb_api import get_ticker
from ver3.config_v3 import get_version_config
from ver3.live_executor_v3 import LiveExecutorV3
from lib.core.logger import TradingLogger


def load_positions(positions_file: Path):
    """Load current positions from file."""
    if not positions_file.exists():
        return {}

    with open(positions_file, 'r') as f:
        return json.load(f)


def display_positions(positions: dict):
    """Display current positions in a readable format."""
    if not positions:
        print("\n📭 No active positions\n")
        return

    print("\n" + "="*80)
    print("CURRENT POSITIONS")
    print("="*80)

    for coin, pos in positions.items():
        entry_price = pos['entry_price']
        size = pos['size']
        entry_count = pos.get('entry_count', 1)
        position_pct = pos.get('position_pct', 100)

        # Get current price
        ticker_data = get_ticker(coin)
        current_price = entry_price
        if ticker_data:
            current_price = float(ticker_data.get('closing_price', entry_price))

        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        pnl_color = "+" if pnl_pct >= 0 else ""

        print(f"\n{coin}")
        print(f"  Entry Price:  {entry_price:>15,.0f} KRW")
        print(f"  Current Price:{current_price:>15,.0f} KRW")
        print(f"  Size:         {size:>15.8f} {coin}")
        print(f"  Position:     {position_pct:>15.0f}%")
        print(f"  Entry Count:  {entry_count:>15} times")
        print(f"  P&L:          {pnl_color}{pnl_pct:>14.2f}%")

    print("\n" + "="*80 + "\n")


def close_position(coin: str, executor: LiveExecutorV3, logger: TradingLogger, dry_run: bool = True):
    """Close a single position."""
    if not executor.has_position(coin):
        print(f"❌ No position found for {coin}")
        return False

    # Get current price
    ticker_data = get_ticker(coin)
    if not ticker_data:
        print(f"❌ Could not fetch current price for {coin}")
        return False

    current_price = float(ticker_data.get('closing_price', 0))

    # Get position summary
    pos_summary = executor.get_position_summary(coin)
    entry_price = pos_summary['entry_price']
    size = pos_summary['size']
    pnl_pct = ((current_price - entry_price) / entry_price) * 100

    # Confirm
    print(f"\n⚠️  About to close position:")
    print(f"   Coin: {coin}")
    print(f"   Size: {size:.8f}")
    print(f"   Entry: {entry_price:,.0f} KRW")
    print(f"   Current: {current_price:,.0f} KRW")
    print(f"   P&L: {pnl_pct:+.2f}%")
    print(f"   Mode: {'DRY-RUN' if dry_run else 'LIVE'}")

    confirm = input(f"\nConfirm close {coin}? (yes/no): ").strip().lower()

    if confirm != 'yes':
        print("❌ Cancelled")
        return False

    # Execute close
    result = executor.execute_exit(
        ticker=coin,
        price=current_price,
        dry_run=dry_run,
        reason="Manual close"
    )

    if result.get('success'):
        print(f"✅ Successfully closed {coin} position")
        logger.logger.info(f"Manual close: {coin} @ {current_price:,.0f} KRW (P&L: {pnl_pct:+.2f}%)")
        return True
    else:
        print(f"❌ Failed to close {coin}: {result.get('message')}")
        return False


def close_all_positions(executor: LiveExecutorV3, logger: TradingLogger, dry_run: bool = True):
    """Close all positions."""
    all_positions = executor.get_all_positions()

    if not all_positions:
        print("\n📭 No positions to close\n")
        return

    print(f"\n⚠️  About to close ALL {len(all_positions)} positions:")
    for coin in all_positions.keys():
        print(f"   - {coin}")

    print(f"   Mode: {'DRY-RUN' if dry_run else 'LIVE'}")

    confirm = input(f"\nConfirm close all positions? (yes/no): ").strip().lower()

    if confirm != 'yes':
        print("❌ Cancelled")
        return

    # Close each position
    success_count = 0
    for coin in list(all_positions.keys()):
        print(f"\nClosing {coin}...")
        if close_position(coin, executor, logger, dry_run):
            success_count += 1

    print(f"\n✅ Closed {success_count}/{len(all_positions)} positions")


def interactive_mode(executor: LiveExecutorV3, logger: TradingLogger, dry_run: bool):
    """Interactive mode - let user choose what to close."""
    positions = executor.get_all_positions()

    if not positions:
        print("\n📭 No positions to close\n")
        return

    print("\nSelect action:")
    print("  1. Close specific coin")
    print("  2. Close all positions")
    print("  3. Exit")

    choice = input("\nEnter choice (1/2/3): ").strip()

    if choice == '1':
        coin = input("\nEnter coin to close (e.g., SOL): ").strip().upper()
        if coin in positions:
            close_position(coin, executor, logger, dry_run)
        else:
            print(f"❌ No position found for {coin}")
    elif choice == '2':
        close_all_positions(executor, logger, dry_run)
    elif choice == '3':
        print("👋 Exiting")
    else:
        print("❌ Invalid choice")


def main():
    """Main function."""
    print("\n" + "="*80)
    print("MANUAL POSITION CLOSER - Ver3")
    print("="*80)

    # Load config
    config = get_version_config()
    dry_run = config['EXECUTION_CONFIG'].get('dry_run', True)

    print(f"\nMode: {'DRY-RUN' if dry_run else 'LIVE'}")

    # Initialize executor and logger
    logger = TradingLogger()
    from lib.api.bithumb_api import BithumbAPI
    api = BithumbAPI()
    executor = LiveExecutorV3(api, logger, config)

    # Load and display positions
    positions_file = Path('logs/positions_v3.json')
    positions = load_positions(positions_file)
    display_positions(positions)

    if not positions:
        return

    # Parse command line arguments
    if len(sys.argv) > 1:
        arg = sys.argv[1].upper()

        if arg == '--ALL':
            close_all_positions(executor, logger, dry_run)
        elif arg in positions:
            close_position(arg, executor, logger, dry_run)
        else:
            print(f"❌ Unknown argument or coin not found: {arg}")
    else:
        # Interactive mode
        interactive_mode(executor, logger, dry_run)


if __name__ == '__main__':
    main()
