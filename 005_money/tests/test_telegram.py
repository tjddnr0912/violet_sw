#!/usr/bin/env python3
"""
Telegram Notification Test Script

This script tests all Telegram notification functionality for Ver3 Trading Bot.
Run this script to verify your Telegram bot is properly configured and working.

Usage:
    python test_telegram.py

Requirements:
    - TELEGRAM_BOT_TOKEN set in .env
    - TELEGRAM_CHAT_ID set in .env
    - TELEGRAM_NOTIFICATIONS_ENABLED=True in .env
"""

import os
import sys
from pathlib import Path

# Add the 001_python_code directory to Python path
sys.path.insert(0, str(Path(__file__).parent / "001_python_code"))

from lib.core.telegram_notifier import get_telegram_notifier


def print_header(text):
    """Print formatted section header."""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60)


def print_status(success, message):
    """Print status message with emoji."""
    emoji = "✅" if success else "❌"
    print(f"{emoji} {message}")


def check_configuration():
    """Check if Telegram is properly configured."""
    print_header("Configuration Check")

    telegram = get_telegram_notifier()

    # Check enabled status
    if not telegram.enabled:
        print_status(False, "Telegram notifications are DISABLED")
        print("\nPossible reasons:")
        print("  1. TELEGRAM_NOTIFICATIONS_ENABLED is set to False")
        print("  2. TELEGRAM_BOT_TOKEN is missing")
        print("  3. TELEGRAM_CHAT_ID is missing")
        print("\nTo fix:")
        print("  1. Create/edit .env file in the project root")
        print("  2. Add the following lines:")
        print("     TELEGRAM_BOT_TOKEN=your_bot_token_here")
        print("     TELEGRAM_CHAT_ID=your_chat_id_here")
        print("     TELEGRAM_NOTIFICATIONS_ENABLED=True")
        return False

    # Check token
    if telegram.bot_token:
        token_preview = telegram.bot_token[:10] + "..." if len(telegram.bot_token) > 10 else telegram.bot_token
        print_status(True, f"Bot Token: {token_preview}")
    else:
        print_status(False, "Bot Token: Not found")
        return False

    # Check chat ID
    if telegram.chat_id:
        print_status(True, f"Chat ID: {telegram.chat_id}")
    else:
        print_status(False, "Chat ID: Not found")
        return False

    print_status(True, "Configuration looks good!")
    return True


def test_simple_message():
    """Test sending a simple text message."""
    print_header("Test 1: Simple Text Message")

    telegram = get_telegram_notifier()

    message = "🤖 **Ver3 Trading Bot Test**\n\nThis is a test message from the trading bot."

    print("Sending simple message...")
    success = telegram.send_message(message)

    if success:
        print_status(True, "Simple message sent successfully!")
        print("   Check your Telegram app to see the message.")
    else:
        print_status(False, "Failed to send simple message")
        print("   Check your bot token and chat ID")

    return success


def test_buy_alert():
    """Test sending a buy trade alert."""
    print_header("Test 2: Buy Trade Alert")

    telegram = get_telegram_notifier()

    print("Sending buy alert...")
    success = telegram.send_trade_alert(
        action="BUY",
        ticker="BTC",
        amount=0.001,
        price=50000000,
        success=True,
        reason="Test buy - Score: 4/4, Regime: BULLISH",
        order_id="TEST_BUY_12345"
    )

    if success:
        print_status(True, "Buy alert sent successfully!")
    else:
        print_status(False, "Failed to send buy alert")

    return success


def test_sell_alert():
    """Test sending a sell trade alert."""
    print_header("Test 3: Sell Trade Alert")

    telegram = get_telegram_notifier()

    print("Sending sell alert...")
    success = telegram.send_trade_alert(
        action="SELL",
        ticker="ETH",
        amount=0.05,
        price=4200000,
        success=True,
        reason="Test sell - TP1 reached (+2.5%)",
        order_id="TEST_SELL_67890"
    )

    if success:
        print_status(True, "Sell alert sent successfully!")
    else:
        print_status(False, "Failed to send sell alert")

    return success


def test_close_alert():
    """Test sending a position close alert."""
    print_header("Test 4: Position Close Alert")

    telegram = get_telegram_notifier()

    print("Sending close alert...")
    success = telegram.send_trade_alert(
        action="CLOSE",
        ticker="XRP",
        amount=100.0,
        price=800,
        success=True,
        reason="Test close - Stop-loss triggered",
        order_id="TEST_CLOSE_11111"
    )

    if success:
        print_status(True, "Close alert sent successfully!")
    else:
        print_status(False, "Failed to send close alert")

    return success


def test_error_alert():
    """Test sending an error alert."""
    print_header("Test 5: Error Alert")

    telegram = get_telegram_notifier()

    print("Sending error alert...")
    success = telegram.send_error_alert(
        error_type="Test Error",
        error_message="This is a test error notification",
        details="Ticker: BTC\nAction: BUY\nReason: Testing error notification system"
    )

    if success:
        print_status(True, "Error alert sent successfully!")
    else:
        print_status(False, "Failed to send error alert")

    return success


def test_bot_status_started():
    """Test sending bot started status."""
    print_header("Test 6: Bot Started Status")

    telegram = get_telegram_notifier()

    print("Sending bot started status...")
    success = telegram.send_bot_status(
        status="STARTED",
        positions=0,
        max_positions=2,
        total_pnl=0,
        coins=["BTC", "ETH", "XRP"]
    )

    if success:
        print_status(True, "Bot started status sent successfully!")
    else:
        print_status(False, "Failed to send bot started status")

    return success


def test_bot_status_running():
    """Test sending bot running status."""
    print_header("Test 7: Bot Running Status")

    telegram = get_telegram_notifier()

    print("Sending bot running status...")
    success = telegram.send_bot_status(
        status="RUNNING",
        positions=2,
        max_positions=2,
        total_pnl=50000,
        coins=["BTC", "ETH"]
    )

    if success:
        print_status(True, "Bot running status sent successfully!")
    else:
        print_status(False, "Failed to send bot running status")

    return success


def test_bot_status_stopped():
    """Test sending bot stopped status."""
    print_header("Test 8: Bot Stopped Status")

    telegram = get_telegram_notifier()

    print("Sending bot stopped status...")
    success = telegram.send_bot_status(
        status="STOPPED",
        positions=1,
        max_positions=2,
        total_pnl=-15000,
        coins=["BTC"]
    )

    if success:
        print_status(True, "Bot stopped status sent successfully!")
    else:
        print_status(False, "Failed to send bot stopped status")

    return success


def test_daily_summary():
    """Test sending daily summary."""
    print_header("Test 9: Daily Trading Summary")

    telegram = get_telegram_notifier()

    print("Sending daily summary...")
    success = telegram.send_daily_summary({
        'date': '2025-12-09',
        'buy_count': 5,
        'sell_count': 3,
        'total_volume': 500000,
        'total_fees': 1250,
        'net_pnl': 25000,
        'success_count': 7,
        'fail_count': 1
    })

    if success:
        print_status(True, "Daily summary sent successfully!")
    else:
        print_status(False, "Failed to send daily summary")

    return success


def main():
    """Main test function."""
    print("\n" + "=" * 60)
    print("  📱 TELEGRAM NOTIFICATION TEST SUITE")
    print("  Ver3 Trading Bot")
    print("=" * 60)

    # Check configuration first
    if not check_configuration():
        print("\n" + "=" * 60)
        print("  ❌ Configuration check failed!")
        print("  Please fix the configuration and try again.")
        print("=" * 60)
        return

    # Run all tests
    tests = [
        ("Simple Message", test_simple_message),
        ("Buy Alert", test_buy_alert),
        ("Sell Alert", test_sell_alert),
        ("Close Alert", test_close_alert),
        ("Error Alert", test_error_alert),
        ("Bot Started", test_bot_status_started),
        ("Bot Running", test_bot_status_running),
        ("Bot Stopped", test_bot_status_stopped),
        ("Daily Summary", test_daily_summary),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print_status(False, f"Exception in {test_name}: {e}")
            results.append((test_name, False))

    # Print summary
    print_header("Test Summary")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print(f"\nTotal tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")

    print("\nDetailed results:")
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        emoji = "✅" if result else "❌"
        print(f"  {emoji} {test_name:20s} - {status}")

    print("\n" + "=" * 60)
    if passed == total:
        print("  🎉 ALL TESTS PASSED!")
        print("  Your Telegram integration is working perfectly!")
    else:
        print("  ⚠️  SOME TESTS FAILED")
        print("  Check your Telegram bot configuration.")
    print("=" * 60)
    print("\n📱 Check your Telegram app to see all the notifications!\n")


if __name__ == "__main__":
    main()
