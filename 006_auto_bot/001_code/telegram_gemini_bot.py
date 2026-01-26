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
import json
from datetime import datetime
from typing import Optional, Tuple, Dict, List
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

        # Blog selection feature
        self.blogs = self._load_blog_configs()
        self.default_blog_key = os.getenv("DEFAULT_BLOG", "brave_ogu")
        self.selection_timeout = int(os.getenv("BLOG_SELECTION_TIMEOUT", "600"))  # 10 minutes

        # Pending uploads awaiting blog selection
        # key: message_id, value: {md_content, html_content, title, labels, sources, created_at}
        self.pending_uploads: Dict[int, Dict] = {}

    def _load_blog_configs(self) -> Dict[str, Dict]:
        """Load blog configurations from .env BLOG_LIST JSON"""
        blogs = {}

        # Try loading from BLOG_LIST JSON
        blog_list_json = os.getenv("BLOG_LIST")
        if blog_list_json:
            try:
                blog_list = json.loads(blog_list_json)
                for blog in blog_list:
                    key = blog.get("key")
                    if key:
                        blogs[key] = {
                            "id": blog.get("id"),
                            "name": blog.get("name", key)
                        }
                logger.info(f"Loaded {len(blogs)} blogs from BLOG_LIST")
            except json.JSONDecodeError as e:
                logger.warning(f"BLOG_LIST JSON parsing failed: {e}")

        # Fallback to individual env vars if BLOG_LIST not set
        if not blogs:
            if os.getenv("BLOGGER_BLOG_ID"):
                blogs["brave_ogu"] = {
                    "id": os.getenv("BLOGGER_BLOG_ID"),
                    "name": "Brave Ogu"
                }
            logger.info("Using single blog from BLOGGER_BLOG_ID")

        return blogs

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

**Length Requirement (CRITICAL):**
- The article MUST be at least 1500 characters (excluding TITLE/LABELS/SOURCES metadata)
- If the topic is simple, expand with:
  - Related background information
  - Practical examples and use cases
  - Common mistakes and tips
  - Comparisons with alternatives
- Do NOT pad with repetitive or meaningless content. Add genuinely useful information.

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

        # If multiple blogs configured, show selection UI first (before Gemini processing)
        if len(self.blogs) > 1 and self.upload_to_blog:
            self._show_blog_selection_first(question=text)
        else:
            # Single blog mode - process and upload directly
            self._process_and_upload_single(question=text)

    def _show_blog_selection_first(self, question: str) -> None:
        """Show blog selection UI immediately after receiving question"""
        # Build inline keyboard (exclude default blog from selection)
        keyboard = []
        row = []
        for key, blog in self.blogs.items():
            if key == self.default_blog_key:
                continue
            row.append({
                "text": f"{blog['name']}",
                "callback_data": f"blog:{key}"
            })
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # Add "Default only" button
        keyboard.append([{
            "text": "Default only",
            "callback_data": "blog:default_only"
        }])

        # Preview question
        question_preview = question[:200] + ('...' if len(question) > 200 else '')
        timeout_min = self.selection_timeout // 60
        default_blog_name = self.blogs.get(self.default_blog_key, {}).get("name", "Default")

        msg_text = f"""<b>Question received!</b>

<b>Question:</b>
{question_preview}

<b>Select blog to upload:</b>
(Auto-upload to {default_blog_name} only after {timeout_min} min)"""

        # Send message with inline keyboard
        result = self.send_message_with_inline_keyboard(
            text=msg_text,
            inline_keyboard=keyboard
        )

        if result.get("success"):
            message_id = result["message_id"]
            # Store pending with question only (Gemini processing happens after selection)
            self.pending_uploads[message_id] = {
                "question": question,
                "created_at": time.time()
            }
            logger.info(f"Blog selection pending (msg_id: {message_id}, timeout: {timeout_min}min)")
        else:
            # Fallback to default processing if keyboard send fails
            logger.warning("Failed to send selection UI, processing with default only")
            self._process_and_upload_single(question=question)

    def _process_and_upload_single(self, question: str, message_id: Optional[int] = None) -> None:
        """Process question and upload to default blog only (single blog mode)"""
        # Update status
        if message_id:
            self.edit_message_text(message_id, "Processing: Asking Gemini...")
        else:
            self.send_message("Processing: Asking Gemini...")

        # Run Gemini
        success, gemini_content, gemini_title, gemini_labels, gemini_sources = self.run_gemini(question)

        if not success:
            error_msg = f"Gemini error: {gemini_content}"
            if message_id:
                self.edit_message_text(message_id, error_msg)
            else:
                self.send_message(error_msg)
            return

        # Update status
        if message_id:
            self.edit_message_text(message_id, "Processing: Claude HTML conversion...")

        # Prepare content
        sources_section = self._format_sources_section(gemini_sources)
        full_md_content = gemini_content + sources_section

        # Convert to HTML
        html_content = None
        try:
            from shared.claude_html_converter import convert_md_to_html_via_claude
            html_content = convert_md_to_html_via_claude(full_md_content)
        except Exception as e:
            logger.warning(f"Claude CLI failed: {e}")

        # Upload to default only
        self._upload_default_only(
            md_content=full_md_content,
            html_content=html_content,
            title=gemini_title,
            labels=gemini_labels,
            sources=gemini_sources,
            message_id=message_id
        )

    def _show_blog_selection(
        self,
        md_content: str,
        html_content: Optional[str],
        title: str,
        labels: list,
        sources: list
    ) -> None:
        """Show blog selection inline keyboard"""
        # Build inline keyboard (exclude default blog from selection)
        keyboard = []
        row = []
        for key, blog in self.blogs.items():
            if key == self.default_blog_key:
                continue  # Skip default blog in selection
            row.append({
                "text": f"{blog['name']}",
                "callback_data": f"blog:{key}"
            })
            if len(row) == 2:  # 2 buttons per row
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # Add "Default only" button
        keyboard.append([{
            "text": "Default only",
            "callback_data": "blog:default_only"
        }])

        # Preview message
        labels_str = ', '.join(labels) if labels else '-'
        preview = md_content[:300] + ('...' if len(md_content) > 300 else '')
        preview = HtmlUtils.fix_unclosed_tags(preview)
        timeout_min = self.selection_timeout // 60

        default_blog_name = self.blogs.get(self.default_blog_key, {}).get("name", "Default")
        msg_text = f"""<b>Gemini response complete!</b>

<b>Title:</b> {title}
<b>Labels:</b> {labels_str}

<b>Select additional blog to upload:</b>
(Auto-upload to {default_blog_name} only after {timeout_min} minutes)

<b>Preview:</b>
{preview}"""

        # Send message with inline keyboard
        result = self.send_message_with_inline_keyboard(
            text=msg_text,
            inline_keyboard=keyboard
        )

        if result.get("success"):
            message_id = result["message_id"]
            # Store pending upload data
            self.pending_uploads[message_id] = {
                "md_content": md_content,
                "html_content": html_content,
                "title": title,
                "labels": labels,
                "sources": sources,
                "created_at": time.time()
            }
            logger.info(f"Blog selection pending (msg_id: {message_id}, timeout: {timeout_min}min)")
        else:
            # Fallback to default upload if keyboard send fails
            logger.warning("Failed to send selection UI, uploading to default only")
            self._upload_default_only(md_content, html_content, title, labels, sources)

    def _handle_callback_query(self, callback_query: dict) -> None:
        """Handle inline keyboard button click"""
        callback_id = callback_query["id"]
        data = callback_query.get("data", "")
        message = callback_query.get("message", {})
        message_id = message.get("message_id")

        # Verify user authorization
        from_user = callback_query.get("from", {})
        if str(from_user.get("id")) != self.chat_id:
            self.answer_callback_query(callback_id, "Unauthorized", show_alert=True)
            return

        # Parse callback data
        if not data.startswith("blog:"):
            self.answer_callback_query(callback_id, "Unknown action")
            return

        blog_key = data.split(":", 1)[1]

        # Check if pending data exists
        if message_id not in self.pending_uploads:
            self.answer_callback_query(callback_id, "Expired or already processed", show_alert=True)
            return

        pending = self.pending_uploads.pop(message_id)

        # Acknowledge button click
        self.answer_callback_query(callback_id, "Processing started...")

        # Now process the question (Gemini + Claude + Upload)
        self._process_after_selection(
            question=pending["question"],
            blog_key=blog_key,
            message_id=message_id
        )

    def _process_after_selection(
        self,
        question: str,
        blog_key: str,
        message_id: int
    ) -> None:
        """Process question after blog selection (Gemini → Claude → Upload)"""
        # Step 1: Gemini
        self.edit_message_text(message_id, "Processing: Asking Gemini...")
        logger.info(f"Processing question after selection (blog: {blog_key})")

        success, gemini_content, gemini_title, gemini_labels, gemini_sources = self.run_gemini(question)

        if not success:
            self.edit_message_text(message_id, f"Gemini error: {gemini_content}")
            return

        # Step 2: Claude HTML conversion
        self.edit_message_text(message_id, "Processing: Claude에서 HTML을 생성 중...")

        sources_section = self._format_sources_section(gemini_sources)
        full_md_content = gemini_content + sources_section

        html_content = None
        try:
            from shared.claude_html_converter import convert_md_to_html_via_claude
            html_content = convert_md_to_html_via_claude(full_md_content)
            logger.info(f"Claude HTML conversion complete ({len(html_content)} chars)")
        except Exception as e:
            logger.warning(f"Claude CLI failed: {e}")

        # Step 3: Upload
        self.edit_message_text(message_id, "Processing: Uploading to blog...")

        if blog_key == "default_only":
            self._upload_default_only(
                md_content=full_md_content,
                html_content=html_content,
                title=gemini_title,
                labels=gemini_labels,
                sources=gemini_sources,
                message_id=message_id
            )
        else:
            self._upload_dual(
                blog_key=blog_key,
                md_content=full_md_content,
                html_content=html_content,
                title=gemini_title,
                labels=gemini_labels,
                sources=gemini_sources,
                message_id=message_id
            )

    def _check_pending_timeouts(self) -> None:
        """Check and process timed out pending uploads"""
        current_time = time.time()
        expired_ids = []

        for message_id, pending in self.pending_uploads.items():
            elapsed = current_time - pending["created_at"]
            if elapsed >= self.selection_timeout:
                expired_ids.append(message_id)

        for message_id in expired_ids:
            pending = self.pending_uploads.pop(message_id)
            logger.info(f"Selection timeout, processing with default only (msg_id: {message_id})")

            # Process with default_only (question based)
            self._process_after_selection(
                question=pending["question"],
                blog_key="default_only",
                message_id=message_id
            )

    def _upload_default_only(
        self,
        md_content: str,
        html_content: Optional[str],
        title: str,
        labels: list,
        sources: list,
        message_id: Optional[int] = None,
        is_timeout: bool = False
    ) -> None:
        """Upload to default blog only (HTML + original markdown)"""
        if not self.upload_to_blog:
            result_msg = f"<b>Test mode - upload skipped</b>\n\nTitle: {title}"
            if message_id:
                self.edit_message_text(message_id, result_msg)
            else:
                self.send_message(result_msg)
            return

        default_blog = self.blogs.get(self.default_blog_key)
        if not default_blog:
            logger.error(f"Default blog '{self.default_blog_key}' not found")
            return

        # Prepare content: HTML + original section
        if html_content:
            original_section = self._create_original_section(md_content)
            upload_content = f"{html_content}\n{original_section}"
            is_markdown = False
        else:
            upload_content = md_content
            is_markdown = True

        # Upload
        success, url = self._do_upload(
            blog_id=default_blog["id"],
            title=title,
            content=upload_content,
            labels=labels,
            is_markdown=is_markdown
        )

        timeout_notice = " (auto-upload after timeout)" if is_timeout else ""
        if success:
            result_msg = f"""<b>Blog upload complete!{timeout_notice}</b>

<b>Blog:</b> {default_blog['name']}
<b>Title:</b> {title}
<b>URL:</b> {url}"""
        else:
            result_msg = f"""<b>Upload failed{timeout_notice}</b>

<b>Blog:</b> {default_blog['name']}
<b>Error:</b> {url}"""

        if message_id:
            self.edit_message_text(message_id, result_msg)
        else:
            self.send_message(result_msg)

        logger.info(f"Default upload {'success' if success else 'failed'}: {title}")

    def _upload_dual(
        self,
        blog_key: str,
        md_content: str,
        html_content: Optional[str],
        title: str,
        labels: list,
        sources: list,
        message_id: Optional[int] = None
    ) -> None:
        """Upload to both default blog and selected blog"""
        if not self.upload_to_blog:
            result_msg = f"<b>Test mode - upload skipped</b>\n\nTitle: {title}"
            if message_id:
                self.edit_message_text(message_id, result_msg)
            else:
                self.send_message(result_msg)
            return

        default_blog = self.blogs.get(self.default_blog_key)
        selected_blog = self.blogs.get(blog_key)

        if not default_blog or not selected_blog:
            logger.error(f"Blog not found: default={self.default_blog_key}, selected={blog_key}")
            return

        results = []

        # 1. Upload to default blog: HTML + original section
        if html_content:
            original_section = self._create_original_section(md_content)
            default_content = f"{html_content}\n{original_section}"
            default_is_md = False
        else:
            default_content = md_content
            default_is_md = True

        success1, url1 = self._do_upload(
            blog_id=default_blog["id"],
            title=title,
            content=default_content,
            labels=labels,
            is_markdown=default_is_md
        )
        results.append((default_blog["name"], success1, url1, "HTML + Raw"))

        # 2. Upload to selected blog: HTML only (no original section)
        if html_content:
            selected_content = html_content
            selected_is_md = False
        else:
            selected_content = md_content
            selected_is_md = True

        success2, url2 = self._do_upload(
            blog_id=selected_blog["id"],
            title=title,
            content=selected_content,
            labels=labels,
            is_markdown=selected_is_md
        )
        results.append((selected_blog["name"], success2, url2, "HTML only"))

        # Build result message
        result_lines = ["<b>Dual upload complete!</b>", f"\n<b>Title:</b> {title}\n"]
        for blog_name, success, url, content_type in results:
            status = "OK" if success else "FAILED"
            if success:
                result_lines.append(f"<b>{blog_name}</b> ({content_type}): {url}")
            else:
                result_lines.append(f"<b>{blog_name}</b> ({content_type}): {status} - {url}")

        result_msg = "\n".join(result_lines)

        if message_id:
            self.edit_message_text(message_id, result_msg)
        else:
            self.send_message(result_msg)

        logger.info(f"Dual upload: default={'OK' if success1 else 'FAIL'}, selected={'OK' if success2 else 'FAIL'}")

    def _do_upload(
        self,
        blog_id: str,
        title: str,
        content: str,
        labels: list,
        is_markdown: bool = False
    ) -> Tuple[bool, str]:
        """Perform actual blog upload"""
        try:
            from shared.blogger_uploader import BloggerUploader

            credentials_path = os.getenv("BLOGGER_CREDENTIALS_PATH", "./credentials/blogger_credentials.json")
            token_path = os.getenv("BLOGGER_TOKEN_PATH", "./credentials/blogger_token.pkl")
            is_draft = os.getenv("BLOGGER_IS_DRAFT", "false").lower() == "true"

            if not labels:
                labels = ["AI", "Gemini"]

            uploader = BloggerUploader(
                blog_id=blog_id,
                credentials_path=credentials_path,
                token_path=token_path
            )

            result = uploader.upload_post(
                title=title,
                content=content,
                labels=labels,
                is_draft=is_draft,
                is_markdown=is_markdown
            )

            if result.get("success"):
                return True, result.get("url", "URL not available")
            else:
                return False, result.get("message", "Upload failed")

        except ImportError:
            return False, "blogger_uploader module not found"
        except Exception as e:
            return False, f"Upload error: {str(e)}"

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
            blogs_list = "\n".join([f"  - {k}: {v['name']}" for k, v in self.blogs.items()])
            pending_count = len(self.pending_uploads)
            self.send_message(f"""<b>Bot Status</b>
- Blog upload: {upload_status}
- Blogs configured: {len(self.blogs)}
{blogs_list}
- Default blog: {self.default_blog_key}
- Selection timeout: {self.selection_timeout // 60} min
- Pending selections: {pending_count}
- Last update ID: {self.last_update_id}""")

        else:
            self.send_message(f"Unknown command: {cmd}")

    def run(self) -> None:
        """Bot main loop"""
        logger.info("=" * 50)
        logger.info("Telegram Gemini Blogger Bot started")
        logger.info(f"Blogger upload: {'Enabled' if self.upload_to_blog else 'Disabled'}")
        logger.info(f"Blogs configured: {len(self.blogs)} ({', '.join(self.blogs.keys())})")
        logger.info(f"Default blog: {self.default_blog_key}")
        logger.info(f"Selection timeout: {self.selection_timeout}s")
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

                    # Handle callback query (inline keyboard button click)
                    if "callback_query" in update:
                        self._handle_callback_query(update["callback_query"])

                # Check for pending upload timeouts
                self._check_pending_timeouts()

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
