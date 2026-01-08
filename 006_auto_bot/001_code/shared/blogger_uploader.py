#!/usr/bin/env python3
"""
Google Blogger API Uploader
---------------------------
Google Blogger API v3를 사용한 자동 포스팅 모듈
Selenium 없이 공식 API로 안정적인 업로드 가능
"""

import os
import logging
import pickle
from typing import Dict, List, Optional
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import markdown

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# OAuth2 scopes for Blogger API
SCOPES = ['https://www.googleapis.com/auth/blogger']


class BloggerUploader:
    """Google Blogger API를 사용한 자동 포스팅 클래스"""

    def __init__(
        self,
        blog_id: str,
        credentials_path: str = './credentials/blogger_credentials.json',
        token_path: str = './credentials/blogger_token.pkl'
    ):
        """
        Initialize BloggerUploader

        Args:
            blog_id: Google Blogger 블로그 ID
            credentials_path: OAuth2 클라이언트 credentials.json 파일 경로
            token_path: 저장된 토큰 파일 경로
        """
        self.blog_id = blog_id
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None
        self.creds = None

        # Ensure directories exist
        os.makedirs(os.path.dirname(credentials_path), exist_ok=True)
        os.makedirs(os.path.dirname(token_path), exist_ok=True)

        logger.info(f"BloggerUploader initialized for blog ID: {blog_id}")

    def authenticate(self) -> bool:
        """
        Google OAuth2 인증 수행

        Returns:
            True if authentication successful, False otherwise
        """
        try:
            # 저장된 토큰이 있으면 로드
            if os.path.exists(self.token_path):
                with open(self.token_path, 'rb') as token:
                    self.creds = pickle.load(token)
                logger.info("Loaded existing credentials from token file")

            # 토큰이 없거나 만료된 경우
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    # 토큰 갱신
                    logger.info("Refreshing expired credentials...")
                    self.creds.refresh(Request())
                else:
                    # 새로운 인증 필요
                    if not os.path.exists(self.credentials_path):
                        logger.error(f"Credentials file not found: {self.credentials_path}")
                        logger.error("Please download OAuth2 credentials from Google Cloud Console")
                        return False

                    logger.info("Starting new OAuth2 flow...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path, SCOPES
                    )
                    self.creds = flow.run_local_server(port=0)

                # 토큰 저장
                with open(self.token_path, 'wb') as token:
                    pickle.dump(self.creds, token)
                logger.info(f"Credentials saved to {self.token_path}")

            # Blogger API 서비스 생성
            self.service = build('blogger', 'v3', credentials=self.creds)
            logger.info("Blogger API service created successfully")
            return True

        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return False

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        return self.service is not None and self.creds is not None and self.creds.valid

    def convert_markdown_to_html(self, markdown_content: str) -> str:
        """Convert markdown content to HTML"""
        html = markdown.markdown(
            markdown_content,
            extensions=['extra', 'codehilite', 'tables', 'toc', 'nl2br']
        )
        return html

    def get_blog_info(self) -> Optional[Dict]:
        """
        블로그 정보 조회

        Returns:
            Blog info dictionary or None
        """
        try:
            if not self.is_authenticated():
                if not self.authenticate():
                    return None

            blog = self.service.blogs().get(blogId=self.blog_id).execute()
            logger.info(f"Blog: {blog.get('name')} ({blog.get('url')})")
            return blog

        except Exception as e:
            logger.error(f"Failed to get blog info: {e}")
            return None

    def upload_post(
        self,
        title: str,
        content: str,
        labels: Optional[List[str]] = None,
        is_draft: bool = False,
        is_markdown: bool = True
    ) -> Dict:
        """
        블로그에 게시글 업로드

        Args:
            title: 게시글 제목
            content: 게시글 내용 (markdown 또는 HTML)
            labels: 라벨(태그) 리스트
            is_draft: True면 임시저장, False면 즉시 발행
            is_markdown: True면 마크다운을 HTML로 변환

        Returns:
            Dictionary with upload result
        """
        try:
            logger.info(f"Uploading post: {title[:50]}...")

            # 인증 확인
            if not self.is_authenticated():
                if not self.authenticate():
                    return {
                        'success': False,
                        'message': 'Authentication failed. Run setup_auth() first.'
                    }

            # 마크다운 변환
            if is_markdown:
                html_content = self.convert_markdown_to_html(content)
            else:
                html_content = content

            # 게시글 데이터 구성
            post_body = {
                'kind': 'blogger#post',
                'blog': {'id': self.blog_id},
                'title': title,
                'content': html_content
            }

            # 라벨 추가
            if labels:
                post_body['labels'] = labels

            # 게시글 생성
            if is_draft:
                # 임시저장
                result = self.service.posts().insert(
                    blogId=self.blog_id,
                    body=post_body,
                    isDraft=True
                ).execute()
                logger.info(f"Draft saved: {result.get('url', 'N/A')}")
            else:
                # 즉시 발행
                result = self.service.posts().insert(
                    blogId=self.blog_id,
                    body=post_body,
                    isDraft=False
                ).execute()
                logger.info(f"Post published: {result.get('url', 'N/A')}")

            return {
                'success': True,
                'url': result.get('url'),
                'post_id': result.get('id'),
                'message': 'Post uploaded successfully'
            }

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    def update_post(
        self,
        post_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        labels: Optional[List[str]] = None,
        is_markdown: bool = True
    ) -> Dict:
        """
        기존 게시글 수정

        Args:
            post_id: 수정할 게시글 ID
            title: 새 제목 (None이면 변경 안함)
            content: 새 내용 (None이면 변경 안함)
            labels: 새 라벨 (None이면 변경 안함)
            is_markdown: content가 마크다운인지 여부

        Returns:
            Dictionary with update result
        """
        try:
            if not self.is_authenticated():
                if not self.authenticate():
                    return {
                        'success': False,
                        'message': 'Authentication failed'
                    }

            # 기존 게시글 조회
            existing = self.service.posts().get(
                blogId=self.blog_id,
                postId=post_id
            ).execute()

            # 업데이트할 내용 구성
            post_body = {
                'kind': 'blogger#post',
                'id': post_id,
                'blog': {'id': self.blog_id},
                'title': title if title else existing.get('title'),
                'content': self.convert_markdown_to_html(content) if content and is_markdown else (content if content else existing.get('content'))
            }

            if labels is not None:
                post_body['labels'] = labels

            # 업데이트 실행
            result = self.service.posts().update(
                blogId=self.blog_id,
                postId=post_id,
                body=post_body
            ).execute()

            return {
                'success': True,
                'url': result.get('url'),
                'message': 'Post updated successfully'
            }

        except Exception as e:
            logger.error(f"Update failed: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    def delete_post(self, post_id: str) -> Dict:
        """
        게시글 삭제

        Args:
            post_id: 삭제할 게시글 ID

        Returns:
            Dictionary with delete result
        """
        try:
            if not self.is_authenticated():
                if not self.authenticate():
                    return {
                        'success': False,
                        'message': 'Authentication failed'
                    }

            self.service.posts().delete(
                blogId=self.blog_id,
                postId=post_id
            ).execute()

            return {
                'success': True,
                'message': 'Post deleted successfully'
            }

        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return {
                'success': False,
                'message': str(e)
            }

    def list_posts(self, max_results: int = 10) -> List[Dict]:
        """
        최근 게시글 목록 조회

        Args:
            max_results: 조회할 최대 게시글 수

        Returns:
            List of post dictionaries
        """
        try:
            if not self.is_authenticated():
                if not self.authenticate():
                    return []

            result = self.service.posts().list(
                blogId=self.blog_id,
                maxResults=max_results
            ).execute()

            posts = result.get('items', [])
            logger.info(f"Found {len(posts)} posts")
            return posts

        except Exception as e:
            logger.error(f"Failed to list posts: {e}")
            return []

    def setup_auth(self):
        """
        초기 인증 설정 (최초 1회 실행)

        이 메서드를 실행하면 브라우저가 열리고 Google 로그인 후
        권한 승인을 요청합니다. 승인 후 토큰이 저장됩니다.
        """
        logger.info("=" * 60)
        logger.info("GOOGLE BLOGGER API 인증 설정")
        logger.info("=" * 60)
        logger.info("")
        logger.info("사전 준비사항:")
        logger.info("1. Google Cloud Console (https://console.cloud.google.com)")
        logger.info("2. 새 프로젝트 생성 또는 기존 프로젝트 선택")
        logger.info("3. 'Blogger API v3' 활성화")
        logger.info("4. OAuth 2.0 클라이언트 ID 생성 (데스크톱 앱)")
        logger.info("5. credentials.json 다운로드")
        logger.info(f"6. {self.credentials_path}에 저장")
        logger.info("")
        logger.info("=" * 60)

        if not os.path.exists(self.credentials_path):
            logger.error(f"credentials.json을 {self.credentials_path}에 저장해주세요")
            return False

        # 인증 진행
        if self.authenticate():
            logger.info("")
            logger.info("=" * 60)
            logger.info("인증 완료!")
            logger.info(f"토큰이 {self.token_path}에 저장되었습니다.")
            logger.info("이제 자동 포스팅이 가능합니다.")
            logger.info("=" * 60)

            # 블로그 정보 확인
            blog_info = self.get_blog_info()
            if blog_info:
                logger.info(f"연결된 블로그: {blog_info.get('name')}")
                logger.info(f"블로그 URL: {blog_info.get('url')}")

            return True
        else:
            logger.error("인증 실패")
            return False

    def __enter__(self):
        """Context manager entry"""
        if not self.is_authenticated():
            self.authenticate()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        pass


# CLI interface for testing
if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description='Google Blogger API Uploader')
    parser.add_argument('--blog-id', default=os.getenv('BLOGGER_BLOG_ID', ''),
                        help='Blogger Blog ID')
    parser.add_argument('--setup', action='store_true',
                        help='Setup authentication (run once)')
    parser.add_argument('--check', action='store_true',
                        help='Check authentication status')
    parser.add_argument('--list', action='store_true',
                        help='List recent posts')
    parser.add_argument('--info', action='store_true',
                        help='Show blog info')
    parser.add_argument('--test-post', action='store_true',
                        help='Create a test post (draft)')

    args = parser.parse_args()

    if not args.blog_id:
        print("Error: --blog-id is required or set BLOGGER_BLOG_ID in .env")
        print("")
        print("블로그 ID 확인 방법:")
        print("1. Blogger 대시보드 (https://www.blogger.com) 접속")
        print("2. 블로그 선택 후 URL 확인")
        print("3. URL: https://www.blogger.com/blog/posts/XXXXXXXXX")
        print("   여기서 XXXXXXXXX가 블로그 ID입니다")
        parser.print_help()
        exit(1)

    uploader = BloggerUploader(
        blog_id=args.blog_id,
        credentials_path=os.getenv('BLOGGER_CREDENTIALS_PATH', './credentials/blogger_credentials.json'),
        token_path=os.getenv('BLOGGER_TOKEN_PATH', './credentials/blogger_token.pkl')
    )

    if args.setup:
        uploader.setup_auth()

    elif args.check:
        if uploader.authenticate():
            print("Authentication status: OK")
            blog_info = uploader.get_blog_info()
            if blog_info:
                print(f"Blog: {blog_info.get('name')}")
                print(f"URL: {blog_info.get('url')}")
        else:
            print("Authentication status: FAILED")
            print("Run: python blogger_uploader.py --setup")

    elif args.list:
        posts = uploader.list_posts(max_results=5)
        if posts:
            print(f"\nRecent {len(posts)} posts:")
            for post in posts:
                print(f"  - [{post.get('id')}] {post.get('title')}")
                print(f"    URL: {post.get('url')}")
        else:
            print("No posts found or authentication failed")

    elif args.info:
        blog_info = uploader.get_blog_info()
        if blog_info:
            print(f"Blog Name: {blog_info.get('name')}")
            print(f"Blog URL: {blog_info.get('url')}")
            print(f"Blog ID: {blog_info.get('id')}")
            print(f"Posts: {blog_info.get('posts', {}).get('totalItems', 0)}")

    elif args.test_post:
        result = uploader.upload_post(
            title=f"테스트 포스트 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            content="# 테스트\n\n이것은 **테스트** 포스트입니다.\n\n- 항목 1\n- 항목 2",
            labels=['테스트', '자동화'],
            is_draft=True,
            is_markdown=True
        )
        if result['success']:
            print(f"Test post created (draft): {result.get('url')}")
        else:
            print(f"Failed: {result['message']}")

    else:
        parser.print_help()
        print("\n" + "=" * 60)
        print("QUICK START:")
        print("=" * 60)
        print("1. Google Cloud Console에서 credentials.json 다운로드")
        print("2. ./credentials/blogger_credentials.json에 저장")
        print("3. python blogger_uploader.py --blog-id YOUR_BLOG_ID --setup")
        print("=" * 60)
