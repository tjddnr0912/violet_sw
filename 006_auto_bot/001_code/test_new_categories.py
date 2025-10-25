#!/usr/bin/env python3
"""
Test new stock and crypto categories
"""

import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

from v3.config import config
from v3.news_aggregator import NewsAggregator
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

print("=" * 60)
print("Testing New Stock & Crypto Categories")
print("=" * 60)

# Test stock category feeds
print("\n📈 주식 카테고리 RSS 피드:")
for url in config.NEWS_SOURCES_BY_CATEGORY['주식']:
    print(f"  - {url}")

print("\n💰 암호화폐 카테고리 RSS 피드:")
for url in config.NEWS_SOURCES_BY_CATEGORY['암호화폐']:
    print(f"  - {url}")

# Test fetching news
print("\n" + "=" * 60)
print("Fetching sample news from new categories...")
print("=" * 60)

# Create aggregator with only stock and crypto feeds
test_feeds = (
    config.NEWS_SOURCES_BY_CATEGORY['주식'][:2] +  # First 2 stock feeds
    config.NEWS_SOURCES_BY_CATEGORY['암호화폐'][:2]  # First 2 crypto feeds
)

aggregator = NewsAggregator(test_feeds, category_map=config.CATEGORY_MAP)

# Fetch news (last 7 days to ensure we get some results)
news_items = aggregator.fetch_news(hours_limit=168)

print(f"\n✅ Fetched {len(news_items)} news items")

# Group by category
from collections import defaultdict
by_category = defaultdict(list)

for item in news_items:
    by_category[item['category']].append(item)

# Display results
for category, items in by_category.items():
    print(f"\n{'='*60}")
    print(f"{category} 카테고리: {len(items)}개 뉴스")
    print(f"{'='*60}")

    for i, item in enumerate(items[:3], 1):  # Show first 3
        print(f"{i}. [{item['source']}] {item['title'][:60]}...")
        print(f"   Published: {item['published_date']}")
        print(f"   Link: {item['link'][:80]}...")
        print()

print("=" * 60)
print("✅ Test completed successfully!")
print("=" * 60)
