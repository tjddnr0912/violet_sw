"""
Strategy Optimization for V2 - Parameter Search for 3%+ Annual Return

This script tests multiple parameter combinations to find optimal settings
that can achieve 3% or higher annual returns while maintaining acceptable risk levels.

Optimization Dimensions:
1. Entry Score Threshold (2, 3, 4 points)
2. RSI Oversold Level (25, 30, 35)
3. Stoch RSI Threshold (15, 20, 25)
4. Bollinger Band Multiplier (1.5, 2.0, 2.5)
5. Chandelier Stop Multiplier (2.0, 2.5, 3.0, 3.5)
6. Position Size (30%, 50%, 70%)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import sys
import os
from itertools import product

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../pybithumb')))

from pybithumb import get_candlestick as pybithumb_get_candlestick


def get_candlestick(symbol: str, interval: str) -> pd.DataFrame:
    """Fetch candlestick data from Bithumb."""
    try:
        df = pybithumb_get_candlestick(symbol, "KRW", interval)
        if df is None or len(df) == 0:
            return None
        df = df.reset_index()
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None


class StrategyOptimizer:
    """Optimize v2 strategy parameters for better returns."""

    def __init__(self, initial_capital: float = 10_000_000):
        self.initial_capital = initial_capital
        self.trading_fee = 0.0005

        # Parameter search space
        self.param_grid = {
            'min_entry_score': [2, 3, 4],
            'rsi_oversold': [25, 30, 35],
            'stoch_oversold': [15, 20, 25],
            'bb_std': [1.5, 2.0, 2.5],
            'chandelier_multiplier': [2.0, 2.5, 3.0, 3.5],
            'position_size_pct': [0.3, 0.5, 0.7],
        }

        # Fixed parameters
        self.bb_period = 20
        self.rsi_period = 14
        self.stoch_period = 14
        self.atr_period = 14

    def fetch_1year_data(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Fetch 1 year of historical data."""
        print("📊 Fetching 1 year of historical data...")

        daily_df = get_candlestick('BTC', '24h')
        hourly_4h_df = get_candlestick('BTC', '4h')

        if daily_df is None or hourly_4h_df is None:
            raise ValueError("Failed to fetch data")

        # Filter to last 12 months
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        daily_df = daily_df[daily_df['timestamp'] >= start_date]
        hourly_4h_df = hourly_4h_df[hourly_4h_df['timestamp'] >= start_date]

        print(f"✅ Fetched {len(daily_df)} daily candles, {len(hourly_4h_df)} 4H candles")
        return daily_df, hourly_4h_df

    def calculate_indicators(self, df: pd.DataFrame, bb_std: float) -> pd.DataFrame:
        """Calculate technical indicators with variable BB std."""
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=self.bb_period).mean()
        bb_std_dev = df['close'].rolling(window=self.bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std_dev * bb_std)
        df['bb_lower'] = df['bb_middle'] - (bb_std_dev * bb_std)

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi'] = df['rsi'].fillna(50).clip(0, 100)

        # Stochastic RSI
        rsi_min = df['rsi'].rolling(window=self.stoch_period).min()
        rsi_max = df['rsi'].rolling(window=self.stoch_period).max()
        rsi_range = (rsi_max - rsi_min).replace(0, 1e-10)
        stoch_k = 100 * (df['rsi'] - rsi_min) / rsi_range
        df['stoch_k'] = stoch_k.rolling(window=3).mean().fillna(50).clip(0, 100)
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean().fillna(50).clip(0, 100)

        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=self.atr_period).mean().fillna(0)

        return df

    def calculate_regime(self, daily_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate EMA regime."""
        daily_df['ema50'] = daily_df['close'].ewm(span=50, adjust=False).mean()
        daily_df['ema200'] = daily_df['close'].ewm(span=200, adjust=False).mean()
        daily_df['regime'] = np.where(
            daily_df['ema50'] > daily_df['ema200'],
            'bullish',
            'bearish'
        )
        return daily_df

    def calculate_entry_score(self, row: pd.Series, prev_row: pd.Series,
                             rsi_threshold: int, stoch_threshold: int) -> Tuple[int, Dict]:
        """Calculate entry score with variable thresholds."""
        score = 0
        components = {}

        # BB Touch (+1)
        if row['low'] <= row['bb_lower']:
            score += 1
            components['bb_touch'] = 1
        else:
            components['bb_touch'] = 0

        # RSI Oversold (+1)
        if row['rsi'] < rsi_threshold:
            score += 1
            components['rsi_oversold'] = 1
        else:
            components['rsi_oversold'] = 0

        # Stoch Cross (+2)
        k_cross = prev_row['stoch_k'] <= prev_row['stoch_d'] and row['stoch_k'] > row['stoch_d']
        both_below = row['stoch_k'] < stoch_threshold and row['stoch_d'] < stoch_threshold

        if k_cross and both_below:
            score += 2
            components['stoch_cross'] = 2
        else:
            components['stoch_cross'] = 0

        return score, components

    def run_backtest_with_params(self, daily_df: pd.DataFrame, exec_df: pd.DataFrame,
                                 params: Dict[str, Any]) -> Dict[str, Any]:
        """Run backtest with specific parameter set."""
        # Reset capital
        capital = self.initial_capital
        position = None
        trades = []

        # Calculate indicators with params
        daily_df = self.calculate_regime(daily_df)
        exec_df = self.calculate_indicators(exec_df, params['bb_std'])

        # Map regime to 4H
        exec_df['regime'] = exec_df['timestamp'].apply(
            lambda ts: daily_df[daily_df['timestamp'] <= ts]['regime'].iloc[-1]
            if len(daily_df[daily_df['timestamp'] <= ts]) > 0 else 'unknown'
        )

        # Simulation loop
        start_idx = max(self.bb_period, self.rsi_period, self.stoch_period) + 1

        for i in range(start_idx, len(exec_df)):
            current = exec_df.iloc[i]
            previous = exec_df.iloc[i - 1]

            if current['regime'] != 'bullish':
                continue

            # Exit logic
            if position is not None:
                exit_signal = False
                exit_price = None
                exit_reason = None

                # Chandelier stop
                lookback = exec_df.iloc[max(0, i - self.atr_period):i + 1]
                highest_high = lookback['high'].max()
                chandelier_stop = highest_high - (current['atr'] * params['chandelier_multiplier'])

                if current['low'] <= chandelier_stop:
                    exit_signal = True
                    exit_price = min(current['open'], chandelier_stop)
                    exit_reason = 'Chandelier Stop'

                # First target
                elif current['high'] >= current['bb_middle'] and not position.get('first_target_hit'):
                    exit_price = max(current['open'], current['bb_middle'])
                    partial_qty = position['quantity'] * 0.5
                    proceeds = partial_qty * exit_price * (1 - self.trading_fee)
                    capital += proceeds

                    position['quantity'] -= partial_qty
                    position['first_target_hit'] = True

                    trades.append({
                        'exit_time': current['timestamp'],
                        'exit_price': exit_price,
                        'quantity': partial_qty,
                        'pnl': proceeds - (partial_qty * position['entry_price']),
                        'exit_reason': 'Partial 50%'
                    })

                # Second target
                elif current['high'] >= current['bb_upper']:
                    exit_signal = True
                    exit_price = max(current['open'], current['bb_upper'])
                    exit_reason = 'BB Upper'

                # Full exit
                if exit_signal and position is not None:
                    qty = position['quantity']
                    proceeds = qty * exit_price * (1 - self.trading_fee)
                    capital += proceeds

                    pnl = proceeds - (qty * position['entry_price'])
                    trades.append({
                        'exit_time': current['timestamp'],
                        'exit_price': exit_price,
                        'quantity': qty,
                        'pnl': pnl,
                        'exit_reason': exit_reason
                    })

                    position = None

            # Entry logic
            if position is None:
                score, components = self.calculate_entry_score(
                    current, previous,
                    params['rsi_oversold'],
                    params['stoch_oversold']
                )

                if score >= params['min_entry_score']:
                    position_value = capital * params['position_size_pct']
                    entry_price = current['close']
                    quantity = (position_value / entry_price) * (1 - self.trading_fee)
                    cost = quantity * entry_price

                    capital -= cost
                    position = {
                        'entry_time': current['timestamp'],
                        'entry_price': entry_price,
                        'quantity': quantity,
                        'first_target_hit': False
                    }

        # Force close remaining
        if position is not None:
            final = exec_df.iloc[-1]
            qty = position['quantity']
            exit_price = final['close']
            proceeds = qty * exit_price * (1 - self.trading_fee)
            capital += proceeds

            trades.append({
                'exit_time': final['timestamp'],
                'exit_price': exit_price,
                'quantity': qty,
                'pnl': proceeds - (qty * position['entry_price']),
                'exit_reason': 'End'
            })

        # Calculate metrics
        if len(trades) == 0:
            return None

        trades_df = pd.DataFrame(trades)
        total_pnl = trades_df['pnl'].sum()
        total_return_pct = ((capital - self.initial_capital) / self.initial_capital) * 100

        winning = len(trades_df[trades_df['pnl'] > 0])
        losing = len(trades_df[trades_df['pnl'] <= 0])
        win_rate = (winning / len(trades_df) * 100) if len(trades_df) > 0 else 0

        profit_sum = trades_df[trades_df['pnl'] > 0]['pnl'].sum()
        loss_sum = abs(trades_df[trades_df['pnl'] <= 0]['pnl'].sum())
        profit_factor = (profit_sum / loss_sum) if loss_sum > 0 else float('inf')

        return {
            'params': params,
            'total_trades': len(trades_df),
            'winning_trades': winning,
            'losing_trades': losing,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'return_pct': total_return_pct,
            'profit_factor': profit_factor,
            'final_capital': capital,
        }

    def optimize(self, daily_df: pd.DataFrame, exec_df: pd.DataFrame) -> pd.DataFrame:
        """Run optimization across parameter grid."""
        results = []

        # Generate all parameter combinations
        keys = self.param_grid.keys()
        values = self.param_grid.values()
        combinations = list(product(*values))

        total = len(combinations)
        print(f"\n🔍 Testing {total} parameter combinations...")
        print("=" * 100)

        for idx, combo in enumerate(combinations, 1):
            params = dict(zip(keys, combo))

            if idx % 50 == 0:
                print(f"Progress: {idx}/{total} ({idx/total*100:.1f}%)")

            result = self.run_backtest_with_params(daily_df.copy(), exec_df.copy(), params)

            if result is not None:
                results.append(result)

        print(f"✅ Completed {len(results)} valid backtests\n")

        # Convert to DataFrame
        results_df = pd.DataFrame(results)

        # Expand params dict into columns
        params_df = pd.DataFrame(results_df['params'].tolist())
        results_df = pd.concat([params_df, results_df.drop('params', axis=1)], axis=1)

        return results_df


def print_optimization_report(results_df: pd.DataFrame, target_return: float = 3.0):
    """Print comprehensive optimization report."""
    print("=" * 100)
    print(f"📊 전략 최적화 결과 - 목표 수익률 {target_return}% 이상")
    print("=" * 100)

    # Filter for target return
    qualified = results_df[results_df['return_pct'] >= target_return].copy()

    print(f"\n✅ {target_return}% 이상 달성한 전략: {len(qualified)}/{len(results_df)} 개")

    if len(qualified) == 0:
        print(f"\n⚠️  {target_return}% 이상 수익을 낸 파라미터 조합이 없습니다.")
        print("\n📉 최고 수익률 TOP 10:")
        top10 = results_df.nlargest(10, 'return_pct')
    else:
        print("\n📈 목표 달성 전략 TOP 10 (수익률 기준):")
        top10 = qualified.nlargest(10, 'return_pct')

    print("-" * 100)
    print(f"{'순위':<6} {'수익률':<10} {'거래':<8} {'승률':<10} {'PF':<8} {'Score':<8} {'RSI':<6} {'Stoch':<8} {'BB':<6} {'Chan':<6} {'Size':<6}")
    print("-" * 100)

    for idx, row in top10.iterrows():
        print(f"{idx+1:<6} "
              f"{row['return_pct']:>8.2f}% "
              f"{row['total_trades']:>6}회 "
              f"{row['win_rate']:>8.1f}% "
              f"{row['profit_factor']:>6.2f} "
              f"{row['min_entry_score']:>6}점 "
              f"<{row['rsi_oversold']:<4} "
              f"<{row['stoch_oversold']:<6} "
              f"{row['bb_std']:<6.1f} "
              f"{row['chandelier_multiplier']:<6.1f} "
              f"{row['position_size_pct']*100:<5.0f}%")

    # Best strategy recommendation
    if len(qualified) > 0:
        best = qualified.nlargest(1, 'return_pct').iloc[0]
    else:
        best = results_df.nlargest(1, 'return_pct').iloc[0]

    print("\n" + "=" * 100)
    print("🏆 최고 성과 전략 상세")
    print("=" * 100)
    print(f"  예상 연수익률:        {best['return_pct']:>10.2f}%")
    print(f"  총 거래 횟수:          {best['total_trades']:>10} 회")
    print(f"  승률:                  {best['win_rate']:>10.2f}%")
    print(f"  Profit Factor:         {best['profit_factor']:>10.2f}")
    print(f"  최종 자본:        {best['final_capital']:>15,.0f} KRW")
    print(f"  총 손익:          {best['total_pnl']:>15,.0f} KRW")

    print("\n⚙️  권장 파라미터 설정:")
    print(f"  - 진입 점수 (min_entry_score):      {best['min_entry_score']} 점")
    print(f"  - RSI 과매도 기준 (rsi_oversold):   {best['rsi_oversold']}")
    print(f"  - Stoch 과매도 기준 (stoch_oversold): {best['stoch_oversold']}")
    print(f"  - 볼린저밴드 배수 (bb_std):         {best['bb_std']}")
    print(f"  - 샹들리에 배수 (chandelier_multiplier): {best['chandelier_multiplier']}")
    print(f"  - 포지션 크기 (position_size_pct):  {best['position_size_pct']*100:.0f}%")

    print("\n📝 config_v2.py 수정 권장사항:")
    print("-" * 100)
    print(f"ENTRY_SCORING_CONFIG = {{")
    print(f"    'min_entry_score': {int(best['min_entry_score'])},  # 현재: 3")
    print(f"}}")
    print(f"\nINDICATOR_CONFIG = {{")
    print(f"    'rsi_oversold': {int(best['rsi_oversold'])},  # 현재: 30")
    print(f"    'stoch_oversold': {int(best['stoch_oversold'])},  # 현재: 20")
    print(f"    'bb_std': {best['bb_std']},  # 현재: 2.0")
    print(f"    'chandelier_multiplier': {best['chandelier_multiplier']},  # 현재: 3.0")
    print(f"}}")
    print(f"\nPOSITION_CONFIG = {{")
    print(f"    'initial_position_pct': {int(best['position_size_pct']*100)},  # 현재: 50")
    print(f"}}")

    print("\n" + "=" * 100)

    # Save results
    output_dir = 'logs/optimization'
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    results_df.to_csv(f'{output_dir}/optimization_results_{timestamp}.csv', index=False)
    print(f"💾 전체 결과 저장: {output_dir}/optimization_results_{timestamp}.csv")
    print("=" * 100)


def main():
    """Main execution."""
    print("=" * 100)
    print("🔍 BTC Trading Bot V2 - 전략 최적화 (1년 백테스팅)")
    print("=" * 100)
    print("\n목표: 연 3% 이상 수익률 달성 가능한 파라미터 조합 찾기")
    print("\n최적화 대상 파라미터:")
    print("  1. 진입 점수 기준: 2, 3, 4점")
    print("  2. RSI 과매도: 25, 30, 35")
    print("  3. Stoch 과매도: 15, 20, 25")
    print("  4. 볼린저밴드 배수: 1.5, 2.0, 2.5")
    print("  5. 샹들리에 배수: 2.0, 2.5, 3.0, 3.5")
    print("  6. 포지션 크기: 30%, 50%, 70%")
    print(f"\n예상 테스트 조합: {3 * 3 * 3 * 3 * 4 * 3} = 972 가지")

    try:
        optimizer = StrategyOptimizer(initial_capital=10_000_000)

        # Fetch data
        daily_df, exec_df = optimizer.fetch_1year_data()

        # Run optimization
        results_df = optimizer.optimize(daily_df, exec_df)

        # Print report
        print_optimization_report(results_df, target_return=3.0)

    except Exception as e:
        print(f"\n❌ 최적화 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
