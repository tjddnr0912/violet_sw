#!/usr/bin/env python3
"""
Telegram Notification Module
----------------------------
Send blog summary notifications via Telegram bot
"""

import logging
from typing import Optional

from .telegram_api import TelegramClient
from .html_utils import HtmlUtils

logger = logging.getLogger(__name__)


class TelegramNotifier(TelegramClient):
    """Telegram bot notification sender for news bot"""

    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize Telegram notifier

        Args:
            bot_token: Telegram Bot API token (from @BotFather)
            chat_id: Target chat/channel ID
        """
        super().__init__(bot_token, chat_id)

    def send_blog_notification(
        self,
        summary_content: str,
        upload_success: bool,
        blog_url: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> dict:
        """
        Send blog upload notification with summary

        Args:
            summary_content: Blog summary markdown content
            upload_success: Whether blog upload succeeded
            blog_url: URL of uploaded blog post (if successful)
            error_message: Error message (if failed)

        Returns:
            API response dict
        """
        # Build status header
        if upload_success:
            status_header = "<b>Blog upload successful!</b>"
            if blog_url:
                status_header += f"\n<a href='{blog_url}'>View Post</a>"
        else:
            status_header = "<b>Blog upload failed</b>"
            if error_message:
                status_header += f"\nError: {error_message}"

        # Convert markdown summary to telegram-friendly format
        telegram_summary = HtmlUtils.markdown_to_telegram_html(summary_content)

        # Truncate if too long
        telegram_summary = HtmlUtils.truncate_with_tag_fix(telegram_summary, 4000)

        # Build full message
        message = f"{status_header}\n\n{'\u2500' * 30}\n\n{telegram_summary}"

        # Try HTML first, fallback to plain text if parsing fails
        result = self.send_message(message, parse_mode="HTML")

        if not result.get("success") and "parse entities" in result.get("error", ""):
            logger.warning("HTML parsing failed, retrying with plain text...")
            # Build plain text version
            plain_header = "Blog upload successful!" if upload_success else "Blog upload failed"
            if upload_success and blog_url:
                plain_header += f"\n{blog_url}"
            elif not upload_success and error_message:
                plain_header += f"\nError: {error_message}"

            # Simple text cleanup (remove markdown/html)
            import re
            plain_summary = summary_content
            plain_summary = re.sub(r'[#*_`]', '', plain_summary)
            plain_summary = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', plain_summary)
            plain_summary = re.sub(r'<[^>]+>', '', plain_summary)

            if len(plain_summary) > 3900:
                plain_summary = plain_summary[:3800] + "\n\n... (truncated)"

            plain_message = f"{plain_header}\n\n{'\u2500' * 30}\n\n{plain_summary}"
            result = self.send_message(plain_message, parse_mode=None)

        return result


# CLI for testing
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Error: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        exit(1)

    notifier = TelegramNotifier(bot_token, chat_id)

    print("Testing Telegram connection...")
    if notifier.test_connection():
        print("Connection successful!")

        # Test blog notification
        test_summary = """
# 2024-12-12 News Summary

## Headlines

### Economy
- **Test News 1**: Economic content here.
- **Test News 2**: Additional economic news.

### Politics
- **Test News 3**: Political news here.

---
Auto-generated news summary.
        """

        print("\nSending test blog notification...")
        result = notifier.send_blog_notification(
            summary_content=test_summary,
            upload_success=True,
            blog_url="https://example.blogspot.com/2024/12/test-post.html"
        )

        if result["success"]:
            print("Test notification sent!")
        else:
            print(f"Failed: {result['error']}")
    else:
        print("Connection failed!")
