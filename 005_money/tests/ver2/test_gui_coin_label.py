#!/usr/bin/env python3
"""
GUI Test for Dynamic Coin Label Feature

This script tests:
1. Initial label shows correct coin from saved preference
2. Label updates when coin changes
3. Preference persists after "changing" coin
"""

import tkinter as tk
from tkinter import ttk
import json
import os
import sys

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(script_dir))

from ver2 import config_v2


class CoinLabelTester:
    def __init__(self, root):
        self.root = root
        self.root.title("Coin Label Dynamic Update Test")
        self.root.geometry("600x400")

        self.preferences_file = os.path.join(script_dir, 'user_preferences_v2.json')

        # Load saved preference
        saved_coin = self._load_user_preferences()
        if saved_coin:
            config_v2.set_symbol_in_config(saved_coin)

        self.config = config_v2.get_version_config()
        self.create_widgets()

    def _load_user_preferences(self):
        """Load user preferences from JSON file"""
        try:
            if os.path.exists(self.preferences_file):
                with open(self.preferences_file, 'r', encoding='utf-8') as f:
                    preferences = json.load(f)
                    saved_coin = preferences.get('selected_coin', None)
                    if saved_coin:
                        is_valid, _ = config_v2.validate_symbol(saved_coin)
                        if is_valid:
                            return saved_coin
            return None
        except Exception as e:
            print(f"Warning: Could not load user preferences: {e}")
            return None

    def _save_user_preferences(self, selected_coin):
        """Save user preferences to JSON file"""
        try:
            from datetime import datetime
            preferences = {
                'selected_coin': selected_coin,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            with open(self.preferences_file, 'w', encoding='utf-8') as f:
                json.dump(preferences, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Could not save user preferences: {e}")

    def create_widgets(self):
        """Create test GUI widgets"""
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Title
        title = ttk.Label(main_frame, text="Dynamic Coin Label Test",
                         font=('Arial', 16, 'bold'))
        title.pack(pady=(0, 20))

        # Current coin from preferences
        current_coin = self.config['TRADING_CONFIG'].get('symbol', 'BTC')
        pref_label = ttk.Label(main_frame,
                              text=f"Loaded from preferences: {current_coin}",
                              font=('Arial', 12),
                              foreground='blue')
        pref_label.pack(pady=(0, 10))

        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)

        # Holdings label frame (simulating the actual GUI)
        holdings_frame = ttk.LabelFrame(main_frame, text="Trading Status (Like in Real GUI)", padding="10")
        holdings_frame.pack(fill=tk.X, pady=10)

        # Dynamic holdings label (THIS IS THE KEY FEATURE)
        self.coin_holdings_label_text = tk.StringVar(value=f"보유 {current_coin}:")
        holdings_label = ttk.Label(holdings_frame,
                                   textvariable=self.coin_holdings_label_text,
                                   font=('Arial', 12, 'bold'),
                                   foreground='green')
        holdings_label.grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)

        holdings_value = ttk.Label(holdings_frame, text="0.00000000",
                                   font=('Arial', 10))
        holdings_value.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        # Separator
        ttk.Separator(main_frame, orient='horizontal').pack(fill=tk.X, pady=10)

        # Coin selector
        selector_frame = ttk.LabelFrame(main_frame, text="Coin Selector", padding="10")
        selector_frame.pack(fill=tk.X, pady=10)

        ttk.Label(selector_frame, text="Select Coin:", font=('Arial', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)

        coin_descriptions = {
            'BTC': 'Bitcoin (Market Leader)',
            'ETH': 'Ethereum (Smart Contracts)',
            'XRP': 'Ripple (Fast Payments)',
            'SOL': 'Solana (High Performance)'
        }

        dropdown_values = [f"{symbol} - {desc}" for symbol, desc in coin_descriptions.items()]
        initial_value = f"{current_coin} - {coin_descriptions.get(current_coin, 'Unknown')}"

        self.coin_selector_var = tk.StringVar(value=initial_value)
        coin_selector = ttk.Combobox(selector_frame,
                                     textvariable=self.coin_selector_var,
                                     values=dropdown_values,
                                     state='readonly',
                                     width=35)
        coin_selector.grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)

        change_button = ttk.Button(selector_frame, text="변경 (Change)",
                                  command=self.change_coin)
        change_button.grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)

        # Status log
        log_frame = ttk.LabelFrame(main_frame, text="Status Log", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self.log_text = tk.Text(log_frame, height=8, width=60, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Initial log
        self.log(f"✅ GUI initialized with coin: {current_coin}")
        if os.path.exists(self.preferences_file):
            self.log(f"✅ Preferences loaded from: {self.preferences_file}")
        else:
            self.log(f"ℹ️  No saved preferences found, using default: {current_coin}")

    def log(self, message):
        """Add message to log"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def change_coin(self):
        """Handle coin change (simplified version of actual GUI method)"""
        selected = self.coin_selector_var.get()
        selected_coin = selected.split(' - ')[0].strip()

        current_coin = self.config['TRADING_CONFIG'].get('symbol', 'BTC')

        if selected_coin == current_coin:
            self.log(f"ℹ️  Already using {selected_coin}")
            return

        self.log(f"⏳ Changing coin: {current_coin} → {selected_coin}")

        try:
            # Update config
            config_v2.set_symbol_in_config(selected_coin)
            self.config = config_v2.get_version_config()
            self.log(f"✅ Config updated to {selected_coin}")

            # Save preference (KEY FEATURE)
            self._save_user_preferences(selected_coin)
            self.log(f"💾 Preference saved to {self.preferences_file}")

            # Update label (KEY FEATURE)
            self.coin_holdings_label_text.set(f"보유 {selected_coin}:")
            self.log(f"✅ Label updated: 보유 {selected_coin}:")

            # Update window title
            self.root.title(f"Coin Label Test - {selected_coin}")

            self.log(f"✅ Coin change complete: {selected_coin}")
            self.log("ℹ️  Close and reopen this window to test persistence")

        except Exception as e:
            self.log(f"❌ Error: {str(e)}")


def main():
    """Run the test GUI"""
    print("=" * 60)
    print("Starting GUI Coin Label Test")
    print("=" * 60)
    print("\nInstructions:")
    print("1. Notice the initial coin from saved preference")
    print("2. Select a different coin from dropdown")
    print("3. Click '변경' button")
    print("4. Watch the '보유 [COIN]:' label update")
    print("5. Close the window")
    print("6. Run this script again")
    print("7. Verify the last selected coin is remembered")
    print("=" * 60)
    print()

    root = tk.Tk()
    app = CoinLabelTester(root)
    root.mainloop()


if __name__ == '__main__':
    main()
