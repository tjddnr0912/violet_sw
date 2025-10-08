#!/usr/bin/env python3
"""
Standalone test for GUITradingBotV2 to diagnose issues.
This runs the bot independently without GUI to check if core logic works.
"""

import sys
import os
import time
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/test_bot_v2.log'),
        logging.StreamHandler()
    ]
)

# Add paths
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

from gui_trading_bot_v2 import GUITradingBotV2

def test_log_callback(message):
    """Test callback for logging"""
    print(f"[CALLBACK] {message}")

def test_signal_callback(event_type, signal_data):
    """Test callback for signals"""
    print(f"[SIGNAL] {event_type}: {signal_data}")

if __name__ == "__main__":
    print("=" * 60)
    print("GUITradingBotV2 Standalone Test")
    print("=" * 60)

    # Create bot with callbacks
    bot = GUITradingBotV2(
        log_callback=test_log_callback,
        signal_callback=test_signal_callback
    )

    print(f"\n✅ Bot initialized")
    print(f"   - Dry run: {bot.dry_run}")
    print(f"   - Live mode: {bot.live_mode}")
    print(f"   - Regime: {bot.regime}")

    # Test single market analysis
    print(f"\n📊 Running single market analysis...")
    try:
        bot.analyze_market()
        print("✅ Market analysis completed")
    except Exception as e:
        print(f"❌ Market analysis failed: {str(e)}")
        import traceback
        traceback.print_exc()

    # Get status
    print(f"\n📈 Bot status:")
    status = bot.get_status()
    for key, value in status.items():
        print(f"   - {key}: {value}")

    # Optional: Run bot for 3 cycles (3 minutes)
    run_cycles = input("\n🔄 Run bot for 3 analysis cycles (3 minutes)? [y/N]: ")
    if run_cycles.lower() == 'y':
        print("\n🚀 Starting bot (will run 3 cycles)...")

        # Start in background
        import threading
        bot_thread = threading.Thread(target=bot.run, daemon=True)
        bot_thread.start()

        # Wait for 3 minutes
        for i in range(3):
            print(f"\n⏳ Cycle {i+1}/3 - Waiting 60 seconds...")
            time.sleep(60)
            status = bot.get_status()
            print(f"   Regime: {status['regime']}, Entry Score: {status['entry_score']}/4")

        # Stop bot
        bot.stop()
        print("\n✅ Bot stopped")

    print("\n" + "=" * 60)
    print("Test completed")
    print("=" * 60)
