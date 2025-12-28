"""
Telegram Notifier - Simple implementation using requests library

This module provides Telegram notification functionality for the trading bot,
allowing real-time alerts for trades, errors, and bot status updates.

Environment Variables Required:
    TELEGRAM_BOT_TOKEN: Bot token from BotFather
    TELEGRAM_CHAT_ID: Chat ID to send messages to
    TELEGRAM_NOTIFICATIONS_ENABLED: Enable/disable notifications (default: False)

Features:
- Simple trade alerts (buy/sell success/failure)
- Error notifications
- Bot status updates (started/stopped/running)
- Daily trading summaries
- Singleton pattern for global access

Usage:
    from lib.core.telegram_notifier import get_telegram_notifier

    telegram = get_telegram_notifier()
    telegram.send_trade_alert(
        action="BUY",
        ticker="BTC",
        amount=0.001,
        price=50000000,
        success=True
    )
"""

import os
import requests
import threading
import time
from typing import Optional, Dict, Any
from datetime import datetime


class TelegramNotifier:
    """
    Simple Telegram notification sender using requests library.

    This class handles all Telegram notifications for the trading bot,
    including trade alerts, error notifications, and status updates.

    Attributes:
        bot_token (str): Telegram bot token from BotFather
        chat_id (str): Chat ID to send messages to
        enabled (bool): Whether notifications are enabled
        base_url (str): Telegram API base URL
    """

    def __init__(self):
        """
        Initialize the Telegram notifier with environment variables.

        Checks for TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, and
        TELEGRAM_NOTIFICATIONS_ENABLED environment variables.
        If credentials are missing, notifications are automatically disabled.
        """
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = os.getenv("TELEGRAM_NOTIFICATIONS_ENABLED", "False").lower() == "true"

        if self.bot_token:
            self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        else:
            self.base_url = None

        # Validate configuration
        if self.enabled and (not self.bot_token or not self.chat_id):
            print("⚠️  Telegram notifications enabled but credentials not found!")
            print("   Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file")
            self.enabled = False

        # Track consecutive failures for alerting
        self._consecutive_failures = 0
        self._failure_threshold = 3  # Alert after 3 consecutive failures

    def _escape_markdown(self, text: str) -> str:
        """
        Escape Markdown special characters to prevent formatting errors.

        Args:
            text (str): Raw text that may contain special characters

        Returns:
            str: Text with escaped special characters

        Note:
            Escapes: _ * [ ] ( ) ~ ` > # + - = | { } . !
        """
        special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in special_chars:
            text = text.replace(char, f'\\{char}')
        return text

    def send_message(self, message: str, parse_mode: str = "Markdown", max_retries: int = 3) -> bool:
        """
        Send a message to Telegram with retry logic and exponential backoff.

        Args:
            message (str): Message text (supports Markdown or HTML formatting)
            parse_mode (str): Format mode - "Markdown" or "HTML" (default: Markdown)
            max_retries (int): Maximum number of retry attempts (default: 3)

        Returns:
            bool: True if sent successfully, False otherwise

        Note:
            - Silently returns False if notifications are disabled
            - Retries with exponential backoff: 1s, 2s, 4s
            - Tracks consecutive failures and alerts after threshold
            - Catches all exceptions to prevent disrupting bot operation
        """
        if not self.enabled:
            return False

        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode
                }

                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()

                # Success - reset failure counter
                self._consecutive_failures = 0
                return True

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    # Exponential backoff: 2^attempt seconds (1s, 2s, 4s)
                    backoff_time = 2 ** attempt
                    print(f"⚠️  Telegram send failed (attempt {attempt + 1}/{max_retries}), retrying in {backoff_time}s: {e}")
                    time.sleep(backoff_time)
                    continue
                else:
                    # Final failure
                    self._consecutive_failures += 1
                    error_msg = f"❌ Telegram notification failed after {max_retries} attempts: {e}"

                    # Alert if threshold reached
                    if self._consecutive_failures >= self._failure_threshold:
                        print(f"\n{'='*60}")
                        print(f"🚨 ALERT: {self._consecutive_failures} consecutive Telegram failures!")
                        print(f"   Check network connection or Telegram credentials")
                        print(f"   Trading will continue, but notifications are not being sent")
                        print(f"{'='*60}\n")

                    print(error_msg)
                    return False

            except Exception as e:
                self._consecutive_failures += 1
                print(f"❌ Unexpected error sending Telegram notification: {e}")

                if self._consecutive_failures >= self._failure_threshold:
                    print(f"\n{'='*60}")
                    print(f"🚨 ALERT: {self._consecutive_failures} consecutive Telegram failures!")
                    print(f"   Unexpected error type - check logs for details")
                    print(f"{'='*60}\n")

                return False

        return False

    def send_trade_alert(
        self,
        action: str,
        ticker: str,
        amount: float,
        price: float,
        success: bool,
        reason: str = "",
        order_id: str = ""
    ) -> bool:
        """
        Send trading alert notification.

        Args:
            action (str): Trade action - "BUY", "SELL", or "CLOSE"
            ticker (str): Coin ticker symbol (e.g., "BTC", "ETH")
            amount (float): Trade amount (units of cryptocurrency)
            price (float): Trade price in KRW
            success (bool): Whether the trade was successful
            reason (str, optional): Additional reason or context for the trade
            order_id (str, optional): Order ID from the exchange

        Returns:
            bool: True if notification sent successfully

        Example:
            >>> telegram.send_trade_alert(
            ...     action="BUY",
            ...     ticker="BTC",
            ...     amount=0.001,
            ...     price=50000000,
            ...     success=True,
            ...     reason="Score: 4/4",
            ...     order_id="12345678"
            ... )
        """
        if not self.enabled:
            return False

        # Emoji based on action and success
        if success:
            if action == "BUY":
                emoji = "🟢"
            elif action == "SELL":
                emoji = "🔴"
            else:  # CLOSE or other
                emoji = "🔵"
            status = "성공"
        else:
            emoji = "❌"
            status = "실패"

        # Format message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Calculate total trade value
        total_value = amount * price

        message = f"""
{emoji} *{action} {status}*

📊 코인: `{ticker}`
💰 수량: `{amount:.8f}`
💵 가격: `{price:,.0f} KRW`
💸 총액: `{total_value:,.0f} KRW`

⏰ 시각: {timestamp}
"""

        if reason:
            message += f"📝 사유: {reason}\n"

        if order_id:
            message += f"🔖 주문ID: `{order_id}`\n"

        return self.send_message(message)

    def send_error_alert(
        self,
        error_type: str,
        error_message: str,
        details: str = ""
    ) -> bool:
        """
        Send error alert notification.

        Args:
            error_type (str): Type or category of error
            error_message (str): Main error message
            details (str, optional): Additional error details or stack trace

        Returns:
            bool: True if notification sent successfully

        Example:
            >>> telegram.send_error_alert(
            ...     error_type="API Connection Error",
            ...     error_message="Failed to connect to Bithumb API",
            ...     details="Timeout after 10 seconds"
            ... )
        """
        if not self.enabled:
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = f"""
⚠️ *에러 발생*

🔴 유형: {error_type}
📝 메시지: `{error_message}`

⏰ 시각: {timestamp}
"""

        if details:
            # Limit details length to prevent message overflow
            max_detail_len = 500
            if len(details) > max_detail_len:
                details = details[:max_detail_len] + "..."
            message += f"\n📋 상세:\n```\n{details}\n```"

        return self.send_message(message)

    def send_bot_status(
        self,
        status: str,
        positions: int,
        max_positions: int,
        total_pnl: float = 0,
        coins: list = None
    ) -> bool:
        """
        Send bot status notification.

        Args:
            status (str): Bot status - "STARTED", "STOPPED", "RUNNING", "ERROR"
            positions (int): Current number of open positions
            max_positions (int): Maximum allowed positions
            total_pnl (float, optional): Total profit/loss in KRW (default: 0)
            coins (list, optional): List of monitored coin symbols

        Returns:
            bool: True if notification sent successfully

        Example:
            >>> telegram.send_bot_status(
            ...     status="STARTED",
            ...     positions=2,
            ...     max_positions=3,
            ...     total_pnl=50000,
            ...     coins=["BTC", "ETH", "XRP"]
            ... )
        """
        if not self.enabled:
            return False

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Select emoji based on status
        status_emoji = {
            "STARTED": "🚀",
            "STOPPED": "🛑",
            "RUNNING": "✅",
            "ERROR": "❌"
        }.get(status, "ℹ️")

        message = f"""
{status_emoji} *봇 상태: {status}*

📊 포지션: {positions}/{max_positions}
💰 총 손익: `{total_pnl:+,.0f} KRW`

⏰ 시각: {timestamp}
"""

        if coins:
            coins_str = ', '.join(coins)
            message += f"🪙 모니터링 코인: {coins_str}\n"

        return self.send_message(message)

    def send_daily_summary(self, summary_data: Dict[str, Any]) -> bool:
        """
        Send daily trading summary notification.

        Args:
            summary_data (dict): Dictionary containing summary information:
                - date (str): Date of summary (e.g., "2025-12-09")
                - buy_count (int): Number of buy orders
                - sell_count (int): Number of sell orders
                - total_volume (float): Total trading volume in KRW
                - total_fees (float): Total fees paid in KRW
                - net_pnl (float): Net profit/loss in KRW
                - success_count (int): Number of successful trades
                - fail_count (int): Number of failed trades

        Returns:
            bool: True if notification sent successfully

        Example:
            >>> telegram.send_daily_summary({
            ...     'date': '2025-12-09',
            ...     'buy_count': 5,
            ...     'sell_count': 3,
            ...     'total_volume': 500000,
            ...     'total_fees': 1250,
            ...     'net_pnl': 25000,
            ...     'success_count': 7,
            ...     'fail_count': 1
            ... })
        """
        if not self.enabled:
            return False

        message = f"""
📈 *일일 거래 요약*

📅 날짜: {summary_data.get('date', 'N/A')}

🔵 매수 횟수: {summary_data.get('buy_count', 0)}
🔴 매도 횟수: {summary_data.get('sell_count', 0)}
💰 총 거래액: {summary_data.get('total_volume', 0):,.0f} KRW
💸 수수료: {summary_data.get('total_fees', 0):,.0f} KRW
📊 순손익: `{summary_data.get('net_pnl', 0):+,.0f} KRW`

✅ 성공: {summary_data.get('success_count', 0)}
❌ 실패: {summary_data.get('fail_count', 0)}
"""

        return self.send_message(message)

    def send_dynamic_factors_summary(self, factors_data: Dict[str, Any]) -> bool:
        """
        Send dynamic factors summary notification.

        This provides the same information visible in the GUI's Dynamic Factors tab,
        allowing CLI users to monitor factor states via Telegram.

        Args:
            factors_data (dict): Dictionary containing factor information:
                - volatility_level (str): Current volatility level (LOW/NORMAL/HIGH/EXTREME)
                - atr_percent (float): ATR as percentage of price
                - regime (str): Current market regime
                - chandelier_multiplier_modifier (float): Chandelier stop multiplier
                - position_size_modifier (float): Position size adjustment
                - rsi_oversold_threshold (int): RSI oversold threshold
                - stoch_oversold_threshold (int): Stochastic oversold threshold
                - entry_weights (dict): Entry condition weights (bb_touch, rsi_oversold, stoch_cross)
                - min_entry_score (int): Minimum score required for entry

        Returns:
            bool: True if notification sent successfully
        """
        if not self.enabled:
            return False

        # Extract values with defaults
        volatility = factors_data.get('volatility_level', 'UNKNOWN')
        atr_pct = factors_data.get('atr_percent', 0.0)
        regime = factors_data.get('regime', 'unknown')
        chandelier_mod = factors_data.get('chandelier_multiplier_modifier', 1.0)
        pos_size_mod = factors_data.get('position_size_modifier', 1.0)
        rsi_threshold = factors_data.get('rsi_oversold_threshold', 30)
        stoch_threshold = factors_data.get('stoch_oversold_threshold', 20)
        min_score = factors_data.get('min_entry_score', 2)

        # Entry weights
        entry_weights = factors_data.get('entry_weights', {})
        bb_weight = entry_weights.get('bb_touch', 1.0)
        rsi_weight = entry_weights.get('rsi_oversold', 1.0)
        stoch_weight = entry_weights.get('stoch_cross', 2.0)

        # Volatility emoji
        vol_emoji = {
            'LOW': '🟢',
            'NORMAL': '🟡',
            'HIGH': '🟠',
            'EXTREME': '🔴'
        }.get(volatility.upper(), '⚪')

        # Regime emoji
        regime_emoji = {
            'strong_bullish': '🚀',
            'bullish': '📈',
            'neutral': '➖',
            'bearish': '📉',
            'strong_bearish': '💥',
            'ranging': '↔️'
        }.get(regime.lower(), '❓')

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = f"""
🎚️ *동적 팩터 현황*

⏰ 시각: {timestamp}

*📊 시장 상태*
{regime_emoji} 레짐: `{regime.upper()}`
{vol_emoji} 변동성: `{volatility}` (ATR {atr_pct:.2f}%)

*⚙️ 리스크 파라미터*
🛑 Chandelier 배수: `{chandelier_mod:.2f}x`
📏 포지션 크기: `{pos_size_mod:.0%}`
📉 RSI 과매도: `{rsi_threshold}`
📊 Stoch 과매도: `{stoch_threshold}`

*🎯 진입 가중치*
BB Touch: `{bb_weight:.2f}`
RSI 과매도: `{rsi_weight:.2f}`
Stoch Cross: `{stoch_weight:.2f}`
최소 스코어: `{min_score}`
"""

        return self.send_message(message)

    def send_performance_summary(self, performance_data: Dict[str, Any]) -> bool:
        """
        Send 7-day performance summary notification.

        Args:
            performance_data (dict): Dictionary containing performance information:
                - total_trades (int): Total number of trades
                - win_count (int): Number of winning trades
                - loss_count (int): Number of losing trades
                - win_rate (float): Win rate as decimal (0.0-1.0)
                - total_profit (float): Total profit in KRW
                - total_loss (float): Total loss in KRW
                - profit_factor (float): Profit factor (gross profit / gross loss)
                - avg_profit (float): Average profit per winning trade
                - avg_loss (float): Average loss per losing trade
                - per_condition (dict): Performance breakdown by entry condition

        Returns:
            bool: True if notification sent successfully
        """
        if not self.enabled:
            return False

        total_trades = performance_data.get('total_trades', 0)
        win_count = performance_data.get('win_count', 0)
        loss_count = performance_data.get('loss_count', 0)
        win_rate = performance_data.get('win_rate', 0.0)
        total_profit = performance_data.get('total_profit', 0.0)
        total_loss = performance_data.get('total_loss', 0.0)
        profit_factor = performance_data.get('profit_factor', 0.0)
        avg_profit = performance_data.get('avg_profit', 0.0)
        avg_loss = performance_data.get('avg_loss', 0.0)
        net_pnl = total_profit - abs(total_loss)

        # PnL emoji
        pnl_emoji = '📈' if net_pnl >= 0 else '📉'

        # Win rate indicator
        if win_rate >= 0.6:
            wr_indicator = '🟢'
        elif win_rate >= 0.4:
            wr_indicator = '🟡'
        else:
            wr_indicator = '🔴'

        message = f"""
📊 *7일 성과 요약*

*거래 통계*
총 거래: `{total_trades}`
승리: `{win_count}` / 패배: `{loss_count}`
{wr_indicator} 승률: `{win_rate:.1%}`

*손익 분석*
{pnl_emoji} 순손익: `{net_pnl:+,.0f} KRW`
총 수익: `{total_profit:+,.0f} KRW`
총 손실: `{total_loss:,.0f} KRW`
PF: `{profit_factor:.2f}`

*평균*
평균 수익: `{avg_profit:+,.0f} KRW`
평균 손실: `{avg_loss:,.0f} KRW`
"""

        # Add per-condition breakdown if available
        per_condition = performance_data.get('per_condition', {})
        if per_condition:
            message += "\n*조건별 성과*\n"
            for condition, stats in per_condition.items():
                cond_trades = stats.get('trades', 0)
                cond_wr = stats.get('win_rate', 0.0)
                if cond_trades > 0:
                    message += f"  {condition}: `{cond_wr:.0%}` ({cond_trades}건)\n"

        return self.send_message(message)

    def send_regime_change_alert(
        self,
        old_regime: str,
        new_regime: str,
        coin: str = "Market",
        ema_diff_pct: float = 0.0
    ) -> bool:
        """
        Send market regime change alert notification.

        This alert is sent when the market regime changes significantly,
        helping CLI users stay informed about market condition shifts.

        Args:
            old_regime (str): Previous market regime
            new_regime (str): New market regime
            coin (str): Coin symbol (default: "Market" for general)
            ema_diff_pct (float): EMA difference percentage

        Returns:
            bool: True if notification sent successfully
        """
        if not self.enabled:
            return False

        # Regime emojis and descriptions
        regime_info = {
            'strong_bullish': ('🚀', '강한 상승장', 'EMA50 > EMA200 +5%'),
            'bullish': ('📈', '상승장', 'EMA50 > EMA200'),
            'neutral': ('➖', '중립', 'EMAs 근접'),
            'bearish': ('📉', '하락장', 'EMA50 < EMA200'),
            'strong_bearish': ('💥', '강한 하락장', 'EMA50 < EMA200 -5%'),
            'ranging': ('↔️', '횡보장', 'ADX < 15'),
        }

        old_info = regime_info.get(old_regime.lower(), ('❓', old_regime, ''))
        new_info = regime_info.get(new_regime.lower(), ('❓', new_regime, ''))

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Determine if this is a significant shift (bullish to bearish or vice versa)
        bullish_regimes = {'strong_bullish', 'bullish'}
        bearish_regimes = {'strong_bearish', 'bearish'}

        old_is_bullish = old_regime.lower() in bullish_regimes
        new_is_bullish = new_regime.lower() in bullish_regimes
        old_is_bearish = old_regime.lower() in bearish_regimes
        new_is_bearish = new_regime.lower() in bearish_regimes

        if (old_is_bullish and new_is_bearish) or (old_is_bearish and new_is_bullish):
            alert_level = "🚨 *중요 레짐 전환!*"
        else:
            alert_level = "📢 *레짐 변경 알림*"

        message = f"""
{alert_level}

⏰ 시각: {timestamp}
🪙 대상: `{coin}`

*변경 내역*
이전: {old_info[0]} `{old_info[1]}`
현재: {new_info[0]} `{new_info[1]}`

EMA 격차: `{ema_diff_pct:+.2f}%`

_전략이 새 레짐에 맞게 조정됩니다._
"""

        return self.send_message(message)


# Singleton instance - ensures only one notifier exists
_notifier_instance = None
_notifier_lock = threading.Lock()


def get_telegram_notifier() -> TelegramNotifier:
    """
    Get singleton instance of TelegramNotifier (thread-safe).

    This function ensures that only one TelegramNotifier instance
    exists throughout the application lifecycle. Uses double-checked
    locking pattern for thread safety in multi-threaded environments.

    Returns:
        TelegramNotifier: The singleton notifier instance

    Usage:
        >>> from lib.core.telegram_notifier import get_telegram_notifier
        >>> telegram = get_telegram_notifier()
        >>> telegram.send_message("Hello from Trading Bot!")

    Thread Safety:
        Safe for concurrent calls from multiple threads.
        Uses double-checked locking to minimize lock contention.
    """
    global _notifier_instance

    # First check (without lock) - fast path for already initialized instance
    if _notifier_instance is None:
        # Acquire lock for initialization
        with _notifier_lock:
            # Second check (with lock) - prevent multiple initialization
            if _notifier_instance is None:
                _notifier_instance = TelegramNotifier()

    return _notifier_instance
