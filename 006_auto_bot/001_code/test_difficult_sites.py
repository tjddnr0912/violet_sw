#!/usr/bin/env python3
"""
Test fetching from difficult sites (Bloomberg, MarketWatch)
"""

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import sys
sys.path.insert(0, '.')

from v3.news_aggregator import NewsAggregator

# Test URLs
test_urls = {
    'Bloomberg': 'https://www.bloomberg.com/news/articles/2025-10-25/stablecoin-use-for-payments-jumps-70-since-us-regulation',
    'MarketWatch': 'https://www.marketwatch.com/story/this-one-buyer-is-driving-golds-surge-and-could-easily-trigger-its-fall-bc02e323',
    'Hankyung': 'https://www.hankyung.com/article/2025102518277'
}

print("=" * 60)
print("Testing Article Extraction from Difficult Sites")
print("=" * 60)

# Create aggregator to use its fetch method
aggregator = NewsAggregator([])

for site_name, url in test_urls.items():
    print(f"\n{'='*60}")
    print(f"Testing: {site_name}")
    print(f"URL: {url[:80]}...")
    print('='*60)

    content = aggregator._fetch_full_article(url)

    if content:
        print(f"✅ Success! Extracted {len(content)} characters")
        print(f"\nPreview (first 300 chars):")
        print("-" * 60)
        print(content[:300])
        print("-" * 60)
    else:
        print(f"❌ Failed to extract content")

print("\n" + "=" * 60)
print("Test completed!")
print("=" * 60)
