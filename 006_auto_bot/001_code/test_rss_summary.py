#!/usr/bin/env python3
"""
Test RSS feed descriptions from Bloomberg and MarketWatch
"""

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import feedparser

# Test RSS feeds
test_feeds = {
    'Bloomberg': 'https://feeds.bloomberg.com/markets/news.rss',
    'MarketWatch': 'https://www.marketwatch.com/rss/topstories',
}

print("=" * 60)
print("Testing RSS Feed Descriptions")
print("=" * 60)

for site_name, feed_url in test_feeds.items():
    print(f"\n{'='*60}")
    print(f"Site: {site_name}")
    print(f"Feed: {feed_url}")
    print('='*60)

    try:
        feed = feedparser.parse(feed_url)

        if feed.entries:
            entry = feed.entries[0]
            title = entry.get('title', 'N/A')
            summary = entry.get('summary', '') or entry.get('description', '')

            # Clean HTML if present
            from bs4 import BeautifulSoup
            if summary:
                summary_clean = BeautifulSoup(summary, 'html.parser').get_text(strip=True)
            else:
                summary_clean = ''

            print(f"\n📰 First Article:")
            print(f"Title: {title}")
            print(f"\n📝 RSS Summary ({len(summary_clean)} chars):")
            print("-" * 60)
            print(summary_clean[:400])
            print("-" * 60)

            if len(summary_clean) > 100:
                print("✅ RSS summary has sufficient content")
            else:
                print("⚠️ RSS summary is too short")

        else:
            print("❌ No entries found in feed")

    except Exception as e:
        print(f"❌ Error: {str(e)}")

print("\n" + "=" * 60)
print("Test completed!")
print("=" * 60)
