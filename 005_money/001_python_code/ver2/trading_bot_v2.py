"""
Trading Bot V2 - Live Trading Execution for Multi-Timeframe Strategy

This module implements the live trading bot for Version 2 strategy,
handling real-time data fetching, signal generation, and trade execution.

Architecture:
- Fetches multi-timeframe data (1D + 4H) from Bithumb
- Uses StrategyV2 for signal generation
- Delegates order execution to LiveExecutorV2
- Integrates with existing logging and configuration systems

Usage:
    from ver2.trading_bot_v2 import TradingBotV2

    bot = TradingBotV2()
    bot.authenticate()
    bot.run_trading_cycle()
"""

import time
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

# Add parent directory to path for lib imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.api.bithumb_api import BithumbAPI, get_candlestick, get_ticker
from lib.core.logger import TradingLogger, TransactionHistory, MarkdownTransactionLogger
from lib.core.portfolio_manager import PortfolioManager
import config  # Global config compatibility layer

from .strategy_v2 import StrategyV2
from .config_v2 import get_version_config


class TradingBotV2:
    """
    Version 2 Live Trading Bot

    Features:
    - Multi-timeframe data handling (1D regime + 4H execution)
    - Score-based entry system (3+ points required)
    - Position scaling management (50% initial, scale at BB mid)
    - Chandelier Exit stop-loss
    - Safety features: dry-run, daily limits, consecutive loss tracking
    """

    def __init__(self, config_override: Dict[str, Any] = None):
        """
        Initialize Trading Bot V2.

        Args:
            config_override: Optional configuration overrides
        """
        # Load configurations
        self.v2_config = get_version_config()
        self.global_config = config.get_config()

        # Apply overrides if provided
        if config_override:
            self.v2_config.update(config_override)

        # Initialize logger
        log_dir = self.global_config.get('logging', {}).get('log_dir', 'logs')
        self.logger = TradingLogger(log_dir)
        self.transaction_history = TransactionHistory()
        self.markdown_logger = MarkdownTransactionLogger()

        # Initialize API
        api_config = self.global_config.get('api', {})
        self.api = BithumbAPI(
            connect_key=api_config.get('connect_key'),
            secret_key=api_config.get('secret_key')
        )

        # Initialize strategy
        self.strategy = StrategyV2(config=self.v2_config, logger=self.logger)

        # Initialize portfolio manager
        self.portfolio_manager = PortfolioManager(self.api, self.transaction_history)

        # Trading state
        self.is_authenticated = False
        self.current_position = self._load_position_state()
        self.daily_trade_count = 0
        self.consecutive_losses = 0
        self.last_trade_time = None
        self.current_date = None

        self.logger.logger.info("="*60)
        self.logger.logger.info("Trading Bot V2 Initialized")
        self.logger.logger.info(f"Strategy: {self.strategy.VERSION_DISPLAY_NAME}")
        self.logger.logger.info("="*60)

    # ========== AUTHENTICATION ==========

    def authenticate(self) -> bool:
        """
        Authenticate with Bithumb API and verify access.

        Returns:
            True if authentication successful
        """
        try:
            safety_config = self.global_config.get('safety', {})

            if safety_config.get('dry_run', True):
                self.logger.logger.info("🔧 Running in DRY-RUN mode (no real trades)")
                self.is_authenticated = True
                return True

            # In live mode, authentication happens during first trade
            self.is_authenticated = True
            self.logger.logger.info("✅ API authentication ready (verified on first trade)")
            return True

        except Exception as e:
            self.logger.log_error("Authentication failed", e)
            return False

    # ========== DATA FETCHING ==========

    def fetch_multi_timeframe_data(
        self,
        ticker: str
    ) -> Tuple[Optional[Any], Optional[Any]]:
        """
        Fetch data for both timeframes (1D and 4H).

        Args:
            ticker: Cryptocurrency symbol (e.g., 'BTC')

        Returns:
            Tuple of (daily_data, hourly_data) DataFrames
        """
        try:
            timeframe_config = self.v2_config.get('TIMEFRAME_CONFIG', {})

            # Fetch daily data for regime filter
            regime_interval = timeframe_config.get('regime_interval', '24h')  # Bithumb uses '24h' not '1d'
            regime_candles = timeframe_config.get('regime_candles', 250)

            self.logger.logger.debug(f"Fetching {regime_interval} data")
            daily_data = get_candlestick(ticker, regime_interval)

            if daily_data is None or len(daily_data) < 200:
                self.logger.logger.warning(
                    f"Insufficient daily data: {len(daily_data) if daily_data is not None else 0} candles"
                )
                return None, None

            # Fetch 4H data for execution
            exec_interval = timeframe_config.get('execution_interval', '4h')
            exec_candles = timeframe_config.get('execution_candles', 200)

            self.logger.logger.debug(f"Fetching {exec_interval} data")
            hourly_data = get_candlestick(ticker, exec_interval)

            if hourly_data is None or len(hourly_data) < 50:
                self.logger.logger.warning(
                    f"Insufficient 4H data: {len(hourly_data) if hourly_data is not None else 0} candles"
                )
                return None, None

            self.logger.logger.info(
                f"✅ Data fetched: {len(daily_data)} daily, {len(hourly_data)} 4H candles"
            )

            return daily_data, hourly_data

        except Exception as e:
            self.logger.log_error(f"Error fetching multi-timeframe data for {ticker}", e)
            return None, None

    # ========== POSITION MANAGEMENT ==========

    def _load_position_state(self) -> Dict[str, Any]:
        """
        Load current position state from transaction history.

        Returns:
            Dictionary with position details
        """
        return {
            'size': 0.0,
            'entry_price': 0.0,
            'entry_time': None,
            'highest_high': 0.0,
            'position_pct': 0.0,  # 0-100, where 100 is full position
            'stop_loss': 0.0,
            'first_target_hit': False,
        }

    def _save_position_state(self):
        """Save current position state to persistent storage."""
        # TODO: Implement position state persistence (JSON file or database)
        pass

    def _update_position_from_balance(self, ticker: str):
        """
        Update position state from actual account balance.

        Args:
            ticker: Cryptocurrency symbol
        """
        try:
            if self.global_config.get('safety', {}).get('dry_run', True):
                # In dry-run, calculate from transaction history
                self.current_position['size'] = self._calculate_position_from_history(ticker)
            else:
                # In live mode, query actual balance
                balance = self.api.get_balance(ticker)
                if balance and balance.get('status') == '0000':
                    data = balance.get('data', {})
                    available = float(data.get(f'available_{ticker.lower()}', 0))
                    in_use = float(data.get(f'in_use_{ticker.lower()}', 0))
                    self.current_position['size'] = available + in_use

        except Exception as e:
            self.logger.log_error(f"Error updating position from balance: {ticker}", e)

    def _calculate_position_from_history(self, ticker: str) -> float:
        """Calculate position size from transaction history (for dry-run mode)."""
        try:
            position = 0.0
            for tx in self.transaction_history.transactions:
                if tx.get('ticker') == ticker and tx.get('success'):
                    if tx.get('action') == 'BUY':
                        position += tx.get('amount', 0.0)
                    elif tx.get('action') == 'SELL':
                        position -= tx.get('amount', 0.0)

            return max(0.0, position)

        except Exception as e:
            self.logger.log_error(f"Error calculating position from history: {ticker}", e)
            return 0.0

    # ========== TRADE EXECUTION ==========

    def execute_trade(
        self,
        ticker: str,
        action: str,
        amount: float,
        price: float,
        reason: str = ""
    ) -> bool:
        """
        Execute a trade (buy or sell).

        Args:
            ticker: Cryptocurrency symbol
            action: 'BUY' or 'SELL'
            amount: Amount to trade in units of cryptocurrency
            price: Current price (for dry-run)
            reason: Reason for trade

        Returns:
            True if trade executed successfully
        """
        try:
            safety_config = self.global_config.get('safety', {})

            if safety_config.get('dry_run', True):
                # Dry-run mode - simulate trade
                total_value = amount * price
                order_id = f"DRY_RUN_{int(time.time())}_{action}"

                self.logger.logger.info(
                    f"[DRY-RUN] {action}: {amount:.6f} {ticker} @ {price:,.0f} KRW "
                    f"(Total: {total_value:,.0f} KRW) | Reason: {reason}"
                )

                # Record transaction
                fee = total_value * self.global_config.get('trading', {}).get('trading_fee_rate', 0.0005)

                self.transaction_history.add_transaction(
                    ticker=ticker,
                    action=action,
                    amount=amount,
                    price=price,
                    order_id=order_id,
                    fee=fee,
                    success=True
                )

                # Log to markdown
                self.markdown_logger.log_transaction(
                    ticker=ticker,
                    action=action,
                    amount=amount,
                    price=price,
                    order_id=order_id,
                    fee=fee,
                    success=True,
                    transaction_history=self.transaction_history
                )

                # Update position
                if action == 'BUY':
                    self.current_position['size'] += amount
                    if self.current_position['entry_price'] == 0:
                        self.current_position['entry_price'] = price
                        self.current_position['entry_time'] = datetime.now()
                    else:
                        # Update average entry price for scaling
                        old_value = self.current_position['size'] * self.current_position['entry_price']
                        new_value = amount * price
                        self.current_position['entry_price'] = (old_value + new_value) / (self.current_position['size'] + amount)

                elif action == 'SELL':
                    self.current_position['size'] -= amount
                    if self.current_position['size'] <= 0:
                        # Position fully closed
                        self.current_position = self._load_position_state()

                self.daily_trade_count += 1
                self.last_trade_time = datetime.now()

                return True

            else:
                # Live mode - execute real trade
                self.logger.logger.warning("🔴 LIVE TRADING MODE - Executing real trade!")

                if action == 'BUY':
                    response = self.api.place_buy_order(ticker, units=amount)
                elif action == 'SELL':
                    response = self.api.place_sell_order(ticker, units=amount)
                else:
                    return False

                if response and response.get('status') == '0000':
                    order_id = response.get('order_id', 'N/A')
                    total_value = amount * price

                    self.logger.log_trade_execution(
                        ticker, action, amount, price, order_id, True
                    )

                    # Record transaction
                    fee = total_value * self.global_config.get('trading', {}).get('trading_fee_rate', 0.0005)

                    self.transaction_history.add_transaction(
                        ticker=ticker,
                        action=action,
                        amount=amount,
                        price=price,
                        order_id=order_id,
                        fee=fee,
                        success=True
                    )

                    self.markdown_logger.log_transaction(
                        ticker=ticker,
                        action=action,
                        amount=amount,
                        price=price,
                        order_id=order_id,
                        fee=fee,
                        success=True,
                        transaction_history=self.transaction_history
                    )

                    self.daily_trade_count += 1
                    self.last_trade_time = datetime.now()

                    return True
                else:
                    error_msg = response.get('message', 'Unknown error') if response else 'No response'
                    self.logger.log_error(f"Trade execution failed: {error_msg}")
                    return False

        except Exception as e:
            self.logger.log_error(f"Error executing trade: {action} {ticker}", e)
            return False

    # ========== SAFETY CHECKS ==========

    def check_safety_limits(self) -> Tuple[bool, str]:
        """
        Check if it's safe to trade based on safety limits.

        Returns:
            Tuple of (is_safe, reason)
        """
        safety_config = self.global_config.get('safety', {})
        risk_config = self.v2_config.get('RISK_CONFIG', {})

        # Check emergency stop
        if safety_config.get('emergency_stop', False):
            return False, "Emergency stop activated"

        # Check daily trade limit
        max_daily_trades = risk_config.get('max_daily_trades', 5)
        if self.daily_trade_count >= max_daily_trades:
            return False, f"Daily trade limit reached: {self.daily_trade_count}/{max_daily_trades}"

        # Check consecutive losses
        max_consecutive_losses = risk_config.get('max_consecutive_losses', 3)
        if self.consecutive_losses >= max_consecutive_losses:
            return False, f"Consecutive loss limit reached: {self.consecutive_losses}/{max_consecutive_losses}"

        # All checks passed
        return True, "All safety checks passed"

    # ========== TRADING CYCLE ==========

    def run_trading_cycle(self) -> bool:
        """
        Execute one complete trading cycle.

        Flow:
        1. Fetch multi-timeframe data
        2. Check market regime (daily)
        3. Calculate entry score (4H)
        4. Generate trading signal
        5. Check safety limits
        6. Execute trade if signal generated
        7. Manage existing position

        Returns:
            True if cycle completed successfully
        """
        try:
            # Check for new trading day
            current_date = datetime.now().date()
            if self.current_date != current_date:
                if self.current_date is not None:
                    self.logger.logger.info(
                        f"📅 New trading day: {current_date} | "
                        f"Yesterday trades: {self.daily_trade_count}"
                    )
                self.current_date = current_date
                self.daily_trade_count = 0

            # Get target ticker
            ticker = self.global_config.get('trading', {}).get('target_ticker', 'BTC')
            self.logger.logger.info(f"\n{'='*60}")
            self.logger.logger.info(f"Trading Cycle Start: {ticker} | {datetime.now()}")
            self.logger.logger.info(f"{'='*60}")

            # Authenticate if needed
            if not self.is_authenticated:
                if not self.authenticate():
                    self.logger.logger.error("Authentication failed, skipping cycle")
                    return False

            # Fetch multi-timeframe data
            daily_data, hourly_data = self.fetch_multi_timeframe_data(ticker)

            if daily_data is None or hourly_data is None:
                self.logger.logger.error("Failed to fetch market data")
                return False

            # Check regime (daily timeframe)
            regime = self.strategy.check_regime(daily_data)
            self.logger.logger.info(f"Market Regime: {regime}")

            if regime != 'BULLISH':
                self.logger.logger.info(
                    f"⏸️  Holding - Market regime is {regime}, only trading in BULLISH"
                )

                # Still manage existing position if any
                if self.current_position['size'] > 0:
                    self._manage_existing_position(ticker, hourly_data)

                return True

            # Calculate indicators
            indicators = self.strategy.calculate_indicators(hourly_data)

            # Calculate entry score
            entry_score, score_details = self.strategy.calculate_entry_score(
                hourly_data, indicators
            )

            self.logger.logger.info(
                f"Entry Score: {entry_score}/4 | Details: {score_details.get('breakdown', [])}"
            )

            # Generate entry signal
            signal = self.strategy.generate_entry_signal(
                regime=regime,
                score=entry_score,
                current_position=self.current_position['size']
            )

            self.logger.logger.info(
                f"Signal: {signal['action']} | Confidence: {signal['confidence']:.2f} | "
                f"Reason: {signal['reason']}"
            )

            # Check safety limits
            is_safe, safety_reason = self.check_safety_limits()
            if not is_safe:
                self.logger.logger.warning(f"⚠️  Safety check failed: {safety_reason}")
                return True

            # Execute signal
            if signal['action'] in ['BUY', 'SCALE']:
                success = self._execute_entry(ticker, signal, indicators, hourly_data)
                if success:
                    self.logger.logger.info("✅ Entry executed successfully")
                else:
                    self.logger.logger.warning("❌ Entry execution failed")

            elif signal['action'] == 'HOLD':
                # Manage existing position if any
                if self.current_position['size'] > 0:
                    self._manage_existing_position(ticker, hourly_data)

            self.logger.logger.info(f"{'='*60}\n")
            return True

        except Exception as e:
            self.logger.log_error("Error in trading cycle", e)
            return False

    def _execute_entry(
        self,
        ticker: str,
        signal: Dict[str, Any],
        indicators: Dict,
        hourly_data: Any
    ) -> bool:
        """Execute entry trade based on signal."""
        try:
            # Get current price
            ticker_data = get_ticker(ticker)
            if not ticker_data:
                self.logger.logger.error("Failed to get current price")
                return False

            current_price = float(ticker_data.get('closing_price', 0))

            # Calculate position size
            trade_amount_krw = self.global_config.get('trading', {}).get('trade_amount_krw', 50000)
            position_pct = signal.get('position_pct', 50.0)
            adjusted_amount_krw = trade_amount_krw * (position_pct / 100.0)

            # Calculate units to buy
            units = adjusted_amount_krw / current_price

            # Calculate stop-loss
            stop_loss = self.strategy.calculate_chandelier_stop(hourly_data, indicators)

            # Execute trade
            success = self.execute_trade(
                ticker=ticker,
                action='BUY',
                amount=units,
                price=current_price,
                reason=signal['reason']
            )

            if success:
                # Update position state
                self.current_position['stop_loss'] = stop_loss
                self.current_position['highest_high'] = current_price
                self._save_position_state()

            return success

        except Exception as e:
            self.logger.log_error("Error executing entry", e)
            return False

    def _manage_existing_position(self, ticker: str, hourly_data: Any):
        """Manage existing position - check for exits."""
        try:
            # Get current price
            ticker_data = get_ticker(ticker)
            if not ticker_data:
                return

            current_price = float(ticker_data.get('closing_price', 0))

            # Update highest high
            if current_price > self.current_position['highest_high']:
                self.current_position['highest_high'] = current_price

            # Calculate indicators
            indicators = self.strategy.calculate_indicators(hourly_data)

            # Check exit conditions
            exit_signal = self.strategy.check_exit_conditions(
                data_4h=hourly_data,
                indicators=indicators,
                entry_price=self.current_position['entry_price'],
                highest_high=self.current_position['highest_high'],
                position_pct=self.current_position['position_pct']
            )

            if exit_signal['action'] != 'HOLD':
                self.logger.logger.info(
                    f"🚨 Exit Signal: {exit_signal['action']} | {exit_signal['reason']}"
                )

                # Calculate exit amount
                exit_pct = exit_signal['exit_pct']
                exit_amount = self.current_position['size'] * (exit_pct / 100.0)

                # Execute exit
                success = self.execute_trade(
                    ticker=ticker,
                    action='SELL',
                    amount=exit_amount,
                    price=current_price,
                    reason=exit_signal['reason']
                )

                if success:
                    self.logger.logger.info(f"✅ Exit executed: {exit_pct}% of position")

                    # Update position state
                    if exit_pct >= 100:
                        # Position fully closed
                        profit = (current_price - self.current_position['entry_price']) * exit_amount
                        profit_pct = (profit / (self.current_position['entry_price'] * exit_amount)) * 100

                        self.logger.logger.info(
                            f"💰 Position Closed | Profit: {profit:,.0f} KRW ({profit_pct:+.2f}%)"
                        )

                        # Update consecutive losses counter
                        if profit < 0:
                            self.consecutive_losses += 1
                        else:
                            self.consecutive_losses = 0

                        self.current_position = self._load_position_state()
                    else:
                        # Partial exit
                        if exit_signal['action'] == 'TAKE_PROFIT_1':
                            self.current_position['first_target_hit'] = True

                    self._save_position_state()

        except Exception as e:
            self.logger.log_error("Error managing existing position", e)

    # ========== UTILITY METHODS ==========

    def get_current_balance(self, currency: str = "KRW") -> float:
        """
        Get current balance for a currency.

        Args:
            currency: Currency symbol ('KRW' or ticker like 'BTC')

        Returns:
            Available balance
        """
        try:
            if self.global_config.get('safety', {}).get('dry_run', True):
                # Dry-run mode - return mock balance
                if currency == "KRW":
                    return 1000000.0  # 1M KRW
                else:
                    return self._calculate_position_from_history(currency)

            # Live mode - query API
            balance_response = self.api.get_balance("ALL")

            if balance_response and balance_response.get('status') == '0000':
                data = balance_response.get('data', {})

                if currency == "KRW":
                    return float(data.get('available_krw', '0'))
                else:
                    return float(data.get(f'available_{currency.lower()}', '0'))
            else:
                return 0.0

        except Exception as e:
            self.logger.log_error(f"Error getting balance: {currency}", e)
            return 0.0

    def get_account_summary(self, force_refresh: bool = False):
        """Get account summary from portfolio manager."""
        return self.portfolio_manager.get_account_summary(force_refresh)

    def get_portfolio_status_text(self) -> str:
        """Get portfolio status as formatted text."""
        return self.portfolio_manager.get_portfolio_status_text()

    def generate_daily_report(self) -> str:
        """Generate daily trading report."""
        ticker = self.global_config.get('trading', {}).get('target_ticker', 'BTC')
        report = self.transaction_history.generate_report(ticker, days=1)

        # Add current position info
        if self.current_position['size'] > 0:
            report += f"""
=== Current Position ===
Size: {self.current_position['size']:.6f} {ticker}
Entry Price: {self.current_position['entry_price']:,.0f} KRW
Stop Loss: {self.current_position['stop_loss']:,.0f} KRW
First Target Hit: {self.current_position['first_target_hit']}
"""

        # Add balance info
        krw_balance = self.get_current_balance("KRW")
        coin_balance = self.get_current_balance(ticker)

        report += f"""
=== Current Balance ===
KRW Balance: {krw_balance:,.0f} 원
{ticker} Balance: {coin_balance:.6f} 개
Daily Trade Count: {self.daily_trade_count}회
"""

        return report

    def reset_daily_counters(self):
        """Reset daily trading counters."""
        self.daily_trade_count = 0
        self.logger.logger.info("Daily trade counters reset")


# ========== MODULE-LEVEL CONVENIENCE FUNCTIONS ==========

def create_bot_v2(config_override: Dict[str, Any] = None) -> TradingBotV2:
    """
    Create and initialize a Trading Bot V2 instance.

    Args:
        config_override: Optional configuration overrides

    Returns:
        Initialized TradingBotV2 instance
    """
    return TradingBotV2(config_override=config_override)
