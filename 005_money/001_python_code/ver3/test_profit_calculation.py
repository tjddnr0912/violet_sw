#!/usr/bin/env python3
"""
Test script to verify profit percentage calculation in Account Info Widget.

This script tests:
1. P&L calculation with different price scenarios
2. Widget display formatting
3. Color coding (green for profit, red for loss)
"""

import sys
import os
import tkinter as tk
from tkinter import ttk

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(script_dir))

from ver3.widgets.account_info_widget import AccountInfoWidget


def test_pnl_calculation():
    """Test P&L calculation logic"""
    print("\n" + "="*50)
    print("Testing P&L Calculation Logic")
    print("="*50)

    # Create dummy widget to access calculate_pnl method
    root = tk.Tk()
    root.withdraw()  # Hide main window
    widget = AccountInfoWidget(root)

    test_cases = [
        # (avg_price, current_price, expected_pnl_pct)
        (100000, 120000, 20.0),   # +20% profit
        (100000, 80000, -20.0),   # -20% loss
        (50000, 50000, 0.0),      # 0% (no change)
        (100000, 150000, 50.0),   # +50% profit
        (200000, 190000, -5.0),   # -5% loss
        (1000000, 1015000, 1.5),  # +1.5% profit
        (0, 100000, 0.0),         # Edge case: avg_price = 0
    ]

    all_passed = True

    for avg_price, current_price, expected_pnl in test_cases:
        calculated_pnl = widget.calculate_pnl(avg_price, current_price)

        passed = abs(calculated_pnl - expected_pnl) < 0.01  # Allow small floating point error
        status = "✓ PASS" if passed else "✗ FAIL"

        print(f"\n{status}")
        print(f"  Avg Price: {avg_price:,.0f} KRW")
        print(f"  Current Price: {current_price:,.0f} KRW")
        print(f"  Expected P&L: {expected_pnl:+.2f}%")
        print(f"  Calculated P&L: {calculated_pnl:+.2f}%")

        if not passed:
            all_passed = False

    root.destroy()

    print("\n" + "="*50)
    if all_passed:
        print("✓ All P&L calculation tests PASSED")
    else:
        print("✗ Some tests FAILED")
    print("="*50 + "\n")

    return all_passed


def test_widget_display():
    """Test visual display of profit/loss"""
    print("\n" + "="*50)
    print("Testing Widget Display")
    print("="*50)
    print("\nOpening test window...")
    print("You should see 3 holdings with different P&L percentages:")
    print("  - BTC: +15.5% (green)")
    print("  - ETH: -8.2% (red)")
    print("  - SOL: +0.0% (black/gray)")
    print("\nClose the window to continue...")

    root = tk.Tk()
    root.title("Account Info Widget - P&L Test")
    root.geometry("400x500")

    # Create widget
    widget = AccountInfoWidget(root)
    widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Update balance
    widget.update_balance(1000000)

    # Test case 1: BTC with profit
    widget.update_holding(
        coin='BTC',
        avg_price=100000000,
        quantity=0.001,
        current_price=115500000  # +15.5% profit
    )

    # Test case 2: ETH with loss
    widget.update_holding(
        coin='ETH',
        avg_price=5000000,
        quantity=0.2,
        current_price=4590000  # -8.2% loss
    )

    # Test case 3: SOL with no change
    widget.update_holding(
        coin='SOL',
        avg_price=250000,
        quantity=4.0,
        current_price=250000  # 0% change
    )

    root.mainloop()

    print("\n" + "="*50)
    print("Widget display test completed")
    print("="*50 + "\n")


def main():
    """Run all tests"""
    print("\n" + "#"*50)
    print("# Account Info Widget - Profit Calculation Test")
    print("#"*50)

    # Test 1: Calculation logic
    calculation_passed = test_pnl_calculation()

    # Test 2: Visual display
    print("\nProceed to visual display test? (y/n): ", end='')
    if input().lower() == 'y':
        test_widget_display()

    print("\n" + "#"*50)
    print("# Test Summary")
    print("#"*50)
    print(f"\nCalculation Logic: {'✓ PASSED' if calculation_passed else '✗ FAILED'}")
    print("\nAll tests completed!\n")


if __name__ == "__main__":
    main()
