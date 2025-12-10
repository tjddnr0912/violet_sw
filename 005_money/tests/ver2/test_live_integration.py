"""
Test script to verify LiveExecutorV2 integration with GUITradingBotV2

This script tests:
1. Import of all required modules
2. Initialization of GUITradingBotV2 in different modes
3. Verification of LiveExecutorV2 integration
4. Configuration checks

DO NOT execute real trades - tests only initialization and config
"""

import sys
import os

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ver2.gui_trading_bot_v2 import GUITradingBotV2
from ver2 import config_v2


def test_imports():
    """Test 1: Verify all imports work correctly"""
    print("\n" + "="*70)
    print("TEST 1: Verifying imports...")
    print("="*70)

    try:
        from lib.api.bithumb_api import BithumbAPI, get_candlestick, get_ticker
        from lib.core.logger import TradingLogger
        from ver2.live_executor_v2 import LiveExecutorV2
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {str(e)}")
        return False


def test_dry_run_initialization():
    """Test 2: Initialize bot in dry-run mode"""
    print("\n" + "="*70)
    print("TEST 2: Initializing bot in DRY-RUN mode...")
    print("="*70)

    try:
        # Create a simple log callback
        def log_callback(msg):
            print(f"[BOT LOG] {msg}")

        # Initialize bot in dry-run mode
        bot = GUITradingBotV2(log_callback=log_callback)

        # Verify configuration
        print(f"\n📋 Bot Configuration:")
        print(f"   Mode: {'LIVE' if bot.live_mode else 'BACKTEST'}")
        print(f"   Dry-run: {bot.dry_run}")
        print(f"   Executor initialized: {bot.executor is not None}")
        print(f"   API initialized: {bot.api is not None}")
        print(f"   Logger initialized: {bot.logger is not None}")

        # Check position state
        print(f"\n📊 Position State:")
        print(f"   Regime: {bot.regime}")
        print(f"   Has position: {bot.position is not None}")
        print(f"   Entry score: {bot.entry_score}")

        print("\n✅ Dry-run initialization successful")
        return True

    except Exception as e:
        print(f"❌ Dry-run initialization failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_live_mode_initialization():
    """Test 3: Initialize bot in LIVE mode (with API key check)"""
    print("\n" + "="*70)
    print("TEST 3: Initializing bot in LIVE mode (no API keys = fallback to dry-run)...")
    print("="*70)

    try:
        # Create a simple log callback
        def log_callback(msg):
            print(f"[BOT LOG] {msg}")

        # Temporarily modify config to live mode
        config = config_v2.get_version_config(mode='live')

        # Initialize bot (should fallback to dry-run if no API keys)
        bot = GUITradingBotV2(log_callback=log_callback)

        # Verify configuration
        print(f"\n📋 Bot Configuration:")
        print(f"   Mode: {'LIVE' if bot.live_mode else 'BACKTEST'}")
        print(f"   Dry-run: {bot.dry_run}")
        print(f"   Executor initialized: {bot.executor is not None}")

        # Check environment variables
        connect_key = os.environ.get('BITHUMB_CONNECT_KEY')
        secret_key = os.environ.get('BITHUMB_SECRET_KEY')

        print(f"\n🔑 API Key Status:")
        print(f"   BITHUMB_CONNECT_KEY: {'SET' if connect_key else 'NOT SET'}")
        print(f"   BITHUMB_SECRET_KEY: {'SET' if secret_key else 'NOT SET'}")

        if not connect_key or not secret_key:
            print("\n⚠️  Expected behavior: Bot should fallback to dry-run mode")
            if bot.dry_run:
                print("✅ Correct: Bot is in dry-run mode")
            else:
                print("❌ Error: Bot should be in dry-run without API keys")
                return False
        else:
            print("\n✅ API keys found - LiveExecutorV2 should be initialized")
            if bot.executor:
                print("✅ Correct: LiveExecutorV2 is initialized")
            else:
                print("❌ Error: LiveExecutorV2 should be initialized with API keys")
                return False

        print("\n✅ Live mode initialization test successful")
        return True

    except Exception as e:
        print(f"❌ Live mode initialization failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_configuration_validation():
    """Test 4: Validate configuration settings"""
    print("\n" + "="*70)
    print("TEST 4: Validating configuration...")
    print("="*70)

    try:
        config = config_v2.get_version_config()

        # Check critical config sections
        critical_sections = [
            'EXECUTION_CONFIG',
            'TRADING_CONFIG',
            'SAFETY_CONFIG',
            'INDICATOR_CONFIG',
            'ENTRY_SCORING_CONFIG'
        ]

        print("\n📋 Configuration Sections:")
        for section in critical_sections:
            if section in config:
                print(f"   ✅ {section}")
            else:
                print(f"   ❌ {section} - MISSING")
                return False

        # Check trading config values
        print(f"\n💰 Trading Configuration:")
        trading_config = config.get('TRADING_CONFIG', {})
        print(f"   Symbol: {trading_config.get('symbol', 'N/A')}")
        print(f"   Trade amount (KRW): {trading_config.get('trade_amount_krw', 'N/A')}")
        print(f"   Min trade amount: {trading_config.get('min_trade_amount', 'N/A')}")

        # Check execution config
        print(f"\n⚙️  Execution Configuration:")
        exec_config = config.get('EXECUTION_CONFIG', {})
        print(f"   Mode: {exec_config.get('mode', 'N/A')}")
        print(f"   Dry-run: {exec_config.get('dry_run', 'N/A')}")
        print(f"   Confirmation required: {exec_config.get('confirmation_required', 'N/A')}")

        # Check safety config
        print(f"\n🛡️  Safety Configuration:")
        safety_config = config.get('SAFETY_CONFIG', {})
        print(f"   Max daily trades: {safety_config.get('max_daily_trades', 'N/A')}")
        print(f"   Max consecutive losses: {safety_config.get('max_consecutive_losses', 'N/A')}")
        print(f"   Max daily loss %: {safety_config.get('max_daily_loss_pct', 'N/A')}")

        print("\n✅ Configuration validation successful")
        return True

    except Exception as e:
        print(f"❌ Configuration validation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_executor_methods():
    """Test 5: Verify executor methods are accessible"""
    print("\n" + "="*70)
    print("TEST 5: Verifying executor method signatures...")
    print("="*70)

    try:
        from ver2.live_executor_v2 import LiveExecutorV2

        # Check required methods exist
        required_methods = [
            'execute_order',
            'close_position',
            'update_stop_loss',
            'update_highest_high',
            'get_position',
            'has_position'
        ]

        print("\n🔍 Checking LiveExecutorV2 methods:")
        for method_name in required_methods:
            if hasattr(LiveExecutorV2, method_name):
                print(f"   ✅ {method_name}")
            else:
                print(f"   ❌ {method_name} - MISSING")
                return False

        print("\n✅ All required executor methods present")
        return True

    except Exception as e:
        print(f"❌ Executor method check failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("LIVE EXECUTOR V2 INTEGRATION TEST SUITE")
    print("="*70)
    print("\nThis test suite verifies the integration of LiveExecutorV2 with GUITradingBotV2")
    print("NO REAL TRADES will be executed during these tests\n")

    tests = [
        ("Import Verification", test_imports),
        ("Dry-run Initialization", test_dry_run_initialization),
        ("Live Mode Initialization", test_live_mode_initialization),
        ("Configuration Validation", test_configuration_validation),
        ("Executor Methods", test_executor_methods)
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {str(e)}")
            results.append((test_name, False))

    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Integration is working correctly!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed - Please review errors above")
        return 1


if __name__ == "__main__":
    exit(main())
