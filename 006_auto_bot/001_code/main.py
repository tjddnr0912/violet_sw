#!/usr/bin/env python3
"""
Automated News Aggregation and Blog Posting Bot
------------------------------------------------
Daily news aggregation, AI summarization, and automatic blog posting
"""

import logging
import schedule
import time
import os
from datetime import datetime, timedelta

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
            logger.info(f"Step 1: Fetching top {self.config.MAX_NEWS_COUNT} news articles (within {self.config.NEWS_HOURS_LIMIT}h)...")
            news_items = self.news_aggregator.get_daily_news(
                count=self.config.MAX_NEWS_COUNT,
                hours_limit=self.config.NEWS_HOURS_LIMIT
            )

            if not news_items:
                logger.warning("No news items found. Aborting task.")
                return

            logger.info(f"Successfully fetched {len(news_items)} news articles")

            # V3 specific workflow: raw markdown + AI blog summary
            if self.version == 'v3':
                # Step 2: Save raw news organized by category
                logger.info("Step 2: Saving raw news by category...")
                raw_result = self.markdown_writer.save_raw_news_by_category(news_items)

                if raw_result['success']:
                    logger.info(f"Raw news saved: {raw_result.get('filepath', 'N/A')}")

                    # Step 3: Create AI blog summary from raw markdown
                    logger.info("Step 3: Creating AI blog summary with Gemini...")
                    raw_markdown = raw_result.get('markdown_content', '')

                    if raw_markdown:
                        blog_summary = self.ai_summarizer.create_blog_summary(raw_markdown)

                        # Step 4: Save blog summary
                        logger.info("Step 4: Saving blog summary...")
                        blog_result = self.markdown_writer.save_blog_summary(blog_summary)

                        if blog_result['success']:
                            # Track upload status for telegram notification
                            blog_upload_success = False
                            blog_url = None
                            blog_error = None

                            # Step 5: Upload to Google Blogger (if enabled)
                            if getattr(self.config, 'BLOGGER_ENABLED', False):
                                logger.info("Step 5: Uploading to Google Blogger...")
                                try:
                                    from blogger_uploader import BloggerUploader

                                    current_date = datetime.now().strftime("%Y년 %m월 %d일")
                                    post_title = f"{current_date} 뉴스 요약"

                                    with BloggerUploader(
                                        blog_id=self.config.BLOGGER_BLOG_ID,
                                        credentials_path=self.config.BLOGGER_CREDENTIALS_PATH,
                                        token_path=self.config.BLOGGER_TOKEN_PATH
                                    ) as uploader:
                                        upload_result = uploader.upload_post(
                                            title=post_title,
                                            content=blog_summary,
                                            labels=self.config.BLOGGER_LABELS,
                                            is_draft=self.config.BLOGGER_IS_DRAFT,
                                            is_markdown=True
                                        )

                                        if upload_result['success']:
                                            logger.info(f"Blogger upload success: {upload_result.get('url', 'N/A')}")
                                            blog_upload_success = True
                                            blog_url = upload_result.get('url')
                                        else:
                                            logger.warning(f"Blogger upload failed: {upload_result['message']}")
                                            blog_error = upload_result['message']

                                except ImportError:
                                    blog_error = "blogger_uploader not found"
                                    logger.error("blogger_uploader not found. Run: pip install google-api-python-client google-auth-oauthlib")
                                except Exception as e:
                                    blog_error = str(e)
                                    logger.error(f"Blogger upload error: {e}")
                            else:
                                logger.info("Blogger upload disabled (BLOGGER_ENABLED=false)")

                            # Step 6: Send Telegram notification (if enabled)
                            if getattr(self.config, 'TELEGRAM_ENABLED', False):
                                logger.info("Step 6: Sending Telegram notification...")
                                try:
                                    from telegram_notifier import TelegramNotifier

                                    notifier = TelegramNotifier(
                                        bot_token=self.config.TELEGRAM_BOT_TOKEN,
                                        chat_id=self.config.TELEGRAM_CHAT_ID
                                    )

                                    telegram_result = notifier.send_blog_notification(
                                        summary_content=blog_summary,
                                        upload_success=blog_upload_success,
                                        blog_url=blog_url,
                                        error_message=blog_error if not blog_upload_success else None
                                    )

                                    if telegram_result['success']:
                                        logger.info("Telegram notification sent successfully")
                                    else:
                                        logger.warning(f"Telegram notification failed: {telegram_result.get('error', 'Unknown')}")

                                except ImportError:
                                    logger.error("telegram_notifier not found")
                                except Exception as e:
                                    logger.error(f"Telegram notification error: {e}")
                            else:
                                logger.info("Telegram notification disabled (TELEGRAM_ENABLED=false)")

                            logger.info("=" * 60)
                            logger.info("✅ Daily task completed successfully!")
                            logger.info(f"Raw news saved: {raw_result.get('filepath', 'N/A')}")
                            logger.info(f"Blog summary saved: {blog_result.get('filepath', 'N/A')}")
                            logger.info("=" * 60)
                        else:
                            logger.warning(f"Failed to save blog summary: {blog_result['message']}")
                    else:
                        logger.warning("No markdown content to summarize")
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

    def run_once(self, max_retries: int = 3):
        """Run the task once immediately with retry logic"""
        logger.info("Running task immediately (one-time execution)")
        for attempt in range(max_retries):
            try:
                self.run_daily_task()
                return True
            except (ConnectionError, ConnectionResetError, ConnectionAbortedError) as e:
                logger.warning(f"네트워크 에러 (시도 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1) * 10  # 20초, 40초, 80초
                    logger.info(f"{wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                else:
                    logger.error("최대 재시도 횟수 초과")
                    return False
            except Exception as e:
                logger.error(f"작업 실행 중 오류: {e}", exc_info=True)
                return False
        return False

    def run_daily_task_with_retry(self, max_retries: int = 3) -> bool:
        """
        Execute daily task with retry logic for network errors

        Args:
            max_retries: Maximum number of retry attempts

        Returns:
            True if task completed successfully, False otherwise
        """
        for attempt in range(max_retries):
            try:
                self.run_daily_task()
                return True
            except (ConnectionError, ConnectionResetError, ConnectionAbortedError) as e:
                logger.warning(f"네트워크 에러 (시도 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1) * 30  # 60초, 120초, 240초
                    logger.info(f"{wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"최대 재시도 횟수 초과. 다음 스케줄에서 다시 시도합니다.")
                    return False
            except Exception as e:
                logger.error(f"작업 실행 중 오류: {e}", exc_info=True)
                return False
        return False

    def run_weekly_task(self):
        """Execute weekly news summary task (every Sunday at 9am)"""
        if self.version != 'v3':
            logger.info("Weekly task is only available for v3")
            return

        try:
            logger.info("=" * 60)
            logger.info("Starting weekly news summary task")
            logger.info("=" * 60)

            # Step 1: Collect daily summaries for this week
            logger.info("Step 1: Collecting daily summaries for this week...")
            daily_content, start_date_str, end_date_str = self.markdown_writer.collect_daily_summaries_for_week()

            if not daily_content:
                logger.warning("No daily summaries found for this week. Aborting.")
                return

            logger.info(f"Collected summaries from {start_date_str} to {end_date_str}")

            # Step 2: Create weekly summary with AI
            logger.info("Step 2: Creating weekly summary with Gemini AI...")
            weekly_summary = self.ai_summarizer.create_weekly_summary(
                daily_content, start_date_str, end_date_str
            )

            # Step 3: Save weekly summary
            logger.info("Step 3: Saving weekly summary...")
            today = datetime.now()
            days_since_monday = today.weekday()
            if days_since_monday == 6:
                days_since_monday = 6
            monday = today - timedelta(days=days_since_monday)
            save_result = self.markdown_writer.save_weekly_summary(weekly_summary, monday)

            if not save_result['success']:
                logger.error(f"Failed to save weekly summary: {save_result['message']}")
                return

            # Step 4: Upload to Blogger (if enabled)
            if getattr(self.config, 'BLOGGER_ENABLED', False):
                logger.info("Step 4: Uploading weekly summary to Blogger...")
                try:
                    from blogger_uploader import BloggerUploader

                    post_title = f"📅 주간 뉴스 요약 ({start_date_str} ~ {end_date_str})"

                    with BloggerUploader(
                        blog_id=self.config.BLOGGER_BLOG_ID,
                        credentials_path=self.config.BLOGGER_CREDENTIALS_PATH,
                        token_path=self.config.BLOGGER_TOKEN_PATH
                    ) as uploader:
                        upload_result = uploader.upload_post(
                            title=post_title,
                            content=weekly_summary,
                            labels=self.config.BLOGGER_WEEKLY_LABELS,
                            is_draft=self.config.BLOGGER_IS_DRAFT,
                            is_markdown=True
                        )

                        if upload_result['success']:
                            logger.info(f"Weekly summary uploaded: {upload_result.get('url', 'N/A')}")
                        else:
                            logger.warning(f"Blogger upload failed: {upload_result['message']}")

                except Exception as e:
                    logger.error(f"Blogger upload error: {e}")

            # Step 5: Send Telegram notification (if enabled)
            if getattr(self.config, 'TELEGRAM_ENABLED', False):
                logger.info("Step 5: Sending Telegram notification...")
                try:
                    from telegram_notifier import TelegramNotifier

                    notifier = TelegramNotifier(
                        bot_token=self.config.TELEGRAM_BOT_TOKEN,
                        chat_id=self.config.TELEGRAM_CHAT_ID
                    )

                    message = f"📅 주간 뉴스 요약 완료!\n기간: {start_date_str} ~ {end_date_str}"
                    notifier.send_message(message)

                except Exception as e:
                    logger.error(f"Telegram notification error: {e}")

            logger.info("=" * 60)
            logger.info("✅ Weekly task completed successfully!")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error during weekly task: {str(e)}", exc_info=True)

    def run_monthly_task(self):
        """Execute monthly news summary task (every 1st of month at 10am)"""
        if self.version != 'v3':
            logger.info("Monthly task is only available for v3")
            return

        try:
            logger.info("=" * 60)
            logger.info("Starting monthly news summary task")
            logger.info("=" * 60)

            # Get last month's year and month
            today = datetime.now()
            if today.month == 1:
                last_month = 12
                last_year = today.year - 1
            else:
                last_month = today.month - 1
                last_year = today.year

            logger.info(f"Processing {last_year}년 {last_month}월")

            # Step 1: Collect daily summaries for last month
            logger.info("Step 1: Collecting daily summaries for last month...")
            daily_content = self.markdown_writer.collect_daily_summaries_for_month(last_year, last_month)

            if not daily_content:
                logger.warning("No daily summaries found for last month. Aborting.")
                return

            # Step 2: Create monthly summary with AI
            logger.info("Step 2: Creating monthly summary with Gemini AI...")
            monthly_summary = self.ai_summarizer.create_monthly_summary(
                daily_content, last_year, last_month
            )

            # Step 3: Save monthly summary
            logger.info("Step 3: Saving monthly summary...")
            save_result = self.markdown_writer.save_monthly_summary(monthly_summary, last_year, last_month)

            if not save_result['success']:
                logger.error(f"Failed to save monthly summary: {save_result['message']}")
                return

            # Step 4: Upload to Blogger (if enabled)
            blog_upload_success = False
            blog_url = None

            if getattr(self.config, 'BLOGGER_ENABLED', False):
                logger.info("Step 4: Uploading monthly summary to Blogger...")
                try:
                    from blogger_uploader import BloggerUploader

                    post_title = f"📆 {last_year}년 {last_month}월 월간 뉴스 요약"

                    with BloggerUploader(
                        blog_id=self.config.BLOGGER_BLOG_ID,
                        credentials_path=self.config.BLOGGER_CREDENTIALS_PATH,
                        token_path=self.config.BLOGGER_TOKEN_PATH
                    ) as uploader:
                        upload_result = uploader.upload_post(
                            title=post_title,
                            content=monthly_summary,
                            labels=self.config.BLOGGER_MONTHLY_LABELS,
                            is_draft=self.config.BLOGGER_IS_DRAFT,
                            is_markdown=True
                        )

                        if upload_result['success']:
                            logger.info(f"Monthly summary uploaded: {upload_result.get('url', 'N/A')}")
                            blog_upload_success = True
                            blog_url = upload_result.get('url')
                        else:
                            logger.warning(f"Blogger upload failed: {upload_result['message']}")

                except Exception as e:
                    logger.error(f"Blogger upload error: {e}")

            # Step 5: Cleanup last month's folders (only after successful blog upload)
            if blog_upload_success:
                logger.info("Step 5: Cleaning up last month's news folders...")
                cleanup_result = self.markdown_writer.cleanup_month_folders(last_year, last_month)
                logger.info(f"Cleanup result: {cleanup_result['message']}")
            else:
                logger.warning("Skipping cleanup because blog upload was not successful")

            # Step 6: Send Telegram notification (if enabled)
            if getattr(self.config, 'TELEGRAM_ENABLED', False):
                logger.info("Step 6: Sending Telegram notification...")
                try:
                    from telegram_notifier import TelegramNotifier

                    notifier = TelegramNotifier(
                        bot_token=self.config.TELEGRAM_BOT_TOKEN,
                        chat_id=self.config.TELEGRAM_CHAT_ID
                    )

                    message = f"📆 {last_year}년 {last_month}월 월간 뉴스 요약 완료!"
                    if blog_url:
                        message += f"\n🔗 {blog_url}"
                    if blog_upload_success:
                        message += f"\n🗑️ {last_month}월 뉴스 폴더 정리 완료"

                    notifier.send_message(message)

                except Exception as e:
                    logger.error(f"Telegram notification error: {e}")

            logger.info("=" * 60)
            logger.info("✅ Monthly task completed successfully!")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error during monthly task: {str(e)}", exc_info=True)

    def _check_and_run_monthly(self):
        """Check if today is the 1st of the month and run monthly task"""
        if datetime.now().day == 1:
            logger.info("Today is the 1st of the month, running monthly task...")
            self.run_monthly_task()
        else:
            # Silent pass - don't log every day
            pass

    def run_scheduled(self):
        """Run the task on a daily schedule with error recovery"""
        posting_time = self.config.POSTING_TIME
        logger.info(f"Scheduling daily task at {posting_time}")

        # Schedule daily news task with retry logic
        schedule.every().day.at(posting_time).do(self.run_daily_task_with_retry)

        # V3: Schedule weekly and monthly tasks
        if self.version == 'v3':
            weekly_time = getattr(self.config, 'WEEKLY_POSTING_TIME', '09:00')
            monthly_time = getattr(self.config, 'MONTHLY_POSTING_TIME', '10:00')

            # Weekly task: Every Sunday at 9am
            schedule.every().sunday.at(weekly_time).do(self.run_weekly_task)
            logger.info(f"Scheduled weekly task: Every Sunday at {weekly_time}")

            # Monthly task: Every 1st of month at 10am
            # schedule doesn't support "1st of month" directly, so we check in a wrapper
            schedule.every().day.at(monthly_time).do(self._check_and_run_monthly)
            logger.info(f"Scheduled monthly task: Every 1st at {monthly_time}")

        logger.info("News bot is now running. Press Ctrl+C to stop.")
        logger.info(f"Next run scheduled at: {posting_time}")

        consecutive_errors = 0
        max_consecutive_errors = 10

        try:
            while True:
                try:
                    schedule.run_pending()
                    consecutive_errors = 0  # Reset on success
                except (ConnectionError, ConnectionResetError, ConnectionAbortedError) as e:
                    consecutive_errors += 1
                    logger.warning(f"스케줄러 네트워크 에러 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("연속 에러 한도 초과. 60초 대기 후 계속...")
                        time.sleep(60)
                        consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"스케줄러 오류 ({consecutive_errors}/{max_consecutive_errors}): {e}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("연속 에러 한도 초과. 60초 대기 후 계속...")
                        time.sleep(60)
                        consecutive_errors = 0

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
        choices=['once', 'scheduled', 'weekly', 'monthly'],
        default='once',
        help='Execution mode: "once" for daily, "scheduled" for auto, "weekly" for weekly summary, "monthly" for monthly summary'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: fetch news and summarize without saving'
    )
    parser.add_argument(
        '--no-cleanup',
        action='store_true',
        help='Skip cleanup of old folders after monthly summary (useful for testing)'
    )

    args = parser.parse_args()

    try:
        # Initialize bot with specified version
        bot = NewsBot(version=args.version)

        if args.test:
            logger.info("Running in TEST mode (no saving)")
            # Test: fetch and summarize only
            news_items = bot.news_aggregator.get_daily_news(
                count=bot.config.MAX_NEWS_COUNT,
                hours_limit=bot.config.NEWS_HOURS_LIMIT
            )
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

        elif args.mode == 'weekly':
            if args.version != 'v3':
                logger.error("Weekly mode is only available for v3")
            else:
                logger.info("Running weekly summary task...")
                bot.run_weekly_task()

        elif args.mode == 'monthly':
            if args.version != 'v3':
                logger.error("Monthly mode is only available for v3")
            else:
                logger.info("Running monthly summary task...")
                # If --no-cleanup flag is set, temporarily disable cleanup
                if args.no_cleanup:
                    original_cleanup = bot.markdown_writer.cleanup_month_folders
                    bot.markdown_writer.cleanup_month_folders = lambda y, m: {'success': True, 'message': 'Skipped (--no-cleanup)'}
                bot.run_monthly_task()
                if args.no_cleanup:
                    bot.markdown_writer.cleanup_month_folders = original_cleanup

        elif args.mode == 'scheduled':
            bot.run_scheduled()

    except KeyboardInterrupt:
        logger.info("Execution interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        raise


if __name__ == '__main__':
    main()
