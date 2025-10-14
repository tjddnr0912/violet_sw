import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup
import logging
import time
from newspaper import Article

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NewsAggregator:
    """Aggregates news from multiple RSS feeds"""

    def __init__(self, rss_feeds: List[str], category_map: Dict[str, str] = None):
        """
        Initialize NewsAggregator with RSS feed URLs

        Args:
            rss_feeds: List of RSS feed URLs
            category_map: Dict mapping feed URL to category name (optional)
        """
        self.rss_feeds = rss_feeds
        self.category_map = category_map or {}
        self.news_items = []

    def fetch_news(self) -> List[Dict]:
        """
        Fetch news from all RSS feeds

        Returns:
            List of news items as dictionaries
        """
        self.news_items = []

        for feed_url in self.rss_feeds:
            try:
                logger.info(f"Fetching news from: {feed_url}")
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:5]:  # Get top 5 from each source
                    news_item = self._parse_entry(entry, feed_url)
                    if news_item:
                        self.news_items.append(news_item)

            except Exception as e:
                logger.error(f"Error fetching from {feed_url}: {str(e)}")
                continue

        logger.info(f"Total news items fetched: {len(self.news_items)}")
        return self.news_items

    def _fetch_full_article(self, url: str) -> str:
        """
        Fetch full article content from URL using web scraping

        Args:
            url: Article URL

        Returns:
            Full article text, or empty string if failed
        """
        try:
            logger.info(f"Fetching full article from: {url[:60]}...")

            # Use newspaper3k for article extraction
            article = Article(url)
            article.download()
            article.parse()

            if article.text:
                logger.info(f"Successfully extracted article ({len(article.text)} chars)")
                return article.text
            else:
                logger.warning(f"No text content found in article: {url[:60]}...")
                return ""

        except Exception as e:
            logger.error(f"Error fetching article from {url[:60]}...: {str(e)}")
            return ""

    def _parse_entry(self, entry, source_url: str) -> Dict:
        """
        Parse a single RSS entry and fetch full article content

        Args:
            entry: RSS entry object
            source_url: Source RSS feed URL

        Returns:
            Dictionary containing news item data
        """
        try:
            # Extract publication date
            published_date = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_date = datetime(*entry.published_parsed[:6])
            else:
                published_date = datetime.now()

            # Extract description/summary from RSS
            rss_description = ''
            if hasattr(entry, 'summary'):
                rss_description = self._clean_html(entry.summary)
            elif hasattr(entry, 'description'):
                rss_description = self._clean_html(entry.description)

            # Get article link
            article_link = entry.link if hasattr(entry, 'link') else ''

            # Fetch full article content
            full_content = ''
            if article_link:
                full_content = self._fetch_full_article(article_link)
                # Add small delay to be respectful to servers
                time.sleep(1)

            # Use full content if available, otherwise fall back to RSS description
            description = full_content if full_content else rss_description

            # Get source name from feed
            source_name = self._extract_source_name(source_url)

            return {
                'title': entry.title if hasattr(entry, 'title') else 'No Title',
                'link': article_link,
                'description': description,
                'rss_summary': rss_description,  # Keep RSS summary for reference
                'full_content': full_content,  # Store full content separately
                'published_date': published_date,
                'source': source_name,
                'source_url': source_url
            }

        except Exception as e:
            logger.error(f"Error parsing entry: {str(e)}")
            return None

    def _clean_html(self, html_text: str) -> str:
        """
        Remove HTML tags from text

        Args:
            html_text: Text containing HTML tags

        Returns:
            Clean text without HTML tags
        """
        if not html_text:
            return ''

        soup = BeautifulSoup(html_text, 'html.parser')
        return soup.get_text(strip=True)

    def _extract_source_name(self, url: str) -> str:
        """
        Extract source name from RSS feed URL

        Args:
            url: RSS feed URL

        Returns:
            Source name
        """
        source_mapping = {
            'cnn.com': 'CNN',
            'bbci.co.uk': 'BBC',
            'aljazeera.com': 'Al Jazeera',
            'theguardian.com': 'The Guardian',
            'reuters.com': 'Reuters',
            'nytimes.com': 'The New York Times',
        }

        for domain, name in source_mapping.items():
            if domain in url:
                return name

        return 'Unknown Source'

    def select_top_news(self, count: int = 10) -> List[Dict]:
        """
        Select top news items based on recency and diversity

        Args:
            count: Number of news items to select

        Returns:
            List of selected news items
        """
        if not self.news_items:
            logger.warning("No news items available")
            return []

        # Sort by published date (most recent first)
        sorted_news = sorted(
            self.news_items,
            key=lambda x: x['published_date'],
            reverse=True
        )

        # Select diverse sources
        selected = []
        used_sources = set()

        # First pass: one from each source
        for item in sorted_news:
            if item['source'] not in used_sources:
                selected.append(item)
                used_sources.add(item['source'])

                if len(selected) >= count:
                    break

        # Second pass: fill remaining slots with most recent
        if len(selected) < count:
            for item in sorted_news:
                if item not in selected:
                    selected.append(item)

                    if len(selected) >= count:
                        break

        logger.info(f"Selected {len(selected)} news items")
        return selected[:count]

    def get_daily_news(self, count: int = 10) -> List[Dict]:
        """
        Fetch and select daily news

        Args:
            count: Number of news items to select

        Returns:
            List of selected news items
        """
        self.fetch_news()
        return self.select_top_news(count)
