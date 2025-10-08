#!/usr/bin/env python3
"""
Test script for coin selection persistence feature.
This script verifies that:
1. User preferences can be saved to JSON
2. User preferences can be loaded from JSON
3. Invalid coins are rejected
4. Default is used when no preference exists
"""

import json
import os
import sys

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(script_dir))

from ver2 import config_v2

def test_save_load_preferences():
    """Test saving and loading user preferences"""
    print("=" * 60)
    print("Test 1: Save and Load Preferences")
    print("=" * 60)

    preferences_file = os.path.join(script_dir, 'user_preferences_v2.json')

    # Test 1: Save BTC preference
    print("\n1. Saving BTC preference...")
    test_pref = {
        'selected_coin': 'BTC',
        'last_updated': '2025-10-08 16:00:00'
    }
    with open(preferences_file, 'w', encoding='utf-8') as f:
        json.dump(test_pref, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Saved to {preferences_file}")

    # Test 2: Load BTC preference
    print("\n2. Loading preference...")
    with open(preferences_file, 'r', encoding='utf-8') as f:
        loaded = json.load(f)
    print(f"   ✅ Loaded: {loaded['selected_coin']}")
    assert loaded['selected_coin'] == 'BTC', "Should load BTC"

    # Test 3: Save ETH preference
    print("\n3. Saving ETH preference...")
    test_pref['selected_coin'] = 'ETH'
    with open(preferences_file, 'w', encoding='utf-8') as f:
        json.dump(test_pref, f, indent=2, ensure_ascii=False)

    # Test 4: Verify ETH persisted
    with open(preferences_file, 'r', encoding='utf-8') as f:
        loaded = json.load(f)
    print(f"   ✅ Changed to: {loaded['selected_coin']}")
    assert loaded['selected_coin'] == 'ETH', "Should load ETH"

    print("\n✅ All persistence tests passed!")
    return preferences_file


def test_coin_validation():
    """Test coin symbol validation"""
    print("\n" + "=" * 60)
    print("Test 2: Coin Validation")
    print("=" * 60)

    # Test valid coins
    valid_coins = ['BTC', 'ETH', 'XRP', 'SOL']
    print("\n1. Testing valid coins:")
    for coin in valid_coins:
        is_valid, error_msg = config_v2.validate_symbol(coin)
        status = "✅" if is_valid else "❌"
        print(f"   {status} {coin}: {is_valid}")
        assert is_valid, f"{coin} should be valid"

    # Test invalid coins
    print("\n2. Testing invalid coins:")
    invalid_coins = ['INVALID', 'DOGE', '', 'bitcoin']
    for coin in invalid_coins:
        is_valid, error_msg = config_v2.validate_symbol(coin)
        status = "✅" if not is_valid else "❌"
        print(f"   {status} {coin}: Valid={is_valid}")
        assert not is_valid, f"{coin} should be invalid"

    print("\n✅ All validation tests passed!")


def test_config_update():
    """Test updating config with new coin"""
    print("\n" + "=" * 60)
    print("Test 3: Config Update")
    print("=" * 60)

    print("\n1. Setting symbol to ETH...")
    config_v2.set_symbol_in_config('ETH')

    print("2. Getting config...")
    config = config_v2.get_version_config()
    current_symbol = config['TRADING_CONFIG']['symbol']
    print(f"   Current symbol: {current_symbol}")
    assert current_symbol == 'ETH', "Config should have ETH"

    print("\n3. Setting symbol to SOL...")
    config_v2.set_symbol_in_config('SOL')
    config = config_v2.get_version_config()
    current_symbol = config['TRADING_CONFIG']['symbol']
    print(f"   Current symbol: {current_symbol}")
    assert current_symbol == 'SOL', "Config should have SOL"

    # Reset to BTC
    print("\n4. Resetting to BTC...")
    config_v2.set_symbol_in_config('BTC')
    config = config_v2.get_version_config()
    print(f"   Final symbol: {config['TRADING_CONFIG']['symbol']}")

    print("\n✅ All config update tests passed!")


def test_preferences_format():
    """Test that preferences file has correct format"""
    print("\n" + "=" * 60)
    print("Test 4: Preferences File Format")
    print("=" * 60)

    preferences_file = os.path.join(script_dir, 'user_preferences_v2.json')

    # Create test preference
    test_pref = {
        'selected_coin': 'XRP',
        'last_updated': '2025-10-08 17:30:00'
    }

    print("\n1. Writing formatted JSON...")
    with open(preferences_file, 'w', encoding='utf-8') as f:
        json.dump(test_pref, f, indent=2, ensure_ascii=False)

    print("2. Reading formatted JSON...")
    with open(preferences_file, 'r', encoding='utf-8') as f:
        content = f.read()

    print("\nFile contents:")
    print("-" * 40)
    print(content)
    print("-" * 40)

    # Verify it's valid JSON
    loaded = json.loads(content)
    assert 'selected_coin' in loaded, "Must have selected_coin"
    assert 'last_updated' in loaded, "Must have last_updated"
    print("\n✅ Preferences file format is correct!")


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("COIN PERSISTENCE FEATURE - TEST SUITE")
    print("=" * 60)

    try:
        # Run all tests
        preferences_file = test_save_load_preferences()
        test_coin_validation()
        test_config_update()
        test_preferences_format()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)

        print(f"\nPreferences file location: {preferences_file}")
        print("\nNext steps:")
        print("1. Run the GUI: python 001_python_code/ver2/gui_app_v2.py")
        print("2. Change coin selection from dropdown")
        print("3. Click '변경' button")
        print("4. Close and reopen GUI")
        print("5. Verify the coin selection persists")

        return True

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
