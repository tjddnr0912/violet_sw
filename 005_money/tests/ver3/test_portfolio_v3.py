"""
Test Suite for Portfolio Manager V3

This module contains comprehensive tests for the multi-coin portfolio
trading system.

Run:
    python -m ver3.test_portfolio_v3

Or from project root:
    cd /Users/seongwookjang/project/git/violet_sw/005_money
    python 001_python_code/ver3/test_portfolio_v3.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ver3.portfolio_manager_v3 import PortfolioManagerV3
from ver3.config_v3 import get_version_config
from lib.api.bithumb_api import BithumbAPI
from lib.core.logger import TradingLogger


def test_configuration():
    """Test 1: Configuration Loading"""
    print("=" * 60)
    print("TEST 1: Configuration Loading")
    print("=" * 60)

    try:
        config = get_version_config()

        # Check portfolio config exists
        assert 'PORTFOLIO_CONFIG' in config, "PORTFOLIO_CONFIG missing"

        portfolio_config = config['PORTFOLIO_CONFIG']

        # Validate portfolio settings
        assert portfolio_config.get('max_positions', 0) >= 1, "max_positions must be >= 1"
        assert len(portfolio_config.get('default_coins', [])) >= 1, "Must have at least 1 default coin"

        print("✅ Configuration loaded successfully")
        print(f"   Default coins: {portfolio_config.get('default_coins')}")
        print(f"   Max positions: {portfolio_config.get('max_positions')}")
        print(f"   Parallel analysis: {portfolio_config.get('parallel_analysis')}")

        return True

    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_portfolio_manager_init():
    """Test 2: Portfolio Manager Initialization"""
    print("\n" + "=" * 60)
    print("TEST 2: Portfolio Manager Initialization")
    print("=" * 60)

    try:
        config = get_version_config()
        api = BithumbAPI()  # No keys needed for dry-run
        logger = TradingLogger(log_dir='logs')

        test_coins = ['BTC', 'ETH', 'XRP']

        # Create portfolio manager
        pm = PortfolioManagerV3(
            coins=test_coins,
            config=config,
            api=api,
            logger=logger
        )

        # Verify monitors created
        assert len(pm.monitors) == 3, f"Expected 3 monitors, got {len(pm.monitors)}"

        # Verify each coin has a monitor
        for coin in test_coins:
            assert coin in pm.monitors, f"Monitor for {coin} not found"

        print("✅ Portfolio Manager initialized successfully")
        print(f"   Coins monitored: {test_coins}")
        print(f"   Monitors created: {len(pm.monitors)}")

        return True

    except Exception as e:
        print(f"❌ Portfolio Manager init test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_parallel_analysis():
    """Test 3: Parallel Coin Analysis"""
    print("\n" + "=" * 60)
    print("TEST 3: Parallel Coin Analysis")
    print("=" * 60)

    try:
        config = get_version_config()
        config['EXECUTION_CONFIG']['dry_run'] = True  # Force dry-run

        api = BithumbAPI()
        logger = TradingLogger(log_dir='logs')

        test_coins = ['BTC', 'ETH']

        pm = PortfolioManagerV3(
            coins=test_coins,
            config=config,
            api=api,
            logger=logger
        )

        print(f"\nAnalyzing {len(test_coins)} coins in parallel...")

        # Analyze all coins
        results = pm.analyze_all()

        # Verify results for each coin
        assert len(results) == len(test_coins), f"Expected {len(test_coins)} results, got {len(results)}"

        for coin in test_coins:
            assert coin in results, f"Result for {coin} not found"

            result = results[coin]
            assert 'action' in result, f"{coin}: 'action' missing from result"
            assert 'entry_score' in result, f"{coin}: 'entry_score' missing"
            assert 'market_regime' in result, f"{coin}: 'market_regime' missing"

            print(f"\n✅ {coin} Analysis:")
            print(f"   Regime: {result.get('market_regime', '?')}")
            print(f"   Action: {result.get('action', '?')}")
            print(f"   Entry Score: {result.get('entry_score', 0)}/4")
            print(f"   Signal Strength: {result.get('signal_strength', 0):.2f}")

        print("\n✅ Parallel analysis completed successfully")

        return True

    except Exception as e:
        print(f"❌ Parallel analysis test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_portfolio_decision():
    """Test 4: Portfolio Decision Logic"""
    print("\n" + "=" * 60)
    print("TEST 4: Portfolio Decision Logic")
    print("=" * 60)

    try:
        config = get_version_config()
        config['EXECUTION_CONFIG']['dry_run'] = True
        config['PORTFOLIO_CONFIG']['max_positions'] = 2  # Limit for testing

        api = BithumbAPI()
        logger = TradingLogger(log_dir='logs')

        test_coins = ['BTC', 'ETH', 'XRP']

        pm = PortfolioManagerV3(
            coins=test_coins,
            config=config,
            api=api,
            logger=logger
        )

        # Analyze coins
        results = pm.analyze_all()

        print("\nAnalysis Results:")
        for coin, result in results.items():
            print(f"  {coin}: {result.get('action')} (score: {result.get('entry_score')}/4)")

        # Make portfolio decisions
        decisions = pm.make_portfolio_decision(results)

        print(f"\nPortfolio Decisions: {len(decisions)} actions")
        for coin, action, entry_number in decisions:
            if entry_number > 1:
                print(f"  {action}: {coin} (Pyramid #{entry_number})")
            else:
                print(f"  {action}: {coin}")

        # Verify portfolio limits respected
        buy_decisions = [d for d in decisions if d[1] == 'BUY']
        assert len(buy_decisions) <= config['PORTFOLIO_CONFIG']['max_positions'], \
            f"Too many buy decisions: {len(buy_decisions)}"

        print(f"\n✅ Portfolio decision logic working correctly")
        print(f"   Max positions: {config['PORTFOLIO_CONFIG']['max_positions']}")
        print(f"   Entry decisions: {len(buy_decisions)}")

        return True

    except Exception as e:
        print(f"❌ Portfolio decision test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_portfolio_summary():
    """Test 5: Portfolio Summary"""
    print("\n" + "=" * 60)
    print("TEST 5: Portfolio Summary")
    print("=" * 60)

    try:
        config = get_version_config()
        config['EXECUTION_CONFIG']['dry_run'] = True

        api = BithumbAPI()
        logger = TradingLogger(log_dir='logs')

        test_coins = ['BTC', 'ETH']

        pm = PortfolioManagerV3(
            coins=test_coins,
            config=config,
            api=api,
            logger=logger
        )

        # Get summary
        summary = pm.get_portfolio_summary()

        # Verify summary structure
        assert 'total_positions' in summary, "total_positions missing"
        assert 'max_positions' in summary, "max_positions missing"
        assert 'total_pnl_krw' in summary, "total_pnl_krw missing"
        assert 'coins' in summary, "coins dict missing"

        print("✅ Portfolio Summary Generated:")
        print(f"   Total Positions: {summary['total_positions']}/{summary['max_positions']}")
        print(f"   Total P&L: {summary['total_pnl_krw']:,.0f} KRW")
        print(f"   Coins Tracked: {len(summary['coins'])}")

        for coin, data in summary['coins'].items():
            print(f"\n   [{coin}]")
            analysis = data.get('analysis', {})
            print(f"     Regime: {analysis.get('market_regime', '?')}")
            print(f"     Score: {analysis.get('entry_score', 0)}/4")

        return True

    except Exception as e:
        print(f"❌ Portfolio summary test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ver3_bot():
    """Test 6: TradingBotV3 Initialization"""
    print("\n" + "=" * 60)
    print("TEST 6: TradingBotV3 Initialization")
    print("=" * 60)

    try:
        from ver3.trading_bot_v3 import TradingBotV3
        from ver3.config_v3 import get_version_config

        config = get_version_config()
        config['EXECUTION_CONFIG']['dry_run'] = True

        # Create bot
        bot = TradingBotV3(config)

        # Verify bot properties
        assert bot.VERSION_NAME == "ver3", "Incorrect version name"
        assert len(bot.coins) >= 1, "No coins configured"
        assert bot.portfolio_manager is not None, "Portfolio manager not initialized"

        print("✅ TradingBotV3 initialized successfully")
        print(f"   Version: {bot.VERSION_NAME}")
        print(f"   Display Name: {bot.VERSION_DISPLAY_NAME}")
        print(f"   Coins: {', '.join(bot.coins)}")
        print(f"   Max Positions: {bot.portfolio_config.get('max_positions')}")

        # Test version info
        version_info = bot.get_version_info()
        print(f"\n   Version Info Keys: {list(version_info.keys())}")

        return True

    except Exception as e:
        print(f"❌ TradingBotV3 test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all tests"""
    print("\n")
    print("*" * 60)
    print(" PORTFOLIO MANAGER V3 TEST SUITE")
    print("*" * 60)

    tests = [
        ("Configuration Loading", test_configuration),
        ("Portfolio Manager Init", test_portfolio_manager_init),
        ("Parallel Analysis", test_parallel_analysis),
        ("Portfolio Decision Logic", test_portfolio_decision),
        ("Portfolio Summary", test_portfolio_summary),
        ("TradingBotV3 Initialization", test_ver3_bot),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ Test '{test_name}' crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "-" * 60)
    print(f"Total: {passed}/{total} tests passed")
    print("-" * 60)

    if passed == total:
        print("\n🎉 All tests passed! Ver3 is ready for deployment.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please fix before deploying.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
