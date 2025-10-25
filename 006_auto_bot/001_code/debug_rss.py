#!/usr/bin/env python3
"""
Debug RSS feed parsing
"""

import ssl
import certifi
import feedparser

# Set SSL context to use certifi certificates
ssl._create_default_https_context = ssl._create_unverified_context

# Test URLs
test_urls = [
    'https://www.hankyung.com/feed/economy',
    'https://www.mk.co.kr/rss/40300001/',
    'https://www.blockmedia.co.kr/feed',
    'https://www.tokenpost.kr/rss/news',
]

for url in test_urls:
    print(f"\n{'='*60}")
    print(f"Testing: {url}")
    print('='*60)

    try:
        feed = feedparser.parse(url)

        print(f"Feed status: {feed.get('status', 'N/A')}")
        print(f"Feed version: {feed.get('version', 'N/A')}")
        print(f"Number of entries: {len(feed.entries)}")

        if feed.entries:
            print("\nFirst entry:")
            entry = feed.entries[0]
            print(f"  Title: {entry.get('title', 'N/A')}")
            print(f"  Link: {entry.get('link', 'N/A')}")
            print(f"  Published: {entry.get('published', 'N/A')}")
            print(f"  Has published_parsed: {hasattr(entry, 'published_parsed')}")
            if hasattr(entry, 'published_parsed'):
                print(f"  Published parsed: {entry.published_parsed}")
        else:
            print("  ⚠️ No entries found!")
            print(f"  Feed keys: {feed.keys()}")
            if 'bozo_exception' in feed:
                print(f"  Bozo exception: {feed.bozo_exception}")

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
