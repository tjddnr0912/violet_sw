#!/usr/bin/env python3
"""
Test script to verify GUI launches and multi-chart tab is visible
This script will launch the GUI and perform basic checks
"""

import tkinter as tk
from tkinter import ttk
import sys
import os
import time

# Ensure working directory is project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
os.chdir(project_root)

# Add to path
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

def test_gui_import():
    """Test if GUI can be imported"""
    print("Test 1: Importing gui_app...")
    try:
        from gui_app import TradingBotGUI
        print("✓ gui_app imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import gui_app: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multi_chart_tab_import():
    """Test if MultiTimeframeChartTab can be imported"""
    print("\nTest 2: Importing MultiTimeframeChartTab...")
    try:
        from multi_chart_tab import MultiTimeframeChartTab
        print("✓ MultiTimeframeChartTab imported successfully")
        return True
    except Exception as e:
        print(f"✗ Failed to import MultiTimeframeChartTab: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_gui_creation():
    """Test if GUI window can be created"""
    print("\nTest 3: Creating GUI window...")
    try:
        root = tk.Tk()
        root.withdraw()  # Hide window during test

        from gui_app import TradingBotGUI
        app = TradingBotGUI(root)

        print("✓ GUI window created successfully")

        # Check if notebook exists
        if hasattr(app, 'notebook'):
            print("✓ Notebook widget found")

            # Count tabs
            tab_count = app.notebook.index('end')
            print(f"  Total tabs: {tab_count}")

            # List tab names
            for i in range(tab_count):
                tab_name = app.notebook.tab(i, 'text')
                print(f"  Tab {i}: {tab_name}")

                if "멀티 타임프레임" in tab_name or "Multi" in tab_name:
                    print("  ✓ Multi-timeframe tab found!")
        else:
            print("✗ Notebook widget not found")
            return False

        # Check if multi_chart_widget exists
        if hasattr(app, 'multi_chart_widget'):
            print("✓ multi_chart_widget attribute found")
        else:
            print("✗ multi_chart_widget attribute not found")
            return False

        root.destroy()
        return True

    except Exception as e:
        print(f"✗ Failed to create GUI: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("GUI Launch Test Suite")
    print("=" * 60)

    results = {}

    results['Import gui_app'] = test_gui_import()
    if not results['Import gui_app']:
        print("\n✗ Cannot proceed without gui_app import")
        return 1

    results['Import MultiTimeframeChartTab'] = test_multi_chart_tab_import()
    if not results['Import MultiTimeframeChartTab']:
        print("\n✗ Cannot proceed without MultiTimeframeChartTab import")
        return 1

    results['Create GUI'] = test_gui_creation()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:35s}: {status}")

    all_passed = all(results.values())
    if all_passed:
        print("\n✓ All GUI tests passed!")
        print("\n🎉 GUI is ready to launch!")
        print("\nTo launch the full GUI, run:")
        print("  cd /Users/seongwookjang/project/git/violet_sw/005_money/001_python_code")
        print("  source ../.venv/bin/activate")
        print("  python gui_app.py")
        return 0
    else:
        print("\n✗ Some tests failed - see details above")
        return 1

if __name__ == "__main__":
    sys.exit(main())
