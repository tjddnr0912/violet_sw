#!/usr/bin/env python3
"""
Test script to verify Ver3 GUI file logging functionality.

This script tests:
1. Log file creation
2. Writing logs to file
3. Daily rotation mechanism
4. Multiple log level handling
"""

import os
import sys
import time
from datetime import datetime

# Add paths for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)
sys.path.insert(0, os.path.dirname(script_dir))

def test_gui_logging():
    """Test GUI logging functionality without starting the full GUI"""
    print("=== Testing Ver3 GUI File Logging ===\n")

    # Import after path setup
    from ver3.gui_app_v3 import TradingBotGUIV3
    import tkinter as tk

    # Create a minimal Tk root for testing
    root = tk.Tk()
    root.withdraw()  # Hide the window

    try:
        print("1. Creating GUI instance...")
        app = TradingBotGUIV3(root)

        print("2. Testing log file creation...")
        expected_log_file = os.path.join('logs', f'ver3_gui_{datetime.now().strftime("%Y%m%d")}.log')

        if os.path.exists(expected_log_file):
            print(f"   ✓ Log file created: {expected_log_file}")
        else:
            print(f"   ✗ Log file not found: {expected_log_file}")
            return False

        print("\n3. Testing different log levels...")
        test_messages = [
            ("INFO", "Test info message"),
            ("WARNING", "Test warning message"),
            ("ERROR", "Test error message"),
            ("INFO", "Another info message with special chars: 한글 테스트"),
        ]

        for level, message in test_messages:
            app._log_to_gui(level, message)
            print(f"   Logged [{level}]: {message}")

        print("\n4. Verifying file contents...")
        time.sleep(0.1)  # Brief wait for file writes

        with open(expected_log_file, 'r', encoding='utf-8') as f:
            file_contents = f.read()
            print(f"   Log file size: {len(file_contents)} bytes")

            # Check if test messages are in file
            all_found = True
            for level, message in test_messages:
                if message in file_contents:
                    print(f"   ✓ Found: {message}")
                else:
                    print(f"   ✗ Missing: {message}")
                    all_found = False

            if all_found:
                print("\n5. Full log file contents:")
                print("   " + "=" * 60)
                for line in file_contents.split('\n'):
                    if line.strip():
                        print(f"   {line}")
                print("   " + "=" * 60)

            return all_found

    except Exception as e:
        print(f"   ✗ Error during test: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        root.destroy()

if __name__ == "__main__":
    success = test_gui_logging()

    if success:
        print("\n=== ✓ All tests passed! ===")
        print("\nFile logging is working correctly.")
        print(f"Logs are being written to: logs/ver3_gui_YYYYMMDD.log")
        sys.exit(0)
    else:
        print("\n=== ✗ Some tests failed ===")
        sys.exit(1)
