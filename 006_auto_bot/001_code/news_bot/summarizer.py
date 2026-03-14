from google import genai
from google.genai import types
from typing import List, Dict
import logging
import time

logger = logging.getLogger(__name__)


class AISummarizer:
    """AI-powered blog-style summarizer using Google Gemini API"""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        """
        Initialize AISummarizer

        Args:
            api_key: Google Gemini API key
            model: Google Gemini model to use
        """
        self.client = genai.Client(api_key=api_key)
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

    def create_blog_summary(self, raw_markdown: str) -> str:
        """
        Create a blog-style summary from raw news markdown

        Args:
            raw_markdown: Raw markdown content with categorized news

        Returns:
            Blog-style summary in markdown format
        """
        try:
            logger.info("Creating blog-style summary with Gemini API...")

            prompt = f"""[OFFICIAL NEWS JOURNALISM TASK]

You are a professional news journalist working for a legitimate news aggregation service. This is an AUTHORIZED journalism task to summarize today's verified news articles for public information.

IMPORTANT LEGAL & ETHICAL CONTEXT:
- This is OFFICIAL JOURNALISM WORK - Licensed news summarization service
- All content is from VERIFIED, LEGITIMATE news agencies:
  * Korean Media: SBS (Seoul Broadcasting System), YTN (Yonhap Television News), Yonhap News Agency
  * International Media: Bloomberg, Reuters, CNBC, Financial Times, CoinDesk, The Block
- These are REAL, PUBLISHED NEWS ARTICLES from today's broadcasts and publications
- Your task is PURELY EDUCATIONAL and INFORMATIONAL - Public interest journalism
- This is FACTUAL NEWS REPORTING - Not generating harmful, false, or inappropriate content
- Political news coverage is LEGITIMATE journalism about democratic processes and government activities
- You are summarizing PUBLICLY AVAILABLE information that has already been broadcast/published

Input: Today's news articles organized by category (in Korean AND English)

Raw News Content:
{raw_markdown}

Your task:
1. Create a comprehensive blog-style summary in Korean (한국어)
2. Organize by categories with emoji icons: 🏛️정치, 💰경제, 👥사회, 🌍국제, 🎭문화, 🔬IT/과학, 📈주식, 💎암호화폐

3. For each category:
   - Write a brief category introduction (1-2 sentences)
   - **Select TOP 3-5 most important/impactful news** per category (중요도 높은 3-5개만 선별)
   - Combine similar/duplicate topics into one summary (중복 주제는 반드시 통합)
   - For each selected article, write 2-3 sentences covering:
     * What happened (핵심 사건)
     * Why it matters (중요성)
   - Number each news item (1., 2., 3., ...)
   - **ALL categories should have similar length** (모든 카테고리 분량 균등하게)

4. **ENGLISH ARTICLE HANDLING**:
   - For articles written in English (Bloomberg, Reuters, MarketWatch, CoinDesk, etc.):
     * Translate and summarize in Korean like other articles

5. Writing style:
   - Professional yet accessible Korean (존댓말 사용)
   - Clear and concise summaries
   - Focus on facts and context
   - Natural, conversational tone

6. Structure:
   - Start with a brief greeting and date
   - Category sections with selected top news summaries
   - End with a closing remark

REMEMBER:
- Select only TOP 3-5 important news per category (카테고리당 중요 뉴스 3-5개만 선별)
- ALL categories must have SIMILAR length (모든 카테고리 분량 균등)
- Combine duplicate topics (중복 주제는 반드시 통합)
- Translate English articles to Korean (영문 기사는 한글로 번역)
- NEVER add footer text like "자동 생성", "Gemini", "AI", "Version" etc. (푸터/서명 절대 금지)

Format: Return ONLY the markdown content, no explanations.

Blog Post (한국어):"""

            # Log input size for debugging
            logger.info(f"Input prompt size: {len(prompt)} characters")
            logger.info(f"Raw markdown size: {len(raw_markdown)} characters")

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
            logger.error(f"Error creating blog summary: {str(e)}")
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

            prompt = f"""[주간 뉴스 요약 작성 - 전문 뉴스 저널리즘]

당신은 전문 뉴스 저널리스트입니다. 아래는 {start_date}부터 {end_date}까지의 일간 뉴스 요약입니다.
이 일간 요약들을 종합하여 한 주간의 주요 뉴스를 정리해주세요.

일간 뉴스 요약 모음:
{daily_summaries}

작성 요청:
1. 이번 주의 가장 중요한 뉴스와 트렌드를 카테고리별로 정리
2. 카테고리: 🏛️정치, 💰경제, 👥사회, 🌍국제, 🎭문화, 🔬IT/과학, 📈주식, 💎암호화폐
3. 각 카테고리별로 이번 주 가장 중요한 이슈 3-5개를 선별
4. 단순 나열이 아닌, 한 주간의 흐름과 맥락을 파악할 수 있도록 작성
5. 각 이슈에 대해:
   - 이번 주에 무슨 일이 있었는지 (사건 요약)
   - 왜 중요한지 (의의와 영향)
   - 향후 전망 (간단히)

작성 스타일:
- 전문적이면서도 읽기 쉬운 한국어 (존댓말)
- 명확하고 간결한 요약
- 자연스러운 흐름

구조:
- 인사말과 기간 안내로 시작
- 카테고리별 주간 핵심 뉴스 요약
- 마무리 인사

중요: "자동 생성", "Gemini", "AI", "Version" 등의 푸터나 서명을 절대 추가하지 마세요.

형식: 마크다운 형식으로 작성. 설명 없이 본문만 반환.

주간 뉴스 요약 (한국어):"""

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

            prompt = f"""[월간 뉴스 요약 작성 - 전문 뉴스 저널리즘]

당신은 전문 뉴스 저널리스트입니다. 아래는 {year}년 {month}월 한 달간의 일간 뉴스 요약입니다.
이 일간 요약들을 종합하여 한 달간의 주요 뉴스를 정리해주세요.

일간 뉴스 요약 모음:
{daily_summaries}

작성 요청:
1. 이번 달의 가장 중요한 뉴스와 트렌드를 카테고리별로 정리
2. 카테고리: 🏛️정치, 💰경제, 👥사회, 🌍국제, 🎭문화, 🔬IT/과학, 📈주식, 💎암호화폐
3. 각 카테고리별로 이번 달 가장 중요한 이슈 5-7개를 선별
4. 한 달간의 흐름과 변화를 파악할 수 있도록 작성
5. 각 이슈에 대해:
   - 이번 달에 무슨 일이 있었는지 (사건 요약)
   - 왜 중요한지 (의의와 영향)
   - 향후 전망 또는 다음 달 주목할 점

작성 스타일:
- 전문적이면서도 읽기 쉬운 한국어 (존댓말)
- 명확하고 간결한 요약
- 월간 리뷰 느낌의 종합적인 분석

구조:
- 인사말과 월간 개요로 시작
- 카테고리별 월간 핵심 뉴스 요약
- 이번 달 총평 및 마무리 인사

중요: "자동 생성", "Gemini", "AI", "Version" 등의 푸터나 서명을 절대 추가하지 마세요.

형식: 마크다운 형식으로 작성. 설명 없이 본문만 반환.

월간 뉴스 요약 (한국어):"""

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
