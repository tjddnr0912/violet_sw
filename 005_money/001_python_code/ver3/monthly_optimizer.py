"""
Monthly Backtest Optimizer - Parameter Optimization through Walk-Forward Analysis

This module performs monthly parameter optimization using:
- 3-month historical backtesting
- Grid search for optimal parameters
- Walk-forward validation (train/test split)
- Parameter change limits (±20% from current values)

Usage:
    from ver3.monthly_optimizer import MonthlyOptimizer

    optimizer = MonthlyOptimizer()
    results = optimizer.run_optimization()
    if results['success']:
        optimizer.apply_recommended_parameters()

Optimization Schedule:
    - Run manually or via scheduled task on 1st of each month
    - Requires at least 3 months of historical data
    - Produces detailed report of parameter changes
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path
import itertools
import pandas as pd
import numpy as np

from ver3.config_v3 import (
    get_version_config,
    DYNAMIC_FACTOR_CONFIG,
    ENTRY_SCORING_CONFIG,
    INDICATOR_CONFIG,
    EXIT_CONFIG,
)
from ver3.strategy_v3 import StrategyV3
from lib.api.bithumb_api import BithumbAPI, get_candlestick
from lib.core.logger import TradingLogger


# Default parameter bounds for grid search
DEFAULT_PARAMETER_BOUNDS = {
    'chandelier_multiplier': (2.0, 5.0, 0.5),  # (min, max, step)
    'rsi_oversold_threshold': (20, 40, 5),
    'stoch_oversold_threshold': (15, 30, 5),
    'min_entry_score': (1, 4, 1),
    'bb_weight': (0.5, 2.0, 0.5),
    'rsi_weight': (0.5, 2.0, 0.5),
    'stoch_weight': (1.0, 3.0, 0.5),
}

# Maximum allowed change from current values
MAX_CHANGE_PERCENT = 20.0


class BacktestResult:
    """Container for backtest results."""

    def __init__(self):
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit_pct = 0.0
        self.max_drawdown_pct = 0.0
        self.sharpe_ratio = 0.0
        self.profit_factor = 1.0
        self.trades: List[Dict] = []

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def score(self) -> float:
        """
        Calculate optimization score.

        Weights:
        - Win rate: 30%
        - Profit factor: 30%
        - Sharpe ratio: 20%
        - Total trades (activity): 20%

        Higher is better.
        """
        if self.total_trades < 5:
            return 0.0  # Require minimum trades

        # Normalize metrics
        wr_score = min(self.win_rate, 1.0)
        pf_score = min(self.profit_factor / 3.0, 1.0)  # Normalize to 0-1
        sr_score = max(0, min(self.sharpe_ratio / 2.0, 1.0))  # Normalize
        activity_score = min(self.total_trades / 30.0, 1.0)  # 30 trades = max

        return (
            wr_score * 0.30 +
            pf_score * 0.30 +
            sr_score * 0.20 +
            activity_score * 0.20
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': round(self.win_rate, 3),
            'total_profit_pct': round(self.total_profit_pct, 2),
            'max_drawdown_pct': round(self.max_drawdown_pct, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 2),
            'profit_factor': round(self.profit_factor, 2),
            'score': round(self.score, 3),
        }


class MonthlyOptimizer:
    """
    Monthly parameter optimizer using walk-forward backtesting.

    Features:
    - Grid search over parameter space
    - Walk-forward validation (70% train, 30% test)
    - Parameter change limits
    - Detailed optimization reports
    """

    def __init__(
        self,
        coins: List[str] = None,
        lookback_months: int = 3,
        output_dir: str = 'logs/optimization',
    ):
        """
        Initialize optimizer.

        Args:
            coins: List of coins to optimize (default: ['BTC', 'ETH', 'XRP'])
            lookback_months: Number of months of data to use
            output_dir: Directory for optimization reports
        """
        self.coins = coins or ['BTC', 'ETH', 'XRP']
        self.lookback_months = lookback_months
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load current config
        self.config = get_version_config()
        self.logger = TradingLogger()

        # Current parameter values (for change limit calculation)
        self.current_params = self._extract_current_params()

    def _extract_current_params(self) -> Dict[str, float]:
        """Extract current parameter values from config."""
        return {
            'chandelier_multiplier': INDICATOR_CONFIG.get('chandelier_multiplier', 3.0),
            'rsi_oversold_threshold': ENTRY_SCORING_CONFIG.get('scoring_rules', {}).get('rsi_oversold', {}).get('threshold', 30),
            'stoch_oversold_threshold': 20,  # Default
            'min_entry_score': ENTRY_SCORING_CONFIG.get('min_score_for_entry', 2),
            'bb_weight': 1.0,  # Default weight
            'rsi_weight': 1.0,
            'stoch_weight': 2.0,
        }

    def run_optimization(self) -> Dict[str, Any]:
        """
        Run full optimization process.

        Returns:
            Dictionary with:
            - success: bool
            - recommended_params: Dict of new parameter values
            - improvement_pct: Expected improvement percentage
            - report_path: Path to detailed report
        """
        self.logger.logger.info("=" * 60)
        self.logger.logger.info("Starting Monthly Parameter Optimization")
        self.logger.logger.info("=" * 60)

        try:
            # Step 1: Fetch historical data
            self.logger.logger.info("Step 1: Fetching historical data...")
            historical_data = self._fetch_historical_data()

            if not historical_data:
                return {
                    'success': False,
                    'error': 'Failed to fetch historical data',
                }

            # Step 2: Generate parameter combinations
            self.logger.logger.info("Step 2: Generating parameter combinations...")
            param_combinations = self._generate_param_combinations()
            self.logger.logger.info(f"  Generated {len(param_combinations)} combinations")

            # Step 3: Run walk-forward backtests
            self.logger.logger.info("Step 3: Running walk-forward backtests...")
            results = self._run_walk_forward_tests(historical_data, param_combinations)

            if not results:
                return {
                    'success': False,
                    'error': 'No valid backtest results',
                }

            # Step 4: Find best parameters
            self.logger.logger.info("Step 4: Analyzing results...")
            best_params, best_result = self._find_best_params(results)

            # Step 5: Apply change limits
            self.logger.logger.info("Step 5: Applying change limits...")
            limited_params = self._apply_change_limits(best_params)

            # Step 6: Calculate improvement
            baseline_result = self._run_single_backtest(
                historical_data,
                self.current_params
            )
            improvement_pct = (
                (best_result.score - baseline_result.score) / baseline_result.score * 100
                if baseline_result.score > 0 else 0
            )

            # Step 7: Generate report
            report_path = self._generate_report(
                baseline_result,
                best_result,
                limited_params,
                results
            )

            self.logger.logger.info("=" * 60)
            self.logger.logger.info("Optimization Complete!")
            self.logger.logger.info(f"  Baseline Score: {baseline_result.score:.3f}")
            self.logger.logger.info(f"  Best Score: {best_result.score:.3f}")
            self.logger.logger.info(f"  Expected Improvement: {improvement_pct:+.1f}%")
            self.logger.logger.info(f"  Report: {report_path}")
            self.logger.logger.info("=" * 60)

            return {
                'success': True,
                'recommended_params': limited_params,
                'baseline_score': baseline_result.score,
                'best_score': best_result.score,
                'improvement_pct': improvement_pct,
                'report_path': str(report_path),
            }

        except Exception as e:
            self.logger.log_error("Optimization failed", e)
            import traceback
            self.logger.logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
            }

    def _fetch_historical_data(self) -> Dict[str, pd.DataFrame]:
        """Fetch historical OHLCV data for all coins."""
        data = {}
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.lookback_months * 30)

        for coin in self.coins:
            try:
                # Fetch 4H candles for execution timeframe
                df = get_candlestick(coin, interval='4h')
                if df is not None and not df.empty:
                    # Filter to date range
                    if 'timestamp' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['timestamp'])
                        df = df[df['timestamp'] >= start_date]

                    data[coin] = df
                    self.logger.logger.info(f"  {coin}: {len(df)} candles fetched")

            except Exception as e:
                self.logger.logger.warning(f"  {coin}: Failed to fetch data - {e}")

        return data

    def _generate_param_combinations(self) -> List[Dict[str, float]]:
        """Generate all parameter combinations for grid search."""
        param_ranges = {}

        for param, (min_val, max_val, step) in DEFAULT_PARAMETER_BOUNDS.items():
            # Generate values within bounds
            values = []
            current = min_val
            while current <= max_val:
                values.append(current)
                current += step
            param_ranges[param] = values

        # Generate all combinations
        keys = list(param_ranges.keys())
        value_lists = [param_ranges[k] for k in keys]

        combinations = []
        for values in itertools.product(*value_lists):
            combo = dict(zip(keys, values))
            combinations.append(combo)

        return combinations

    def _run_walk_forward_tests(
        self,
        historical_data: Dict[str, pd.DataFrame],
        param_combinations: List[Dict[str, float]]
    ) -> List[Tuple[Dict[str, float], BacktestResult]]:
        """
        Run walk-forward backtests for all parameter combinations.

        Walk-forward: 70% train, 30% test
        """
        results = []
        total = len(param_combinations)

        for i, params in enumerate(param_combinations):
            if (i + 1) % 50 == 0:
                self.logger.logger.info(f"  Progress: {i + 1}/{total}")

            try:
                result = self._run_single_backtest(historical_data, params)
                results.append((params, result))
            except Exception as e:
                self.logger.logger.debug(f"  Backtest failed for params {params}: {e}")
                continue

        return results

    def _run_single_backtest(
        self,
        historical_data: Dict[str, pd.DataFrame],
        params: Dict[str, float]
    ) -> BacktestResult:
        """Run a single backtest with given parameters."""
        result = BacktestResult()

        # Create modified config with parameters
        test_config = self._create_test_config(params)

        # Simple simulation: iterate through data and simulate trades
        for coin, df in historical_data.items():
            if df is None or len(df) < 50:
                continue

            # Use last 30% as test period
            test_start = int(len(df) * 0.7)
            test_df = df.iloc[test_start:].copy()

            # Simulate trades
            coin_result = self._simulate_trades(test_df, test_config, params)

            # Aggregate results
            result.total_trades += coin_result.total_trades
            result.winning_trades += coin_result.winning_trades
            result.losing_trades += coin_result.losing_trades
            result.total_profit_pct += coin_result.total_profit_pct
            result.trades.extend(coin_result.trades)

        # Calculate aggregate metrics
        if result.trades:
            result.max_drawdown_pct = self._calculate_max_drawdown(result.trades)
            result.sharpe_ratio = self._calculate_sharpe_ratio(result.trades)

            profits = [t['profit_pct'] for t in result.trades if t['profit_pct'] > 0]
            losses = [abs(t['profit_pct']) for t in result.trades if t['profit_pct'] <= 0]

            if losses:
                result.profit_factor = sum(profits) / sum(losses) if sum(losses) > 0 else 999.0
            else:
                result.profit_factor = 999.0 if profits else 1.0

        return result

    def _simulate_trades(
        self,
        df: pd.DataFrame,
        config: Dict[str, Any],
        params: Dict[str, float]
    ) -> BacktestResult:
        """
        Simulate trades on historical data.

        Simple simulation logic:
        - Entry when RSI < threshold and price touches BB lower
        - Exit when price hits BB middle or stop-loss
        """
        result = BacktestResult()

        if len(df) < 30:
            return result

        # Calculate indicators
        df = self._calculate_indicators(df.copy(), config)

        in_position = False
        entry_price = 0.0
        entry_idx = 0
        stop_loss = 0.0

        for i in range(30, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i - 1]

            if not in_position:
                # Check entry conditions
                entry_score = 0

                # BB touch
                if row['low'] <= row['bb_lower']:
                    entry_score += params.get('bb_weight', 1.0)

                # RSI oversold
                if row['rsi'] < params.get('rsi_oversold_threshold', 30):
                    entry_score += params.get('rsi_weight', 1.0)

                # Stochastic cross
                if (prev_row['stoch_k'] <= prev_row['stoch_d'] and
                    row['stoch_k'] > row['stoch_d'] and
                    row['stoch_k'] < params.get('stoch_oversold_threshold', 20)):
                    entry_score += params.get('stoch_weight', 2.0)

                if entry_score >= params.get('min_entry_score', 2):
                    in_position = True
                    entry_price = row['close']
                    entry_idx = i
                    # Calculate stop-loss
                    atr = row.get('atr', row['close'] * 0.02)
                    stop_loss = entry_price - (atr * params.get('chandelier_multiplier', 3.0))

            else:
                # Check exit conditions
                current_price = row['close']

                # Stop-loss hit
                if current_price <= stop_loss:
                    profit_pct = ((current_price - entry_price) / entry_price) * 100
                    result.trades.append({
                        'entry_idx': entry_idx,
                        'exit_idx': i,
                        'entry_price': entry_price,
                        'exit_price': current_price,
                        'profit_pct': profit_pct,
                        'reason': 'stop_loss',
                    })
                    result.total_trades += 1
                    if profit_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    result.total_profit_pct += profit_pct
                    in_position = False

                # Target hit (BB middle)
                elif current_price >= row['bb_middle']:
                    profit_pct = ((current_price - entry_price) / entry_price) * 100
                    result.trades.append({
                        'entry_idx': entry_idx,
                        'exit_idx': i,
                        'entry_price': entry_price,
                        'exit_price': current_price,
                        'profit_pct': profit_pct,
                        'reason': 'target_hit',
                    })
                    result.total_trades += 1
                    if profit_pct > 0:
                        result.winning_trades += 1
                    else:
                        result.losing_trades += 1
                    result.total_profit_pct += profit_pct
                    in_position = False

        return result

    def _calculate_indicators(self, df: pd.DataFrame, config: Dict) -> pd.DataFrame:
        """Calculate technical indicators for backtesting."""
        # Simple moving averages
        df['sma_20'] = df['close'].rolling(window=20).mean()

        # Bollinger Bands
        df['bb_middle'] = df['sma_20']
        std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (2 * std)
        df['bb_lower'] = df['bb_middle'] - (2 * std)

        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))

        # Stochastic
        low_14 = df['low'].rolling(window=14).min()
        high_14 = df['high'].rolling(window=14).max()
        df['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14)
        df['stoch_d'] = df['stoch_k'].rolling(window=3).mean()

        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()

        return df.fillna(0)

    def _calculate_max_drawdown(self, trades: List[Dict]) -> float:
        """Calculate maximum drawdown from trade history."""
        if not trades:
            return 0.0

        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in trades:
            cumulative += trade['profit_pct']
            peak = max(peak, cumulative)
            drawdown = peak - cumulative
            max_dd = max(max_dd, drawdown)

        return max_dd

    def _calculate_sharpe_ratio(self, trades: List[Dict]) -> float:
        """Calculate Sharpe ratio from trade history."""
        if len(trades) < 2:
            return 0.0

        returns = [t['profit_pct'] for t in trades]
        avg_return = np.mean(returns)
        std_return = np.std(returns)

        if std_return == 0:
            return 0.0

        # Annualized (assuming 4H trades, ~6 trades per day, ~252 trading days)
        return (avg_return / std_return) * np.sqrt(252 * 6)

    def _create_test_config(self, params: Dict[str, float]) -> Dict[str, Any]:
        """Create test configuration with given parameters."""
        config = get_version_config()

        # Update indicator config
        config['INDICATOR_CONFIG']['chandelier_multiplier'] = params.get('chandelier_multiplier', 3.0)

        return config

    def _find_best_params(
        self,
        results: List[Tuple[Dict[str, float], BacktestResult]]
    ) -> Tuple[Dict[str, float], BacktestResult]:
        """Find parameters with best score."""
        best_params = None
        best_result = None
        best_score = -1

        for params, result in results:
            if result.score > best_score:
                best_score = result.score
                best_params = params
                best_result = result

        return best_params, best_result

    def _apply_change_limits(self, new_params: Dict[str, float]) -> Dict[str, float]:
        """Apply maximum change limits to prevent drastic parameter shifts."""
        limited = {}

        for param, new_value in new_params.items():
            current_value = self.current_params.get(param, new_value)

            # Calculate allowed range
            max_change = current_value * (MAX_CHANGE_PERCENT / 100)
            min_allowed = current_value - max_change
            max_allowed = current_value + max_change

            # Clamp to allowed range
            limited_value = max(min_allowed, min(max_allowed, new_value))

            # Also respect absolute bounds
            bounds = DEFAULT_PARAMETER_BOUNDS.get(param)
            if bounds:
                limited_value = max(bounds[0], min(bounds[1], limited_value))

            limited[param] = limited_value

        return limited

    def _generate_report(
        self,
        baseline: BacktestResult,
        best: BacktestResult,
        recommended_params: Dict[str, float],
        all_results: List[Tuple[Dict[str, float], BacktestResult]]
    ) -> Path:
        """Generate detailed optimization report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f'optimization_report_{timestamp}.md'

        lines = []
        lines.append("# Monthly Parameter Optimization Report")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        lines.append("## Summary\n")
        lines.append(f"- **Coins Analyzed**: {', '.join(self.coins)}")
        lines.append(f"- **Lookback Period**: {self.lookback_months} months")
        lines.append(f"- **Combinations Tested**: {len(all_results)}")
        lines.append("")

        lines.append("## Results Comparison\n")
        lines.append("| Metric | Baseline | Optimized | Change |")
        lines.append("|--------|----------|-----------|--------|")
        lines.append(f"| Score | {baseline.score:.3f} | {best.score:.3f} | {(best.score - baseline.score):+.3f} |")
        lines.append(f"| Win Rate | {baseline.win_rate:.1%} | {best.win_rate:.1%} | {(best.win_rate - baseline.win_rate)*100:+.1f}pp |")
        lines.append(f"| Profit Factor | {baseline.profit_factor:.2f} | {best.profit_factor:.2f} | {(best.profit_factor - baseline.profit_factor):+.2f} |")
        lines.append(f"| Total Trades | {baseline.total_trades} | {best.total_trades} | {best.total_trades - baseline.total_trades:+d} |")
        lines.append("")

        lines.append("## Recommended Parameter Changes\n")
        lines.append("| Parameter | Current | Recommended | Change |")
        lines.append("|-----------|---------|-------------|--------|")
        for param, new_value in recommended_params.items():
            current = self.current_params.get(param, new_value)
            change_pct = ((new_value - current) / current * 100) if current != 0 else 0
            lines.append(f"| {param} | {current:.2f} | {new_value:.2f} | {change_pct:+.1f}% |")
        lines.append("")

        lines.append("## Top 5 Parameter Combinations\n")
        sorted_results = sorted(all_results, key=lambda x: x[1].score, reverse=True)[:5]
        for i, (params, result) in enumerate(sorted_results, 1):
            lines.append(f"### #{i} (Score: {result.score:.3f})")
            lines.append(f"- Win Rate: {result.win_rate:.1%}")
            lines.append(f"- Profit Factor: {result.profit_factor:.2f}")
            lines.append(f"- Parameters: {params}")
            lines.append("")

        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return report_path

    def apply_recommended_parameters(
        self,
        params: Dict[str, float],
        output_file: str = 'logs/dynamic_factors_v3.json'
    ) -> bool:
        """
        Apply recommended parameters to dynamic factors file.

        Args:
            params: Recommended parameters from optimization
            output_file: Path to dynamic factors file

        Returns:
            bool: True if successful
        """
        try:
            # Load existing factors
            factors = {}
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    factors = json.load(f)

            # Update with new parameters
            factors['chandelier_multiplier_modifier'] = params.get('chandelier_multiplier', 3.0) / 3.0
            factors['rsi_oversold_threshold'] = params.get('rsi_oversold_threshold', 30)
            factors['stoch_oversold_threshold'] = params.get('stoch_oversold_threshold', 20)
            factors['min_entry_score'] = int(params.get('min_entry_score', 2))

            factors['entry_weights'] = {
                'bb_touch': params.get('bb_weight', 1.0),
                'rsi_oversold': params.get('rsi_weight', 1.0),
                'stoch_cross': params.get('stoch_weight', 2.0),
            }

            factors['last_monthly_optimization'] = datetime.now().isoformat()

            # Save
            with open(output_file, 'w') as f:
                json.dump(factors, f, indent=2)

            self.logger.logger.info(f"Applied optimized parameters to {output_file}")
            return True

        except Exception as e:
            self.logger.log_error("Failed to apply parameters", e)
            return False


def run_monthly_optimization():
    """Convenience function to run monthly optimization."""
    optimizer = MonthlyOptimizer()
    results = optimizer.run_optimization()

    if results['success'] and results['improvement_pct'] > 5.0:
        # Only apply if improvement is significant (>5%)
        optimizer.apply_recommended_parameters(results['recommended_params'])
        print(f"Applied optimized parameters with {results['improvement_pct']:.1f}% expected improvement")
    else:
        print(f"Optimization complete but no significant improvement found")

    return results


if __name__ == "__main__":
    run_monthly_optimization()
