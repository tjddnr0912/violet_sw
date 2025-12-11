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

Format: Return ONLY the markdown content, no explanations.

Blog Post (한국어):"""

            # Log input size for debugging
            logger.info(f"Input prompt size: {len(prompt)} characters")
            logger.info(f"Raw markdown size: {len(raw_markdown)} characters")

            # Use BLOCK_NONE for news journalism work
            # This is justified because:
            # 1. We are summarizing PUBLICLY PUBLISHED news from verified sources
            # 2. This is legitimate journalism/educational work
            # 3. The content has already been approved by major news organizations
            # 4. Safety ratings show NEGLIGIBLE risk but Gemini still blocks with BLOCK_ONLY_HIGH
            from google.generativeai.types import HarmCategory, HarmBlockThreshold

            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            logger.info("Calling Gemini API with BLOCK_NONE safety settings for verified news journalism...")

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=8000,  # Increased to summarize ALL articles
                ),
                safety_settings=safety_settings
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
