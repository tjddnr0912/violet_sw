from google import genai
from google.genai import types
from typing import List, Dict
import logging
import os
import re
import time

from shared.gemini_cli import is_quota_error, call_gemini_cli

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
    """AI-powered blog-style summarizer using Google Gemini API"""

    def __init__(self, api_key: str, model: str = "gemini-3.1-flash-lite-preview"):
        """
        Initialize AISummarizer

        Args:
            api_key: Google Gemini API key
            model: Google Gemini model to use
        """
        self.client = genai.Client(api_key=api_key)
        self.model_name = model
        self._use_cli_fallback = False  # flips to True after first quota error

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

        # CLI fallback path: skip API entirely once quota was hit
        if self._use_cli_fallback:
            return self._summarize_via_cli(prompt, raw_markdown)

        try:
            logger.info("Calling Gemini API with safety OFF for verified news journalism...")

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.7,
                    max_output_tokens=8000,
                    safety_settings=self.safety_settings,
                ),
            )

            # Check if response has valid content
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]

                # Log detailed response info for debugging
                logger.info(f"Gemini finish_reason: {candidate.finish_reason}")
                logger.info(f"Safety ratings: {candidate.safety_ratings}")

                if candidate.finish_reason == types.FinishReason.STOP:
                    blog_summary = response.text.strip()
                    blog_summary = self._remove_footer(blog_summary)
                    logger.info(f"Successfully created blog summary ({len(blog_summary)} chars)")
                    return blog_summary
                elif candidate.finish_reason == types.FinishReason.SAFETY:
                    logger.warning("Blog summary blocked by safety filter")
                    logger.warning(f"Safety ratings: {candidate.safety_ratings}")
                    return self._create_fallback_summary(raw_markdown)
                else:
                    logger.warning(f"Unexpected finish reason: {candidate.finish_reason}")
                    logger.warning(f"Candidate content: {candidate}")
                    return self._create_fallback_summary(raw_markdown)
            else:
                logger.warning("No valid response candidates")
                logger.warning(f"Response: {response}")
                return self._create_fallback_summary(raw_markdown)

        except Exception as e:
            if is_quota_error(e):
                logger.warning(f"API quota exhausted, switching to Gemini CLI: {e}")
                self._use_cli_fallback = True
                return self._summarize_via_cli(prompt, raw_markdown)
            logger.error(f"Error creating blog summary: {str(e)}")
            return self._create_fallback_summary(raw_markdown)

    def _summarize_via_cli(self, prompt: str, raw_markdown: str) -> str:
        """Run Gemini summarization via CLI fallback. Returns markdown summary or fallback text."""
        logger.info("[CLI Fallback] Summarizing via gemini -p...")
        try:
            text = call_gemini_cli(prompt)
            if not text or len(text) < 200:
                logger.warning(f"[CLI Fallback] Insufficient response: {len(text)} chars")
                return self._create_fallback_summary(raw_markdown)
            cleaned = self._remove_footer(text.strip())
            logger.info(f"[CLI Fallback] Summary completed ({len(cleaned)} chars)")
            return cleaned
        except Exception as e:
            logger.error(f"[CLI Fallback] Failed: {e}")
            return self._create_fallback_summary(raw_markdown)

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
        try:
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

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.7,
                    max_output_tokens=8000,
                    safety_settings=self.safety_settings,
                ),
            )

            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.finish_reason == types.FinishReason.STOP:
                    weekly_summary = response.text.strip()
                    weekly_summary = self._remove_footer(weekly_summary)
                    logger.info(f"Successfully created weekly summary ({len(weekly_summary)} chars)")
                    return weekly_summary

            logger.warning("Failed to create weekly summary, returning fallback")
            return f"""# 📅 주간 뉴스 요약 ({start_date} ~ {end_date})

> AI 요약 생성 중 오류가 발생했습니다.

{daily_summaries}
"""

        except Exception as e:
            logger.error(f"Error creating weekly summary: {str(e)}")
            return f"""# 📅 주간 뉴스 요약 ({start_date} ~ {end_date})

> 오류: {str(e)}

{daily_summaries}
"""

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
        try:
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

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.7,
                    max_output_tokens=10000,
                    safety_settings=self.safety_settings,
                ),
            )

            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if candidate.finish_reason == types.FinishReason.STOP:
                    monthly_summary = response.text.strip()
                    monthly_summary = self._remove_footer(monthly_summary)
                    logger.info(f"Successfully created monthly summary ({len(monthly_summary)} chars)")
                    return monthly_summary

            logger.warning("Failed to create monthly summary, returning fallback")
            return f"""# 📆 {year}년 {month}월 월간 뉴스 요약

> AI 요약 생성 중 오류가 발생했습니다.

{daily_summaries}
"""

        except Exception as e:
            logger.error(f"Error creating monthly summary: {str(e)}")
            return f"""# 📆 {year}년 {month}월 월간 뉴스 요약

> 오류: {str(e)}

{daily_summaries}
"""
