#!/usr/bin/env python3
"""
Test script for Telegram bot commands

This script tests the Telegram bot handler functionality
without running the full trading bot.

Usage:
    python test_telegram_commands.py

Prerequisites:
    1. Set TELEGRAM_BOT_TOKEN in .env
    2. Set TELEGRAM_CHAT_ID in .env
    3. Set TELEGRAM_NOTIFICATIONS_ENABLED=True in .env
    4. Install python-telegram-bot: pip install python-telegram-bot>=20.7
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Setup path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "001_python_code"))

# Load environment variables
load_dotenv(project_root / ".env")


def check_dependencies():
    """Check if required dependencies are installed."""
    print("Checking dependencies...")

    try:
        import telegram
        print(f"  python-telegram-bot: {telegram.__version__}")
    except ImportError:
        print("  python-telegram-bot: NOT INSTALLED")
        print("\n  Install with: pip install python-telegram-bot>=20.7")
        return False

    return True


def check_credentials():
    """Check if Telegram credentials are configured."""
    print("\nChecking credentials...")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    enabled = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "False").lower() == "true"

    if bot_token:
        print(f"  Bot Token: {bot_token[:10]}...{bot_token[-5:]}")
    else:
        print("  Bot Token: NOT SET")

    if chat_id:
        print(f"  Chat ID: {chat_id}")
    else:
        print("  Chat ID: NOT SET")

    print(f"  Notifications Enabled: {enabled}")

    if not bot_token or not chat_id:
        print("\n  Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file")
        return False

    if not enabled:
        print("\n  Set TELEGRAM_NOTIFICATIONS_ENABLED=True in .env file")
        return False

    return True


class MockTradingBot:
    """Mock trading bot for testing commands."""

    def __init__(self):
        self.running = True
        self.cycle_count = 42
        self.last_analysis_time = None
        self.coins = ['BTC', 'ETH', 'XRP']
        self.check_interval = 900  # 15 minutes

        # Mock transaction history
        self.transaction_history = MockTransactionHistory()

    def get_portfolio_summary(self):
        """Return mock portfolio summary."""
        return {
            'total_positions': 1,
            'max_positions': 2,
            'total_pnl_krw': 15000,
            'coins': {
                'BTC': {
                    'analysis': {
                        'market_regime': 'bullish',
                        'entry_score': 3,
                        'action': 'HOLD'
                    },
                    'position': {
                        'has_position': True,
                        'entry_price': 50000000,
                        'current_price': 51000000,
                        'size': 0.001,
                        'pnl': 15000,
                        'pnl_pct': 2.0,
                        'entry_time': '2025-12-16 10:00:00'
                    }
                },
                'ETH': {
                    'analysis': {
                        'market_regime': 'ranging',
                        'entry_score': 1,
                        'action': 'HOLD'
                    },
                    'position': {
                        'has_position': False
                    }
                },
                'XRP': {
                    'analysis': {
                        'market_regime': 'bearish',
                        'entry_score': 0,
                        'action': 'HOLD'
                    },
                    'position': {
                        'has_position': False
                    }
                }
            }
        }

    def stop(self):
        """Stop the mock bot."""
        print("\n[MockBot] Stop command received!")
        self.running = False


class MockTransactionHistory:
    """Mock transaction history for testing."""

    def get_summary(self, days=1):
        """Return mock summary."""
        return {
            'buy_count': 3,
            'sell_count': 2,
            'total_volume': 250000,
            'total_fees': 625,
            'net_pnl': 15000,
            'successful_transactions': 5,
            'fail_count': 0
        }


def test_handler():
    """Test the Telegram bot handler."""
    print("\n" + "=" * 60)
    print("Testing Telegram Bot Handler")
    print("=" * 60)

    from lib.core.telegram_bot_handler import TelegramBotHandler

    # Create mock trading bot
    mock_bot = MockTradingBot()
    print("\nMock trading bot created:")
    print(f"  Running: {mock_bot.running}")
    print(f"  Cycles: {mock_bot.cycle_count}")
    print(f"  Coins: {mock_bot.coins}")

    # Create handler with mock bot
    handler = TelegramBotHandler(mock_bot)

    if not handler.enabled:
        print("\nHandler not enabled. Check credentials.")
        return

    print("\nStarting Telegram bot handler...")
    print("The bot will now listen for commands.")
    print("\nAvailable commands:")
    print("  /start    - Welcome message")
    print("  /help     - Command list")
    print("  /status   - Bot status")
    print("  /positions - Position details")
    print("  /summary  - Trading summary")
    print("  /stop     - Stop bot (with confirmation)")
    print("\nSend these commands to your bot in Telegram!")
    print("\nPress Ctrl+C to stop the test...")

    try:
        handler.start()

        # Keep running until interrupted or bot stopped
        while handler.running and mock_bot.running:
            time.sleep(1)

        if not mock_bot.running:
            print("\nBot was stopped via Telegram command!")

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    finally:
        handler.stop()
        print("Handler stopped")


def main():
    print("=" * 60)
    print("Telegram Bot Commands Test")
    print("=" * 60)

    # Check dependencies
    if not check_dependencies():
        print("\nPlease install missing dependencies first.")
        return 1

    # Check credentials
    if not check_credentials():
        print("\nPlease configure credentials first.")
        return 1

    # Run test
    test_handler()

    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
