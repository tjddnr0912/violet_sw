#!/usr/bin/env python3
"""
SOL Purchase Verification Script for Version 2

This script verifies the SOL purchase functionality using the fixed Bithumb API.
It includes all necessary safety checks and confirmation prompts.

IMPORTANT: This script executes REAL trades with REAL money.
Use with extreme caution!

Usage:
    python verify_sol_purchase.py [--amount AMOUNT] [--auto-confirm] [--no-confirm]
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime

# Add parent directories to path for imports
base_path = Path(__file__).parent.parent
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

from lib.api.bithumb_api import BithumbAPI, get_ticker
from lib.core.logger import TradingLogger
from lib.core.config_common import API_CONFIG
from ver2 import config_v2


def print_header():
    """Print script header with warnings."""
    print("=" * 80)
    print("⚠️  SOL PURCHASE VERIFICATION SCRIPT - VERSION 2")
    print("=" * 80)
    print()
    print("🔴 WARNING: THIS SCRIPT EXECUTES REAL TRADES WITH REAL MONEY")
    print("🔴 WARNING: REAL FUNDS WILL BE USED FOR SOL PURCHASE")
    print()
    print("=" * 80)
    print()


def check_api_credentials(api_config: dict) -> tuple[bool, str]:
    """
    Verify API credentials are properly configured.

    Returns:
        Tuple of (is_valid, error_message)
    """
    connect_key = api_config.get('bithumb_connect_key', '')
    secret_key = api_config.get('bithumb_secret_key', '')

    # Check if keys are set
    if not connect_key or not secret_key:
        return False, "API keys are not set"

    # Check for default/placeholder values
    if connect_key in ['YOUR_CONNECT_KEY', 'your_connect_key']:
        return False, "Connect key is still set to default placeholder value"

    if secret_key in ['YOUR_SECRET_KEY', 'your_secret_key']:
        return False, "Secret key is still set to default placeholder value"

    # Check minimum length
    if len(connect_key) < 20:
        return False, f"Connect key too short ({len(connect_key)} chars)"

    if len(secret_key) < 20:
        return False, f"Secret key too short ({len(secret_key)} chars)"

    return True, ""


def get_current_price(ticker: str) -> float:
    """
    Get current price for a cryptocurrency.

    Args:
        ticker: Cryptocurrency symbol (e.g., 'SOL')

    Returns:
        Current price in KRW, or 0.0 if failed
    """
    try:
        data = get_ticker(ticker)
        if data:
            price = float(data.get('closing_price', 0))
            return price
        return 0.0
    except Exception as e:
        print(f"❌ Error getting price: {e}")
        return 0.0


def calculate_purchase_units(amount_krw: float, price: float) -> float:
    """
    Calculate how many units can be purchased with given KRW amount.

    Args:
        amount_krw: KRW amount to spend
        price: Current price per unit

    Returns:
        Number of units that can be purchased (rounded to 8 decimal places for Bithumb)
    """
    if price <= 0:
        return 0.0

    # Calculate units and round to 8 decimal places (Bithumb requirement)
    units = amount_krw / price
    return round(units, 8)


def display_purchase_plan(ticker: str, amount_krw: float, price: float, units: float):
    """Display purchase plan details."""
    print("\n📋 PURCHASE PLAN")
    print("-" * 60)
    print(f"  Cryptocurrency:  {ticker}")
    print(f"  Current Price:   {price:,.0f} KRW")
    print(f"  Purchase Amount: {amount_krw:,.0f} KRW")
    print(f"  Units to Buy:    {units:.8f} {ticker}")
    print(f"  Total Cost:      {amount_krw:,.0f} KRW")
    print("-" * 60)
    print()


def check_minimum_order_amount(amount_krw: float) -> tuple[bool, str]:
    """
    Check if order amount meets Bithumb minimum requirement.

    Bithumb minimum order: 5,000 KRW

    Returns:
        Tuple of (is_valid, message)
    """
    BITHUMB_MIN_ORDER = 5000

    if amount_krw < BITHUMB_MIN_ORDER:
        return False, (
            f"Order amount ({amount_krw:,.0f} KRW) is below Bithumb minimum ({BITHUMB_MIN_ORDER:,.0f} KRW).\n"
            f"  💡 Suggestion: Use at least {BITHUMB_MIN_ORDER:,.0f} KRW for this order."
        )

    return True, ""


def get_user_confirmation(amount_krw: float) -> bool:
    """
    Ask user for final confirmation before executing trade.

    Args:
        amount_krw: KRW amount to spend

    Returns:
        True if user confirms, False otherwise
    """
    print("🔴 FINAL CONFIRMATION REQUIRED")
    print("-" * 60)
    print(f"  You are about to execute a REAL trade for {amount_krw:,.0f} KRW")
    print(f"  This will use REAL MONEY from your Bithumb account")
    print("-" * 60)
    print()

    response = input("Type 'CONFIRM' to proceed with the order: ").strip()

    if response == 'CONFIRM':
        print("\n✅ Confirmation received. Proceeding with order execution...\n")
        return True
    else:
        print(f"\n❌ Confirmation failed (you typed: '{response}'). Order cancelled.\n")
        return False


def execute_purchase(api: BithumbAPI, ticker: str, units: float) -> dict:
    """
    Execute the actual purchase order.

    Args:
        api: BithumbAPI instance
        ticker: Cryptocurrency symbol
        units: Number of units to buy

    Returns:
        API response dictionary
    """
    print(f"🚀 Executing market buy order for {units:.8f} {ticker}...")
    print()

    response = api.place_buy_order(
        order_currency=ticker,
        payment_currency="KRW",
        units=units,
        type_order="market"
    )

    return response


def display_execution_result(response: dict):
    """Display execution result."""
    print("\n" + "=" * 80)
    print("📊 EXECUTION RESULT")
    print("=" * 80)

    if not response:
        print("❌ No response received from API")
        return

    status = response.get('status', 'UNKNOWN')

    if status == '0000':
        print("✅ ORDER EXECUTED SUCCESSFULLY")
        print("-" * 60)
        print(f"  Order ID:   {response.get('order_id', 'N/A')}")
        print(f"  Status:     {status}")
        print(f"  Message:    Success")

        # Display additional data if available
        if 'data' in response:
            data = response['data']
            if isinstance(data, dict):
                for key, value in data.items():
                    print(f"  {key}:  {value}")
    else:
        print("❌ ORDER FAILED")
        print("-" * 60)
        print(f"  Status Code: {status}")
        print(f"  Message:     {response.get('message', 'Unknown error')}")

    print("-" * 60)
    print("\n📝 Full API Response:")
    print(response)
    print()


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description='SOL Purchase Verification Script - Execute real SOL purchase on Bithumb'
    )
    parser.add_argument(
        '--amount',
        type=float,
        default=5000,
        help='Amount in KRW to purchase (default: 5000, minimum: 5000)'
    )
    parser.add_argument(
        '--auto-confirm',
        action='store_true',
        help='Automatically confirm the purchase without prompting'
    )
    parser.add_argument(
        '--no-confirm',
        action='store_true',
        help='Skip execution (dry-run mode for testing script flow)'
    )

    return parser.parse_args()


def main():
    """Main verification script execution."""
    # Parse arguments
    args = parse_arguments()

    print_header()

    # Configuration
    TICKER = 'SOL'
    REQUESTED_AMOUNT_KRW = args.amount
    RECOMMENDED_AMOUNT_KRW = 5000  # Bithumb minimum
    AUTO_CONFIRM = args.auto_confirm
    NO_CONFIRM = args.no_confirm

    # Step 1: Check API credentials
    print("🔍 Step 1: Verifying API credentials...")
    is_valid, error_msg = check_api_credentials(API_CONFIG)

    if not is_valid:
        print(f"❌ API credential check failed: {error_msg}")
        print("\n💡 Please set your API keys:")
        print("   export BITHUMB_CONNECT_KEY='your_connect_key'")
        print("   export BITHUMB_SECRET_KEY='your_secret_key'")
        sys.exit(1)

    print("✅ API credentials verified")
    print(f"   Connect Key: {API_CONFIG['bithumb_connect_key'][:10]}...")
    print()

    # Step 2: Check minimum order amount
    print("🔍 Step 2: Checking order amount...")
    is_valid, message = check_minimum_order_amount(REQUESTED_AMOUNT_KRW)

    if not is_valid:
        print(f"⚠️  {message}")
        print()

        if AUTO_CONFIRM:
            amount_krw = RECOMMENDED_AMOUNT_KRW
            print(f"✅ Auto-using recommended amount: {amount_krw:,.0f} KRW")
        else:
            print(f"❌ Order amount too low. Please use --amount {RECOMMENDED_AMOUNT_KRW} or higher")
            sys.exit(1)
    else:
        amount_krw = REQUESTED_AMOUNT_KRW
        print(f"✅ Order amount OK: {amount_krw:,.0f} KRW")

    print()

    # Step 3: Get current SOL price
    print("🔍 Step 3: Fetching current SOL price...")
    price = get_current_price(TICKER)

    if price <= 0:
        print("❌ Failed to get current price")
        sys.exit(1)

    print(f"✅ Current {TICKER} price: {price:,.0f} KRW")
    print()

    # Step 4: Calculate purchase units
    print("🔍 Step 4: Calculating purchase units...")
    units = calculate_purchase_units(amount_krw, price)

    if units <= 0:
        print("❌ Cannot calculate units (price may be invalid)")
        sys.exit(1)

    print(f"✅ Calculated units: {units:.8f} {TICKER}")
    print()

    # Step 5: Display purchase plan
    display_purchase_plan(TICKER, amount_krw, price, units)

    # Step 6: Check dry-run mode and no-confirm flag
    dry_run = config_v2.EXECUTION_CONFIG.get('dry_run', True)

    if dry_run:
        print("ℹ️  DRY-RUN MODE IS ENABLED (from config)")
        print("   No real order will be executed.")
        print("   Set config_v2.EXECUTION_CONFIG['dry_run'] = False for live trading")
        print()
        sys.exit(0)

    if NO_CONFIRM:
        print("ℹ️  NO-CONFIRM MODE (--no-confirm flag)")
        print("   Script will not execute real order (testing mode)")
        print()
        sys.exit(0)

    # Step 7: Final confirmation
    if AUTO_CONFIRM:
        print("⚠️  AUTO-CONFIRM MODE ENABLED (--auto-confirm flag)")
        print(f"   Proceeding with order for {amount_krw:,.0f} KRW automatically")
        print()
    else:
        if not get_user_confirmation(amount_krw):
            print("Order cancelled by user")
            sys.exit(0)

    # Step 8: Initialize API and execute order
    print("🔍 Step 8: Initializing API and executing order...")

    try:
        # Initialize BithumbAPI with credentials
        api = BithumbAPI(
            connect_key=API_CONFIG['bithumb_connect_key'],
            secret_key=API_CONFIG['bithumb_secret_key']
        )

        # Execute purchase
        response = execute_purchase(api, TICKER, units)

        # Display result
        display_execution_result(response)

        # Log execution time
        print(f"⏰ Execution completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

    except Exception as e:
        print(f"\n❌ EXCEPTION OCCURRED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("=" * 80)
    print("✅ VERIFICATION SCRIPT COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Script interrupted by user (Ctrl+C)")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
