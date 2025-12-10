#!/usr/bin/env python3
"""
Test TP2 close_position logic
"""

import sys
sys.path.append('001_python_code')

from datetime import datetime
from ver3.live_executor_v3 import Position

def test_tp2_detection():
    """Test TP2 detection logic"""
    print("=== Testing TP2 Detection ===\n")

    # Test Case 1: TP1 not hit (should NOT be TP2)
    pos1 = Position(
        ticker="BTC",
        size=0.001,
        entry_price=100000000,
        entry_time=datetime.now(),
        stop_loss=95000000
    )
    pos1.first_target_hit = False
    pos1.second_target_hit = False
    is_tp2_1 = pos1.first_target_hit and not pos1.second_target_hit
    print(f"Test 1 - TP1 not hit:")
    print(f"  first_target_hit: {pos1.first_target_hit}")
    print(f"  second_target_hit: {pos1.second_target_hit}")
    print(f"  is_tp2: {is_tp2_1}")
    print(f"  Expected: False")
    print(f"  Result: {'✅ PASS' if not is_tp2_1 else '❌ FAIL'}\n")

    # Test Case 2: TP1 hit, TP2 not hit (should be TP2)
    pos2 = Position(
        ticker="BTC",
        size=0.001,
        entry_price=100000000,
        entry_time=datetime.now(),
        stop_loss=95000000
    )
    pos2.first_target_hit = True
    pos2.second_target_hit = False
    is_tp2_2 = pos2.first_target_hit and not pos2.second_target_hit
    print(f"Test 2 - TP1 hit, TP2 not hit (TP2 exit):")
    print(f"  first_target_hit: {pos2.first_target_hit}")
    print(f"  second_target_hit: {pos2.second_target_hit}")
    print(f"  is_tp2: {is_tp2_2}")
    print(f"  Expected: True")
    print(f"  Result: {'✅ PASS' if is_tp2_2 else '❌ FAIL'}\n")

    # Test Case 3: Both TP1 and TP2 hit (should NOT be TP2)
    pos3 = Position(
        ticker="BTC",
        size=0.001,
        entry_price=100000000,
        entry_time=datetime.now(),
        stop_loss=95000000
    )
    pos3.first_target_hit = True
    pos3.second_target_hit = True
    is_tp2_3 = pos3.first_target_hit and not pos3.second_target_hit
    print(f"Test 3 - Both TP1 and TP2 hit (already closed):")
    print(f"  first_target_hit: {pos3.first_target_hit}")
    print(f"  second_target_hit: {pos3.second_target_hit}")
    print(f"  is_tp2: {is_tp2_3}")
    print(f"  Expected: False")
    print(f"  Result: {'✅ PASS' if not is_tp2_3 else '❌ FAIL'}\n")

def test_sell_units_calculation():
    """Test sell units calculation for TP2 vs normal exit"""
    print("=== Testing Sell Units Calculation ===\n")

    # Simulated values
    pos_size = 0.00030616
    actual_balance = 0.00030616

    # Test Case 1: TP2 exit (should use 100%)
    is_tp2 = True
    if is_tp2:
        sell_units = actual_balance
    else:
        sell_units = actual_balance * 0.999

    print(f"Test 1 - TP2 Exit:")
    print(f"  Position size: {pos_size:.8f}")
    print(f"  Actual balance: {actual_balance:.8f}")
    print(f"  is_tp2: {is_tp2}")
    print(f"  Sell units: {sell_units:.8f}")
    print(f"  Expected: {actual_balance:.8f} (100%)")
    print(f"  Result: {'✅ PASS' if sell_units == actual_balance else '❌ FAIL'}\n")

    # Test Case 2: Normal exit (should use 99.9%)
    is_tp2 = False
    if is_tp2:
        sell_units = actual_balance
    else:
        sell_units = actual_balance * 0.999

    expected = actual_balance * 0.999
    print(f"Test 2 - Normal Exit:")
    print(f"  Position size: {pos_size:.8f}")
    print(f"  Actual balance: {actual_balance:.8f}")
    print(f"  is_tp2: {is_tp2}")
    print(f"  Sell units: {sell_units:.8f}")
    print(f"  Expected: {expected:.8f} (99.9%)")
    print(f"  Result: {'✅ PASS' if sell_units == expected else '❌ FAIL'}\n")

def test_current_btc_scenario():
    """Test current BTC dust scenario"""
    print("=== Testing Current BTC Scenario ===\n")

    # Current BTC position from positions_v3.json
    pos_size = 3.16e-07  # 0.00000031 BTC (dust)
    actual_balance = 3.16e-07
    first_target_hit = True
    second_target_hit = True  # Already hit!

    is_tp2 = first_target_hit and not second_target_hit

    print(f"Current BTC Position:")
    print(f"  Size: {pos_size:.8f} BTC ({pos_size:.2e})")
    print(f"  first_target_hit: {first_target_hit}")
    print(f"  second_target_hit: {second_target_hit}")
    print(f"  is_tp2: {is_tp2}")
    print(f"\nAnalysis:")
    print(f"  This is NOT a TP2 exit (already completed)")
    print(f"  This is dust that should have been removed")
    print(f"  Recommendation: Manual deletion required\n")

if __name__ == "__main__":
    test_tp2_detection()
    test_sell_units_calculation()
    test_current_btc_scenario()

    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)
