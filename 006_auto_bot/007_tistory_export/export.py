#!/usr/bin/env python3
"""
Tistory Blog Export - Entry Point
---------------------------------
티스토리 블로그 게시글을 Markdown + Image로 내보내기

Usage:
    python export.py --blog-url https://myblog.tistory.com
    python export.py --blog-url https://myblog.tistory.com --max-posts 10
    python export.py --blog-url https://myblog.tistory.com --category "개발"
    python export.py --single-post 123  # 단일 게시글만
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# 프로젝트 경로 설정
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# .env 파일 로드 (상위 디렉토리 001_code의 .env 사용)
env_paths = [
    PROJECT_ROOT / '.env',
    PROJECT_ROOT.parent / '001_code' / '.env',
    PROJECT_ROOT.parent / '.env'
]

for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded env from: {env_path}")
        break


def main():
    parser = argparse.ArgumentParser(
        description='티스토리 블로그 게시글을 Markdown으로 내보내기',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 모든 게시글 내보내기
  python export.py --blog-url https://gong-mil-le.tistory.com

  # 최근 10개만
  python export.py --blog-url https://gong-mil-le.tistory.com --max-posts 10

  # 특정 카테고리만
  python export.py --blog-url https://gong-mil-le.tistory.com --category "시장정보"

  # 단일 게시글
  python export.py --blog-url https://gong-mil-le.tistory.com --single-post 123

  # 브라우저 표시
  python export.py --blog-url https://gong-mil-le.tistory.com --no-headless

Environment Variables (in .env):
  TISTORY_BLOG_URL - 블로그 URL
  TISTORY_COOKIE_PATH - 쿠키 파일 경로
        """
    )

    # 필수/선택 인자
    parser.add_argument(
        '--blog-url',
        default=os.getenv('TISTORY_BLOG_URL', ''),
        help='티스토리 블로그 URL (예: https://myblog.tistory.com)'
    )

    parser.add_argument(
        '--export-dir',
        default='./exports',
        help='내보내기 저장 디렉토리 (기본: ./exports)'
    )

    parser.add_argument(
        '--cookie-path',
        default=os.getenv('TISTORY_COOKIE_PATH', '../001_code/cookies/tistory_cookies.pkl'),
        help='쿠키 파일 경로 (기존 로그인 세션 사용)'
    )

    parser.add_argument(
        '--method',
        choices=['auto', 'manage', 'sitemap', 'crawl'],
        default='auto',
        help='게시글 목록 가져오기 방법 (기본: auto)'
    )

    parser.add_argument(
        '--max-posts',
        type=int,
        default=None,
        help='최대 게시글 수 제한'
    )

    parser.add_argument(
        '--category',
        default=None,
        help='특정 카테고리만 필터링'
    )

    parser.add_argument(
        '--single-post',
        default=None,
        help='단일 게시글 ID만 내보내기'
    )

    parser.add_argument(
        '--headless',
        action='store_true',
        default=True,
        help='헤드리스 모드로 실행 (기본값)'
    )

    parser.add_argument(
        '--no-headless',
        dest='headless',
        action='store_false',
        help='브라우저 표시 모드로 실행'
    )

    parser.add_argument(
        '--list-only',
        action='store_true',
        help='게시글 목록만 출력 (다운로드 안 함)'
    )

    args = parser.parse_args()

    # 블로그 URL 확인
    if not args.blog_url:
        print("Error: --blog-url이 필요합니다.")
        print("또는 .env 파일에 TISTORY_BLOG_URL을 설정하세요.")
        parser.print_help()
        sys.exit(1)

    # 내보내기 디렉토리 생성
    export_dir = Path(args.export_dir)
    if not export_dir.is_absolute():
        export_dir = PROJECT_ROOT / export_dir

    print("=" * 60)
    print("Tistory Blog Export Tool")
    print("=" * 60)
    print(f"Blog URL: {args.blog_url}")
    print(f"Export Dir: {export_dir}")
    print(f"Method: {args.method}")
    print(f"Headless: {args.headless}")
    if args.max_posts:
        print(f"Max Posts: {args.max_posts}")
    if args.category:
        print(f"Category Filter: {args.category}")
    if args.single_post:
        print(f"Single Post: {args.single_post}")
    print("=" * 60)

    # Exporter 임포트 및 실행
    from tistory_exporter import TistoryExporter, PostMetadata

    try:
        with TistoryExporter(
            blog_url=args.blog_url,
            export_dir=str(export_dir),
            cookie_path=args.cookie_path,
            headless=args.headless
        ) as exporter:

            # 단일 게시글 모드
            if args.single_post:
                post = PostMetadata(
                    post_id=args.single_post,
                    title=f"Post {args.single_post}",
                    url=f"{args.blog_url}/{args.single_post}",
                    date="",
                    category="",
                    tags=[],
                    visibility="public"
                )
                result = exporter.download_post(post)
                if result:
                    print(f"\nExported: {result.metadata.title}")
                    print(f"Path: {result.markdown_path}")
                    print(f"Images: {result.image_count}")
                else:
                    print("\nFailed to export post")
                return

            # 목록만 보기 모드
            if args.list_only:
                posts = []
                if args.method in ['auto', 'manage']:
                    if exporter.load_cookies() and exporter.is_logged_in():
                        posts = exporter.get_all_posts()

                if not posts and args.method in ['auto', 'sitemap']:
                    posts = exporter.get_posts_from_sitemap()

                if not posts and args.method in ['auto', 'crawl']:
                    posts = exporter.get_posts_by_crawling()

                print(f"\nFound {len(posts)} posts:")
                print("-" * 60)
                for i, post in enumerate(posts, 1):
                    print(f"{i:3}. [{post.post_id}] {post.title}")
                    print(f"     Category: {post.category or 'N/A'}")
                    print(f"     Date: {post.date or 'N/A'}")
                    print()
                return

            # 전체 내보내기
            results = exporter.export_all(
                method=args.method,
                max_posts=args.max_posts,
                category_filter=args.category
            )

            # 결과 요약
            print("\n" + "=" * 60)
            print("Export Summary")
            print("=" * 60)
            print(f"Total Exported: {len(results)} posts")
            print(f"Total Images: {sum(r.image_count for r in results)}")
            print(f"Location: {export_dir}")
            print("=" * 60)

    except KeyboardInterrupt:
        print("\n\nExport cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
