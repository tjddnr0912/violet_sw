"""
Performance Tracker - Trading Performance Analytics

Tracks and analyzes trading performance for dynamic factor adjustment:
- Win rate calculation
- Profit factor
- Per-condition success rates
- Drawdown monitoring
- Weekly performance summaries

Usage:
    from ver3.performance_tracker import PerformanceTracker

    tracker = PerformanceTracker()
    tracker.record_entry('BTC', 45000000, ['bb_touch', 'rsi_oversold'], 'bullish')
    tracker.record_exit('BTC', 46000000, 50000, 2.2)
    performance = tracker.get_recent_performance(days=7)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import threading


@dataclass
class TradeRecord:
    """Single trade record."""
    coin: str
    entry_time: str  # ISO format string
    exit_time: Optional[str]  # ISO format string
    entry_price: float
    exit_price: Optional[float]
    entry_conditions: List[str]  # ['bb_touch', 'rsi_oversold', etc.]
    profit_krw: float = 0.0
    profit_pct: float = 0.0
    regime: str = "unknown"
    trade_id: str = ""
    status: str = "open"  # 'open' or 'closed'

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'TradeRecord':
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PerformanceTracker:
    """
    Tracks trading performance for dynamic factor optimization.

    Thread-safe implementation for concurrent access from trading bot.

    Features:
    - Record trade entries and exits
    - Calculate win rate, profit factor
    - Track per-condition performance (BB, RSI, Stoch)
    - Generate weekly performance summaries
    - Persist trade history to JSON
    """

    def __init__(
        self,
        history_file: str = 'logs/performance_history_v3.json',
        max_history_size: int = 500  # Rolling window to prevent file bloat
    ):
        """
        Initialize PerformanceTracker.

        Args:
            history_file: Path to persist trade history
            max_history_size: Maximum number of trades to keep in history
        """
        self.history_file = Path(history_file)
        self.max_history_size = max_history_size
        self.trades: List[TradeRecord] = []
        self._lock = threading.Lock()

        self._load_history()

    def record_entry(
        self,
        coin: str,
        entry_price: float,
        entry_conditions: List[str],
        regime: str = "unknown"
    ) -> str:
        """
        Record a new trade entry.

        Args:
            coin: Cryptocurrency symbol (e.g., 'BTC')
            entry_price: Entry price in KRW
            entry_conditions: List of conditions that triggered entry
            regime: Market regime at entry time

        Returns:
            trade_id: Unique identifier for this trade
        """
        with self._lock:
            entry_time = datetime.now()
            trade_id = f"{coin}_{int(entry_time.timestamp())}"

            trade = TradeRecord(
                coin=coin,
                entry_time=entry_time.isoformat(),
                exit_time=None,
                entry_price=entry_price,
                exit_price=None,
                entry_conditions=entry_conditions,
                regime=regime,
                trade_id=trade_id,
                status='open'
            )

            self.trades.append(trade)
            self._save_history()

            return trade_id

    def record_exit(
        self,
        coin: str,
        exit_price: float,
        profit_krw: float,
        profit_pct: float,
        trade_id: str = None
    ) -> bool:
        """
        Record trade exit for most recent open position.

        Args:
            coin: Cryptocurrency symbol
            exit_price: Exit price in KRW
            profit_krw: Profit/loss in KRW
            profit_pct: Profit/loss percentage

        Returns:
            bool: True if exit was recorded, False if no open trade found
        """
        with self._lock:
            # Find the most recent open trade for this coin
            for trade in reversed(self.trades):
                if trade.coin == coin and trade.status == 'open':
                    if trade_id and trade.trade_id != trade_id:
                        continue

                    trade.exit_time = datetime.now().isoformat()
                    trade.exit_price = exit_price
                    trade.profit_krw = profit_krw
                    trade.profit_pct = profit_pct
                    trade.status = 'closed'

                    self._save_history()
                    return True

            return False

    def get_open_trades(self, coin: str = None) -> List[TradeRecord]:
        """Get list of currently open trades."""
        with self._lock:
            if coin:
                return [t for t in self.trades if t.status == 'open' and t.coin == coin]
            return [t for t in self.trades if t.status == 'open']

    def get_recent_performance(self, days: int = 7) -> Dict[str, Any]:
        """
        Get performance metrics for recent period.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with performance metrics:
            - total_trades: int
            - win_rate: float (0.0-1.0)
            - profit_factor: float
            - avg_profit_pct: float
            - total_profit_krw: float
            - max_drawdown_pct: float
            - condition_performance: Dict per entry condition
            - regime_performance: Dict per market regime
            - trades: List of trade records
        """
        with self._lock:
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff.isoformat()

            # Filter closed trades in the period
            recent_trades = [
                t for t in self.trades
                if t.status == 'closed' and t.exit_time and t.exit_time >= cutoff_str
            ]

            if not recent_trades:
                return {
                    'total_trades': 0,
                    'win_rate': 0.5,  # Default neutral
                    'profit_factor': 1.0,
                    'avg_profit_pct': 0.0,
                    'total_profit_krw': 0.0,
                    'max_drawdown_pct': 0.0,
                    'condition_performance': {},
                    'regime_performance': {},
                    'trades': []
                }

            # Calculate basic metrics
            wins = [t for t in recent_trades if t.profit_krw > 0]
            losses = [t for t in recent_trades if t.profit_krw <= 0]

            total_trades = len(recent_trades)
            win_rate = len(wins) / total_trades if total_trades > 0 else 0.5

            gross_profit = sum(t.profit_krw for t in wins)
            gross_loss = abs(sum(t.profit_krw for t in losses))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

            avg_profit_pct = sum(t.profit_pct for t in recent_trades) / total_trades
            total_profit_krw = sum(t.profit_krw for t in recent_trades)

            # Calculate max drawdown
            max_drawdown_pct = self._calculate_max_drawdown(recent_trades)

            # Condition-specific performance
            condition_performance = self._analyze_condition_performance(recent_trades)

            # Regime-specific performance
            regime_performance = self._analyze_regime_performance(recent_trades)

            return {
                'total_trades': total_trades,
                'wins': len(wins),
                'losses': len(losses),
                'win_rate': round(win_rate, 3),
                'profit_factor': round(profit_factor, 2) if profit_factor != float('inf') else 999.0,
                'avg_profit_pct': round(avg_profit_pct, 2),
                'total_profit_krw': round(total_profit_krw, 0),
                'max_drawdown_pct': round(max_drawdown_pct, 2),
                'condition_performance': condition_performance,
                'regime_performance': regime_performance,
                'trades': [t.to_dict() for t in recent_trades]
            }

    def _analyze_condition_performance(self, trades: List[TradeRecord]) -> Dict[str, Dict]:
        """Analyze performance by entry condition."""
        conditions = ['bb_touch', 'rsi_oversold', 'stoch_cross']
        performance = {}

        for condition in conditions:
            cond_trades = [t for t in trades if condition in t.entry_conditions]
            if not cond_trades:
                performance[condition] = {
                    'total': 0,
                    'wins': 0,
                    'win_rate': 0.5,
                    'avg_profit_pct': 0.0
                }
                continue

            cond_wins = [t for t in cond_trades if t.profit_krw > 0]

            performance[condition] = {
                'total': len(cond_trades),
                'wins': len(cond_wins),
                'win_rate': round(len(cond_wins) / len(cond_trades), 3),
                'avg_profit_pct': round(
                    sum(t.profit_pct for t in cond_trades) / len(cond_trades), 2
                )
            }

        return performance

    def _analyze_regime_performance(self, trades: List[TradeRecord]) -> Dict[str, Dict]:
        """Analyze performance by market regime."""
        regimes = ['strong_bullish', 'bullish', 'neutral', 'bearish', 'strong_bearish', 'ranging']
        performance = {}

        for regime in regimes:
            regime_trades = [t for t in trades if t.regime == regime]
            if not regime_trades:
                continue

            regime_wins = [t for t in regime_trades if t.profit_krw > 0]

            performance[regime] = {
                'total': len(regime_trades),
                'wins': len(regime_wins),
                'win_rate': round(len(regime_wins) / len(regime_trades), 3),
                'avg_profit_pct': round(
                    sum(t.profit_pct for t in regime_trades) / len(regime_trades), 2
                ),
                'total_profit_krw': round(sum(t.profit_krw for t in regime_trades), 0)
            }

        return performance

    def _calculate_max_drawdown(self, trades: List[TradeRecord]) -> float:
        """Calculate maximum drawdown percentage from trade sequence."""
        if not trades:
            return 0.0

        # Sort by exit time
        sorted_trades = sorted(trades, key=lambda t: t.exit_time or '')

        # Calculate cumulative P&L and drawdown
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0

        for trade in sorted_trades:
            cumulative += trade.profit_pct
            peak = max(peak, cumulative)
            drawdown = peak - cumulative
            max_dd = max(max_dd, drawdown)

        return max_dd

    def get_weekly_summary(self) -> Dict[str, Any]:
        """Get weekly trading summary for reporting."""
        return self.get_recent_performance(days=7)

    def get_monthly_summary(self) -> Dict[str, Any]:
        """Get monthly trading summary."""
        return self.get_recent_performance(days=30)

    def get_trades_for_weekly_update(self) -> List[Dict]:
        """
        Get trade data formatted for DynamicFactorManager weekly update.

        Returns list of dicts with entry_conditions and profit info.
        """
        perf = self.get_recent_performance(days=7)
        return perf.get('trades', [])

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics."""
        with self._lock:
            closed_trades = [t for t in self.trades if t.status == 'closed']
            open_trades = [t for t in self.trades if t.status == 'open']

            return {
                'total_trades': len(closed_trades),
                'open_trades': len(open_trades),
                'oldest_trade': self.trades[0].entry_time if self.trades else None,
                'newest_trade': self.trades[-1].entry_time if self.trades else None,
            }

    # ========================================
    # Persistence
    # ========================================

    def _load_history(self):
        """Load trade history from file."""
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.trades = [TradeRecord.from_dict(item) for item in data]
        except Exception:
            self.trades = []

    def _save_history(self):
        """Save trade history to file."""
        try:
            # Trim to max size (keep most recent)
            if len(self.trades) > self.max_history_size:
                self.trades = self.trades[-self.max_history_size:]

            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump([t.to_dict() for t in self.trades], f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def clear_history(self):
        """Clear all trade history."""
        with self._lock:
            self.trades = []
            self._save_history()

    def export_to_csv(self, filepath: str) -> bool:
        """
        Export trade history to CSV file.

        Args:
            filepath: Path for CSV output

        Returns:
            bool: True if successful
        """
        try:
            import csv

            with self._lock:
                closed_trades = [t for t in self.trades if t.status == 'closed']

            if not closed_trades:
                return False

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'trade_id', 'coin', 'entry_time', 'exit_time',
                    'entry_price', 'exit_price', 'profit_krw', 'profit_pct',
                    'regime', 'entry_conditions'
                ])

                for trade in closed_trades:
                    writer.writerow([
                        trade.trade_id,
                        trade.coin,
                        trade.entry_time,
                        trade.exit_time,
                        trade.entry_price,
                        trade.exit_price,
                        trade.profit_krw,
                        trade.profit_pct,
                        trade.regime,
                        ','.join(trade.entry_conditions)
                    ])

            return True

        except Exception:
            return False


# Singleton instance
_tracker_instance: Optional[PerformanceTracker] = None

def get_performance_tracker(
    history_file: str = 'logs/performance_history_v3.json'
) -> PerformanceTracker:
    """
    Factory function to get PerformanceTracker singleton.

    Args:
        history_file: Path to history file (only used on first call)

    Returns:
        PerformanceTracker instance
    """
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = PerformanceTracker(history_file)
    return _tracker_instance


def reset_performance_tracker():
    """Reset the singleton instance (for testing)."""
    global _tracker_instance
    _tracker_instance = None
