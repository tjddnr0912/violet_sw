#!/usr/bin/env python3
"""
Test Script: Real ETH Purchase (5000 KRW) using Ver3 LiveExecutorV3 - AUTO MODE

This script tests Ver3's actual buy execution code by placing a REAL order
on Bithumb to purchase exactly 5000 KRW worth of ETH.

⚠️  WARNING: THIS USES REAL MONEY - NOT A DRY RUN ⚠️
⚠️  AUTO-CONFIRMATION MODE - NO PROMPTS ⚠️

Usage:
    python test_eth_buy_5000_auto.py --confirm

The --confirm flag is REQUIRED to proceed with execution.

Requirements:
- BITHUMB_CONNECT_KEY and BITHUMB_SECRET_KEY environment variables must be set
- Minimum 5000 KRW available in Bithumb account
- Bithumb API must have trading permissions enabled
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


def get_current_eth_price() -> float:
    """Get current ETH price from Bithumb"""
    try:
        ticker_data = get_ticker('ETH')
        if ticker_data:
            price = float(ticker_data.get('closing_price', 0))
            return price
        return 0.0
    except Exception as e:
        print(f"❌ Error fetching ETH price: {e}")
        return 0.0


def calculate_units(krw_amount: float, price: float) -> float:
    """Calculate ETH units for given KRW amount"""
    if price <= 0:
        return 0.0

    # Calculate raw units
    units = krw_amount / price

    # Round to 4 decimal places (Bithumb standard)
    units = round(units, 4)

    return units


def validate_price(price: float) -> bool:
    """Validate ETH price is in reasonable range"""
    # ETH price sanity checks (as of 2025)
    MIN_REASONABLE_PRICE = 1000000   # 1M KRW minimum
    MAX_REASONABLE_PRICE = 10000000  # 10M KRW maximum

    if price < MIN_REASONABLE_PRICE:
        print_warning(f"ETH price seems too low: {price:,.0f} KRW")
        return False

    if price > MAX_REASONABLE_PRICE:
        print_warning(f"ETH price seems too high: {price:,.0f} KRW")
        return False

    return True


def main(auto_confirm: bool = False):
    """Main test execution"""
    print_header("Ver3 LiveExecutorV3 - Real ETH Purchase Test (AUTO MODE)")
    print("This script will purchase 5000 KRW worth of ETH using REAL API")

    if not auto_confirm:
        print("\n❌ ERROR: --confirm flag is required to execute this script")
        print("\nUsage: python test_eth_buy_5000_auto.py --confirm")
        return False

    # Configuration
    PURCHASE_AMOUNT_KRW = 5000
    TICKER = 'ETH'

    # Step 1: Verify API Keys
    print_header("Step 1: Verifying API Keys")
    connect_key, secret_key = verify_api_keys()

    if not connect_key or not secret_key:
        print("❌ Test aborted - API keys not properly configured")
        return False

    print(f"✅ API Keys found:")
    print_info("Connect Key", f"{connect_key[:10]}...{connect_key[-4:]}")
    print_info("Secret Key", f"{secret_key[:10]}...{secret_key[-4:]}")

    # Step 2: Get Current ETH Price
    print_header("Step 2: Fetching Current ETH Price")
    current_price = get_current_eth_price()

    if current_price <= 0:
        print("❌ Failed to fetch ETH price - cannot proceed")
        return False

    print(f"✅ Current ETH Price: {current_price:,.0f} KRW")

    # Step 3: Validate Price
    print_header("Step 3: Validating Price")
    if not validate_price(current_price):
        print("❌ Price validation failed - please check manually")
        return False

    print("✅ Price is within reasonable range")

    # Step 4: Calculate Units
    print_header("Step 4: Calculating Purchase Units")
    units_to_buy = calculate_units(PURCHASE_AMOUNT_KRW, current_price)

    if units_to_buy <= 0:
        print("❌ Failed to calculate units")
        return False

    print_info("KRW Amount", f"{PURCHASE_AMOUNT_KRW:,.0f} KRW")
    print_info("ETH Price", f"{current_price:,.0f} KRW")
    print_info("ETH Units", f"{units_to_buy:.6f} ETH")
    print_info("Actual Cost", f"{units_to_buy * current_price:,.2f} KRW")

    # Step 5: Display Purchase Details (AUTO-CONFIRM)
    print_header("Step 5: Purchase Details (AUTO-CONFIRM MODE)")
    print_warning("THIS IS NOT A DRY RUN - REAL ORDER WILL BE PLACED")

    print("\nPurchase Details:")
    print_info("Cryptocurrency", "ETH (Ethereum)")
    print_info("Purchase Amount", f"{PURCHASE_AMOUNT_KRW:,.0f} KRW")
    print_info("Current ETH Price", f"{current_price:,.0f} KRW")
    print_info("Units to Purchase", f"{units_to_buy:.4f} ETH")
    print_info("Estimated Total", f"{PURCHASE_AMOUNT_KRW:,.0f} KRW")
    print_info("Trading Fee (~0.05%)", f"~{PURCHASE_AMOUNT_KRW * 0.0005:,.0f} KRW")

    print("\n✅ Auto-confirmed via --confirm flag")
    print("⏳ Proceeding with real order in 3 seconds...")
    time.sleep(3)

    # Step 6: Initialize Components
    print_header("Step 6: Initializing Trading Components")

    # Initialize API
    api = BithumbAPI(connect_key=connect_key, secret_key=secret_key)
    print("✅ BithumbAPI initialized")

    # Initialize Logger
    config = get_version_config()
    log_dir = config['LOGGING_CONFIG'].get('log_dir', 'logs')
    logger = TradingLogger(log_dir=log_dir)
    print("✅ TradingLogger initialized")

    # Initialize LiveExecutorV3
    executor = LiveExecutorV3(api=api, logger=logger, config=config)
    print("✅ LiveExecutorV3 initialized")

    # Step 7: Execute Real Order
    print_header("Step 7: Executing REAL BUY Order on Bithumb")
    print_warning("PLACING REAL ORDER NOW...")

    result = executor.execute_order(
        ticker=TICKER,
        action='BUY',
        units=units_to_buy,
        price=current_price,
        dry_run=False,  # 🔴 REAL EXECUTION
        reason=f"Test purchase: {PURCHASE_AMOUNT_KRW} KRW worth of {TICKER}"
    )

    # Step 8: Report Results
    print_header("Step 8: Order Execution Results")

    if result['success']:
        print("\n✅ ORDER EXECUTED SUCCESSFULLY!\n")
        print_info("Order ID", str(result.get('order_id', 'N/A')))
        print_info("Ticker", TICKER)
        print_info("Action", "BUY")
        print_info("Executed Price", f"{result.get('executed_price', 0):,.0f} KRW")
        print_info("Executed Units", f"{result.get('executed_units', 0):.6f} ETH")
        print_info("Total Value", f"{result.get('executed_units', 0) * result.get('executed_price', 0):,.2f} KRW")
        print_info("Status", result.get('message', 'N/A'))

        print("\n📊 Next Steps:")
        print("   1. Check your Bithumb account to verify the order")
        print("   2. Check position state file: logs/positions_v3.json")
        print("   3. Review transaction logs in logs/ directory")

        return True

    else:
        print("\n❌ ORDER EXECUTION FAILED\n")
        print_info("Error Message", result.get('message', 'Unknown error'))
        print_info("Order ID", str(result.get('order_id', 'None')))

        print("\n🔍 Troubleshooting:")
        print("   1. Check API keys have trading permissions enabled on Bithumb")
        print("   2. Verify sufficient KRW balance in account")
        print("   3. Check Bithumb API status: https://api.bithumb.com/")
        print("   4. Review error logs in logs/ directory")

        return False


if __name__ == '__main__':
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║                                                                    ║")
    print("║       ⚠️  REAL MONEY TRADING - NOT A SIMULATION ⚠️                ║")
    print("║                                                                    ║")
    print("║  This script will place a REAL order on Bithumb exchange using    ║")
    print("║  your actual API keys and real KRW balance.                       ║")
    print("║                                                                    ║")
    print("║  Purchase Amount: 5000 KRW worth of ETH                           ║")
    print("║  Execution Mode: LIVE (dry_run=False)                             ║")
    print("║  Confirmation: AUTO (--confirm flag required)                     ║")
    print("║                                                                    ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print("\n")

    parser = argparse.ArgumentParser(description='Real ETH purchase test - AUTO MODE')
    parser.add_argument('--confirm', action='store_true',
                        help='Confirm execution (REQUIRED to proceed)')
    args = parser.parse_args()

    try:
        success = main(auto_confirm=args.confirm)

        print("\n" + "=" * 70)
        if success:
            print("✅ TEST COMPLETED SUCCESSFULLY")
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
