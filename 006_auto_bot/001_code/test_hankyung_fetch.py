#!/usr/bin/env python3
"""
Test fetching from Hankyung with different methods
"""

import ssl
import certifi

# Fix SSL
ssl._create_default_https_context = ssl._create_unverified_context

# Test URL
test_url = "https://www.hankyung.com/article/2025102518277"

print("=" * 60)
print("Testing Hankyung article fetch with User-Agent")
print("=" * 60)

# Method 1: newspaper3k with custom config
print("\n1️⃣ Testing with newspaper3k + User-Agent...")
try:
    from newspaper import Article, Config

    config = Config()
    config.browser_user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    config.request_timeout = 10
    config.memoize_articles = False

    article = Article(test_url, config=config)
    article.download()
    article.parse()

    if article.text:
        print(f"✅ Success! Extracted {len(article.text)} characters")
        print(f"Preview: {article.text[:200]}...")
    else:
        print("⚠️ Downloaded but no text extracted")

except Exception as e:
    print(f"❌ Failed: {str(e)}")

# Method 2: requests with headers
print("\n2️⃣ Testing with requests + headers...")
try:
    import requests
    from bs4 import BeautifulSoup

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }

    response = requests.get(test_url, headers=headers, timeout=10)

    if response.status_code == 200:
        print(f"✅ Success! Status code: {response.status_code}")
        soup = BeautifulSoup(response.content, 'html.parser')

        # Try to find article content
        article_body = soup.find('div', class_='article-body') or soup.find('div', class_='txt')
        if article_body:
            text = article_body.get_text(strip=True)
            print(f"Extracted {len(text)} characters")
            print(f"Preview: {text[:200]}...")
        else:
            print("⚠️ Could not find article body")
    else:
        print(f"❌ Status code: {response.status_code}")

except Exception as e:
    print(f"❌ Failed: {str(e)}")

print("\n" + "=" * 60)
