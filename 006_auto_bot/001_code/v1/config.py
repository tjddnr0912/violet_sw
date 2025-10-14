import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Configuration class for news automation bot"""

    # Google Gemini API Configuration
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')

    # News API Configuration (optional - if you want to use NewsAPI)
    NEWS_API_KEY = os.getenv('NEWS_API_KEY', '')

    # News Sources (RSS Feeds)
    NEWS_SOURCES = [
        'http://rss.cnn.com/rss/edition_world.rss',
        'https://feeds.bbci.co.uk/news/world/rss.xml',
        'https://www.aljazeera.com/xml/rss/all.xml',
        'https://www.theguardian.com/world/rss',
        'https://www.reuters.com/rssFeed/worldNews',
        'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
    ]

    # Bot Settings
    MAX_NEWS_COUNT = 10  # Number of news articles to select daily
    SUMMARY_MAX_LENGTH = 300  # Maximum length of AI summary in words

    # Output Settings
    OUTPUT_DIR = '../004_News_paper'  # Directory to save markdown files

    # Scheduling
    POSTING_TIME = "09:00"  # Time to run daily (HH:MM format)

    # Version Info
    VERSION = "1"
    VERSION_NAME = "Global News"
    VERSION_DESCRIPTION = "글로벌 뉴스(CNN, BBC, Al Jazeera, Guardian, Reuters, NYT) 수집 및 요약"

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
