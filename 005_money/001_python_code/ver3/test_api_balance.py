#!/usr/bin/env python3
"""
Test script to verify Bithumb API balance query works correctly.

This script tests:
1. API connection and authentication
2. Balance query for KRW and all coins
3. Price query for specific coins
4. P&L calculation example

Run this before implementing the GUI fix to ensure API access works.
"""

import sys
import os

# Add paths
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)
sys.path.insert(0, os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

from lib.api.bithumb_api import BithumbAPI, get_ticker
from ver3 import config_v3


def test_api_connection():
    """Test API connection and authentication"""
    print("=" * 70)
    print("Testing Bithumb API Connection")
    print("=" * 70)

    # Get API config
    config = config_v3.get_version_config()
    api_config = config.get('API_CONFIG', {})

    connect_key = api_config.get('bithumb_connect_key')
    secret_key = api_config.get('bithumb_secret_key')

    print(f"\nAPI Configuration:")
    if connect_key and not connect_key.startswith('YOUR_'):
        print(f"  Connect Key: {connect_key[:10]}...")
    else:
        print(f"  Connect Key: NOT CONFIGURED (using default/placeholder)")

    if secret_key and not secret_key.startswith('YOUR_'):
        print(f"  Secret Key: {secret_key[:10]}...")
    else:
        print(f"  Secret Key: NOT CONFIGURED (using default/placeholder)")

    # Initialize API
    api = BithumbAPI(connect_key=connect_key, secret_key=secret_key)

    # Test balance query
    print("\n[1/3] Testing balance query...")
    print("-" * 70)
    balance_response = api.get_balance(currency='ALL')

    if balance_response and balance_response.get('status') == '0000':
        print("✅ Balance query successful!")
        data = balance_response.get('data', {})

        # Show KRW balance
        krw_total = float(data.get('total_krw', '0'))
        krw_available = float(data.get('available_krw', '0'))
        krw_in_use = float(data.get('in_use_krw', '0'))

        print(f"\n💰 KRW Balance:")
        print(f"  Total:     {krw_total:>15,.0f} KRW")
        print(f"  Available: {krw_available:>15,.0f} KRW")
        print(f"  In Use:    {krw_in_use:>15,.0f} KRW")

        # Show coin holdings
        print("\n🪙 Coin Holdings:")
        found_holdings = False

        for coin in ['BTC', 'ETH', 'XRP', 'SOL']:
            total_key = f'total_{coin.lower()}'
            available_key = f'available_{coin.lower()}'
            in_use_key = f'in_use_{coin.lower()}'

            total = float(data.get(total_key, '0'))
            available = float(data.get(available_key, '0'))
            in_use = float(data.get(in_use_key, '0'))

            if total > 0:
                found_holdings = True
                print(f"  {coin}:")
                print(f"    Total:     {total:>15.8f}")
                print(f"    Available: {available:>15.8f}")
                print(f"    In Use:    {in_use:>15.8f}")

        if not found_holdings:
            print("  (No coin holdings found)")

        return True, data
    else:
        status = balance_response.get('status', 'UNKNOWN') if balance_response else 'NO_RESPONSE'
        message = balance_response.get('message', 'No response from API') if balance_response else 'No response from API'

        print(f"❌ Balance query failed!")
        print(f"  Status Code: {status}")
        print(f"  Message: {message}")

        if status == '5100':
            print("\n💡 Error 5100 means: Invalid API Key")
            print("   Please check your API credentials in environment variables or config_v3.py")
        elif status == '5200':
            print("\n💡 Error 5200 means: API Signature Error")
            print("   Please check your Secret Key is correct")
        elif status == '5600':
            print("\n💡 Error 5600 means: Missing API Permissions")
            print("   Please enable 'Balance Inquiry' permission on Bithumb API settings")

        return False, None


def test_price_query():
    """Test price query for coins"""
    print("\n[2/3] Testing price query...")
    print("-" * 70)

    coins_to_test = ['BTC', 'ETH', 'SOL', 'XRP']

    for coin in coins_to_test:
        ticker_data = get_ticker(coin)
        if ticker_data:
            price = float(ticker_data.get('closing_price', '0'))
            print(f"✅ {coin:>5} price: {price:>15,.0f} KRW")
        else:
            print(f"❌ {coin:>5} price query failed")


def test_pnl_calculation(balance_data):
    """Test P&L calculation for holdings"""
    print("\n[3/3] Testing P&L calculation...")
    print("-" * 70)

    if not balance_data:
        print("⚠️  No balance data available for P&L calculation")
        return

    found_any = False

    # Check each coin
    for coin in ['BTC', 'ETH', 'SOL', 'XRP']:
        total_key = f'total_{coin.lower()}'
        quantity = float(balance_data.get(total_key, '0'))

        if quantity > 0:
            found_any = True

            # Get current price
            ticker_data = get_ticker(coin)
            if ticker_data:
                current_price = float(ticker_data.get('closing_price', '0'))
                current_value = quantity * current_price

                print(f"\n{coin} Holdings:")
                print(f"  Quantity:      {quantity:>15.8f}")
                print(f"  Current Price: {current_price:>15,.0f} KRW")
                print(f"  Current Value: {current_value:>15,.0f} KRW")

                # Note: We can't calculate actual P&L without average purchase price
                # That comes from positions file or trade history
                print(f"  (Note: For P&L calculation, need avg purchase price from positions file)")

    if not found_any:
        print("⚠️  No coin holdings found for P&L calculation")


def main():
    """Main test function"""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " Bithumb API Balance Query Test ".center(68) + "║")
    print("╚" + "═" * 68 + "╝")
    print()

    # Test API connection and balance
    success, balance_data = test_api_connection()

    # Test price queries
    test_price_query()

    # Test P&L calculation
    test_pnl_calculation(balance_data)

    # Summary
    print()
    print("=" * 70)
    if success:
        print("✅ API TESTS PASSED - API is working correctly!")
        print("=" * 70)
        print("\nNext steps:")
        print("1. The API connection is working")
        print("2. You can now implement the real balance query in GUI")
        print("3. Run: python 001_python_code/ver3/gui_app_v3.py")
    else:
        print("❌ API TEST FAILED - Please fix API configuration")
        print("=" * 70)
        print("\nTroubleshooting:")
        print("1. Check API keys are correctly set in environment variables:")
        print("   export BITHUMB_CONNECT_KEY='your_key_here'")
        print("   export BITHUMB_SECRET_KEY='your_secret_here'")
        print()
        print("2. Or set them in ver3/config_v3.py API_CONFIG section")
        print()
        print("3. Verify API permissions on Bithumb:")
        print("   - Login to Bithumb > My Page > API Management")
        print("   - Ensure 'Balance Inquiry' permission is enabled")
        print()
        print("4. Check API keys are valid (not expired)")
    print()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
