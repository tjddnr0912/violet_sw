"""
Scenario Comparison Backtest - Dynamic Factor Early Adoption Analysis

Compares two scenarios:
1. Baseline: Natural regime transition using EMA50/EMA200 detection
2. Early Adoption: Force strong_bearish mode from start date

Usage:
    python ver3/backtest_scenario_compare.py
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import sys
from pathlib import Path

# Add parent directories to path
base_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(base_dir))
sys.path.insert(0, str(base_dir / 'pybithumb'))

try:
    from pybithumb import get_candlestick as pybithumb_get_candlestick
except ImportError as e:
    print(f"pybithumb import error: {e}")
    sys.exit(1)

sys.path.insert(0, str(base_dir / '001_python_code'))
from ver3.config_v3 import get_version_config
from ver3.regime_detector import RegimeDetector, ExtendedRegime


@dataclass
class Trade:
    """Single trade record."""
    coin: str
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    pnl_pct: float
    reason: str
    regime: str
    entry_score: int


@dataclass
class BacktestResult:
    """Backtest result summary."""
    scenario_name: str
    initial_capital: float
    final_equity: float
    total_return: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    max_drawdown_pct: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Dict] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """Comparison between two scenarios."""
    baseline: BacktestResult
    early_adoption: BacktestResult
    return_difference: float
    win_rate_difference: float
    trade_count_difference: int
    max_drawdown_difference: float


class BacktestEngine:
    """
    Backtest engine with regime override support.

    Implements:
    - Regime-aware entry/exit logic
    - Dynamic entry threshold (entry_threshold_modifier)
    - Dynamic stop loss (stop_loss_modifier)
    - Regime-based take profit (bb_middle vs bb_upper)
    """

    def __init__(
        self,
        coins: List[str],
        initial_capital: float = 1_000_000,
        regime_override: Optional[str] = None,
        scenario_name: str = "Backtest"
    ):
        self.coins = coins
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.regime_override = regime_override
        self.scenario_name = scenario_name

        self.positions: Dict[str, Dict] = {}
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict] = []

        # Config
        self.config = get_version_config()
        self.regime_detector = RegimeDetector(self.config)

        # Trading parameters
        self.position_amount = 100_000  # KRW per position
        self.max_positions = 2
        self.base_min_score = 2
        self.chandelier_base_mult = 3.0
        self.trading_fee = 0.0005  # 0.05%

        # Indicator settings
        self.bb_period = 20
        self.bb_std = 2.0
        self.rsi_period = 14
        self.stoch_k_period = 14
        self.stoch_d_period = 3
        self.atr_period = 14
        self.ema_fast = 50
        self.ema_slow = 200

    def fetch_historical_data(self, coin: str, days: int = 35) -> Optional[pd.DataFrame]:
        """Fetch 4H candlestick data."""
        try:
            df = pybithumb_get_candlestick(coin, "KRW", "4h")
            if df is None or len(df) == 0:
                return None

            df = df.reset_index()
            df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

            # Filter by days
            cutoff = datetime.now() - timedelta(days=days)
            df = df[df['timestamp'] >= cutoff]

            return df.reset_index(drop=True)
        except Exception as e:
            print(f"Error fetching {coin} data: {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators."""
        df = df.copy()

        # EMA for regime detection
        df['ema_fast'] = df['close'].ewm(span=self.ema_fast, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.ema_slow, adjust=False).mean()

        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(window=self.bb_period).mean()
        bb_std = df['close'].rolling(window=self.bb_period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * self.bb_std)
        df['bb_lower'] = df['bb_middle'] - (bb_std * self.bb_std)

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss.replace(0, np.inf)
        df['rsi'] = 100 - (100 / (1 + rs))

        # Stochastic
        low_min = df['low'].rolling(window=self.stoch_k_period).min()
        high_max = df['high'].rolling(window=self.stoch_k_period).max()
        df['stoch_k'] = 100 * (df['close'] - low_min) / (high_max - low_min).replace(0, np.inf)
        df['stoch_d'] = df['stoch_k'].rolling(window=self.stoch_d_period).mean()

        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=self.atr_period).mean()

        return df

    def get_current_regime(self, df: pd.DataFrame) -> Tuple[ExtendedRegime, Dict]:
        """Get current regime (with optional override)."""
        if self.regime_override:
            # Force specific regime
            regime_map = {
                'strong_bullish': ExtendedRegime.STRONG_BULLISH,
                'bullish': ExtendedRegime.BULLISH,
                'neutral': ExtendedRegime.NEUTRAL,
                'bearish': ExtendedRegime.BEARISH,
                'strong_bearish': ExtendedRegime.STRONG_BEARISH,
                'ranging': ExtendedRegime.RANGING,
            }
            regime = regime_map.get(self.regime_override, ExtendedRegime.NEUTRAL)
            metadata = {'regime': regime.value, 'override': True}
            return regime, metadata
        else:
            # Natural regime detection
            return self.regime_detector.detect_regime(df, df)

    def get_regime_strategy(self, regime: ExtendedRegime) -> Dict[str, Any]:
        """Get strategy parameters for regime."""
        return self.regime_detector.get_regime_strategy(regime)

    def calculate_entry_score(self, df: pd.DataFrame) -> Tuple[int, List[str]]:
        """Calculate entry score (0-4)."""
        if len(df) < 2:
            return 0, []

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        score = 0
        conditions = []

        # 1. BB Touch (1 point)
        if latest['close'] <= latest['bb_lower']:
            score += 1
            conditions.append('bb_touch')

        # 2. RSI Oversold (1 point)
        if latest['rsi'] < 30:
            score += 1
            conditions.append('rsi_oversold')

        # 3. Stochastic Cross (2 points)
        if (prev['stoch_k'] <= prev['stoch_d'] and
            latest['stoch_k'] > latest['stoch_d'] and
            latest['stoch_k'] < 20):
            score += 2
            conditions.append('stoch_cross')

        return score, conditions

    def check_extreme_oversold(self, df: pd.DataFrame) -> Tuple[bool, int]:
        """Check extreme oversold conditions for bearish regime."""
        if len(df) < 1:
            return False, 0

        latest = df.iloc[-1]

        conditions = [
            latest['rsi'] < 20,           # RSI extreme
            latest['stoch_k'] < 10,       # Stochastic extreme
            latest['close'] <= latest['bb_lower']  # Price at BB lower
        ]

        count = sum(conditions)
        return count >= 2, count

    def calculate_stop_loss(self, entry_price: float, atr: float,
                           stop_loss_modifier: float) -> float:
        """Calculate Chandelier Exit stop loss."""
        multiplier = self.chandelier_base_mult * stop_loss_modifier
        return entry_price - (atr * multiplier)

    def open_position(
        self,
        coin: str,
        entry_price: float,
        timestamp: datetime,
        entry_score: int,
        stop_loss: float,
        regime: ExtendedRegime,
        strategy: Dict[str, Any],
        indicators: Dict[str, float]
    ):
        """Open new position."""
        amount_krw = self.position_amount
        size = (amount_krw / entry_price) * (1 - self.trading_fee)

        self.capital -= amount_krw

        # Determine take profit target
        if strategy['take_profit_target'] == 'bb_middle':
            tp_price = indicators['bb_middle']
        else:  # bb_upper
            tp_price = indicators['bb_upper']

        position = {
            'coin': coin,
            'entry_price': entry_price,
            'entry_time': timestamp,
            'size': size,
            'stop_loss': stop_loss,
            'tp_price': tp_price,
            'entry_score': entry_score,
            'regime': regime.value,
            'full_exit': strategy['full_exit_at_first_target'],
        }

        self.positions[coin] = position

    def close_position(
        self,
        coin: str,
        exit_price: float,
        timestamp: datetime,
        reason: str
    ):
        """Close position and record trade."""
        if coin not in self.positions:
            return

        pos = self.positions[coin]

        proceeds = pos['size'] * exit_price * (1 - self.trading_fee)
        cost = pos['size'] * pos['entry_price']
        pnl = proceeds - cost
        pnl_pct = (pnl / cost) * 100

        self.capital += proceeds

        trade = Trade(
            coin=coin,
            entry_time=pos['entry_time'],
            exit_time=timestamp,
            entry_price=pos['entry_price'],
            exit_price=exit_price,
            size=pos['size'],
            pnl=pnl,
            pnl_pct=pnl_pct,
            reason=reason,
            regime=pos['regime'],
            entry_score=pos['entry_score']
        )
        self.trades.append(trade)

        del self.positions[coin]

    def run_backtest(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> BacktestResult:
        """Run backtest for specified period."""
        print(f"\n{'='*60}")
        print(f"Running: {self.scenario_name}")
        print(f"Regime Override: {self.regime_override or 'None (auto-detect)'}")
        print(f"{'='*60}\n")

        # Fetch data for all coins
        coin_data: Dict[str, pd.DataFrame] = {}
        for coin in self.coins:
            df = self.fetch_historical_data(coin, days=35)
            if df is None or len(df) < 50:
                print(f"  Insufficient data for {coin}, skipping")
                continue

            df = self.calculate_indicators(df)

            # Filter by date range
            df = df[(df['timestamp'] >= start_date) & (df['timestamp'] <= end_date)]

            if len(df) < 20:
                print(f"  Insufficient data for {coin} in date range, skipping")
                continue

            coin_data[coin] = df
            print(f"  {coin}: {len(df)} candles loaded")

        if not coin_data:
            print("No data available for backtest")
            return self._create_empty_result()

        # Get common timestamps
        all_timestamps = set(coin_data[list(coin_data.keys())[0]]['timestamp'])
        for df in coin_data.values():
            all_timestamps &= set(df['timestamp'])

        timestamps = sorted(all_timestamps)
        print(f"\n  Backtesting {len(timestamps)} timeframes")
        print(f"  Period: {timestamps[0]} to {timestamps[-1]}\n")

        # Main simulation loop
        for i, ts in enumerate(timestamps):
            # Skip warmup period
            if i < 20:
                continue

            # Calculate current equity
            current_equity = self.capital
            for coin, pos in self.positions.items():
                if coin in coin_data:
                    row = coin_data[coin][coin_data[coin]['timestamp'] == ts]
                    if len(row) > 0:
                        current_equity += pos['size'] * row.iloc[0]['close']

            self.equity_curve.append({
                'timestamp': ts,
                'equity': current_equity
            })

            # Process each coin
            for coin in list(coin_data.keys()):
                df = coin_data[coin]
                historical = df[df['timestamp'] <= ts].tail(50)

                if len(historical) < 20:
                    continue

                row = historical.iloc[-1]
                current_price = row['close']

                # Get regime and strategy
                regime, _ = self.get_current_regime(historical)
                strategy = self.get_regime_strategy(regime)

                # Check exits first
                if coin in self.positions:
                    pos = self.positions[coin]

                    # Stop loss check
                    if current_price <= pos['stop_loss']:
                        self.close_position(coin, current_price, ts, 'STOP_LOSS')
                        continue

                    # Take profit check
                    if current_price >= pos['tp_price']:
                        self.close_position(coin, current_price, ts, 'TAKE_PROFIT')
                        continue

                # Check entries
                if coin not in self.positions and len(self.positions) < self.max_positions:
                    if not strategy['allow_entry']:
                        continue

                    entry_score, conditions = self.calculate_entry_score(historical)

                    # Apply entry threshold modifier
                    adjusted_min_score = int(self.base_min_score * strategy['entry_threshold_modifier'])
                    adjusted_min_score = max(1, min(4, adjusted_min_score))

                    if entry_score < adjusted_min_score:
                        continue

                    # For bearish regimes, check extreme oversold
                    if strategy['entry_mode'] == 'reversion':
                        is_extreme, _ = self.check_extreme_oversold(historical)
                        if not is_extreme:
                            continue

                    # Calculate stop loss with modifier
                    stop_loss = self.calculate_stop_loss(
                        current_price,
                        row['atr'],
                        strategy['stop_loss_modifier']
                    )

                    indicators = {
                        'bb_middle': row['bb_middle'],
                        'bb_upper': row['bb_upper'],
                    }

                    if self.capital >= self.position_amount:
                        self.open_position(
                            coin, current_price, ts, entry_score,
                            stop_loss, regime, strategy, indicators
                        )

        # Close remaining positions
        if timestamps:
            final_ts = timestamps[-1]
            for coin in list(self.positions.keys()):
                if coin in coin_data:
                    df = coin_data[coin]
                    final_row = df[df['timestamp'] == final_ts]
                    if len(final_row) > 0:
                        self.close_position(coin, final_row.iloc[0]['close'], final_ts, 'END')

        return self._calculate_result()

    def _calculate_result(self) -> BacktestResult:
        """Calculate backtest result metrics."""
        final_equity = self.equity_curve[-1]['equity'] if self.equity_curve else self.capital
        total_return = final_equity - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100

        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]

        win_rate = len(winning_trades) / len(self.trades) * 100 if self.trades else 0
        avg_win = np.mean([t.pnl for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl for t in losing_trades]) if losing_trades else 0

        # Profit factor
        total_wins = sum(t.pnl for t in winning_trades) if winning_trades else 0
        total_losses = abs(sum(t.pnl for t in losing_trades)) if losing_trades else 1
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Max drawdown
        max_drawdown_pct = 0
        if self.equity_curve:
            peak = self.equity_curve[0]['equity']
            for point in self.equity_curve:
                if point['equity'] > peak:
                    peak = point['equity']
                drawdown = (peak - point['equity']) / peak * 100
                max_drawdown_pct = max(max_drawdown_pct, drawdown)

        return BacktestResult(
            scenario_name=self.scenario_name,
            initial_capital=self.initial_capital,
            final_equity=final_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            total_trades=len(self.trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown_pct,
            trades=self.trades,
            equity_curve=self.equity_curve
        )

    def _create_empty_result(self) -> BacktestResult:
        """Create empty result for failed backtest."""
        return BacktestResult(
            scenario_name=self.scenario_name,
            initial_capital=self.initial_capital,
            final_equity=self.initial_capital,
            total_return=0,
            total_return_pct=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            avg_win=0,
            avg_loss=0,
            profit_factor=0,
            max_drawdown_pct=0
        )


class ScenarioBacktester:
    """Compare two scenarios: Baseline vs Early Adoption."""

    def __init__(
        self,
        coins: List[str],
        start_date: str,
        end_date: str,
        initial_capital: float = 1_000_000
    ):
        self.coins = coins
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d")
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d")
        self.initial_capital = initial_capital

    def run_comparison(self) -> ComparisonResult:
        """Run both scenarios and compare."""
        print("\n" + "="*80)
        print("SCENARIO COMPARISON BACKTEST")
        print("="*80)
        print(f"Coins: {', '.join(self.coins)}")
        print(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        print(f"Initial Capital: {self.initial_capital:,.0f} KRW")
        print("="*80)

        # Run baseline (natural regime detection)
        baseline_engine = BacktestEngine(
            coins=self.coins,
            initial_capital=self.initial_capital,
            regime_override=None,
            scenario_name="Baseline (Auto Regime)"
        )
        baseline_result = baseline_engine.run_backtest(self.start_date, self.end_date)

        # Run early adoption (forced strong_bearish)
        early_engine = BacktestEngine(
            coins=self.coins,
            initial_capital=self.initial_capital,
            regime_override='strong_bearish',
            scenario_name="Early Adoption (Strong Bearish)"
        )
        early_result = early_engine.run_backtest(self.start_date, self.end_date)

        # Calculate differences
        comparison = ComparisonResult(
            baseline=baseline_result,
            early_adoption=early_result,
            return_difference=early_result.total_return_pct - baseline_result.total_return_pct,
            win_rate_difference=early_result.win_rate - baseline_result.win_rate,
            trade_count_difference=early_result.total_trades - baseline_result.total_trades,
            max_drawdown_difference=baseline_result.max_drawdown_pct - early_result.max_drawdown_pct
        )

        return comparison

    def generate_report(self, result: ComparisonResult) -> str:
        """Generate comparison report."""
        b = result.baseline
        e = result.early_adoption

        report = []
        report.append("\n" + "="*80)
        report.append("COMPARISON RESULTS")
        report.append("="*80)
        report.append("")
        report.append(f"{'Metric':<25} {'Baseline':>18} {'Early Adoption':>18} {'Difference':>15}")
        report.append("-"*80)

        # Final Equity
        diff_equity = e.final_equity - b.final_equity
        report.append(f"{'Final Equity':<25} {b.final_equity:>15,.0f} KRW {e.final_equity:>15,.0f} KRW {diff_equity:>+14,.0f}")

        # Total Return
        diff_ret = e.total_return_pct - b.total_return_pct
        report.append(f"{'Total Return':<25} {b.total_return_pct:>17.2f}% {e.total_return_pct:>17.2f}% {diff_ret:>+14.2f}pp")

        # Win Rate
        diff_wr = e.win_rate - b.win_rate
        report.append(f"{'Win Rate':<25} {b.win_rate:>17.1f}% {e.win_rate:>17.1f}% {diff_wr:>+14.1f}pp")

        # Total Trades
        diff_trades = e.total_trades - b.total_trades
        report.append(f"{'Total Trades':<25} {b.total_trades:>18} {e.total_trades:>18} {diff_trades:>+15}")

        # Profit Factor
        diff_pf = e.profit_factor - b.profit_factor
        report.append(f"{'Profit Factor':<25} {b.profit_factor:>18.2f} {e.profit_factor:>18.2f} {diff_pf:>+15.2f}")

        # Max Drawdown
        diff_dd = b.max_drawdown_pct - e.max_drawdown_pct  # Positive = better for early
        report.append(f"{'Max Drawdown':<25} {b.max_drawdown_pct:>17.2f}% {e.max_drawdown_pct:>17.2f}% {diff_dd:>+14.2f}pp")

        report.append("-"*80)
        report.append("")

        # Conclusion
        if result.return_difference > 0:
            report.append("CONCLUSION:")
            report.append(f"  Early strong_bearish adoption would have resulted in")
            report.append(f"  {result.return_difference:+.2f}%p additional returns ({diff_equity:+,.0f} KRW)")
            if result.trade_count_difference < 0:
                report.append(f"  with {abs(result.trade_count_difference)} fewer trades (more selective)")
            if result.max_drawdown_difference > 0:
                report.append(f"  and {result.max_drawdown_difference:.2f}%p less drawdown (better risk management)")
        else:
            report.append("CONCLUSION:")
            report.append(f"  Natural regime detection performed better by")
            report.append(f"  {abs(result.return_difference):.2f}%p ({abs(diff_equity):,.0f} KRW)")

        report.append("")
        report.append("="*80)

        # Trade details
        report.append("\nTRADE DETAILS")
        report.append("-"*80)

        report.append(f"\n[Baseline Trades: {b.total_trades}]")
        for t in b.trades[:10]:  # Show first 10
            report.append(f"  {t.entry_time.strftime('%m-%d %H:%M')} {t.coin} "
                         f"Entry:{t.entry_price:,.0f} Exit:{t.exit_price:,.0f} "
                         f"P&L:{t.pnl:+,.0f} ({t.pnl_pct:+.2f}%) [{t.reason}]")
        if len(b.trades) > 10:
            report.append(f"  ... and {len(b.trades) - 10} more trades")

        report.append(f"\n[Early Adoption Trades: {e.total_trades}]")
        for t in e.trades[:10]:
            report.append(f"  {t.entry_time.strftime('%m-%d %H:%M')} {t.coin} "
                         f"Entry:{t.entry_price:,.0f} Exit:{t.exit_price:,.0f} "
                         f"P&L:{t.pnl:+,.0f} ({t.pnl_pct:+.2f}%) [{t.reason}]")
        if len(e.trades) > 10:
            report.append(f"  ... and {len(e.trades) - 10} more trades")

        report.append("\n" + "="*80)

        return "\n".join(report)

    def generate_chart(self, result: ComparisonResult, output_path: str = None):
        """Generate comparison chart."""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            print("matplotlib not available, skipping chart generation")
            return

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'Scenario Comparison: {self.start_date.date()} to {self.end_date.date()}',
                    fontsize=14, fontweight='bold')

        b = result.baseline
        e = result.early_adoption

        # 1. Equity Curve Comparison (top-left)
        ax1 = axes[0, 0]
        if b.equity_curve and e.equity_curve:
            b_times = [p['timestamp'] for p in b.equity_curve]
            b_equity = [p['equity'] for p in b.equity_curve]
            e_times = [p['timestamp'] for p in e.equity_curve]
            e_equity = [p['equity'] for p in e.equity_curve]

            ax1.plot(b_times, b_equity, 'b-', label='Baseline', linewidth=1.5)
            ax1.plot(e_times, e_equity, 'r-', label='Early Adoption', linewidth=1.5)
            ax1.axhline(y=self.initial_capital, color='gray', linestyle='--', alpha=0.5)
            ax1.set_title('Equity Curve')
            ax1.set_ylabel('Equity (KRW)')
            ax1.legend()
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax1.tick_params(axis='x', rotation=45)
            ax1.grid(True, alpha=0.3)

        # 2. Cumulative Return (top-right)
        ax2 = axes[0, 1]
        if b.equity_curve and e.equity_curve:
            b_returns = [(p['equity'] - self.initial_capital) / self.initial_capital * 100
                        for p in b.equity_curve]
            e_returns = [(p['equity'] - self.initial_capital) / self.initial_capital * 100
                        for p in e.equity_curve]

            ax2.plot(b_times, b_returns, 'b-', label='Baseline', linewidth=1.5)
            ax2.plot(e_times, e_returns, 'r-', label='Early Adoption', linewidth=1.5)
            ax2.axhline(y=0, color='gray', linestyle='--', alpha=0.5)
            ax2.fill_between(b_times, 0, b_returns, alpha=0.3, color='blue')
            ax2.fill_between(e_times, 0, e_returns, alpha=0.3, color='red')
            ax2.set_title('Cumulative Return (%)')
            ax2.set_ylabel('Return (%)')
            ax2.legend()
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax2.tick_params(axis='x', rotation=45)
            ax2.grid(True, alpha=0.3)

        # 3. Metrics Comparison (bottom-left)
        ax3 = axes[1, 0]
        metrics = ['Return (%)', 'Win Rate (%)', 'Profit Factor', 'Max DD (%)']
        baseline_vals = [b.total_return_pct, b.win_rate, b.profit_factor, -b.max_drawdown_pct]
        early_vals = [e.total_return_pct, e.win_rate, e.profit_factor, -e.max_drawdown_pct]

        x = np.arange(len(metrics))
        width = 0.35

        bars1 = ax3.bar(x - width/2, baseline_vals, width, label='Baseline', color='blue', alpha=0.7)
        bars2 = ax3.bar(x + width/2, early_vals, width, label='Early Adoption', color='red', alpha=0.7)

        ax3.set_ylabel('Value')
        ax3.set_title('Metrics Comparison')
        ax3.set_xticks(x)
        ax3.set_xticklabels(metrics)
        ax3.legend()
        ax3.axhline(y=0, color='gray', linestyle='-', alpha=0.3)
        ax3.grid(True, alpha=0.3, axis='y')

        # Add value labels
        for bar, val in zip(bars1, baseline_vals):
            ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{val:.1f}', ha='center', va='bottom', fontsize=8)
        for bar, val in zip(bars2, early_vals):
            ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    f'{val:.1f}', ha='center', va='bottom', fontsize=8)

        # 4. Trade Distribution (bottom-right)
        ax4 = axes[1, 1]
        if b.trades or e.trades:
            b_pnls = [t.pnl for t in b.trades] if b.trades else [0]
            e_pnls = [t.pnl for t in e.trades] if e.trades else [0]

            ax4.hist(b_pnls, bins=10, alpha=0.6, label='Baseline', color='blue')
            ax4.hist(e_pnls, bins=10, alpha=0.6, label='Early Adoption', color='red')
            ax4.axvline(x=0, color='black', linestyle='--', alpha=0.5)
            ax4.set_title('Trade P&L Distribution')
            ax4.set_xlabel('P&L (KRW)')
            ax4.set_ylabel('Frequency')
            ax4.legend()
            ax4.grid(True, alpha=0.3)

        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches='tight')
            print(f"\nChart saved to: {output_path}")
        else:
            plt.show()

        plt.close()


def main():
    """Run scenario comparison backtest."""
    # Configuration
    coins = ['BTC', 'ETH', 'XRP']
    # Note: Use actual recent dates (2025-12 to 2026-01)
    start_date = "2025-12-10"
    end_date = "2026-01-09"
    initial_capital = 1_000_000

    # Run comparison
    backtester = ScenarioBacktester(
        coins=coins,
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital
    )

    result = backtester.run_comparison()

    # Generate report
    report = backtester.generate_report(result)
    print(report)

    # Generate chart
    chart_path = str(base_dir / 'logs' / f'backtest_comparison_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
    backtester.generate_chart(result, chart_path)

    return result


if __name__ == '__main__':
    main()
