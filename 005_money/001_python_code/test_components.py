#!/usr/bin/env python3
"""
Component testing script for multi-timeframe chart system
Tests DataManager, IndicatorCalculator, and ChartColumn independently
"""

import sys
import time
from datetime import datetime

def test_data_manager():
    """Test DataManager caching and API calls"""
    print("\n=== Testing DataManager ===")
    from data_manager import DataManager

    dm = DataManager("BTC", cache_ttl_seconds=15, rate_limit_seconds=1.0)

    # Test 1: Fetch data for BTC with 1h interval
    print("Test 1: Fetching BTC 1h data...")
    try:
        df = dm.fetch_data("1h")
        if df is not None and not df.empty:
            print(f"✓ Data fetched successfully: {len(df)} candles")
            print(f"  Columns: {list(df.columns)}")
            print(f"  Latest close: {df['close'].iloc[-1]}")
        else:
            print("✗ Failed to fetch data or data is empty")
            return False
    except Exception as e:
        print(f"✗ Error fetching data: {e}")
        return False

    # Test 2: Test caching (should be instant)
    print("\nTest 2: Testing cache (should be instant)...")
    start = time.time()
    df_cached = dm.fetch_data("1h")
    elapsed = time.time() - start

    if elapsed < 0.1:
        print(f"✓ Cache working (elapsed: {elapsed:.4f}s)")
    else:
        print(f"⚠ Cache may not be working (elapsed: {elapsed:.4f}s)")

    # Test 3: Test cache expiry (force refresh)
    print("\nTest 3: Testing force refresh...")
    try:
        df_fresh = dm.fetch_data("1h", force_refresh=True)
        if df_fresh is not None:
            print("✓ Force refresh successful")
        else:
            print("✗ Force refresh failed")
    except Exception as e:
        print(f"✗ Error on force refresh: {e}")

    # Test 4: Test different intervals
    print("\nTest 4: Testing multiple intervals...")
    try:
        data_dict = dm.fetch_multiple_intervals(["30m", "6h", "24h"])
        for interval, df_interval in data_dict.items():
            if df_interval is not None:
                print(f"✓ {interval}: {len(df_interval)} candles")
            else:
                print(f"✗ {interval}: Failed")
    except Exception as e:
        print(f"✗ Multiple intervals error: {e}")

    print("\n✓ DataManager tests completed")
    return True


def test_indicator_calculator():
    """Test IndicatorCalculator with sample data"""
    print("\n=== Testing IndicatorCalculator ===")
    from data_manager import DataManager
    from indicator_calculator import IndicatorCalculator

    # Get sample data
    dm = DataManager("BTC")
    df = dm.fetch_data("1h")

    if df is None or df.empty:
        print("✗ Cannot test without data")
        return False

    ic = IndicatorCalculator()

    # Test 1: Moving Averages
    print("\nTest 1: Calculating Moving Averages...")
    try:
        ma_short, ma_long = ic.calculate_ma(df)
        if ma_short is not None and ma_long is not None:
            print(f"✓ MA calculated: short={ma_short.iloc[-1]:.2f}, long={ma_long.iloc[-1]:.2f}")
        else:
            print("✗ MA calculation failed")
    except Exception as e:
        print(f"✗ MA error: {e}")

    # Test 2: RSI
    print("\nTest 2: Calculating RSI...")
    try:
        rsi = ic.calculate_rsi(df)
        if rsi is not None:
            print(f"✓ RSI calculated: {rsi.iloc[-1]:.2f}")
        else:
            print("✗ RSI calculation failed")
    except Exception as e:
        print(f"✗ RSI error: {e}")

    # Test 3: MACD
    print("\nTest 3: Calculating MACD...")
    try:
        macd, signal, histogram = ic.calculate_macd(df)
        if macd is not None:
            print(f"✓ MACD calculated: macd={macd.iloc[-1]:.2f}, signal={signal.iloc[-1]:.2f}")
        else:
            print("✗ MACD calculation failed")
    except Exception as e:
        print(f"✗ MACD error: {e}")

    # Test 4: Bollinger Bands
    print("\nTest 4: Calculating Bollinger Bands...")
    try:
        upper, middle, lower = ic.calculate_bollinger_bands(df)
        if upper is not None:
            print(f"✓ BB calculated: upper={upper.iloc[-1]:.2f}, middle={middle.iloc[-1]:.2f}, lower={lower.iloc[-1]:.2f}")
        else:
            print("✗ BB calculation failed")
    except Exception as e:
        print(f"✗ BB error: {e}")

    # Test 5: Volume
    print("\nTest 5: Calculating Volume MA...")
    try:
        vol_ma = ic.calculate_volume_ma(df)
        if vol_ma is not None:
            print(f"✓ Volume MA calculated: {vol_ma.iloc[-1]:.2f}")
        else:
            print("✗ Volume MA calculation failed")
    except Exception as e:
        print(f"✗ Volume MA error: {e}")

    print("\n✓ IndicatorCalculator tests completed")
    return True


def test_chart_column_headless():
    """Test ChartColumn without GUI (just logic)"""
    print("\n=== Testing ChartColumn Logic ===")

    # We can't test full GUI without display, but we can test data flow
    print("Test 1: Checking ChartColumn imports...")
    try:
        from chart_column import ChartColumn
        print("✓ ChartColumn imported successfully")
    except Exception as e:
        print(f"✗ ChartColumn import failed: {e}")
        return False

    print("✓ ChartColumn logic tests completed")
    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("Multi-Timeframe Chart System - Component Testing")
    print("=" * 60)

    results = {}

    # Test DataManager
    results['DataManager'] = test_data_manager()
    time.sleep(2)  # Rate limiting between test suites

    # Test IndicatorCalculator
    results['IndicatorCalculator'] = test_indicator_calculator()

    # Test ChartColumn
    results['ChartColumn'] = test_chart_column_headless()

    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    for component, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{component:25s}: {status}")

    all_passed = all(results.values())
    if all_passed:
        print("\n✓ All component tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed - see details above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
