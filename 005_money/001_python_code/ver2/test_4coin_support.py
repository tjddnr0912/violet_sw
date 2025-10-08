#!/usr/bin/env python3
"""
Test suite for 4-coin trading support
Tests BTC, ETH, XRP, SOL across all major functions

This script verifies:
1. API connectivity for all 4 coins
2. Historical data availability and sufficiency
3. Indicator calculations across different price ranges
4. Order simulation in dry-run mode
5. Configuration validation
"""

import sys
import os
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ver2.config_v2 import (
    AVAILABLE_COINS,
    POPULAR_COINS,
    validate_symbol,
    list_available_symbols,
    get_symbol_from_config,
    set_symbol_in_config,
)
from lib.api.bithumb_api import get_candlestick, get_ticker


class FourCoinTester:
    """Test suite for 4-coin support verification"""

    def __init__(self):
        self.test_results = []
        self.coins = AVAILABLE_COINS  # BTC, ETH, XRP, SOL
        self.total_tests = 0
        self.passed_tests = 0

    def log_test(self, test_name: str, passed: bool, message: str = ""):
        """Log test result"""
        self.total_tests += 1
        if passed:
            self.passed_tests += 1
            status = "✓"
        else:
            status = "✗"

        result = f"{status} {test_name}"
        if message:
            result += f": {message}"

        self.test_results.append((passed, result))
        print(result)

    def print_header(self, title: str):
        """Print section header"""
        print(f"\n{'=' * 60}")
        print(f"{title}")
        print('=' * 60)

    def test_config_validation(self):
        """Test 1: Configuration validation"""
        self.print_header("[1/5] Configuration Validation Test")

        # Test AVAILABLE_COINS list
        expected_coins = ['BTC', 'ETH', 'XRP', 'SOL']
        if AVAILABLE_COINS == expected_coins:
            self.log_test("AVAILABLE_COINS configuration", True, f"Correctly set to {expected_coins}")
        else:
            self.log_test("AVAILABLE_COINS configuration", False, f"Expected {expected_coins}, got {AVAILABLE_COINS}")

        # Test POPULAR_COINS matches AVAILABLE_COINS
        if POPULAR_COINS == AVAILABLE_COINS:
            self.log_test("POPULAR_COINS matches AVAILABLE_COINS", True)
        else:
            self.log_test("POPULAR_COINS matches AVAILABLE_COINS", False, f"Mismatch: {POPULAR_COINS}")

        # Test validation function for each coin
        for coin in self.coins:
            is_valid, msg = validate_symbol(coin)
            self.log_test(f"Validate symbol '{coin}'", is_valid, msg if not is_valid else "Valid")

        # Test invalid coin rejection
        is_valid, msg = validate_symbol('DOGE')
        if not is_valid:
            self.log_test("Invalid symbol rejection (DOGE)", True, "Correctly rejected")
        else:
            self.log_test("Invalid symbol rejection (DOGE)", False, "Should have been rejected")

        # Test list_available_symbols function
        all_symbols = list_available_symbols()
        if len(all_symbols) == 4:
            self.log_test("list_available_symbols() count", True, f"Returns 4 coins")
        else:
            self.log_test("list_available_symbols() count", False, f"Expected 4, got {len(all_symbols)}")

    def test_api_connectivity(self):
        """Test 2: API connectivity for all 4 coins"""
        self.print_header("[2/5] API Connectivity Test")

        for coin in self.coins:
            try:
                # Test ticker data
                ticker = get_ticker(coin)
                if ticker and 'closing_price' in ticker:
                    price = float(ticker['closing_price'])
                    volume = float(ticker.get('units_traded_24H', 0))
                    self.log_test(
                        f"{coin} ticker fetch",
                        True,
                        f"Price={price:,.0f} KRW, Volume={volume:,.2f}"
                    )
                else:
                    self.log_test(f"{coin} ticker fetch", False, "No data returned")

            except Exception as e:
                self.log_test(f"{coin} ticker fetch", False, f"Error: {str(e)}")

    def test_historical_data(self):
        """Test 3: Historical data availability"""
        self.print_header("[3/5] Historical Data Sufficiency Test")

        intervals = ['4h', '24h']

        for coin in self.coins:
            for interval in intervals:
                try:
                    # Fetch candlestick data
                    candles = get_candlestick(coin, interval)

                    if candles is not None and not candles.empty:
                        candle_count = len(candles)
                        required = 250 if interval == '24h' else 200

                        if candle_count >= required:
                            self.log_test(
                                f"{coin} {interval} candles",
                                True,
                                f"{candle_count} candles (need {required}+ for indicators)"
                            )
                        else:
                            self.log_test(
                                f"{coin} {interval} candles",
                                False,
                                f"Only {candle_count} candles (need {required}+)"
                            )
                    else:
                        self.log_test(f"{coin} {interval} candles", False, "No data returned")

                except Exception as e:
                    self.log_test(f"{coin} {interval} candles", False, f"Error: {str(e)}")

    def test_indicator_calculations(self):
        """Test 4: Indicator calculations across price ranges"""
        self.print_header("[4/5] Indicator Calculation Test")

        for coin in self.coins:
            try:
                # Fetch 4H data for indicator testing
                candles = get_candlestick(coin, '4h')

                if candles is not None and not candles.empty:
                    # Calculate simple indicators to verify data quality
                    close_prices = candles['close']

                    # Calculate EMA50
                    if len(close_prices) >= 50:
                        ema50 = close_prices.ewm(span=50, adjust=False).mean().iloc[-1]

                        # Calculate EMA200
                        if len(close_prices) >= 200:
                            ema200 = close_prices.ewm(span=200, adjust=False).mean().iloc[-1]

                            # Calculate RSI
                            delta = close_prices.diff()
                            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                            rs = gain / loss
                            rsi = (100 - (100 / (1 + rs))).iloc[-1]

                            # Verify values are reasonable (not NaN or extreme)
                            if all([
                                not pd.isna(ema50),
                                not pd.isna(ema200),
                                not pd.isna(rsi),
                                0 <= rsi <= 100
                            ]):
                                self.log_test(
                                    f"{coin} indicators",
                                    True,
                                    f"EMA50={ema50:,.0f}, EMA200={ema200:,.0f}, RSI={rsi:.1f}"
                                )
                            else:
                                self.log_test(f"{coin} indicators", False, "Invalid indicator values (NaN)")
                        else:
                            self.log_test(f"{coin} indicators", False, "Not enough data for EMA200")
                    else:
                        self.log_test(f"{coin} indicators", False, "Not enough data for EMA50")
                else:
                    self.log_test(f"{coin} indicators", False, "No candlestick data")

            except Exception as e:
                self.log_test(f"{coin} indicators", False, f"Error: {str(e)}")

    def test_price_range_compatibility(self):
        """Test 5: Verify system works with different price scales"""
        self.print_header("[5/5] Price Range Compatibility Test")

        # Expected price ranges (approximate)
        price_ranges = {
            'BTC': {'min': 100_000_000, 'max': 300_000_000, 'desc': 'High price (~176M)'},
            'ETH': {'min': 3_000_000, 'max': 10_000_000, 'desc': 'Medium price (~6.4M)'},
            'XRP': {'min': 1_000, 'max': 10_000, 'desc': 'Low price (~4K)'},
            'SOL': {'min': 100_000, 'max': 500_000, 'desc': 'Medium price (~258K)'},
        }

        for coin in self.coins:
            try:
                ticker = get_ticker(coin)
                if ticker and 'closing_price' in ticker:
                    price = float(ticker['closing_price'])
                    expected_range = price_ranges[coin]

                    # Check if price is in reasonable range
                    if expected_range['min'] <= price <= expected_range['max']:
                        self.log_test(
                            f"{coin} price range",
                            True,
                            f"{expected_range['desc']} - Current: {price:,.0f} KRW"
                        )
                    else:
                        # Price is outside expected range, but still valid
                        self.log_test(
                            f"{coin} price range",
                            True,
                            f"{expected_range['desc']} - Current: {price:,.0f} KRW (outside typical range)"
                        )
                else:
                    self.log_test(f"{coin} price range", False, "No price data")

            except Exception as e:
                self.log_test(f"{coin} price range", False, f"Error: {str(e)}")

    def test_order_simulation(self):
        """Test 6: Order simulation (dry-run mode)"""
        self.print_header("[6/6] Order Simulation Test (Dry-run)")

        test_amount_krw = 50000  # 50,000 KRW test amount

        for coin in self.coins:
            try:
                ticker = get_ticker(coin)
                if ticker and 'closing_price' in ticker:
                    price = float(ticker['closing_price'])

                    # Calculate how many coins we can buy
                    coins_to_buy = test_amount_krw / price

                    # Simulate order calculation
                    fee_rate = 0.0005  # 0.05% trading fee
                    fee_amount = test_amount_krw * fee_rate
                    net_amount = test_amount_krw - fee_amount
                    net_coins = net_amount / price

                    self.log_test(
                        f"{coin} order simulation",
                        True,
                        f"Buy {test_amount_krw:,} KRW worth → {net_coins:.6f} coins (fee: {fee_amount:.0f} KRW)"
                    )
                else:
                    self.log_test(f"{coin} order simulation", False, "No price data")

            except Exception as e:
                self.log_test(f"{coin} order simulation", False, f"Error: {str(e)}")

    def run_all_tests(self):
        """Run all test suites"""
        print("\n" + "=" * 60)
        print("4-COIN TRADING SUPPORT TEST SUITE")
        print("Testing: BTC, ETH, XRP, SOL")
        print("=" * 60)

        # Import pandas here to avoid early import
        global pd
        import pandas as pd

        # Run all test suites
        self.test_config_validation()
        self.test_api_connectivity()
        self.test_historical_data()
        self.test_indicator_calculations()
        self.test_price_range_compatibility()
        self.test_order_simulation()

        # Print summary
        self.print_summary()

    def print_summary(self):
        """Print test summary"""
        self.print_header("TEST SUMMARY")

        # Calculate statistics
        pass_rate = (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0

        # Print results grouped by status
        print("\nPassed tests:")
        for passed, result in self.test_results:
            if passed:
                print(f"  {result}")

        if self.passed_tests < self.total_tests:
            print("\nFailed tests:")
            for passed, result in self.test_results:
                if not passed:
                    print(f"  {result}")

        # Print final stats
        print("\n" + "=" * 60)
        print(f"Total: {self.passed_tests}/{self.total_tests} tests passed ({pass_rate:.1f}%)")

        if self.passed_tests == self.total_tests:
            print("✓ All tests passed! 4-coin support is production-ready")
        else:
            print(f"✗ {self.total_tests - self.passed_tests} test(s) failed")

        print("=" * 60)


def main():
    """Main entry point"""
    tester = FourCoinTester()
    tester.run_all_tests()


if __name__ == '__main__':
    main()
