"""
Portfolio Manager V3 - Multi-Coin Trading Coordinator

This module implements the Portfolio Manager Pattern for coordinating
multi-coin trading with centralized risk management and parallel analysis.

Key Classes:
- CoinMonitor: Wrapper for monitoring a single coin using Ver2 strategy
- PortfolioManagerV3: Centralized manager for multi-coin portfolio

Features:
- Parallel coin analysis using ThreadPoolExecutor
- Portfolio-level position limits and risk management
- Entry signal prioritization (highest score first)
- Thread-safe execution
- Centralized decision-making

Usage:
    from ver3.portfolio_manager_v3 import PortfolioManagerV3
    from ver3.config_v3 import get_version_config
    from lib.api.bithumb_api import BithumbAPI
    from lib.core.logger import TradingLogger

    config = get_version_config()
    api = BithumbAPI()
    logger = TradingLogger()

    pm = PortfolioManagerV3(
        coins=['BTC', 'ETH', 'XRP'],
        config=config,
        api=api,
        logger=logger
    )

    # Analyze all coins in parallel
    results = pm.analyze_all()

    # Make portfolio-level decisions
    decisions = pm.make_portfolio_decision(results)

    # Execute trades
    pm.execute_decisions(decisions)
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
import json
import os
from pathlib import Path

from ver2.strategy_v2 import StrategyV2
from ver3.live_executor_v3 import LiveExecutorV3
from lib.core.logger import TradingLogger


class CoinMonitor:
    """
    Wrapper around Ver2 strategy for monitoring a single coin.

    Responsibilities:
    - Run strategy analysis for one coin
    - Cache last analysis result
    - Track update timestamp
    - Provide position status
    """

    def __init__(self, coin: str, strategy: StrategyV2, executor: LiveExecutorV3, logger: TradingLogger):
        """
        Initialize coin monitor.

        Args:
            coin: Cryptocurrency symbol (e.g., 'BTC', 'ETH')
            strategy: StrategyV2 instance (shared across monitors)
            executor: LiveExecutorV3 instance (shared across monitors)
            logger: TradingLogger instance
        """
        self.coin = coin
        self.strategy = strategy
        self.executor = executor
        self.logger = logger

        # State tracking
        self.last_analysis = {}
        self.last_update = None

    def analyze(self) -> Dict[str, Any]:
        """
        Run strategy analysis for this coin.

        Returns:
            Analysis result dictionary with keys:
            - action: 'BUY', 'SELL', or 'HOLD'
            - entry_score: Score 0-4 for entry signals
            - exit_score: Score for exit signals
            - signal_strength: Float 0.0-1.0
            - market_regime: 'bullish', 'bearish', or 'neutral'
            - current_price: Current price in KRW
            - stop_loss_price: Suggested stop-loss
            - indicators: Dict of indicator values
            - reason: Human-readable decision reason
        """
        try:
            # Use Ver2 strategy for analysis
            result = self.strategy.analyze_market(self.coin, interval='4h')

            # Cache result
            self.last_analysis = result
            self.last_update = datetime.now()

            return result

        except Exception as e:
            self.logger.log_error(f"Analysis failed for {self.coin}", e)
            return {
                'action': 'HOLD',
                'signal_strength': 0.0,
                'reason': f'Error: {str(e)}',
                'market_regime': 'error',
                'entry_score': 0,
                'exit_score': 0,
                'current_price': 0,
                'stop_loss_price': 0,
            }

    def has_position(self) -> bool:
        """
        Check if we have an open position for this coin.

        Returns:
            True if position exists, False otherwise
        """
        return self.executor.has_position(self.coin)

    def get_position_summary(self) -> Dict[str, Any]:
        """
        Get position details for this coin.

        Returns:
            Dictionary with position information:
            - has_position: bool
            - size: float (units)
            - entry_price: float (KRW)
            - entry_time: datetime
            - stop_loss: float (KRW)
            - pnl: float (unrealized P&L in KRW)
        """
        return self.executor.get_position_summary(self.coin)


class PortfolioManagerV3:
    """
    Multi-coin portfolio manager with centralized risk management.

    Features:
    - Parallel coin analysis using ThreadPoolExecutor
    - Portfolio-level position limits (max 2 positions)
    - Entry signal prioritization by score
    - Centralized risk management
    - Thread-safe execution

    Architecture:
    - Uses CoinMonitor for each coin
    - Shares single StrategyV2 instance (stateless)
    - Shares single LiveExecutorV3 instance (thread-safe)
    - Coordinates decisions across all coins
    """

    def __init__(
        self,
        coins: List[str],
        config: Dict[str, Any],
        api,
        logger: TradingLogger
    ):
        """
        Initialize portfolio manager.

        Args:
            coins: List of coins to monitor (e.g., ['BTC', 'ETH', 'XRP'])
            config: Ver3 configuration dictionary from config_v3.py
            api: BithumbAPI instance
            logger: TradingLogger instance
        """
        self.coins = coins
        self.config = config
        self.logger = logger

        # Shared components
        self.strategy = StrategyV2(config, logger)
        self.executor = LiveExecutorV3(api, logger, config)

        # Per-coin monitors
        self.monitors = {
            coin: CoinMonitor(coin, self.strategy, self.executor, logger)
            for coin in coins
        }

        # Portfolio state
        self.last_results = {}
        self.last_decisions = []

        # State file for last executed actions
        log_dir = config.get('LOGGING_CONFIG', {}).get('log_dir', 'logs')
        self.actions_state_file = Path(log_dir) / 'last_executed_actions_v3.json'

        # Track last executed action per coin: {coin: 'BUY'|'SELL'|'-'}
        self.last_executed_actions = self._load_last_actions()

        self.logger.logger.info(f"Portfolio Manager V3 initialized with coins: {coins}")

    def _load_last_actions(self) -> Dict[str, str]:
        """
        Load last executed actions from state file.

        Returns:
            Dictionary mapping coin to last action ('BUY'|'SELL'|'-')
        """
        try:
            if self.actions_state_file.exists():
                with open(self.actions_state_file, 'r') as f:
                    data = json.load(f)
                self.logger.logger.info(f"Loaded last actions for {len(data)} coins from state file")
                return data
            else:
                self.logger.logger.debug("No existing last actions state file found")
                return {}
        except Exception as e:
            self.logger.log_error("Error loading last actions state", e)
            return {}

    def _save_last_actions(self):
        """Save last executed actions to state file."""
        try:
            # Ensure directory exists
            self.actions_state_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.actions_state_file, 'w') as f:
                json.dump(self.last_executed_actions, f, indent=2)

            self.logger.logger.debug(f"Saved last actions for {len(self.last_executed_actions)} coins")
        except Exception as e:
            self.logger.log_error("Error saving last actions state", e)

    def analyze_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Analyze all coins in parallel using ThreadPoolExecutor.

        Returns:
            Dict mapping coin symbol to analysis result:
            {
                'BTC': {'action': 'BUY', 'entry_score': 3, ...},
                'ETH': {'action': 'HOLD', 'entry_score': 1, ...},
                'XRP': {'action': 'BUY', 'entry_score': 4, ...}
            }
        """
        results = {}

        # Get thread pool config
        portfolio_config = self.config.get('PORTFOLIO_CONFIG', {})
        max_workers = portfolio_config.get('max_workers', len(self.coins))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all analysis tasks
            futures = {
                executor.submit(monitor.analyze): coin
                for coin, monitor in self.monitors.items()
            }

            # Collect results as they complete
            for future in as_completed(futures):
                coin = futures[future]
                try:
                    results[coin] = future.result()
                    action = results[coin].get('action', 'HOLD')
                    score = results[coin].get('entry_score', 0)
                    self.logger.logger.debug(
                        f"Analysis complete for {coin}: {action} (score {score}/4)"
                    )
                except Exception as e:
                    self.logger.log_error(f"Failed to get result for {coin}", e)
                    results[coin] = {
                        'action': 'HOLD',
                        'signal_strength': 0.0,
                        'reason': f'Exception: {str(e)}',
                        'market_regime': 'error',
                        'entry_score': 0,
                        'exit_score': 0,
                        'current_price': 0,
                    }

        self.last_results = results
        return results

    def make_portfolio_decision(self, coin_results: Dict[str, Dict]) -> List[Tuple[str, str, int]]:
        """
        Make portfolio-level trading decisions with risk limits and pyramiding support.

        Decision Logic:
        1. Check stop-loss for all positions (FIRST PRIORITY)
        2. Count current positions
        3. Check portfolio position limit
        4. Prioritize entry signals by score (highest first)
        5. Allow pyramiding if conditions met
        6. Allow exits regardless of limits

        Args:
            coin_results: Analysis results from analyze_all()

        Returns:
            List of (coin, action, entry_number) tuples to execute:
            [('XRP', 'BUY', 1), ('BTC', 'BUY', 2)] - in priority order
            entry_number: 1=new position, 2+=pyramiding
        """
        decisions = []

        # 0. PRIORITY: Check stop-loss for all active positions
        for coin in self.coins:
            if self.executor.has_position(coin):
                result = coin_results.get(coin, {})
                current_price = result.get('current_price', 0)

                if current_price > 0 and self.executor.check_stop_loss(coin, current_price):
                    decisions.append((coin, 'SELL', 0))  # entry_number=0 for stop-loss
                    self.logger.logger.warning(
                        f"🚨 STOP-LOSS TRIGGERED: {coin} at {current_price:,.0f} KRW"
                    )

        # 0.5 SECOND PRIORITY: Check profit targets for all active positions
        exit_config = self.config.get('EXIT_CONFIG', {})
        for coin in self.coins:
            if self.executor.has_position(coin):
                result = coin_results.get(coin, {})
                current_price = result.get('current_price', 0)
                target_prices = result.get('target_prices', {})

                if current_price <= 0 or not target_prices:
                    continue

                pos_summary = self.executor.get_position_summary(coin)
                first_target_hit = pos_summary.get('first_target_hit', False)
                second_target_hit = pos_summary.get('second_target_hit', False)

                # Check first target (50% partial exit)
                first_target = target_prices.get('first_target', 0)
                if not first_target_hit and first_target > 0 and current_price >= first_target:
                    decisions.append((coin, 'PARTIAL_SELL_50', 0))
                    profit_pct = ((current_price - pos_summary['entry_price']) / pos_summary['entry_price']) * 100
                    self.logger.logger.info(
                        f"🎯 FIRST TARGET HIT: {coin} at {current_price:,.0f} KRW "
                        f"(+{profit_pct:.2f}%) - Selling 50%"
                    )

                # Check second target (remaining 100% exit)
                second_target = target_prices.get('second_target', 0)
                if first_target_hit and not second_target_hit and second_target > 0 and current_price >= second_target:
                    decisions.append((coin, 'SELL', 0))
                    profit_pct = ((current_price - pos_summary['entry_price']) / pos_summary['entry_price']) * 100
                    self.logger.logger.info(
                        f"🎯 SECOND TARGET HIT: {coin} at {current_price:,.0f} KRW "
                        f"(+{profit_pct:.2f}%) - Closing position"
                    )

        # 1. Count current positions
        active_positions = [
            coin for coin in self.coins
            if self.executor.has_position(coin)
        ]
        total_positions = len(active_positions)

        # 2. Get portfolio limits
        portfolio_config = self.config.get('PORTFOLIO_CONFIG', {})
        max_positions = portfolio_config.get('max_positions', 2)

        self.logger.logger.info(
            f"Portfolio status: {total_positions}/{max_positions} positions"
        )
        if active_positions:
            self.logger.logger.info(f"Active positions: {active_positions}")

        # 3. Process entry signals (including pyramiding)
        entry_candidates = []
        for coin, result in coin_results.items():
            if result['action'] == 'BUY':
                has_pos = self.executor.has_position(coin)

                if not has_pos:
                    # New position entry
                    entry_candidates.append((coin, result, 1))  # entry_number=1
                elif self._can_pyramid(coin, result):
                    # Pyramiding entry
                    entry_number = self.executor.get_entry_count(coin) + 1
                    entry_candidates.append((coin, result, entry_number))
                    self.logger.logger.info(
                        f"Pyramid opportunity: {coin} (entry #{entry_number})"
                    )

        if entry_candidates:
            self.logger.logger.info(
                f"Entry candidates: {[(c[0], f'#{c[2]}') for c in entry_candidates]}"
            )

            # Prioritize by entry score (highest first), then signal strength
            entry_candidates.sort(
                key=lambda x: (x[1].get('entry_score', 0), x[1].get('signal_strength', 0)),
                reverse=True
            )

            # Apply tie-breaker using coin rank if scores are equal
            coin_rank = portfolio_config.get('coin_rank', {})
            entry_candidates.sort(
                key=lambda x: (
                    x[1].get('entry_score', 0),
                    x[1].get('signal_strength', 0),
                    coin_rank.get(x[0], 0)
                ),
                reverse=True
            )

            # Apply portfolio position limit (only for NEW positions, not pyramiding)
            for coin, result, entry_number in entry_candidates:
                if entry_number == 1:  # New position
                    if total_positions >= max_positions:
                        self.logger.logger.info(
                            f"Portfolio limit reached ({max_positions} positions), skipping {coin} entry"
                        )
                        continue

                    decisions.append((coin, 'BUY', entry_number))
                    total_positions += 1
                    score_details = result.get('score_details', '')
                    self.logger.logger.info(
                        f"Entry decision: {coin} (score: {result.get('entry_score')}/4 [{score_details}], "
                        f"strength: {result.get('signal_strength', 0):.2f})"
                    )
                else:  # Pyramiding
                    decisions.append((coin, 'BUY', entry_number))
                    score_details = result.get('score_details', '')
                    self.logger.logger.info(
                        f"Pyramid decision: {coin} entry #{entry_number} (score: {result.get('entry_score')}/4 [{score_details}], "
                        f"strength: {result.get('signal_strength', 0):.2f})"
                    )

        # 4. Process exit signals (always allow exits)
        exit_candidates = [
            (coin, result)
            for coin, result in coin_results.items()
            if result['action'] == 'SELL' and self.executor.has_position(coin)
        ]

        for coin, result in exit_candidates:
            decisions.append((coin, 'SELL', 0))  # entry_number=0 for exits
            exit_reason = result.get('reason', 'Exit signal')
            self.logger.logger.info(f"Exit decision: {coin} ({exit_reason})")

        self.last_decisions = decisions
        return decisions

    def _can_pyramid(self, coin: str, result: Dict) -> bool:
        """
        Check if additional entry (pyramiding) is allowed for a coin.

        Pyramiding Conditions:
        1. Pyramiding enabled in config
        2. Entry count below maximum
        3. Score meets pyramid threshold
        4. Signal strength meets threshold
        5. Price increased enough from last entry
        6. Market regime allows pyramiding

        Args:
            coin: Cryptocurrency symbol
            result: Analysis result from strategy

        Returns:
            True if pyramiding is allowed
        """
        pyramid_config = self.config.get('PYRAMIDING_CONFIG', {})

        # Check if pyramiding enabled
        if not pyramid_config.get('enabled', False):
            return False

        # Check entry count limit
        entry_count = self.executor.get_entry_count(coin)
        max_entries = pyramid_config.get('max_entries_per_coin', 3)
        if entry_count >= max_entries:
            self.logger.logger.debug(
                f"Pyramid blocked for {coin}: Max entries reached ({entry_count}/{max_entries})"
            )
            return False

        # Check score threshold
        min_score = pyramid_config.get('min_score_for_pyramid', 3)
        entry_score = result.get('entry_score', 0)
        if entry_score < min_score:
            self.logger.logger.debug(
                f"Pyramid blocked for {coin}: Score too low ({entry_score}/{min_score})"
            )
            return False

        # Check signal strength threshold
        min_strength = pyramid_config.get('min_signal_strength_for_pyramid', 0.7)
        signal_strength = result.get('signal_strength', 0.0)
        if signal_strength < min_strength:
            self.logger.logger.debug(
                f"Pyramid blocked for {coin}: Signal strength too low ({signal_strength:.2f}/{min_strength})"
            )
            return False

        # Check price increase from last entry
        current_price = result.get('current_price', 0)
        last_entry_price = self.executor.get_last_entry_price(coin)
        min_increase_pct = pyramid_config.get('min_price_increase_pct', 2.0)

        if last_entry_price > 0:
            price_increase_pct = ((current_price - last_entry_price) / last_entry_price) * 100
            if price_increase_pct < min_increase_pct:
                self.logger.logger.debug(
                    f"Pyramid blocked for {coin}: Price increase too low "
                    f"({price_increase_pct:.2f}%/{min_increase_pct}%)"
                )
                return False

        # Check market regime
        allowed_regimes = pyramid_config.get('allow_pyramid_in_regime', ['bullish', 'neutral'])
        market_regime = result.get('market_regime', 'neutral')
        if market_regime not in allowed_regimes:
            self.logger.logger.debug(
                f"Pyramid blocked for {coin}: Regime not allowed ({market_regime} not in {allowed_regimes})"
            )
            return False

        # All checks passed
        self.logger.logger.info(
            f"Pyramid allowed for {coin}: "
            f"Score={entry_score}, Strength={signal_strength:.2f}, "
            f"Price increase={price_increase_pct:.2f}%"
        )
        return True

    def execute_decisions(self, decisions: List[Tuple[str, str, int]]):
        """
        Execute trading decisions through LiveExecutorV3 with pyramiding support.

        Args:
            decisions: List of (coin, action, entry_number) tuples from make_portfolio_decision()
                      Example: [('ETH', 'BUY', 1), ('BTC', 'BUY', 2), ('XRP', 'SELL', 0)]
                      entry_number: 1=new position, 2+=pyramiding, 0=exit
        """
        for coin, action, entry_number in decisions:
            monitor = self.monitors[coin]
            analysis = monitor.last_analysis

            if action == 'BUY':
                # Entry parameters from analysis
                price = analysis.get('current_price', 0)

                # For NEW positions, calculate stop-loss based on entry price
                # For pyramiding, use existing stop-loss from analysis
                if entry_number == 1:  # New position
                    # Calculate stop-loss using entry price as initial highest_high
                    # Formula: entry_price - (ATR × multiplier)
                    execution_data = analysis.get('execution_data', {})
                    atr = execution_data.get('atr', 0)
                    chandelier_multiplier = self.config.get('INDICATOR_CONFIG', {}).get('chandelier_multiplier', 3.0)
                    stop_loss = price - (atr * chandelier_multiplier)

                    self.logger.logger.info(
                        f"Calculated initial stop-loss for {coin}: {stop_loss:,.0f} KRW "
                        f"(Entry: {price:,.0f}, ATR: {atr:,.2f}, Multiplier: {chandelier_multiplier})"
                    )
                else:  # Pyramiding - use existing stop-loss
                    stop_loss = analysis.get('stop_loss_price', 0)

                if price <= 0:
                    self.logger.logger.error(
                        f"Invalid price for {coin}: {price}, skipping order"
                    )
                    continue

                # Calculate position size with pyramiding multiplier
                base_amount_krw = self.config['TRADING_CONFIG'].get('trade_amount_krw', 50000)

                if entry_number > 1:  # Pyramiding
                    pyramid_config = self.config.get('PYRAMIDING_CONFIG', {})
                    multipliers = pyramid_config.get('position_size_multiplier', [1.0, 0.5, 0.25])
                    multiplier = multipliers[entry_number - 1] if entry_number <= len(multipliers) else multipliers[-1]
                    trade_amount_krw = base_amount_krw * multiplier

                    self.logger.logger.info(
                        f"Pyramid entry #{entry_number} for {coin}: "
                        f"Using {multiplier*100:.0f}% position size ({trade_amount_krw:,.0f} KRW)"
                    )
                else:  # New position
                    trade_amount_krw = base_amount_krw

                units = trade_amount_krw / price

                # Execute buy order
                order_result = self.executor.execute_order(
                    ticker=coin,
                    action='BUY',
                    units=units,
                    price=price,
                    dry_run=self.config['EXECUTION_CONFIG'].get('dry_run', True),
                    reason=(
                        f"{'Pyramid ' if entry_number > 1 else ''}Entry score: {analysis.get('entry_score')}/4, "
                        f"regime: {analysis.get('market_regime')}"
                    )
                )

                if order_result.get('success'):
                    # Update stop-loss
                    self.executor.update_stop_loss(coin, stop_loss)
                    # Track last executed action
                    self.last_executed_actions[coin] = 'BUY'
                    self._save_last_actions()  # Persist to file
                    if entry_number > 1:
                        self.logger.logger.info(
                            f"{coin} pyramid #{entry_number} added: {units:.6f} @ {price:,.0f} KRW"
                        )
                    else:
                        self.logger.logger.info(
                            f"{coin} position opened: {units:.6f} @ {price:,.0f} KRW"
                        )
                else:
                    self.logger.logger.error(
                        f"{coin} order failed: {order_result.get('message')}"
                    )

            elif action == 'PARTIAL_SELL_50':
                # First target hit - 50% partial exit
                price = analysis.get('current_price', 0)

                if price <= 0:
                    self.logger.logger.error(
                        f"Invalid price for {coin}: {price}, skipping order"
                    )
                    continue

                # Execute 50% partial exit
                order_result = self.executor.execute_partial_exit(
                    ticker=coin,
                    exit_pct=50.0,
                    price=price,
                    dry_run=self.config['EXECUTION_CONFIG'].get('dry_run', True),
                    reason="First target (BB middle) reached"
                )

                if order_result.get('success'):
                    # Mark first target as hit
                    self.executor.mark_first_target_hit(coin)

                    # Move stop-loss to breakeven
                    exit_config = self.config.get('EXIT_CONFIG', {})
                    if exit_config.get('trail_after_breakeven', True):
                        pos_summary = self.executor.get_position_summary(coin)
                        entry_price = pos_summary['entry_price']
                        self.executor.update_stop_loss(coin, entry_price)
                        self.logger.logger.info(
                            f"{coin} stop-loss moved to breakeven: {entry_price:,.0f} KRW"
                        )

                    self.logger.logger.info(
                        f"{coin} first target reached: 50% sold @ {price:,.0f} KRW"
                    )
                else:
                    self.logger.logger.error(
                        f"{coin} partial exit failed: {order_result.get('message')}"
                    )

            elif action == 'SELL':
                # Exit at current price (full exit or second target)
                price = analysis.get('current_price', 0)

                if price <= 0:
                    self.logger.logger.error(
                        f"Invalid price for {coin}: {price}, skipping order"
                    )
                    continue

                # Check if this is second target or regular exit
                pos_summary = self.executor.get_position_summary(coin)
                first_target_hit = pos_summary.get('first_target_hit', False)

                # Close entire position
                order_result = self.executor.close_position(
                    ticker=coin,
                    price=price,
                    dry_run=self.config['EXECUTION_CONFIG'].get('dry_run', True),
                    reason="Second target (BB upper) reached" if first_target_hit else analysis.get('reason', 'Exit signal')
                )

                if order_result.get('success'):
                    # Mark second target as hit if first was hit
                    if first_target_hit:
                        self.executor.mark_second_target_hit(coin)

                    # Track last executed action
                    self.last_executed_actions[coin] = 'SELL'
                    self._save_last_actions()  # Persist to file
                    self.logger.logger.info(
                        f"{coin} position closed @ {price:,.0f} KRW"
                    )
                else:
                    self.logger.logger.error(
                        f"{coin} exit failed: {order_result.get('message')}"
                    )

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive portfolio summary for GUI display.

        Returns:
            Dictionary with portfolio state:
            {
                'total_positions': int,
                'max_positions': int,
                'total_pnl_krw': float,
                'coins': {
                    'BTC': {
                        'analysis': {...},
                        'position': {...},
                        'last_update': str (ISO format)
                    },
                    ...
                },
                'last_decisions': List[Tuple[str, str, int]]  # (coin, action, entry_number)
            }
        """
        # Count positions
        active_positions = [
            coin for coin in self.coins
            if self.executor.has_position(coin)
        ]

        # Portfolio-level stats
        total_pnl = 0.0
        for coin in active_positions:
            position = self.executor.get_position(coin)
            if position:
                # Get current price from last analysis
                current_price = self.last_results.get(coin, {}).get(
                    'current_price', position.entry_price
                )
                pnl = (current_price - position.entry_price) * position.size
                total_pnl += pnl

        return {
            'total_positions': len(active_positions),
            'max_positions': self.config.get('PORTFOLIO_CONFIG', {}).get('max_positions', 2),
            'total_pnl_krw': total_pnl,
            'coins': {
                coin: {
                    'analysis': self.last_results.get(coin, {}),
                    'position': self.monitors[coin].get_position_summary(),
                    'last_update': (
                        self.monitors[coin].last_update.isoformat()
                        if self.monitors[coin].last_update
                        else None
                    ),
                    'last_executed_action': self.last_executed_actions.get(coin, '-'),  # Add last executed action
                }
                for coin in self.coins
            },
            'last_decisions': self.last_decisions,
        }

    def get_monitor(self, coin: str) -> Optional[CoinMonitor]:
        """
        Get CoinMonitor for specific coin.

        Args:
            coin: Cryptocurrency symbol

        Returns:
            CoinMonitor instance or None if coin not monitored
        """
        return self.monitors.get(coin)
