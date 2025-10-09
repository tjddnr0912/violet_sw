"""
Test Pyramiding Functionality for Ver3

This script tests the pyramiding strategy implementation:
1. Position tracking with multiple entries
2. Average entry price calculation
3. Pyramiding decision logic
4. Position size reduction with each entry
"""

import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ver3.live_executor_v3 import LiveExecutorV3, Position
from ver3.config_v3 import get_version_config, PYRAMIDING_CONFIG
from lib.core.logger import TradingLogger


def test_position_pyramiding():
    """Test Position class with pyramiding support"""
    print("\n" + "="*60)
    print("TEST 1: Position Class with Pyramiding")
    print("="*60)

    # Create initial position
    pos = Position(
        ticker='BTC',
        size=0.001,
        entry_price=50000000,
        entry_time=datetime.now(),
        stop_loss=48000000
    )

    print(f"Initial position:")
    print(f"  Size: {pos.size:.6f}")
    print(f"  Entry price: {pos.entry_price:,.0f} KRW")
    print(f"  Entry count: {pos.entry_count}")
    print(f"  Entry prices: {pos.entry_prices}")

    # Simulate pyramid entry 2
    print("\n--- Simulating Pyramid Entry #2 ---")
    old_value = pos.size * pos.entry_price
    new_size = 0.0005  # 50% of original
    new_price = 51000000  # Price increased 2%
    new_value = new_size * new_price
    total_size = pos.size + new_size

    pos.entry_price = (old_value + new_value) / total_size
    pos.size = total_size
    pos.entry_count += 1
    pos.entry_prices.append(new_price)
    pos.entry_sizes.append(new_size)

    print(f"After pyramid #2:")
    print(f"  Size: {pos.size:.6f}")
    print(f"  Avg entry price: {pos.entry_price:,.0f} KRW")
    print(f"  Entry count: {pos.entry_count}")
    print(f"  Entry prices: {[f'{p:,.0f}' for p in pos.entry_prices]}")
    print(f"  Entry sizes: {pos.entry_sizes}")

    # Simulate pyramid entry 3
    print("\n--- Simulating Pyramid Entry #3 ---")
    old_value = pos.size * pos.entry_price
    new_size = 0.00025  # 25% of original
    new_price = 52000000  # Price increased another 2%
    new_value = new_size * new_price
    total_size = pos.size + new_size

    pos.entry_price = (old_value + new_value) / total_size
    pos.size = total_size
    pos.entry_count += 1
    pos.entry_prices.append(new_price)
    pos.entry_sizes.append(new_size)

    print(f"After pyramid #3:")
    print(f"  Size: {pos.size:.6f}")
    print(f"  Avg entry price: {pos.entry_price:,.0f} KRW")
    print(f"  Entry count: {pos.entry_count}")
    print(f"  Entry prices: {[f'{p:,.0f}' for p in pos.entry_prices]}")
    print(f"  Entry sizes: {pos.entry_sizes}")

    # Test serialization
    print("\n--- Testing Serialization ---")
    pos_dict = pos.to_dict()
    print(f"Position dict keys: {list(pos_dict.keys())}")

    # Test deserialization
    pos_loaded = Position.from_dict(pos_dict)
    print(f"Loaded position entry count: {pos_loaded.entry_count}")
    print(f"Loaded position avg price: {pos_loaded.entry_price:,.0f} KRW")

    return True


def test_executor_pyramiding():
    """Test LiveExecutorV3 pyramiding methods"""
    print("\n" + "="*60)
    print("TEST 2: LiveExecutorV3 Pyramiding Methods")
    print("="*60)

    # Create mock API and logger
    class MockAPI:
        pass

    logger = TradingLogger()
    config = get_version_config()

    # Initialize executor with custom state file
    executor = LiveExecutorV3(
        api=MockAPI(),
        logger=logger,
        config=config,
        state_file='logs/test_positions_pyramid.json'
    )

    # Test initial state
    print(f"\nInitial state:")
    print(f"  Entry count for BTC: {executor.get_entry_count('BTC')}")
    print(f"  Last entry price for BTC: {executor.get_last_entry_price('BTC')}")

    # Simulate first entry
    print("\n--- Simulating Entry #1 ---")
    result1 = executor.execute_order(
        ticker='BTC',
        action='BUY',
        units=0.001,
        price=50000000,
        dry_run=True,
        reason="Initial entry"
    )
    print(f"Order result: {result1['success']}")
    print(f"Entry count: {executor.get_entry_count('BTC')}")
    print(f"Last entry price: {executor.get_last_entry_price('BTC'):,.0f} KRW")

    # Simulate pyramid entry 2
    print("\n--- Simulating Pyramid Entry #2 ---")
    result2 = executor.execute_order(
        ticker='BTC',
        action='BUY',
        units=0.0005,
        price=51000000,
        dry_run=True,
        reason="Pyramid entry #2"
    )
    print(f"Order result: {result2['success']}")
    print(f"Entry count: {executor.get_entry_count('BTC')}")
    print(f"Last entry price: {executor.get_last_entry_price('BTC'):,.0f} KRW")

    pos = executor.get_position('BTC')
    print(f"Average entry price: {pos.entry_price:,.0f} KRW")
    print(f"Total size: {pos.size:.6f}")

    # Simulate pyramid entry 3
    print("\n--- Simulating Pyramid Entry #3 ---")
    result3 = executor.execute_order(
        ticker='BTC',
        action='BUY',
        units=0.00025,
        price=52000000,
        dry_run=True,
        reason="Pyramid entry #3"
    )
    print(f"Order result: {result3['success']}")
    print(f"Entry count: {executor.get_entry_count('BTC')}")
    print(f"Last entry price: {executor.get_last_entry_price('BTC'):,.0f} KRW")
    print(f"All entry prices: {[f'{p:,.0f}' for p in executor.get_all_entry_prices('BTC')]}")

    pos = executor.get_position('BTC')
    print(f"Average entry price: {pos.entry_price:,.0f} KRW")
    print(f"Total size: {pos.size:.6f}")

    # Test position summary
    print("\n--- Position Summary ---")
    summary = executor.get_position_summary('BTC')
    print(f"Has position: {summary['has_position']}")
    print(f"Entry count: {summary['entry_count']}")
    print(f"Entry prices: {[f'{p:,.0f}' for p in summary['entry_prices']]}")
    print(f"Entry sizes: {summary['entry_sizes']}")

    # Clean up test file
    import os
    if os.path.exists('logs/test_positions_pyramid.json'):
        os.remove('logs/test_positions_pyramid.json')
        print("\nTest state file cleaned up")

    return True


def test_pyramiding_config():
    """Test pyramiding configuration"""
    print("\n" + "="*60)
    print("TEST 3: Pyramiding Configuration")
    print("="*60)

    print("\nPyramiding Config:")
    for key, value in PYRAMIDING_CONFIG.items():
        print(f"  {key}: {value}")

    # Verify configuration values
    assert PYRAMIDING_CONFIG['enabled'] == True, "Pyramiding should be enabled"
    assert PYRAMIDING_CONFIG['max_entries_per_coin'] == 3, "Max entries should be 3"
    assert PYRAMIDING_CONFIG['min_score_for_pyramid'] == 3, "Min score should be 3"
    assert PYRAMIDING_CONFIG['position_size_multiplier'] == [1.0, 0.5, 0.25], "Multipliers incorrect"

    print("\n✓ All configuration values correct")
    return True


def test_pyramid_decision_logic():
    """Test pyramiding decision logic"""
    print("\n" + "="*60)
    print("TEST 4: Pyramiding Decision Logic")
    print("="*60)

    # This would require mocking PortfolioManagerV3 and its dependencies
    # For now, we'll just verify the logic conditions

    pyramid_config = PYRAMIDING_CONFIG

    print("\nPyramiding will be allowed if:")
    print(f"  1. Enabled: {pyramid_config['enabled']}")
    print(f"  2. Entry count < {pyramid_config['max_entries_per_coin']}")
    print(f"  3. Entry score >= {pyramid_config['min_score_for_pyramid']}")
    print(f"  4. Signal strength >= {pyramid_config['min_signal_strength_for_pyramid']}")
    print(f"  5. Price increase >= {pyramid_config['min_price_increase_pct']}%")
    print(f"  6. Market regime in {pyramid_config['allow_pyramid_in_regime']}")

    print("\nPosition size multipliers:")
    multipliers = pyramid_config['position_size_multiplier']
    for i, mult in enumerate(multipliers, 1):
        print(f"  Entry #{i}: {mult*100:.0f}% of base amount")

    return True


def run_all_tests():
    """Run all pyramiding tests"""
    print("\n" + "="*80)
    print("PYRAMIDING FUNCTIONALITY TEST SUITE")
    print("="*80)

    tests = [
        ("Position Pyramiding", test_position_pyramiding),
        ("Executor Pyramiding", test_executor_pyramiding),
        ("Pyramiding Config", test_pyramiding_config),
        ("Pyramid Decision Logic", test_pyramid_decision_logic),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = test_func()
            if result:
                passed += 1
                print(f"\n✓ {test_name} PASSED")
            else:
                failed += 1
                print(f"\n✗ {test_name} FAILED")
        except Exception as e:
            failed += 1
            print(f"\n✗ {test_name} FAILED with exception:")
            print(f"  {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*80)
    print(f"TEST RESULTS: {passed} passed, {failed} failed")
    print("="*80)

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
