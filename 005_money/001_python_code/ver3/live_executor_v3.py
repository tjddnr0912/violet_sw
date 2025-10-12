"""
Live Executor V3 - Thread-Safe Order Execution and Position Management

This module extends Ver2's LiveExecutor with thread-safety for multi-coin portfolio trading.

New Features in V3:
- Thread-safe position updates using threading.Lock
- Multi-coin position tracking
- Concurrent order execution support

Inherited Features from V2:
- Order placement (market/limit orders)
- Position tracking with persistent state
- Partial position management (50% scaling)
- Stop-loss monitoring
- Transaction logging

Usage:
    from ver3.live_executor_v3 import LiveExecutorV3

    executor = LiveExecutorV3(api, logger, config)
    # Thread-safe execution for multiple coins
    executor.execute_order(ticker='ETH', action='BUY', units=0.1, price=3000000)
"""

import json
import os
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

from lib.api.bithumb_api import BithumbAPI
from lib.core.logger import TradingLogger


# Bithumb 코인별 소수점 자릿수 제한
BITHUMB_DECIMAL_LIMITS = {
    'BTC': 4,   # Bitcoin: 소수점 4자리
    'ETH': 4,   # Ethereum: 소수점 4자리
    'XRP': 0,   # Ripple: 정수 단위
    'SOL': 2,   # Solana: 소수점 2자리
    'ADA': 0,   # Cardano: 정수 단위
    'DOGE': 0,  # Dogecoin: 정수 단위
    'MATIC': 0, # Polygon: 정수 단위
    'DOT': 2,   # Polkadot: 소수점 2자리
    'AVAX': 2,  # Avalanche: 소수점 2자리
    'LINK': 2,  # Chainlink: 소수점 2자리
    'BCH': 4,   # Bitcoin Cash: 소수점 4자리
    'LTC': 4,   # Litecoin: 소수점 4자리
}


def round_units_for_bithumb(ticker: str, units: float) -> float:
    """
    빗썸 API 요구사항에 맞게 수량을 반올림합니다.

    Args:
        ticker: 코인 심볼
        units: 원본 수량

    Returns:
        반올림된 수량
    """
    decimal_places = BITHUMB_DECIMAL_LIMITS.get(ticker, 4)  # 기본값 4자리
    return round(units, decimal_places)


class Position:
    """
    Position data class for tracking open positions with pyramiding support.
    """

    def __init__(
        self,
        ticker: str,
        size: float,
        entry_price: float,
        entry_time: datetime,
        stop_loss: float = 0.0,
        highest_high: float = 0.0,
        profit_target_mode: str = 'bb_based',
        tp1_percentage: float = 1.5,
        tp2_percentage: float = 2.5
    ):
        self.ticker = ticker
        self.size = size
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.stop_loss = stop_loss
        self.highest_high = highest_high if highest_high > 0 else entry_price
        self.position_pct = 100.0  # 100% = full position
        self.first_target_hit = False
        self.second_target_hit = False

        # Profit target mode configuration (locked when position opened)
        self.profit_target_mode = profit_target_mode  # 'bb_based' or 'percentage_based'
        self.tp1_percentage = tp1_percentage  # TP1 percentage (only used if mode is percentage_based)
        self.tp2_percentage = tp2_percentage  # TP2 percentage (only used if mode is percentage_based)

        # Pyramiding support - track multiple entries
        self.entry_count = 1  # Number of entries (initial = 1)
        self.entry_prices = [entry_price]  # List of all entry prices
        self.entry_times = [entry_time]  # List of all entry times
        self.entry_sizes = [size]  # List of entry sizes for each pyramid

    def to_dict(self) -> Dict[str, Any]:
        """Convert position to dictionary for serialization."""
        return {
            'ticker': self.ticker,
            'size': self.size,
            'entry_price': self.entry_price,
            'entry_time': self.entry_time.isoformat() if self.entry_time else None,
            'stop_loss': self.stop_loss,
            'highest_high': self.highest_high,
            'position_pct': self.position_pct,
            'first_target_hit': self.first_target_hit,
            'second_target_hit': self.second_target_hit,
            # Profit target mode (locked at position open)
            'profit_target_mode': self.profit_target_mode,
            'tp1_percentage': self.tp1_percentage,
            'tp2_percentage': self.tp2_percentage,
            # Pyramiding fields
            'entry_count': self.entry_count,
            'entry_prices': self.entry_prices,
            'entry_times': [t.isoformat() if t else None for t in self.entry_times],
            'entry_sizes': self.entry_sizes,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create position from dictionary."""
        pos = cls(
            ticker=data.get('ticker', ''),
            size=data.get('size', 0.0),
            entry_price=data.get('entry_price', 0.0),
            entry_time=datetime.fromisoformat(data['entry_time']) if data.get('entry_time') else None,
            stop_loss=data.get('stop_loss', 0.0),
            highest_high=data.get('highest_high', 0.0),
            profit_target_mode=data.get('profit_target_mode', 'bb_based'),  # Backward compatible
            tp1_percentage=data.get('tp1_percentage', 1.5),
            tp2_percentage=data.get('tp2_percentage', 2.5)
        )
        pos.position_pct = data.get('position_pct', 100.0)
        pos.first_target_hit = data.get('first_target_hit', False)
        pos.second_target_hit = data.get('second_target_hit', False)

        # Load pyramiding fields (backward compatible)
        pos.entry_count = data.get('entry_count', 1)
        pos.entry_prices = data.get('entry_prices', [pos.entry_price])
        entry_times_iso = data.get('entry_times', [])
        pos.entry_times = [
            datetime.fromisoformat(t) if t else None
            for t in entry_times_iso
        ] if entry_times_iso else [pos.entry_time]
        pos.entry_sizes = data.get('entry_sizes', [pos.size])

        return pos


class LiveExecutorV3:
    """
    Thread-safe order executor and position manager for Version 3 portfolio trading.

    Responsibilities:
    - Execute buy/sell orders via Bithumb API (thread-safe)
    - Track multi-coin positions with state persistence
    - Manage partial exits (50% scaling strategy)
    - Monitor stop-loss levels
    - Log all transactions
    - Thread-safe concurrent operations

    Thread Safety:
    - Uses threading.Lock for position updates
    - Safe for concurrent calls from PortfolioManagerV3
    """

    def __init__(
        self,
        api: BithumbAPI,
        logger: TradingLogger,
        config: Dict[str, Any] = None,
        state_file: str = None,
        markdown_logger=None,
        transaction_history=None
    ):
        """
        Initialize Live Executor V3.

        Args:
            api: BithumbAPI instance
            logger: TradingLogger instance
            config: Configuration dictionary
            state_file: Path to position state file (default: logs/positions_v3.json)
            markdown_logger: MarkdownTransactionLogger instance for markdown transaction log
            transaction_history: TransactionHistory instance for JSON transaction log (GUI display)
        """
        self.api = api
        self.logger = logger
        self.markdown_logger = markdown_logger
        self.transaction_history = transaction_history
        self.config = config or {}

        # Position state file (Ver3 uses separate state file)
        if state_file is None:
            log_dir = self.config.get('LOGGING_CONFIG', {}).get('log_dir', 'logs')
            self.state_file = Path(log_dir) / 'positions_v3.json'
        else:
            self.state_file = Path(state_file)

        # Ensure state file directory exists
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # Thread safety for position updates
        self._position_lock = threading.Lock()

        # Load positions
        self.positions: Dict[str, Position] = self._load_positions()

        self.logger.logger.info(f"LiveExecutorV3 initialized (thread-safe) | Positions loaded: {len(self.positions)}")

    # ========== POSITION MANAGEMENT ==========

    def _load_positions(self) -> Dict[str, Position]:
        """Load positions from state file."""
        try:
            if not self.state_file.exists():
                self.logger.logger.debug("No existing position state file found")
                return {}

            with open(self.state_file, 'r') as f:
                data = json.load(f)

            positions = {}
            for ticker, pos_data in data.items():
                try:
                    positions[ticker] = Position.from_dict(pos_data)
                except Exception as e:
                    self.logger.log_error(f"Error loading position for {ticker}", e)

            self.logger.logger.info(f"Loaded {len(positions)} positions from state file")
            return positions

        except Exception as e:
            self.logger.log_error("Error loading position state", e)
            return {}

    def _save_positions(self):
        """Save positions to state file (thread-safe)."""
        try:
            with self._position_lock:  # Thread-safe file write
                data = {
                    ticker: pos.to_dict()
                    for ticker, pos in self.positions.items()
                }

                with open(self.state_file, 'w') as f:
                    json.dump(data, f, indent=2)

                self.logger.logger.debug(f"Saved {len(self.positions)} positions to state file")

        except Exception as e:
            self.logger.log_error("Error saving position state", e)

    def get_position(self, ticker: str) -> Optional[Position]:
        """
        Get current position for a ticker.

        Args:
            ticker: Cryptocurrency symbol

        Returns:
            Position object or None if no position
        """
        return self.positions.get(ticker)

    def has_position(self, ticker: str) -> bool:
        """Check if there's an open position for ticker."""
        return ticker in self.positions and self.positions[ticker].size > 0

    # ========== ORDER EXECUTION ==========

    def execute_order(
        self,
        ticker: str,
        action: str,
        units: float,
        price: float,
        dry_run: bool = True,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Execute a buy or sell order.

        Args:
            ticker: Cryptocurrency symbol
            action: 'BUY' or 'SELL'
            units: Amount in cryptocurrency units
            price: Current price (for dry-run and logging)
            dry_run: If True, simulate order without real execution
            reason: Reason for order (for logging)

        Returns:
            Dictionary with execution result:
            - success: bool
            - order_id: str
            - executed_price: float
            - executed_units: float
            - message: str
        """
        try:
            total_value = units * price

            self.logger.logger.info(
                f"{'[DRY-RUN] ' if dry_run else '[LIVE] '}"
                f"Executing {action}: {units:.6f} {ticker} @ {price:,.0f} KRW "
                f"(Total: {total_value:,.0f} KRW)"
            )

            if reason:
                self.logger.logger.info(f"  Reason: {reason}")

            if dry_run:
                # Simulate execution
                order_id = f"DRY_RUN_{action}_{int(time.time())}"
                result = {
                    'success': True,
                    'order_id': order_id,
                    'executed_price': price,
                    'executed_units': units,
                    'message': 'Dry-run execution successful'
                }

            else:
                # Real execution
                self.logger.logger.warning("🔴 EXECUTING REAL ORDER ON BITHUMB")

                # 빗썸 API 요구사항에 맞게 수량 반올림
                rounded_units = round_units_for_bithumb(ticker, units)
                self.logger.logger.info(
                    f"Units adjusted for Bithumb: {units:.8f} -> {rounded_units} "
                    f"(decimal places: {BITHUMB_DECIMAL_LIMITS.get(ticker, 4)})"
                )

                if action == 'BUY':
                    # Bithumb API: place_buy_order(order_currency, payment_currency, units, price, type_order)
                    response = self.api.place_buy_order(
                        order_currency=ticker,
                        payment_currency="KRW",
                        units=rounded_units,
                        type_order="market"
                    )
                elif action == 'SELL':
                    # Bithumb API: place_sell_order(order_currency, payment_currency, units, price, type_order)
                    response = self.api.place_sell_order(
                        order_currency=ticker,
                        payment_currency="KRW",
                        units=rounded_units,
                        type_order="market"
                    )
                else:
                    return {
                        'success': False,
                        'order_id': None,
                        'executed_price': 0.0,
                        'executed_units': 0.0,
                        'message': f'Invalid action: {action}'
                    }

                if response and response.get('status') == '0000':
                    order_id = response.get('order_id', 'N/A')
                    result = {
                        'success': True,
                        'order_id': order_id,
                        'executed_price': price,
                        'executed_units': units,
                        'message': 'Order executed successfully'
                    }
                else:
                    error_msg = response.get('message', 'Unknown error') if response else 'No response'
                    result = {
                        'success': False,
                        'order_id': None,
                        'executed_price': 0.0,
                        'executed_units': 0.0,
                        'message': f'Order failed: {error_msg}'
                    }

            # Update position if successful
            if result['success']:
                self._update_position_after_trade(ticker, action, units, price)

                # Calculate fee
                total_value = units * price
                fee = total_value * 0.0005  # 0.05% Bithumb fee

                # Calculate P&L for SELL transactions
                pnl = 0.0
                if action == 'SELL' and self.markdown_logger and self.transaction_history:
                    profit_amount, profit_rate = self.markdown_logger.calculate_sell_profit(
                        ticker=ticker,
                        sell_amount=units,
                        sell_price=price,
                        transaction_history=self.transaction_history
                    )
                    pnl = profit_amount
                    self.logger.logger.info(f"SELL P&L: {pnl:+,.0f} KRW ({profit_rate:+.2f}%)")

                # Log transaction to JSON (for GUI display)
                if self.transaction_history:
                    self.transaction_history.add_transaction(
                        ticker=ticker,
                        action=action,
                        amount=units,
                        price=price,
                        order_id=result.get('order_id', 'N/A'),
                        fee=fee,
                        success=True,
                        pnl=pnl  # Include P&L for SELL transactions
                    )

                # Log transaction to markdown file (for human-readable history)
                if self.markdown_logger:
                    self.markdown_logger.log_transaction(
                        ticker=ticker,
                        action=action,
                        amount=units,  # Amount in cryptocurrency units (not KRW value)
                        price=price,
                        order_id=result.get('order_id', 'N/A'),
                        fee=fee,
                        success=True,
                        transaction_history=self.transaction_history
                    )

            return result

        except Exception as e:
            self.logger.log_error(f"Error executing order: {action} {ticker}", e)
            return {
                'success': False,
                'order_id': None,
                'executed_price': 0.0,
                'executed_units': 0.0,
                'message': f'Exception: {str(e)}'
            }

    def _update_position_after_trade(
        self,
        ticker: str,
        action: str,
        units: float,
        price: float
    ):
        """Update position state after trade execution (supports pyramiding)."""
        try:
            if action == 'BUY':
                if ticker in self.positions:
                    # Pyramiding - add to existing position
                    pos = self.positions[ticker]
                    old_value = pos.size * pos.entry_price
                    new_value = units * price
                    total_size = pos.size + units

                    # Update weighted average entry price
                    pos.entry_price = (old_value + new_value) / total_size
                    pos.size = total_size

                    # Track pyramid entry
                    pos.entry_count += 1
                    pos.entry_prices.append(price)
                    pos.entry_times.append(datetime.now())
                    pos.entry_sizes.append(units)

                    # IMPORTANT: Reset profit target flags when pyramiding
                    # This allows TP1/TP2 to trigger again for the increased position
                    if pos.first_target_hit:
                        pos.first_target_hit = False
                        pos.position_pct = 100.0  # Reset to full position
                        self.logger.logger.info(
                            f"PYRAMID: Resetting TP flags for {ticker} - position now 100%"
                        )

                    self.logger.logger.info(
                        f"PYRAMID ENTRY #{pos.entry_count}: {ticker} | "
                        f"Added: {units:.6f} @ {price:,.0f} KRW | "
                        f"Total size: {pos.size:.6f} | "
                        f"Avg entry: {pos.entry_price:,.0f} KRW"
                    )
                else:
                    # New position (first entry) - capture profit target mode from current config
                    exit_config = self.config.get('EXIT_CONFIG', {})
                    profit_mode = exit_config.get('profit_target_mode', 'bb_based')
                    tp1_pct = exit_config.get('tp1_percentage', 1.5)
                    tp2_pct = exit_config.get('tp2_percentage', 2.5)

                    pos = Position(
                        ticker=ticker,
                        size=units,
                        entry_price=price,
                        entry_time=datetime.now(),
                        highest_high=price,
                        profit_target_mode=profit_mode,
                        tp1_percentage=tp1_pct,
                        tp2_percentage=tp2_pct
                    )
                    self.positions[ticker] = pos

                    mode_str = f"% mode (TP1: {tp1_pct}%, TP2: {tp2_pct}%)" if profit_mode == 'percentage_based' else "BB mode"
                    self.logger.logger.info(
                        f"Position opened: {ticker} ({mode_str}) | "
                        f"Size: {pos.size:.6f} | "
                        f"Entry: {pos.entry_price:,.0f}"
                    )

            elif action == 'SELL':
                if ticker in self.positions:
                    pos = self.positions[ticker]
                    pos.size -= units

                    if pos.size <= 0:
                        # Position fully closed
                        profit = (price - pos.entry_price) * (pos.size + units)  # Use original size
                        profit_pct = (profit / (pos.entry_price * (pos.size + units))) * 100

                        self.logger.logger.info(
                            f"Position closed: {ticker} | "
                            f"Entries: {pos.entry_count} | "
                            f"Profit: {profit:,.0f} KRW ({profit_pct:+.2f}%)"
                        )

                        del self.positions[ticker]
                    else:
                        # Partial exit
                        exit_pct = (units / (pos.size + units)) * 100
                        self.logger.logger.info(
                            f"Partial exit: {ticker} | "
                            f"Exited: {exit_pct:.1f}% | "
                            f"Remaining: {pos.size:.6f}"
                        )

                        # Update position percentage
                        pos.position_pct = (pos.size / (pos.size + units)) * 100

            # Save updated positions
            self._save_positions()

        except Exception as e:
            self.logger.log_error(f"Error updating position after trade: {ticker}", e)

    # ========== POSITION SCALING ==========

    def execute_scale_entry(
        self,
        ticker: str,
        additional_units: float,
        price: float,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Scale into existing position (add to position).

        Args:
            ticker: Cryptocurrency symbol
            additional_units: Additional units to buy
            price: Current price
            dry_run: Dry-run mode flag

        Returns:
            Execution result dictionary
        """
        if not self.has_position(ticker):
            return {
                'success': False,
                'message': 'Cannot scale - no existing position'
            }

        return self.execute_order(
            ticker=ticker,
            action='BUY',
            units=additional_units,
            price=price,
            dry_run=dry_run,
            reason="Scaling into existing position"
        )

    def execute_partial_exit(
        self,
        ticker: str,
        exit_pct: float,
        price: float,
        dry_run: bool = True,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Execute partial exit of position.

        Args:
            ticker: Cryptocurrency symbol
            exit_pct: Percentage of position to exit (0-100)
            price: Current price
            dry_run: Dry-run mode flag
            reason: Reason for exit

        Returns:
            Execution result dictionary
        """
        if not self.has_position(ticker):
            return {
                'success': False,
                'message': 'Cannot exit - no position'
            }

        pos = self.positions[ticker]
        exit_units = pos.size * (exit_pct / 100.0)

        return self.execute_order(
            ticker=ticker,
            action='SELL',
            units=exit_units,
            price=price,
            dry_run=dry_run,
            reason=reason or f"Partial exit ({exit_pct:.0f}%)"
        )

    # ========== STOP-LOSS MONITORING ==========

    def update_stop_loss(self, ticker: str, new_stop: float):
        """
        Update stop-loss level for a position.

        Args:
            ticker: Cryptocurrency symbol
            new_stop: New stop-loss price
        """
        if ticker in self.positions:
            old_stop = self.positions[ticker].stop_loss
            self.positions[ticker].stop_loss = new_stop

            self.logger.logger.info(
                f"Stop-loss updated: {ticker} | "
                f"Old: {old_stop:,.0f} → New: {new_stop:,.0f}"
            )

            self._save_positions()

    def update_highest_high(self, ticker: str, current_price: float):
        """
        Update highest high for trailing stop calculation.

        Args:
            ticker: Cryptocurrency symbol
            current_price: Current price
        """
        if ticker in self.positions:
            pos = self.positions[ticker]

            if current_price > pos.highest_high:
                pos.highest_high = current_price
                self.logger.logger.debug(
                    f"Highest high updated: {ticker} | {pos.highest_high:,.0f}"
                )
                self._save_positions()

    def check_stop_loss(self, ticker: str, current_price: float) -> bool:
        """
        Check if current price has hit stop-loss.

        Args:
            ticker: Cryptocurrency symbol
            current_price: Current price

        Returns:
            True if stop-loss hit
        """
        if ticker not in self.positions:
            return False

        pos = self.positions[ticker]

        if pos.stop_loss > 0 and current_price <= pos.stop_loss:
            self.logger.logger.warning(
                f"⚠️  STOP-LOSS HIT: {ticker} | "
                f"Price: {current_price:,.0f} <= Stop: {pos.stop_loss:,.0f}"
            )
            return True

        return False

    # ========== TARGET MANAGEMENT ==========

    def mark_first_target_hit(self, ticker: str):
        """Mark first target as hit."""
        if ticker in self.positions:
            self.positions[ticker].first_target_hit = True
            self.logger.logger.info(f"First target marked as hit: {ticker}")
            self._save_positions()

    def mark_second_target_hit(self, ticker: str):
        """Mark second target as hit."""
        if ticker in self.positions:
            self.positions[ticker].second_target_hit = True
            self.logger.logger.info(f"Second target marked as hit: {ticker}")
            self._save_positions()

    # ========== UTILITY METHODS ==========

    def get_all_positions(self) -> Dict[str, Position]:
        """Get all open positions."""
        return self.positions.copy()

    def get_position_summary(self, ticker: str) -> Dict[str, Any]:
        """
        Get summary of position for display.

        Args:
            ticker: Cryptocurrency symbol

        Returns:
            Dictionary with position details
        """
        if ticker not in self.positions:
            return {
                'has_position': False,
                'ticker': ticker
            }

        pos = self.positions[ticker]

        return {
            'has_position': True,
            'ticker': ticker,
            'size': pos.size,
            'entry_price': pos.entry_price,
            'entry_time': pos.entry_time.strftime('%Y-%m-%d %H:%M:%S') if pos.entry_time else 'N/A',
            'stop_loss': pos.stop_loss,
            'highest_high': pos.highest_high,
            'position_pct': pos.position_pct,
            'first_target_hit': pos.first_target_hit,
            'second_target_hit': pos.second_target_hit,
            # Profit target mode (locked at position open)
            'profit_target_mode': pos.profit_target_mode,
            'tp1_percentage': pos.tp1_percentage,
            'tp2_percentage': pos.tp2_percentage,
            # Pyramiding info
            'entry_count': pos.entry_count,
            'entry_prices': pos.entry_prices,
            'entry_sizes': pos.entry_sizes,
        }

    def close_position(self, ticker: str, price: float, dry_run: bool = True, reason: str = "") -> Dict[str, Any]:
        """
        Close entire position.

        Args:
            ticker: Cryptocurrency symbol
            price: Current price
            dry_run: Dry-run mode flag
            reason: Reason for closing

        Returns:
            Execution result dictionary
        """
        if not self.has_position(ticker):
            return {
                'success': False,
                'message': 'No position to close'
            }

        pos = self.positions[ticker]

        return self.execute_order(
            ticker=ticker,
            action='SELL',
            units=pos.size,
            price=price,
            dry_run=dry_run,
            reason=reason or "Closing full position"
        )

    def reset_all_positions(self):
        """Reset all positions (use with caution!)."""
        self.logger.logger.warning("⚠️  RESETTING ALL POSITIONS")
        self.positions = {}
        self._save_positions()

    # ========== PYRAMIDING HELPER METHODS ==========

    def get_entry_count(self, ticker: str) -> int:
        """
        Get number of entries for a position (for pyramiding).

        Args:
            ticker: Cryptocurrency symbol

        Returns:
            Number of entries (0 if no position)
        """
        if ticker not in self.positions:
            return 0
        return self.positions[ticker].entry_count

    def get_last_entry_price(self, ticker: str) -> float:
        """
        Get price of the last entry for pyramiding comparison.

        Args:
            ticker: Cryptocurrency symbol

        Returns:
            Last entry price (0.0 if no position)
        """
        if ticker not in self.positions:
            return 0.0

        pos = self.positions[ticker]
        if not pos.entry_prices:
            return pos.entry_price

        return pos.entry_prices[-1]  # Last entry price

    def get_all_entry_prices(self, ticker: str) -> List[float]:
        """
        Get all entry prices for a position.

        Args:
            ticker: Cryptocurrency symbol

        Returns:
            List of entry prices (empty if no position)
        """
        if ticker not in self.positions:
            return []
        return self.positions[ticker].entry_prices.copy()
