#!/usr/bin/env python3
"""
Debug script to analyze stop-loss calculation issues.

This script tests the Chandelier Exit calculation and identifies
why stop-loss prices are higher than entry prices.
"""

import sys
import pandas as pd
from pathlib import Path

# Add parent directory to path
base_path = Path(__file__).parent.parent
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

from lib.api.bithumb_api import get_candlestick, get_ticker
from ver2.strategy_v2 import StrategyV2
from ver3.config_v3 import get_version_config


def test_stop_loss_calculation(ticker: str):
    """
    Test stop-loss calculation for a specific ticker.

    Args:
        ticker: Cryptocurrency symbol (e.g., 'ETH', 'XRP')
    """
    print("=" * 80)
    print(f"STOP-LOSS CALCULATION DEBUG FOR {ticker}")
    print("=" * 80)

    # Get config and strategy
    config = get_version_config()
    strategy = StrategyV2(config, None)

    # Get current price
    ticker_data = get_ticker(ticker)
    if not ticker_data:
        print(f"❌ Failed to get ticker data for {ticker}")
        return

    current_price = float(ticker_data.get('closing_price', 0))
    print(f"\n📊 Current Price: {current_price:,.0f} KRW")

    # Get 4H candlestick data
    print(f"\n📥 Fetching 4H candlestick data for {ticker}...")
    df = get_candlestick(ticker, '4h')

    if df is None or len(df) == 0:
        print(f"❌ Failed to get candlestick data")
        return

    print(f"✅ Loaded {len(df)} candles")

    # Calculate ATR using strategy's method
    print("\n⚙️  Calculating ATR...")
    atr_series = strategy._calculate_atr(df)

    if atr_series is None or len(atr_series) == 0:
        print(f"❌ Failed to calculate ATR")
        return

    # Add ATR to dataframe
    df['atr'] = atr_series
    latest_atr = df['atr'].iloc[-1]
    print(f"\n📈 Technical Indicators:")
    print(f"   ATR (14): {latest_atr:,.2f} KRW")

    # Get highest high over ATR period
    atr_period = 14
    highest_high = df['high'].iloc[-atr_period:].max()
    print(f"   Highest High (14 candles): {highest_high:,.0f} KRW")

    # Calculate Chandelier Exit
    multiplier = 3.0
    chandelier_stop = highest_high - (latest_atr * multiplier)

    print(f"\n🧮 Chandelier Exit Calculation:")
    print(f"   Formula: Highest High - (ATR × Multiplier)")
    print(f"   Calculation: {highest_high:,.0f} - ({latest_atr:,.2f} × {multiplier})")
    print(f"   Calculated Stop-Loss: {chandelier_stop:,.0f} KRW")

    # Calculate percentage from current price
    pct_from_current = ((chandelier_stop - current_price) / current_price) * 100

    print(f"\n📊 Stop-Loss Analysis:")
    print(f"   Current Price: {current_price:,.0f} KRW")
    print(f"   Stop-Loss:     {chandelier_stop:,.0f} KRW")
    print(f"   Difference:    {pct_from_current:+.2f}%")

    if chandelier_stop > current_price:
        print(f"\n❌ ERROR: Stop-loss ({chandelier_stop:,.0f}) is HIGHER than current price ({current_price:,.0f})")
        print(f"   This means stop-loss will trigger immediately or won't work!")
    elif chandelier_stop < current_price * 0.95:
        print(f"\n✅ NORMAL: Stop-loss is {abs(pct_from_current):.2f}% below current price")
    else:
        print(f"\n⚠️  WARNING: Stop-loss is very close to current price")

    # Test strategy's _calculate_chandelier_stop() method
    print(f"\n🔍 Testing StrategyV2._calculate_chandelier_stop()...")
    strategy_stop = strategy._calculate_chandelier_stop(df)
    print(f"   Strategy Result: {strategy_stop:,.0f} KRW")

    if abs(strategy_stop - chandelier_stop) > 1:
        print(f"   ❌ MISMATCH: Strategy calculation differs from manual calculation")
        print(f"      Manual:   {chandelier_stop:,.0f}")
        print(f"      Strategy: {strategy_stop:,.0f}")
        print(f"      Diff:     {strategy_stop - chandelier_stop:,.0f}")
    else:
        print(f"   ✅ MATCH: Strategy calculation is correct")

    # Test full analysis
    print(f"\n🔍 Testing full analyze_market()...")
    result = strategy.analyze_market(ticker, interval='4h')

    if result:
        stop_from_analysis = result.get('stop_loss_price', 0)
        print(f"   Analysis stop_loss_price: {stop_from_analysis:,.0f} KRW")

        if stop_from_analysis > current_price:
            print(f"   ❌ BUG FOUND: analyze_market() returns stop-loss HIGHER than current price!")
            print(f"      This is the root cause of the issue.")
        elif abs(stop_from_analysis - chandelier_stop) > 1:
            print(f"   ⚠️  WARNING: analyze_market() stop-loss differs from calculated value")
            print(f"      Expected: {chandelier_stop:,.0f}")
            print(f"      Got:      {stop_from_analysis:,.0f}")
        else:
            print(f"   ✅ OK: analyze_market() returns correct stop-loss")

    print("\n" + "=" * 80)


def main():
    """Main function."""
    print("\n🔍 STOP-LOSS CALCULATION DEBUGGER\n")

    # Test for current holdings
    tickers = ['ETH', 'XRP']

    for ticker in tickers:
        try:
            test_stop_loss_calculation(ticker)
            print("\n")
        except Exception as e:
            print(f"\n❌ Error testing {ticker}: {e}")
            import traceback
            traceback.print_exc()
            print("\n")

    print("=" * 80)
    print("DEBUG COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
