import os
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import glob

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MarkdownWriter:
    """Markdown file writer for news articles (Version 3)"""

    def __init__(self, base_dir: str = '../004_News_paper'):
        """
        Initialize MarkdownWriter

        Args:
            base_dir: Base directory for storing markdown files
        """
        self.base_dir = base_dir
        self._ensure_base_directory()

    def _ensure_base_directory(self):
        """Create base directory if it doesn't exist"""
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)
            logger.info(f"Created base directory: {self.base_dir}")

    def _get_date_folder(self) -> str:
        """
        Get date-based folder path (YYYYMMDD format)

        Returns:
            Full path to date folder
        """
        date_str = datetime.now().strftime("%Y%m%d")
        date_folder = os.path.join(self.base_dir, date_str)

        if not os.path.exists(date_folder):
            os.makedirs(date_folder)
            logger.info(f"Created date folder: {date_folder}")

        return date_folder

    def save_raw_news_by_category(self, news_items: List[Dict]) -> Dict:
        """
        Save raw news articles organized by category

        Args:
            news_items: List of news items with category information

        Returns:
            Response dictionary with file information including markdown content
        """
        try:
            # Get date folder
            date_folder = self._get_date_folder()

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_news_by_category_{timestamp}.md"
            filepath = os.path.join(date_folder, filename)

            # Generate markdown content for raw news by category
            markdown_content = self._generate_raw_markdown_by_category(news_items)

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)

            logger.info(f"Successfully saved raw news by category: {filepath}")

            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'markdown_content': markdown_content,  # Return content for AI processing
                'message': 'Raw news file saved successfully'
            }

        except Exception as e:
            logger.error(f"Error saving raw news file: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def _generate_raw_markdown_by_category(self, news_items: List[Dict]) -> str:
        """
        Generate markdown content for raw news articles organized by category

        Args:
            news_items: List of news items

        Returns:
            Formatted markdown content organized by category
        """
        from datetime import datetime

        # Create markdown header
        current_date = datetime.now().strftime("%Y년 %m월 %d일")
        current_time = datetime.now().strftime("%H:%M:%S")

        markdown = f"""# 원본 뉴스 기사 모음 (카테고리별)

> 수집 일시: {current_date} {current_time}

---

## 📰 카테고리별 뉴스 기사

"""

        # Group news by category
        news_by_category = {}
        for item in news_items:
            category = item.get('category', '기타')
            if category not in news_by_category:
                news_by_category[category] = []
            news_by_category[category].append(item)

        # Category icons
        category_icons = {
            '정치': '🏛️',
            '경제': '💰',
            '사회': '👥',
            '국제': '🌍',
            '문화': '🎭',
            'IT/과학': '🔬',
            '주식': '📈',
            '암호화폐': '💎',
            '기타': '📌'
        }

        # Add each category section
        for category in ['정치', '경제', '사회', '국제', '문화', 'IT/과학', '주식', '암호화폐', '기타']:
            if category not in news_by_category:
                continue

            icon = category_icons.get(category, '📌')
            markdown += f"\n## {icon} {category}\n\n"

            for i, item in enumerate(news_by_category[category], 1):
                source = item.get('source', 'Unknown')
                item_title = item.get('title', 'No Title')
                description = item.get('description', '')
                link = item.get('link', '')
                pub_date = item.get('published_date', datetime.now())

                # Format publication date
                if isinstance(pub_date, datetime):
                    date_str = pub_date.strftime("%Y-%m-%d %H:%M")
                else:
                    date_str = str(pub_date)

                news_section = f"""### {i}. {item_title}

**출처:** {source}
**발행일:** {date_str}
**링크:** [{link}]({link})

#### 원문 내용

{description}

---

"""
                markdown += news_section

        # Add footer
        markdown += """

---

*원본 뉴스 수집 by Automated News Bot (Version 3)*
"""

        return markdown

    def save_blog_summary(self, blog_content: str) -> Dict:
        """
        Save AI-generated blog summary

        Args:
            blog_content: Blog-style summary content

        Returns:
            Response dictionary with file information
        """
        try:
            # Get date folder
            date_folder = self._get_date_folder()

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"blog_summary_{timestamp}.md"
            filepath = os.path.join(date_folder, filename)

            # Add header
            current_date = datetime.now().strftime("%Y년 %m월 %d일")
            current_time = datetime.now().strftime("%H:%M:%S")

            full_content = f"""# 📰 {current_date} 뉴스 블로그 요약

> 생성 일시: {current_date} {current_time}
> 생성: Gemini AI
> 버전: Version 3 (All Categories)

---

{blog_content}

---

*자동 생성: Gemini API | Version 3*
"""

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_content)

            logger.info(f"Successfully saved blog summary: {filepath}")

            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'message': 'Blog summary saved successfully'
            }

        except Exception as e:
            logger.error(f"Error saving blog summary: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def collect_daily_summaries_for_week(self) -> Tuple[str, str, str]:
        """
        Collect daily blog summaries from Monday to Sunday morning

        Returns:
            Tuple of (combined_content, start_date_str, end_date_str)
        """
        today = datetime.now()

        # Find the Monday of this week (if today is Sunday, it's the previous Monday)
        # weekday(): Monday=0, Sunday=6
        days_since_monday = today.weekday()
        if days_since_monday == 6:  # Sunday
            days_since_monday = 6
        monday = today - timedelta(days=days_since_monday)

        # Collect from Monday to Saturday (Sunday's summary might not exist yet at 9am)
        saturday = monday + timedelta(days=5)

        start_date_str = monday.strftime("%Y년 %m월 %d일")
        end_date_str = saturday.strftime("%Y년 %m월 %d일")

        logger.info(f"Collecting daily summaries from {start_date_str} to {end_date_str}")

        combined_content = []
        current_date = monday

        while current_date <= saturday:
            date_folder = current_date.strftime("%Y%m%d")
            folder_path = os.path.join(self.base_dir, date_folder)

            if os.path.exists(folder_path):
                # Find blog_summary files in this folder
                summary_files = glob.glob(os.path.join(folder_path, "blog_summary_*.md"))

                for summary_file in sorted(summary_files):
                    try:
                        with open(summary_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            date_header = current_date.strftime("%Y년 %m월 %d일")
                            combined_content.append(f"\n\n---\n## 📅 {date_header}\n\n{content}")
                            logger.info(f"Added summary from {summary_file}")
                    except Exception as e:
                        logger.warning(f"Failed to read {summary_file}: {e}")

            current_date += timedelta(days=1)

        return '\n'.join(combined_content), start_date_str, end_date_str

    def collect_daily_summaries_for_month(self, year: int, month: int) -> str:
        """
        Collect daily blog summaries for a specific month

        Args:
            year: Year (e.g., 2025)
            month: Month (e.g., 12)

        Returns:
            Combined content of all daily summaries
        """
        logger.info(f"Collecting daily summaries for {year}년 {month}월")

        combined_content = []

        # Find all folders matching YYYYMM*
        month_prefix = f"{year}{month:02d}"
        all_folders = sorted(glob.glob(os.path.join(self.base_dir, f"{month_prefix}*")))

        for folder_path in all_folders:
            if os.path.isdir(folder_path):
                # Find blog_summary files in this folder
                summary_files = glob.glob(os.path.join(folder_path, "blog_summary_*.md"))

                for summary_file in sorted(summary_files):
                    try:
                        with open(summary_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            folder_name = os.path.basename(folder_path)
                            # Extract date from folder name (YYYYMMDD)
                            if len(folder_name) == 8:
                                day = int(folder_name[6:8])
                                date_header = f"{year}년 {month}월 {day}일"
                                combined_content.append(f"\n\n---\n## 📅 {date_header}\n\n{content}")
                                logger.info(f"Added summary from {summary_file}")
                    except Exception as e:
                        logger.warning(f"Failed to read {summary_file}: {e}")

        return '\n'.join(combined_content)

    def cleanup_month_folders(self, year: int, month: int) -> Dict:
        """
        Delete all folders and weekly summaries for a specific month

        Args:
            year: Year (e.g., 2025)
            month: Month (e.g., 12)

        Returns:
            Response dictionary with cleanup results
        """
        logger.info(f"Cleaning up folders for {year}년 {month}월")

        deleted_folders = []
        deleted_files = []
        errors = []

        # Find all daily folders matching YYYYMM*
        month_prefix = f"{year}{month:02d}"
        all_folders = glob.glob(os.path.join(self.base_dir, f"{month_prefix}*"))

        for folder_path in all_folders:
            if os.path.isdir(folder_path):
                try:
                    shutil.rmtree(folder_path)
                    deleted_folders.append(folder_path)
                    logger.info(f"Deleted folder: {folder_path}")
                except Exception as e:
                    errors.append(f"{folder_path}: {str(e)}")
                    logger.error(f"Failed to delete {folder_path}: {e}")

        # Also delete weekly summaries for this month
        weekly_folder = os.path.join(self.base_dir, "weekly")
        if os.path.exists(weekly_folder):
            weekly_files = glob.glob(os.path.join(weekly_folder, f"weekly_summary_{month_prefix}*.md"))
            for weekly_file in weekly_files:
                try:
                    os.remove(weekly_file)
                    deleted_files.append(weekly_file)
                    logger.info(f"Deleted weekly summary: {weekly_file}")
                except Exception as e:
                    errors.append(f"{weekly_file}: {str(e)}")
                    logger.error(f"Failed to delete {weekly_file}: {e}")

        return {
            'success': len(errors) == 0,
            'deleted_folders': deleted_folders,
            'deleted_files': deleted_files,
            'errors': errors,
            'message': f"Deleted {len(deleted_folders)} folders, {len(deleted_files)} weekly files" + (f", {len(errors)} errors" if errors else "")
        }

    def save_weekly_summary(self, content: str, start_date: datetime) -> Dict:
        """
        Save weekly summary to a file

        Args:
            content: Weekly summary content
            start_date: Start date of the week

        Returns:
            Response dictionary with file information
        """
        try:
            # Create weekly folder
            week_folder = os.path.join(self.base_dir, "weekly")
            if not os.path.exists(week_folder):
                os.makedirs(week_folder)

            # Generate filename
            week_str = start_date.strftime("%Y%m%d")
            filename = f"weekly_summary_{week_str}.md"
            filepath = os.path.join(week_folder, filename)

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"Successfully saved weekly summary: {filepath}")

            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'content': content,
                'message': 'Weekly summary saved successfully'
            }

        except Exception as e:
            logger.error(f"Error saving weekly summary: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def save_monthly_summary(self, content: str, year: int, month: int) -> Dict:
        """
        Save monthly summary to a file

        Args:
            content: Monthly summary content
            year: Year (e.g., 2025)
            month: Month (e.g., 12)

        Returns:
            Response dictionary with file information
        """
        try:
            # Create monthly folder
            month_folder = os.path.join(self.base_dir, "monthly")
            if not os.path.exists(month_folder):
                os.makedirs(month_folder)

            # Generate filename
            filename = f"monthly_summary_{year}{month:02d}.md"
            filepath = os.path.join(month_folder, filename)

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.info(f"Successfully saved monthly summary: {filepath}")

            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'content': content,
                'message': 'Monthly summary saved successfully'
            }

        except Exception as e:
            logger.error(f"Error saving monthly summary: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }
