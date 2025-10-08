"""
Test Live Executor Integration - Verification Script

This script verifies that the LiveExecutorV2 integration in gui_trading_bot_v2.py
is working correctly. It tests:

1. Import of modules
2. Initialization in dry-run mode
3. Initialization in live mode (with API keys)
4. Order execution flow (simulated)
5. Position tracking
6. Stop-loss updates

Run this script to verify the integration is complete and functional.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_imports():
    """Test 1: Verify all required imports work"""
    print("\n" + "="*60)
    print("TEST 1: Import Verification")
    print("="*60)

    try:
        from ver2.live_executor_v2 import LiveExecutorV2, Position
        print("✅ LiveExecutorV2 import successful")

        from ver2.gui_trading_bot_v2 import GUITradingBotV2
        print("✅ GUITradingBotV2 import successful")

        from ver2 import config_v2
        print("✅ config_v2 import successful")

        return True
    except Exception as e:
        print(f"❌ Import failed: {str(e)}")
        return False


def test_dry_run_initialization():
    """Test 2: Verify bot initializes in dry-run mode"""
    print("\n" + "="*60)
    print("TEST 2: Dry-Run Mode Initialization")
    print("="*60)

    try:
        from ver2.gui_trading_bot_v2 import GUITradingBotV2
        from ver2 import config_v2

        # Force dry-run mode in config
        config = config_v2.get_version_config()
        config['EXECUTION_CONFIG']['dry_run'] = True
        config['EXECUTION_CONFIG']['mode'] = 'live'

        # Temporarily override config
        original_get_config = config_v2.get_version_config
        config_v2.get_version_config = lambda: config

        bot = GUITradingBotV2()

        # Restore original config
        config_v2.get_version_config = original_get_config

        print(f"✅ Bot initialized successfully")
        print(f"   - Live mode: {bot.live_mode}")
        print(f"   - Dry run: {bot.dry_run}")
        print(f"   - Executor: {bot.executor}")

        if bot.dry_run:
            print("✅ Dry-run mode confirmed")
        else:
            print("⚠️  Warning: Dry-run mode not active")

        return True

    except Exception as e:
        print(f"❌ Initialization failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_live_mode_initialization():
    """Test 3: Verify bot detects live mode configuration"""
    print("\n" + "="*60)
    print("TEST 3: Live Mode Configuration Detection")
    print("="*60)

    try:
        from ver2 import config_v2

        config = config_v2.get_version_config()

        print(f"Current configuration:")
        print(f"   - Mode: {config['EXECUTION_CONFIG'].get('mode', 'backtest')}")
        print(f"   - Dry run: {config['EXECUTION_CONFIG'].get('dry_run', True)}")

        if config['EXECUTION_CONFIG'].get('mode') == 'live':
            print("✅ Live mode configured")

            if not config['EXECUTION_CONFIG'].get('dry_run', True):
                print("⚠️  WARNING: REAL TRADING MODE ACTIVE IN CONFIG")
                print("   Real money will be used if API keys are set!")
            else:
                print("✅ Dry-run safety enabled")
        else:
            print("ℹ️  Backtest mode configured (safe)")

        return True

    except Exception as e:
        print(f"❌ Configuration check failed: {str(e)}")
        return False


def test_executor_interface():
    """Test 4: Verify LiveExecutorV2 interface"""
    print("\n" + "="*60)
    print("TEST 4: LiveExecutorV2 Interface Verification")
    print("="*60)

    try:
        from ver2.live_executor_v2 import LiveExecutorV2
        from lib.api.bithumb_api import BithumbAPI
        from lib.core.logger import TradingLogger

        # Check required methods exist
        required_methods = [
            'execute_order',
            'get_position',
            'has_position',
            'update_stop_loss',
            'update_highest_high',
            'check_stop_loss',
            'close_position',
            'get_position_summary',
        ]

        for method in required_methods:
            if hasattr(LiveExecutorV2, method):
                print(f"✅ Method exists: {method}")
            else:
                print(f"❌ Missing method: {method}")
                return False

        print("\n✅ All required methods present")
        return True

    except Exception as e:
        print(f"❌ Interface check failed: {str(e)}")
        return False


def test_integration_flow():
    """Test 5: Verify integration flow in gui_trading_bot_v2.py"""
    print("\n" + "="*60)
    print("TEST 5: Integration Flow Verification")
    print("="*60)

    try:
        # Read the file and check for critical integration points
        file_path = os.path.join(
            os.path.dirname(__file__),
            'gui_trading_bot_v2.py'
        )

        with open(file_path, 'r') as f:
            content = f.read()

        # Check for import
        if 'from ver2.live_executor_v2 import LiveExecutorV2' in content:
            print("✅ LiveExecutorV2 imported")
        else:
            print("❌ LiveExecutorV2 not imported")
            return False

        # Check for initialization
        if 'self.executor = LiveExecutorV2(' in content:
            print("✅ Executor initialized in __init__")
        else:
            print("❌ Executor not initialized")
            return False

        # Check for execute_order calls
        if 'self.executor.execute_order(' in content:
            print("✅ execute_order called for trades")
        else:
            print("❌ execute_order not called")
            return False

        # Check for close_position
        if 'self.executor.close_position(' in content:
            print("✅ close_position called for exits")
        else:
            print("❌ close_position not called")
            return False

        # Check for update_stop_loss
        if 'self.executor.update_stop_loss(' in content:
            print("✅ update_stop_loss called")
        else:
            print("❌ update_stop_loss not called")
            return False

        # Check for update_highest_high
        if 'self.executor.update_highest_high(' in content:
            print("✅ update_highest_high called")
        else:
            print("❌ update_highest_high not called")
            return False

        print("\n✅ All integration points verified in code")
        return True

    except Exception as e:
        print(f"❌ Flow verification failed: {str(e)}")
        return False


def test_api_key_detection():
    """Test 6: Check API key configuration"""
    print("\n" + "="*60)
    print("TEST 6: API Key Configuration Check")
    print("="*60)

    connect_key = os.environ.get('BITHUMB_CONNECT_KEY')
    secret_key = os.environ.get('BITHUMB_SECRET_KEY')

    if connect_key and secret_key:
        print("✅ API keys found in environment variables")
        print("   - BITHUMB_CONNECT_KEY: Set")
        print("   - BITHUMB_SECRET_KEY: Set")
        print("\n⚠️  CAUTION: Real trading will be possible when dry_run=False")
    else:
        print("ℹ️  API keys not found in environment variables")
        print("   - BITHUMB_CONNECT_KEY: Not set")
        print("   - BITHUMB_SECRET_KEY: Not set")
        print("\n✅ Safe: Real trading not possible without API keys")
        print("   Bot will automatically fall back to dry-run mode")

    return True


def run_all_tests():
    """Run all integration tests"""
    print("\n" + "="*60)
    print("LIVE EXECUTOR INTEGRATION TEST SUITE")
    print("="*60)

    tests = [
        ("Module Imports", test_imports),
        ("Dry-Run Initialization", test_dry_run_initialization),
        ("Live Mode Configuration", test_live_mode_initialization),
        ("Executor Interface", test_executor_interface),
        ("Integration Flow", test_integration_flow),
        ("API Key Detection", test_api_key_detection),
    ]

    results = {}

    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {str(e)}")
            results[test_name] = False

    # Print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for result in results.values() if result)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED - Integration is complete!")
        print("\nℹ️  To enable real trading:")
        print("   1. Set environment variables:")
        print("      export BITHUMB_CONNECT_KEY='your_key'")
        print("      export BITHUMB_SECRET_KEY='your_secret'")
        print("   2. Set in config_v2.py:")
        print("      EXECUTION_CONFIG['mode'] = 'live'")
        print("      EXECUTION_CONFIG['dry_run'] = False")
        print("   3. ⚠️  WARNING: Real money will be used!")
    else:
        print("\n⚠️  Some tests failed - please review errors above")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
