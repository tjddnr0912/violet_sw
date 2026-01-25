#!/usr/bin/env python3
"""
Telegram + Gemini CLI + Blogger Integration Bot
------------------------------------------------
1. Receive messages from Telegram (polling)
2. Send questions to Gemini CLI
3. Upload results to Google Blogger
4. Send notification via Telegram

Usage:
    python telegram_gemini_bot.py           # Normal execution
    python telegram_gemini_bot.py --test    # Test mode (skip blog upload)
"""

import os
import sys
import time
import subprocess
import logging
import argparse
import re
from datetime import datetime
from typing import Optional, Tuple
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# Import shared modules
from shared.telegram_api import TelegramClient
from shared.html_utils import HtmlUtils


def setup_logging():
    """Configure logging - console + file output"""
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    log_filename = f'telegram_bot_{datetime.now().strftime("%Y%m%d")}.log'
    log_path = os.path.join(log_dir, log_filename)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


logger = setup_logging()


class TelegramGeminiBot(TelegramClient):
    """Telegram bot that processes messages with Gemini and uploads to Blogger"""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        upload_to_blog: bool = True
    ):
        super().__init__(bot_token, chat_id)
        self.upload_to_blog = upload_to_blog
        self.last_update_id = 0

    def run_gemini(self, question: str) -> Tuple[bool, str, str, list, list]:
        """
        Run Gemini CLI

        Returns:
            Tuple[bool, str, str, list, list]: (success, content, title, labels, sources)
        """
        try:
            logger.info(f"Running Gemini: {question[:50]}...")

            # Build prompt with blog style + title/labels generation
            prompt = f"""{question}

---
IMPORTANT:
- DO NOT include any thinking process, reasoning steps, or internal analysis.
- Start with the final answer directly. No "Let me think", "I will", "Let's analyze", "First, I need to" or similar phrases.

Write a blog-style article answering the question above.

Writing Guidelines:
- Use clear structure with subheadings and paragraphs
- Highlight key points with bold text or lists
- Include examples or code if helpful
- Use a friendly, readable tone
- Include sources if available

At the very end, add these metadata lines:
TITLE: [A concise title representing the content]
LABELS: [2-3 keywords separated by commas]
SOURCES: [Sources in "title|URL" format, comma-separated]"""

            # Run gemini CLI
            result = subprocess.run(
                ["gemini", prompt],
                capture_output=True,
                text=True,
                timeout=900  # 15 minute timeout
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    logger.info(f"Gemini response success (length: {len(output)})")
                    logger.info(f"Gemini response tail:\n{output[-500:]}")
                    content, title, labels, sources = self._parse_response(output)
                    logger.info(f"Parsed - title: {title}, labels: {labels}, sources: {len(sources)}, content: {len(content)}")
                    return True, content, title, labels, sources
                else:
                    logger.warning("Gemini response is empty")
                    return False, "Gemini response is empty.", "", [], []
            else:
                error = result.stderr.strip() or "Unknown error"
                logger.error(f"Gemini execution failed (returncode={result.returncode}): {error}")
                return False, f"Gemini error: {error}", "", [], []

        except subprocess.TimeoutExpired:
            logger.error("Gemini response timeout (15 min)")
            return False, "Gemini response timeout (15 min)", "", [], []
        except FileNotFoundError:
            logger.error("gemini CLI not found")
            return False, "gemini CLI not found. Please check installation.", "", [], []
        except Exception as e:
            logger.error(f"Gemini execution error: {str(e)}", exc_info=True)
            return False, f"Gemini execution error: {str(e)}", "", [], []

    def _parse_response(self, response: str) -> Tuple[str, str, list, list]:
        """
        Parse Gemini response to extract content, title, labels, and sources

        Returns:
            Tuple[str, str, list, list]: (content, title, labels, sources)
        """
        lines = response.strip().split('\n')
        title = ""
        labels = []
        sources = []
        content_end_idx = len(lines)

        # Find TITLE:, LABELS:, SOURCES: from the end
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i].strip()

            # SOURCES: pattern
            source_match = re.match(r'^SOURCES?:\s*(.+)$', line, re.IGNORECASE)
            if source_match:
                source_str = source_match.group(1).strip()
                for src in source_str.split(','):
                    src = src.strip()
                    if '|' in src:
                        parts = src.split('|', 1)
                        src_title = parts[0].strip()
                        src_url = parts[1].strip()
                        if src_url and src_title:
                            sources.append({"title": src_title, "url": src_url})
                    elif src.startswith('http'):
                        sources.append({"title": src, "url": src})
                content_end_idx = min(content_end_idx, i)

            # LABELS: pattern
            label_match = re.match(r'^LABELS?:\s*(.+)$', line, re.IGNORECASE)
            if label_match:
                label_str = label_match.group(1).strip()
                labels = [l.strip() for l in label_str.split(',') if l.strip()]
                content_end_idx = min(content_end_idx, i)

            # TITLE: pattern
            title_match = re.match(r'^TITLE:\s*(.+)$', line, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
                content_end_idx = min(content_end_idx, i)

        # Extract content (before TITLE/LABELS/SOURCES)
        content_lines = lines[:content_end_idx]

        # Remove trailing separators and empty lines
        while content_lines and content_lines[-1].strip() in ['---', '']:
            content_lines.pop()

        # Default title if not found
        if not title:
            first_line = response.split('\n')[0].strip()
            if first_line.startswith('#'):
                first_line = first_line.lstrip('#').strip()
            if len(first_line) > 60:
                title = first_line[:57] + "..."
            elif len(first_line) > 10:
                title = first_line
            else:
                title = response[:50].replace('\n', ' ').strip() + "..."
            logger.warning(f"TITLE not found, using default: {title}")

        # Default labels if not found
        if not labels:
            labels = ["AI", "Gemini"]
            logger.warning("LABELS not found, using default: ['AI', 'Gemini']")

        content = '\n'.join(content_lines).strip()
        return content, title, labels, sources

    def _format_sources_section(self, sources: list) -> str:
        """Format sources list as markdown section"""
        if not sources:
            return ""

        source_lines = ["", "---", "", "## References", ""]
        for src in sources:
            title = src.get("title", "Source")
            url = src.get("url", "")
            if url:
                source_lines.append(f"- [{title}]({url})")
            else:
                source_lines.append(f"- {title}")

        return '\n'.join(source_lines)

    def _create_original_section(self, cleaned_md: str) -> str:
        """정제된 Markdown을 접기 형태의 HTML로 생성

        Args:
            cleaned_md: 메타데이터(TITLE/LABELS/SOURCES) 제거된 정제 콘텐츠
                        = content + sources_section (기존 업로드 내용)
        """
        import html as html_module
        escaped_content = html_module.escape(cleaned_md)

        return f'''
<details style="margin-top: 40px !important; padding: 15px !important; background-color: #f5f5f5 !important; border-radius: 8px !important; border: 1px solid #e0e0e0 !important;">
  <summary style="cursor: pointer !important; font-weight: 600 !important; color: #666666 !important; padding: 10px 0 !important;">
    📄 Raw Data
  </summary>
  <pre style="margin-top: 15px !important; padding: 15px !important; background-color: #ffffff !important; border-radius: 4px !important; white-space: pre-wrap !important; word-wrap: break-word !important; font-size: 13px !important; line-height: 1.6 !important; color: #333333 !important; overflow-x: auto !important;">{escaped_content}</pre>
</details>
'''

    def upload_to_blogger(self, title: str, content: str, labels: list = None, sources: list = None) -> Tuple[bool, str]:
        """Upload to Google Blogger"""
        if not self.upload_to_blog:
            return True, "(Test mode - upload skipped)"

        try:
            from shared.blogger_uploader import BloggerUploader

            blog_id = os.getenv("BLOGGER_BLOG_ID")
            credentials_path = os.getenv("BLOGGER_CREDENTIALS_PATH", "./credentials/blogger_credentials.json")
            token_path = os.getenv("BLOGGER_TOKEN_PATH", "./credentials/blogger_token.pkl")
            is_draft = os.getenv("BLOGGER_IS_DRAFT", "false").lower() == "true"

            if not labels:
                labels = ["AI", "Gemini"]

            if not blog_id:
                return False, "BLOGGER_BLOG_ID environment variable not set."

            # Add sources section (정제된 Markdown)
            sources_section = self._format_sources_section(sources)
            full_md_content = content + sources_section

            # Claude CLI로 HTML 변환 시도
            upload_content = full_md_content
            is_markdown = True

            try:
                from shared.claude_html_converter import convert_md_to_html_via_claude
                logger.info("Using Claude CLI for HTML conversion...")
                html_content = convert_md_to_html_via_claude(full_md_content)

                # 원본을 <details> 태그로 HTML 하단에 추가
                original_section = self._create_original_section(full_md_content)
                upload_content = f"{html_content}\n{original_section}"
                is_markdown = False
                logger.info(f"Claude HTML conversion complete ({len(upload_content)} chars)")
            except Exception as e:
                logger.warning(f"Claude CLI failed, fallback to markdown lib: {e}")
                upload_content = full_md_content
                is_markdown = True

            logger.info(f"Initializing Blogger uploader... (labels: {labels}, sources: {len(sources) if sources else 0})")
            uploader = BloggerUploader(
                blog_id=blog_id,
                credentials_path=credentials_path,
                token_path=token_path
            )

            logger.info("Uploading to blog...")
            result = uploader.upload_post(
                title=title,
                content=upload_content,
                labels=labels,
                is_draft=is_draft,
                is_markdown=is_markdown
            )

            if result.get("success"):
                post_url = result.get("url", "URL not available")
                return True, post_url
            else:
                return False, result.get("message", "Upload failed")

        except ImportError:
            return False, "blogger_uploader module not found."
        except Exception as e:
            return False, f"Upload error: {str(e)}"

    def process_message(self, message: dict) -> None:
        """Process received message"""
        text = message.get("text", "")
        chat = message.get("chat", {})

        # Only process allowed chat_id
        if str(chat.get("id")) != self.chat_id:
            logger.warning(f"Unauthorized chat_id: {chat.get('id')}")
            return

        # Handle commands
        if text.startswith("/"):
            self._handle_command(text)
            return

        if not text:
            return

        logger.info(f"Question received (length: {len(text)}): {text[:100]}{'...' if len(text) > 100 else ''}")

        # Send processing notification
        self.send_message("Question received. Asking Gemini...")

        # Run Gemini
        success, gemini_content, gemini_title, gemini_labels, gemini_sources = self.run_gemini(text)

        if not success:
            self.send_message(f"Gemini error: {gemini_content}")
            return

        # Upload to blog
        upload_success, upload_result = self.upload_to_blogger(
            gemini_title, gemini_content, gemini_labels, gemini_sources
        )

        # Build result message
        labels_str = ', '.join(gemini_labels) if gemini_labels else '-'
        sources_count = len(gemini_sources) if gemini_sources else 0

        # Format sources for Telegram
        sources_str = ""
        if gemini_sources:
            sources_str = "\n<b>References:</b>\n"
            for src in gemini_sources[:5]:
                title = src.get("title", "Source")
                url = src.get("url", "")
                if url:
                    sources_str += f"- <a href=\"{url}\">{title}</a>\n"
                else:
                    sources_str += f"- {title}\n"
            if len(gemini_sources) > 5:
                sources_str += f"... and {len(gemini_sources) - 5} more\n"

        # Truncate preview
        preview = gemini_content[:500] + ('...' if len(gemini_content) > 500 else '')
        preview = HtmlUtils.fix_unclosed_tags(preview)

        if upload_success:
            result_msg = f"""<b>Gemini response complete!</b>

<b>Title:</b> {gemini_title}
<b>Labels:</b> {labels_str}

<b>Blog upload:</b> {upload_result}

<b>Preview:</b>
{preview}{sources_str}"""
        else:
            preview_long = gemini_content[:1000]
            preview_long = HtmlUtils.fix_unclosed_tags(preview_long)
            result_msg = f"""<b>Gemini response complete!</b>

<b>Title:</b> {gemini_title}
<b>Labels:</b> {labels_str}

<b>Blog upload failed:</b> {upload_result}

<b>Response:</b>
{preview_long}{sources_str}"""

        self.send_message(result_msg)
        logger.info(f"Completed - title: {gemini_title}, labels: {gemini_labels}, sources: {sources_count}")

    def _handle_command(self, command: str) -> None:
        """Handle bot commands"""
        cmd = command.split()[0].lower()

        if cmd == "/start":
            self.send_message("""<b>Gemini Blogger Bot</b>

Enter a question and:
1. Gemini CLI generates response
2. Auto-upload to Google Blogger
3. Notification via Telegram

<b>Commands:</b>
/help - Help
/status - Status check""")

        elif cmd == "/help":
            self.send_message("""<b>Usage:</b>
Just type your question!

Examples:
- What is list comprehension in Python?
- Explain blockchain technology
- Difference between React and Vue""")

        elif cmd == "/status":
            upload_status = "Enabled" if self.upload_to_blog else "Test mode"
            self.send_message(f"""<b>Bot Status</b>
- Blog upload: {upload_status}
- Last update ID: {self.last_update_id}""")

        else:
            self.send_message(f"Unknown command: {cmd}")

    def run(self) -> None:
        """Bot main loop"""
        logger.info("=" * 50)
        logger.info("Telegram Gemini Blogger Bot started")
        logger.info(f"Blogger upload: {'Enabled' if self.upload_to_blog else 'Disabled'}")
        logger.info("=" * 50)

        logger.info("Sending startup message...")
        self.send_message("Gemini Blogger bot started! Enter your question.")
        logger.info("Startup message sent, starting polling...")

        loop_errors = 0

        while True:
            try:
                updates = self.get_updates(offset=self.last_update_id + 1)

                for update in updates:
                    self.last_update_id = update["update_id"]

                    if "message" in update:
                        self.process_message(update["message"])

                loop_errors = 0

                # Adaptive wait based on consecutive failures
                if self.consecutive_failures > 5:
                    wait_time = min(self.consecutive_failures, 30)
                    time.sleep(wait_time)
                else:
                    time.sleep(1)

            except KeyboardInterrupt:
                logger.info("Bot stopping...")
                self.send_message("Bot stopped.")
                break
            except Exception as e:
                loop_errors += 1
                wait_time = min(5 * loop_errors, 60)
                logger.error(f"Error (waiting {wait_time}s): {e}")
                time.sleep(wait_time)


def main():
    parser = argparse.ArgumentParser(description="Telegram Gemini Blogger Bot")
    parser.add_argument("--test", action="store_true", help="Test mode (skip blog upload)")
    args = parser.parse_args()

    # Check environment variables
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        print("Error: Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env file.")
        sys.exit(1)

    # Run bot
    bot = TelegramGeminiBot(
        bot_token=bot_token,
        chat_id=chat_id,
        upload_to_blog=not args.test
    )

    bot.run()


if __name__ == "__main__":
    main()
