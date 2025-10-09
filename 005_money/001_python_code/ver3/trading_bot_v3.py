"""
Trading Bot V3 - Multi-Coin Portfolio Coordinator

This module implements the main trading bot for Ver3, coordinating
portfolio-level multi-coin trading using the Portfolio Manager Pattern.

Key Responsibilities:
- Initialize PortfolioManagerV3 with selected coins
- Run periodic analysis cycles (15-minute intervals)
- Coordinate portfolio-level decision making
- Execute trades through thread-safe LiveExecutorV3
- Provide status updates and logging

Usage:
    from ver3.trading_bot_v3 import TradingBotV3
    from ver3.config_v3 import get_version_config

    config = get_version_config()
    bot = TradingBotV3(config)
    bot.run()
"""

import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from ver3.portfolio_manager_v3 import PortfolioManagerV3
from ver3.config_v3 import get_version_config, get_portfolio_config
from lib.api.bithumb_api import BithumbAPI
from lib.core.logger import TradingLogger
from lib.interfaces.version_interface import VersionInterface


class TradingBotV3(VersionInterface):
    """
    Version 3 Trading Bot - Multi-Coin Portfolio Manager

    This bot coordinates multi-coin portfolio trading using the
    Portfolio Manager Pattern with parallel analysis and centralized
    risk management.

    Architecture:
    - Uses PortfolioManagerV3 for multi-coin coordination
    - Analyzes 2-3 coins in parallel every 15 minutes
    - Makes portfolio-level trading decisions
    - Executes trades through thread-safe LiveExecutorV3

    Features:
    - Multi-coin simultaneous trading
    - Portfolio position limits (max 2)
    - Entry signal prioritization
    - Thread-safe execution
    - Comprehensive logging
    """

    VERSION_NAME = "ver3"
    VERSION_DISPLAY_NAME = "Portfolio Multi-Coin Strategy"
    VERSION_DESCRIPTION = "Multi-coin portfolio trading with parallel analysis and coordinated risk management"
    VERSION_AUTHOR = "Claude AI"
    VERSION_DATE = "2025-10-08"

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Trading Bot V3.

        Args:
            config: Configuration dictionary from config_v3.py
        """
        self.config = config
        self.running = False

        # Extract portfolio configuration
        self.portfolio_config = config.get('PORTFOLIO_CONFIG', {})
        self.coins = self.portfolio_config.get('default_coins', ['BTC', 'ETH', 'XRP'])
        self.check_interval = config.get('SCHEDULE_CONFIG', {}).get('check_interval_seconds', 900)

        # Initialize logger
        log_config = config.get('LOGGING_CONFIG', {})
        self.logger = TradingLogger(log_dir=log_config.get('log_dir', 'logs'))

        # Initialize API
        self.api = BithumbAPI()

        # Initialize Portfolio Manager
        self.portfolio_manager = PortfolioManagerV3(
            coins=self.coins,
            config=config,
            api=self.api,
            logger=self.logger
        )

        # State tracking
        self.cycle_count = 0
        self.last_analysis_time = None

        self.logger.logger.info("=" * 60)
        self.logger.logger.info(f"Trading Bot V3 Initialized")
        self.logger.logger.info(f"  Version: {self.VERSION_NAME}")
        self.logger.logger.info(f"  Display Name: {self.VERSION_DISPLAY_NAME}")
        self.logger.logger.info(f"  Coins: {', '.join(self.coins)}")
        self.logger.logger.info(f"  Max Positions: {self.portfolio_config.get('max_positions', 2)}")
        self.logger.logger.info(f"  Check Interval: {self.check_interval}s ({self.check_interval//60}min)")
        self.logger.logger.info("=" * 60)

    # ========================================
    # VersionInterface Implementation
    # ========================================

    def get_config(self) -> Dict[str, Any]:
        """Get current configuration."""
        return self.config

    def get_indicator_names(self) -> List[str]:
        """Get list of indicator names used in this version."""
        # Ver3 uses Ver2 strategy, so same indicators per coin
        return [
            'ema_fast',
            'ema_slow',
            'bb_upper',
            'bb_middle',
            'bb_lower',
            'rsi',
            'stoch_rsi_k',
            'stoch_rsi_d',
            'atr',
            'chandelier_stop',
        ]

    def get_supported_intervals(self) -> List[str]:
        """Get supported candlestick intervals."""
        return ['4h', '24h']

    def validate_configuration(self) -> tuple:
        """Validate current configuration."""
        from ver3.config_v3 import validate_portfolio_config
        return validate_portfolio_config(self.config)

    def get_chart_config(self) -> Dict[str, Any]:
        """Get chart configuration for GUI."""
        return self.config.get('CHART_CONFIG', {})

    def analyze_market(self, coin_symbol: str, interval: str = "4h", limit: int = 200) -> Dict[str, Any]:
        """
        Analyze market for a single coin (delegates to portfolio manager).

        Args:
            coin_symbol: Cryptocurrency symbol
            interval: Candlestick interval
            limit: Number of candles

        Returns:
            Analysis result dictionary
        """
        monitor = self.portfolio_manager.get_monitor(coin_symbol)
        if monitor:
            return monitor.analyze()
        else:
            return {
                'action': 'HOLD',
                'signal_strength': 0.0,
                'reason': f'Coin {coin_symbol} not monitored',
                'market_regime': 'unknown',
                'entry_score': 0,
            }

    # ========================================
    # Bot Control Methods
    # ========================================

    def run(self):
        """
        Run the trading bot main loop.

        This method:
        1. Analyzes all coins in parallel
        2. Makes portfolio-level decisions
        3. Executes trades
        4. Sleeps until next cycle
        """
        self.running = True
        self.logger.logger.info("\n" + "=" * 60)
        self.logger.logger.info("Trading Bot V3 Started")
        self.logger.logger.info("=" * 60)

        try:
            while self.running:
                self.cycle_count += 1
                cycle_start = time.time()

                self.logger.logger.info(f"\n{'='*60}")
                self.logger.logger.info(f"Analysis Cycle #{self.cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self.logger.logger.info(f"{'='*60}")

                try:
                    # 1. Analyze all coins in parallel
                    results = self.portfolio_manager.analyze_all()

                    # 2. Make portfolio-level decisions
                    decisions = self.portfolio_manager.make_portfolio_decision(results)

                    # 3. Execute trading decisions
                    if decisions:
                        self.portfolio_manager.execute_decisions(decisions)
                    else:
                        self.logger.logger.info("No trading actions required (HOLD)")

                    # 4. Log portfolio summary
                    summary = self.portfolio_manager.get_portfolio_summary()
                    self._log_portfolio_summary(summary)

                    self.last_analysis_time = datetime.now()

                except Exception as e:
                    self.logger.log_error("Error in analysis cycle", e)
                    import traceback
                    self.logger.logger.error(traceback.format_exc())

                # Sleep until next cycle
                cycle_elapsed = time.time() - cycle_start
                sleep_time = max(0, self.check_interval - cycle_elapsed)

                if sleep_time > 0:
                    self.logger.logger.info(
                        f"\nCycle completed in {cycle_elapsed:.2f}s. "
                        f"Sleeping {sleep_time:.0f}s until next cycle..."
                    )
                    time.sleep(sleep_time)
                else:
                    self.logger.logger.warning(
                        f"\nCycle took {cycle_elapsed:.2f}s (exceeds interval of {self.check_interval}s)"
                    )

        except KeyboardInterrupt:
            self.logger.logger.info("\nKeyboard interrupt received. Stopping bot...")
            self.stop()
        except Exception as e:
            self.logger.log_error("Fatal error in main loop", e)
            import traceback
            self.logger.logger.error(traceback.format_exc())
            self.stop()

    def stop(self):
        """Stop the trading bot."""
        self.running = False
        self.logger.logger.info("\n" + "=" * 60)
        self.logger.logger.info("Trading Bot V3 Stopped")
        self.logger.logger.info(f"Total cycles completed: {self.cycle_count}")
        self.logger.logger.info("=" * 60)

    def _log_portfolio_summary(self, summary: Dict[str, Any]):
        """
        Log portfolio summary.

        Args:
            summary: Portfolio summary from get_portfolio_summary()
        """
        self.logger.logger.info("\n" + "-" * 60)
        self.logger.logger.info("Portfolio Summary")
        self.logger.logger.info("-" * 60)

        # Portfolio stats
        total_pos = summary.get('total_positions', 0)
        max_pos = summary.get('max_positions', 2)
        total_pnl = summary.get('total_pnl_krw', 0)

        self.logger.logger.info(f"Positions: {total_pos}/{max_pos}")
        self.logger.logger.info(f"Total P&L: {total_pnl:+,.0f} KRW")

        # Per-coin summary
        coins_data = summary.get('coins', {})
        if coins_data:
            self.logger.logger.info("\nPer-Coin Status:")
            for coin, data in coins_data.items():
                analysis = data.get('analysis', {})
                position = data.get('position', {})

                regime = analysis.get('market_regime', '?')
                score = analysis.get('entry_score', 0)
                action = analysis.get('action', 'HOLD')

                has_pos = position.get('has_position', False)
                pos_info = ""
                if has_pos:
                    entry_price = position.get('entry_price', 0)
                    pnl = position.get('pnl', 0)
                    pos_info = f" | Position: {entry_price:,.0f} KRW | P&L: {pnl:+,.0f}"

                self.logger.logger.info(
                    f"  [{coin}] {regime.upper():8s} | Score: {score}/4 | "
                    f"Action: {action:4s}{pos_info}"
                )

        self.logger.logger.info("-" * 60)

    # ========================================
    # Version Information Methods
    # ========================================

    def get_strategy_description(self) -> str:
        """Get human-readable strategy description."""
        return f"""
{self.VERSION_DISPLAY_NAME}

Architecture: Portfolio Manager Pattern
- Monitors {len(self.coins)} coins: {', '.join(self.coins)}
- Parallel analysis using ThreadPoolExecutor
- Portfolio-level risk management
- Thread-safe concurrent execution

Key Features:
1. Multi-Coin Analysis
   - Each coin analyzed using Ver2 strategy
   - Parallel execution for efficiency
   - {self.check_interval//60}-minute analysis intervals

2. Portfolio Risk Management
   - Max {self.portfolio_config.get('max_positions', 2)} simultaneous positions
   - Entry prioritization by signal score
   - {self.portfolio_config.get('max_portfolio_risk_pct', 6.0)}% total portfolio risk limit

3. Individual Coin Strategy (Ver2)
   - Daily EMA(50/200) regime filter
   - 4H score-based entry system
   - ATR-based Chandelier Exit
   - Partial position management

4. Thread Safety
   - Position updates use threading.Lock
   - Safe concurrent order execution
   - Isolated per-coin analysis

Configuration:
- Coins: {', '.join(self.coins)}
- Max Positions: {self.portfolio_config.get('max_positions', 2)}
- Analysis Interval: {self.check_interval}s ({self.check_interval//60}min)
- Trade Amount: {self.config.get('TRADING_CONFIG', {}).get('trade_amount_krw', 50000):,} KRW per coin
"""

    def get_version_info(self) -> Dict[str, Any]:
        """Get version information."""
        return {
            'name': self.VERSION_NAME,
            'display_name': self.VERSION_DISPLAY_NAME,
            'description': self.VERSION_DESCRIPTION,
            'author': self.VERSION_AUTHOR,
            'date': self.VERSION_DATE,
            'coins': self.coins,
            'max_positions': self.portfolio_config.get('max_positions', 2),
            'check_interval_seconds': self.check_interval,
            'cycle_count': self.cycle_count,
            'last_analysis': self.last_analysis_time.isoformat() if self.last_analysis_time else None,
            'running': self.running,
        }

    # ========================================
    # Utility Methods
    # ========================================

    def update_coins(self, new_coins: List[str]):
        """
        Update the list of monitored coins.

        Args:
            new_coins: New list of coin symbols to monitor
        """
        self.logger.logger.info(f"Updating monitored coins from {self.coins} to {new_coins}")
        self.coins = new_coins
        self.portfolio_manager.update_monitored_coins(new_coins)
        self.logger.logger.info("Coin list updated successfully")

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get current portfolio summary.

        Returns:
            Portfolio summary dictionary
        """
        return self.portfolio_manager.get_portfolio_summary()
