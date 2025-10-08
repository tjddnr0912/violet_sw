"""
Score Calculation Diagnostic Tool

This script diagnoses why the live bot is getting 0 points while backtest shows activity.
It checks:
1. Data fetching (is data available?)
2. Indicator calculation (are indicators being calculated correctly?)
3. Score component evaluation (which components are failing?)
4. Real-time vs backtest comparison
"""

import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os

# Add paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../pybithumb')))

from pybithumb import get_candlestick as pybithumb_get_candlestick

# lib method not available, use only pybithumb
lib_get_candlestick = None


def get_candlestick_safe(symbol: str, interval: str, method: str = 'pybithumb') -> pd.DataFrame:
    """Fetch candlestick data with fallback"""
    try:
        if method == 'pybithumb':
            df = pybithumb_get_candlestick(symbol, "KRW", interval)
            if df is None:
                return None
            df = df.reset_index()
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        else:
            if lib_get_candlestick is None:
                return None
            df = lib_get_candlestick(symbol, interval)

        if df is not None:
            df = df.sort_values('timestamp')

        return df
    except Exception as e:
        print(f"Error fetching {method} data: {e}")
        return None


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate indicators exactly as gui_trading_bot_v2.py does"""
    # Bollinger Bands
    df['bb_mid'] = df['close'].rolling(window=20).mean()
    df['bb_std'] = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * 2.0)
    df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2.0)

    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # Stochastic RSI
    rsi = df['rsi']
    rsi_min = rsi.rolling(window=14).min()
    rsi_max = rsi.rolling(window=14).max()
    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min) * 100
    df['stoch_k'] = stoch_rsi.rolling(window=3).mean()
    df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()

    # ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr'] = true_range.rolling(window=14).mean()

    return df


def diagnose_score_components(df: pd.DataFrame) -> dict:
    """Diagnose each score component"""
    if df is None or len(df) < 50:
        return {'error': 'Insufficient data'}

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    diagnosis = {
        'timestamp': latest['timestamp'],
        'price': latest['close'],
        'bb_touch': {},
        'rsi_oversold': {},
        'stoch_cross': {},
        'total_score': 0
    }

    # Component 1: BB Touch
    bb_lower = latest['bb_lower']
    low_price = latest['low']

    diagnosis['bb_touch'] = {
        'score': 1 if low_price <= bb_lower else 0,
        'low_price': low_price,
        'bb_lower': bb_lower,
        'distance': low_price - bb_lower,
        'distance_pct': ((low_price - bb_lower) / bb_lower) * 100 if bb_lower > 0 else 0,
        'passes': low_price <= bb_lower,
        'issue': None if not pd.isna(bb_lower) else 'BB Lower is NaN'
    }

    # Component 2: RSI Oversold
    rsi = latest['rsi']
    diagnosis['rsi_oversold'] = {
        'score': 1 if rsi < 30 else 0,
        'rsi': rsi,
        'threshold': 30,
        'distance': rsi - 30,
        'passes': rsi < 30,
        'issue': None if not pd.isna(rsi) else 'RSI is NaN'
    }

    # Component 3: Stoch Cross
    k_curr = latest['stoch_k']
    k_prev = prev['stoch_k']
    d_curr = latest['stoch_d']
    d_prev = prev['stoch_d']

    crossover = (k_prev < d_prev) and (k_curr > d_curr)
    in_oversold = (k_curr < 20) and (d_curr < 20)
    stoch_passes = crossover and in_oversold

    diagnosis['stoch_cross'] = {
        'score': 2 if stoch_passes else 0,
        'stoch_k_curr': k_curr,
        'stoch_k_prev': k_prev,
        'stoch_d_curr': d_curr,
        'stoch_d_prev': d_prev,
        'crossover': crossover,
        'in_oversold': in_oversold,
        'passes': stoch_passes,
        'issue': None if not any(pd.isna([k_curr, k_prev, d_curr, d_prev])) else 'Stoch values contain NaN'
    }

    # Total score
    diagnosis['total_score'] = (
        diagnosis['bb_touch']['score'] +
        diagnosis['rsi_oversold']['score'] +
        diagnosis['stoch_cross']['score']
    )

    return diagnosis


def check_regime(df_daily: pd.DataFrame) -> dict:
    """Check regime filter"""
    if df_daily is None or len(df_daily) < 200:
        return {'regime': 'ERROR', 'error': 'Insufficient daily data'}

    df_daily = df_daily.sort_values('timestamp')
    closes = df_daily['close'].values

    ema_50 = pd.Series(closes).ewm(span=50, adjust=False).mean().values
    ema_200 = pd.Series(closes).ewm(span=200, adjust=False).mean().values

    latest_ema50 = ema_50[-1]
    latest_ema200 = ema_200[-1]

    regime = 'BULLISH' if latest_ema50 > latest_ema200 else 'BEARISH'

    return {
        'regime': regime,
        'ema50': latest_ema50,
        'ema200': latest_ema200,
        'diff': latest_ema50 - latest_ema200,
        'diff_pct': ((latest_ema50 - latest_ema200) / latest_ema200) * 100
    }


def print_diagnosis():
    """Run comprehensive diagnosis"""
    print("=" * 100)
    print("🔍 V2 STRATEGY SCORE DIAGNOSTIC TOOL")
    print("=" * 100)
    print(f"\nCurrent time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Test 1: Fetch daily data for regime
    print("\n" + "="*100)
    print("TEST 1: Daily Data & Regime Filter")
    print("="*100)

    df_daily_pyb = get_candlestick_safe('BTC', '24h', 'pybithumb')
    df_daily_lib = get_candlestick_safe('BTC', '24h', 'lib')

    print(f"  pybithumb: {len(df_daily_pyb) if df_daily_pyb is not None else 'FAILED'} candles")
    print(f"  lib method: {len(df_daily_lib) if df_daily_lib is not None else 'FAILED'} candles")

    df_daily = df_daily_pyb if df_daily_pyb is not None else df_daily_lib

    if df_daily is not None:
        regime_info = check_regime(df_daily)
        print(f"\n  Regime: {regime_info['regime']}")
        print(f"  EMA50:  {regime_info.get('ema50', 0):>15,.0f}")
        print(f"  EMA200: {regime_info.get('ema200', 0):>15,.0f}")
        print(f"  Diff:   {regime_info.get('diff', 0):>15,.0f} ({regime_info.get('diff_pct', 0):>6.2f}%)")

        if regime_info['regime'] != 'BULLISH':
            print(f"\n  ⚠️  WARNING: Regime is {regime_info['regime']} - NO entry signals will be generated!")
    else:
        print("  ❌ FAILED to fetch daily data - regime filter cannot work!")

    # Test 2: Fetch 4H data
    print("\n" + "="*100)
    print("TEST 2: 4H Data & Indicators")
    print("="*100)

    df_4h_pyb = get_candlestick_safe('BTC', '4h', 'pybithumb')
    df_4h_lib = get_candlestick_safe('BTC', '4h', 'lib')

    print(f"  pybithumb: {len(df_4h_pyb) if df_4h_pyb is not None else 'FAILED'} candles")
    print(f"  lib method: {len(df_4h_lib) if df_4h_lib is not None else 'FAILED'} candles")

    df_4h = df_4h_pyb if df_4h_pyb is not None else df_4h_lib

    if df_4h is None:
        print("  ❌ FAILED to fetch 4H data!")
        return

    # Calculate indicators
    print("\n  Calculating indicators...")
    df_4h = calculate_indicators(df_4h)

    # Check for NaN values
    latest = df_4h.iloc[-1]
    nan_indicators = []
    for col in ['bb_lower', 'bb_mid', 'bb_upper', 'rsi', 'stoch_k', 'stoch_d', 'atr']:
        if col in latest and pd.isna(latest[col]):
            nan_indicators.append(col)

    if nan_indicators:
        print(f"  ⚠️  WARNING: NaN values in indicators: {nan_indicators}")
        print("     This will cause all scores to be 0!")

    # Test 3: Score diagnosis
    print("\n" + "="*100)
    print("TEST 3: Entry Score Components")
    print("="*100)

    diagnosis = diagnose_score_components(df_4h)

    print(f"\n  Timestamp: {diagnosis['timestamp']}")
    print(f"  Price:     {diagnosis['price']:>15,.0f} KRW")
    print(f"\n  {'='*80}")
    print(f"  TOTAL SCORE: {diagnosis['total_score']}/4")
    print(f"  {'='*80}")

    # Component 1: BB Touch
    bb = diagnosis['bb_touch']
    print(f"\n  [1] BB Lower Touch: {bb['score']}/1 {'✅' if bb['passes'] else '❌'}")
    print(f"      Low Price:  {bb['low_price']:>15,.0f} KRW")
    print(f"      BB Lower:   {bb['bb_lower']:>15,.0f} KRW")
    print(f"      Distance:   {bb['distance']:>15,.0f} KRW ({bb['distance_pct']:>6.2f}%)")
    if bb['issue']:
        print(f"      ⚠️  ISSUE: {bb['issue']}")
    else:
        if not bb['passes']:
            print(f"      → Price needs to drop {-bb['distance']:,.0f} KRW to touch BB lower")

    # Component 2: RSI
    rsi = diagnosis['rsi_oversold']
    print(f"\n  [2] RSI Oversold: {rsi['score']}/1 {'✅' if rsi['passes'] else '❌'}")
    print(f"      Current RSI: {rsi['rsi']:>6.2f}")
    print(f"      Threshold:   {rsi['threshold']:>6.0f}")
    print(f"      Distance:    {rsi['distance']:>6.2f}")
    if rsi['issue']:
        print(f"      ⚠️  ISSUE: {rsi['issue']}")
    else:
        if not rsi['passes']:
            print(f"      → RSI needs to drop {rsi['distance']:.2f} more")

    # Component 3: Stoch
    stoch = diagnosis['stoch_cross']
    print(f"\n  [3] Stoch RSI Cross: {stoch['score']}/2 {'✅' if stoch['passes'] else '❌'}")
    print(f"      Stoch K (prev): {stoch['stoch_k_prev']:>6.2f}")
    print(f"      Stoch K (curr): {stoch['stoch_k_curr']:>6.2f}")
    print(f"      Stoch D (prev): {stoch['stoch_d_prev']:>6.2f}")
    print(f"      Stoch D (curr): {stoch['stoch_d_curr']:>6.2f}")
    print(f"      Crossover:      {stoch['crossover']} (K crosses above D)")
    print(f"      In Oversold:    {stoch['in_oversold']} (both < 20)")
    if stoch['issue']:
        print(f"      ⚠️  ISSUE: {stoch['issue']}")
    else:
        if not stoch['crossover']:
            if stoch['stoch_k_curr'] > stoch['stoch_d_curr']:
                print(f"      → Crossover already happened, waiting for next opportunity")
            else:
                print(f"      → Waiting for K to cross above D")
        if not stoch['in_oversold']:
            print(f"      → Stoch values are not in oversold zone (< 20)")

    # Test 4: Historical score distribution
    print("\n" + "="*100)
    print("TEST 4: Recent 48H Score History")
    print("="*100)

    # Get last 48 hours (12 4H candles)
    recent_48h = df_4h.iloc[-13:].copy()  # -13 to include previous for cross detection

    score_history = []
    for i in range(1, len(recent_48h)):
        curr = recent_48h.iloc[i]
        prev = recent_48h.iloc[i-1]

        score = 0
        if curr['low'] <= curr['bb_lower']:
            score += 1
        if curr['rsi'] < 30:
            score += 1

        k_cross = (prev['stoch_k'] < prev['stoch_d']) and (curr['stoch_k'] > curr['stoch_d'])
        oversold = (curr['stoch_k'] < 20) and (curr['stoch_d'] < 20)
        if k_cross and oversold:
            score += 2

        score_history.append({
            'time': curr['timestamp'],
            'score': score,
            'bb_touch': 1 if curr['low'] <= curr['bb_lower'] else 0,
            'rsi_os': 1 if curr['rsi'] < 30 else 0,
            'stoch_cross': 2 if (k_cross and oversold) else 0
        })

    print(f"\n  {'Time':<20} {'Score':<8} {'BB':<4} {'RSI':<4} {'Stoch':<6}")
    print(f"  {'-'*44}")
    for sh in score_history:
        print(f"  {str(sh['time']):<20} {sh['score']}/4     {sh['bb_touch']:<4} {sh['rsi_os']:<4} {sh['stoch_cross']:<6}")

    score_counts = pd.DataFrame(score_history)['score'].value_counts().sort_index()
    print(f"\n  Score Distribution (last 48H):")
    for score_val in range(5):
        count = score_counts.get(score_val, 0)
        pct = (count / len(score_history)) * 100 if len(score_history) > 0 else 0
        print(f"    {score_val}/4: {count:>3} times ({pct:>5.1f}%)")

    # Summary
    print("\n" + "="*100)
    print("DIAGNOSTIC SUMMARY")
    print("="*100)

    issues_found = []

    if df_daily is None:
        issues_found.append("❌ Cannot fetch daily data - regime filter broken")
    elif regime_info['regime'] != 'BULLISH':
        issues_found.append(f"⚠️  Regime is {regime_info['regime']} - no entries allowed by strategy")

    if df_4h is None:
        issues_found.append("❌ Cannot fetch 4H data - indicators cannot be calculated")
    elif nan_indicators:
        issues_found.append(f"❌ NaN indicators: {nan_indicators} - score calculation will fail")

    if diagnosis['total_score'] == 0:
        if not issues_found:
            issues_found.append("ℹ️  Current score is 0/4 - this is normal market behavior")
            issues_found.append("   Strategy requires strong oversold conditions (3+ points)")

    max_score_48h = max([sh['score'] for sh in score_history]) if score_history else 0
    if max_score_48h == 0:
        issues_found.append("⚠️  No points scored in last 48H - market conditions may not be suitable")
    elif max_score_48h < 3:
        issues_found.append(f"⚠️  Max score in 48H was {max_score_48h}/4 - no entry signals triggered")

    if issues_found:
        print("\n  Issues Found:")
        for issue in issues_found:
            print(f"    {issue}")
    else:
        print("\n  ✅ No issues detected - system is working correctly")

    print("\n" + "="*100)


if __name__ == "__main__":
    print_diagnosis()
