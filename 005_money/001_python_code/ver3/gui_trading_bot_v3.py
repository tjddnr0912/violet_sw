"""
GUI Trading Bot V3 - Adapter for Portfolio Multi-Coin Strategy

This module adapts TradingBotV3 for GUI usage by:
- Running bot in background thread
- Sending updates to GUI via queue
- Providing thread-safe access to portfolio status
- Handling GUI-specific logging
"""

import time
import queue
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime

from ver3.trading_bot_v3 import TradingBotV3
from ver3.config_v3 import get_version_config
from lib.core.logger import TradingLogger


class GUITradingBotV3:
    """
    GUI adapter for TradingBotV3.

    This class wraps TradingBotV3 to:
    - Run in background thread without blocking GUI
    - Send status updates to GUI via queue
    - Provide thread-safe portfolio summary access
    - Handle GUI lifecycle (start/stop)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        gui_app,
        log_queue: queue.Queue
    ):
        """
        Initialize GUI trading bot adapter.

        Args:
            config: Ver3 configuration dictionary
            gui_app: Reference to GUI application instance
            log_queue: Queue for sending log messages to GUI
        """
        self.config = config
        self.gui_app = gui_app
        self.log_queue = log_queue

        # Create underlying bot
        self.bot = TradingBotV3(config)

        # Bot state
        self.running = False
        self.thread = None

        # Thread-safe access lock
        self.lock = threading.Lock()

        self._send_log("INFO", "GUI Trading Bot V3 initialized")

    def run(self):
        """
        Run the trading bot main loop (designed for background thread).

        This method should be called from a background thread, not the main GUI thread.
        """
        self.running = True
        self._send_log("INFO", "Bot main loop started")

        try:
            while self.running:
                cycle_start = time.time()

                try:
                    # Increment cycle count
                    self.bot.cycle_count += 1

                    self._send_log(
                        "INFO",
                        f"=== Analysis Cycle #{self.bot.cycle_count} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==="
                    )

                    # 1. Analyze all coins in parallel
                    self._send_log("INFO", "Analyzing all coins...")
                    results = self.bot.portfolio_manager.analyze_all()

                    # Log per-coin results
                    for coin, result in results.items():
                        action = result.get('action', 'HOLD')
                        score = result.get('entry_score', 0)
                        regime = result.get('market_regime', '?')
                        self._send_log(
                            "INFO",
                            f"  [{coin}] {regime.upper()} | Score: {score}/4 | Action: {action}"
                        )

                    # 2. Make portfolio-level decisions
                    self._send_log("INFO", "Making portfolio decisions...")
                    decisions = self.bot.portfolio_manager.make_portfolio_decision(results)

                    if decisions:
                        for coin, action, entry_number in decisions:
                            if entry_number > 1:
                                self._send_log("INFO", f"Decision: {coin} -> {action} (Pyramid #{entry_number})")
                            else:
                                self._send_log("INFO", f"Decision: {coin} -> {action}")
                    else:
                        self._send_log("INFO", "No trading actions required (HOLD)")

                    # 3. Execute trading decisions
                    if decisions:
                        self._send_log("INFO", "Executing decisions...")
                        self.bot.portfolio_manager.execute_decisions(decisions)

                    # 4. Log portfolio summary
                    summary = self.bot.portfolio_manager.get_portfolio_summary()
                    self._log_portfolio_summary(summary)

                    # Update last analysis time
                    self.bot.last_analysis_time = datetime.now()

                except Exception as e:
                    self._send_log("ERROR", f"Error in analysis cycle: {str(e)}")
                    import traceback
                    self._send_log("ERROR", traceback.format_exc())

                # Sleep until next cycle
                cycle_elapsed = time.time() - cycle_start
                sleep_time = max(0, self.bot.check_interval - cycle_elapsed)

                if sleep_time > 0:
                    self._send_log(
                        "INFO",
                        f"Cycle completed in {cycle_elapsed:.2f}s. Sleeping {sleep_time:.0f}s until next cycle..."
                    )
                    time.sleep(sleep_time)
                else:
                    self._send_log(
                        "WARNING",
                        f"Cycle took {cycle_elapsed:.2f}s (exceeds interval of {self.bot.check_interval}s)"
                    )

        except Exception as e:
            self._send_log("ERROR", f"Fatal error in main loop: {str(e)}")
            import traceback
            self._send_log("ERROR", traceback.format_exc())
            self.running = False

        self._send_log("INFO", "Bot main loop stopped")

    def stop(self):
        """Stop the trading bot"""
        self._send_log("INFO", "Stopping bot...")
        self.running = False
        if self.bot:
            self.bot.stop()

    def get_portfolio_summary(self) -> Optional[Dict[str, Any]]:
        """
        Get current portfolio summary (thread-safe).

        Returns:
            Portfolio summary dictionary or None if bot not initialized
        """
        with self.lock:
            if self.bot and self.bot.portfolio_manager:
                summary = self.bot.portfolio_manager.get_portfolio_summary()
                # Add bot-level stats
                summary['cycle_count'] = self.bot.cycle_count
                summary['last_update'] = (
                    self.bot.last_analysis_time.isoformat()
                    if self.bot.last_analysis_time
                    else None
                )
                return summary
            return None

    def get_bot_status(self) -> Dict[str, Any]:
        """
        Get bot status information (thread-safe).

        Returns:
            Dictionary with bot status:
            {
                'running': bool,
                'cycle_count': int,
                'coins': List[str],
                'check_interval': int,
                'last_analysis': str (ISO format),
            }
        """
        with self.lock:
            return {
                'running': self.running,
                'cycle_count': self.bot.cycle_count if self.bot else 0,
                'coins': self.bot.coins if self.bot else [],
                'check_interval': self.bot.check_interval if self.bot else 900,
                'last_analysis': (
                    self.bot.last_analysis_time.isoformat()
                    if self.bot and self.bot.last_analysis_time
                    else None
                ),
            }

    def _send_log(self, level: str, message: str):
        """
        Send log message to GUI via queue.

        Args:
            level: Log level (INFO, WARNING, ERROR)
            message: Log message
        """
        try:
            self.log_queue.put_nowait((level, message))
        except queue.Full:
            # Queue full, skip this message
            pass

        # Also log to bot's logger
        if self.bot and self.bot.logger:
            if level == "ERROR":
                self.bot.logger.logger.error(message)
            elif level == "WARNING":
                self.bot.logger.logger.warning(message)
            else:
                self.bot.logger.logger.info(message)

    def _log_portfolio_summary(self, summary: Dict[str, Any]):
        """
        Log portfolio summary to GUI.

        Args:
            summary: Portfolio summary from get_portfolio_summary()
        """
        total_pos = summary.get('total_positions', 0)
        max_pos = summary.get('max_positions', 2)
        total_pnl = summary.get('total_pnl_krw', 0)

        self._send_log("INFO", "-" * 60)
        self._send_log("INFO", "Portfolio Summary")
        self._send_log("INFO", f"  Positions: {total_pos}/{max_pos}")
        self._send_log("INFO", f"  Total P&L: {total_pnl:+,.0f} KRW")

        # Per-coin summary
        coins_data = summary.get('coins', {})
        if coins_data:
            self._send_log("INFO", "Per-Coin Status:")
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

                self._send_log(
                    "INFO",
                    f"  [{coin}] {regime.upper():8s} | Score: {score}/4 | Action: {action:4s}{pos_info}"
                )

        self._send_log("INFO", "-" * 60)
