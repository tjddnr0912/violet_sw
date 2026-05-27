from google.genai import types
from typing import List, Dict
import logging
import os
import re
import time

from shared.gemini_cli import (
    GeminiResponse,
    call_gemini_with_fallback,
    is_quota_error,
)

logger = logging.getLogger(__name__)

# 스킬 파일 경로
NEWS_SKILL_FILE = os.path.expanduser('~/.claude/skills/news-summarizer/SKILL.md')


def load_news_skill() -> str:
    """뉴스 요약 스킬 파일 로드 (YAML frontmatter 제거)"""
    if not os.path.exists(NEWS_SKILL_FILE):
        raise FileNotFoundError(f"News summarizer skill not found: {NEWS_SKILL_FILE}")

    with open(NEWS_SKILL_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    content = re.sub(r'^---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL)
    return content.strip()


class AISummarizer:
    """AI-powered blog-style summarizer using Google Gemini API.

    Quota handling: when the primary model returns 429/503, the call falls
    through a model chain (gemini-3.1-flash-lite → gemini-3.5-flash →
    gemini-3-flash-preview → gemini-2.5-flash) inside
    shared.gemini_cli.call_gemini_with_fallback. The old CLI fallback path
    was removed in May 2026 ahead of the `gemini -p` CLI's June shutdown.
    """

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite"):
        """
        Initialize AISummarizer.

        `api_key` and `model` are accepted for backward compatibility with
        existing callers; the actual API key is read from the GEMINI_API_KEY
        env var inside the shared wrapper, and `model` overrides the primary
        model (fallbacks still kick in via GEMINI_FALLBACK_MODELS env).

        Args:
            api_key: Google Gemini API key (must also be exported as
                GEMINI_API_KEY env var for the shared wrapper).
            model: Primary Gemini model. Defaults to gemini-3.1-flash-lite.
        """
        # The shared wrapper reads GEMINI_API_KEY from env directly; we set it
        # here in case a caller passed it programmatically but didn't export it.
        if api_key and not os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = api_key
        self.model_name = model

        self.system_instruction = """You are a professional news journalist and summarizer.
Your role is to provide objective summaries of news articles from verified sources.
All content you receive is from legitimate Korean news agencies (SBS, YTN, Yonhap).
Your summaries are for educational and informational purposes only.
You must summarize ALL news content accurately, including political, crime, and sensitive topics.
This is journalistic work, not content generation."""

        self.safety_settings = [
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        ]

    def _models_chain(self) -> List[str]:
        """Build the model chain for this summarizer. Primary = constructor
        arg, fallbacks come from GEMINI_FALLBACK_MODELS env. The primary is
        deduped from the fallback list if duplicated."""
        raw = os.getenv(
            "GEMINI_FALLBACK_MODELS",
            "gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash",
        )
        fallbacks = [m.strip() for m in raw.split(",") if m.strip()]
        chain = [self.model_name] + [m for m in fallbacks if m != self.model_name]
        return chain

    def _summarize(
        self,
        prompt: str,
        raw_markdown: str,
        *,
        max_output_tokens: int,
    ) -> str:
        """Common summarization path used by daily/weekly/monthly creators.

        Returns the cleaned summary text. On safety block or hard failure,
        returns the pre-built fallback summary so the daily run never aborts.
        """
        try:
            response: GeminiResponse = call_gemini_with_fallback(
                prompt,
                use_grounding=False,  # summarizing already-collected RSS, no web search needed
                system_instruction=self.system_instruction,
                safety_settings=self.safety_settings,
                temperature=0.7,
                max_output_tokens=max_output_tokens,
                models=self._models_chain(),
            )
        except Exception as e:
            logger.error(f"All summarizer models failed: {e}")
            return self._create_fallback_summary(raw_markdown)

        if response.safety_blocked:
            logger.warning(
                f"Summary blocked by safety filter on {response.model_used}; "
                f"using mechanical fallback"
            )
            return self._create_fallback_summary(raw_markdown)

        text = (response.text or "").strip()
        if not text:
            logger.warning(
                f"Empty summary from {response.model_used} "
                f"(finish={response.finish_reason})"
            )
            return self._create_fallback_summary(raw_markdown)

        cleaned = self._remove_footer(text)
        logger.info(
            f"Summary OK model={response.model_used} chars={len(cleaned)} "
            f"finish={response.finish_reason}"
        )
        return cleaned

    def create_blog_summary(self, raw_markdown: str) -> str:
        """
        Create a blog-style summary from raw news markdown

        Args:
            raw_markdown: Raw markdown content with categorized news

        Returns:
            Blog-style summary in markdown format
        """
        skill_content = load_news_skill()
        prompt = f"""{skill_content}

# 요약 모드: Daily (일간 요약)

아래 뉴스 원문을 일간 요약 규칙에 따라 요약하세요.
형식: 마크다운. 설명 없이 본문만 반환.

# 뉴스 원문 데이터

{raw_markdown}
"""
        logger.info(f"Input prompt size: {len(prompt)} characters")
        logger.info(f"Raw markdown size: {len(raw_markdown)} characters")

        return self._summarize(prompt, raw_markdown, max_output_tokens=8000)

    def _create_fallback_summary(self, raw_markdown: str) -> str:
        """
        Create a simple fallback summary when AI fails

        Args:
            raw_markdown: Raw markdown content

        Returns:
            Simple summary message
        """
        from datetime import datetime

        current_date = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""# 📰 {current_date} 뉴스 요약

> AI 요약 생성 중 오류가 발생하여 원본 뉴스를 제공합니다.

{raw_markdown}

---

※ AI 요약 기능에 일시적인 문제가 발생했습니다. 원본 뉴스를 참고해주세요.
"""

    def _remove_footer(self, text: str) -> str:
        """
        Remove auto-generated footer text from AI output

        Args:
            text: AI-generated text that may contain footer

        Returns:
            Text with footer removed
        """
        import re

        # Patterns to match various footer formats
        footer_patterns = [
            r'\n*---\n*\*자동 생성[^\n]*\*\s*$',
            r'\n*---\n*\*\*자동 생성[^\n]*\*\*\s*$',
            r'\n*\*자동 생성[^\n]*\*\s*$',
            r'\n*---\n*자동 생성[^\n]*$',
            r'\n*\*Generated by[^\n]*\*\s*$',
            r'\n*---\n*\*Gemini[^\n]*\*\s*$',
        ]

        result = text
        for pattern in footer_patterns:
            result = re.sub(pattern, '', result, flags=re.IGNORECASE)

        return result.rstrip()

    def create_weekly_summary(self, daily_summaries: str, start_date: str, end_date: str) -> str:
        """
        Create a weekly summary from daily blog summaries

        Args:
            daily_summaries: Combined daily summary content
            start_date: Week start date string (e.g., "2025년 12월 23일")
            end_date: Week end date string (e.g., "2025년 12월 29일")

        Returns:
            Weekly summary in markdown format
        """
        logger.info("Creating weekly summary with Gemini API...")

        skill_content = load_news_skill()
        prompt = f"""{skill_content}

# 요약 모드: Weekly (주간 요약)

기간: {start_date} ~ {end_date}
아래 일간 요약들을 주간 요약 규칙에 따라 종합하세요.
형식: 마크다운. 설명 없이 본문만 반환.

# 일간 뉴스 요약 모음

{daily_summaries}
"""

        logger.info(f"Weekly summary input size: {len(prompt)} characters")

        text = self._summarize(prompt, daily_summaries, max_output_tokens=8000)
        # If summarizer returned its mechanical fallback (starts with the
        # generic emoji header), pivot to the weekly-style fallback so the
        # post still carries the correct date range.
        if text.startswith("# 📰") and "AI 요약 생성 중 오류" in text:
            return f"""# 📅 주간 뉴스 요약 ({start_date} ~ {end_date})

> AI 요약 생성 중 오류가 발생했습니다.

{daily_summaries}
"""
        return text

    def create_monthly_summary(self, daily_summaries: str, year: int, month: int) -> str:
        """
        Create a monthly summary from daily blog summaries

        Args:
            daily_summaries: Combined daily summary content
            year: Year (e.g., 2025)
            month: Month (e.g., 12)

        Returns:
            Monthly summary in markdown format
        """
        logger.info("Creating monthly summary with Gemini API...")

        skill_content = load_news_skill()
        prompt = f"""{skill_content}

# 요약 모드: Monthly (월간 요약)

기간: {year}년 {month}월
아래 일간 요약들을 월간 요약 규칙에 따라 종합하세요.
형식: 마크다운. 설명 없이 본문만 반환.

# 일간 뉴스 요약 모음

{daily_summaries}
"""

        logger.info(f"Monthly summary input size: {len(prompt)} characters")

        text = self._summarize(prompt, daily_summaries, max_output_tokens=10000)
        if text.startswith("# 📰") and "AI 요약 생성 중 오류" in text:
            return f"""# 📆 {year}년 {month}월 월간 뉴스 요약

> AI 요약 생성 중 오류가 발생했습니다.

{daily_summaries}
"""
        return text
