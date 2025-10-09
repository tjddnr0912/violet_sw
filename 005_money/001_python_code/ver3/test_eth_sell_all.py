#!/usr/bin/env python3
"""
Test Script: Sell ALL ETH Holdings Using Ver3 LiveExecutorV3

This script uses Ver3's actual sell execution code to place a REAL sell order
on Bithumb to close the entire ETH position.

WARNINGS:
- This script places REAL orders on Bithumb exchange
- This will sell ALL your ETH holdings
- You will receive KRW in exchange for your ETH
- This action is IRREVERSIBLE once executed

Usage:
    python test_eth_sell_all.py --confirm  # Execute real sell
    python test_eth_sell_all.py            # Show position only (no sell)
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# Add project root and 001_python_code to path
project_root = Path(__file__).parent.parent.parent
code_dir = project_root / '001_python_code'
sys.path.insert(0, str(code_dir))

from ver3.live_executor_v3 import LiveExecutorV3
from lib.api.bithumb_api import BithumbAPI, get_ticker
from lib.core.logger import TradingLogger
from ver3.config_v3 import get_version_config


def print_separator(char="=", length=80):
    """Print a separator line."""
    print(char * length)


def print_warning_banner():
    """Print safety warning banner."""
    print_separator("!")
    print("!!  WARNING: REAL MONEY TRANSACTION  !!")
    print_separator("!")
    print()
    print("This script will place a REAL SELL ORDER on Bithumb exchange.")
    print("You are about to sell ALL of your ETH holdings for KRW.")
    print()
    print("⚠️  This action is IRREVERSIBLE")
    print("⚠️  Your ETH will be converted to KRW at current market price")
    print("⚠️  Trading fees will apply (approximately 0.05%)")
    print()
    print_separator("!")
    print()


def get_api_keys():
    """Get API keys from environment variables."""
    connect_key = os.environ.get('BITHUMB_CONNECT_KEY')
    secret_key = os.environ.get('BITHUMB_SECRET_KEY')

    if not connect_key or not secret_key:
        print("❌ ERROR: API keys not found in environment variables")
        print()
        print("Please set the following environment variables:")
        print("  export BITHUMB_CONNECT_KEY='your_connect_key'")
        print("  export BITHUMB_SECRET_KEY='your_secret_key'")
        print()
        sys.exit(1)

    # Basic validation
    if connect_key in ['YOUR_CONNECT_KEY', 'your_connect_key'] or len(connect_key) < 20:
        print("❌ ERROR: Invalid BITHUMB_CONNECT_KEY")
        sys.exit(1)

    if secret_key in ['YOUR_SECRET_KEY', 'your_secret_key'] or len(secret_key) < 20:
        print("❌ ERROR: Invalid BITHUMB_SECRET_KEY")
        sys.exit(1)

    return connect_key, secret_key


def query_eth_balance(api: BithumbAPI):
    """Query current ETH balance from Bithumb API."""
    print("📊 Querying ETH balance from Bithumb API...")
    print()

    try:
        balance_response = api.get_balance(currency='ETH')

        if not balance_response:
            print("❌ Failed to get balance response from API")
            return None

        if balance_response.get('status') != '0000':
            error_msg = balance_response.get('message', 'Unknown error')
            print(f"❌ API Error: {error_msg}")
            return None

        data = balance_response.get('data', {})
        available_eth = float(data.get('available_eth', 0))
        in_use_eth = float(data.get('in_use_eth', 0))
        total_eth = float(data.get('total_eth', 0))

        print(f"✅ Balance Query Successful:")
        print(f"   Available ETH: {available_eth:.8f}")
        print(f"   In-Use ETH: {in_use_eth:.8f}")
        print(f"   Total ETH: {total_eth:.8f}")
        print()

        return {
            'available': available_eth,
            'in_use': in_use_eth,
            'total': total_eth
        }

    except Exception as e:
        print(f"❌ Exception querying balance: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_current_eth_price():
    """Get current ETH price from Bithumb."""
    print("💰 Getting current ETH price...")
    print()

    try:
        ticker_data = get_ticker('ETH')

        if not ticker_data:
            print("❌ Failed to get ticker data")
            return None

        current_price = float(ticker_data.get('closing_price', 0))

        print(f"✅ Current ETH Price: {current_price:,.0f} KRW")
        print()

        return current_price

    except Exception as e:
        print(f"❌ Exception getting price: {e}")
        return None


def display_position_info(executor: LiveExecutorV3, ticker: str, current_price: float):
    """Display current position information."""
    print_separator("-")
    print("📋 CURRENT POSITION INFORMATION")
    print_separator("-")
    print()

    if not executor.has_position(ticker):
        print(f"⚠️  No position found for {ticker} in positions_v3.json")
        print()
        return None

    position = executor.get_position(ticker)
    summary = executor.get_position_summary(ticker)

    print(f"Ticker: {ticker}")
    print(f"Position Size: {position.size:.8f} {ticker}")
    print(f"Entry Price: {position.entry_price:,.0f} KRW")
    print(f"Entry Time: {summary['entry_time']}")
    print(f"Current Price: {current_price:,.0f} KRW")
    print()

    # Check if pyramided
    entry_count = summary.get('entry_count', 1)
    if entry_count > 1:
        print(f"⚠️  PYRAMIDED POSITION (Multiple Entries: {entry_count})")
        print()
        print("Entry Details:")
        for i, (price, size) in enumerate(zip(summary['entry_prices'], summary['entry_sizes']), 1):
            print(f"  Entry #{i}: {size:.8f} {ticker} @ {price:,.0f} KRW")
        print()
        print(f"Weighted Average Entry: {position.entry_price:,.0f} KRW")
        print()

    # Calculate P&L
    total_value_krw = position.size * current_price
    entry_value_krw = position.size * position.entry_price
    profit_krw = total_value_krw - entry_value_krw
    profit_pct = (profit_krw / entry_value_krw) * 100 if entry_value_krw > 0 else 0.0

    print(f"Entry Value: {entry_value_krw:,.0f} KRW")
    print(f"Current Value: {total_value_krw:,.0f} KRW")
    print(f"Unrealized P&L: {profit_krw:+,.0f} KRW ({profit_pct:+.2f}%)")
    print()

    # Estimate fees
    estimated_fee = total_value_krw * 0.0005  # 0.05% fee
    net_proceeds = total_value_krw - estimated_fee

    print(f"Estimated Trading Fee (0.05%): {estimated_fee:,.0f} KRW")
    print(f"Estimated Net Proceeds: {net_proceeds:,.0f} KRW")
    print()

    return {
        'size': position.size,
        'entry_price': position.entry_price,
        'current_price': current_price,
        'total_value': total_value_krw,
        'profit': profit_krw,
        'profit_pct': profit_pct,
        'entry_count': entry_count
    }


def execute_sell_order(executor: LiveExecutorV3, ticker: str, price: float, dry_run: bool):
    """Execute the sell order using LiveExecutorV3.close_position()."""

    if dry_run:
        print("🔵 DRY-RUN MODE: Simulating sell order...")
    else:
        print("🔴 LIVE MODE: Executing REAL sell order on Bithumb...")

    print()
    print_separator("-")

    # Execute using close_position (sells entire position)
    result = executor.close_position(
        ticker=ticker,
        price=price,
        dry_run=dry_run,
        reason="Test script: Selling all ETH holdings"
    )

    print_separator("-")
    print()

    return result


def display_execution_result(result: dict, position_info: dict):
    """Display the execution result."""
    print_separator("=")
    print("📊 EXECUTION RESULT")
    print_separator("=")
    print()

    if result['success']:
        print("✅ ORDER EXECUTED SUCCESSFULLY")
        print()
        print(f"Order ID: {result['order_id']}")
        print(f"Executed Price: {result['executed_price']:,.0f} KRW")
        print(f"Executed Units: {result['executed_units']:.8f} ETH")
        print(f"Message: {result['message']}")
        print()

        # Calculate actual proceeds
        actual_value = result['executed_units'] * result['executed_price']
        estimated_fee = actual_value * 0.0005
        net_proceeds = actual_value - estimated_fee

        print(f"Gross Proceeds: {actual_value:,.0f} KRW")
        print(f"Estimated Fee: {estimated_fee:,.0f} KRW")
        print(f"Net Proceeds: {net_proceeds:,.0f} KRW")
        print()

        if position_info:
            print(f"Total P&L: {position_info['profit']:+,.0f} KRW ({position_info['profit_pct']:+.2f}%)")

    else:
        print("❌ ORDER EXECUTION FAILED")
        print()
        print(f"Order ID: {result.get('order_id', 'N/A')}")
        print(f"Message: {result['message']}")

    print()
    print_separator("=")


def verify_position_closed(executor: LiveExecutorV3, ticker: str):
    """Verify that the position has been removed from positions_v3.json."""
    print()
    print("🔍 Verifying position closure...")
    print()

    if not executor.has_position(ticker):
        print(f"✅ Position for {ticker} has been removed from positions_v3.json")
        print("✅ Position fully closed")
    else:
        position = executor.get_position(ticker)
        if position.size > 0:
            print(f"⚠️  WARNING: Position still exists with size {position.size:.8f} {ticker}")
        else:
            print(f"✅ Position size is 0 (closed)")

    print()


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description='Sell ALL ETH holdings using Ver3 LiveExecutorV3',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_eth_sell_all.py              # Show position info only (safe)
  python test_eth_sell_all.py --confirm    # Execute REAL sell order (CAREFUL!)
        """
    )
    parser.add_argument(
        '--confirm',
        action='store_true',
        help='Execute real sell order (without this flag, only shows position info)'
    )

    args = parser.parse_args()

    # Configuration
    ticker = 'ETH'

    print()
    print_separator("=")
    print("TEST SCRIPT: Sell ALL ETH Holdings")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print_separator("=")
    print()

    # Step 1: Get API keys
    print("🔑 Step 1: Validating API Keys")
    print()
    connect_key, secret_key = get_api_keys()
    print(f"✅ API keys found")
    print(f"   Connect Key: {connect_key[:10]}...")
    print(f"   Secret Key: {secret_key[:10]}...")
    print()

    # Step 2: Initialize components
    print("⚙️  Step 2: Initializing Components")
    print()

    # Initialize API
    api = BithumbAPI(connect_key=connect_key, secret_key=secret_key)
    print("✅ BithumbAPI initialized")

    # Initialize logger
    logger = TradingLogger(log_dir='logs')
    print("✅ TradingLogger initialized")

    # Get Ver3 config
    config = get_version_config(interval='4h', mode='live')
    print("✅ Ver3 config loaded")

    # Initialize LiveExecutorV3
    executor = LiveExecutorV3(
        api=api,
        logger=logger,
        config=config,
        state_file='logs/positions_v3.json'
    )
    print("✅ LiveExecutorV3 initialized")
    print()

    # Step 3: Query ETH balance from API
    print("📊 Step 3: Querying ETH Balance from Bithumb")
    print()
    balance_info = query_eth_balance(api)

    if not balance_info:
        print("❌ Failed to query balance. Aborting.")
        sys.exit(1)

    if balance_info['available'] <= 0:
        print(f"⚠️  WARNING: No available ETH to sell (available: {balance_info['available']})")
        print("Position may be in use or already sold.")
        print()

    # Step 4: Get current price
    print("💰 Step 4: Getting Current ETH Price")
    print()
    current_price = get_current_eth_price()

    if not current_price:
        print("❌ Failed to get current price. Aborting.")
        sys.exit(1)

    # Step 5: Display position info
    print("📋 Step 5: Displaying Position Information")
    print()
    position_info = display_position_info(executor, ticker, current_price)

    if not position_info:
        print("⚠️  No position found in Ver3 state file")
        print()

        # But if API shows balance, we can still sell it
        if balance_info['available'] > 0:
            print(f"However, API shows available ETH: {balance_info['available']:.8f}")
            print("Proceeding with API balance...")
            position_info = {
                'size': balance_info['available'],
                'current_price': current_price,
                'total_value': balance_info['available'] * current_price,
                'entry_count': 1
            }
        else:
            print("No ETH to sell. Exiting.")
            sys.exit(0)

    # Step 6: Execute sell order (if --confirm flag provided)
    if not args.confirm:
        print()
        print_separator("=")
        print("ℹ️  INFORMATION MODE (No action taken)")
        print_separator("=")
        print()
        print("This was an information-only run. No orders were placed.")
        print()
        print("To execute the REAL sell order, run:")
        print(f"  python {os.path.basename(__file__)} --confirm")
        print()
        print_separator("=")
        return

    # Show warning banner
    print()
    print_warning_banner()

    # Final confirmation
    print("You are about to sell:")
    print(f"  {position_info['size']:.8f} ETH")
    print(f"  Estimated value: {position_info['total_value']:,.0f} KRW")
    if 'entry_count' in position_info and position_info['entry_count'] > 1:
        print(f"  Pyramided position with {position_info['entry_count']} entries")
    print()

    user_input = input("Type 'CONFIRM' to proceed with REAL sell order: ")

    if user_input.strip().upper() != 'CONFIRM':
        print()
        print("❌ Sell order cancelled by user")
        print()
        sys.exit(0)

    print()
    print("🚀 Proceeding with REAL sell order...")
    print()

    # Execute the sell
    result = execute_sell_order(
        executor=executor,
        ticker=ticker,
        price=current_price,
        dry_run=False  # REAL execution
    )

    # Display result
    display_execution_result(result, position_info)

    # Verify position closed
    if result['success']:
        verify_position_closed(executor, ticker)

    print()
    print(f"✅ Test script completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print()
        print()
        print("❌ Script interrupted by user (Ctrl+C)")
        print()
        sys.exit(1)
    except Exception as e:
        print()
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
