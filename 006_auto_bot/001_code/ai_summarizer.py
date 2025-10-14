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
    """AI-powered news summarizer using Google Gemini API"""

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

    def summarize_article(self, title: str, description: str, max_length: int = 300) -> str:
        """
        Summarize a single news article

        Args:
            title: Article title
            description: Article description/content
            max_length: Maximum length of summary in words

        Returns:
            Summarized text
        """
        try:
            prompt = f"""당신은 전문적인 뉴스 요약 전문가입니다. 객관적이고 정확하게 뉴스를 요약합니다.

다음 뉴스 기사를 한국어로 요약해주세요.
제목: {title}
내용: {description}

요약 요구사항:
- 반드시 한국어로 작성할 것
- {max_length}자 이내로 작성
- 핵심 내용만 간결하게 정리
- 객관적이고 명확한 한국어 문체 사용
- 중요한 사실과 배경을 포함
- 영어 단어는 한글로 번역하되, 고유명사는 괄호 안에 원어 병기

요약 (한국어):"""

            # Configure safety settings to be more permissive for news content
            safety_settings = [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_ONLY_HIGH"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_ONLY_HIGH"
                }
            ]

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.7,
                    max_output_tokens=500,
                ),
                safety_settings=safety_settings
            )

            # Check if response has valid content
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]

                # Check finish reason
                if candidate.finish_reason == 1:  # STOP (successful)
                    summary = response.text.strip()
                    logger.info(f"Successfully summarized article: {title[:50]}...")
                    return summary
                elif candidate.finish_reason == 2:  # SAFETY
                    logger.warning(f"Article blocked by safety filter: {title[:50]}...")
                    # Return original description without safety filter notice
                    return description[:max_length] + "..." if len(description) > max_length else description
                else:
                    logger.warning(f"Unexpected finish reason {candidate.finish_reason} for: {title[:50]}...")
                    return description[:max_length] + "..." if len(description) > max_length else description
            else:
                logger.warning(f"No valid response candidates for: {title[:50]}...")
                return description[:max_length] + "..."

        except Exception as e:
            logger.error(f"Error summarizing article '{title}': {str(e)}")
            return description[:max_length] + "..."

    def summarize_news_batch(self, news_items: List[Dict], max_length: int = 300, delay: float = 30.0) -> List[Dict]:
        """
        Summarize multiple news articles with rate limiting

        Args:
            news_items: List of news item dictionaries
            max_length: Maximum length of each summary in words
            delay: Delay in seconds between requests (default: 30s for free tier)

        Returns:
            List of news items with added 'summary' field
        """
        summarized_items = []

        for i, item in enumerate(news_items, 1):
            logger.info(f"Summarizing article {i}/{len(news_items)}: {item['title'][:50]}...")

            # Add retry logic for rate limit errors
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    summary = self.summarize_article(
                        title=item['title'],
                        description=item['description'],
                        max_length=max_length
                    )

                    # Add summary to the news item
                    item_with_summary = item.copy()
                    item_with_summary['summary'] = summary
                    summarized_items.append(item_with_summary)
                    break  # Success, exit retry loop

                except Exception as e:
                    error_msg = str(e)
                    if '429' in error_msg or 'quota' in error_msg.lower():
                        retry_count += 1
                        if retry_count < max_retries:
                            wait_time = delay * retry_count  # Exponential backoff
                            logger.warning(f"Rate limit hit. Waiting {wait_time}s before retry {retry_count}/{max_retries}...")
                            time.sleep(wait_time)
                        else:
                            logger.error(f"Max retries reached for article: {item['title'][:50]}...")
                            # Add item without AI summary
                            item_with_summary = item.copy()
                            item_with_summary['summary'] = f"[요약 실패: API 제한] {item['description'][:max_length]}..."
                            summarized_items.append(item_with_summary)
                    else:
                        # Other error, log and continue
                        logger.error(f"Error processing article: {error_msg}")
                        item_with_summary = item.copy()
                        item_with_summary['summary'] = item['description'][:max_length] + "..."
                        summarized_items.append(item_with_summary)
                        break

            # Add delay between requests to respect rate limits (except for last item)
            if i < len(news_items):
                logger.info(f"Waiting {delay}s before next request (rate limit protection)...")
                time.sleep(delay)

        logger.info(f"Completed summarizing {len(summarized_items)} articles")
        return summarized_items

    def generate_blog_post(self, news_items: List[Dict]) -> str:
        """
        Generate a complete blog post from summarized news items

        Args:
            news_items: List of news items with summaries

        Returns:
            Formatted blog post HTML
        """
        try:
            from datetime import datetime

            # Create blog post header
            current_date = datetime.now().strftime("%Y년 %m월 %d일")
            blog_post = f"""<h2>📰 {current_date} 글로벌 주요 뉴스 TOP 10</h2>
<p>오늘 전세계에서 주목받고 있는 주요 뉴스를 AI가 선별하고 요약했습니다.</p>
<hr>
"""

            # Add each news item
            for i, item in enumerate(news_items, 1):
                source = item.get('source', 'Unknown')
                title = item.get('title', 'No Title')
                summary = item.get('summary', item.get('description', ''))
                link = item.get('link', '')
                pub_date = item.get('published_date', datetime.now())

                # Format publication date
                if isinstance(pub_date, datetime):
                    date_str = pub_date.strftime("%Y-%m-%d %H:%M")
                else:
                    date_str = str(pub_date)

                news_section = f"""
<h3>{i}. {title}</h3>
<p><strong>출처:</strong> {source} | <strong>발행일:</strong> {date_str}</p>
<blockquote>{summary}</blockquote>
<p><a href="{link}" target="_blank">원문 보기 →</a></p>
<hr>
"""
                blog_post += news_section

            # Add footer
            blog_post += """
<p style="text-align: center; color: #888; font-size: 0.9em;">
※ 본 뉴스는 AI가 자동으로 수집하고 요약한 내용입니다.<br>
정확한 정보는 원문을 참고해주시기 바랍니다.
</p>
"""

            logger.info("Generated complete blog post")
            return blog_post

        except Exception as e:
            logger.error(f"Error generating blog post: {str(e)}")
            raise
