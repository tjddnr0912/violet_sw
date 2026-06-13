"""
Shared modules for 006_auto_bot
--------------------------------
Common utilities used by both news_bot and telegram_gemini_bot
"""

from .html_utils import HtmlUtils
from .telegram_api import TelegramClient
from .telegram_notifier import TelegramNotifier

__all__ = ['HtmlUtils', 'TelegramClient', 'TelegramNotifier']
