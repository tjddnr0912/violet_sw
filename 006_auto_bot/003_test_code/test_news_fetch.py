#!/usr/bin/env python3
"""
Test script for news fetching functionality
"""

import sys
import os

# Add parent directory to path to import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from news_aggregator import NewsAggregator


def test_news_fetch():
    """Test fetching news from RSS feeds"""
    print("=" * 60)
    print("Testing News Aggregator")
    print("=" * 60)

    # Test RSS feeds
    test_feeds = [
        'http://rss.cnn.com/rss/edition_world.rss',
        'https://feeds.bbci.co.uk/news/world/rss.xml',
    ]

    aggregator = NewsAggregator(test_feeds)

    print("\nFetching news from RSS feeds...")
    news_items = aggregator.fetch_news()

    print(f"\nTotal news fetched: {len(news_items)}")

    if news_items:
        print("\nFirst 3 news items:")
        print("-" * 60)
        for i, item in enumerate(news_items[:3], 1):
            print(f"\n{i}. {item['title']}")
            print(f"   Source: {item['source']}")
            print(f"   Published: {item['published_date']}")
            print(f"   Link: {item['link'][:60]}...")
            print(f"   Description: {item['description'][:100]}...")

        # Test selecting top news
        print("\n" + "=" * 60)
        print("Testing Top News Selection")
        print("=" * 60)

        top_news = aggregator.select_top_news(count=5)
        print(f"\nSelected {len(top_news)} top news items:")

        for i, item in enumerate(top_news, 1):
            print(f"{i}. [{item['source']}] {item['title'][:50]}...")

        print("\n✅ News fetch test completed successfully!")
    else:
        print("\n⚠️  No news items found. Check your internet connection or RSS feeds.")

    print("=" * 60)


if __name__ == '__main__':
    test_news_fetch()
