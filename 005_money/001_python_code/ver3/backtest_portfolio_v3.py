"""
Portfolio Backtest for Version 3 Strategy

This script performs portfolio-level backtesting with your current Ver3 settings:
- Multi-coin portfolio: ETH, XRP, SOL
- Entry: Min score 3/4 (BB, RSI, Stoch)
- Exit: Percentage-based TP1 1.5%, TP2 2.5%
- Stop-Loss: Chandelier Exit (ATR × 3.0)
- Position: 50,000 KRW per coin
- Max positions: 3 concurrent
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
import sys
import os
from pathlib import Path

# Add parent directories to path
base_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(base_dir))
sys.path.insert(0, str(base_dir / 'pybithumb'))

try:
    from pybithumb import get_candlestick as pybithumb_get_candlestick
except ImportError as e:
    print(f"❌ pybithumb import error: {e}")
    sys.exit(1)

# Import Ver3 components
sys.path.insert(0, str(base_dir / '001_python_code'))
from ver3.config_v3 import get_version_config
from ver3.preference_manager_v3 import PreferenceManagerV3
from ver3.strategy_v3 import StrategyV3


class PortfolioBacktestV3:
    """Multi-coin portfolio backtesting engine."""

    def __init__(self, coins: List[str], initial_capital: float = 1_000_000):
        """
        Initialize portfolio backtest.

        Args:
            coins: List of coins to trade
            initial_capital: Starting capital in KRW
        """
        self.coins = coins
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions = {}  # {coin: position_dict}
        self.trades = []  # All trades history
        self.equity_curve = []  # Equity over time

        # Load Ver3 config with user preferences
        config = get_version_config()
        pref_manager = PreferenceManagerV3()
        prefs = pref_manager.load_preferences()
        self.config = pref_manager.merge_with_config(prefs, config)

        # Extract settings
        entry_config = prefs.get('entry_scoring', {})
        exit_config = prefs.get('exit_scoring', {})
        risk_config = prefs.get('risk_management', {})

        self.min_entry_score = entry_config.get('min_entry_score', 3)
        self.position_amount = risk_config.get('position_amount_krw', 50000)
        self.max_positions = prefs.get('portfolio_config', {}).get('max_positions', 3)
        self.tp1_pct = exit_config.get('tp1_target', 1.5)
        self.tp2_pct = exit_config.get('tp2_target', 2.5)
        self.chandelier_mult = exit_config.get('chandelier_atr_multiplier', 3.0)
        self.trading_fee = 0.0005  # 0.05%

        # Initialize strategy
        self.strategy = StrategyV3(self.config, None)

        print(f"📊 Portfolio Backtest V3 Initialized")
        print(f"Coins: {coins}")
        print(f"Initial Capital: {initial_capital:,.0f} KRW")
        print(f"Position Size: {self.position_amount:,.0f} KRW per coin")
        print(f"Max Positions: {self.max_positions}")
        print(f"Entry: Min score {self.min_entry_score}/4")
        print(f"Exit: TP1 {self.tp1_pct}%, TP2 {self.tp2_pct}%")
        print(f"Stop-Loss: Chandelier ATR × {self.chandelier_mult}")
        print()

    def fetch_historical_data(self, coin: str, days: int = 90) -> pd.DataFrame:
        """Fetch historical 4h candlestick data."""
        try:
            df = pybithumb_get_candlestick(coin, "KRW", "4h")
            if df is None or len(df) == 0:
                return None

            df = df.reset_index()
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

            # Keep last N days
            cutoff = datetime.now() - timedelta(days=days)
            df = df[df['timestamp'] >= cutoff]

            return df.reset_index(drop=True)
        except Exception as e:
            print(f"❌ Error fetching {coin} data: {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all indicators using strategy."""
        df = self.strategy._calculate_execution_indicators(df)
        return df

    def calculate_entry_score(self, df: pd.DataFrame) -> Tuple[int, str]:
        """Calculate entry score."""
        return self.strategy._calculate_entry_score(df)

    def calculate_stop_loss(self, df: pd.DataFrame) -> float:
        """Calculate Chandelier Exit stop-loss."""
        return self.strategy._calculate_chandelier_stop(df)

    def open_position(self, coin: str, entry_price: float, timestamp: datetime,
                     entry_score: int, stop_loss: float):
        """Open new position."""
        # Calculate position size
        amount_krw = self.position_amount
        size = (amount_krw / entry_price) * (1 - self.trading_fee)

        # Deduct from capital
        self.capital -= amount_krw

        # Calculate targets
        tp1_price = entry_price * (1 + self.tp1_pct / 100)
        tp2_price = entry_price * (1 + self.tp2_pct / 100)

        position = {
            'coin': coin,
            'entry_price': entry_price,
            'entry_time': timestamp,
            'size': size,
            'initial_size': size,
            'stop_loss': stop_loss,
            'tp1_price': tp1_price,
            'tp2_price': tp2_price,
            'tp1_hit': False,
            'tp2_hit': False,
            'entry_score': entry_score
        }

        self.positions[coin] = position

        print(f"🟢 OPEN {coin} @ {entry_price:,.0f} KRW | Size: {size:.6f} | "
              f"TP1: {tp1_price:,.0f} | TP2: {tp2_price:,.0f} | SL: {stop_loss:,.0f}")

    def close_position(self, coin: str, exit_price: float, timestamp: datetime,
                      reason: str, partial: float = 1.0):
        """Close position (full or partial)."""
        if coin not in self.positions:
            return

        pos = self.positions[coin]
        exit_size = pos['size'] * partial

        # Calculate P&L
        proceeds = exit_size * exit_price * (1 - self.trading_fee)
        cost = exit_size * pos['entry_price']
        pnl = proceeds - cost
        pnl_pct = (pnl / cost) * 100

        # Update capital
        self.capital += proceeds

        # Record trade
        trade = {
            'coin': coin,
            'entry_time': pos['entry_time'],
            'exit_time': timestamp,
            'entry_price': pos['entry_price'],
            'exit_price': exit_price,
            'size': exit_size,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'reason': reason,
            'partial': partial < 1.0
        }
        self.trades.append(trade)

        # Update or remove position
        if partial < 1.0:
            # Partial exit
            pos['size'] -= exit_size
            if reason == 'TP1':
                pos['tp1_hit'] = True
                # Move stop-loss to breakeven
                pos['stop_loss'] = pos['entry_price']
            print(f"🟡 PARTIAL {coin} ({partial*100:.0f}%) @ {exit_price:,.0f} KRW | "
                  f"P&L: {pnl:+,.0f} KRW ({pnl_pct:+.2f}%) | {reason}")
        else:
            # Full exit
            del self.positions[coin]
            print(f"🔴 CLOSE {coin} @ {exit_price:,.0f} KRW | "
                  f"P&L: {pnl:+,.0f} KRW ({pnl_pct:+.2f}%) | {reason}")

    def run_backtest(self, months: int = 3):
        """Run portfolio backtest."""
        print(f"\n{'='*80}")
        print(f"Running {months}-Month Backtest")
        print(f"{'='*80}\n")

        # Fetch data for all coins
        coin_data = {}
        for coin in self.coins:
            print(f"Fetching {coin} data...")
            df = self.fetch_historical_data(coin, days=months*30)
            if df is None or len(df) < 50:
                print(f"⚠️  Insufficient data for {coin}, skipping")
                continue

            # Calculate indicators
            df = self.calculate_indicators(df)
            coin_data[coin] = df
            print(f"✓ {coin}: {len(df)} candles")

        if not coin_data:
            print("❌ No data available for backtest")
            return

        # Get common timestamps
        all_timestamps = set(coin_data[list(coin_data.keys())[0]]['timestamp'])
        for coin_df in coin_data.values():
            all_timestamps &= set(coin_df['timestamp'])

        timestamps = sorted(all_timestamps)
        print(f"\n✓ Total timeframes: {len(timestamps)}")
        print(f"Period: {timestamps[0]} to {timestamps[-1]}")
        print(f"\n{'='*80}\n")

        # Run simulation
        for i, ts in enumerate(timestamps):
            # Skip first 50 candles for indicator warmup
            if i < 50:
                continue

            current_equity = self.capital + sum(
                pos['size'] * coin_data[pos['coin']][
                    coin_data[pos['coin']]['timestamp'] == ts
                ]['close'].iloc[0]
                for pos in self.positions.values()
                if len(coin_data[pos['coin']][coin_data[pos['coin']]['timestamp'] == ts]) > 0
            )
            self.equity_curve.append({
                'timestamp': ts,
                'equity': current_equity
            })

            # Check exits first (stop-loss, TP1, TP2)
            for coin in list(self.positions.keys()):
                pos = self.positions[coin]
                df = coin_data[coin]
                row = df[df['timestamp'] == ts]

                if len(row) == 0:
                    continue

                row = row.iloc[0]
                current_price = row['close']

                # Check stop-loss
                if current_price <= pos['stop_loss']:
                    self.close_position(coin, current_price, ts, 'STOP-LOSS')
                    continue

                # Check TP2
                if pos['tp1_hit'] and current_price >= pos['tp2_price']:
                    self.close_position(coin, current_price, ts, 'TP2', partial=1.0)
                    continue

                # Check TP1
                if not pos['tp1_hit'] and current_price >= pos['tp1_price']:
                    self.close_position(coin, current_price, ts, 'TP1', partial=0.5)

            # Check entries
            if len(self.positions) < self.max_positions:
                entry_candidates = []

                for coin, df in coin_data.items():
                    if coin in self.positions:
                        continue

                    # Get data up to current timestamp
                    historical = df[df['timestamp'] <= ts].tail(50)

                    if len(historical) < 50:
                        continue

                    # Calculate entry score
                    entry_score, _ = self.calculate_entry_score(historical)

                    if entry_score >= self.min_entry_score:
                        row = historical.iloc[-1]
                        stop_loss = self.calculate_stop_loss(historical)

                        entry_candidates.append({
                            'coin': coin,
                            'score': entry_score,
                            'price': row['close'],
                            'stop_loss': stop_loss
                        })

                # Sort by score and enter best candidates
                entry_candidates.sort(key=lambda x: x['score'], reverse=True)

                for candidate in entry_candidates:
                    if len(self.positions) >= self.max_positions:
                        break

                    if self.capital >= self.position_amount:
                        self.open_position(
                            candidate['coin'],
                            candidate['price'],
                            ts,
                            candidate['score'],
                            candidate['stop_loss']
                        )

        # Close any remaining positions at final price
        final_ts = timestamps[-1]
        for coin in list(self.positions.keys()):
            df = coin_data[coin]
            final_price = df[df['timestamp'] == final_ts]['close'].iloc[0]
            self.close_position(coin, final_price, final_ts, 'END', partial=1.0)

        # Generate report
        self.generate_report(months)

    def generate_report(self, months: int):
        """Generate backtest report."""
        print(f"\n{'='*80}")
        print(f"📊 BACKTEST RESULTS ({months} Months)")
        print(f"{'='*80}\n")

        # Calculate metrics
        final_equity = self.equity_curve[-1]['equity'] if self.equity_curve else self.capital
        total_return = final_equity - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100

        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] <= 0]

        win_rate = len(winning_trades) / len(self.trades) * 100 if self.trades else 0

        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0

        # Print summary
        print(f"Period: {self.equity_curve[0]['timestamp']} to {self.equity_curve[-1]['timestamp']}")
        print(f"Duration: {months} months\n")

        print(f"Initial Capital:  {self.initial_capital:>15,.0f} KRW")
        print(f"Final Equity:     {final_equity:>15,.0f} KRW")
        print(f"Total Return:     {total_return:>15,.0f} KRW ({total_return_pct:+.2f}%)\n")

        print(f"Total Trades:     {len(self.trades):>15}")
        print(f"Winning Trades:   {len(winning_trades):>15} ({win_rate:.1f}%)")
        print(f"Losing Trades:    {len(losing_trades):>15}\n")

        print(f"Average Win:      {avg_win:>15,.0f} KRW")
        print(f"Average Loss:     {avg_loss:>15,.0f} KRW")

        if avg_loss != 0:
            profit_factor = abs(sum(t['pnl'] for t in winning_trades) /
                              sum(t['pnl'] for t in losing_trades))
            print(f"Profit Factor:    {profit_factor:>15.2f}")

        print(f"\n{'='*80}\n")

        # Trade breakdown by coin
        print("Trade Breakdown by Coin:")
        for coin in self.coins:
            coin_trades = [t for t in self.trades if t['coin'] == coin]
            if coin_trades:
                coin_pnl = sum(t['pnl'] for t in coin_trades)
                coin_wins = len([t for t in coin_trades if t['pnl'] > 0])
                print(f"  {coin}: {len(coin_trades)} trades, "
                      f"{coin_wins}/{len(coin_trades)} wins, "
                      f"P&L: {coin_pnl:+,.0f} KRW")

        print(f"\n{'='*80}")


if __name__ == '__main__':
    # Run backtest with current Ver3 settings
    backtest = PortfolioBacktestV3(
        coins=['ETH', 'XRP', 'SOL'],
        initial_capital=1_000_000  # 1M KRW
    )

    backtest.run_backtest(months=3)
