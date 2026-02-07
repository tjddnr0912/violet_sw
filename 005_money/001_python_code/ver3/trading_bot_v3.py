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
from lib.core.logger import TradingLogger, MarkdownTransactionLogger, TransactionHistory
from lib.interfaces.version_interface import VersionInterface
from lib.core.telegram_notifier import get_telegram_notifier
from lib.core.telegram_bot_handler import get_telegram_bot_handler

# Dynamic factor system imports
from ver3.dynamic_factor_manager import get_dynamic_factor_manager
from ver3.performance_tracker import get_performance_tracker


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

    def __init__(self, config: Dict[str, Any], log_prefix: str = 'ver3_cli'):
        """
        Initialize Trading Bot V3.

        Args:
            config: Configuration dictionary from config_v3.py
            log_prefix: Prefix for log filename (default: 'ver3_cli')
        """
        self.config = config
        self.running = False

        # Extract portfolio configuration
        self.portfolio_config = config.get('PORTFOLIO_CONFIG', {})
        self.coins = self.portfolio_config.get('default_coins', ['BTC', 'ETH', 'XRP'])
        self.check_interval = config.get('SCHEDULE_CONFIG', {}).get('check_interval_seconds', 900)

        # Initialize logger with specified prefix
        log_config = config.get('LOGGING_CONFIG', {})
        log_dir = log_config.get('log_dir', 'logs')
        self.logger = TradingLogger(log_dir=log_dir, log_prefix=log_prefix)
        self.markdown_logger = MarkdownTransactionLogger()
        self.transaction_history = TransactionHistory(history_file=f'{log_dir}/transaction_history.json')

        # Initialize API with keys from environment variables or config
        import os
        api_config = config.get('API_CONFIG', {})
        connect_key = os.getenv('BITHUMB_CONNECT_KEY') or api_config.get('bithumb_connect_key')
        secret_key = os.getenv('BITHUMB_SECRET_KEY') or api_config.get('bithumb_secret_key')

        if connect_key and secret_key:
            self.api = BithumbAPI(connect_key, secret_key)
            self.logger.logger.info("API initialized with credentials")
        else:
            self.api = BithumbAPI()
            self.logger.logger.warning("API initialized WITHOUT credentials - trading will fail")

        # Initialize Portfolio Manager
        self.portfolio_manager = PortfolioManagerV3(
            coins=self.coins,
            config=config,
            api=self.api,
            logger=self.logger,
            markdown_logger=self.markdown_logger,
            transaction_history=self.transaction_history
        )

        # State tracking
        self.cycle_count = 0
        self.last_analysis_time = None

        # Initialize Telegram notifier
        self.telegram = get_telegram_notifier()

        # Initialize Telegram bot handler (for interactive commands)
        self.telegram_handler = get_telegram_bot_handler(self)

        # Daily summary tracking
        self._daily_summary_sent_date = None  # Track which date we sent summary for

        # Initialize dynamic factor system
        self.factor_manager = get_dynamic_factor_manager(config, self.logger)
        self.performance_tracker = get_performance_tracker()

        # Factor update tracking
        self._last_daily_factor_update = None  # Track last daily factor update date
        self._last_weekly_factor_update = None  # Track last weekly factor update week

        # Regime change tracking (for telegram alerts)
        self._previous_regime = None  # Track previous regime for change detection
        self._last_regime_alert_time = None  # Debounce: prevent frequent regime alerts
        self._regime_alert_cooldown = 1800  # 30 minutes cooldown between same regime alerts

        # Consecutive timeout tracking (for auto-restart)
        self._consecutive_timeout_count = 0
        self._max_consecutive_timeouts = 3  # 3회 연속 timeout 시 자동 재시작 (15분)

        # Circuit breaker for API failures
        self._api_failure_count = 0
        self._circuit_breaker_open = False
        self._circuit_breaker_open_time = None
        self._circuit_breaker_threshold = 5  # Open after 5 consecutive failures
        self._circuit_breaker_cooldown = 300  # 5 minutes

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
        return ['1h', '24h']

    def validate_configuration(self) -> tuple:
        """Validate current configuration."""
        from ver3.config_v3 import validate_portfolio_config
        return validate_portfolio_config(self.config)

    def get_chart_config(self) -> Dict[str, Any]:
        """Get chart configuration for GUI."""
        return self.config.get('CHART_CONFIG', {})

    def analyze_market(self, coin_symbol: str, interval: str = "1h", limit: int = 200) -> Dict[str, Any]:
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

        # Send startup notification
        try:
            current_positions = len(self.portfolio_manager.executor.positions)
            self.telegram.send_bot_status(
                status="STARTED",
                positions=current_positions,
                max_positions=self.portfolio_config.get('max_positions', 2),
                total_pnl=0,
                coins=self.coins
            )
        except Exception as e:
            self.logger.logger.warning(f"Failed to send startup Telegram notification: {e}")

        # Start Telegram command handler (for /status, /stop, etc.)
        try:
            self.telegram_handler.start()
            self.logger.logger.info("Telegram command handler started")
        except Exception as e:
            self.logger.logger.warning(f"Failed to start Telegram command handler: {e}")

        try:
            while self.running:
                self.cycle_count += 1
                cycle_start = time.time()

                self.logger.logger.info(f"\n{'='*60}")
                self.logger.logger.info(f"Analysis Cycle #{self.cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self.logger.logger.info(f"{'='*60}")

                try:
                    # Circuit breaker check
                    if self._circuit_breaker_open:
                        elapsed = time.time() - (self._circuit_breaker_open_time or 0)
                        if elapsed < self._circuit_breaker_cooldown:
                            remaining = self._circuit_breaker_cooldown - elapsed
                            self.logger.logger.warning(
                                f"⚡ Circuit breaker OPEN: {remaining:.0f}s remaining. Skipping analysis."
                            )
                            time.sleep(min(remaining, 60))
                            continue
                        else:
                            self._circuit_breaker_open = False
                            self._api_failure_count = 0
                            self.logger.logger.info("⚡ Circuit breaker CLOSED: Resuming analysis.")

                    # Track analysis time for hang detection
                    analysis_start = time.time()
                    ANALYSIS_CYCLE_WARNING_THRESHOLD = 180  # 3 minutes warning

                    # 1. Analyze all coins in parallel
                    results = self.portfolio_manager.analyze_all()

                    # Check for timeout results (now using timeout_occurred flag)
                    timeout_coins = [
                        coin for coin, result in results.items()
                        if result.get('timeout_occurred', False)
                    ]

                    # Check for consecutive all-timeout and trigger auto-restart
                    if timeout_coins:
                        self.logger.logger.warning(f"Analysis timeout occurred for: {timeout_coins}")

                        # Check if ALL coins timed out
                        all_timeout = len(timeout_coins) == len(results)
                        if all_timeout:
                            self._consecutive_timeout_count += 1
                            self.logger.logger.warning(
                                f"All coins timed out ({self._consecutive_timeout_count}/{self._max_consecutive_timeouts})"
                            )

                            if self._consecutive_timeout_count >= self._max_consecutive_timeouts:
                                self.logger.logger.error(
                                    f"Consecutive timeout limit reached. Triggering restart..."
                                )
                                try:
                                    self.telegram.send_message(
                                        "🚨 *연속 Timeout 감지*\n\n"
                                        f"연속 {self._consecutive_timeout_count}회 모든 코인 Timeout.\n"
                                        "자동 재시작을 트리거합니다.",
                                        parse_mode='Markdown'
                                    )
                                except Exception:
                                    pass
                                # Exit with non-zero code for watchdog to restart
                                # Use os._exit() to force terminate all threads (including Telegram asyncio loop)
                                self.running = False
                                import os
                                os._exit(1)
                        else:
                            # 일부만 timeout - 단건 알림만 전송
                            try:
                                self.telegram.send_message(
                                    f"⚠️ Analysis Timeout\n"
                                    f"Coins: {', '.join(timeout_coins)}\n"
                                    f"Bot continues with HOLD for these coins."
                                )
                            except Exception:
                                pass  # Don't let telegram failure block the cycle
                    else:
                        # 정상 분석 시 카운터 리셋
                        if self._consecutive_timeout_count > 0:
                            self.logger.logger.info(
                                f"Timeout recovery: consecutive count reset (was {self._consecutive_timeout_count})"
                            )
                        self._consecutive_timeout_count = 0

                    # 2. Check for regime changes and send alerts
                    self._check_and_send_regime_change_alert(results)

                    # 3. Make portfolio-level decisions
                    decisions = self.portfolio_manager.make_portfolio_decision(results)

                    # 4. Execute trading decisions
                    if decisions:
                        self.portfolio_manager.execute_decisions(decisions)
                    else:
                        self.logger.logger.info("No trading actions required (HOLD)")

                    # 5. Log portfolio summary
                    summary = self.portfolio_manager.get_portfolio_summary()
                    self._log_portfolio_summary(summary)

                    self.last_analysis_time = datetime.now()

                    # Check if analysis took too long (warning threshold)
                    analysis_elapsed = time.time() - analysis_start
                    if analysis_elapsed > ANALYSIS_CYCLE_WARNING_THRESHOLD:
                        self.logger.logger.warning(
                            f"Analysis cycle took {analysis_elapsed:.1f}s (threshold: {ANALYSIS_CYCLE_WARNING_THRESHOLD}s)"
                        )

                except Exception as e:
                    self.logger.log_error("Error in analysis cycle", e)
                    import traceback
                    self.logger.logger.error(traceback.format_exc())

                    # Circuit breaker: track API failures
                    self._api_failure_count += 1
                    if self._api_failure_count >= self._circuit_breaker_threshold:
                        self._circuit_breaker_open = True
                        self._circuit_breaker_open_time = time.time()
                        self.logger.logger.error(
                            f"⚡ Circuit breaker OPENED: {self._api_failure_count} consecutive failures. "
                            f"Pausing for {self._circuit_breaker_cooldown}s."
                        )
                        try:
                            self.telegram.send_message(
                                f"⚡ *Circuit Breaker OPEN*\n\n"
                                f"연속 {self._api_failure_count}회 분석 실패.\n"
                                f"{self._circuit_breaker_cooldown // 60}분간 분석 중단.",
                                parse_mode='Markdown'
                            )
                        except Exception:
                            pass
                else:
                    # Reset failure count on successful cycle
                    if self._api_failure_count > 0:
                        self.logger.logger.info(
                            f"API failure count reset (was {self._api_failure_count})"
                        )
                    self._api_failure_count = 0

                # Check and run scheduled factor updates (daily at 00:00, weekly on Sunday)
                self._check_scheduled_factor_updates()

                # Check and send daily summary at 23:50
                self._check_and_send_daily_summary()

                # Adaptive analysis interval: shorter in bear + high volatility
                effective_interval = self._get_adaptive_interval()

                # Sleep until next cycle
                cycle_elapsed = time.time() - cycle_start
                sleep_time = max(0, effective_interval - cycle_elapsed)

                if sleep_time > 0:
                    interval_note = ""
                    if effective_interval != self.check_interval:
                        interval_note = f" (adaptive: {effective_interval}s)"
                    self.logger.logger.info(
                        f"\nCycle completed in {cycle_elapsed:.2f}s. "
                        f"Sleeping {sleep_time:.0f}s until next cycle...{interval_note}"
                    )
                    time.sleep(sleep_time)
                else:
                    self.logger.logger.warning(
                        f"\nCycle took {cycle_elapsed:.2f}s (exceeds interval of {effective_interval}s)"
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

        # Stop Telegram command handler
        try:
            self.telegram_handler.stop()
            self.logger.logger.info("Telegram command handler stopped")
        except Exception as e:
            self.logger.logger.warning(f"Failed to stop Telegram command handler: {e}")

        # Send shutdown notification
        try:
            current_positions = len(self.portfolio_manager.executor.positions)
            self.telegram.send_bot_status(
                status="STOPPED",
                positions=current_positions,
                max_positions=self.portfolio_config.get('max_positions', 2),
                total_pnl=0,  # Could calculate actual P&L if needed
                coins=self.coins
            )
        except Exception as e:
            self.logger.logger.warning(f"Failed to send shutdown Telegram notification: {e}")
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
                timeout_flag = analysis.get('timeout_occurred', False)
                # Timeout 발생 시 (⏱) 표시 추가
                regime_suffix = " (⏱)" if timeout_flag else ""
                score = analysis.get('entry_score', 0)
                action = analysis.get('action', 'HOLD')

                has_pos = position.get('has_position', False)
                pos_info = ""
                if has_pos:
                    entry_price = position.get('entry_price', 0)
                    pnl = position.get('pnl', 0)
                    pos_info = f" | Position: {entry_price:,.0f} KRW | P&L: {pnl:+,.0f}"

                self.logger.logger.info(
                    f"  [{coin}] {regime.upper()}{regime_suffix} | Score: {score}/4 | "
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

    # ========================================
    # Daily Summary Methods
    # ========================================

    def _check_and_send_daily_summary(self):
        """
        Check if it's time to send daily summary (23:50) and send if needed.

        This method checks:
        1. Current time is between 23:45 and 23:59
        2. Summary hasn't been sent for today yet
        """
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        today_date = now.strftime('%Y-%m-%d')

        # Check if it's between 23:45 and 23:59 (to catch 23:50 within 15-min cycle)
        if current_hour == 23 and 45 <= current_minute <= 59:
            # Check if we already sent summary today
            if self._daily_summary_sent_date != today_date:
                self.logger.logger.info(f"Sending daily summary for {today_date}...")
                success = self._send_daily_summary()
                if success:
                    self._daily_summary_sent_date = today_date
                    self.logger.logger.info("Daily summary sent successfully")
                else:
                    self.logger.logger.warning("Failed to send daily summary")

    def _send_daily_summary(self) -> bool:
        """
        Generate and send daily trading summary via Telegram.

        Returns:
            bool: True if sent successfully, False otherwise
        """
        try:
            today_date = datetime.now().strftime('%Y-%m-%d')

            # Get today's trading summary (days=1 means today only)
            summary = self.transaction_history.get_summary(days=1)

            # Prepare summary data for Telegram
            summary_data = {
                'date': today_date,
                'buy_count': summary.get('buy_count', 0),
                'sell_count': summary.get('sell_count', 0),
                'total_volume': summary.get('total_volume', 0),
                'total_fees': summary.get('total_fees', 0),
                'net_pnl': summary.get('net_pnl', 0),
                'success_count': summary.get('successful_transactions', 0),
                'fail_count': summary.get('fail_count', 0)
            }

            # Log summary locally
            self.logger.logger.info(f"\n{'='*60}")
            self.logger.logger.info(f"Daily Summary - {today_date}")
            self.logger.logger.info(f"{'='*60}")
            self.logger.logger.info(f"  Buy orders: {summary_data['buy_count']}")
            self.logger.logger.info(f"  Sell orders: {summary_data['sell_count']}")
            self.logger.logger.info(f"  Total volume: {summary_data['total_volume']:,.0f} KRW")
            self.logger.logger.info(f"  Total fees: {summary_data['total_fees']:,.0f} KRW")
            self.logger.logger.info(f"  Net P&L: {summary_data['net_pnl']:+,.0f} KRW")
            self.logger.logger.info(f"  Success: {summary_data['success_count']}, Failed: {summary_data['fail_count']}")
            self.logger.logger.info(f"{'='*60}")

            # Send via Telegram
            return self.telegram.send_daily_summary(summary_data)

        except Exception as e:
            self.logger.log_error("Error generating daily summary", e)
            import traceback
            self.logger.logger.error(traceback.format_exc())
            return False

    def send_daily_summary_now(self) -> bool:
        """
        Manually trigger sending daily summary (for testing or manual invocation).

        Returns:
            bool: True if sent successfully, False otherwise
        """
        self.logger.logger.info("Manually triggered daily summary...")
        return self._send_daily_summary()

    # ========================================
    # Dynamic Factor Update Methods
    # ========================================

    def _check_scheduled_factor_updates(self):
        """
        Check and run scheduled factor updates.

        Update Schedule:
        - Daily (00:00-00:15): Update regime-based factors (EMA diff, volatility classification)
        - Weekly (Sunday 00:00-00:15): Update entry weights based on performance
        """
        now = datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        today_date = now.strftime('%Y-%m-%d')
        current_week = now.strftime('%Y-W%W')  # e.g., '2025-W51'

        # Check for daily update window (00:00 ~ 00:15)
        if current_hour == 0 and 0 <= current_minute <= 15:
            if self._last_daily_factor_update != today_date:
                self.logger.logger.info(f"Running daily factor update for {today_date}...")
                success = self._run_daily_factor_update()
                if success:
                    self._last_daily_factor_update = today_date
                    self.logger.logger.info("Daily factor update completed")

                # Check for weekly update (Sunday = weekday 6)
                if now.weekday() == 6:  # Sunday
                    weekly_update_day = self.config.get('DYNAMIC_FACTOR_CONFIG', {}).get('weekly_update_day', 6)
                    if now.weekday() == weekly_update_day:
                        if self._last_weekly_factor_update != current_week:
                            self.logger.logger.info(f"Running weekly factor update for {current_week}...")
                            success = self._run_weekly_factor_update()
                            if success:
                                self._last_weekly_factor_update = current_week
                                self.logger.logger.info("Weekly factor update completed")

    def _run_daily_factor_update(self) -> bool:
        """
        Run daily factor update.

        Updates:
        - Regime-based parameters (based on latest daily candle)
        - Volatility level classification
        - BB parameters (if needed)

        Returns:
            bool: True if successful
        """
        try:
            self.logger.logger.info("\n" + "=" * 60)
            self.logger.logger.info("Daily Factor Update")
            self.logger.logger.info("=" * 60)

            # Get latest analysis results for regime information
            # We use the first coin as reference for daily regime
            if self.coins:
                reference_coin = self.coins[0]
                monitor = self.portfolio_manager.get_monitor(reference_coin)
                if monitor:
                    analysis = monitor.analyze()
                    regime = analysis.get('market_regime', 'unknown')
                    regime_metadata = analysis.get('regime_metadata', {})
                    ema_diff_pct = regime_metadata.get('ema_diff_pct', 0.0)

                    # Update daily factors in factor manager
                    new_factors = self.factor_manager.update_daily_factors(regime, ema_diff_pct)

                    self.logger.logger.info(f"  Regime: {regime}")
                    self.logger.logger.info(f"  EMA Diff: {ema_diff_pct:.2f}%")
                    self.logger.logger.info(f"  Updated factors: {list(new_factors.keys())}")

                    # Send notification
                    self._send_factor_update_notification('daily', new_factors)

                    return True

            self.logger.logger.warning("No coins available for daily factor update")
            return False

        except Exception as e:
            self.logger.log_error("Error in daily factor update", e)
            import traceback
            self.logger.logger.error(traceback.format_exc())
            return False

    def _run_weekly_factor_update(self) -> bool:
        """
        Run weekly factor update based on trading performance.

        Updates:
        - Entry condition weights (BB, RSI, Stoch)
        - RSI/Stoch thresholds based on win rates
        - Minimum entry score

        Returns:
            bool: True if successful
        """
        try:
            self.logger.logger.info("\n" + "=" * 60)
            self.logger.logger.info("Weekly Factor Update (Performance-Based)")
            self.logger.logger.info("=" * 60)

            # Get recent performance from tracker
            performance = self.performance_tracker.get_recent_performance(days=7)

            total_trades = performance.get('total_trades', 0)
            min_trades = self.config.get('DYNAMIC_FACTOR_CONFIG', {}).get('min_trades_for_weekly_update', 5)

            if total_trades < min_trades:
                self.logger.logger.info(
                    f"  Skipping weekly update: {total_trades} trades < {min_trades} required"
                )
                return True  # Not an error, just skip

            # Extract performance metrics
            win_rate = performance.get('win_rate', 0.5)
            profit_factor = performance.get('profit_factor', 1.0)

            # Get trade records for detailed analysis
            trades = performance.get('trades', [])

            self.logger.logger.info(f"  7-Day Performance:")
            self.logger.logger.info(f"    Total Trades: {total_trades}")
            self.logger.logger.info(f"    Win Rate: {win_rate:.1%}")
            self.logger.logger.info(f"    Profit Factor: {profit_factor:.2f}")

            # Update weekly factors
            new_factors = self.factor_manager.update_weekly_factors(
                win_rate=win_rate,
                profit_factor=profit_factor,
                trades=trades
            )

            # Log updated weights
            entry_weights = new_factors.get('entry_weights', {})
            self.logger.logger.info(f"  Updated Entry Weights:")
            for condition, weight in entry_weights.items():
                self.logger.logger.info(f"    {condition}: {weight:.2f}")

            # Send notification
            self._send_factor_update_notification('weekly', new_factors)

            return True

        except Exception as e:
            self.logger.log_error("Error in weekly factor update", e)
            import traceback
            self.logger.logger.error(traceback.format_exc())
            return False

    def _send_factor_update_notification(self, update_type: str, factors: Dict[str, Any]):
        """
        Send Telegram notification for factor updates.

        Args:
            update_type: 'daily' or 'weekly'
            factors: Updated factors dictionary
        """
        try:
            if update_type == 'daily':
                message = (
                    f"📊 Daily Factor Update\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Chandelier Mult: {factors.get('chandelier_multiplier_modifier', 1.0):.2f}x\n"
                    f"Position Size: {factors.get('position_size_modifier', 1.0):.0%}\n"
                    f"RSI Threshold: {factors.get('rsi_oversold_threshold', 30):.0f}\n"
                    f"Volatility: {factors.get('volatility_level', 'unknown')}"
                )
            else:
                entry_weights = factors.get('entry_weights', {})
                message = (
                    f"📈 Weekly Factor Update\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Entry Weights:\n"
                    f"  BB Touch: {entry_weights.get('bb_touch', 1.0):.2f}\n"
                    f"  RSI: {entry_weights.get('rsi_oversold', 1.0):.2f}\n"
                    f"  Stoch: {entry_weights.get('stoch_cross', 2.0):.2f}\n"
                    f"Min Score: {factors.get('min_entry_score', 2)}"
                )

            self.telegram.send_message(message)

        except Exception as e:
            self.logger.logger.warning(f"Failed to send factor update notification: {e}")

    def _check_and_send_regime_change_alert(self, analysis_results: Dict[str, Any]):
        """
        Check if market regime has changed and send Telegram alert.

        Args:
            analysis_results: Analysis results from portfolio manager
        """
        try:
            # Get regime from first coin's analysis (reference coin)
            if not self.coins:
                return

            reference_coin = self.coins[0]
            if reference_coin not in analysis_results:
                return

            analysis = analysis_results[reference_coin]
            current_regime = analysis.get('market_regime', 'unknown')
            timeout_occurred = analysis.get('timeout_occurred', False)
            regime_metadata = analysis.get('regime_metadata', {})
            ema_diff_pct = regime_metadata.get('ema_diff_pct', 0.0)

            # Skip if timeout occurred (using last valid regime, but actual analysis failed)
            if timeout_occurred:
                return

            # Skip if regime is unknown, timeout, or error (these are not real market regimes)
            if current_regime in ('unknown', 'timeout', 'error'):
                return

            # Check for regime change
            if self._previous_regime is not None and self._previous_regime != current_regime:
                self.logger.logger.info(
                    f"Regime change detected: {self._previous_regime} -> {current_regime}"
                )

                # Apply debounce: only send alert if cooldown period has passed
                now = datetime.now()
                should_send_alert = True

                if self._last_regime_alert_time is not None:
                    elapsed = (now - self._last_regime_alert_time).total_seconds()
                    if elapsed < self._regime_alert_cooldown:
                        should_send_alert = False
                        self.logger.logger.info(
                            f"Regime alert suppressed (debounce): {int(self._regime_alert_cooldown - elapsed)}s remaining"
                        )

                if should_send_alert:
                    # Send telegram alert
                    self.telegram.send_regime_change_alert(
                        old_regime=self._previous_regime,
                        new_regime=current_regime,
                        coin=reference_coin,
                        ema_diff_pct=ema_diff_pct
                    )
                    self._last_regime_alert_time = now

            # Update previous regime
            self._previous_regime = current_regime

        except Exception as e:
            self.logger.logger.warning(f"Error checking regime change: {e}")

    def _get_adaptive_interval(self) -> int:
        """
        Get adaptive analysis interval based on market conditions.

        In bear regimes with high volatility, reduce interval to half
        for faster stop-loss/profit-taking response.

        Returns:
            Effective check interval in seconds
        """
        try:
            factors = self.factor_manager.get_current_factors()
            volatility = factors.get('volatility_level', 'NORMAL')
            regime = factors.get('market_regime', 'unknown')

            bear_regimes = ['bearish', 'strong_bearish']

            # Bear + HIGH/EXTREME volatility → half interval
            if regime in bear_regimes and volatility in ('HIGH', 'EXTREME'):
                adaptive = max(150, self.check_interval // 2)  # min 2.5 minutes
                return adaptive

            # Has open positions in bear market → slightly shorter
            has_positions = len(self.portfolio_manager.executor.positions) > 0
            if has_positions and regime in bear_regimes:
                adaptive = max(180, int(self.check_interval * 0.7))
                return adaptive

        except Exception:
            pass

        return self.check_interval

    def get_current_factors(self) -> Dict[str, Any]:
        """
        Get current dynamic factors (for GUI display).

        Returns:
            Dictionary with all current dynamic factors
        """
        return self.factor_manager.get_current_factors()

    def force_factor_update(self, update_type: str = 'all') -> bool:
        """
        Manually force factor update (for testing or manual adjustment).

        Args:
            update_type: 'daily', 'weekly', or 'all'

        Returns:
            bool: True if successful
        """
        self.logger.logger.info(f"Manually forcing {update_type} factor update...")

        success = True
        if update_type in ['daily', 'all']:
            success = self._run_daily_factor_update() and success
        if update_type in ['weekly', 'all']:
            success = self._run_weekly_factor_update() and success

        return success
