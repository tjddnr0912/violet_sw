#!/usr/bin/env python3
"""
Tistory Blog Export Tool
------------------------
티스토리 블로그 게시글을 Markdown + Image 조합으로 로컬에 다운로드합니다.

Features:
- 모든 게시글 또는 특정 카테고리만 다운로드
- HTML을 깔끔한 Markdown으로 변환
- 이미지 로컬 다운로드 및 경로 자동 변환
- 게시글 메타데이터 (날짜, 카테고리, 태그) 보존
"""

import os
import re
import time
import pickle
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, asdict
import json

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from tqdm import tqdm

from html_to_markdown import HTMLToMarkdownConverter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class PostMetadata:
    """게시글 메타데이터"""
    post_id: str
    title: str
    url: str
    date: str
    category: str
    tags: List[str]
    visibility: str  # public, private, protected


@dataclass
class ExportedPost:
    """내보내기된 게시글 정보"""
    metadata: PostMetadata
    markdown_path: str
    images_dir: str
    image_count: int


class TistoryExporter:
    """티스토리 블로그 게시글 내보내기 클래스"""

    def __init__(
        self,
        blog_url: str,
        export_dir: str = './exports',
        cookie_path: str = None,
        user_data_dir: str = None,
        headless: bool = True
    ):
        """
        Initialize TistoryExporter

        Args:
            blog_url: 티스토리 블로그 URL (예: 'https://myblog.tistory.com')
            export_dir: 내보내기 저장 디렉토리
            cookie_path: 쿠키 파일 경로 (기존 001_code의 쿠키 사용 가능)
            user_data_dir: Chrome 프로필 디렉토리
            headless: 헤드리스 모드 여부
        """
        self.blog_url = blog_url.rstrip('/')
        self.blog_name = urlparse(blog_url).netloc.split('.')[0]
        self.export_dir = Path(export_dir)
        self.cookie_path = cookie_path
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.driver = None
        self.wait = None
        self.session = requests.Session()

        # HTML to Markdown converter
        self.md_converter = HTMLToMarkdownConverter()

        # Ensure export directory exists
        self.export_dir.mkdir(parents=True, exist_ok=True)

        # Initialize driver
        self._init_driver()

    def _init_driver(self):
        """Initialize Chrome WebDriver"""
        options = Options()

        if self.headless:
            options.add_argument("--headless=new")

        # Anti-detection settings
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # User data directory
        if self.user_data_dir:
            options.add_argument(f"--user-data-dir={self.user_data_dir}")

        # Stability options
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")
        options.add_argument("--lang=ko_KR")

        # User-Agent
        options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 15)

        # Hide navigator.webdriver
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"}
        )

        logger.info("Chrome WebDriver initialized")

    def load_cookies(self) -> bool:
        """Load cookies from file"""
        if not self.cookie_path or not os.path.exists(self.cookie_path):
            logger.warning(f"Cookie file not found: {self.cookie_path}")
            return False

        try:
            # Navigate to Tistory domain first
            self.driver.get("https://www.tistory.com")
            time.sleep(2)

            with open(self.cookie_path, 'rb') as f:
                cookies = pickle.load(f)

            for cookie in cookies:
                cookie.pop('sameSite', None)
                cookie.pop('expiry', None)
                try:
                    self.driver.add_cookie(cookie)
                except Exception as e:
                    logger.debug(f"Skipping cookie: {e}")

            # Also add cookies to requests session
            for cookie in cookies:
                self.session.cookies.set(
                    cookie.get('name', ''),
                    cookie.get('value', ''),
                    domain=cookie.get('domain', '')
                )

            logger.info(f"Cookies loaded from {self.cookie_path}")
            self.driver.refresh()
            time.sleep(2)
            return True

        except Exception as e:
            logger.error(f"Failed to load cookies: {e}")
            return False

    def is_logged_in(self) -> bool:
        """Check if logged in to Tistory"""
        try:
            self.driver.get(f"{self.blog_url}/manage")
            time.sleep(3)

            current_url = self.driver.current_url
            if "tistory.com/auth/login" in current_url:
                return False

            if "/manage" in current_url and "login" not in current_url:
                logger.info("Login verified")
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking login: {e}")
            return False

    def get_all_posts(self, max_pages: int = 100) -> List[PostMetadata]:
        """
        관리자 페이지에서 모든 게시글 목록 가져오기

        Args:
            max_pages: 최대 페이지 수 (안전장치)

        Returns:
            게시글 메타데이터 리스트
        """
        posts = []
        page = 1

        logger.info("Fetching post list from manage page...")

        while page <= max_pages:
            url = f"{self.blog_url}/manage/posts?page={page}"
            self.driver.get(url)
            time.sleep(2)

            try:
                # 게시글 목록 테이블 찾기
                table_selectors = [
                    "table.table_post tbody tr",
                    ".list_post li",
                    ".post-list .post-item",
                    "table tbody tr[data-id]",
                    ".mce-list tr"
                ]

                rows = []
                for selector in table_selectors:
                    rows = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if rows:
                        logger.debug(f"Found posts with selector: {selector}")
                        break

                if not rows:
                    logger.info(f"No more posts found on page {page}")
                    break

                # 각 행에서 게시글 정보 추출
                for row in rows:
                    try:
                        post = self._parse_post_row(row)
                        if post:
                            posts.append(post)
                    except Exception as e:
                        logger.debug(f"Error parsing row: {e}")
                        continue

                logger.info(f"Page {page}: Found {len(rows)} posts (Total: {len(posts)})")

                # 다음 페이지 확인
                try:
                    next_btn = self.driver.find_element(
                        By.CSS_SELECTOR,
                        ".pagination .next:not(.disabled), .paging .btn_next:not(.disabled)"
                    )
                    if not next_btn.is_enabled():
                        break
                except NoSuchElementException:
                    # 다음 페이지 버튼이 없으면 종료
                    if page > 1:
                        break

                page += 1

            except Exception as e:
                logger.error(f"Error fetching page {page}: {e}")
                break

        logger.info(f"Total posts found: {len(posts)}")
        return posts

    def _parse_post_row(self, row) -> Optional[PostMetadata]:
        """테이블 행에서 게시글 정보 추출"""
        try:
            # 게시글 ID
            post_id = row.get_attribute('data-id')
            if not post_id:
                # data-id가 없으면 링크에서 추출
                link = row.find_element(By.CSS_SELECTOR, "a[href*='/manage/post/']")
                href = link.get_attribute('href')
                match = re.search(r'/manage/post/(\d+)', href)
                if match:
                    post_id = match.group(1)

            if not post_id:
                return None

            # 제목
            title_elem = row.find_element(By.CSS_SELECTOR, ".title a, .post-title, td.title a")
            title = title_elem.text.strip()

            # URL
            post_url = f"{self.blog_url}/{post_id}"

            # 날짜
            date = ""
            try:
                date_elem = row.find_element(By.CSS_SELECTOR, ".date, .post-date, td.date")
                date = date_elem.text.strip()
            except:
                pass

            # 카테고리
            category = ""
            try:
                cat_elem = row.find_element(By.CSS_SELECTOR, ".category, .post-category, td.category")
                category = cat_elem.text.strip()
            except:
                pass

            # 공개 상태
            visibility = "public"
            try:
                vis_elem = row.find_element(By.CSS_SELECTOR, ".ico_secret, .private, [class*='secret']")
                if vis_elem:
                    visibility = "private"
            except:
                pass

            return PostMetadata(
                post_id=post_id,
                title=title,
                url=post_url,
                date=date,
                category=category,
                tags=[],
                visibility=visibility
            )

        except Exception as e:
            logger.debug(f"Parse error: {e}")
            return None

    def get_posts_from_sitemap(self) -> List[PostMetadata]:
        """
        sitemap.xml에서 게시글 목록 가져오기 (로그인 불필요)

        Returns:
            게시글 메타데이터 리스트
        """
        posts = []
        sitemap_urls = [
            f"{self.blog_url}/sitemap.xml",
            f"{self.blog_url}/sitemap",
            f"{self.blog_url}/rss"
        ]

        for sitemap_url in sitemap_urls:
            try:
                response = self.session.get(sitemap_url, timeout=10)
                if response.status_code != 200:
                    continue

                soup = BeautifulSoup(response.content, 'xml')

                # sitemap.xml 파싱
                urls = soup.find_all('url')
                for url in urls:
                    loc = url.find('loc')
                    if not loc:
                        continue

                    post_url = loc.text.strip()

                    # 게시글 URL 패턴 확인
                    match = re.search(r'/(\d+)$', post_url)
                    if not match:
                        continue

                    post_id = match.group(1)

                    # 날짜 추출
                    lastmod = url.find('lastmod')
                    date = lastmod.text.strip() if lastmod else ""

                    posts.append(PostMetadata(
                        post_id=post_id,
                        title=f"Post {post_id}",  # 실제 제목은 나중에 채움
                        url=post_url,
                        date=date,
                        category="",
                        tags=[],
                        visibility="public"
                    ))

                if posts:
                    logger.info(f"Found {len(posts)} posts from {sitemap_url}")
                    break

            except Exception as e:
                logger.debug(f"Error fetching {sitemap_url}: {e}")
                continue

        return posts

    def get_posts_by_crawling(self, max_posts: int = 500) -> List[PostMetadata]:
        """
        블로그 페이지를 크롤링하여 게시글 목록 가져오기

        Args:
            max_posts: 최대 게시글 수

        Returns:
            게시글 메타데이터 리스트
        """
        posts = []
        visited_ids = set()
        page = 1

        logger.info("Crawling blog pages to find posts...")

        while len(posts) < max_posts:
            # 페이지 URL 패턴 시도
            page_urls = [
                f"{self.blog_url}?page={page}",
                f"{self.blog_url}/page/{page}",
                f"{self.blog_url}/index?page={page}"
            ]

            found_new = False

            for page_url in page_urls:
                try:
                    self.driver.get(page_url)
                    time.sleep(2)

                    # 게시글 링크 찾기
                    link_patterns = [
                        f"a[href*='{self.blog_url}/'][href$=re.compile(r'\\d+')]",
                        ".post-item a",
                        ".article-title a",
                        "article a[href*='/']",
                        ".entry-title a",
                        "h2 a, h3 a"
                    ]

                    links = self.driver.find_elements(By.CSS_SELECTOR, "a")

                    for link in links:
                        href = link.get_attribute('href')
                        if not href:
                            continue

                        # 게시글 URL 패턴 확인 (숫자 ID로 끝나는 URL)
                        if self.blog_url in href:
                            match = re.search(r'/(\d+)$', href)
                            if match:
                                post_id = match.group(1)

                                if post_id in visited_ids:
                                    continue

                                visited_ids.add(post_id)
                                found_new = True

                                # 제목 추출 시도
                                title = link.text.strip()
                                if not title:
                                    title = f"Post {post_id}"

                                posts.append(PostMetadata(
                                    post_id=post_id,
                                    title=title,
                                    url=href,
                                    date="",
                                    category="",
                                    tags=[],
                                    visibility="public"
                                ))

                    if found_new:
                        break

                except Exception as e:
                    logger.debug(f"Error on {page_url}: {e}")
                    continue

            if not found_new:
                break

            page += 1
            logger.info(f"Page {page}: Found {len(posts)} posts so far...")

        logger.info(f"Total posts found by crawling: {len(posts)}")
        return posts

    def download_post(self, post: PostMetadata) -> Optional[ExportedPost]:
        """
        단일 게시글 다운로드 및 변환

        Args:
            post: 게시글 메타데이터

        Returns:
            ExportedPost 객체 또는 None
        """
        try:
            # 게시글 페이지 로드
            self.driver.get(post.url)
            time.sleep(2)

            # 페이지 소스 파싱
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # 제목 업데이트
            title = self._extract_title(soup) or post.title

            # 본문 HTML 추출
            content_html = self._extract_content(soup)
            if not content_html:
                logger.warning(f"No content found for post {post.post_id}")
                return None

            # 날짜 추출
            date = self._extract_date(soup) or post.date

            # 카테고리 추출
            category = self._extract_category(soup) or post.category

            # 태그 추출
            tags = self._extract_tags(soup)

            # 메타데이터 업데이트
            post.title = title
            post.date = date
            post.category = category
            post.tags = tags

            # 게시글 저장 디렉토리 생성
            safe_title = self._sanitize_filename(title)
            post_dir = self.export_dir / f"{post.post_id}_{safe_title}"
            post_dir.mkdir(parents=True, exist_ok=True)

            # 이미지 디렉토리
            images_dir = post_dir / "images"
            images_dir.mkdir(exist_ok=True)

            # 이미지 다운로드 및 경로 변환
            content_html, image_count = self._download_images(content_html, images_dir)

            # HTML을 Markdown으로 변환
            markdown_content = self.md_converter.convert(content_html)

            # 메타데이터를 YAML 프론트매터로 추가
            frontmatter = self._create_frontmatter(post)
            full_markdown = frontmatter + "\n\n" + markdown_content

            # Markdown 파일 저장
            md_path = post_dir / "README.md"
            md_path.write_text(full_markdown, encoding='utf-8')

            # 메타데이터 JSON 저장
            meta_path = post_dir / "metadata.json"
            meta_path.write_text(json.dumps(asdict(post), ensure_ascii=False, indent=2), encoding='utf-8')

            logger.info(f"Exported: {title} ({image_count} images)")

            return ExportedPost(
                metadata=post,
                markdown_path=str(md_path),
                images_dir=str(images_dir),
                image_count=image_count
            )

        except Exception as e:
            logger.error(f"Error downloading post {post.post_id}: {e}")
            return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """페이지에서 제목 추출"""
        selectors = [
            ".entry-title",
            ".post-title",
            ".article-title",
            "h1.title",
            ".tit_post",
            "header h1",
            "article h1",
            "h1"
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem and elem.text.strip():
                return elem.text.strip()

        return None

    def _extract_content(self, soup: BeautifulSoup) -> Optional[str]:
        """페이지에서 본문 HTML 추출"""
        selectors = [
            ".entry-content",
            ".post-content",
            ".article-content",
            ".contents_style",
            "#content",
            ".post-body",
            "article .content",
            ".tt_article_useless_p_margin",
            ".area_view"
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                # 불필요한 요소 제거
                for unwanted in elem.select('script, style, .ad, .advertisement, .related-posts'):
                    unwanted.decompose()
                return str(elem)

        return None

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """페이지에서 날짜 추출"""
        selectors = [
            ".entry-date",
            ".post-date",
            "time",
            ".date",
            ".created",
            "[datetime]"
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                # datetime 속성 우선
                if elem.get('datetime'):
                    return elem.get('datetime')
                if elem.text.strip():
                    return elem.text.strip()

        return None

    def _extract_category(self, soup: BeautifulSoup) -> Optional[str]:
        """페이지에서 카테고리 추출"""
        selectors = [
            ".category a",
            ".post-category",
            ".entry-category",
            ".cat-links a",
            "[rel='category'] a"
        ]

        for selector in selectors:
            elem = soup.select_one(selector)
            if elem and elem.text.strip():
                return elem.text.strip()

        return None

    def _extract_tags(self, soup: BeautifulSoup) -> List[str]:
        """페이지에서 태그 추출"""
        tags = []
        selectors = [
            ".tags a",
            ".post-tags a",
            ".entry-tags a",
            ".tag-links a",
            "[rel='tag']"
        ]

        for selector in selectors:
            elems = soup.select(selector)
            for elem in elems:
                tag = elem.text.strip()
                if tag and tag not in tags:
                    tags.append(tag)

        return tags

    def _download_images(self, html: str, images_dir: Path) -> Tuple[str, int]:
        """
        HTML 내 이미지를 다운로드하고 경로를 로컬로 변경

        Args:
            html: 원본 HTML
            images_dir: 이미지 저장 디렉토리

        Returns:
            (수정된 HTML, 다운로드된 이미지 수)
        """
        soup = BeautifulSoup(html, 'html.parser')
        img_tags = soup.find_all('img')
        downloaded = 0

        for img in img_tags:
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if not src:
                continue

            try:
                # 절대 URL로 변환
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = self.blog_url + src
                elif not src.startswith('http'):
                    src = urljoin(self.blog_url, src)

                # 이미지 다운로드
                response = self.session.get(src, timeout=30)
                if response.status_code != 200:
                    logger.debug(f"Failed to download: {src}")
                    continue

                # 파일명 생성
                ext = self._get_image_extension(response, src)
                filename = f"img_{downloaded:03d}{ext}"
                filepath = images_dir / filename

                # 이미지 저장
                filepath.write_bytes(response.content)

                # HTML에서 경로 변경
                img['src'] = f"images/{filename}"
                img.pop('data-src', None)
                img.pop('data-lazy-src', None)

                downloaded += 1

            except Exception as e:
                logger.debug(f"Image download error: {e}")
                continue

        return str(soup), downloaded

    def _get_image_extension(self, response: requests.Response, url: str) -> str:
        """이미지 확장자 결정"""
        content_type = response.headers.get('Content-Type', '')

        type_map = {
            'image/jpeg': '.jpg',
            'image/png': '.png',
            'image/gif': '.gif',
            'image/webp': '.webp',
            'image/svg+xml': '.svg'
        }

        for mime, ext in type_map.items():
            if mime in content_type:
                return ext

        # URL에서 추출
        parsed = urlparse(url)
        path = parsed.path.lower()
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']:
            if path.endswith(ext):
                return ext if ext != '.jpeg' else '.jpg'

        return '.jpg'  # 기본값

    def _sanitize_filename(self, filename: str, max_length: int = 50) -> str:
        """파일명에 사용할 수 없는 문자 제거"""
        # 특수문자 제거
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 공백을 언더스코어로
        filename = re.sub(r'\s+', '_', filename)
        # 길이 제한
        if len(filename) > max_length:
            filename = filename[:max_length]
        return filename.strip('_.')

    def _create_frontmatter(self, post: PostMetadata) -> str:
        """YAML 프론트매터 생성"""
        lines = [
            "---",
            f"title: \"{post.title}\"",
            f"date: {post.date}",
            f"category: \"{post.category}\"",
            f"tags: [{', '.join(f'\"{t}\"' for t in post.tags)}]",
            f"url: {post.url}",
            f"post_id: {post.post_id}",
            f"visibility: {post.visibility}",
            "---"
        ]
        return '\n'.join(lines)

    def export_all(
        self,
        method: str = 'auto',
        max_posts: Optional[int] = None,
        category_filter: Optional[str] = None
    ) -> List[ExportedPost]:
        """
        모든 게시글 내보내기

        Args:
            method: 게시글 목록 가져오기 방법
                   'manage' - 관리자 페이지 (로그인 필요)
                   'sitemap' - sitemap.xml (로그인 불필요)
                   'crawl' - 블로그 페이지 크롤링
                   'auto' - 자동 선택
            max_posts: 최대 게시글 수 제한
            category_filter: 특정 카테고리만 필터링

        Returns:
            ExportedPost 리스트
        """
        # 게시글 목록 가져오기
        posts = []

        if method == 'auto':
            # 로그인 상태 확인
            if self.cookie_path and self.load_cookies() and self.is_logged_in():
                method = 'manage'
            else:
                method = 'sitemap'

        logger.info(f"Using method: {method}")

        if method == 'manage':
            if not self.is_logged_in():
                if not self.load_cookies() or not self.is_logged_in():
                    logger.error("Login required for manage method")
                    logger.info("Falling back to sitemap method...")
                    method = 'sitemap'

            if method == 'manage':
                posts = self.get_all_posts()

        if method == 'sitemap' or not posts:
            posts = self.get_posts_from_sitemap()

        if method == 'crawl' or not posts:
            posts = self.get_posts_by_crawling()

        if not posts:
            logger.error("No posts found!")
            return []

        # 필터링
        if category_filter:
            posts = [p for p in posts if category_filter.lower() in p.category.lower()]
            logger.info(f"Filtered to {len(posts)} posts in category '{category_filter}'")

        if max_posts:
            posts = posts[:max_posts]
            logger.info(f"Limited to {len(posts)} posts")

        # 각 게시글 다운로드
        exported = []

        for post in tqdm(posts, desc="Downloading posts"):
            result = self.download_post(post)
            if result:
                exported.append(result)
            time.sleep(1)  # Rate limiting

        # 내보내기 요약 저장
        summary_path = self.export_dir / "export_summary.json"
        summary = {
            'blog_url': self.blog_url,
            'export_date': datetime.now().isoformat(),
            'total_posts': len(posts),
            'exported_posts': len(exported),
            'total_images': sum(e.image_count for e in exported),
            'posts': [
                {
                    'post_id': e.metadata.post_id,
                    'title': e.metadata.title,
                    'path': e.markdown_path,
                    'images': e.image_count
                }
                for e in exported
            ]
        }
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

        logger.info(f"\nExport completed!")
        logger.info(f"Total posts: {len(posts)}")
        logger.info(f"Exported: {len(exported)}")
        logger.info(f"Total images: {sum(e.image_count for e in exported)}")
        logger.info(f"Saved to: {self.export_dir}")

        return exported

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()
            self.driver = None
            logger.info("Browser closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv

    # 상위 디렉토리의 .env 파일 로드
    env_path = Path(__file__).parent.parent / '001_code' / '.env'
    if env_path.exists():
        load_dotenv(env_path)
    else:
        load_dotenv()

    parser = argparse.ArgumentParser(description='Tistory Blog Export Tool')
    parser.add_argument('--blog-url', default=os.getenv('TISTORY_BLOG_URL', ''),
                       help='Tistory blog URL')
    parser.add_argument('--export-dir', default='./exports',
                       help='Export directory (default: ./exports)')
    parser.add_argument('--cookie-path',
                       default=os.getenv('TISTORY_COOKIE_PATH', '../001_code/cookies/tistory_cookies.pkl'),
                       help='Cookie file path')
    parser.add_argument('--method', choices=['auto', 'manage', 'sitemap', 'crawl'],
                       default='auto', help='Method to fetch post list')
    parser.add_argument('--max-posts', type=int, default=None,
                       help='Maximum number of posts to export')
    parser.add_argument('--category', default=None,
                       help='Filter by category')
    parser.add_argument('--headless', action='store_true', default=True,
                       help='Run in headless mode')
    parser.add_argument('--no-headless', dest='headless', action='store_false',
                       help='Run with visible browser')

    args = parser.parse_args()

    if not args.blog_url:
        print("Error: --blog-url is required or set TISTORY_BLOG_URL in .env")
        parser.print_help()
        exit(1)

    with TistoryExporter(
        blog_url=args.blog_url,
        export_dir=args.export_dir,
        cookie_path=args.cookie_path,
        headless=args.headless
    ) as exporter:
        exporter.export_all(
            method=args.method,
            max_posts=args.max_posts,
            category_filter=args.category
        )
