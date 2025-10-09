#!/usr/bin/env python3
"""
Test script to verify Account Info Widget P&L calculation fix.

This script tests that the profit percentage is calculated correctly
when avg_price and current_price are different.
"""

import sys
import os
import tkinter as tk

# Add paths
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(script_dir))

from ver3.widgets.account_info_widget import AccountInfoWidget


def test_pnl_calculation():
    """Test P&L percentage calculation"""
    print("=" * 60)
    print("Testing Account Info Widget P&L Calculation")
    print("=" * 60)

    root = tk.Tk()
    root.title("Test Account Info Widget")
    root.geometry("500x400")

    # Create widget
    widget = AccountInfoWidget(root)
    widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Update balance
    widget.update_balance(500000)  # 500K KRW balance

    # Test Case 1: Profit scenario
    print("\n[TEST 1] Profit Scenario")
    print("BTC bought at 80,000,000 KRW, now at 90,000,000 KRW")
    print("Expected P&L: +12.5%")
    holdings_data = {
        'BTC': {
            'avg_price': 80000000,
            'quantity': 0.01,
            'current_price': 90000000
        }
    }
    widget.update_holdings_batch(holdings_data)

    # Wait 3 seconds
    root.after(3000, lambda: test_case_2(widget, root))

    root.mainloop()


def test_case_2(widget, root):
    """Test Case 2: Loss scenario"""
    print("\n[TEST 2] Loss Scenario")
    print("ETH bought at 3,500,000 KRW, now at 3,000,000 KRW")
    print("Expected P&L: -14.29%")
    holdings_data = {
        'ETH': {
            'avg_price': 3500000,
            'quantity': 0.5,
            'current_price': 3000000
        }
    }
    widget.update_holdings_batch(holdings_data)

    # Wait 3 seconds
    root.after(3000, lambda: test_case_3(widget, root))


def test_case_3(widget, root):
    """Test Case 3: Multiple coins with mixed P&L"""
    print("\n[TEST 3] Multiple Coins - Mixed P&L")
    print("BTC: +5%, ETH: -8%, XRP: +15%")
    holdings_data = {
        'BTC': {
            'avg_price': 85000000,
            'quantity': 0.01,
            'current_price': 89250000  # +5%
        },
        'ETH': {
            'avg_price': 3500000,
            'quantity': 0.5,
            'current_price': 3220000  # -8%
        },
        'XRP': {
            'avg_price': 2000,
            'quantity': 100,
            'current_price': 2300  # +15%
        }
    }
    widget.update_holdings_batch(holdings_data)

    # Wait 3 seconds then close
    root.after(3000, lambda: finish_test(root))


def finish_test(root):
    """Finish test"""
    print("\n" + "=" * 60)
    print("Test completed!")
    print("Check the GUI to verify percentages are displayed correctly.")
    print("The console should show DEBUG output with calculated P&L values.")
    print("=" * 60)
    print("\nClosing in 2 seconds...")
    root.after(2000, root.quit)


if __name__ == "__main__":
    test_pnl_calculation()
