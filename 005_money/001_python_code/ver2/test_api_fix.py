#!/usr/bin/env python3
"""
Test script to verify the API fix for Invalid Parameter error
"""

import sys
import os

# Add parent directories to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

def test_api_syntax():
    """Test that the API call syntax is correct"""
    print("=" * 60)
    print("API Fix Verification Test")
    print("=" * 60)
    print()

    # Test 1: Import modules
    print("[1/4] Testing imports...")
    try:
        from ver2.live_executor_v2 import LiveExecutorV2
        from lib.api.bithumb_api import BithumbAPI
        from lib.core.logger import TradingLogger
        print("✓ All modules imported successfully")
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False

    # Test 2: Check API method signatures
    print("\n[2/4] Checking API method signatures...")
    try:
        import inspect

        # Check place_buy_order signature
        buy_sig = inspect.signature(BithumbAPI.place_buy_order)
        print(f"✓ place_buy_order signature: {buy_sig}")

        # Check place_sell_order signature
        sell_sig = inspect.signature(BithumbAPI.place_sell_order)
        print(f"✓ place_sell_order signature: {sell_sig}")

        # Verify parameters
        buy_params = list(buy_sig.parameters.keys())
        expected_buy = ['self', 'order_currency', 'payment_currency', 'units', 'price', 'type_order']

        if buy_params == expected_buy:
            print(f"✓ place_buy_order parameters correct: {buy_params}")
        else:
            print(f"✗ place_buy_order parameters mismatch!")
            print(f"  Expected: {expected_buy}")
            print(f"  Got: {buy_params}")
            return False

    except Exception as e:
        print(f"✗ Signature check failed: {e}")
        return False

    # Test 3: Read and verify the fixed code
    print("\n[3/4] Verifying fixed code in live_executor_v2.py...")
    try:
        executor_file = os.path.join(os.path.dirname(__file__), 'live_executor_v2.py')
        with open(executor_file, 'r') as f:
            content = f.read()

        # Check for correct API calls
        if 'order_currency=ticker' in content:
            print("✓ Found 'order_currency=ticker' (correct parameter naming)")
        else:
            print("✗ Missing 'order_currency=ticker'")
            return False

        if 'payment_currency="KRW"' in content:
            print("✓ Found 'payment_currency=\"KRW\"' (correct parameter)")
        else:
            print("✗ Missing 'payment_currency=\"KRW\"'")
            return False

        if 'type_order="market"' in content:
            print("✓ Found 'type_order=\"market\"' (correct order type)")
        else:
            print("✗ Missing 'type_order=\"market\"'")
            return False

    except Exception as e:
        print(f"✗ Code verification failed: {e}")
        return False

    # Test 4: Syntax check
    print("\n[4/4] Running Python syntax check...")
    try:
        import py_compile
        executor_file = os.path.join(os.path.dirname(__file__), 'live_executor_v2.py')
        py_compile.compile(executor_file, doraise=True)
        print("✓ No syntax errors in live_executor_v2.py")
    except Exception as e:
        print(f"✗ Syntax error: {e}")
        return False

    return True

def show_fix_summary():
    """Show summary of the fix"""
    print("\n" + "=" * 60)
    print("FIX SUMMARY")
    print("=" * 60)
    print()
    print("PROBLEM:")
    print("  - API call was missing explicit parameter names")
    print("  - Caused 'Invalid Parameter' error (code 5500)")
    print()
    print("BEFORE (Incorrect):")
    print("  response = self.api.place_buy_order(ticker, units=units)")
    print()
    print("AFTER (Fixed):")
    print("  response = self.api.place_buy_order(")
    print("      order_currency=ticker,")
    print("      payment_currency=\"KRW\",")
    print("      units=units,")
    print("      type_order=\"market\"")
    print("  )")
    print()
    print("ROOT CAUSE:")
    print("  - Bithumb API expects specific parameter names")
    print("  - Must specify payment_currency explicitly")
    print("  - Must specify type_order for order type")
    print()
    print("AFFECTED COINS:")
    print("  - All 4 major coins: BTC, ETH, XRP, SOL")
    print()
    print("=" * 60)

if __name__ == '__main__':
    print()
    success = test_api_syntax()

    if success:
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        show_fix_summary()
        print("\nNEXT STEPS:")
        print("1. Restart the trading bot (GUI or CLI)")
        print("2. Monitor logs for successful order execution")
        print("3. Verify no more 'Invalid Parameter' errors")
        print()
    else:
        print("\n" + "=" * 60)
        print("❌ TESTS FAILED")
        print("=" * 60)
        print("\nPlease review the errors above and fix them.")
        print()
        sys.exit(1)
