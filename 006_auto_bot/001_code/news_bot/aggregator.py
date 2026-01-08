import ssl
import certifi
import feedparser
import requests
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup
import logging
import time
from newspaper import Article

# Fix SSL certificate verification issues on macOS
ssl._create_default_https_context = ssl._create_unverified_context

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
            category_map: Dict mapping feed URL to category name
        """
        self.rss_feeds = rss_feeds
        self.category_map = category_map or {}
        self.news_items = []

        # Configure newspaper3k globally with browser-like headers
        from newspaper import Config
        self.newspaper_config = Config()
        self.newspaper_config.browser_user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        self.newspaper_config.request_timeout = 10
        self.newspaper_config.memoize_articles = False

        # Prepare headers for requests fallback
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Sec-Fetch-Dest': 'document'
        }

    def fetch_news(self, hours_limit: int = 24) -> List[Dict]:
        """
        Fetch news from all RSS feeds

        Args:
            hours_limit: Only include news published within this many hours (default: 24)

        Returns:
            List of news items as dictionaries
        """
        self.news_items = []
        cutoff_time = datetime.now() - timedelta(hours=hours_limit)

        for feed_url in self.rss_feeds:
            try:
                logger.info(f"Fetching news from: {feed_url}")
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:10]:  # Get top 10 from each source (increased from 5)
                    news_item = self._parse_entry(entry, feed_url)
                    if news_item:
                        # Filter by publication date (only recent news)
                        pub_date = news_item.get('published_date')
                        if pub_date and pub_date >= cutoff_time:
                            self.news_items.append(news_item)
                            logger.debug(f"Added news: {news_item['title'][:50]}... (published: {pub_date})")
                        else:
                            logger.debug(f"Skipped old news: {news_item['title'][:50]}... (published: {pub_date})")

            except Exception as e:
                logger.error(f"Error fetching from {feed_url}: {str(e)}")
                continue

        logger.info(f"Total news items fetched (within {hours_limit}h): {len(self.news_items)}")
        return self.news_items

    def _fetch_full_article(self, url: str) -> str:
        """
        Fetch full article content from URL using web scraping
        Try newspaper3k first, fallback to requests if it fails

        Args:
            url: Article URL

        Returns:
            Full article text, or empty string if failed
        """
        logger.info(f"Fetching full article from: {url[:60]}...")

        # Method 1: Try newspaper3k with configured headers
        try:
            article = Article(url, config=self.newspaper_config)
            article.download()
            article.parse()

            if article.text and len(article.text) > 100:  # Ensure meaningful content
                logger.info(f"Successfully extracted article ({len(article.text)} chars) via newspaper3k")
                return article.text
            else:
                logger.debug(f"newspaper3k extracted insufficient content, trying requests...")
        except Exception as e:
            logger.debug(f"newspaper3k failed for {url[:60]}...: {str(e)}, trying requests fallback...")

        # Method 2: Fallback to requests + BeautifulSoup
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Remove script and style elements
            for script in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                script.decompose()

            # Try common article content selectors
            article_selectors = [
                'article',
                {'class': 'article-body'},
                {'class': 'article-content'},
                {'class': 'story-body'},
                {'class': 'post-content'},
                {'class': 'entry-content'},
                {'id': 'article-body'},
                {'class': 'txt'},
                {'class': 'news_view'},
                'main'
            ]

            text = ''
            for selector in article_selectors:
                if isinstance(selector, dict):
                    element = soup.find('div', selector)
                else:
                    element = soup.find(selector)

                if element:
                    text = element.get_text(separator=' ', strip=True)
                    if len(text) > 100:  # Found meaningful content
                        break

            if text and len(text) > 100:
                logger.info(f"Successfully extracted article ({len(text)} chars) via requests")
                return text
            else:
                logger.warning(f"Could not extract meaningful content from {url[:60]}...")
                return ""

        except Exception as e:
            logger.error(f"All methods failed for {url[:60]}...: {str(e)}")
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

            # Determine if we should try to fetch full article
            # Skip sites with strong paywalls or bot protection
            skip_fetch_domains = ['bloomberg.com', 'marketwatch.com', 'ft.com', 'wsj.com']
            should_fetch = not any(domain in article_link for domain in skip_fetch_domains)

            # Fetch full article content (unless skipped)
            full_content = ''
            if article_link and should_fetch:
                full_content = self._fetch_full_article(article_link)
                # Add delay to be respectful to servers and avoid rate limiting
                # Longer delay for sites with strict anti-bot measures
                if 'hankyung.com' in article_link or 'mk.co.kr' in article_link:
                    time.sleep(2)  # 2 seconds for Korean economy sites
                else:
                    time.sleep(1)  # 1 second for others
            elif article_link and not should_fetch:
                logger.debug(f"Skipping full article fetch for paywall site: {article_link[:60]}...")

            # Use full content if available, otherwise fall back to RSS description
            description = full_content if full_content else rss_description

            # Get source name from feed
            source_name = self._extract_source_name(source_url)

            # Get category from map
            category = self.category_map.get(source_url, '기타')

            return {
                'title': entry.title if hasattr(entry, 'title') else 'No Title',
                'link': article_link,
                'description': description,
                'rss_summary': rss_description,  # Keep RSS summary for reference
                'full_content': full_content,  # Store full content separately
                'published_date': published_date,
                'source': source_name,
                'source_url': source_url,
                'category': category  # Add category information
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
            # 국내 일반 뉴스
            'sbs.co.kr': 'SBS',
            'ytn.co.kr': 'YTN',
            'yonhapnewstv.co.kr': '연합뉴스TV',
            'yonhapnews.co.kr': '연합뉴스',

            # 국내 경제/주식
            'hankyung.com': '한국경제',
            'mk.co.kr': '매일경제',
            'sedaily.com': '서울경제',
            'infomax.co.kr': '연합인포맥스',

            # 국내 암호화폐
            'blockmedia.co.kr': '블록미디어',
            'decenter.kr': '디센터',

            # 해외 일반 뉴스
            'cnn.com': 'CNN',
            'bbci.co.uk': 'BBC',
            'aljazeera.com': 'Al Jazeera',
            'theguardian.com': 'The Guardian',
            'reuters.com': 'Reuters',
            'reutersagency.com': 'Reuters',
            'nytimes.com': 'The New York Times',

            # 해외 경제/주식
            'bloomberg.com': 'Bloomberg',
            'cnbc.com': 'CNBC',
            'marketwatch.com': 'MarketWatch',
            'ft.com': 'Financial Times',
            'wsj.com': 'Wall Street Journal',

            # 해외 암호화폐
            'coindesk.com': 'CoinDesk',
            'cointelegraph.com': 'CoinTelegraph',
            'decrypt.co': 'Decrypt',
            'theblock.co': 'The Block',
            'cryptoslate.com': 'CryptoSlate',
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

    def get_daily_news(self, count: int = 10, hours_limit: int = 24) -> List[Dict]:
        """
        Fetch and select daily news

        Args:
            count: Number of news items to select
            hours_limit: Only include news published within this many hours

        Returns:
            List of selected news items
        """
        self.fetch_news(hours_limit=hours_limit)
        return self.select_top_news(count)
