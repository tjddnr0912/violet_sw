import os
from dotenv import load_dotenv

# Load environment variables from .env file
# override=True ensures .env takes precedence over system environment variables
load_dotenv(override=True)


class Config:
    """Configuration class for Korean news automation bot (Version 3)"""

    # Google Gemini API Configuration
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash-lite')

    # News API Configuration (optional - if you want to use NewsAPI)
    NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')

    # News Fetching Settings
    NEWS_HOURS_LIMIT = int(os.getenv('NEWS_HOURS_LIMIT', '24'))  # Default: 24 hours

    # Korean News Sources by Category (RSS Feeds)
    NEWS_SOURCES_BY_CATEGORY = {
        '정치': [
            'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=01',  # SBS 정치
            'https://www.ytn.co.kr/_ln/0101_xml',  # YTN 정치
            'https://www.yonhapnewstv.co.kr/category/news/politics/feed/',  # 연합뉴스 정치
        ],
        '경제': [
            'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02',  # SBS 경제
            'https://www.ytn.co.kr/_ln/0102_xml',  # YTN 경제
            'https://www.yonhapnewstv.co.kr/category/news/economy/feed/',  # 연합뉴스 경제
        ],
        '사회': [
            'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=07',  # SBS 사회
            'https://www.ytn.co.kr/_ln/0103_xml',  # YTN 사회
            'https://www.yonhapnewstv.co.kr/category/news/society/feed/',  # 연합뉴스 사회
        ],
        '국제': [
            'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=08',  # SBS 국제
            'https://www.ytn.co.kr/_ln/0104_xml',  # YTN 국제
            'https://www.yonhapnewstv.co.kr/category/news/international/feed/',  # 연합뉴스 국제
        ],
        '문화': [
            'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03',  # SBS 문화
            'https://www.ytn.co.kr/_ln/0105_xml',  # YTN 생활/문화
            'https://www.yonhapnewstv.co.kr/category/news/culture/feed/',  # 연합뉴스 문화
        ],
        'IT/과학': [
            'https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=09',  # SBS IT/과학
            'https://www.ytn.co.kr/_ln/0106_xml',  # YTN IT/과학
        ],
        '주식': [
            # 국내 주식 뉴스
            'https://www.hankyung.com/feed/economy',  # 한국경제 경제
            'https://www.mk.co.kr/rss/40300001/',  # 매일경제 증권/금융
            'https://www.sedaily.com/NewsRSS/1S11',  # 서울경제 증권
            # 해외 주식 뉴스
            'https://feeds.bloomberg.com/markets/news.rss',  # Bloomberg Markets
            'https://www.reutersagency.com/feed/?taxonomy=best-topics&post_type=best',  # Reuters Business
            'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147',  # CNBC Top News
            'https://www.marketwatch.com/rss/topstories',  # MarketWatch Top Stories
            'https://www.ft.com/?format=rss',  # Financial Times
        ],
        '암호화폐': [
            # 국내 암호화폐 뉴스
            'https://www.blockmedia.co.kr/feed',  # 블록미디어
            'https://decenter.kr/NewsRSS/S1N14',  # 디센터
            # 해외 암호화폐 뉴스
            'https://www.coindesk.com/arc/outboundfeeds/rss/',  # CoinDesk
            'https://cointelegraph.com/rss',  # CoinTelegraph
            'https://decrypt.co/feed',  # Decrypt
            'https://www.theblock.co/rss.xml',  # The Block
            'https://cryptoslate.com/feed/',  # CryptoSlate
        ],
    }

    # V3: Collect ALL categories
    SELECTED_CATEGORIES = None  # None means all categories

    # Build NEWS_SOURCES from selected categories
    NEWS_SOURCES = []
    categories_to_use = SELECTED_CATEGORIES if SELECTED_CATEGORIES else NEWS_SOURCES_BY_CATEGORY.keys()
    for category in categories_to_use:
        if category in NEWS_SOURCES_BY_CATEGORY:
            NEWS_SOURCES.extend(NEWS_SOURCES_BY_CATEGORY[category])

    # Add category mapping for URL lookup
    CATEGORY_MAP = {}
    for category, urls in NEWS_SOURCES_BY_CATEGORY.items():
        for url in urls:
            CATEGORY_MAP[url] = category

    # Bot Settings
    MAX_NEWS_COUNT = 50  # Increased for more categories (8 categories now)
    SUMMARY_MAX_LENGTH = 300  # Maximum length of AI summary in words

    # Output Settings
    OUTPUT_DIR = '../004_News_paper'  # Directory to save markdown files

    # Scheduling
    POSTING_TIME = "07:00"  # Time to run daily (HH:MM format)

    # Version Info
    VERSION = "3"
    VERSION_NAME = "Korean News - All Categories (Including Stock & Crypto)"
    VERSION_DESCRIPTION = "모든 카테고리(정치,경제,사회,국제,문화,IT/과학,주식,암호화폐) 수집 → 카테고리별 Raw 파일 + Gemini AI 블로그 요약 생성"

    # Validation
    # Tistory Configuration (Selenium-based)
    TISTORY_ENABLED = os.getenv('TISTORY_ENABLED', 'false').lower() == 'true'
    TISTORY_BLOG_URL = os.getenv('TISTORY_BLOG_URL', '')
    TISTORY_CATEGORY = os.getenv('TISTORY_CATEGORY', '')
    TISTORY_TAGS = os.getenv('TISTORY_TAGS', '뉴스,AI요약,자동화').split(',')
    TISTORY_HEADLESS = os.getenv('TISTORY_HEADLESS', 'true').lower() == 'true'
    TISTORY_COOKIE_PATH = os.getenv('TISTORY_COOKIE_PATH', './cookies/tistory_cookies.pkl')
    TISTORY_VISIBILITY = os.getenv('TISTORY_VISIBILITY', 'public')  # public, private, protected
    # Chrome User Profile for persistent login (replaces cookie-based auth)
    TISTORY_USER_DATA_DIR = os.getenv('TISTORY_USER_DATA_DIR', './chrome_profile/tistory')

    # Telegram Notification Configuration
    TELEGRAM_ENABLED = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

    # Google Blogger Configuration (API-based - more stable than Tistory)
    BLOGGER_ENABLED = os.getenv('BLOGGER_ENABLED', 'false').lower() == 'true'
    BLOGGER_BLOG_ID = os.getenv('BLOGGER_BLOG_ID', '')
    BLOGGER_CREDENTIALS_PATH = os.getenv('BLOGGER_CREDENTIALS_PATH', './credentials/blogger_credentials.json')
    BLOGGER_TOKEN_PATH = os.getenv('BLOGGER_TOKEN_PATH', './credentials/blogger_token.pkl')
    BLOGGER_LABELS = os.getenv('BLOGGER_LABELS', '뉴스,AI요약,자동화').split(',')
    BLOGGER_IS_DRAFT = os.getenv('BLOGGER_IS_DRAFT', 'false').lower() == 'true'

    @classmethod
    def validate(cls):
        """Validate that all required configuration is set"""
        errors = []

        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is not set")

        if cls.TISTORY_ENABLED and not cls.TISTORY_BLOG_URL:
            errors.append("TISTORY_BLOG_URL is not set but TISTORY_ENABLED is true")

        if cls.BLOGGER_ENABLED and not cls.BLOGGER_BLOG_ID:
            errors.append("BLOGGER_BLOG_ID is not set but BLOGGER_ENABLED is true")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")

        return True


# Global config instance
config = Config()
