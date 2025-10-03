"""
Bitcoin Multi-Timeframe Trading Strategy v2.0 - Backtrader Implementation

This is the main strategy class that orchestrates all components using Backtrader's
event-driven architecture.

Architecture Pattern: Dependency Injection
- All complex logic delegated to specialized modules
- Strategy class acts as orchestrator/coordinator

Components:
- RegimeFilter: Daily EMA 50/200 crossover filter
- IndicatorCalculator: Technical indicators (BB, RSI, Stoch RSI, ATR)
- EntrySignalScorer: Score-based entry system (3+ points required)
- PositionManager: Position sizing and Chandelier Exit
- RiskManager: Risk guardrails and circuit breakers
"""

import backtrader as bt
from datetime import datetime, date
from typing import Optional

from .regime_filter_v2 import RegimeFilter
from .indicators_v2 import IndicatorCalculator
from .entry_signals_v2 import EntrySignalScorer
from .position_manager_v2 import PositionManager
from .risk_manager_v2 import RiskManager


class BitcoinMultiTimeframeStrategy(bt.Strategy):
    """
    Main strategy class implementing multi-timeframe trend-following system.

    Data Feed Requirements:
    - datas[0]: Daily timeframe (for regime filter)
    - datas[1]: 4-Hour timeframe (for entry/exit signals)

    Strategy Flow:
    1. Check regime filter (daily) → Only trade in bullish regime
    2. If bullish: Evaluate entry signals (4H) using scoring system
    3. If entry signal (3+ points): Execute 50% position entry
    4. Manage position: Chandelier trailing stop, scaling exits at BB mid/upper
    5. Risk checks: Consecutive losses, daily loss limits, trade count
    """

    # ========== STRATEGY PARAMETERS ==========
    params = (
        # Position Management
        ('risk_per_trade', 0.02),           # 2% risk per trade
        ('initial_position_pct', 0.50),     # 50% initial entry
        ('first_exit_pct', 0.50),           # 50% exit at first target

        # Entry/Exit Configuration
        ('entry_score_threshold', 3),       # Minimum score for entry (3-4)
        ('atr_multiplier', 3.0),            # Chandelier Exit multiplier

        # Risk Management
        ('max_consecutive_losses', 5),      # Circuit breaker
        ('max_daily_loss_pct', 0.05),       # 5% daily loss limit
        ('max_daily_trades', 2),            # Max trades per day

        # Indicator Parameters (4H)
        ('bb_period', 20),
        ('bb_std', 2.0),
        ('rsi_period', 14),
        ('stoch_rsi_period', 14),
        ('stoch_k_smooth', 3),
        ('stoch_d_smooth', 3),
        ('atr_period', 14),

        # Regime Filter Parameters (Daily)
        ('ema_fast', 50),
        ('ema_slow', 200),
        ('regime_confirmation_bars', 2),     # Hysteresis buffer

        # Debug & Logging
        ('debug_mode', True),
    )

    def __init__(self):
        """
        Initialize strategy components and data feeds.

        This method is called once at the start of backtesting.
        All indicators and modules are initialized here.
        """
        print("="*60)
        print("Initializing Bitcoin Multi-Timeframe Strategy v2.0")
        print("="*60)

        # ===== DATA FEEDS =====
        self.data_daily = self.datas[0]  # Daily timeframe
        self.data_4h = self.datas[1]     # 4-Hour timeframe

        print(f"📊 Data feeds loaded:")
        print(f"   Daily: {self.data_daily._name}")
        print(f"   4H: {self.data_4h._name}")

        # ===== REGIME FILTER (Daily Timeframe) =====
        print(f"\n🔍 Initializing regime filter...")
        self.regime_filter = RegimeFilter(
            data=self.data_daily,
            ema_fast_period=self.params.ema_fast,
            ema_slow_period=self.params.ema_slow,
            confirmation_bars=self.params.regime_confirmation_bars
        )
        print(f"   EMA Fast: {self.params.ema_fast}, EMA Slow: {self.params.ema_slow}")

        # ===== INDICATOR CALCULATOR (4H Timeframe) =====
        print(f"\n📈 Initializing indicators...")
        indicator_config = {
            'bb_period': self.params.bb_period,
            'bb_std': self.params.bb_std,
            'rsi_period': self.params.rsi_period,
            'stoch_rsi_period': self.params.stoch_rsi_period,
            'stoch_rsi_k_smooth': self.params.stoch_k_smooth,
            'stoch_rsi_d_smooth': self.params.stoch_d_smooth,
            'atr_period': self.params.atr_period,
        }
        self.indicator_calc = IndicatorCalculator(
            data=self.data_4h,
            config=indicator_config
        )
        print(f"   BB({self.params.bb_period}, {self.params.bb_std})")
        print(f"   RSI({self.params.rsi_period})")
        print(f"   Stoch RSI({self.params.stoch_rsi_period})")
        print(f"   ATR({self.params.atr_period})")

        # ===== ENTRY SIGNAL SCORER =====
        print(f"\n🎯 Initializing entry signal scorer...")
        self.entry_scorer = EntrySignalScorer(
            indicators=self.indicator_calc,
            threshold=self.params.entry_score_threshold
        )
        print(f"   Entry threshold: {self.params.entry_score_threshold}/4 points")

        # ===== POSITION MANAGER =====
        print(f"\n💼 Initializing position manager...")
        self.position_manager = PositionManager(
            strategy=self,
            atr_multiplier=self.params.atr_multiplier,
            indicators=self.indicator_calc,
            initial_pct=self.params.initial_position_pct,
            first_exit_pct=self.params.first_exit_pct
        )
        print(f"   Initial entry: {self.params.initial_position_pct*100:.0f}%")
        print(f"   First exit: {self.params.first_exit_pct*100:.0f}%")
        print(f"   Chandelier multiplier: {self.params.atr_multiplier}x ATR")

        # ===== RISK MANAGER =====
        print(f"\n🛡️  Initializing risk manager...")
        self.risk_manager = RiskManager(
            max_consecutive_losses=self.params.max_consecutive_losses,
            max_daily_loss_pct=self.params.max_daily_loss_pct,
            max_daily_trades=self.params.max_daily_trades
        )
        print(f"   Max consecutive losses: {self.params.max_consecutive_losses}")
        print(f"   Max daily loss: {self.params.max_daily_loss_pct*100:.1f}%")
        print(f"   Max daily trades: {self.params.max_daily_trades}")

        # ===== STATE TRACKING =====
        self.trade_count = 0
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.current_date = None
        self.initial_capital = self.broker.get_value()

        print(f"\n💰 Initial capital: ${self.initial_capital:.2f}")
        print("="*60)
        print("Strategy initialization complete. Ready for backtest.\n")

    def next(self):
        """
        Main strategy logic executed on every 4H bar close.

        Execution Flow:
        1. Check for new trading day (reset daily counters)
        2. Check regime filter (daily timeframe)
        3. If bearish regime: Only manage existing positions
        4. If bullish regime: Evaluate entry signals
        5. If entry signal & risk checks pass: Execute entry
        6. If position exists: Manage exits and trailing stops
        """
        # ===== STEP 0: Check for New Trading Day =====
        current_date = self.data_4h.datetime.date(0)
        if self.current_date != current_date:
            # New day started - reset daily counters
            if self.current_date is not None:
                self.log(f"📅 New trading day: {current_date}, Daily P&L: ${self.daily_pnl:.2f}")
            self.current_date = current_date
            self.daily_pnl = 0.0
            self.daily_trade_count = 0

        # ===== STEP 1: Check Regime Filter (Daily Timeframe) =====
        regime_status = self.regime_filter.get_current_regime()

        if regime_status != "BULLISH":
            # Bearish or neutral regime - only manage existing positions
            if self.position:
                self.position_manager.manage_existing_position(self.data_4h)
            return  # Skip entry logic

        # ===== STEP 2: Entry Signal Evaluation (4H Timeframe) =====
        if not self.position:
            # No existing position - check for entry signals
            entry_signal, score, reasons = self.entry_scorer.calculate_entry_score(
                current_bar=self.data_4h
            )

            if entry_signal:
                # Entry signal detected - validate with risk manager
                if self.risk_manager.validate_entry(
                    consecutive_losses=self.consecutive_losses,
                    daily_pnl=self.daily_pnl,
                    portfolio_value=self.broker.get_value(),
                    daily_trade_count=self.daily_trade_count
                ):
                    self.execute_entry(score, reasons)
                else:
                    self.log(f"⛔ Entry REJECTED by risk manager (Score: {score}/4)")

        # ===== STEP 3: Position Management =====
        else:
            self.position_manager.manage_existing_position(self.data_4h)

    def execute_entry(self, score: int, reasons: list):
        """
        Execute entry order with proper position sizing.

        Args:
            score: Entry signal score (3-4)
            reasons: List of reason strings for the entry
        """
        try:
            # Calculate position size based on 2% risk
            entry_data = self.position_manager.calculate_entry_size(
                entry_price=self.data_4h.close[0],
                atr=self.indicator_calc.atr[0],
                portfolio_value=self.broker.get_value(),
                risk_per_trade=self.params.risk_per_trade
            )

            # Execute buy order
            order = self.buy(size=entry_data['entry_size'])

            # Initialize position tracking
            self.position_manager.initialize_position(
                entry_price=entry_data['entry_price'],
                entry_size=entry_data['entry_size'],
                full_size=entry_data['full_size'],
                initial_stop=entry_data['initial_stop'],
                entry_score=score
            )

            self.trade_count += 1
            self.daily_trade_count += 1

            self.log(f"✅ ENTRY EXECUTED:")
            self.log(f"   Price: ${entry_data['entry_price']:.2f}")
            self.log(f"   Size: {entry_data['entry_size']:.4f} BTC")
            self.log(f"   Stop: ${entry_data['initial_stop']:.2f}")
            self.log(f"   Score: {score}/4 - {', '.join(reasons)}")
            self.log(f"   Risk: ${entry_data['max_risk_usd']:.2f} (2% of portfolio)")

        except Exception as e:
            self.log(f"❌ Entry execution error: {str(e)}")

    def notify_order(self, order):
        """
        Handle order execution notifications from broker.

        Args:
            order: Backtrader order object
        """
        if order.status in [order.Submitted, order.Accepted]:
            # Order submitted/accepted - waiting for execution
            return

        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"   BUY FILLED: "
                    f"Price=${order.executed.price:.2f}, "
                    f"Size={order.executed.size:.4f}, "
                    f"Cost=${order.executed.value:.2f}, "
                    f"Comm=${order.executed.comm:.2f}"
                )
            elif order.issell():
                self.log(
                    f"   SELL FILLED: "
                    f"Price=${order.executed.price:.2f}, "
                    f"Size={order.executed.size:.4f}, "
                    f"Value=${order.executed.value:.2f}, "
                    f"Comm=${order.executed.comm:.2f}"
                )

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log(f"⚠️  Order Status: {order.getstatusname()}")

    def notify_trade(self, trade):
        """
        Handle trade closure notifications.

        This is called when a position is completely closed.
        We use it to track consecutive losses and update daily P&L.

        Args:
            trade: Backtrader trade object
        """
        if not trade.isclosed:
            return

        # Trade closed - calculate P&L
        pnl = trade.pnl
        pnl_pct = (pnl / trade.value) * 100 if trade.value != 0 else 0

        self.daily_pnl += pnl

        # Update consecutive loss counter
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # Log trade closure
        self.log(f"💰 TRADE CLOSED:")
        self.log(f"   P&L: ${pnl:.2f} ({pnl_pct:+.2f}%)")
        self.log(f"   Consecutive Losses: {self.consecutive_losses}")
        self.log(f"   Daily P&L: ${self.daily_pnl:.2f}")
        self.log(f"   Portfolio Value: ${self.broker.get_value():.2f}")

        # Reset position manager state
        self.position_manager.reset_position_state()

    def log(self, message: str):
        """
        Custom logging with timestamp.

        Args:
            message: Log message
        """
        if self.params.debug_mode:
            dt = self.data_4h.datetime.datetime(0)
            print(f"{dt.strftime('%Y-%m-%d %H:%M')} | {message}")

    def stop(self):
        """
        Called at the end of backtesting.

        Print final statistics and performance metrics.
        """
        print("\n" + "="*60)
        print("BACKTEST COMPLETE - Final Statistics")
        print("="*60)

        final_value = self.broker.get_value()
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100

        print(f"Initial Capital: ${self.initial_capital:.2f}")
        print(f"Final Value: ${final_value:.2f}")
        print(f"Total Return: {total_return:+.2f}%")
        print(f"Total Trades: {self.trade_count}")
        print(f"Final Consecutive Losses: {self.consecutive_losses}")
        print("="*60 + "\n")
