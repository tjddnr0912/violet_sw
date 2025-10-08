"""
Comprehensive 3-Month Backtest for Version 2 Strategy

This script performs a detailed backtesting analysis of the v2 trading strategy
over the past 3 months using historical BTC data from Bithumb.

Strategy Configuration:
- Regime Filter: EMA 50/200 Golden Cross on daily timeframe
- Entry Scoring: BB Touch(+1), RSI<30(+1), Stoch Cross(+2) = Min 3/4 points
- Position Management: 50% initial entry, partial exits at BB mid/upper
- Stop Loss: Chandelier Exit (ATR-based trailing stop)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import pybithumb
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../pybithumb')))

try:
    from pybithumb import get_candlestick as pybithumb_get_candlestick
except ImportError as e:
    print(f"❌ pybithumb import error: {e}")
    sys.exit(1)


def get_candlestick(symbol: str, interval: str) -> pd.DataFrame:
    """
    Fetch candlestick data from Bithumb using pybithumb.

    Args:
        symbol: Coin symbol (e.g., 'BTC')
        interval: Interval ('24h' for daily, '4h' for 4-hour)

    Returns:
        DataFrame with OHLCV data
    """
    try:
        # Use pybithumb.get_candlestick directly
        df = pybithumb_get_candlestick(symbol, "KRW", interval)

        if df is None or len(df) == 0:
            return None

        # Rename columns to match expected format
        df = df.reset_index()
        # pybithumb returns: index, open, high, low, close, volume
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

        return df

    except Exception as e:
        print(f"Error fetching candlestick data: {e}")
        import traceback
        traceback.print_exc()
        return None


class BacktestV2:
    """Comprehensive backtesting engine for v2 strategy."""

    def __init__(self, initial_capital: float = 10_000_000):
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting capital in KRW (default: 10M KRW)
        """
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = None  # Current position
        self.trades = []  # Trade history
        self.equity_curve = []  # Equity over time

        # Strategy parameters (from config_v2.py)
        self.min_entry_score = 3
        self.bb_period = 20
        self.bb_std = 2.0
        self.rsi_period = 14
        self.stoch_rsi_period = 14
        self.stoch_period = 14
        self.atr_period = 14
        self.chandelier_multiplier = 3.0
        self.trading_fee = 0.0005  # 0.05% per trade

        # Position sizing
        self.position_size_pct = 0.5  # Use 50% of capital per trade

    def fetch_historical_data(self, months: int = 3) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Fetch 3 months of historical data for both timeframes.

        Args:
            months: Number of months to fetch (default: 3)

        Returns:
            Tuple of (daily_df, hourly_4h_df)
        """
        print(f"📊 Fetching {months} months of historical data...")

        # Fetch daily data for regime filter (need extra for EMA200)
        daily_df = get_candlestick('BTC', '24h')
        if daily_df is None or len(daily_df) < 250:
            raise ValueError("Insufficient daily data for backtesting")

        # Fetch 4H data for execution
        hourly_4h_df = get_candlestick('BTC', '4h')
        if hourly_4h_df is None or len(hourly_4h_df) < 200:
            raise ValueError("Insufficient 4H data for backtesting")

        # Filter to last N months
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30)

        daily_df = daily_df[daily_df['timestamp'] >= start_date]
        hourly_4h_df = hourly_4h_df[hourly_4h_df['timestamp'] >= start_date]

        print(f"✅ Fetched {len(daily_df)} daily candles and {len(hourly_4h_df)} 4H candles")
        return daily_df, hourly_4h_df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators."""
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=self.bb_period).mean()
        bb_std = df['close'].rolling(window=self.bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * self.bb_std)
        df['bb_lower'] = df['bb_middle'] - (bb_std * self.bb_std)

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
        """Calculate EMA regime filter on daily data."""
        daily_df['ema50'] = daily_df['close'].ewm(span=50, adjust=False).mean()
        daily_df['ema200'] = daily_df['close'].ewm(span=200, adjust=False).mean()
        daily_df['regime'] = np.where(
            daily_df['ema50'] > daily_df['ema200'],
            'bullish',
            'bearish'
        )
        return daily_df

    def calculate_entry_score(self, row: pd.Series, prev_row: pd.Series) -> Tuple[int, Dict[str, int]]:
        """
        Calculate entry score for current candle.

        Returns:
            Tuple of (total_score, components_dict)
        """
        score = 0
        components = {}

        # Component 1: BB Lower Touch (+1)
        if row['low'] <= row['bb_lower']:
            score += 1
            components['bb_touch'] = 1
        else:
            components['bb_touch'] = 0

        # Component 2: RSI < 30 (+1)
        if row['rsi'] < 30:
            score += 1
            components['rsi_oversold'] = 1
        else:
            components['rsi_oversold'] = 0

        # Component 3: Stoch RSI Cross below 20 (+2)
        k_cross = prev_row['stoch_k'] <= prev_row['stoch_d'] and row['stoch_k'] > row['stoch_d']
        both_below_20 = row['stoch_k'] < 20 and row['stoch_d'] < 20

        if k_cross and both_below_20:
            score += 2
            components['stoch_cross'] = 2
        else:
            components['stoch_cross'] = 0

        return score, components

    def calculate_chandelier_stop(self, df: pd.DataFrame, idx: int) -> float:
        """Calculate Chandelier Exit stop price."""
        if idx < self.atr_period:
            return 0.0

        lookback = df.iloc[max(0, idx - self.atr_period):idx + 1]
        highest_high = lookback['high'].max()
        current_atr = df.iloc[idx]['atr']

        stop = highest_high - (current_atr * self.chandelier_multiplier)
        return stop

    def run_backtest(self, daily_df: pd.DataFrame, exec_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Run backtest simulation.

        Args:
            daily_df: Daily candles with regime filter
            exec_df: 4H candles with indicators

        Returns:
            Dictionary with backtest results
        """
        print("\n🚀 Starting backtest simulation...")

        # Calculate all indicators
        daily_df = self.calculate_regime(daily_df)
        exec_df = self.calculate_indicators(exec_df)

        # Map daily regime to 4H candles
        exec_df['regime'] = exec_df['timestamp'].apply(
            lambda ts: daily_df[daily_df['timestamp'] <= ts]['regime'].iloc[-1]
            if len(daily_df[daily_df['timestamp'] <= ts]) > 0 else 'unknown'
        )

        # Simulation loop
        for i in range(max(self.bb_period, self.rsi_period, self.stoch_period) + 1, len(exec_df)):
            current = exec_df.iloc[i]
            previous = exec_df.iloc[i - 1]

            # Skip if not in bullish regime
            if current['regime'] != 'bullish':
                self.equity_curve.append({
                    'timestamp': current['timestamp'],
                    'equity': self.capital,
                    'position_value': 0,
                    'total_equity': self.capital
                })
                continue

            # Check exit conditions if in position
            if self.position is not None:
                exit_signal = None
                exit_price = None
                exit_reason = None

                # Check Chandelier stop
                chandelier_stop = self.calculate_chandelier_stop(exec_df, i)
                if current['low'] <= chandelier_stop:
                    exit_signal = True
                    exit_price = min(current['open'], chandelier_stop)
                    exit_reason = 'Chandelier Stop'

                # Check first target (BB middle)
                elif current['high'] >= current['bb_middle'] and not self.position.get('first_target_hit'):
                    # Partial exit (50%)
                    exit_price = max(current['open'], current['bb_middle'])
                    partial_qty = self.position['quantity'] * 0.5
                    proceeds = partial_qty * exit_price * (1 - self.trading_fee)
                    self.capital += proceeds

                    self.position['quantity'] -= partial_qty
                    self.position['first_target_hit'] = True

                    # Record partial exit
                    self.trades.append({
                        'entry_time': self.position['entry_time'],
                        'exit_time': current['timestamp'],
                        'entry_price': self.position['entry_price'],
                        'exit_price': exit_price,
                        'quantity': partial_qty,
                        'pnl': proceeds - (partial_qty * self.position['entry_price']),
                        'pnl_pct': ((exit_price - self.position['entry_price']) / self.position['entry_price']) * 100,
                        'exit_reason': 'Partial Exit - BB Middle (50%)',
                        'score': self.position['entry_score']
                    })

                # Check second target (BB upper)
                elif current['high'] >= current['bb_upper']:
                    exit_signal = True
                    exit_price = max(current['open'], current['bb_upper'])
                    exit_reason = 'BB Upper Target (100%)'

                # Full exit if signal
                if exit_signal and self.position is not None:
                    qty = self.position['quantity']
                    proceeds = qty * exit_price * (1 - self.trading_fee)
                    self.capital += proceeds

                    # Record trade
                    self.trades.append({
                        'entry_time': self.position['entry_time'],
                        'exit_time': current['timestamp'],
                        'entry_price': self.position['entry_price'],
                        'exit_price': exit_price,
                        'quantity': qty,
                        'pnl': proceeds - (qty * self.position['entry_price']),
                        'pnl_pct': ((exit_price - self.position['entry_price']) / self.position['entry_price']) * 100,
                        'exit_reason': exit_reason,
                        'score': self.position['entry_score']
                    })

                    self.position = None

            # Check entry conditions if no position
            if self.position is None:
                score, components = self.calculate_entry_score(current, previous)

                if score >= self.min_entry_score:
                    # Enter position
                    position_value = self.capital * self.position_size_pct
                    entry_price = current['close']
                    quantity = (position_value / entry_price) * (1 - self.trading_fee)
                    cost = quantity * entry_price

                    self.capital -= cost
                    self.position = {
                        'entry_time': current['timestamp'],
                        'entry_price': entry_price,
                        'quantity': quantity,
                        'entry_score': score,
                        'components': components,
                        'first_target_hit': False
                    }

            # Track equity
            position_value = 0
            if self.position is not None:
                position_value = self.position['quantity'] * current['close']

            self.equity_curve.append({
                'timestamp': current['timestamp'],
                'equity': self.capital,
                'position_value': position_value,
                'total_equity': self.capital + position_value
            })

        # Force close any remaining position
        if self.position is not None:
            final_candle = exec_df.iloc[-1]
            qty = self.position['quantity']
            exit_price = final_candle['close']
            proceeds = qty * exit_price * (1 - self.trading_fee)
            self.capital += proceeds

            self.trades.append({
                'entry_time': self.position['entry_time'],
                'exit_time': final_candle['timestamp'],
                'entry_price': self.position['entry_price'],
                'exit_price': exit_price,
                'quantity': qty,
                'pnl': proceeds - (qty * self.position['entry_price']),
                'pnl_pct': ((exit_price - self.position['entry_price']) / self.position['entry_price']) * 100,
                'exit_reason': 'End of Backtest',
                'score': self.position['entry_score']
            })

            self.position = None

        # Calculate statistics
        return self.calculate_statistics()

    def calculate_statistics(self) -> Dict[str, Any]:
        """Calculate comprehensive performance statistics."""
        trades_df = pd.DataFrame(self.trades)
        equity_df = pd.DataFrame(self.equity_curve)

        if len(trades_df) == 0:
            return {
                'total_trades': 0,
                'message': 'No trades executed during backtest period'
            }

        # Basic metrics
        total_trades = len(trades_df)
        winning_trades = len(trades_df[trades_df['pnl'] > 0])
        losing_trades = len(trades_df[trades_df['pnl'] <= 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # P&L metrics
        total_pnl = trades_df['pnl'].sum()
        total_pnl_pct = ((self.capital - self.initial_capital) / self.initial_capital) * 100

        avg_win = trades_df[trades_df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0
        avg_loss = abs(trades_df[trades_df['pnl'] <= 0]['pnl'].mean()) if losing_trades > 0 else 0

        largest_win = trades_df['pnl'].max() if total_trades > 0 else 0
        largest_loss = trades_df['pnl'].min() if total_trades > 0 else 0

        # Risk metrics
        profit_factor = (trades_df[trades_df['pnl'] > 0]['pnl'].sum() /
                        abs(trades_df[trades_df['pnl'] <= 0]['pnl'].sum())) if losing_trades > 0 else float('inf')

        # Drawdown
        equity_df['peak'] = equity_df['total_equity'].cummax()
        equity_df['drawdown'] = (equity_df['total_equity'] - equity_df['peak']) / equity_df['peak'] * 100
        max_drawdown = equity_df['drawdown'].min()

        return {
            'initial_capital': self.initial_capital,
            'final_capital': self.capital,
            'total_pnl': total_pnl,
            'total_pnl_pct': total_pnl_pct,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'profit_factor': profit_factor,
            'max_drawdown': max_drawdown,
            'trades': trades_df,
            'equity_curve': equity_df
        }


def print_backtest_report(results: Dict[str, Any]):
    """Print comprehensive backtest report."""
    print("\n" + "="*80)
    print("📊 BTC TRADING BOT V2 - 3개월 백테스팅 결과 보고서")
    print("="*80)

    if results.get('total_trades', 0) == 0:
        print("\n⚠️  백테스팅 기간 동안 거래가 발생하지 않았습니다.")
        print("   - 진입 조건(3점 이상)을 충족하는 시점이 없었거나")
        print("   - 시장 체제가 Bearish 상태였을 가능성이 있습니다.")
        return

    # 1. 수익성 지표
    print("\n📈 1. 수익성 (Profitability)")
    print("-" * 80)
    print(f"  초기 자본:        {results['initial_capital']:>15,.0f} KRW")
    print(f"  최종 자본:        {results['final_capital']:>15,.0f} KRW")
    print(f"  총 손익:          {results['total_pnl']:>15,.0f} KRW  ({results['total_pnl_pct']:>6.2f}%)")
    print(f"  최대 낙폭:        {results['max_drawdown']:>15.2f}%")

    # 2. 거래 통계
    print("\n💼 2. 거래 통계 (Trade Statistics)")
    print("-" * 80)
    print(f"  총 거래 횟수:     {results['total_trades']:>15} 회")
    print(f"  승리 거래:        {results['winning_trades']:>15} 회")
    print(f"  손실 거래:        {results['losing_trades']:>15} 회")
    print(f"  승률:             {results['win_rate']:>15.2f}%")

    # 3. 손익 분석
    print("\n💰 3. 손익 분석 (P&L Analysis)")
    print("-" * 80)
    print(f"  평균 수익:        {results['avg_win']:>15,.0f} KRW")
    print(f"  평균 손실:        {results['avg_loss']:>15,.0f} KRW")
    print(f"  최대 수익:        {results['largest_win']:>15,.0f} KRW")
    print(f"  최대 손실:        {results['largest_loss']:>15,.0f} KRW")
    print(f"  Profit Factor:    {results['profit_factor']:>15.2f}")

    # 4. 거래 내역 상세
    trades_df = results['trades']

    print("\n📋 4. 거래 내역 상세 (Trade Details)")
    print("-" * 80)
    print(f"{'No':<4} {'진입일시':<20} {'청산일시':<20} {'진입가':<12} {'청산가':<12} {'수익률':<10} {'손익(KRW)':<15} {'종료사유':<25}")
    print("-" * 80)

    for idx, trade in trades_df.iterrows():
        print(f"{idx+1:<4} "
              f"{trade['entry_time'].strftime('%Y-%m-%d %H:%M'):<20} "
              f"{trade['exit_time'].strftime('%Y-%m-%d %H:%M'):<20} "
              f"{trade['entry_price']:>12,.0f} "
              f"{trade['exit_price']:>12,.0f} "
              f"{trade['pnl_pct']:>9.2f}% "
              f"{trade['pnl']:>14,.0f} "
              f"{trade['exit_reason']:<25}")

    # 5. 스코어별 승률 분석
    print("\n🎯 5. Entry Score별 승률 분석")
    print("-" * 80)
    score_analysis = trades_df.groupby('score').agg({
        'pnl': ['count', lambda x: (x > 0).sum(), 'sum']
    }).round(2)
    score_analysis.columns = ['거래수', '승리', '총손익(KRW)']
    score_analysis['승률(%)'] = (score_analysis['승리'] / score_analysis['거래수'] * 100).round(2)
    print(score_analysis.to_string())

    # 6. 월별 수익률
    print("\n📅 6. 월별 수익률 (Monthly Returns)")
    print("-" * 80)
    trades_df['month'] = pd.to_datetime(trades_df['exit_time']).dt.to_period('M')
    monthly = trades_df.groupby('month').agg({
        'pnl': ['count', 'sum']
    })
    monthly.columns = ['거래수', '손익(KRW)']
    print(monthly.to_string())

    print("\n" + "="*80)
    print("✅ 백테스팅 보고서 완료")
    print("="*80)


def main():
    """Main execution function."""
    print("="*80)
    print("🤖 BTC Trading Bot V2 - 3개월 백테스팅")
    print("="*80)
    print("\n전략 설정:")
    print("  - 시장 체제: EMA 50/200 Golden Cross (Daily)")
    print("  - 진입 시스템: 점수 기반 (3점 이상)")
    print("    • BB Lower Touch: +1점")
    print("    • RSI < 30: +1점")
    print("    • Stoch RSI Cross < 20: +2점")
    print("  - 청산 전략:")
    print("    • 1차 목표: BB Middle에서 50% 청산")
    print("    • 2차 목표: BB Upper에서 100% 청산")
    print("    • 손절: Chandelier Exit (ATR 기반)")
    print("  - 초기 자본: 10,000,000 KRW")
    print("  - 포지션 크기: 50% of capital")
    print("  - 거래 수수료: 0.05%")

    try:
        # Initialize backtest
        backtest = BacktestV2(initial_capital=10_000_000)

        # Fetch data
        daily_df, exec_df = backtest.fetch_historical_data(months=3)

        # Run backtest
        results = backtest.run_backtest(daily_df, exec_df)

        # Print report
        print_backtest_report(results)

        # Save results
        output_dir = 'logs/backtests'
        os.makedirs(output_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        if results.get('total_trades', 0) > 0:
            results['trades'].to_csv(f'{output_dir}/trades_{timestamp}.csv', index=False)
            results['equity_curve'].to_csv(f'{output_dir}/equity_{timestamp}.csv', index=False)
            print(f"\n💾 결과 저장 완료: {output_dir}/")

    except Exception as e:
        print(f"\n❌ 백테스팅 중 오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
