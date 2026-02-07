"""
Telegram Bot Handler - Interactive command handler for trading bot control

This module provides bi-directional Telegram bot functionality, allowing users
to control and monitor the trading bot via Telegram commands.

Environment Variables Required:
    TELEGRAM_BOT_TOKEN: Bot token from BotFather
    TELEGRAM_CHAT_ID: Authorized chat ID (for security)
    TELEGRAM_NOTIFICATIONS_ENABLED: Enable/disable (default: False)

Supported Commands:
    /start - Welcome message and bot introduction
    /help - List available commands
    /status - Current bot status, positions, and cycle info
    /positions - Detailed position information
    /factors - Dynamic factor status
    /performance - 7-day performance summary
    /close <COIN> - Close position for specific coin (with confirmation)
    /stop - Stop the trading bot (with confirmation)
    /reboot - Restart the trading bot (with confirmation)
    /summary - Get today's trading summary

Usage:
    from lib.core.telegram_bot_handler import TelegramBotHandler

    handler = TelegramBotHandler(trading_bot)
    handler.start()  # Start listening for commands in background

    # Later...
    handler.stop()   # Stop the handler

Security:
    - Only responds to messages from authorized chat_id
    - Stop command requires confirmation
    - All commands are logged
"""

import os
import asyncio
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable
from functools import wraps

# Suppress httpx INFO logs (polling messages)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# Check if python-telegram-bot is available
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        CallbackQueryHandler,
        ContextTypes,
    )
    TELEGRAM_BOT_AVAILABLE = True
except ImportError:
    TELEGRAM_BOT_AVAILABLE = False
    print("Warning: python-telegram-bot not installed. Install with: pip install python-telegram-bot")


class TelegramBotHandler:
    """
    Interactive Telegram bot handler for trading bot control.

    This class runs a Telegram bot that listens for commands and
    provides real-time information about the trading bot status.

    Attributes:
        trading_bot: Reference to TradingBotV3 instance
        bot_token (str): Telegram bot token
        chat_id (str): Authorized chat ID
        enabled (bool): Whether the handler is enabled
        running (bool): Whether the handler is currently running
    """

    def __init__(self, trading_bot=None):
        """
        Initialize the Telegram bot handler.

        Args:
            trading_bot: Reference to TradingBotV3 instance (can be set later)
        """
        self.trading_bot = trading_bot
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "False").lower() == "true"

        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._application = None

        # Pending stop confirmation
        self._stop_pending = False
        self._stop_confirm_time: Optional[datetime] = None

        # Pending reboot confirmation
        self._reboot_pending = False
        self._reboot_confirm_time: Optional[datetime] = None

        # Pending close confirmation (per-coin)
        self._close_pending: Dict[str, datetime] = {}

        # Start time for uptime calculation
        self._start_time: Optional[datetime] = None

        # Validate configuration
        if not TELEGRAM_BOT_AVAILABLE:
            print("TelegramBotHandler: python-telegram-bot library not available")
            self.enabled = False
        elif self.enabled and (not self.bot_token or not self.chat_id):
            print("TelegramBotHandler: Credentials missing, disabling handler")
            self.enabled = False

    def set_trading_bot(self, trading_bot):
        """
        Set the trading bot reference.

        Args:
            trading_bot: Reference to TradingBotV3 instance
        """
        self.trading_bot = trading_bot

    def _authorized(self, func):
        """
        Decorator to check if user is authorized.

        Only allows commands from the configured chat_id.
        """
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
            user_chat_id = str(update.effective_chat.id)
            if user_chat_id != self.chat_id:
                await update.message.reply_text(
                    "Unauthorized. This bot only responds to its owner."
                )
                print(f"Unauthorized access attempt from chat_id: {user_chat_id}")
                return
            return await func(update, context)
        return wrapper

    # ========================================
    # Command Handlers
    # ========================================

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command - Welcome message."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        message = """
*Trading Bot Controller*

Welcome to the Ver3 Trading Bot Telegram interface.

Use /help to see available commands.

*Quick Status:*
"""
        if self.trading_bot:
            status = "Running" if self.trading_bot.running else "Stopped"
            coins = ', '.join(self.trading_bot.coins)
            message += f"Status: {status}\nCoins: {coins}"
        else:
            message += "Bot not connected"

        await update.message.reply_text(message, parse_mode='Markdown')

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command - List available commands."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        message = """
*Available Commands*

/status - Bot status overview
/positions - Detailed position info
/summary - Today's trading summary
/factors - Dynamic factor status
/performance - 7-day performance
/bear\\_mode - Bear Quick-Trade mode status

*Trading Commands*
/close <COIN> - Close position (e.g. /close BTC)
/stop - Stop the trading bot
/reboot - Restart the trading bot

*Info Commands*
/start - Welcome message
/help - This help message
"""
        await update.message.reply_text(message, parse_mode='Markdown')

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command - Bot status overview."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            # Get bot status
            is_running = self.trading_bot.running
            status_emoji = "Running" if is_running else "Stopped"
            status_icon = "🟢" if is_running else "🔴"

            # Uptime calculation
            uptime_str = "N/A"
            if self._start_time and is_running:
                uptime = datetime.now() - self._start_time
                hours, remainder = divmod(int(uptime.total_seconds()), 3600)
                minutes, seconds = divmod(remainder, 60)
                uptime_str = f"{hours}h {minutes}m {seconds}s"

            # Cycle info
            cycle_count = self.trading_bot.cycle_count
            last_analysis = self.trading_bot.last_analysis_time
            last_analysis_str = last_analysis.strftime("%H:%M:%S") if last_analysis else "N/A"

            # Time since last analysis
            if last_analysis:
                time_since = datetime.now() - last_analysis
                minutes_ago = int(time_since.total_seconds() / 60)
                last_analysis_str += f" ({minutes_ago}m ago)"

            # Portfolio summary
            summary = self.trading_bot.get_portfolio_summary()
            total_positions = summary.get('total_positions', 0)
            max_positions = summary.get('max_positions', 2)
            total_pnl = summary.get('total_pnl_krw', 0)

            # Build position summary
            position_lines = []
            coins_data = summary.get('coins', {})
            for coin, data in coins_data.items():
                position = data.get('position', {})
                has_pos = position.get('has_position', False)
                if has_pos:
                    pnl = position.get('pnl', 0)
                    pnl_pct = position.get('pnl_pct', 0)
                    pnl_emoji = "+" if pnl >= 0 else ""
                    position_lines.append(f"  {coin}: {pnl_emoji}{pnl:,.0f} KRW ({pnl_pct:+.1f}%)")

            positions_str = "\n".join(position_lines) if position_lines else "  None"

            # Monitored coins
            coins = ', '.join(self.trading_bot.coins)

            # Check interval
            interval_min = self.trading_bot.check_interval // 60

            message = f"""
{status_icon} *Bot Status: {status_emoji}*

*Runtime*
Uptime: `{uptime_str}`
Cycles: `{cycle_count}`
Last Analysis: `{last_analysis_str}`
Interval: `{interval_min}min`

*Portfolio*
Positions: `{total_positions}/{max_positions}`
Total P&L: `{total_pnl:+,.0f} KRW`

*Open Positions*
{positions_str}

*Monitoring*
Coins: `{coins}`
"""

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"Error getting status: {e}")

    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /positions command - Detailed position info."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            summary = self.trading_bot.get_portfolio_summary()
            coins_data = summary.get('coins', {})

            message_lines = ["*Position Details*\n"]

            has_positions = False
            for coin, data in coins_data.items():
                position = data.get('position', {})
                analysis = data.get('analysis', {})

                has_pos = position.get('has_position', False)
                regime = analysis.get('market_regime', 'unknown')
                timeout_flag = analysis.get('timeout_occurred', False)
                # Timeout 발생 시 표시 형식 변경
                regime_display = f"{regime.upper()} (⏱)" if timeout_flag else regime.upper()
                score = analysis.get('entry_score', 0)
                action = analysis.get('action', 'HOLD')

                if has_pos:
                    has_positions = True
                    entry_price = position.get('entry_price', 0)
                    current_price = position.get('current_price', 0)
                    size = position.get('size', 0)
                    pnl = position.get('pnl', 0)
                    pnl_pct = position.get('pnl_pct', 0)
                    entry_time = position.get('entry_time', 'N/A')

                    pnl_emoji = "📈" if pnl >= 0 else "📉"

                    message_lines.append(f"""
{pnl_emoji} *{coin}*
  Entry: `{entry_price:,.0f} KRW`
  Current: `{current_price:,.0f} KRW`
  Size: `{size:.8f}`
  P&L: `{pnl:+,.0f} KRW ({pnl_pct:+.1f}%)`
  Regime: `{regime_display}`
  Score: `{score}/4`
  Since: `{entry_time}`
""")
                else:
                    # Build extreme oversold info for bearish regimes
                    extreme_info = ""
                    bearish_conditions = analysis.get('bearish_conditions', {})
                    if bearish_conditions and regime.lower() in ['bearish', 'strong_bearish']:
                        extreme_count = bearish_conditions.get('extreme_condition_count', 0)
                        is_extreme = bearish_conditions.get('is_extreme_oversold', False)
                        extreme_emoji = "✅" if is_extreme else "❌"

                        rsi_val = bearish_conditions.get('current_rsi', 0)
                        stoch_val = bearish_conditions.get('current_stoch_k', 0)
                        rsi_ok = "✓" if bearish_conditions.get('rsi_extreme', False) else "✗"
                        stoch_ok = "✓" if bearish_conditions.get('stoch_extreme', False) else "✗"
                        bb_ok = "✓" if bearish_conditions.get('price_at_bb_lower', False) else "✗"

                        extreme_info = f"\n  Extreme: `{extreme_count}/3` {extreme_emoji} (RSI:{rsi_val:.0f}{rsi_ok} Stoch:{stoch_val:.0f}{stoch_ok} BB:{bb_ok})"

                    message_lines.append(f"""
*{coin}* (No Position)
  Regime: `{regime_display}`
  Score: `{score}/4`
  Signal: `{action}`{extreme_info}
""")

            if not has_positions:
                message_lines.append("\n_No open positions_")

            await update.message.reply_text(''.join(message_lines), parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"Error getting positions: {e}")

    async def cmd_summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /summary command - Today's trading summary."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            # Get today's summary from transaction history
            summary = self.trading_bot.transaction_history.get_summary(days=1)
            today_date = datetime.now().strftime('%Y-%m-%d')

            buy_count = summary.get('buy_count', 0)
            sell_count = summary.get('sell_count', 0)
            total_volume = summary.get('total_volume', 0)
            total_fees = summary.get('total_fees', 0)
            net_pnl = summary.get('net_pnl', 0)
            success_count = summary.get('successful_transactions', 0)
            fail_count = summary.get('fail_count', 0)

            pnl_emoji = "📈" if net_pnl >= 0 else "📉"

            message = f"""
*Daily Summary - {today_date}*

*Trades*
  Buys: `{buy_count}`
  Sells: `{sell_count}`
  Success: `{success_count}`
  Failed: `{fail_count}`

*Volume*
  Total: `{total_volume:,.0f} KRW`
  Fees: `{total_fees:,.0f} KRW`

{pnl_emoji} *Net P&L: `{net_pnl:+,.0f} KRW`*
"""

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"Error getting summary: {e}")

    async def cmd_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stop command - Stop trading bot with confirmation."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        if not self.trading_bot.running:
            await update.message.reply_text("Bot is already stopped.")
            return

        try:
            # Get current position info
            summary = self.trading_bot.get_portfolio_summary()
            total_positions = summary.get('total_positions', 0)
            total_pnl = summary.get('total_pnl_krw', 0)

            # Build position warning
            position_warning = ""
            if total_positions > 0:
                position_warning = f"\nOpen positions: *{total_positions}*"
                coins_data = summary.get('coins', {})
                for coin, data in coins_data.items():
                    position = data.get('position', {})
                    if position.get('has_position', False):
                        pnl = position.get('pnl', 0)
                        position_warning += f"\n  {coin}: {pnl:+,.0f} KRW"

            # Create confirmation keyboard
            keyboard = [
                [
                    InlineKeyboardButton("Stop Bot", callback_data="stop_confirm"),
                    InlineKeyboardButton("Cancel", callback_data="stop_cancel"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = f"""
*Stop Trading Bot?*
{position_warning}

Are you sure you want to stop the bot?

_Positions will NOT be closed automatically._
"""

            self._stop_pending = True
            self._stop_confirm_time = datetime.now()

            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def cmd_reboot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /reboot command - Restart bot via watchdog."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            # Get current position info
            summary = self.trading_bot.get_portfolio_summary()
            total_positions = summary.get('total_positions', 0)

            # Build position info
            position_info = ""
            if total_positions > 0:
                position_info = f"\nOpen positions: *{total_positions}* (will be preserved)"
            else:
                position_info = "\nNo open positions."

            # Create confirmation keyboard
            keyboard = [
                [
                    InlineKeyboardButton("Reboot", callback_data="reboot_confirm"),
                    InlineKeyboardButton("Cancel", callback_data="reboot_cancel"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = f"""
*Reboot Trading Bot?*
{position_info}

This will restart the bot process.
Positions will be preserved across restart.

_Bot will be back online in ~15 seconds._
"""

            self._reboot_pending = True
            self._reboot_confirm_time = datetime.now()

            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def cmd_factors(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /factors command - Dynamic factor status."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            # Get current dynamic factors
            factors = self.trading_bot.get_current_factors()

            # Format volatility info
            volatility = factors.get('volatility_level', 'UNKNOWN')
            atr_pct = factors.get('atr_percent', 0.0)
            regime = factors.get('regime', 'unknown')

            # Risk parameters
            chandelier_mod = factors.get('chandelier_multiplier_modifier', 1.0)
            pos_size_mod = factors.get('position_size_modifier', 1.0)
            rsi_threshold = factors.get('rsi_oversold_threshold', 30)
            stoch_threshold = factors.get('stoch_oversold_threshold', 20)
            min_score = factors.get('min_entry_score', 2)

            # Entry weights
            entry_weights = factors.get('entry_weights', {})
            bb_weight = entry_weights.get('bb_touch', 1.0)
            rsi_weight = entry_weights.get('rsi_oversold', 1.0)
            stoch_weight = entry_weights.get('stoch_cross', 2.0)

            # Volatility emoji
            vol_emoji = {
                'LOW': '🟢', 'NORMAL': '🟡', 'HIGH': '🟠', 'EXTREME': '🔴'
            }.get(volatility.upper(), '⚪')

            # Regime emoji
            regime_emoji = {
                'strong_bullish': '🚀', 'bullish': '📈', 'neutral': '➖',
                'bearish': '📉', 'strong_bearish': '💥', 'ranging': '↔️'
            }.get(regime.lower(), '❓')

            message = f"""
🎚️ *Dynamic Factor Status*

*Market State*
{regime_emoji} Regime: `{regime.upper()}`
{vol_emoji} Volatility: `{volatility}` (ATR {atr_pct:.2f}%)

*Risk Parameters*
🛑 Chandelier Mult: `{chandelier_mod:.2f}x`
📏 Position Size: `{pos_size_mod:.0%}`
📉 RSI Oversold: `{rsi_threshold}`
📊 Stoch Oversold: `{stoch_threshold}`

*Entry Weights*
BB Touch: `{bb_weight:.2f}`
RSI Oversold: `{rsi_weight:.2f}`
Stoch Cross: `{stoch_weight:.2f}`
Min Score: `{min_score}`
"""

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"Error getting factors: {e}")

    async def cmd_bear_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /bear_mode command - Bear Quick-Trade mode status."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            status = self.trading_bot.portfolio_manager.get_bear_mode_status()
            enabled = status.get('enabled', False)
            config = status.get('config', {})
            cooldowns = status.get('cooldowns_hours', {})
            daily_pnl = status.get('daily_realized_pnl', 0)
            daily_date = status.get('daily_pnl_date', '')

            status_emoji = "🟢 ON" if enabled else "🔴 OFF"

            message = f"🐻 *Bear Quick-Trade Mode*\n\n"
            message += f"Status: {status_emoji}\n\n"

            if enabled:
                message += f"*Settings*\n"
                message += f"익절: `+{config.get('profit_target_pct', 0.8)}%`\n"
                message += f"손절 (bearish): `-{config.get('hard_stop_pct_bearish', 1.5)}%`\n"
                message += f"손절 (strong bear): `-{config.get('hard_stop_pct_strong_bearish', 1.0)}%`\n"
                message += f"보유한도 (bearish): `{config.get('max_hold_hours_bearish', 4)}h`\n"
                message += f"보유한도 (strong bear): `{config.get('max_hold_hours_strong_bearish', 2)}h`\n"
                message += f"포지션 (bearish): `{config.get('position_mult_bearish', 0.5)*100:.0f}%`\n"
                message += f"포지션 (strong bear): `{config.get('position_mult_strong_bearish', 0.3)*100:.0f}%`\n"
                message += f"쿨다운 (bearish): `{config.get('cooldown_hours_bearish', 6)}h`\n"
                message += f"쿨다운 (strong bear): `{config.get('cooldown_hours_strong_bearish', 12)}h`\n\n"

                message += f"*Today ({daily_date})*\n"
                message += f"실현 P&L: `{daily_pnl:+,.0f} KRW`\n"
                total_capital = self.trading_bot.config.get('TRADING_CONFIG', {}).get('total_capital_krw', 1000000)
                daily_limit = total_capital * config.get('daily_loss_limit_pct', 2.0) / 100
                message += f"일일 한도: `-{daily_limit:,.0f} KRW`\n\n"

                if cooldowns:
                    message += f"*Cooldowns*\n"
                    for coin, hours in cooldowns.items():
                        message += f"{coin}: `{hours:.1f}h` since last exit\n"

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance command - 7-day performance summary."""
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            # Get performance tracker
            performance_tracker = self.trading_bot.performance_tracker
            performance = performance_tracker.get_recent_performance(days=7)

            total_trades = performance.get('total_trades', 0)
            win_count = performance.get('win_count', 0)
            loss_count = performance.get('loss_count', 0)
            win_rate = performance.get('win_rate', 0.0)
            total_profit = performance.get('total_profit', 0.0)
            total_loss = performance.get('total_loss', 0.0)
            profit_factor = performance.get('profit_factor', 0.0)
            net_pnl = total_profit - abs(total_loss)

            # Win rate indicator
            if win_rate >= 0.6:
                wr_indicator = '🟢'
            elif win_rate >= 0.4:
                wr_indicator = '🟡'
            else:
                wr_indicator = '🔴'

            pnl_emoji = '📈' if net_pnl >= 0 else '📉'

            message = f"""
📊 *7-Day Performance*

*Trade Statistics*
Total: `{total_trades}`
Wins: `{win_count}` / Losses: `{loss_count}`
{wr_indicator} Win Rate: `{win_rate:.1%}`

*P&L Analysis*
{pnl_emoji} Net P&L: `{net_pnl:+,.0f} KRW`
Gross Profit: `{total_profit:+,.0f} KRW`
Gross Loss: `{total_loss:,.0f} KRW`
Profit Factor: `{profit_factor:.2f}`
"""

            # Add per-condition breakdown if available
            per_condition = performance.get('per_condition', {})
            if per_condition:
                message += "\n*Per-Condition*\n"
                for condition, stats in per_condition.items():
                    cond_trades = stats.get('trades', 0)
                    cond_wr = stats.get('win_rate', 0.0)
                    if cond_trades > 0:
                        message += f"  {condition}: `{cond_wr:.0%}` ({cond_trades})\n"

            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"Error getting performance: {e}")

    async def cmd_resume(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /resume command - Clear observation mode and allow new entries.

        Usage: /resume
        """
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            performance_tracker = self.trading_bot.performance_tracker

            # 현재 관찰 모드 상태 확인
            obs_status = performance_tracker.get_observation_status()

            if not obs_status['is_observation_mode']:
                await update.message.reply_text(
                    "ℹ️ 관찰 모드가 활성화되어 있지 않습니다.\n"
                    "새 진입이 이미 허용된 상태입니다."
                )
                return

            # 관찰 모드 해제
            result = performance_tracker.clear_observation_mode()

            message = f"""
✅ *관찰 모드 해제됨*

{result}

*이전 상태:*
- 연속 손실: `{obs_status['consecutive_losses']}회`
- 사유: {obs_status['reason']}

⚠️ 주의: 시장 상황이 개선되지 않았다면 추가 손실 위험이 있습니다.
"""
            await update.message.reply_text(message, parse_mode='Markdown')

        except Exception as e:
            await update.message.reply_text(f"Error clearing observation mode: {e}")

    async def cmd_optimize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /optimize command - Force run weekly factor optimization.

        Usage: /optimize
        """
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        try:
            await update.message.reply_text("🔄 주간 최적화 실행 중...")

            # Run weekly factor update
            success = self.trading_bot._run_weekly_factor_update()

            if success:
                # Get updated factors
                factors = self.trading_bot.factor_manager.get_current_factors()

                message = f"""
✅ *주간 최적화 완료*

*업데이트된 Entry Weights:*
- BB Touch: `{factors.get('entry_weight_bb_touch', 1.0):.1f}`
- RSI Oversold: `{factors.get('entry_weight_rsi_oversold', 1.0):.1f}`
- Stoch Cross: `{factors.get('entry_weight_stoch_cross', 2.0):.1f}`

*Min Entry Score:* `{factors.get('min_entry_score', 2)}`
*마지막 업데이트:* `{factors.get('last_weekly_update', 'N/A')}`
"""
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(
                    "⚠️ 최적화가 스킵되었습니다.\n"
                    "최소 거래 수를 충족하지 못했을 수 있습니다."
                )

        except Exception as e:
            await update.message.reply_text(f"Error running optimization: {e}")

    async def cmd_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Handle /close command - Close position for specific coin.

        Usage: /close BTC or /close ETH
        """
        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            await update.message.reply_text("Unauthorized.")
            return

        if not self.trading_bot:
            await update.message.reply_text("Trading bot not connected.")
            return

        # Parse coin argument
        args = context.args
        if not args or len(args) < 1:
            # Show available coins with positions
            try:
                summary = self.trading_bot.get_portfolio_summary()
                coins_with_positions = []
                coins_data = summary.get('coins', {})

                for coin, data in coins_data.items():
                    position = data.get('position', {})
                    if position.get('has_position', False):
                        pnl = position.get('pnl', 0)
                        pnl_pct = position.get('pnl_pct', 0)
                        coins_with_positions.append(f"  {coin}: {pnl:+,.0f} KRW ({pnl_pct:+.1f}%)")

                if coins_with_positions:
                    positions_str = "\n".join(coins_with_positions)
                    message = f"""
*Usage:* `/close <COIN>`

*Example:* `/close BTC`

*Open Positions:*
{positions_str}
"""
                else:
                    message = "*No open positions to close.*"

                await update.message.reply_text(message, parse_mode='Markdown')
            except Exception as e:
                await update.message.reply_text(f"Error: {e}")
            return

        coin = args[0].upper()

        # Validate coin
        if coin not in self.trading_bot.coins:
            available = ', '.join(self.trading_bot.coins)
            await update.message.reply_text(
                f"Invalid coin: {coin}\n\nAvailable: {available}"
            )
            return

        try:
            # Check if position exists
            executor = self.trading_bot.portfolio_manager.executor
            if not executor.has_position(coin):
                await update.message.reply_text(f"No open position for {coin}.")
                return

            # Get position details
            position_info = executor.get_position_info(coin)
            entry_price = position_info.get('entry_price', 0)
            size = position_info.get('size', 0)
            pnl = position_info.get('unrealized_pnl', 0)
            pnl_pct = position_info.get('pnl_percent', 0)
            entry_time = position_info.get('entry_time', 'N/A')

            # Get current price
            from lib.api.bithumb_api import get_ticker
            ticker_data = get_ticker(coin)
            current_price = float(ticker_data.get('closing_price', 0)) if ticker_data else 0

            pnl_emoji = "📈" if pnl >= 0 else "📉"

            # Create confirmation keyboard
            keyboard = [
                [
                    InlineKeyboardButton("Close Position", callback_data=f"close_confirm_{coin}"),
                    InlineKeyboardButton("Cancel", callback_data="close_cancel"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            message = f"""
*Close {coin} Position?*

{pnl_emoji} *Current P&L: `{pnl:+,.0f} KRW` ({pnl_pct:+.1f}%)*

*Position Details*
  Entry: `{entry_price:,.0f} KRW`
  Current: `{current_price:,.0f} KRW`
  Size: `{size:.8f} {coin}`
  Since: `{entry_time}`

Are you sure you want to close this position?
"""

            # Set pending confirmation
            self._close_pending[coin] = datetime.now()

            await update.message.reply_text(
                message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

        except Exception as e:
            await update.message.reply_text(f"Error: {e}")

    async def callback_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline keyboards."""
        query = update.callback_query
        await query.answer()

        user_chat_id = str(update.effective_chat.id)
        if user_chat_id != self.chat_id:
            return

        if query.data == "stop_confirm":
            # Check if confirmation is still valid (within 60 seconds)
            if self._stop_pending and self._stop_confirm_time:
                elapsed = (datetime.now() - self._stop_confirm_time).total_seconds()
                if elapsed <= 60:
                    # Stop the bot
                    if self.trading_bot and self.trading_bot.running:
                        self.trading_bot.stop()
                        await query.edit_message_text(
                            "Bot stopped successfully.\n\n"
                            "_Use your terminal to restart the bot._",
                            parse_mode='Markdown'
                        )
                    else:
                        await query.edit_message_text("Bot is already stopped.")
                else:
                    await query.edit_message_text(
                        "Confirmation expired. Use /stop again if needed."
                    )
            else:
                await query.edit_message_text("No pending stop request.")

            self._stop_pending = False
            self._stop_confirm_time = None

        elif query.data == "stop_cancel":
            self._stop_pending = False
            self._stop_confirm_time = None
            await query.edit_message_text("Stop cancelled. Bot continues running.")

        # Handle reboot confirmation
        elif query.data == "reboot_confirm":
            if self._reboot_pending and self._reboot_confirm_time:
                elapsed = (datetime.now() - self._reboot_confirm_time).total_seconds()
                if elapsed <= 60:
                    await query.edit_message_text(
                        "Rebooting bot...\n\n"
                        "_Bot will restart in ~15 seconds._",
                        parse_mode='Markdown'
                    )
                    self._reboot_pending = False
                    self._reboot_confirm_time = None
                    # Use os._exit(1) to trigger watchdog restart
                    import os
                    os._exit(1)
                else:
                    await query.edit_message_text(
                        "Confirmation expired. Use /reboot again if needed."
                    )
            else:
                await query.edit_message_text("No pending reboot request.")

            self._reboot_pending = False
            self._reboot_confirm_time = None

        elif query.data == "reboot_cancel":
            self._reboot_pending = False
            self._reboot_confirm_time = None
            await query.edit_message_text("Reboot cancelled. Bot continues running.")

        # Handle close position confirmations
        elif query.data.startswith("close_confirm_"):
            coin = query.data.replace("close_confirm_", "")

            # Check if confirmation is still valid (within 60 seconds)
            if coin in self._close_pending:
                elapsed = (datetime.now() - self._close_pending[coin]).total_seconds()
                if elapsed <= 60:
                    try:
                        executor = self.trading_bot.portfolio_manager.executor
                        dry_run = self.trading_bot.config.get('dry_run', True)

                        # Get current price
                        from lib.api.bithumb_api import get_ticker
                        ticker_data = get_ticker(coin)
                        current_price = float(ticker_data.get('closing_price', 0)) if ticker_data else 0

                        if current_price <= 0:
                            await query.edit_message_text(f"Failed to get current price for {coin}.")
                            del self._close_pending[coin]
                            return

                        # Execute close position
                        result = executor.close_position(
                            ticker=coin,
                            price=current_price,
                            dry_run=dry_run,
                            reason="Manual close via Telegram"
                        )

                        if result.get('success'):
                            pnl = result.get('realized_pnl', 0)
                            mode = "DRY-RUN" if dry_run else "LIVE"
                            await query.edit_message_text(
                                f"*{coin} Position Closed* [{mode}]\n\n"
                                f"Realized P&L: `{pnl:+,.0f} KRW`\n"
                                f"Close Price: `{current_price:,.0f} KRW`",
                                parse_mode='Markdown'
                            )
                        else:
                            error_msg = result.get('message', 'Unknown error')
                            await query.edit_message_text(
                                f"Failed to close {coin} position:\n{error_msg}"
                            )

                    except Exception as e:
                        await query.edit_message_text(f"Error closing position: {e}")

                    del self._close_pending[coin]
                else:
                    await query.edit_message_text(
                        "Confirmation expired. Use /close again if needed."
                    )
                    del self._close_pending[coin]
            else:
                await query.edit_message_text("No pending close request for this coin.")

        elif query.data == "close_cancel":
            # Clear all pending close requests
            self._close_pending.clear()
            await query.edit_message_text("Close cancelled. Position unchanged.")

    # ========================================
    # Lifecycle Methods
    # ========================================

    def start(self):
        """
        Start the Telegram bot handler in a background thread.

        This method starts an async event loop in a separate thread
        to handle incoming Telegram commands without blocking the
        main trading bot thread.
        """
        if not self.enabled:
            print("TelegramBotHandler: Not enabled, skipping start")
            return

        if self.running:
            print("TelegramBotHandler: Already running")
            return

        self._start_time = datetime.now()
        self.running = True

        self._thread = threading.Thread(target=self._run_async_loop, daemon=True)
        self._thread.start()

        print("TelegramBotHandler: Started in background thread")

    def _run_async_loop(self):
        """Run the async event loop in a separate thread."""
        try:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            self._loop.run_until_complete(self._start_bot())

        except Exception as e:
            print(f"TelegramBotHandler: Error in async loop: {e}")
        finally:
            if self._loop:
                self._loop.close()

    async def _start_bot(self):
        """Start the Telegram bot application."""
        try:
            # Create application
            self._application = Application.builder().token(self.bot_token).build()

            # Add command handlers
            self._application.add_handler(CommandHandler("start", self.cmd_start))
            self._application.add_handler(CommandHandler("help", self.cmd_help))
            self._application.add_handler(CommandHandler("status", self.cmd_status))
            self._application.add_handler(CommandHandler("positions", self.cmd_positions))
            self._application.add_handler(CommandHandler("summary", self.cmd_summary))
            self._application.add_handler(CommandHandler("factors", self.cmd_factors))
            self._application.add_handler(CommandHandler("performance", self.cmd_performance))
            self._application.add_handler(CommandHandler("close", self.cmd_close))
            self._application.add_handler(CommandHandler("stop", self.cmd_stop))
            self._application.add_handler(CommandHandler("reboot", self.cmd_reboot))
            self._application.add_handler(CommandHandler("resume", self.cmd_resume))
            self._application.add_handler(CommandHandler("optimize", self.cmd_optimize))
            self._application.add_handler(CommandHandler("bear_mode", self.cmd_bear_mode))

            # Add callback query handler for inline buttons
            self._application.add_handler(CallbackQueryHandler(self.callback_handler))

            # Start polling
            await self._application.initialize()
            await self._application.start()
            await self._application.updater.start_polling(drop_pending_updates=True)

            print("TelegramBotHandler: Bot started polling")

            # Keep running until stopped
            while self.running:
                await asyncio.sleep(1)

            # Cleanup
            await self._application.updater.stop()
            await self._application.stop()
            await self._application.shutdown()

        except Exception as e:
            print(f"TelegramBotHandler: Error starting bot: {e}")
            import traceback
            traceback.print_exc()

    def stop(self):
        """
        Stop the Telegram bot handler.

        This method signals the handler to stop and waits for
        the background thread to finish.
        """
        if not self.running:
            return

        print("TelegramBotHandler: Stopping...")
        self.running = False

        # Wait for thread to finish (with timeout)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

        print("TelegramBotHandler: Stopped")


# Singleton instance
_handler_instance: Optional[TelegramBotHandler] = None
_handler_lock = threading.Lock()


def get_telegram_bot_handler(trading_bot=None) -> TelegramBotHandler:
    """
    Get singleton instance of TelegramBotHandler.

    Args:
        trading_bot: Reference to TradingBotV3 instance (optional on first call)

    Returns:
        TelegramBotHandler: The singleton handler instance
    """
    global _handler_instance

    with _handler_lock:
        if _handler_instance is None:
            _handler_instance = TelegramBotHandler(trading_bot)
        elif trading_bot is not None:
            _handler_instance.set_trading_bot(trading_bot)

    return _handler_instance
