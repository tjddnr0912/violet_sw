import google.generativeai as genai
from typing import List, Dict
import logging
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AISummarizer:
    """AI-powered blog-style summarizer using Google Gemini API"""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        """
        Initialize AISummarizer

        Args:
            api_key: Google Gemini API key
            model: Google Gemini model to use (default: gemini-1.5-flash)
        """
        genai.configure(api_key=api_key)

        # Initialize model with system instruction for news journalism
        self.model = genai.GenerativeModel(
            model,
            system_instruction="""You are a professional news journalist and summarizer.
Your role is to provide objective summaries of news articles from verified sources.
All content you receive is from legitimate Korean news agencies (SBS, YTN, Yonhap).
Your summaries are for educational and informational purposes only.
You must summarize ALL news content accurately, including political, crime, and sensitive topics.
This is journalistic work, not content generation."""
        )
        self.model_name = model

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

            prompt = f"""[JOURNALISM TASK] You are a professional news journalist creating a comprehensive blog summary of TODAY'S news articles.

CRITICAL CONTEXT:
- This is OFFICIAL JOURNALISM WORK for news summarization
- All content is from VERIFIED news agencies (Korean: SBS, YTN, Yonhap / International: Bloomberg, Reuters, CNBC, CoinDesk)
- These are REAL NEWS ARTICLES published today
- Your task is EDUCATIONAL and INFORMATIONAL
- This is NOT generating harmful content - just summarizing factual news

Input: Today's news articles organized by category (in Korean AND English)

Raw News Content:
{raw_markdown}

Your task:
1. **IMPORTANT**: Summarize ALL news articles provided - DO NOT skip any articles
2. Create a comprehensive blog-style summary in Korean (한국어)
3. Organize by categories with emoji icons: 🏛️정치, 💰경제, 👥사회, 🌍국제, 🎭문화, 🔬IT/과학, 📈주식, 💎암호화폐

4. For each category:
   - Write a brief category introduction (1-2 sentences)
   - **Summarize EVERY news article** in that category (do not skip articles)
   - For each article, write 2-4 sentences covering:
     * What happened (핵심 사건)
     * Why it matters (중요성)
     * Key details or implications (주요 내용)
   - You MAY combine duplicate/similar topics into one summary
   - Number each news item (1., 2., 3., ...)

5. **ENGLISH ARTICLE HANDLING**:
   - For articles written in English (Bloomberg, Reuters, MarketWatch, CoinDesk, etc.):
     * First TRANSLATE the English content to Korean
     * Then SUMMARIZE in Korean like other articles
     * Maintain the same level of detail as Korean articles

6. Writing style:
   - Professional yet accessible Korean (존댓말 사용)
   - Clear and concise summaries
   - Focus on facts and context
   - Natural, conversational tone

7. Structure:
   - Start with a brief greeting and date
   - Category sections with ALL article summaries
   - End with a closing remark

REMEMBER:
- Include ALL articles (모든 기사 포함)
- Translate English articles to Korean (영문 기사는 한글로 번역)
- You can combine duplicate topics (중복 주제는 합칠 수 있음)

Format: Return ONLY the markdown content, no explanations.

Blog Post (한국어):"""

            # Log input size for debugging
            logger.info(f"Input prompt size: {len(prompt)} characters")
            logger.info(f"Raw markdown size: {len(raw_markdown)} characters")

            # Try WITHOUT safety_settings parameter at all
            # This may allow Gemini to use its default behavior which might be less strict
            logger.info("Calling Gemini API without explicit safety_settings...")

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=8000,  # Increased to summarize ALL articles
                )
                # NO safety_settings parameter - let Gemini use defaults
            )

            # Check if response has valid content
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]

                # Log detailed response info for debugging
                logger.info(f"Gemini finish_reason: {candidate.finish_reason}")
                logger.info(f"Safety ratings: {candidate.safety_ratings}")

                if candidate.finish_reason == 1:  # STOP (successful)
                    blog_summary = response.text.strip()
                    logger.info(f"Successfully created blog summary ({len(blog_summary)} chars)")
                    return blog_summary
                elif candidate.finish_reason == 2:  # SAFETY
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
