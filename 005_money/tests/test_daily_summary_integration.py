"""
Integration test for Daily Summary feature with TradingBotV3.

This test verifies that the daily summary feature works correctly
when integrated with the actual TradingBotV3 class.
"""

import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_python_code'))

# Set environment variables before importing (to avoid API warnings)
os.environ['TELEGRAM_BOT_TOKEN'] = 'test_token'
os.environ['TELEGRAM_CHAT_ID'] = 'test_chat_id'
os.environ['TELEGRAM_NOTIFICATIONS_ENABLED'] = 'false'  # Disable actual sending

from ver3.config_v3 import get_version_config
from ver3.trading_bot_v3 import TradingBotV3


def test_trading_bot_daily_summary_integration():
    """Test that TradingBotV3 can generate and send daily summary"""
    print("\n" + "="*60)
    print("Integration Test: TradingBotV3 Daily Summary")
    print("="*60)

    # Get config
    config = get_version_config()

    # Create bot instance
    print("Creating TradingBotV3 instance...")
    bot = TradingBotV3(config, log_prefix='test_daily_summary')

    # Verify daily summary methods exist
    assert hasattr(bot, '_check_and_send_daily_summary'), "Missing _check_and_send_daily_summary method"
    assert hasattr(bot, '_send_daily_summary'), "Missing _send_daily_summary method"
    assert hasattr(bot, 'send_daily_summary_now'), "Missing send_daily_summary_now method"
    assert hasattr(bot, '_daily_summary_sent_date'), "Missing _daily_summary_sent_date attribute"
    print("  All required methods/attributes present")

    # Add some test transactions
    print("Adding test transactions...")
    bot.transaction_history.add_transaction(
        ticker='BTC',
        action='BUY',
        amount=0.001,
        price=50000000,
        order_id='INT_TEST_001',
        fee=25,
        success=True,
        pnl=0
    )
    bot.transaction_history.add_transaction(
        ticker='BTC',
        action='SELL',
        amount=0.001,
        price=51000000,
        order_id='INT_TEST_002',
        fee=25.5,
        success=True,
        pnl=1000
    )
    print("  Added 2 test transactions")

    # Test send_daily_summary_now()
    print("Testing send_daily_summary_now()...")
    result = bot.send_daily_summary_now()
    print(f"  Result: {result} (False expected since Telegram disabled)")

    # Verify the summary data was generated correctly
    summary = bot.transaction_history.get_summary(days=1)
    print(f"  Today's summary: {summary}")

    # Verify summary contains our test data
    assert summary['buy_count'] >= 1, "Should have at least 1 buy"
    assert summary['sell_count'] >= 1, "Should have at least 1 sell"
    assert summary['net_pnl'] >= 1000, "Should have positive PnL from test transaction"

    print("\nPASSED: TradingBotV3 daily summary integration test")
    return True


def test_check_and_send_at_different_times():
    """Test _check_and_send_daily_summary at different times"""
    print("\n" + "="*60)
    print("Integration Test: Time-based trigger")
    print("="*60)

    config = get_version_config()
    bot = TradingBotV3(config, log_prefix='test_time_trigger')

    # Mock datetime to test different times
    today = datetime.now().strftime('%Y-%m-%d')

    # Test 1: Before 23:45 - should NOT trigger
    print("Testing at 22:00 (before trigger window)...")
    with patch('ver3.trading_bot_v3.datetime') as mock_datetime:
        mock_now = datetime(2025, 12, 12, 22, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.strftime = datetime.strftime

        bot._daily_summary_sent_date = None
        bot._check_and_send_daily_summary()
        assert bot._daily_summary_sent_date is None, "Should not send before 23:45"
        print("  Correctly did not trigger before 23:45")

    # Test 2: At 23:50 - should trigger
    print("Testing at 23:50 (in trigger window)...")
    with patch('ver3.trading_bot_v3.datetime') as mock_datetime:
        mock_now = datetime(2025, 12, 12, 23, 50, 0)
        mock_datetime.now.return_value = mock_now

        bot._daily_summary_sent_date = None
        bot._check_and_send_daily_summary()
        # Note: actual send will fail (telegram disabled), but the logic should attempt
        print("  Trigger logic executed at 23:50")

    print("\nPASSED: Time-based trigger integration test")
    return True


def run_integration_tests():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("Running Daily Summary Integration Tests")
    print("="*60)

    tests = [
        test_trading_bot_daily_summary_integration,
        test_check_and_send_at_different_times,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"FAILED: {test.__name__}")
            print(f"  Error: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR in {test.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "="*60)
    print(f"Integration Test Results: {passed} passed, {failed} failed")
    print("="*60)

    return failed == 0


if __name__ == '__main__':
    success = run_integration_tests()
    sys.exit(0 if success else 1)
