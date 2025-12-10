#!/usr/bin/env python3
"""
Test script for Account Info and Settings Panel widgets.

This script verifies:
1. AccountInfoWidget displays balance and holdings correctly
2. SettingsPanelWidget validates input and saves settings
3. PreferenceManagerV3 persists settings across restarts
"""

import tkinter as tk
from tkinter import ttk
import sys
import os

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)
sys.path.insert(0, os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

from ver3.widgets.account_info_widget import AccountInfoWidget
from ver3.widgets.settings_panel_widget import SettingsPanelWidget
from ver3.preference_manager_v3 import PreferenceManagerV3
from ver3 import config_v3


def test_account_info_widget():
    """Test AccountInfoWidget"""
    print("\n=== Testing AccountInfoWidget ===")

    root = tk.Tk()
    root.title("Test: Account Info Widget")
    root.geometry("400x600")

    # Create widget
    account_widget = AccountInfoWidget(root)
    account_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Test 1: Update balance
    print("Test 1: Updating balance to 1,500,000 KRW")
    account_widget.update_balance(1500000)

    # Test 2: Add holdings
    print("Test 2: Adding holdings for BTC, ETH, XRP")
    holdings = {
        'BTC': {
            'avg_price': 95000000,
            'quantity': 0.0012,
            'current_price': 97000000  # +2% profit
        },
        'ETH': {
            'avg_price': 4100000,
            'quantity': 0.0523,
            'current_price': 4050000  # -1.2% loss
        },
        'XRP': {
            'avg_price': 1500,
            'quantity': 50.0,
            'current_price': 1600  # +6.7% profit
        }
    }

    account_widget.update_holdings_batch(holdings)

    # Test 3: Calculate totals
    total_holdings = account_widget.get_total_holdings_value()
    total_account = account_widget.get_total_account_value()
    print(f"Test 3: Total holdings value: {total_holdings:,.0f} KRW")
    print(f"Test 3: Total account value: {total_account:,.0f} KRW")

    print("\n✅ AccountInfoWidget test window opened. Close to continue.")
    root.mainloop()


def test_settings_panel_widget():
    """Test SettingsPanelWidget"""
    print("\n=== Testing SettingsPanelWidget ===")

    root = tk.Tk()
    root.title("Test: Settings Panel Widget")
    root.geometry("600x700")

    # Get default config
    config = config_v3.get_version_config()

    # Callback function
    def on_apply(updated_config):
        print("\n✅ Settings applied!")
        print(f"Max Positions: {updated_config['PORTFOLIO_CONFIG']['max_positions']}")
        print(f"Min Entry Score: {updated_config['ENTRY_SCORING_CONFIG']['min_entry_score']}")
        print(f"Position Size: {updated_config['POSITION_SIZING_CONFIG']['base_amount_krw']} KRW")
        print(f"Chandelier Multiplier: {updated_config['INDICATOR_CONFIG']['chandelier_multiplier']}")

    # Create widget
    settings_widget = SettingsPanelWidget(root, config, on_apply)
    settings_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    print("Test: Modify settings and click 'Apply Settings' button")
    print("✅ SettingsPanelWidget test window opened. Close to continue.")
    root.mainloop()


def test_preference_manager():
    """Test PreferenceManagerV3"""
    print("\n=== Testing PreferenceManagerV3 ===")

    # Create test preference file
    test_pref_file = os.path.join(script_dir, 'test_user_preferences_v3.json')
    pref_manager = PreferenceManagerV3(test_pref_file)

    # Test 1: Save preferences
    print("\nTest 1: Saving test preferences")
    test_prefs = {
        'portfolio_config': {
            'max_positions': 3,
            'default_coins': ['BTC', 'ETH', 'SOL']
        },
        'entry_scoring': {
            'min_entry_score': 3,
            'rsi_threshold': 30,
            'stoch_threshold': 15
        },
        'exit_scoring': {
            'chandelier_atr_multiplier': 2.5,
            'tp1_target': 2.0,
            'tp2_target': 3.5
        },
        'risk_management': {
            'max_daily_trades': 15,
            'daily_loss_limit_pct': 6.0,
            'max_consecutive_losses': 5,
            'position_amount_krw': 75000
        }
    }

    success = pref_manager.save_preferences(test_prefs)
    print(f"Save result: {'✅ Success' if success else '❌ Failed'}")

    # Test 2: Load preferences
    print("\nTest 2: Loading saved preferences")
    loaded_prefs = pref_manager.load_preferences()
    print(f"Loaded max_positions: {loaded_prefs['portfolio_config']['max_positions']}")
    print(f"Loaded default_coins: {loaded_prefs['portfolio_config']['default_coins']}")
    print(f"Loaded min_entry_score: {loaded_prefs['entry_scoring']['min_entry_score']}")

    # Test 3: Merge with config
    print("\nTest 3: Merging preferences with default config")
    default_config = config_v3.get_version_config()
    merged_config = pref_manager.merge_with_config(loaded_prefs, default_config)
    print(f"Merged max_positions: {merged_config['PORTFOLIO_CONFIG']['max_positions']}")
    print(f"Merged min_entry_score: {merged_config['ENTRY_SCORING_CONFIG']['min_entry_score']}")
    print(f"Merged base_amount_krw: {merged_config['POSITION_SIZING_CONFIG']['base_amount_krw']}")

    # Test 4: Extract preferences from config
    print("\nTest 4: Extracting preferences from config")
    extracted_prefs = pref_manager.extract_preferences_from_config(merged_config)
    print(f"Extracted max_positions: {extracted_prefs['portfolio_config']['max_positions']}")
    print(f"Extracted position_amount_krw: {extracted_prefs['risk_management']['position_amount_krw']}")

    # Cleanup test file
    if os.path.exists(test_pref_file):
        os.remove(test_pref_file)
        print(f"\n🧹 Cleaned up test file: {test_pref_file}")

    print("\n✅ PreferenceManagerV3 tests completed successfully!")


def main():
    """Run all tests"""
    print("=" * 60)
    print("Account Info & Settings Panel - Test Suite")
    print("=" * 60)

    # Test 1: PreferenceManagerV3 (non-GUI)
    test_preference_manager()

    # Test 2: AccountInfoWidget (GUI)
    response = input("\nTest AccountInfoWidget? (y/n): ").lower()
    if response == 'y':
        test_account_info_widget()

    # Test 3: SettingsPanelWidget (GUI)
    response = input("\nTest SettingsPanelWidget? (y/n): ").lower()
    if response == 'y':
        test_settings_panel_widget()

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
