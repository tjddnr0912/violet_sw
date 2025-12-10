#!/usr/bin/env python3
"""
Test script to verify score monitoring widget coin symbol fix.

This script tests:
1. Score widget initialization with coin symbol
2. Adding score checks with different coins
3. Filtering by coin symbol
4. Updating coin dynamically
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ver2.score_monitoring_widget_v2 import ScoreMonitoringWidgetV2
from ver2 import config_v2


def test_score_coin_filtering():
    """Test that score monitoring correctly filters by coin"""
    print("\n=== Testing Score Monitoring Coin Symbol Fix ===\n")

    # Create test window
    root = tk.Tk()
    root.title("Score Monitoring Coin Test - BTC")
    root.geometry("1000x700")

    # Get config
    v2_config = config_v2.get_version_config()

    # Test 1: Initialize with BTC
    print("Test 1: Initializing widget with BTC...")
    widget = ScoreMonitoringWidgetV2(root, v2_config, coin_symbol='BTC')
    assert widget.coin_symbol == 'BTC', "Widget coin should be BTC"
    print("✅ Widget initialized with BTC")

    # Test 2: Add BTC score checks
    print("\nTest 2: Adding BTC score checks...")
    base_time = datetime.now() - timedelta(hours=1)

    for i in range(5):
        widget.add_score_check({
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
        })

    btc_count = len(widget.score_checks)
    print(f"✅ Added {btc_count} BTC score checks")
    assert btc_count == 5, f"Should have 5 BTC checks, got {btc_count}"

    # Test 3: Try to add SOL score checks (should be filtered out)
    print("\nTest 3: Adding SOL score checks (should be filtered)...")
    for i in range(3):
        widget.add_score_check({
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
        })

    # Count should still be 5 (SOL checks should be filtered out)
    still_btc_count = len(widget.score_checks)
    print(f"✅ Still {still_btc_count} checks (SOL checks filtered out)")
    assert still_btc_count == 5, f"Should still have 5 BTC checks, got {still_btc_count}"

    # Test 4: Update to SOL coin
    print("\nTest 4: Updating widget to SOL...")
    widget.update_coin('SOL')
    assert widget.coin_symbol == 'SOL', "Widget coin should be SOL"

    # Title should now show SOL
    title = widget.stats_title_var.get()
    assert 'SOL' in title, f"Title should contain 'SOL', got: {title}"
    print(f"✅ Widget updated to SOL, title: {title}")

    # Score checks should be cleared (no SOL data in memory yet)
    sol_count = len(widget.score_checks)
    print(f"✅ Score checks after coin change: {sol_count} (expected 0 since we filtered out SOL earlier)")

    # Test 5: Add SOL score checks
    print("\nTest 5: Adding SOL score checks...")
    for i in range(3):
        widget.add_score_check({
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

    sol_count_after = len(widget.score_checks)
    print(f"✅ Added {sol_count_after} SOL score checks")
    assert sol_count_after == 3, f"Should have 3 SOL checks, got {sol_count_after}"

    # Test 6: Try to add BTC score checks (should be filtered out now)
    print("\nTest 6: Adding BTC score checks (should be filtered now)...")
    widget.add_score_check({
        'timestamp': datetime.now(),
        'score': 4,
        'components': {
            'bb_touch': 1,
            'rsi_oversold': 1,
            'stoch_cross': 2
        },
        'regime': 'BULLISH',
        'price': 100000000,
        'coin': 'BTC'  # Different coin!
    })

    still_sol_count = len(widget.score_checks)
    print(f"✅ Still {still_sol_count} SOL checks (BTC check filtered out)")
    assert still_sol_count == 3, f"Should still have 3 SOL checks, got {still_sol_count}"

    print("\n=== All Tests Passed! ===")
    print("\nScore monitoring widget now correctly:")
    print("  ✅ Tracks coin symbol for each score check")
    print("  ✅ Filters score checks by current coin")
    print("  ✅ Updates display when coin changes")
    print("  ✅ Shows correct coin in title")
    print("\nYou can now close this window or manually test the UI.")

    root.mainloop()


if __name__ == "__main__":
    test_score_coin_filtering()
