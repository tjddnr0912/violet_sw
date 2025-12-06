#!/usr/bin/env python3
"""
Ver3 Trading Bot CLI Launcher
Directly runs Ver3 trading bot without GUI
"""

import sys
import os
import signal

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Change to project root
project_root = os.path.dirname(parent_dir)
os.chdir(project_root)

from ver3.trading_bot_v3 import TradingBotV3
from ver3 import config_v3
from ver3.preference_manager_v3 import PreferenceManagerV3


def signal_handler(signum, frame):
    """Handle termination signals"""
    print("\n\n프로그램 종료 신호를 받았습니다.")
    print("봇을 안전하게 종료합니다...")
    sys.exit(0)


def main():
    """Main entry point for Ver3 CLI"""

    print("=" * 60)
    print("🤖 Ver3 Trading Bot - CLI Mode")
    print("=" * 60)
    print()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize preference manager
        print("📁 Loading saved preferences...")
        pref_manager = PreferenceManagerV3()
        saved_prefs = pref_manager.load_preferences()

        # Get base configuration
        config = config_v3.get_version_config()

        # Update active coins from preferences
        active_coins_from_prefs = saved_prefs.get('portfolio_config', {}).get('default_coins', ['BTC', 'ETH', 'XRP'])
        try:
            config_v3.update_active_coins(active_coins_from_prefs)
            config = config_v3.get_version_config()
            print(f"✓ Loaded coins from preferences: {active_coins_from_prefs}")
        except (ValueError, KeyError) as e:
            print(f"⚠ Using default coins (preference error: {e})")

        # Merge saved preferences with config
        config = pref_manager.merge_with_config(saved_prefs, config)
        print("✓ Preferences merged with config")
        print()

        # Display startup info
        print("📊 Configuration:")
        print(f"  • Coins: {config['PORTFOLIO_CONFIG']['default_coins']}")
        print(f"  • Max Positions: {config['PORTFOLIO_CONFIG']['max_positions']}")
        print(f"  • Position Size: {config['POSITION_SIZING_CONFIG']['base_amount_krw']:,} KRW")
        print(f"  • Check Interval: {config['SCHEDULE_CONFIG']['check_interval_minutes']} min")
        print(f"  • Dry Run: {config['EXECUTION_CONFIG']['dry_run']}")
        print()

        # Initialize trading bot (bot creates its own logger)
        print("🚀 Initializing Ver3 Trading Bot...")
        bot = TradingBotV3(config)

        print("✅ Bot initialized successfully!")
        print()
        print("Starting trading loop...")
        print("Press Ctrl+C to stop")
        print("=" * 60)
        print()

        # Run the bot
        bot.run()

    except KeyboardInterrupt:
        print("\n\nKeyboard interrupt received")
        print("Shutting down gracefully...")
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
