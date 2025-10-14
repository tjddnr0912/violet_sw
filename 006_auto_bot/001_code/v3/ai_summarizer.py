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

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        """
        Initialize AISummarizer

        Args:
            api_key: Google Gemini API key
            model: Google Gemini model to use (default: gemini-1.5-flash)
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)
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

            prompt = f"""You are a professional news blogger who creates engaging, easy-to-read news summaries in Korean.

IMPORTANT CONTEXT: You are receiving a collection of legitimate news articles from major Korean news organizations. Please create an informative blog post summarizing these articles for journalistic purposes.

Input: Raw news articles organized by category (정치, 경제, 사회, 국제, 문화, IT/과학)

Raw News Content:
{raw_markdown}

Your task:
1. Create a blog-style summary in Korean (한국어)
2. Organize by categories with emoji icons: 🏛️정치, 💰경제, 👥사회, 🌍국제, 🎭문화, 🔬IT/과학
3. For each category:
   - Write a brief introduction (2-3 sentences)
   - Summarize 2-3 key news items in a conversational, engaging style
   - Use bullet points for key facts
   - Include important context and implications
4. Writing style:
   - Friendly, conversational Korean (반말 금지, 존댓말 사용)
   - Clear and easy to understand
   - Focus on "why this matters" not just "what happened"
   - Use natural transitions between topics
5. Structure:
   - Start with a brief greeting and overview
   - Category sections with summaries
   - End with a closing remark

Format: Return ONLY the markdown content, no explanations.

Blog Post (한국어):"""

            # Configure safety settings for news content
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_LOW_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_LOW_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_LOW_AND_ABOVE"
                }
            ]

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=4000,  # Increased for longer blog post
                ),
                safety_settings=safety_settings
            )

            # Check if response has valid content
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]

                if candidate.finish_reason == 1:  # STOP (successful)
                    blog_summary = response.text.strip()
                    logger.info(f"Successfully created blog summary ({len(blog_summary)} chars)")
                    return blog_summary
                elif candidate.finish_reason == 2:  # SAFETY
                    logger.warning("Blog summary blocked by safety filter")
                    return self._create_fallback_summary(raw_markdown)
                else:
                    logger.warning(f"Unexpected finish reason {candidate.finish_reason}")
                    return self._create_fallback_summary(raw_markdown)
            else:
                logger.warning("No valid response candidates")
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
