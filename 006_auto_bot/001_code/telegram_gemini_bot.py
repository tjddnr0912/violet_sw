#!/usr/bin/env python3
"""
Telegram Research Bot + WordPress Integration
---------------------------------------------
1. Receive messages from Telegram (polling)
2. Run deep research / Q&A via Claude + Gemini
3. Publish results to WordPress (grace-moon.com), category chosen at publish time
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
from shared.claude_search import (
    ClaudeSearchError,
    ClaudeSearchResponse,
)
from shared.web_search import web_search

# 스킬 파일 경로
QA_SKILL_FILE = os.path.expanduser('~/.claude/skills/telegram-qa/SKILL.md')


def load_qa_skill() -> str:
    """텔레그램 Q&A 스킬 파일 로드 (YAML frontmatter 제거)"""
    if not os.path.exists(QA_SKILL_FILE):
        raise FileNotFoundError(f"Telegram QA skill not found: {QA_SKILL_FILE}")

    with open(QA_SKILL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    content = re.sub(r'^---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL)
    return content.strip()


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
    """Telegram bot that processes messages with Gemini and publishes to WordPress"""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        upload_to_blog: bool = True
    ):
        super().__init__(bot_token, chat_id)
        self.upload_to_blog = upload_to_blog
        self.last_update_id = 0

        # Quick-mode opt-out command (deep research is the default)
        self.quick_command = os.getenv("RESEARCH_QUICK_COMMAND", "/quick")
        raw_rounds = os.getenv("RESEARCH_MAX_ROUNDS", "3")
        try:
            self.research_max_rounds = max(1, min(4, int(raw_rounds)))
        except ValueError:
            logger.warning(f"Invalid RESEARCH_MAX_ROUNDS={raw_rounds!r}, defaulting to 3")
            self.research_max_rounds = 3

        # Blog selection feature
        self.blogs = self._load_blog_configs()
        self.default_blog_key = os.getenv("DEFAULT_BLOG", "brave_ogu")
        self.selection_timeout = int(os.getenv("BLOG_SELECTION_TIMEOUT", "600"))  # 10 minutes

        # Pending uploads awaiting blog selection
        # key: message_id, value: {question, mode, created_at}
        # Research runs after blog selection (deferred), so md/html/title are not pre-stored.
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
        Run quick-mode research via Claude CLI + WebSearch.

        Migration history:
          - Pre 2026-05-27: subprocess `gemini -p` (deprecated by Google)
          - 2026-05-27 morning: google-genai API + grounding (3.x family)
          - 2026-05-27 evening: Claude CLI + WebSearch — Gemini 3.x grounding
            has a separate, tight quota bucket that hit 429 across all 3.x
            models even when API RPD usage was near zero. Claude WebSearch
            lives in a different quota bucket entirely.

        Method name is kept (`run_gemini`) for caller backward-compat — the
        outer Telegram flow doesn't care about the backend.

        Returns:
            Tuple[bool, str, str, list, list]: (success, content, title, labels, sources)
        """
        try:
            logger.info(f"Running Claude WebSearch (quick): {question[:50]}...")

            # Build prompt with skill + question
            skill_content = load_qa_skill()
            prompt = f"""{skill_content}

# 질문

{question}

---
[중요] 답변 본문 작성 완료 후 반드시 아래 3줄을 포함할 것 (코드블록 없이 플레인 텍스트로):
TITLE: (제목)
LABELS: (키워드 2-3개)
SOURCES: (출처)
"""

            # agy (Gemini) cascade primary; Claude (sonnet->haiku) fallback —
            # quick mode is single-shot Q&A, fallback keeps the prior behavior.
            response: ClaudeSearchResponse = web_search(
                prompt,
                model="sonnet",
                fallback_model="haiku",
                timeout=900,
            )

            output = (response.text or "").strip()
            if not output:
                logger.warning(
                    f"Claude WebSearch returned empty text (model={response.model_used})"
                )
                return False, "⚠️ Claude 응답이 비어있습니다. 잠시 후 다시 시도해주세요.", "", [], []

            logger.info(
                f"Claude WebSearch success (model={response.model_used}, "
                f"length={len(output)}, elapsed={response.elapsed_seconds:.1f}s, "
                f"auto_sources={len(response.sources)})"
            )
            logger.info(f"Claude response tail:\n{output[-500:]}")
            content, title, labels, sources = self._parse_response(output)

            # If the model didn't emit a SOURCES: trailer but Claude's
            # auto-extracted Sources footer carried URLs, surface those.
            if not sources and response.sources:
                sources = [{"title": uri, "url": uri} for uri in response.sources[:8]]

            logger.info(
                f"Parsed - title: {title}, labels: {labels}, "
                f"sources: {len(sources)}, content: {len(content)}"
            )
            return True, content, title, labels, sources

        except ClaudeSearchError as e:
            err = str(e)
            logger.error(f"Claude WebSearch error: {err}")
            return False, self._summarize_gemini_error(err), "", [], []
        except Exception as e:
            err = str(e)
            logger.error(f"Quick-mode execution error: {err}", exc_info=True)
            return False, self._summarize_gemini_error(err), "", [], []

    def _run_research_stage(
        self,
        question: str,
        message_id: Optional[int],
        mode: str,
    ) -> Tuple[bool, str, str, list, list, list]:
        """
        Unified research call. Returns the same shape regardless of mode,
        plus a contradictions list (empty in quick mode).

        Returns: (success, content, title, labels, sources, contradictions)
        """
        if mode == "quick":
            success, content, title, labels, sources = self.run_gemini(question)
            return success, content, title, labels, sources, []

        # mode == "deep"
        from shared.research_orchestrator import run_research, ResearchResult

        def progress(msg: str):
            if message_id:
                preview = question[:120] + ("…" if len(question) > 120 else "")
                self.edit_message_text(message_id, f"🔎 {msg}\n질문: {preview}")

        try:
            result: ResearchResult = run_research(
                question,
                max_rounds=self.research_max_rounds,
                progress_callback=progress,
            )
        except Exception as e:
            logger.error(f"run_research raised: {e}", exc_info=True)
            return False, f"⚠️ Deep research 오류: {str(e)[:300]}", "", [], [], []

        if result.rounds_completed == 0:
            return False, result.content, result.title, result.labels, result.sources, []

        return True, result.content, result.title, result.labels, result.sources, result.contradictions_noted

    @staticmethod
    def _summarize_gemini_error(stderr: str) -> str:
        """Summarize Gemini CLI stderr into a user-friendly message (max 500 chars)"""
        stderr_lower = stderr.lower()
        if "429" in stderr or "capacity" in stderr_lower or "rate" in stderr_lower:
            return "⚠️ Gemini 서버 용량 부족 (429). 잠시 후 다시 시도해주세요."
        if "401" in stderr or "unauthorized" in stderr_lower or "auth" in stderr_lower:
            return "⚠️ Gemini 인증 오류. API 키 또는 OAuth를 확인해주세요."
        if "403" in stderr or "forbidden" in stderr_lower:
            return "⚠️ Gemini 접근 거부 (403). 권한을 확인해주세요."
        if "500" in stderr or "internal" in stderr_lower:
            return "⚠️ Gemini 서버 내부 오류 (500). 잠시 후 다시 시도해주세요."
        # Fallback: truncate raw error
        short = stderr[:400].rsplit('\n', 1)[0] if '\n' in stderr[:400] else stderr[:400]
        return f"⚠️ Gemini 오류:\n{short}"

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
            labels = ["리서치", "분석"]
            logger.warning("LABELS not found, using default: ['리서치', '분석']")

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

    def process_message(self, message: dict) -> None:
        """Process received message"""
        text = message.get("text", "")
        chat = message.get("chat", {})

        # Only process allowed chat_id
        if str(chat.get("id")) != self.chat_id:
            logger.warning(f"Unauthorized chat_id: {chat.get('id')}")
            return

        # Slash commands like /start, /help, /status — but NOT the quick-mode command
        if text.startswith("/") and not self._is_quick_command(text):
            self._handle_command(text)
            return

        if not text:
            return

        # Mode classification: /quick = legacy single-shot; everything else = deep research
        if self._is_quick_command(text):
            question = self._strip_quick_prefix(text)
            if not question:
                self.send_message(f"Usage: {self.quick_command} <질문>")
                return
            mode = "quick"
        else:
            question = text
            mode = "deep"

        logger.info(f"Question received (mode={mode}, length={len(question)}): {question[:100]}{'...' if len(question) > 100 else ''}")

        # WordPress 발행: 항상 카테고리 선택 먼저 (업로드 OFF면 선택 없이 처리)
        if self.upload_to_blog:
            self._show_category_selection(question=question, mode=mode)
        else:
            self._process_and_upload_single(question=question, mode=mode)

    # WP 카테고리 (표시명, term_id) — 텔레그램 발행 선택용
    WP_CATEGORY_CHOICES = [
        ("뉴스", 5), ("일일시황", 6), ("섹터", 7), ("부동산", 8),
        ("SoC", 9), ("SW", 10), ("AI", 11), ("기타", 4),
    ]
    WP_CATEGORY_NAMES = {cid: name for name, cid in WP_CATEGORY_CHOICES}

    def _show_category_selection(self, question: str, mode: str = "deep") -> None:
        """질문 수신 직후 카테고리 선택 UI 표시. 선택한 카테고리로 WordPress에 발행."""
        # Build inline keyboard with WP categories (2개씩 한 줄)
        keyboard = []
        row = []
        for name, cid in self.WP_CATEGORY_CHOICES:
            row.append({"text": name, "callback_data": f"cat:{cid}"})
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)

        # Preview question
        question_preview = question[:200] + ('...' if len(question) > 200 else '')
        timeout_min = self.selection_timeout // 60

        mode_label = "🔎 Deep research" if mode == "deep" else "⚡ Quick"
        msg_text = f"""<b>Question received! ({mode_label})</b>

<b>Question:</b>
{question_preview}

<b>Select category to publish:</b>
(No selection in {timeout_min} min → publish cancelled)"""

        # Send message with inline keyboard
        result = self.send_message_with_inline_keyboard(
            text=msg_text,
            inline_keyboard=keyboard
        )

        if result.get("success"):
            message_id = result["message_id"]
            # Store pending with question only (research happens after selection)
            self.pending_uploads[message_id] = {
                "question": question,
                "mode": mode,
                "created_at": time.time()
            }
            logger.info(f"Category selection pending (msg_id: {message_id}, mode: {mode}, timeout: {timeout_min}min)")
        else:
            # Fallback to no-upload processing if keyboard send fails
            logger.warning("Failed to send selection UI, processing without upload")
            self._process_and_upload_single(question=question, mode=mode)

    def _process_and_upload_single(
        self,
        question: str,
        message_id: Optional[int] = None,
        mode: str = "deep",
    ) -> None:
        """Process question and upload to the single available blog (single-blog mode)."""
        opening = "🔎 Deep research 시작…" if mode == "deep" else "⚡ Asking Gemini…"
        if message_id:
            self.edit_message_text(message_id, opening)
        else:
            init = self.send_message(opening)
            if isinstance(init, dict):
                message_id = init.get("message_id")

        success, content, title_hint, labels, sources, contradictions = \
            self._run_research_stage(question, message_id, mode)

        if not success:
            err = content[:4000]
            if message_id:
                self.edit_message_text(message_id, err)
            else:
                self.send_message(err)
            return

        if message_id:
            self.edit_message_text(message_id, "Claude HTML 생성 중…")

        # Contradictions section (if any) goes BEFORE the References block
        if contradictions:
            content += "\n\n## 라운드 간 모순\n" + "\n".join(f"- {c}" for c in contradictions)
        sources_section = self._format_sources_section(sources)
        full_md_content = content + sources_section

        # 카테고리 미선택 경로(업로드 OFF/테스트) — 기본 '기타'(4)
        self._finalize_and_upload(
            category_id=4,
            full_md_content=full_md_content,
            title_hint=title_hint,
            labels=labels,
            sources=sources,
            message_id=message_id,
        )

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

        # Parse callback data (cat:<term_id>)
        if not data.startswith("cat:"):
            self.answer_callback_query(callback_id, "Unknown action")
            return

        try:
            category_id = int(data.split(":", 1)[1])
        except ValueError:
            self.answer_callback_query(callback_id, "Invalid category")
            return

        # Check if pending data exists
        if message_id not in self.pending_uploads:
            self.answer_callback_query(callback_id, "Expired or already processed", show_alert=True)
            return

        pending = self.pending_uploads.pop(message_id)
        cat_name = self.WP_CATEGORY_NAMES.get(category_id, str(category_id))
        self.answer_callback_query(callback_id, f"Publishing to '{cat_name}'...")
        self._process_after_selection(
            question=pending["question"],
            category_id=category_id,
            message_id=message_id,
            mode=pending.get("mode", "deep"),
        )

    def _process_after_selection(
        self,
        question: str,
        category_id: int,
        message_id: int,
        mode: str = "deep",
    ) -> None:
        """Process question after category selection (research → Claude HTML → WP 발행)."""
        opening = "🔎 Deep research 시작…" if mode == "deep" else "⚡ Asking Gemini…"
        self.edit_message_text(message_id, opening)
        logger.info(f"Processing after selection (category={category_id}, mode={mode})")

        success, content, title_hint, labels, sources, contradictions = \
            self._run_research_stage(question, message_id, mode)

        if not success:
            self.edit_message_text(message_id, content[:4000])
            return

        # Contradictions section (if any) goes BEFORE the References block
        if contradictions:
            content += "\n\n## 라운드 간 모순\n" + "\n".join(f"- {c}" for c in contradictions)
        sources_section = self._format_sources_section(sources)
        full_md_content = content + sources_section

        # 한글 HTML 생성 → 로컬 저장(백업) → WP 발행 → 통지
        self._finalize_and_upload(
            category_id=category_id,
            full_md_content=full_md_content,
            title_hint=title_hint,
            labels=labels,
            sources=sources,
            message_id=message_id,
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
            logger.info(f"Selection timeout, upload cancelled (msg_id: {message_id}, mode: {pending.get('mode', 'deep')})")
            # 무선택 시 업로드하지 않는다(기존 default 자동 업로드 폐지).
            self.edit_message_text(
                message_id,
                "<b>Selection timed out</b>\n\nNo category selected → publish cancelled.",
            )

    def _finalize_and_upload(
        self,
        category_id: int,
        full_md_content: str,
        title_hint: str,
        labels: list,
        sources: list,
        message_id: Optional[int],
    ) -> None:
        """발행 워크플로우 (WordPress, 한글 그대로).

        1) 한글 본문 HTML 생성(저자 박스 미적용).
        2) 저자 박스(GraceMoon) 적용.
        3) 로컬 백업 저장(저자 박스까지 — raw 원문은 더 이상 첨부하지 않음).
        4) 선택한 카테고리로 WordPress 발행(다이어그램 PNG·광고 제거는 업로더가 처리).
        """
        from shared.claude_html_converter import convert_md_to_html_via_claude

        if message_id:
            self.edit_message_text(message_id, "Claude HTML 생성 중…")

        body_ko = None
        claude_title = ""
        try:
            body_ko, claude_title = convert_md_to_html_via_claude(
                full_md_content, apply_editorial_box=False
            )
        except Exception as e:
            logger.warning(f"Claude HTML failed: {e}")
        final_title = claude_title or title_hint

        upload_html = None
        if body_ko:
            from shared.editorial import apply_editorial
            # 저자 박스(GraceMoon) 적용 (raw·광고·다이어그램은 WordPressUploader가 처리)
            upload_html = apply_editorial(
                body_ko, author_key="research", content_type="research"
            )

        if message_id:
            self.edit_message_text(message_id, "Publishing to WordPress…")
        self._upload_single(
            category_id=category_id,
            md_content=full_md_content,
            html_content=upload_html,
            title=final_title,
            labels=labels,
            sources=sources,
            message_id=message_id,
        )

    def _upload_single(
        self,
        category_id: int,
        md_content: str,
        html_content: Optional[str],
        title: str,
        labels: list,
        sources: list,
        message_id: Optional[int] = None,
    ) -> None:
        """선택한 카테고리로 WordPress에 발행(HTML)."""
        cat_name = self.WP_CATEGORY_NAMES.get(category_id, str(category_id))

        if not self.upload_to_blog:
            result_msg = f"<b>Test mode - publish skipped</b>\n\nTitle: {title}"
            if message_id:
                self.edit_message_text(message_id, result_msg)
            else:
                self.send_message(result_msg)
            return

        # 공개용: HTML만 업로드(raw 마크다운 섹션은 붙이지 않음)
        if html_content:
            upload_content = html_content
            is_markdown = False
        else:
            upload_content = md_content
            is_markdown = True

        success, url = self._do_upload(
            category_id=category_id,
            title=title,
            content=upload_content,
            labels=labels,
            is_markdown=is_markdown
        )

        if success:
            result_msg = f"""<b>WordPress 발행 완료!</b>

<b>Category:</b> {cat_name}
<b>Title:</b> {title}
<b>URL:</b> {url}"""
        else:
            result_msg = f"""<b>발행 실패</b>

<b>Category:</b> {cat_name}
<b>Error:</b> {url}"""

        if message_id:
            self.edit_message_text(message_id, result_msg)
        else:
            self.send_message(result_msg)

        logger.info(f"WP publish to '{cat_name}' {'success' if success else 'failed'}: {title}")

    def _do_upload(
        self,
        category_id: int,
        title: str,
        content: str,
        labels: list,
        is_markdown: bool = False
    ) -> Tuple[bool, str]:
        """WordPress 발행 수행 (선택한 카테고리)."""
        try:
            from shared.wordpress_uploader import WordPressUploader

            is_draft = os.getenv("WORDPRESS_DEFAULT_STATUS", "publish").lower() == "draft"

            if not labels:
                labels = ["AI"]

            uploader = WordPressUploader(
                default_categories=[category_id],
                strip_ads_default=True,
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
            return False, "wordpress_uploader module not found"
        except Exception as e:
            return False, f"Upload error: {str(e)}"

    def _handle_command(self, command: str) -> None:
        """Handle bot commands"""
        cmd = command.split()[0].lower()

        if cmd == "/start":
            self.send_message("""<b>GraceMoon Research Bot</b>

Enter a question and:
1. Deep research (Gemini + Claude 검증)
2. Select category → publish to WordPress
3. Notification via Telegram

<b>Commands:</b>
/help - Help
/status - Status check""")

        elif cmd == "/help":
            self.send_message(f"""<b>Usage</b>
- 기본 (Deep research): 그냥 메시지 입력 → 다라운드 Gemini + Claude 검증 (~1~5min)
- 빠른 답변 (Quick): <code>{self.quick_command} 질문</code> → 단발 Gemini (~30s, quota 절약)

Examples:
- 티스토리 API 종료 이후 자동 포스팅 현황    ← Deep 모드 (기본)
- {self.quick_command} What is list comprehension in Python?    ← Quick 모드""")

        elif cmd == "/status":
            upload_status = "Enabled" if self.upload_to_blog else "Test mode"
            cats = ", ".join(name for name, _ in self.WP_CATEGORY_CHOICES)
            pending_count = len(self.pending_uploads)
            self.send_message(f"""<b>Bot Status</b>
- Default mode: Deep research (multi-round)
- Quick opt-out: {self.quick_command}
- Deep max rounds: {self.research_max_rounds}
- WordPress publish: {upload_status}
- Categories: {cats}
- Selection timeout: {self.selection_timeout // 60} min
- Pending selections: {pending_count}
- Last update ID: {self.last_update_id}""")

        else:
            self.send_message(f"Unknown command: {cmd}")

    def _is_quick_command(self, text: str) -> bool:
        return text.startswith(self.quick_command + " ") or text.strip() == self.quick_command

    def _strip_quick_prefix(self, text: str) -> str:
        return text.strip()[len(self.quick_command):].strip()

    def run(self) -> None:
        """Bot main loop"""
        logger.info("=" * 50)
        logger.info("Telegram Research Bot (WordPress) started")
        logger.info(f"WordPress publish: {'Enabled' if self.upload_to_blog else 'Disabled'}")
        logger.info(f"Categories: {', '.join(n for n, _ in self.WP_CATEGORY_CHOICES)}")
        logger.info(f"Selection timeout: {self.selection_timeout}s")
        logger.info("=" * 50)

        logger.info("Sending startup message...")
        self.send_message("Research bot started! Enter your question.")
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
    parser = argparse.ArgumentParser(description="Telegram Research Bot (WordPress)")
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
