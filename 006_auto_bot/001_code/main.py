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

# Import news_bot modules
from news_bot.config import config
from news_bot.aggregator import NewsAggregator
from news_bot.summarizer import AISummarizer
from news_bot.writer import MarkdownWriter


class NewsBot:
    """Main bot class for news aggregation and posting"""

    def __init__(self):
        """Initialize the news bot"""
        try:
            logger.info("Initializing NewsBot")

            self.config = config

            # Validate configuration
            self.config.validate()

            # Initialize components
            category_map = getattr(self.config, 'CATEGORY_MAP', {})
            if category_map:
                self.news_aggregator = NewsAggregator(
                    self.config.NEWS_SOURCES,
                    category_map=category_map
                )
            else:
                self.news_aggregator = NewsAggregator(self.config.NEWS_SOURCES)

            self.ai_summarizer = AISummarizer(
                api_key=self.config.GEMINI_API_KEY,
                model=self.config.GEMINI_MODEL
            )
            self.markdown_writer = MarkdownWriter(
                base_dir=self.config.OUTPUT_DIR
            )

            logger.info("News bot initialized successfully")
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
                                from shared.blogger_uploader import BloggerUploader

                                current_date = datetime.now().strftime("%Y년 %m월 %d일")
                                post_title = f"{current_date} 뉴스 요약"

                                # HTML 변환 방식 결정
                                upload_content = blog_summary
                                is_markdown = True

                                if getattr(self.config, 'HTML_CONVERTER', 'markdown_lib') == 'claude_cli':
                                    try:
                                        from shared.claude_html_converter import convert_md_to_html_via_claude
                                        logger.info("Using Claude CLI for HTML conversion...")
                                        html_output_path = os.path.join(
                                            self.config.OUTPUT_DIR,
                                            datetime.now().strftime("%Y%m%d"),
                                            f"blog_html_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                                        )
                                        upload_content = convert_md_to_html_via_claude(
                                            md_content=blog_summary,
                                            output_path=html_output_path,
                                            include_investment_disclaimer=True
                                        )
                                        is_markdown = False
                                        logger.info(f"Claude HTML conversion complete: {html_output_path}")
                                    except Exception as e:
                                        logger.warning(f"Claude CLI failed, falling back to markdown lib: {e}")
                                        upload_content = blog_summary
                                        is_markdown = True

                                with BloggerUploader(
                                    blog_id=self.config.BLOGGER_BLOG_ID,
                                    credentials_path=self.config.BLOGGER_CREDENTIALS_PATH,
                                    token_path=self.config.BLOGGER_TOKEN_PATH
                                ) as uploader:
                                    upload_result = uploader.upload_post(
                                        title=post_title,
                                        content=upload_content,
                                        labels=self.config.BLOGGER_LABELS,
                                        is_draft=self.config.BLOGGER_IS_DRAFT,
                                        is_markdown=is_markdown
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
                                from shared.telegram_notifier import TelegramNotifier

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
                        logger.info("Daily task completed successfully!")
                        logger.info(f"Raw news saved: {raw_result.get('filepath', 'N/A')}")
                        logger.info(f"Blog summary saved: {blog_result.get('filepath', 'N/A')}")
                        logger.info("=" * 60)
                    else:
                        logger.warning(f"Failed to save blog summary: {blog_result['message']}")
                else:
                    logger.warning("No markdown content to summarize")
            else:
                logger.error(f"Failed to save raw news: {raw_result['message']}")

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
                logger.warning(f"Network error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1) * 10  # 20s, 40s, 80s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries exceeded")
                    return False
            except Exception as e:
                logger.error(f"Error during task execution: {e}", exc_info=True)
                return False
        return False

    def run_daily_task_with_retry(self, max_retries: int = 3) -> bool:
        """Execute daily task with retry logic for network errors"""
        for attempt in range(max_retries):
            try:
                self.run_daily_task()
                return True
            except (ConnectionError, ConnectionResetError, ConnectionAbortedError) as e:
                logger.warning(f"Network error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1) * 30  # 60s, 120s, 240s
                    logger.info(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                else:
                    logger.error("Max retries exceeded. Will retry on next schedule.")
                    return False
            except Exception as e:
                logger.error(f"Error during task execution: {e}", exc_info=True)
                return False
        return False

    def run_weekly_task(self):
        """Execute weekly news summary task (every Sunday at 9am)"""
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
                    from shared.blogger_uploader import BloggerUploader

                    post_title = f"Weekly News Summary ({start_date_str} ~ {end_date_str})"

                    # HTML 변환 방식 결정
                    upload_content = weekly_summary
                    is_markdown = True

                    if getattr(self.config, 'HTML_CONVERTER', 'markdown_lib') == 'claude_cli':
                        try:
                            from shared.claude_html_converter import convert_md_to_html_via_claude
                            logger.info("Using Claude CLI for weekly HTML conversion...")
                            html_output_path = os.path.join(
                                self.config.OUTPUT_DIR,
                                "weekly",
                                f"weekly_html_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                            )
                            upload_content = convert_md_to_html_via_claude(
                                md_content=weekly_summary,
                                output_path=html_output_path,
                                include_investment_disclaimer=True
                            )
                            is_markdown = False
                            logger.info(f"Claude HTML conversion complete: {html_output_path}")
                        except Exception as e:
                            logger.warning(f"Claude CLI failed, falling back to markdown lib: {e}")
                            upload_content = weekly_summary
                            is_markdown = True

                    with BloggerUploader(
                        blog_id=self.config.BLOGGER_BLOG_ID,
                        credentials_path=self.config.BLOGGER_CREDENTIALS_PATH,
                        token_path=self.config.BLOGGER_TOKEN_PATH
                    ) as uploader:
                        upload_result = uploader.upload_post(
                            title=post_title,
                            content=upload_content,
                            labels=self.config.BLOGGER_WEEKLY_LABELS,
                            is_draft=self.config.BLOGGER_IS_DRAFT,
                            is_markdown=is_markdown
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
                    from shared.telegram_notifier import TelegramNotifier

                    notifier = TelegramNotifier(
                        bot_token=self.config.TELEGRAM_BOT_TOKEN,
                        chat_id=self.config.TELEGRAM_CHAT_ID
                    )

                    message = f"Weekly news summary completed!\nPeriod: {start_date_str} ~ {end_date_str}"
                    notifier.send_message(message)

                except Exception as e:
                    logger.error(f"Telegram notification error: {e}")

            logger.info("=" * 60)
            logger.info("Weekly task completed successfully!")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error during weekly task: {str(e)}", exc_info=True)

    def run_monthly_task(self):
        """Execute monthly news summary task (every 1st of month at 10am)"""
        try:
            logger.info("=" * 60)
            logger.info("Starting monthly news summary task")
            logger.info("=" * 60)

            # Get last month's year and month (for summary)
            today = datetime.now()
            if today.month == 1:
                last_month = 12
                last_year = today.year - 1
            else:
                last_month = today.month - 1
                last_year = today.year

            # Get 2 months ago (for cleanup - keep last month for 1 month)
            if today.month <= 2:
                cleanup_month = today.month + 10  # 1->11, 2->12
                cleanup_year = today.year - 1
            else:
                cleanup_month = today.month - 2
                cleanup_year = today.year

            logger.info(f"Processing {last_year}/{last_month} (cleanup target: {cleanup_year}/{cleanup_month})")

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
                    from shared.blogger_uploader import BloggerUploader

                    post_title = f"Monthly News Summary - {last_year}/{last_month}"

                    # HTML 변환 방식 결정
                    upload_content = monthly_summary
                    is_markdown = True

                    if getattr(self.config, 'HTML_CONVERTER', 'markdown_lib') == 'claude_cli':
                        try:
                            from shared.claude_html_converter import convert_md_to_html_via_claude
                            logger.info("Using Claude CLI for monthly HTML conversion...")
                            html_output_path = os.path.join(
                                self.config.OUTPUT_DIR,
                                "monthly",
                                f"monthly_html_{last_year}{last_month:02d}.html"
                            )
                            upload_content = convert_md_to_html_via_claude(
                                md_content=monthly_summary,
                                output_path=html_output_path,
                                include_investment_disclaimer=True
                            )
                            is_markdown = False
                            logger.info(f"Claude HTML conversion complete: {html_output_path}")
                        except Exception as e:
                            logger.warning(f"Claude CLI failed, falling back to markdown lib: {e}")
                            upload_content = monthly_summary
                            is_markdown = True

                    with BloggerUploader(
                        blog_id=self.config.BLOGGER_BLOG_ID,
                        credentials_path=self.config.BLOGGER_CREDENTIALS_PATH,
                        token_path=self.config.BLOGGER_TOKEN_PATH
                    ) as uploader:
                        upload_result = uploader.upload_post(
                            title=post_title,
                            content=upload_content,
                            labels=self.config.BLOGGER_MONTHLY_LABELS,
                            is_draft=self.config.BLOGGER_IS_DRAFT,
                            is_markdown=is_markdown
                        )

                        if upload_result['success']:
                            logger.info(f"Monthly summary uploaded: {upload_result.get('url', 'N/A')}")
                            blog_upload_success = True
                            blog_url = upload_result.get('url')
                        else:
                            logger.warning(f"Blogger upload failed: {upload_result['message']}")

                except Exception as e:
                    logger.error(f"Blogger upload error: {e}")

            # Step 5: Cleanup 2-month-old folders (only after successful blog upload)
            if blog_upload_success:
                logger.info(f"Step 5: Cleaning up {cleanup_year}/{cleanup_month} news folders...")
                cleanup_result = self.markdown_writer.cleanup_month_folders(cleanup_year, cleanup_month)
                logger.info(f"Cleanup result: {cleanup_result['message']}")
            else:
                logger.warning("Skipping cleanup because blog upload was not successful")

            # Step 6: Send Telegram notification (if enabled)
            if getattr(self.config, 'TELEGRAM_ENABLED', False):
                logger.info("Step 6: Sending Telegram notification...")
                try:
                    from shared.telegram_notifier import TelegramNotifier

                    notifier = TelegramNotifier(
                        bot_token=self.config.TELEGRAM_BOT_TOKEN,
                        chat_id=self.config.TELEGRAM_CHAT_ID
                    )

                    message = f"Monthly news summary completed! ({last_year}/{last_month})"
                    if blog_url:
                        message += f"\n{blog_url}"
                    if blog_upload_success:
                        message += f"\nCleaned up {cleanup_year}/{cleanup_month} data"

                    notifier.send_message(message)

                except Exception as e:
                    logger.error(f"Telegram notification error: {e}")

            logger.info("=" * 60)
            logger.info("Monthly task completed successfully!")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Error during monthly task: {str(e)}", exc_info=True)

    def _check_and_run_monthly(self):
        """Check if today is the 1st of the month and run monthly task"""
        if datetime.now().day == 1:
            logger.info("Today is the 1st of the month, running monthly task...")
            self.run_monthly_task()

    def run_scheduled(self):
        """Run the task on a daily schedule with error recovery"""
        posting_time = self.config.POSTING_TIME
        logger.info(f"Scheduling daily task at {posting_time}")

        # Schedule daily news task with retry logic
        schedule.every().day.at(posting_time).do(self.run_daily_task_with_retry)

        # Schedule weekly and monthly tasks
        weekly_time = getattr(self.config, 'WEEKLY_POSTING_TIME', '09:00')
        monthly_time = getattr(self.config, 'MONTHLY_POSTING_TIME', '10:00')

        # Weekly task: Every Sunday at 9am
        schedule.every().sunday.at(weekly_time).do(self.run_weekly_task)
        logger.info(f"Scheduled weekly task: Every Sunday at {weekly_time}")

        # Monthly task: Every 1st of month at 10am
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
                    logger.warning(f"Scheduler network error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Consecutive error limit exceeded. Waiting 60s...")
                        time.sleep(60)
                        consecutive_errors = 0
                except Exception as e:
                    consecutive_errors += 1
                    logger.error(f"Scheduler error ({consecutive_errors}/{max_consecutive_errors}): {e}")
                    if consecutive_errors >= max_consecutive_errors:
                        logger.error("Consecutive error limit exceeded. Waiting 60s...")
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
        # Initialize bot
        bot = NewsBot()

        if args.test:
            logger.info("Running in TEST mode (no saving)")
            # Test: fetch and summarize only
            news_items = bot.news_aggregator.get_daily_news(
                count=bot.config.MAX_NEWS_COUNT,
                hours_limit=bot.config.NEWS_HOURS_LIMIT
            )

            if news_items:
                raw_result = bot.markdown_writer.save_raw_news_by_category(news_items)
                if raw_result['success']:
                    raw_markdown = raw_result.get('markdown_content', '')
                    if raw_markdown:
                        blog_summary = bot.ai_summarizer.create_blog_summary(raw_markdown)
                        print("\n" + "=" * 60)
                        print("GENERATED BLOG SUMMARY (TEST MODE):")
                        print("=" * 60)
                        print(blog_summary[:2000] + "..." if len(blog_summary) > 2000 else blog_summary)
                        print("=" * 60)

        elif args.mode == 'once':
            bot.run_once()

        elif args.mode == 'weekly':
            logger.info("Running weekly summary task...")
            bot.run_weekly_task()

        elif args.mode == 'monthly':
            logger.info("Running monthly summary task...")
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
