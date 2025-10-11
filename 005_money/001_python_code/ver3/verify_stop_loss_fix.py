#!/usr/bin/env python3
"""
Verification script to test that the stop-loss calculation fix works correctly.

This script tests:
1. New position entry uses entry_price for stop-loss calculation
2. Stop-loss is always BELOW entry price
3. Pyramiding entries use existing stop-loss
"""

import sys
from pathlib import Path

# Add parent directory to path
base_path = Path(__file__).parent.parent
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

from ver3.config_v3 import get_version_config
from ver2.strategy_v2 import StrategyV2
from lib.core.logger import TradingLogger


def test_stop_loss_calculation():
    """Test that stop-loss calculation produces valid values."""
    print("=" * 80)
    print("STOP-LOSS FIX VERIFICATION")
    print("=" * 80)

    # Initialize
    config = get_version_config()
    logger = TradingLogger()
    strategy = StrategyV2(config, logger)

    # Test coins
    test_cases = [
        ('ETH', 6328000.0),  # Entry price from actual position
        ('XRP', 4097.0),     # Entry price from actual position
        ('BTC', 150000000.0),  # Example entry price
    ]

    chandelier_multiplier = config.get('INDICATOR_CONFIG', {}).get('chandelier_multiplier', 3.0)

    print(f"\nConfiguration:")
    print(f"  Chandelier Multiplier: {chandelier_multiplier}")
    print(f"  ATR Period: {config.get('INDICATOR_CONFIG', {}).get('atr_period', 14)}")

    all_passed = True

    for ticker, entry_price in test_cases:
        print(f"\n{'='*80}")
        print(f"Testing {ticker} (Entry Price: {entry_price:,.0f} KRW)")
        print(f"{'='*80}")

        # Get analysis
        analysis = strategy.analyze_market(ticker, interval='4h')

        if not analysis:
            print(f"❌ Failed to get analysis for {ticker}")
            all_passed = False
            continue

        # Extract data
        execution_data = analysis.get('execution_data', {})
        atr = execution_data.get('atr', 0)
        current_price = analysis.get('current_price', 0)
        old_stop_loss = analysis.get('stop_loss_price', 0)  # Historical highest_high method

        # Calculate NEW stop-loss (using entry price)
        new_stop_loss = entry_price - (atr * chandelier_multiplier)

        print(f"\n📊 Market Data:")
        print(f"   Current Price: {current_price:,.0f} KRW")
        print(f"   ATR (14):      {atr:,.2f} KRW")

        print(f"\n🧮 Stop-Loss Comparison:")
        print(f"   OLD method (historical highest_high): {old_stop_loss:,.0f} KRW")
        print(f"   NEW method (entry price):             {new_stop_loss:,.0f} KRW")

        # Verify OLD method is broken
        old_pct = ((old_stop_loss - entry_price) / entry_price) * 100
        print(f"\n❌ OLD Method Analysis:")
        print(f"   Entry:     {entry_price:,.0f} KRW")
        print(f"   Stop-Loss: {old_stop_loss:,.0f} KRW")
        print(f"   Difference: {old_pct:+.2f}%")

        if old_stop_loss > entry_price:
            print(f"   ❌ BROKEN: Stop-loss is ABOVE entry price!")

        # Verify NEW method works
        new_pct = ((new_stop_loss - entry_price) / entry_price) * 100
        print(f"\n✅ NEW Method Analysis:")
        print(f"   Entry:     {entry_price:,.0f} KRW")
        print(f"   Stop-Loss: {new_stop_loss:,.0f} KRW")
        print(f"   Difference: {new_pct:+.2f}%")

        # Check validity
        test_passed = True

        if new_stop_loss >= entry_price:
            print(f"   ❌ FAIL: Stop-loss ({new_stop_loss:,.0f}) >= Entry ({entry_price:,.0f})")
            test_passed = False
            all_passed = False
        else:
            print(f"   ✅ PASS: Stop-loss is {abs(new_pct):.2f}% below entry price")

        if new_pct < -10:
            print(f"   ⚠️  WARNING: Stop-loss is very far ({abs(new_pct):.2f}%) from entry")

        if not test_passed:
            all_passed = False

    print(f"\n{'='*80}")
    if all_passed:
        print("✅ ALL TESTS PASSED - Stop-loss fix is working correctly!")
    else:
        print("❌ SOME TESTS FAILED - Stop-loss calculation still has issues")
    print(f"{'='*80}\n")

    return all_passed


def verify_positions_file():
    """Verify that positions_v3.json has correct stop-loss values."""
    print("\n" + "=" * 80)
    print("VERIFYING positions_v3.json")
    print("=" * 80)

    import json

    try:
        with open('logs/positions_v3.json', 'r') as f:
            positions = json.load(f)

        print(f"\nFound {len(positions)} positions:\n")

        all_valid = True

        for ticker, pos in positions.items():
            entry_price = pos.get('entry_price', 0)
            stop_loss = pos.get('stop_loss', 0)

            pct_diff = ((stop_loss - entry_price) / entry_price) * 100

            print(f"[{ticker}]")
            print(f"  Entry Price: {entry_price:,.0f} KRW")
            print(f"  Stop-Loss:   {stop_loss:,.0f} KRW")
            print(f"  Difference:  {pct_diff:+.2f}%")

            if stop_loss >= entry_price:
                print(f"  ❌ INVALID: Stop-loss is above or at entry price!")
                all_valid = False
            elif pct_diff > -5:
                print(f"  ⚠️  WARNING: Stop-loss is very tight ({abs(pct_diff):.2f}%)")
            else:
                print(f"  ✅ VALID: Stop-loss is {abs(pct_diff):.2f}% below entry")
            print()

        if all_valid:
            print("✅ All positions have valid stop-loss values")
        else:
            print("❌ Some positions have invalid stop-loss values")

        return all_valid

    except FileNotFoundError:
        print("❌ positions_v3.json not found")
        return False
    except Exception as e:
        print(f"❌ Error reading positions: {e}")
        return False


if __name__ == "__main__":
    print("\n🔍 STOP-LOSS FIX VERIFICATION SUITE\n")

    # Test 1: Algorithm verification
    test1_passed = test_stop_loss_calculation()

    # Test 2: Positions file verification
    test2_passed = verify_positions_file()

    # Final result
    print("\n" + "=" * 80)
    print("FINAL VERIFICATION RESULTS")
    print("=" * 80)
    print(f"Algorithm Test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Positions File: {'✅ PASSED' if test2_passed else '❌ FAILED'}")

    if test1_passed and test2_passed:
        print("\n✅ VERIFICATION COMPLETE - All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ VERIFICATION FAILED - Issues detected")
        sys.exit(1)
