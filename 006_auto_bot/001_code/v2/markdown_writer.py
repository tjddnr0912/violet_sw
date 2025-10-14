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
    """Markdown file writer for news articles"""

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

    def save_post(
        self,
        title: str,
        content: str,
        news_items: List[Dict],
        tag: str = ""
    ) -> Dict:
        """
        Save blog post as markdown file

        Args:
            title: Post title
            content: Post content (HTML format, will be converted to markdown)
            news_items: List of news items used in the post
            tag: Comma-separated tags

        Returns:
            Response dictionary with file information
        """
        try:
            # Get date folder
            date_folder = self._get_date_folder()

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"news_summary_{timestamp}.md"
            filepath = os.path.join(date_folder, filename)

            # Generate markdown content
            markdown_content = self._generate_markdown(title, news_items, tag)

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)

            logger.info(f"Successfully saved markdown file: {filepath}")

            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'message': 'Markdown file saved successfully'
            }

        except Exception as e:
            logger.error(f"Error saving markdown file: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def save_raw_news(self, news_items: List[Dict]) -> Dict:
        """
        Save raw news articles in markdown format

        Args:
            news_items: List of news items with original content

        Returns:
            Response dictionary with file information
        """
        try:
            # Get date folder
            date_folder = self._get_date_folder()

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"raw_news_{timestamp}.md"
            filepath = os.path.join(date_folder, filename)

            # Generate markdown content for raw news
            markdown_content = self._generate_raw_markdown(news_items)

            # Write to file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(markdown_content)

            logger.info(f"Successfully saved raw news file: {filepath}")

            return {
                'success': True,
                'filepath': filepath,
                'filename': filename,
                'message': 'Raw news file saved successfully'
            }

        except Exception as e:
            logger.error(f"Error saving raw news file: {str(e)}")
            return {
                'success': False,
                'message': f'Error: {str(e)}'
            }

    def _generate_raw_markdown(self, news_items: List[Dict]) -> str:
        """
        Generate markdown content for raw news articles

        Args:
            news_items: List of news items

        Returns:
            Formatted markdown content with original articles
        """
        from datetime import datetime

        # Create markdown header
        current_date = datetime.now().strftime("%Y년 %m월 %d일")
        current_time = datetime.now().strftime("%H:%M:%S")

        markdown = f"""# 원본 뉴스 기사 모음

> 수집 일시: {current_date} {current_time}

---

## 📰 수집된 원본 뉴스 기사

"""

        # Add each news item
        for i, item in enumerate(news_items, 1):
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

*원본 뉴스 수집 by Automated News Bot*
"""

        return markdown

    def _generate_markdown(self, title: str, news_items: List[Dict], tag: str = "") -> str:
        """
        Generate markdown content from news items

        Args:
            title: Post title
            news_items: List of news items with summaries
            tag: Comma-separated tags

        Returns:
            Formatted markdown content
        """
        from datetime import datetime

        # Create markdown header
        current_date = datetime.now().strftime("%Y년 %m월 %d일")
        current_time = datetime.now().strftime("%H:%M:%S")

        markdown = f"""# {title}

> 생성 일시: {current_date} {current_time}
> 태그: {tag if tag else '뉴스, 글로벌뉴스, AI요약, 자동화'}

---

## 📰 오늘의 글로벌 주요 뉴스 (한국어 요약)

오늘 전세계에서 주목받고 있는 주요 뉴스를 AI가 선별하고 한국어로 요약했습니다.

---

"""

        # Group news by category
        news_by_category = {}
        for item in news_items:
            category = item.get('category', '기타')
            if category not in news_by_category:
                news_by_category[category] = []
            news_by_category[category].append(item)

        # Add news items organized by category
        category_icons = {
            '정치': '🏛️',
            '경제': '💰',
            '사회': '👥',
            '국제': '🌍',
            '문화': '🎭',
            'IT/과학': '🔬',
            '기타': '📌'
        }

        item_number = 1
        for category in ['정치', '경제', '사회', '국제', '문화', 'IT/과학', '기타']:
            if category not in news_by_category:
                continue

            icon = category_icons.get(category, '📌')
            markdown += f"\n## {icon} {category}\n\n"

            for item in news_by_category[category]:
                source = item.get('source', 'Unknown')
                item_title = item.get('title', 'No Title')
                summary = item.get('summary', item.get('description', ''))
                link = item.get('link', '')
                pub_date = item.get('published_date', datetime.now())

                # Format publication date
                if isinstance(pub_date, datetime):
                    date_str = pub_date.strftime("%Y-%m-%d %H:%M")
                else:
                    date_str = str(pub_date)

                news_section = f"""### {item_number}. {item_title}

**출처:** {source} | **발행일:** {date_str}

#### 한국어 요약

{summary}

[원문 기사 보기 →]({link})

---

"""
                markdown += news_section
                item_number += 1

        # Add footer
        markdown += """
## 📝 참고사항

※ 본 뉴스는 AI가 자동으로 수집하고 한국어로 요약한 내용입니다.
※ 정확한 정보는 원문을 참고해주시기 바랍니다.

---

*자동 뉴스 봇으로 생성됨*
"""

        return markdown
