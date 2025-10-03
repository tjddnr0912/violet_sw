"""
GUI Trading Bot for Version 2 - Integration Adapter

This module bridges the backtrader-based v2 strategy with the GUI.
Since v2 uses backtrader's event-driven architecture (designed for backtesting),
this adapter simulates real-time trading by:

1. Fetching live market data
2. Calculating indicators manually (mimicking backtrader indicators)
3. Evaluating regime filter and entry signals
4. Managing position state
5. Providing status updates to GUI

Note: This is a SIMULATION adapter. For production, consider:
- Using backtrader's live trading broker integration
- Or refactoring v2 logic into standalone classes
"""

import time
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional, Callable
import sys
import os

# Add paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api.bithumb_api import get_candlestick, get_ticker
from ver2 import config_v2


class GUITradingBotV2:
    """
    GUI integration adapter for v2 strategy.

    Simulates v2 strategy behavior in real-time by:
    - Fetching 1D data for regime filter (EMA 50/200)
    - Fetching 4H data for entry signals (BB, RSI, Stoch RSI)
    - Calculating entry score (0-4 points)
    - Managing position state (entry, scaling, exits)
    - Tracking Chandelier Exit trailing stop
    """

    def __init__(self, log_callback: Optional[Callable] = None):
        self.log_callback = log_callback
        self.config = config_v2.get_version_config()
        self.is_running = False

        # Trading mode from config
        self.dry_run = self.config['EXECUTION_CONFIG'].get('dry_run', True)
        self.live_mode = self.config['EXECUTION_CONFIG'].get('mode', 'backtest') == 'live'

        # Strategy state
        self.regime = 'NEUTRAL'
        self.ema_fast = 0
        self.ema_slow = 0
        self.entry_score = 0
        self.entry_components = {
            'bb_touch': 0,
            'rsi_oversold': 0,
            'stoch_cross': 0
        }

        # Position state
        self.position = None
        self.position_phase = 'NONE'
        self.chandelier_stop = 0
        self.highest_high = 0
        self.first_target_hit = False
        self.breakeven_moved = False

        # Performance tracking
        self.total_profit = 0
        self.total_trades = 0
        self.winning_trades = 0

        # Log initialization with mode info
        mode_str = "LIVE TRADING" if (self.live_mode and not self.dry_run) else "DRY-RUN"
        self.log(f"GUITradingBotV2 initialized - Mode: {mode_str}")
        if self.live_mode and not self.dry_run:
            self.log("⚠️ WARNING: REAL TRADING MODE ACTIVE - Real money will be used!")
        elif self.live_mode and self.dry_run:
            self.log("✅ Dry-run mode: Simulating trades without real execution")

    def log(self, message: str):
        """Log message to GUI"""
        if self.log_callback:
            self.log_callback(message)
        else:
            print(f"[BOT] {message}")

    def run(self):
        """Main bot loop (runs in separate thread)"""
        self.is_running = True
        self.log("Bot started - analyzing market every 60 seconds")

        while self.is_running:
            try:
                self.analyze_market()
                time.sleep(60)  # Check every 60 seconds
            except Exception as e:
                self.log(f"Error in bot loop: {str(e)}")
                time.sleep(60)

    def stop(self):
        """Stop bot"""
        self.is_running = False
        self.log("Bot stopped")

    def analyze_market(self):
        """Analyze market and make trading decisions"""
        # Step 1: Check regime filter (Daily)
        self.update_regime_filter()

        if self.regime != 'BULLISH':
            # Bearish or neutral - only manage existing position
            if self.position:
                self.manage_position()
            return

        # Step 2: Bullish regime - check entry signals (4H)
        if not self.position:
            self.check_entry_signals()
        else:
            self.manage_position()

    def update_regime_filter(self):
        """Update regime filter using Daily EMA 50/200"""
        try:
            # Fetch daily data (Bithumb uses '24h' for daily candles, not '1d')
            df = get_candlestick('BTC', '24h')
            if df is None or len(df) < 200:
                self.regime = 'NEUTRAL'
                return

            # Sort by time index (get_candlestick returns DataFrame with 'time' as index)
            df = df.sort_index()

            # Calculate EMA 50 and EMA 200
            closes = df['close'].values
            ema_fast = self.calculate_ema(closes, 50)
            ema_slow = self.calculate_ema(closes, 200)

            self.ema_fast = ema_fast[-1]
            self.ema_slow = ema_slow[-1]

            # Determine regime
            if self.ema_fast > self.ema_slow:
                old_regime = self.regime
                self.regime = 'BULLISH'
                if old_regime != 'BULLISH':
                    self.log(f"Regime changed to BULLISH (EMA50: {self.ema_fast:.0f} > EMA200: {self.ema_slow:.0f})")
            else:
                old_regime = self.regime
                self.regime = 'BEARISH'
                if old_regime != 'BEARISH':
                    self.log(f"Regime changed to BEARISH (EMA50: {self.ema_fast:.0f} <= EMA200: {self.ema_slow:.0f})")

        except Exception as e:
            self.log(f"Error updating regime filter: {str(e)}")
            self.regime = 'NEUTRAL'

    def check_entry_signals(self):
        """Check entry signals on 4H timeframe"""
        try:
            # Fetch 4H data
            df = get_candlestick('BTC', '4h')
            if df is None or len(df) < 50:
                return

            # Sort by time index (get_candlestick returns DataFrame with 'time' as index)
            df = df.sort_index()

            # Calculate indicators
            df = self.calculate_indicators_4h(df)

            # Get latest values
            latest = df.iloc[-1]
            prev = df.iloc[-2]

            # Calculate entry score
            score = 0
            components = {'bb_touch': 0, 'rsi_oversold': 0, 'stoch_cross': 0}

            # Component 1: BB Lower Touch (+1)
            if latest['low'] <= latest['bb_lower']:
                score += 1
                components['bb_touch'] = 1

            # Component 2: RSI Oversold (+1)
            if latest['rsi'] < 30:
                score += 1
                components['rsi_oversold'] = 1

            # Component 3: Stoch RSI Cross (+2)
            if self.detect_stoch_cross(latest, prev):
                score += 2
                components['stoch_cross'] = 2

            self.entry_score = score
            self.entry_components = components

            # Entry decision
            if score >= 3:
                self.log(f"ENTRY SIGNAL: Score {score}/4 - {components}")
                self.execute_entry(latest)

        except Exception as e:
            self.log(f"Error checking entry signals: {str(e)}")

    def execute_entry(self, bar: pd.Series):
        """Execute entry with 50% position"""
        try:
            entry_price = bar['close']
            atr = bar['atr']

            # Calculate position size (simplified - 2% risk)
            stop_distance = atr * 3.0
            stop_price = entry_price - stop_distance

            # Check if real trading is enabled
            if self.live_mode and not self.dry_run:
                # REAL TRADING MODE
                self.log("🚨 REAL TRADING: Attempting to execute LIVE order...")
                # TODO: Integrate with live_executor_v2.py for actual order placement
                # from live_executor_v2 import LiveExecutorV2
                # executor = LiveExecutorV2(self.config)
                # order_result = executor.place_buy_order('BTC', amount)
                self.log("⚠️ Real order execution not yet connected to live_executor_v2.py")
                self.log("   For now, operating in simulation mode")

            # Initialize position (works for both dry-run and live)
            self.position = {
                'entry_price': entry_price,
                'entry_time': datetime.now(),
                'entry_score': self.entry_score,
                'entry_size': 0.01,  # Placeholder
                'stop_price': stop_price,
                'atr_at_entry': atr
            }

            self.position_phase = 'INITIAL_ENTRY'
            self.chandelier_stop = stop_price
            self.highest_high = bar['high']
            self.first_target_hit = False
            self.breakeven_moved = False

            mode_prefix = "🔴 LIVE" if (self.live_mode and not self.dry_run) else "💚 DRY-RUN"
            self.log(f"{mode_prefix} ENTRY EXECUTED: Price ${entry_price:.0f}, Stop ${stop_price:.0f}")
            self.log(f"  Score: {self.entry_score}/4, Components: {self.entry_components}")

        except Exception as e:
            self.log(f"Error executing entry: {str(e)}")

    def manage_position(self):
        """Manage existing position"""
        if not self.position:
            return

        try:
            # Fetch current 4H bar
            df = get_candlestick('BTC', '4h')
            if df is None:
                return

            # Sort by time index (get_candlestick returns DataFrame with 'time' as index)
            df = df.sort_index()
            df = self.calculate_indicators_4h(df)

            latest = df.iloc[-1]

            # Update highest high
            if latest['high'] > self.highest_high:
                self.highest_high = latest['high']

            # Update Chandelier stop (trails upward only)
            new_stop = self.highest_high - (latest['atr'] * 3.0)
            if new_stop > self.chandelier_stop:
                old_stop = self.chandelier_stop
                self.chandelier_stop = new_stop
                self.log(f"STOP TRAILED: ${old_stop:.0f} -> ${new_stop:.0f}")

            # Check exits
            # Exit 1: Chandelier stop hit
            if latest['low'] <= self.chandelier_stop:
                exit_type = "BREAKEVEN" if self.breakeven_moved else "STOP_LOSS"
                self.execute_exit(latest['close'], exit_type)
                return

            # Exit 2: Final target (BB Upper)
            if latest['high'] >= latest['bb_upper']:
                self.execute_exit(latest['bb_upper'], "FINAL_TARGET")
                return

            # Scaling: First target (BB Middle)
            if not self.first_target_hit and latest['high'] >= latest['bb_mid']:
                self.log(f"FIRST TARGET HIT: ${latest['bb_mid']:.0f}")
                self.chandelier_stop = self.position['entry_price']
                self.first_target_hit = True
                self.breakeven_moved = True
                self.position_phase = 'RISK_FREE_RUNNER'
                self.log("  Stop moved to BREAKEVEN")

        except Exception as e:
            self.log(f"Error managing position: {str(e)}")

    def execute_exit(self, exit_price: float, exit_type: str):
        """Execute exit and calculate P&L"""
        if not self.position:
            return

        entry_price = self.position['entry_price']
        pnl = exit_price - entry_price
        pnl_pct = (pnl / entry_price) * 100

        # Check if real trading is enabled
        if self.live_mode and not self.dry_run:
            # REAL TRADING MODE
            self.log("🚨 REAL TRADING: Attempting to execute LIVE exit order...")
            # TODO: Integrate with live_executor_v2.py for actual order placement
            # from live_executor_v2 import LiveExecutorV2
            # executor = LiveExecutorV2(self.config)
            # order_result = executor.place_sell_order('BTC', amount)
            self.log("⚠️ Real order execution not yet connected to live_executor_v2.py")
            self.log("   For now, operating in simulation mode")

        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1
            self.total_profit += pnl

        mode_prefix = "🔴 LIVE" if (self.live_mode and not self.dry_run) else "💚 DRY-RUN"
        self.log(f"{mode_prefix} EXIT: {exit_type} at ${exit_price:.0f}")
        self.log(f"  P&L: ${pnl:+.0f} ({pnl_pct:+.2f}%)")
        self.log(f"  Total Trades: {self.total_trades}, Win Rate: {self.get_win_rate():.1f}%")

        # Reset position
        self.position = None
        self.position_phase = 'NONE'
        self.chandelier_stop = 0
        self.highest_high = 0
        self.first_target_hit = False
        self.breakeven_moved = False

    def calculate_indicators_4h(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate 4H indicators"""
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

    def detect_stoch_cross(self, current: pd.Series, prev: pd.Series) -> bool:
        """Detect Stochastic RSI bullish crossover"""
        k_curr = current['stoch_k']
        k_prev = prev['stoch_k']
        d_curr = current['stoch_d']
        d_prev = prev['stoch_d']

        # Crossover: K was below D, now above D
        crossover = (k_prev < d_prev) and (k_curr > d_curr)

        # Oversold zone
        in_oversold = (k_curr < 20) and (d_curr < 20)

        return crossover and in_oversold

    def calculate_ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calculate EMA"""
        ema = pd.Series(data).ewm(span=period, adjust=False).mean()
        return ema.values

    def get_status(self) -> Dict[str, Any]:
        """Get current bot status for GUI"""
        status = {
            'regime': self.regime,
            'ema_fast': self.ema_fast,
            'ema_slow': self.ema_slow,
            'entry_score': self.entry_score,
            'entry_components': self.entry_components,
            'position_phase': self.position_phase,
            'chandelier_stop': self.chandelier_stop,
            'highest_high': self.highest_high,
            'first_target_hit': self.first_target_hit,
            'breakeven_moved': self.breakeven_moved,
            'total_profit': self.total_profit,
            'total_trades': self.total_trades,
            'win_rate': self.get_win_rate(),
            'last_action': self.get_last_action()
        }

        # Add position details if exists
        if self.position:
            status['entry_price'] = self.position['entry_price']
            status['position_size'] = self.position['entry_size']
        else:
            status['entry_price'] = 0
            status['position_size'] = 0

        return status

    def get_win_rate(self) -> float:
        """Calculate win rate"""
        if self.total_trades == 0:
            return 0.0
        return (self.winning_trades / self.total_trades) * 100

    def get_last_action(self) -> str:
        """Get last action string"""
        if self.position:
            if self.position_phase == 'RISK_FREE_RUNNER':
                return 'HOLDING (RISK-FREE)'
            else:
                return 'HOLDING'
        elif self.entry_score >= 3:
            return 'SIGNAL DETECTED'
        else:
            return 'WAITING'


# Test function
if __name__ == "__main__":
    def test_log(msg):
        print(f"[TEST] {msg}")

    bot = GUITradingBotV2(log_callback=test_log)
    bot.analyze_market()

    status = bot.get_status()
    print("\nBot Status:")
    for key, value in status.items():
        print(f"  {key}: {value}")
