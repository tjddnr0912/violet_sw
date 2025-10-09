#!/usr/bin/env python3
"""
Test Script: Real SOL Sale (ALL HOLDINGS) using Ver3 LiveExecutorV3

This script tests Ver3's actual sell execution code by placing a REAL order
on Bithumb to sell ALL SOL holdings.

⚠️  WARNING: THIS USES REAL MONEY - NOT A DRY RUN ⚠️
⚠️  THIS WILL SELL 100% OF YOUR SOL HOLDINGS ⚠️

Requirements:
- BITHUMB_CONNECT_KEY and BITHUMB_SECRET_KEY environment variables must be set
- Must have SOL holdings in Bithumb account
- Bithumb API must have trading permissions enabled

Safety Features:
- Verifies API keys are set before execution
- Queries actual SOL balance from Bithumb API
- Shows exact sale details and requires user confirmation
- Validates current SOL price is reasonable
- Calculates exact value in KRW
- Logs all steps clearly
- Reports order status with details
- Requires explicit --confirm flag to proceed
"""

import os
import sys
import time
import argparse
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from lib.api.bithumb_api import BithumbAPI, get_ticker
from lib.core.logger import TradingLogger
from ver3.live_executor_v3 import LiveExecutorV3
from ver3.config_v3 import get_version_config


def print_header(text: str):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)


def print_warning(text: str):
    """Print warning message"""
    print(f"\n⚠️  {text}")


def print_info(label: str, value: str):
    """Print info line"""
    print(f"   {label:25s}: {value}")


def verify_api_keys() -> tuple:
    """Verify API keys are set in environment"""
    connect_key = os.getenv('BITHUMB_CONNECT_KEY')
    secret_key = os.getenv('BITHUMB_SECRET_KEY')

    if not connect_key or not secret_key:
        print_warning("API KEYS NOT FOUND IN ENVIRONMENT VARIABLES")
        print("\nPlease set the following environment variables:")
        print("  export BITHUMB_CONNECT_KEY='your_connect_key'")
        print("  export BITHUMB_SECRET_KEY='your_secret_key'")
        return None, None

    if connect_key in ['YOUR_CONNECT_KEY', 'your_connect_key']:
        print_warning("API CONNECT KEY IS SET TO DEFAULT VALUE")
        return None, None

    if secret_key in ['YOUR_SECRET_KEY', 'your_secret_key']:
        print_warning("API SECRET KEY IS SET TO DEFAULT VALUE")
        return None, None

    return connect_key, secret_key


def get_current_sol_price() -> float:
    """Get current SOL price from Bithumb"""
    try:
        ticker_data = get_ticker('SOL')
        if ticker_data:
            price = float(ticker_data.get('closing_price', 0))
            return price
        return 0.0
    except Exception as e:
        print(f"❌ Error fetching SOL price: {e}")
        return 0.0


def get_sol_balance(api: BithumbAPI) -> float:
    """Query current SOL balance from Bithumb API"""
    try:
        print("   Querying Bithumb API for SOL balance...")
        balance_data = api.get_balance(currency='SOL')

        if not balance_data:
            print("❌ Failed to fetch balance data")
            return 0.0

        if balance_data.get('status') != '0000':
            error_msg = balance_data.get('message', 'Unknown error')
            print(f"❌ API Error: {error_msg}")
            return 0.0

        # Bithumb balance structure: data -> total, available, in_use
        data = balance_data.get('data', {})
        available_sol = float(data.get('available_sol', 0))
        in_use_sol = float(data.get('in_use_sol', 0))
        total_sol = float(data.get('total_sol', 0))

        print(f"\n   SOL Balance Breakdown:")
        print_info("   Total SOL", f"{total_sol:.6f} SOL")
        print_info("   Available SOL", f"{available_sol:.6f} SOL")
        print_info("   In Use SOL", f"{in_use_sol:.6f} SOL")

        # Return available balance (what we can sell)
        return available_sol

    except Exception as e:
        print(f"❌ Error fetching SOL balance: {e}")
        import traceback
        traceback.print_exc()
        return 0.0


def validate_price(price: float) -> bool:
    """Validate SOL price is in reasonable range"""
    # SOL price sanity checks (as of 2025-10)
    MIN_REASONABLE_PRICE = 50000      # 50K KRW minimum
    MAX_REASONABLE_PRICE = 1000000    # 1M KRW maximum

    if price < MIN_REASONABLE_PRICE:
        print_warning(f"SOL price seems too low: {price:,.0f} KRW")
        return False

    if price > MAX_REASONABLE_PRICE:
        print_warning(f"SOL price seems too high: {price:,.0f} KRW")
        return False

    return True


def confirm_sale(sol_units: float, price: float, total_value: float) -> bool:
    """Ask user to confirm sale details"""
    print_header("🔴 REAL MONEY SALE CONFIRMATION")
    print_warning("THIS IS NOT A DRY RUN - REAL SELL ORDER WILL BE PLACED")
    print_warning("THIS WILL SELL 100% OF YOUR SOL HOLDINGS")

    print("\nSale Details:")
    print_info("Cryptocurrency", "SOL (Solana)")
    print_info("Units to Sell", f"{sol_units:.6f} SOL")
    print_info("Current SOL Price", f"{price:,.0f} KRW")
    print_info("Total Sale Value", f"{total_value:,.0f} KRW")
    print_info("Trading Fee (~0.05%)", f"~{total_value * 0.0005:,.0f} KRW")
    print_info("Net Proceeds (Est.)", f"~{total_value * (1 - 0.0005):,.0f} KRW")

    print("\n" + "=" * 70)
    print("\n⚠️  YOU WILL LOSE ALL YOUR SOL HOLDINGS AFTER THIS ORDER ⚠️")
    response = input("\nType 'SELL ALL' to confirm and execute real sell order (or anything else to cancel): ")

    return response.strip().upper() == 'SELL ALL'


def check_position_state(ticker: str):
    """Check if position exists in positions_v3.json"""
    try:
        positions_file = Path(__file__).parent.parent.parent / 'logs' / 'positions_v3.json'
        if positions_file.exists():
            import json
            with open(positions_file, 'r') as f:
                positions = json.load(f)

            if ticker in positions:
                print(f"\n✅ Position found in state file:")
                pos = positions[ticker]
                print_info("   Entry Price", f"{pos.get('entry_price', 0):,.0f} KRW")
                print_info("   Position Size", f"{pos.get('size', 0):.6f} {ticker}")
                print_info("   Entry Time", pos.get('entry_time', 'N/A'))
                return True
            else:
                print(f"\n⚠️  No {ticker} position found in state file")
                print("   (Position may have been opened outside of Ver3 system)")
                return False
    except Exception as e:
        print(f"⚠️  Could not read position state file: {e}")
        return False


def main(confirm_flag: bool = False):
    """Main test execution"""
    print_header("Ver3 LiveExecutorV3 - Real SOL Sale Test (ALL HOLDINGS)")
    print("This script will sell ALL SOL holdings using REAL API")

    # Configuration
    TICKER = 'SOL'

    # Step 1: Verify API Keys
    print_header("Step 1: Verifying API Keys")
    connect_key, secret_key = verify_api_keys()

    if not connect_key or not secret_key:
        print("❌ Test aborted - API keys not properly configured")
        return False

    print(f"✅ API Keys found:")
    print_info("Connect Key", f"{connect_key[:10]}...{connect_key[-4:]}")
    print_info("Secret Key", f"{secret_key[:10]}...{secret_key[-4:]}")

    # Step 2: Initialize API (needed for balance query)
    print_header("Step 2: Initializing Bithumb API")
    api = BithumbAPI(connect_key=connect_key, secret_key=secret_key)
    print("✅ BithumbAPI initialized")

    # Step 3: Query SOL Balance
    print_header("Step 3: Querying Current SOL Balance")
    sol_balance = get_sol_balance(api)

    if sol_balance <= 0:
        print("\n❌ No SOL holdings found in account")
        print("   Cannot proceed with sale - nothing to sell")
        return False

    print(f"\n✅ SOL Balance: {sol_balance:.6f} SOL")

    # Step 4: Check Position State
    print_header("Step 4: Checking Position State")
    check_position_state(TICKER)

    # Step 5: Get Current SOL Price
    print_header("Step 5: Fetching Current SOL Price")
    current_price = get_current_sol_price()

    if current_price <= 0:
        print("❌ Failed to fetch SOL price - cannot proceed")
        return False

    print(f"✅ Current SOL Price: {current_price:,.0f} KRW")

    # Step 6: Validate Price
    print_header("Step 6: Validating Price")
    if not validate_price(current_price):
        print("❌ Price validation failed - please check manually")
        return False

    print("✅ Price is within reasonable range")

    # Step 7: Calculate Total Value
    print_header("Step 7: Calculating Total Sale Value")
    total_value = sol_balance * current_price

    print_info("SOL Units", f"{sol_balance:.6f} SOL")
    print_info("SOL Price", f"{current_price:,.0f} KRW")
    print_info("Total Value", f"{total_value:,.0f} KRW")
    print_info("Est. Net Proceeds", f"{total_value * (1 - 0.0005):,.0f} KRW (after fees)")

    # Step 8: Check --confirm Flag
    if not confirm_flag:
        print_header("Step 8: Confirmation Required")
        print_warning("SAFETY CHECK: --confirm flag not provided")
        print("\nTo proceed with this sale, you must:")
        print("1. Review all the information above carefully")
        print("2. Ensure you really want to sell ALL your SOL")
        print("3. Run this script again with --confirm flag:")
        print(f"\n   python {Path(__file__).name} --confirm")
        print("\n❌ Sale cancelled - confirmation flag required")
        return False

    # Step 9: Get User Confirmation
    print_header("Step 9: User Confirmation")
    if not confirm_sale(sol_balance, current_price, total_value):
        print("\n❌ Sale cancelled by user")
        return False

    print("\n✅ User confirmed - proceeding with real sell order...")
    time.sleep(1)  # Brief pause before execution

    # Step 10: Initialize Components
    print_header("Step 10: Initializing Trading Components")

    # Initialize Logger
    config = get_version_config()
    log_dir = config['LOGGING_CONFIG'].get('log_dir', 'logs')
    logger = TradingLogger(log_dir=log_dir)
    print("✅ TradingLogger initialized")

    # Initialize LiveExecutorV3
    executor = LiveExecutorV3(api=api, logger=logger, config=config)
    print("✅ LiveExecutorV3 initialized")

    # Step 11: Execute Real Sell Order
    print_header("Step 11: Executing REAL SELL Order on Bithumb")
    print_warning("PLACING REAL SELL ORDER NOW...")

    result = executor.execute_order(
        ticker=TICKER,
        action='SELL',
        units=sol_balance,
        price=current_price,
        dry_run=False,  # 🔴 REAL EXECUTION
        reason=f"Test sale: Selling ALL {sol_balance:.6f} SOL holdings"
    )

    # Step 12: Report Results
    print_header("Step 12: Order Execution Results")

    if result['success']:
        print("\n✅ SELL ORDER EXECUTED SUCCESSFULLY!\n")
        print_info("Order ID", str(result.get('order_id', 'N/A')))
        print_info("Ticker", TICKER)
        print_info("Action", "SELL")
        print_info("Executed Price", f"{result.get('executed_price', 0):,.0f} KRW")
        print_info("Executed Units", f"{result.get('executed_units', 0):.6f} SOL")
        print_info("Total Value", f"{result.get('executed_units', 0) * result.get('executed_price', 0):,.2f} KRW")
        print_info("Status", result.get('message', 'N/A'))

        print("\n📊 Next Steps:")
        print("   1. Check your Bithumb account to verify the order")
        print("   2. Verify SOL balance is now 0 (or near 0)")
        print("   3. Check position state file: logs/positions_v3.json")
        print("   4. Verify SOL position has been removed from state")
        print("   5. Review transaction logs in logs/ directory")
        print("   6. Check your KRW balance increased by sale proceeds")

        # Verify position was removed
        time.sleep(1)
        print("\n🔍 Verifying Position Removal:")
        has_position = check_position_state(TICKER)
        if not has_position:
            print("✅ Position successfully removed from state file")
        else:
            print("⚠️  Position still exists in state file (may require manual cleanup)")

        return True

    else:
        print("\n❌ SELL ORDER EXECUTION FAILED\n")
        print_info("Error Message", result.get('message', 'Unknown error'))
        print_info("Order ID", str(result.get('order_id', 'None')))

        print("\n🔍 Troubleshooting:")
        print("   1. Check API keys have trading permissions enabled on Bithumb")
        print("   2. Verify SOL balance is still available (not in pending orders)")
        print("   3. Check Bithumb API status: https://api.bithumb.com/")
        print("   4. Review error logs in logs/ directory")
        print("   5. Try checking balance again - units may be locked in other orders")

        return False


if __name__ == '__main__':
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║                                                                    ║")
    print("║       ⚠️  REAL MONEY TRADING - NOT A SIMULATION ⚠️                ║")
    print("║                                                                    ║")
    print("║  This script will place a REAL SELL order on Bithumb exchange     ║")
    print("║  using your actual API keys.                                      ║")
    print("║                                                                    ║")
    print("║  Action: SELL 100% OF ALL SOL HOLDINGS                            ║")
    print("║  Execution Mode: LIVE (dry_run=False)                             ║")
    print("║  Confirmation Required: --confirm flag + user input               ║")
    print("║                                                                    ║")
    print("║  Press Ctrl+C now to cancel if you did not intend this.          ║")
    print("║                                                                    ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print("\n")

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Sell all SOL holdings via Ver3 LiveExecutorV3')
    parser.add_argument('--confirm', action='store_true',
                       help='Confirm that you want to proceed with the sale')
    args = parser.parse_args()

    try:
        time.sleep(2)  # Give user time to read warning
        success = main(confirm_flag=args.confirm)

        print("\n" + "=" * 70)
        if success:
            print("✅ TEST COMPLETED SUCCESSFULLY - SOL SOLD")
        else:
            print("❌ TEST FAILED OR CANCELLED")
        print("=" * 70 + "\n")

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\n❌ Test cancelled by user (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
