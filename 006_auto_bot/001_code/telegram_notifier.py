#!/usr/bin/env python3
"""
Telegram Notification Module
----------------------------
Send blog summary notifications via Telegram bot
"""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Telegram bot notification sender"""

    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize Telegram notifier

        Args:
            bot_token: Telegram Bot API token (from @BotFather)
            chat_id: Target chat/channel ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_base = f"https://api.telegram.org/bot{bot_token}"

    def send_message(self, text: str, parse_mode: str = "HTML") -> dict:
        """
        Send a text message via Telegram

        Args:
            text: Message text (supports HTML/Markdown)
            parse_mode: "HTML" or "Markdown"

        Returns:
            API response dict
        """
        try:
            url = f"{self.api_base}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True
            }

            response = requests.post(url, json=payload, timeout=30)
            result = response.json()

            if result.get("ok"):
                logger.info("Telegram message sent successfully")
                return {"success": True, "message_id": result["result"]["message_id"]}
            else:
                logger.error(f"Telegram API error: {result.get('description', 'Unknown error')}")
                return {"success": False, "error": result.get("description", "Unknown error")}

        except requests.exceptions.Timeout:
            logger.error("Telegram API timeout")
            return {"success": False, "error": "Request timeout"}
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return {"success": False, "error": str(e)}

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
            status_header = "✅ <b>블로그 업로드 성공!</b>"
            if blog_url:
                status_header += f"\n🔗 <a href='{blog_url}'>포스트 보기</a>"
        else:
            status_header = "❌ <b>블로그 업로드 실패</b>"
            if error_message:
                status_header += f"\n⚠️ 오류: {error_message}"

        # Convert markdown summary to telegram-friendly format
        telegram_summary = self._convert_markdown_to_telegram(summary_content)

        # Truncate if too long (Telegram limit: 4096 chars)
        max_length = 4000
        if len(telegram_summary) > max_length:
            telegram_summary = telegram_summary[:max_length - 100] + "\n\n... (내용이 길어 일부 생략)"
            # Fix unclosed tags AFTER truncation (truncation can break tags)
            telegram_summary = self._fix_unclosed_html_tags(telegram_summary)

        # Build full message
        message = f"{status_header}\n\n{'─' * 30}\n\n{telegram_summary}"

        return self.send_message(message, parse_mode="HTML")

    def _convert_markdown_to_telegram(self, markdown_text: str) -> str:
        """
        Convert markdown to Telegram HTML format

        Args:
            markdown_text: Original markdown content

        Returns:
            Telegram-friendly HTML text
        """
        import re

        text = markdown_text

        # Remove image links ![alt](url)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

        # Convert markdown links [text](url) to HTML
        text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', text)

        # Convert bold **text** to <b>text</b>
        text = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', text)

        # Convert italic *text* to <i>text</i> (but not ** which is bold)
        text = re.sub(r'(?<!\*)\*([^\*]+)\*(?!\*)', r'<i>\1</i>', text)

        # Convert headers # to bold
        text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

        # Convert code blocks ```code``` to <code>code</code>
        text = re.sub(r'```[^\n]*\n(.*?)```', r'<code>\1</code>', text, flags=re.DOTALL)

        # Convert inline code `code` to <code>code</code>
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

        # Clean up excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove horizontal rules
        text = re.sub(r'^-{3,}$', '─' * 20, text, flags=re.MULTILINE)

        # Validate and fix unclosed HTML tags
        text = self._fix_unclosed_html_tags(text)

        return text.strip()

    def _fix_unclosed_html_tags(self, text: str) -> str:
        """
        Fix unclosed HTML tags to prevent Telegram API parsing errors

        Args:
            text: HTML text to validate

        Returns:
            Text with properly closed HTML tags
        """
        import re

        # Tags that Telegram supports: b, i, u, s, code, pre, a
        simple_tags = ['b', 'i', 'u', 's', 'code', 'pre']

        for tag in simple_tags:
            # Count opening and closing tags
            open_pattern = f'<{tag}>'
            close_pattern = f'</{tag}>'

            open_count = text.lower().count(open_pattern)
            close_count = text.lower().count(close_pattern)

            # Add missing closing tags at the end
            if open_count > close_count:
                text += close_pattern * (open_count - close_count)
            # Remove orphan closing tags
            elif close_count > open_count:
                for _ in range(close_count - open_count):
                    # Remove first orphan closing tag found
                    text = re.sub(f'</{tag}>', '', text, count=1, flags=re.IGNORECASE)

        # Handle <a> tags separately (they have href attribute)
        open_a = len(re.findall(r'<a\s+href=', text, re.IGNORECASE))
        close_a = text.lower().count('</a>')

        if open_a > close_a:
            text += '</a>' * (open_a - close_a)
        elif close_a > open_a:
            for _ in range(close_a - open_a):
                text = re.sub(r'</a>', '', text, count=1, flags=re.IGNORECASE)

        return text

    def test_connection(self) -> bool:
        """Test if bot token and chat_id are valid"""
        try:
            # Get bot info
            url = f"{self.api_base}/getMe"
            response = requests.get(url, timeout=10)
            result = response.json()

            if not result.get("ok"):
                logger.error(f"Invalid bot token: {result.get('description')}")
                return False

            bot_name = result["result"]["username"]
            logger.info(f"Telegram bot connected: @{bot_name}")

            # Send test message
            test_result = self.send_message("🤖 News Bot 연결 테스트 성공!")
            return test_result.get("success", False)

        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False


# CLI for testing
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv

    load_dotenv()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Error: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        print("\nHow to get these:")
        print("1. Create bot: Message @BotFather on Telegram, send /newbot")
        print("2. Get chat ID: Message @userinfobot or forward message to @getidsbot")
        exit(1)

    notifier = TelegramNotifier(bot_token, chat_id)

    print("Testing Telegram connection...")
    if notifier.test_connection():
        print("✅ Connection successful!")

        # Test blog notification
        test_summary = """
# 2024년 12월 12일 뉴스 요약

## 주요 뉴스

### 경제
- **테스트 뉴스 1**: 경제 관련 내용입니다.
- **테스트 뉴스 2**: 추가 경제 뉴스입니다.

### 정치
- **테스트 뉴스 3**: 정치 관련 뉴스입니다.

---
자동 생성된 뉴스 요약입니다.
        """

        print("\nSending test blog notification...")
        result = notifier.send_blog_notification(
            summary_content=test_summary,
            upload_success=True,
            blog_url="https://example.blogspot.com/2024/12/test-post.html"
        )

        if result["success"]:
            print("✅ Test notification sent!")
        else:
            print(f"❌ Failed: {result['error']}")
    else:
        print("❌ Connection failed!")
