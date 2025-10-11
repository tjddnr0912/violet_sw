"""
Test script for dual profit-taking system (BB-based vs Percentage-based).

This script verifies:
1. Configuration loads profit target mode correctly
2. Strategy calculates targets based on mode
3. Position stores mode when opened
4. Targets are calculated using position's locked mode
5. Settings persist to user_preferences_v3.json
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ver3 import config_v3
from ver2.strategy_v2 import StrategyV2
from ver3.preference_manager_v3 import PreferenceManagerV3
from lib.core.logger import TradingLogger
import pandas as pd
import numpy as np


def test_config_defaults():
    """Test that config has profit target mode settings."""
    print("\n=== Testing Config Defaults ===")

    config = config_v3.get_version_config()
    exit_config = config['EXIT_CONFIG']

    assert 'profit_target_mode' in exit_config, "profit_target_mode missing from EXIT_CONFIG"
    assert 'tp1_percentage' in exit_config, "tp1_percentage missing from EXIT_CONFIG"
    assert 'tp2_percentage' in exit_config, "tp2_percentage missing from EXIT_CONFIG"

    print(f"✓ Profit target mode: {exit_config['profit_target_mode']}")
    print(f"✓ TP1 percentage: {exit_config['tp1_percentage']}%")
    print(f"✓ TP2 percentage: {exit_config['tp2_percentage']}%")


def test_bb_mode_targets():
    """Test BB-based target calculation."""
    print("\n=== Testing BB-based Mode ===")

    config = config_v3.get_version_config()
    config['EXIT_CONFIG']['profit_target_mode'] = 'bb_based'

    logger = TradingLogger(log_dir='logs')
    strategy = StrategyV2(config, logger)

    # Create sample price data with BB bands
    df = pd.DataFrame({
        'close': [100000] * 50,
        'high': [101000] * 50,
        'low': [99000] * 50,
        'open': [100000] * 50,
        'volume': [1000] * 50,
    })

    # Calculate indicators
    df = strategy._calculate_execution_indicators(df)

    # Calculate targets
    targets = strategy._calculate_target_prices(df, entry_price=100000)

    print(f"✓ Mode: {targets.get('mode')}")
    print(f"✓ First target (BB middle): {targets.get('first_target', 0):,.0f} KRW")
    print(f"✓ Second target (BB upper): {targets.get('second_target', 0):,.0f} KRW")

    assert targets['mode'] == 'bb_based', "Mode should be bb_based"
    assert targets['first_target'] > 0, "First target should be calculated"
    assert targets['second_target'] > 0, "Second target should be calculated"


def test_percentage_mode_targets():
    """Test percentage-based target calculation."""
    print("\n=== Testing Percentage-based Mode ===")

    config = config_v3.get_version_config()
    config['EXIT_CONFIG']['profit_target_mode'] = 'percentage_based'
    config['EXIT_CONFIG']['tp1_percentage'] = 2.0  # 2%
    config['EXIT_CONFIG']['tp2_percentage'] = 4.0  # 4%

    logger = TradingLogger(log_dir='logs')
    strategy = StrategyV2(config, logger)

    # Create sample price data
    df = pd.DataFrame({
        'close': [100000] * 50,
        'high': [101000] * 50,
        'low': [99000] * 50,
        'open': [100000] * 50,
        'volume': [1000] * 50,
    })

    df = strategy._calculate_execution_indicators(df)

    # Calculate targets with entry price
    entry_price = 100000
    targets = strategy._calculate_target_prices(df, entry_price=entry_price)

    expected_tp1 = entry_price * 1.02  # 2%
    expected_tp2 = entry_price * 1.04  # 4%

    print(f"✓ Mode: {targets.get('mode')}")
    print(f"✓ Entry price: {entry_price:,.0f} KRW")
    print(f"✓ First target (TP1 2%): {targets.get('first_target', 0):,.0f} KRW (expected: {expected_tp1:,.0f})")
    print(f"✓ Second target (TP2 4%): {targets.get('second_target', 0):,.0f} KRW (expected: {expected_tp2:,.0f})")

    assert targets['mode'] == 'percentage_based', "Mode should be percentage_based"
    assert abs(targets['first_target'] - expected_tp1) < 1, "TP1 should be entry + 2%"
    assert abs(targets['second_target'] - expected_tp2) < 1, "TP2 should be entry + 4%"
    assert targets['tp1_pct'] == 2.0, "TP1 percentage should be stored"
    assert targets['tp2_pct'] == 4.0, "TP2 percentage should be stored"


def test_preference_persistence():
    """Test that preferences save and load correctly."""
    print("\n=== Testing Preference Persistence ===")

    pref_manager = PreferenceManagerV3()

    # Create test preferences with profit target mode
    test_prefs = {
        'portfolio_config': {
            'max_positions': 3,
            'default_coins': ['BTC', 'ETH', 'XRP']
        },
        'entry_scoring': {
            'min_entry_score': 3,
            'rsi_threshold': 30,
            'stoch_threshold': 20
        },
        'exit_scoring': {
            'chandelier_atr_multiplier': 3.5,
            'profit_target_mode': 'percentage_based',  # Test percentage mode
            'tp1_target': 1.8,
            'tp2_target': 3.2
        },
        'risk_management': {
            'max_daily_trades': 8,
            'daily_loss_limit_pct': 4.0,
            'max_consecutive_losses': 2,
            'position_amount_krw': 60000
        }
    }

    # Save preferences
    success = pref_manager.save_preferences(test_prefs)
    assert success, "Preferences should save successfully"
    print("✓ Preferences saved")

    # Load preferences
    loaded_prefs = pref_manager.load_preferences()

    # Verify profit target settings
    exit_scoring = loaded_prefs.get('exit_scoring', {})
    assert exit_scoring.get('profit_target_mode') == 'percentage_based', "Mode should persist"
    assert exit_scoring.get('tp1_target') == 1.8, "TP1 should persist"
    assert exit_scoring.get('tp2_target') == 3.2, "TP2 should persist"

    print(f"✓ Loaded profit target mode: {exit_scoring.get('profit_target_mode')}")
    print(f"✓ Loaded TP1: {exit_scoring.get('tp1_target')}%")
    print(f"✓ Loaded TP2: {exit_scoring.get('tp2_target')}%")

    # Merge with config
    config = config_v3.get_version_config()
    merged_config = pref_manager.merge_with_config(loaded_prefs, config)

    # Verify merged config
    merged_exit = merged_config['EXIT_CONFIG']
    assert merged_exit['profit_target_mode'] == 'percentage_based', "Merged mode should match"
    assert merged_exit['tp1_percentage'] == 1.8, "Merged TP1 should match"
    assert merged_exit['tp2_percentage'] == 3.2, "Merged TP2 should match"

    print("✓ Preferences merged with config correctly")


def test_position_mode_locking():
    """Test that position stores profit target mode when opened."""
    print("\n=== Testing Position Mode Locking ===")

    from ver3.live_executor_v3 import Position
    from datetime import datetime

    # Create position with percentage mode
    pos = Position(
        ticker='BTC',
        size=0.01,
        entry_price=100000000,
        entry_time=datetime.now(),
        stop_loss=95000000,
        highest_high=100000000,
        profit_target_mode='percentage_based',
        tp1_percentage=2.5,
        tp2_percentage=5.0
    )

    # Verify position stores mode
    assert pos.profit_target_mode == 'percentage_based', "Position should store mode"
    assert pos.tp1_percentage == 2.5, "Position should store TP1"
    assert pos.tp2_percentage == 5.0, "Position should store TP2"

    print(f"✓ Position created with mode: {pos.profit_target_mode}")
    print(f"✓ Position TP1: {pos.tp1_percentage}%")
    print(f"✓ Position TP2: {pos.tp2_percentage}%")

    # Test serialization
    pos_dict = pos.to_dict()
    assert 'profit_target_mode' in pos_dict, "Serialized position should include mode"
    assert 'tp1_percentage' in pos_dict, "Serialized position should include TP1"
    assert 'tp2_percentage' in pos_dict, "Serialized position should include TP2"

    print("✓ Position serializes mode correctly")

    # Test deserialization
    loaded_pos = Position.from_dict(pos_dict)
    assert loaded_pos.profit_target_mode == 'percentage_based', "Loaded position should have mode"
    assert loaded_pos.tp1_percentage == 2.5, "Loaded position should have TP1"
    assert loaded_pos.tp2_percentage == 5.0, "Loaded position should have TP2"

    print("✓ Position deserializes mode correctly")


def run_all_tests():
    """Run all tests."""
    print("\n" + "="*60)
    print("DUAL PROFIT-TAKING SYSTEM TEST SUITE")
    print("="*60)

    try:
        test_config_defaults()
        test_bb_mode_targets()
        test_percentage_mode_targets()
        test_preference_persistence()
        test_position_mode_locking()

        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED!")
        print("="*60)

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
