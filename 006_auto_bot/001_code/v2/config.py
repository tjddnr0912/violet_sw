import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for Korean news automation bot (Version 2)"""

    # Google Gemini API Configuration
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')

    # News API Configuration (optional - if you want to use NewsAPI)
    NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')

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
    }

    # Category to use for news collection (set to None to use all categories)
    SELECTED_CATEGORIES = ['정치', '경제', '사회']  # Customize this list

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
    MAX_NEWS_COUNT = 10  # Number of news articles to select daily
    SUMMARY_MAX_LENGTH = 300  # Maximum length of AI summary in words

    # Output Settings
    OUTPUT_DIR = '../004_News_paper'  # Directory to save markdown files

    # Scheduling
    POSTING_TIME = "09:00"  # Time to run daily (HH:MM format)

    # Version Info
    VERSION = "2"
    VERSION_NAME = "Korean News"
    VERSION_DESCRIPTION = "국내 주요 언론사(MBC, KBS, SBS, 연합뉴스, YTN) 뉴스 수집 및 요약"

    # Validation
    @classmethod
    def validate(cls):
        """Validate that all required configuration is set"""
        errors = []

        if not cls.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is not set")

        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")

        return True


# Global config instance
config = Config()
