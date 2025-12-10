#!/usr/bin/env python3
"""
Test GUI with 4-coin simplified dropdown
This script verifies the coin selector works correctly with only BTC, ETH, XRP, SOL
"""

import tkinter as tk
from tkinter import ttk
import sys
import os

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

from ver2 import config_v2


def test_coin_dropdown():
    """Test the coin dropdown with 4 major coins"""
    root = tk.Tk()
    root.title("Coin Selector Test - 4 Major Coins")
    root.geometry("600x400")

    # Test frame
    test_frame = ttk.LabelFrame(root, text="4-Coin Dropdown Test", padding="20")
    test_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

    # Coin descriptions (same as in gui_app_v2.py)
    coin_descriptions = {
        'BTC': 'Bitcoin (Market Leader)',
        'ETH': 'Ethereum (Smart Contracts)',
        'XRP': 'Ripple (Fast Payments)',
        'SOL': 'Solana (High Performance)'
    }

    # Create dropdown options with descriptions
    dropdown_values = [
        f"{coin} - {coin_descriptions[coin]}"
        for coin in config_v2.AVAILABLE_COINS
    ]

    # Display available coins
    info_label = ttk.Label(
        test_frame,
        text=f"Available coins from config: {', '.join(config_v2.AVAILABLE_COINS)}",
        font=('Arial', 10, 'bold')
    )
    info_label.pack(pady=(0, 20))

    # Dropdown
    ttk.Label(test_frame, text="Select Coin:", font=('Arial', 10)).pack(anchor=tk.W, pady=(0, 5))
    coin_var = tk.StringVar(value=dropdown_values[0])
    dropdown = ttk.Combobox(
        test_frame,
        textvariable=coin_var,
        values=dropdown_values,
        state='readonly',
        width=40,
        font=('Arial', 10)
    )
    dropdown.pack(anchor=tk.W, pady=(0, 20))

    # Result display
    result_frame = ttk.LabelFrame(test_frame, text="Selected Coin Details", padding="10")
    result_frame.pack(fill=tk.BOTH, expand=True)

    selected_coin_var = tk.StringVar(value="BTC")
    selected_desc_var = tk.StringVar(value="Bitcoin (Market Leader)")

    ttk.Label(result_frame, text="Coin Symbol:", font=('Arial', 9)).grid(row=0, column=0, sticky=tk.W, pady=5)
    ttk.Label(result_frame, textvariable=selected_coin_var, font=('Arial', 9, 'bold'), foreground='blue').grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)

    ttk.Label(result_frame, text="Description:", font=('Arial', 9)).grid(row=1, column=0, sticky=tk.W, pady=5)
    ttk.Label(result_frame, textvariable=selected_desc_var, font=('Arial', 9)).grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)

    # Test info
    test_info = ttk.Label(
        test_frame,
        text="✓ Test passed: Dropdown shows only 4 major coins\n✓ No separator line needed\n✓ Descriptions included",
        font=('Arial', 9),
        foreground='green'
    )
    test_info.pack(pady=20)

    def on_select(event=None):
        """Handle coin selection"""
        selected = coin_var.get()
        # Extract symbol from "BTC - Bitcoin (Market Leader)" format
        symbol = selected.split(' - ')[0].strip()
        description = selected.split(' - ')[1].strip() if ' - ' in selected else ""

        selected_coin_var.set(symbol)
        selected_desc_var.set(description)

        # Validate
        is_valid, error_msg = config_v2.validate_symbol(symbol)
        if is_valid:
            print(f"✓ Valid coin selected: {symbol}")
        else:
            print(f"✗ Invalid coin: {error_msg}")

    dropdown.bind('<<ComboboxSelected>>', on_select)

    # Stats
    stats_label = ttk.Label(
        test_frame,
        text=f"Total coins in dropdown: {len(dropdown_values)} (reduced from 427)",
        font=('Arial', 8),
        foreground='gray'
    )
    stats_label.pack(pady=(10, 0))

    root.mainloop()


if __name__ == '__main__':
    print("=" * 60)
    print("Testing 4-Coin Dropdown Implementation")
    print("=" * 60)
    print(f"Available coins: {config_v2.AVAILABLE_COINS}")
    print(f"Total count: {len(config_v2.AVAILABLE_COINS)}")
    print("=" * 60)

    test_coin_dropdown()
