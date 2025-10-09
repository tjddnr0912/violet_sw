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

        self.logger.logger.info(f"Portfolio Manager V3 initialized with coins: {coins}")

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

    def make_portfolio_decision(self, coin_results: Dict[str, Dict]) -> List[Tuple[str, str]]:
        """
        Make portfolio-level trading decisions with risk limits.

        Decision Logic:
        1. Count current positions
        2. Check portfolio position limit
        3. Prioritize entry signals by score (highest first)
        4. Allow exits regardless of limits

        Args:
            coin_results: Analysis results from analyze_all()

        Returns:
            List of (coin, action) tuples to execute:
            [('XRP', 'BUY'), ('BTC', 'BUY')] - in priority order
        """
        decisions = []

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

        # 3. Process entry signals
        entry_candidates = [
            (coin, result)
            for coin, result in coin_results.items()
            if result['action'] == 'BUY' and not self.executor.has_position(coin)
        ]

        if entry_candidates:
            self.logger.logger.info(
                f"Entry candidates: {[c[0] for c in entry_candidates]}"
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

            # Apply portfolio position limit
            for coin, result in entry_candidates:
                if total_positions >= max_positions:
                    self.logger.logger.info(
                        f"Portfolio limit reached ({max_positions} positions), skipping {coin} entry"
                    )
                    break

                decisions.append((coin, 'BUY'))
                total_positions += 1
                self.logger.logger.info(
                    f"Entry decision: {coin} (score: {result.get('entry_score')}/4, "
                    f"strength: {result.get('signal_strength', 0):.2f})"
                )

        # 4. Process exit signals (always allow exits)
        exit_candidates = [
            (coin, result)
            for coin, result in coin_results.items()
            if result['action'] == 'SELL' and self.executor.has_position(coin)
        ]

        for coin, result in exit_candidates:
            decisions.append((coin, 'SELL'))
            exit_reason = result.get('reason', 'Exit signal')
            self.logger.logger.info(f"Exit decision: {coin} ({exit_reason})")

        self.last_decisions = decisions
        return decisions

    def execute_decisions(self, decisions: List[Tuple[str, str]]):
        """
        Execute trading decisions through LiveExecutorV3.

        Args:
            decisions: List of (coin, action) tuples from make_portfolio_decision()
                      Example: [('ETH', 'BUY'), ('BTC', 'SELL')]
        """
        for coin, action in decisions:
            monitor = self.monitors[coin]
            analysis = monitor.last_analysis

            if action == 'BUY':
                # Entry parameters from analysis
                price = analysis.get('current_price', 0)
                stop_loss = analysis.get('stop_loss_price', 0)

                if price <= 0:
                    self.logger.logger.error(
                        f"Invalid price for {coin}: {price}, skipping order"
                    )
                    continue

                # Calculate position size
                trade_amount_krw = self.config['TRADING_CONFIG'].get('trade_amount_krw', 50000)
                units = trade_amount_krw / price

                # Execute buy order
                order_result = self.executor.execute_order(
                    ticker=coin,
                    action='BUY',
                    units=units,
                    price=price,
                    dry_run=self.config['EXECUTION_CONFIG'].get('dry_run', True),
                    reason=(
                        f"Entry score: {analysis.get('entry_score')}/4, "
                        f"regime: {analysis.get('market_regime')}"
                    )
                )

                if order_result.get('success'):
                    # Update stop-loss
                    self.executor.update_stop_loss(coin, stop_loss)
                    self.logger.logger.info(
                        f"{coin} position opened: {units:.6f} @ {price:,.0f} KRW"
                    )
                else:
                    self.logger.logger.error(
                        f"{coin} order failed: {order_result.get('message')}"
                    )

            elif action == 'SELL':
                # Exit at current price
                price = analysis.get('current_price', 0)

                if price <= 0:
                    self.logger.logger.error(
                        f"Invalid price for {coin}: {price}, skipping order"
                    )
                    continue

                # Close entire position
                order_result = self.executor.close_position(
                    ticker=coin,
                    price=price,
                    dry_run=self.config['EXECUTION_CONFIG'].get('dry_run', True),
                    reason=analysis.get('reason', 'Exit signal')
                )

                if order_result.get('success'):
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
                'last_decisions': List[Tuple[str, str]]
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
