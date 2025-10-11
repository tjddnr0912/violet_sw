#!/usr/bin/env python3
"""
Test that Ver3 strategy now correctly calculates percentage-based profit targets.
"""

import sys
from pathlib import Path

# Add paths
base_path = Path(__file__).parent
sys.path.insert(0, str(base_path / '001_python_code'))

from ver3.config_v3 import get_version_config
from ver3.strategy_v3 import StrategyV2 as StrategyV3
import pandas as pd

def test_percentage_targets():
    """Test percentage-based profit target calculation."""

    print("=" * 80)
    print("Ver3 Profit Target Fix Verification")
    print("=" * 80)

    # Load config
    config = get_version_config()
    strategy = StrategyV3(config, None)

    # Verify config mode
    mode = config['EXIT_CONFIG']['profit_target_mode']
    tp1_pct = config['EXIT_CONFIG']['tp1_percentage']
    tp2_pct = config['EXIT_CONFIG']['tp2_percentage']

    print(f"\n📋 Current Config:")
    print(f"  Profit Target Mode: {mode}")
    print(f"  TP1 Percentage: {tp1_pct}%")
    print(f"  TP2 Percentage: {tp2_pct}%")

    # Simulate XRP position
    xrp_entry = 3707.0
    xrp_current = 3792.0  # +2.3% from entry

    print(f"\n📊 XRP Position Simulation:")
    print(f"  Entry Price: {xrp_entry:,.0f} KRW")
    print(f"  Current Price: {xrp_current:,.0f} KRW")
    print(f"  Current P&L: {((xrp_current - xrp_entry) / xrp_entry) * 100:.2f}%")

    # Create dummy DataFrame with required columns
    df = pd.DataFrame({
        'close': [xrp_current],
        'high': [xrp_current],
        'low': [xrp_current],
        'bb_upper': [4000.0],
        'bb_middle': [3850.0],
        'bb_lower': [3700.0],
        'atr': [100.0],
    })

    # Calculate target prices using the fixed method
    targets = strategy._calculate_target_prices(df, entry_price=xrp_entry)

    print(f"\n🎯 Calculated Profit Targets:")
    print(f"  Mode: {targets.get('mode', 'unknown')}")
    print(f"  TP1 (First Target): {targets.get('first_target', 0):,.0f} KRW")
    print(f"  TP2 (Second Target): {targets.get('second_target', 0):,.0f} KRW")
    print(f"  Stop-Loss: {targets.get('stop_loss', 0):,.0f} KRW")

    # Expected values
    expected_tp1 = xrp_entry * (1 + tp1_pct / 100.0)
    expected_tp2 = xrp_entry * (1 + tp2_pct / 100.0)

    print(f"\n✅ Expected Values:")
    print(f"  Expected TP1 (1.5%): {expected_tp1:,.0f} KRW")
    print(f"  Expected TP2 (2.5%): {expected_tp2:,.0f} KRW")

    # Verification
    tp1_correct = abs(targets.get('first_target', 0) - expected_tp1) < 1.0
    tp2_correct = abs(targets.get('second_target', 0) - expected_tp2) < 1.0
    mode_correct = targets.get('mode') == 'percentage_based'

    print(f"\n🔍 Verification:")
    print(f"  TP1 Calculation: {'✅ PASS' if tp1_correct else '❌ FAIL'}")
    print(f"  TP2 Calculation: {'✅ PASS' if tp2_correct else '❌ FAIL'}")
    print(f"  Mode Detection: {'✅ PASS' if mode_correct else '❌ FAIL'}")

    # Check if TP1 should trigger
    tp1_should_trigger = xrp_current >= expected_tp1
    print(f"\n💡 Trade Logic Check:")
    print(f"  Current Price ({xrp_current:,.0f}) >= TP1 ({expected_tp1:,.0f}): {tp1_should_trigger}")

    if tp1_should_trigger:
        print(f"  🚨 TP1 SHOULD TRIGGER! 50% should be sold at {xrp_current:,.0f} KRW")
    else:
        distance = expected_tp1 - xrp_current
        print(f"  ⏳ TP1 not yet reached. Need {distance:,.0f} KRW more.")

    print("\n" + "=" * 80)

    if tp1_correct and tp2_correct and mode_correct:
        print("✅ ALL TESTS PASSED - Fix is working correctly!")
        return True
    else:
        print("❌ TESTS FAILED - Fix needs review")
        return False

if __name__ == '__main__':
    success = test_percentage_targets()
    sys.exit(0 if success else 1)
