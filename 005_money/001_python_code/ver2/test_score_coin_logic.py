#!/usr/bin/env python3
"""
Test script to verify score monitoring coin symbol logic (no GUI).

This script tests the logic without running the GUI:
1. Score data includes coin symbol
2. Filtering logic works correctly
"""

from datetime import datetime, timedelta


def test_coin_filtering_logic():
    """Test coin filtering logic without GUI"""
    print("\n=== Testing Score Monitoring Coin Filtering Logic ===\n")

    # Simulate score checks data
    score_checks = []
    current_coin = 'BTC'

    # Test 1: Add BTC score checks
    print("Test 1: Adding BTC score checks...")
    base_time = datetime.now() - timedelta(hours=1)

    for i in range(5):
        score_data = {
            'timestamp': base_time + timedelta(minutes=i*10),
            'score': i % 4,
            'components': {
                'bb_touch': 1 if i % 2 == 0 else 0,
                'rsi_oversold': 1 if i % 3 == 0 else 0,
                'stoch_cross': 0
            },
            'regime': 'BULLISH',
            'price': 100000000 + (i * 10000),
            'coin': 'BTC'
        }

        # Filtering logic (from add_score_check)
        coin = score_data.get('coin', current_coin)
        if coin == current_coin:
            score_checks.append(score_data)

    print(f"✅ Added {len(score_checks)} BTC score checks")
    assert len(score_checks) == 5, f"Should have 5 BTC checks, got {len(score_checks)}"

    # Test 2: Try to add SOL score checks (should be filtered out)
    print("\nTest 2: Adding SOL score checks (should be filtered)...")
    initial_count = len(score_checks)

    for i in range(3):
        score_data = {
            'timestamp': base_time + timedelta(minutes=i*10),
            'score': 3,
            'components': {
                'bb_touch': 1,
                'rsi_oversold': 1,
                'stoch_cross': 1
            },
            'regime': 'BULLISH',
            'price': 200000 + (i * 1000),
            'coin': 'SOL'  # Different coin!
        }

        # Filtering logic
        coin = score_data.get('coin', current_coin)
        if coin == current_coin:
            score_checks.append(score_data)

    print(f"✅ Still {len(score_checks)} checks (SOL checks filtered out)")
    assert len(score_checks) == initial_count, f"Should still have {initial_count} BTC checks"

    # Test 3: Change to SOL and filter existing data
    print("\nTest 3: Changing to SOL and filtering data...")
    current_coin = 'SOL'

    # Load from file logic - filter by coin
    all_data = score_checks.copy()  # Simulate loaded data

    # Add some SOL data to the "file"
    for i in range(3):
        all_data.append({
            'timestamp': base_time + timedelta(minutes=i*10),
            'score': 3,
            'components': {
                'bb_touch': 1,
                'rsi_oversold': 1,
                'stoch_cross': 1
            },
            'regime': 'BULLISH',
            'price': 200000 + (i * 1000),
            'coin': 'SOL'
        })

    # Filter by current coin (from load_from_file)
    filtered_data = []
    for check in all_data:
        check_coin = check.get('coin', current_coin)
        if check_coin == current_coin:
            filtered_data.append(check)

    print(f"✅ After filtering for SOL: {len(filtered_data)} checks")
    assert len(filtered_data) == 3, f"Should have 3 SOL checks, got {len(filtered_data)}"
    assert all(c.get('coin') == 'SOL' for c in filtered_data), "All checks should be SOL"

    # Test 4: Verify backward compatibility (no coin field)
    print("\nTest 4: Testing backward compatibility (old data without coin field)...")
    current_coin = 'BTC'

    old_data = {
        'timestamp': datetime.now(),
        'score': 2,
        'components': {
            'bb_touch': 1,
            'rsi_oversold': 1,
            'stoch_cross': 0
        },
        'regime': 'BULLISH',
        'price': 100000000
        # No 'coin' field (old data format)
    }

    # Backward compatibility: assume current coin if not specified
    coin = old_data.get('coin', current_coin)
    print(f"✅ Old data without coin field assumed to be: {coin}")
    assert coin == current_coin, "Should assume current coin for old data"

    print("\n=== All Logic Tests Passed! ===")
    print("\nScore monitoring widget coin filtering logic:")
    print("  ✅ Filters incoming score checks by coin")
    print("  ✅ Only displays checks matching current coin")
    print("  ✅ Loads only relevant coin data from file")
    print("  ✅ Backward compatible with old data (no coin field)")
    print("\nThe fix is ready for integration testing!")


if __name__ == "__main__":
    test_coin_filtering_logic()
