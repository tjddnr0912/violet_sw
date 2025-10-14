#!/usr/bin/env python3
"""
Automated News Aggregation and Blog Posting Bot
------------------------------------------------
Daily news aggregation, AI summarization, and automatic Tistory blog posting
"""

import logging
import schedule
import time
import os
from datetime import datetime

# Suppress gRPC/ALTS warnings from Google API
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

import sys
import importlib

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/news_bot_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class NewsBot:
    """Main bot class for news aggregation and posting"""

    def __init__(self, version='v1'):
        """Initialize the news bot with specified version"""
        try:
            # Dynamically import version-specific modules
            self.version = version
            logger.info(f"Initializing NewsBot version: {version}")

            # Import version-specific modules
            config_module = importlib.import_module(f'{version}.config')
            aggregator_module = importlib.import_module(f'{version}.news_aggregator')
            summarizer_module = importlib.import_module(f'{version}.ai_summarizer')
            writer_module = importlib.import_module(f'{version}.markdown_writer')

            self.config = config_module.config

            # Validate configuration
            self.config.validate()

            # Initialize components
            # Pass category_map if available (for v2)
            category_map = getattr(self.config, 'CATEGORY_MAP', {})
            if category_map:
                self.news_aggregator = aggregator_module.NewsAggregator(
                    self.config.NEWS_SOURCES,
                    category_map=category_map
                )
            else:
                self.news_aggregator = aggregator_module.NewsAggregator(self.config.NEWS_SOURCES)
            self.ai_summarizer = summarizer_module.AISummarizer(
                api_key=self.config.GEMINI_API_KEY,
                model=self.config.GEMINI_MODEL
            )
            self.markdown_writer = writer_module.MarkdownWriter(
                base_dir=self.config.OUTPUT_DIR
            )

            logger.info(f"News bot initialized successfully")
            logger.info(f"Version: {self.config.VERSION_NAME}")
            logger.info(f"Description: {self.config.VERSION_DESCRIPTION}")

        except Exception as e:
            logger.error(f"Failed to initialize news bot: {str(e)}")
            raise

    def run_daily_task(self):
        """Execute the daily news aggregation and posting task"""
        try:
            logger.info("=" * 60)
            logger.info("Starting daily news task")
            logger.info("=" * 60)

            # Step 1: Fetch and select top news
            logger.info(f"Step 1: Fetching top {self.config.MAX_NEWS_COUNT} news articles...")
            news_items = self.news_aggregator.get_daily_news(count=self.config.MAX_NEWS_COUNT)

            if not news_items:
                logger.warning("No news items found. Aborting task.")
                return

            logger.info(f"Successfully fetched {len(news_items)} news articles")

            # V3 specific workflow: raw markdown only (no AI summary)
            if self.version == 'v3':
                # Step 2: Save raw news organized by category
                logger.info("Step 2: Saving raw news by category...")
                raw_result = self.markdown_writer.save_raw_news_by_category(news_items)

                if raw_result['success']:
                    logger.info("=" * 60)
                    logger.info("✅ Daily task completed successfully!")
                    logger.info(f"Raw news saved: {raw_result.get('filepath', 'N/A')}")
                    logger.info("=" * 60)
                else:
                    logger.error(f"❌ Failed to save raw news: {raw_result['message']}")

            else:
                # V1, V2 workflow: individual article summaries
                # Step 2: Summarize news with AI
                logger.info("Step 2: Summarizing news articles with AI...")
                summarized_news = self.ai_summarizer.summarize_news_batch(
                    news_items,
                    max_length=self.config.SUMMARY_MAX_LENGTH
                )

                logger.info(f"Successfully summarized {len(summarized_news)} articles")

                # Step 3: Save raw news articles
                logger.info("Step 3: Saving raw news articles...")
                raw_result = self.markdown_writer.save_raw_news(news_items)

                if raw_result['success']:
                    logger.info(f"Raw news saved: {raw_result.get('filepath', 'N/A')}")
                else:
                    logger.warning(f"Failed to save raw news: {raw_result['message']}")

                # Step 4: Prepare blog post content
                logger.info("Step 4: Preparing Korean summary blog post...")

                # Create title with current date
                current_date = datetime.now().strftime("%Y년 %m월 %d일")
                title_suffix = "글로벌 주요 뉴스" if self.version == 'v1' else "국내 주요 뉴스"
                blog_title = f"📰 {current_date} {title_suffix} TOP {self.config.MAX_NEWS_COUNT} (한국어 요약)"

                # Step 5: Save Korean summary as Markdown file
                logger.info("Step 5: Saving Korean summary to Markdown file...")
                result = self.markdown_writer.save_post(
                    title=blog_title,
                    content="",  # Content is generated inside save_post
                    news_items=summarized_news,
                    tag="뉴스,글로벌뉴스,AI요약,자동화,한국어"
                )

                if result['success']:
                    logger.info("=" * 60)
                    logger.info("✅ Daily task completed successfully!")
                    logger.info(f"Korean summary saved: {result.get('filepath', 'N/A')}")
                    logger.info(f"Raw news saved: {raw_result.get('filepath', 'N/A')}")
                    logger.info("=" * 60)
                else:
                    logger.error(f"❌ Failed to save markdown file: {result['message']}")

        except Exception as e:
            logger.error(f"Error during daily task execution: {str(e)}", exc_info=True)

    def run_once(self):
        """Run the task once immediately"""
        logger.info("Running task immediately (one-time execution)")
        self.run_daily_task()

    def run_scheduled(self):
        """Run the task on a daily schedule"""
        posting_time = self.config.POSTING_TIME
        logger.info(f"Scheduling daily task at {posting_time}")

        schedule.every().day.at(posting_time).do(self.run_daily_task)

        logger.info("News bot is now running. Press Ctrl+C to stop.")
        logger.info(f"Next run scheduled at: {posting_time}")

        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute

        except KeyboardInterrupt:
            logger.info("News bot stopped by user")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Automated News Aggregation and Blog Posting Bot'
    )
    parser.add_argument(
        '--version',
        choices=['v1', 'v2', 'v3'],
        default='v1',
        help='Version: "v1" for global news, "v2" for Korean news by category, "v3" for all categories (raw only)'
    )
    parser.add_argument(
        '--mode',
        choices=['once', 'scheduled'],
        default='once',
        help='Execution mode: "once" for immediate run, "scheduled" for daily scheduling'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: fetch news and summarize without saving'
    )

    args = parser.parse_args()

    try:
        # Initialize bot with specified version
        bot = NewsBot(version=args.version)

        if args.test:
            logger.info("Running in TEST mode (no saving)")
            # Test: fetch and summarize only
            news_items = bot.news_aggregator.get_daily_news(count=bot.config.MAX_NEWS_COUNT)
            summarized_news = bot.ai_summarizer.summarize_news_batch(news_items)

            # Generate preview
            title_suffix = "글로벌 주요 뉴스" if args.version == 'v1' else "국내 주요 뉴스"
            markdown_content = bot.markdown_writer._generate_markdown(
                title=f"📰 {datetime.now().strftime('%Y년 %m월 %d일')} {title_suffix} TOP {bot.config.MAX_NEWS_COUNT}",
                news_items=summarized_news,
                tag="뉴스,글로벌뉴스,AI요약,자동화" if args.version == 'v1' else "뉴스,국내뉴스,AI요약,자동화"
            )

            print("\n" + "=" * 60)
            print("GENERATED MARKDOWN CONTENT (TEST MODE):")
            print("=" * 60)
            print(markdown_content)
            print("=" * 60)

        elif args.mode == 'once':
            bot.run_once()

        elif args.mode == 'scheduled':
            bot.run_scheduled()

    except KeyboardInterrupt:
        logger.info("Execution interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
