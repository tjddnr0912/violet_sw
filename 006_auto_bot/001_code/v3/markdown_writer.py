import os
from datetime import datetime
from typing import Dict, List
import logging

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
            '기타': '📌'
        }

        # Add each category section
        for category in ['정치', '경제', '사회', '국제', '문화', 'IT/과학', '기타']:
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
