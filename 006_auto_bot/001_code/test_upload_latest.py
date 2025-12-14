#!/usr/bin/env python3
"""Test uploading the latest blog summary to Tistory"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from tistory_selenium_uploader import TistorySeleniumUploader

# Configuration
BLOG_URL = os.getenv('TISTORY_BLOG_URL', 'https://gong-mil-le.tistory.com')
COOKIE_PATH = './cookies/tistory_cookies.pkl'

# Latest summary file
SUMMARY_FILE = '../004_News_paper/20251212/blog_summary_20251212_003450.md'

def main():
    print("=" * 60)
    print("Tistory Upload Test - Latest Blog Summary")
    print("=" * 60)

    # Read summary content
    with open(SUMMARY_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    print(f"File: {SUMMARY_FILE}")
    print(f"Content length: {len(content)} characters")
    print(f"Preview:\n{content[:300]}...")
    print("=" * 60)

    # Initialize uploader (non-headless for debugging)
    uploader = TistorySeleniumUploader(
        blog_url=BLOG_URL,
        cookie_path=COOKIE_PATH,
        headless=False  # Show browser for debugging
    )

    try:
        # Upload post
        result = uploader.upload_post(
            title="[TEST] 2025년 12월 12일 뉴스 블로그 요약",
            content=content,
            category="",
            tags=["뉴스", "AI요약", "테스트"],
            visibility="private",  # Private for testing
            is_markdown=True
        )

        print("\n" + "=" * 60)
        print(f"Result: {'SUCCESS' if result['success'] else 'FAILED'}")
        print(f"Message: {result.get('message', 'N/A')}")
        if result.get('url'):
            print(f"URL: {result['url']}")
        print("=" * 60)

    finally:
        print("\n>>> 10초 후 브라우저가 닫힙니다...")
        import time as t
        t.sleep(10)
        uploader.close()

if __name__ == "__main__":
    main()
