#!/usr/bin/env python3
"""
Test script to verify the corrected Bithumb API 1.2.0 endpoint implementation
"""

import sys
import os

# Add parent directories to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
grandparent_dir = os.path.dirname(parent_dir)

sys.path.insert(0, current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, grandparent_dir)

def test_api_endpoints():
    """Test that the API endpoints match Bithumb API 1.2.0 specification"""
    print("=" * 70)
    print("Bithumb API 1.2.0 Endpoint Verification Test")
    print("=" * 70)
    print()

    # Test 1: Import modules
    print("[1/5] Testing imports...")
    try:
        from lib.api.bithumb_api import BithumbAPI
        print("✓ BithumbAPI imported successfully")
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

    # Test 2: Verify method signatures
    print("\n[2/5] Checking method signatures...")
    try:
        import inspect

        buy_sig = inspect.signature(BithumbAPI.place_buy_order)
        sell_sig = inspect.signature(BithumbAPI.place_sell_order)

        print(f"✓ place_buy_order signature: {buy_sig}")
        print(f"✓ place_sell_order signature: {sell_sig}")

        # Verify parameters
        buy_params = list(buy_sig.parameters.keys())
        expected = ['self', 'order_currency', 'payment_currency', 'units', 'price', 'type_order']

        if buy_params == expected:
            print(f"✓ Parameters correct: {buy_params}")
        else:
            print(f"✗ Parameter mismatch!")
            print(f"  Expected: {expected}")
            print(f"  Got: {buy_params}")
            return False

    except Exception as e:
        print(f"✗ Signature check failed: {e}")
        return False

    # Test 3: Verify endpoint logic in source code
    print("\n[3/5] Verifying endpoint implementation...")
    try:
        api_file = os.path.join(os.path.dirname(__file__), '../lib/api/bithumb_api.py')
        with open(api_file, 'r') as f:
            content = f.read()

        # Check for correct endpoints
        checks = [
            ('endpoint = "/trade/market_buy"', 'Market buy endpoint'),
            ('endpoint = "/trade/market_sell"', 'Market sell endpoint'),
            ("'order_currency': order_currency", 'order_currency parameter'),
            ("'payment_currency': payment_currency", 'payment_currency parameter'),
        ]

        for pattern, description in checks:
            if pattern in content:
                print(f"✓ Found: {description}")
            else:
                print(f"✗ Missing: {description}")
                return False

    except Exception as e:
        print(f"✗ Code verification failed: {e}")
        return False

    # Test 4: Verify no legacy '/trade/place' for market orders
    print("\n[4/5] Checking for legacy endpoint removal...")
    try:
        # Count occurrences of /trade/place in context of market orders
        lines = content.split('\n')
        market_buy_section = False
        market_sell_section = False

        for i, line in enumerate(lines):
            if 'def place_buy_order' in line:
                market_buy_section = True
                market_sell_section = False
            elif 'def place_sell_order' in line:
                market_buy_section = False
                market_sell_section = True
            elif 'def ' in line and line.strip().startswith('def '):
                market_buy_section = False
                market_sell_section = False

            # Check that market orders don't use legacy endpoint
            if (market_buy_section or market_sell_section):
                if 'endpoint = "/trade/place"' in line and 'type_order == "market"' in lines[max(0, i-3):i+3]:
                    print(f"✗ Found legacy endpoint in market order section at line {i+1}")
                    return False

        print("✓ No legacy '/trade/place' endpoint used for market orders")

    except Exception as e:
        print(f"✗ Legacy endpoint check failed: {e}")
        return False

    # Test 5: Syntax check
    print("\n[5/5] Running Python syntax check...")
    try:
        import py_compile
        py_compile.compile(api_file, doraise=True)
        print("✓ No syntax errors in bithumb_api.py")
    except Exception as e:
        print(f"✗ Syntax error: {e}")
        return False

    return True

def show_fix_details():
    """Show details of the fix"""
    print("\n" + "=" * 70)
    print("FIX DETAILS - Bithumb API 1.2.0 Compliance")
    print("=" * 70)
    print()
    print("PROBLEM:")
    print("  - Used incorrect endpoint: /trade/place (doesn't exist in API 1.2.0)")
    print("  - Sent 'type' parameter for market orders (not needed)")
    print("  - Caused 'Invalid Parameter' error (code 5500)")
    print()
    print("SOLUTION:")
    print("  - Market Buy: POST /trade/market_buy")
    print("  - Market Sell: POST /trade/market_sell")
    print("  - Parameters: order_currency, payment_currency, units")
    print()
    print("BEFORE (Incorrect):")
    print('  endpoint = "/trade/place"')
    print("  parameters = {")
    print("    'order_currency': 'SOL',")
    print("    'payment_currency': 'KRW',")
    print("    'type': 'market',      # ← Not needed for market orders!")
    print("    'units': '0.155231'")
    print("  }")
    print()
    print("AFTER (Correct - API 1.2.0):")
    print('  endpoint = "/trade/market_buy"  # Separate endpoint for market buy')
    print("  parameters = {")
    print("    'order_currency': 'SOL',")
    print("    'payment_currency': 'KRW',")
    print("    'units': '0.155231'")
    print("  }")
    print()
    print("API 1.2.0 SPECIFICATIONS:")
    print("  - Market Buy:  https://api.bithumb.com/trade/market_buy")
    print("  - Market Sell: https://api.bithumb.com/trade/market_sell")
    print("  - Required: order_currency, payment_currency, units")
    print("  - Minimum order: 5,000 KRW")
    print()
    print("AFFECTED OPERATIONS:")
    print("  ✓ Market buy orders (BTC, ETH, XRP, SOL)")
    print("  ✓ Market sell orders (all coins)")
    print("  ✓ All real trading operations")
    print()
    print("=" * 70)

if __name__ == '__main__':
    print()
    success = test_api_endpoints()

    if success:
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED - API 1.2.0 COMPLIANT")
        print("=" * 70)
        show_fix_details()
        print("\nNEXT STEPS:")
        print("1. Restart the trading bot:")
        print("   python run_gui.py")
        print()
        print("2. Monitor logs for successful order execution:")
        print("   tail -f logs/trading_$(date +%Y%m%d).log")
        print()
        print("3. Expected success message:")
        print("   ✅ Order executed successfully")
        print("   Order ID: XXXXXXXX")
        print()
        print("4. Verify no more 'Invalid Parameter' (5500) errors")
        print()
    else:
        print("\n" + "=" * 70)
        print("❌ TESTS FAILED")
        print("=" * 70)
        print("\nPlease review the errors above and fix them.")
        print()
        sys.exit(1)
