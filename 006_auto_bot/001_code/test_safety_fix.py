#!/usr/bin/env python3
"""
Test AI summary with improved safety settings using real 11/06 data
"""

import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

from v3.ai_summarizer import AISummarizer
from v3.config import config

print("=" * 60)
print("Testing AI Summary with Improved Safety Settings")
print("=" * 60)

# Read the actual 11/06 raw news file
raw_file_path = "../004_News_paper/20251106/raw_news_by_category_20251106_235451.md"

print(f"\n📂 Reading: {raw_file_path}")

try:
    with open(raw_file_path, 'r', encoding='utf-8') as f:
        raw_markdown = f.read()

    print(f"✅ File loaded: {len(raw_markdown)} characters")

    # Count articles
    article_count = raw_markdown.count("### ")
    print(f"📰 Articles found: ~{article_count}")

    # Check categories
    categories = []
    for cat in ['🏛️ 정치', '💰 경제', '👥 사회', '🌍 국제', '🎭 문화', '🔬 IT/과학', '📈 주식', '💎 암호화폐']:
        if cat in raw_markdown:
            categories.append(cat)

    print(f"📑 Categories: {', '.join(categories)}")

except Exception as e:
    print(f"❌ Error reading file: {str(e)}")
    exit(1)

# Initialize AI summarizer with current config
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ GEMINI_API_KEY not set")
    exit(1)

summarizer = AISummarizer(api_key, model=config.GEMINI_MODEL)

print("\n🤖 Generating AI summary with improved settings...")
print("Changes applied:")
print("  ✓ Safety settings: BLOCK_ONLY_HIGH")
print("  ✓ Enhanced journalism context in prompt")
print("  ✓ Political news explicitly authorized")
print()

try:
    summary = summarizer.create_blog_summary(raw_markdown)

    print("\n" + "=" * 60)
    print("📄 RESULT")
    print("=" * 60)

    if "AI 요약 생성 중 오류가 발생" in summary:
        print("❌ FAILED - Fallback activated")
        print("\nFallback message detected. AI summary was blocked or failed.")
    else:
        print("✅ SUCCESS - AI summary generated")
        print(f"\nSummary length: {len(summary)} characters")

        # Check if it's actually summarized (not just raw copy)
        if len(summary) < len(raw_markdown) * 0.3:
            print("✓ Content is properly summarized (< 30% of original)")
        else:
            print("⚠ Content might not be properly summarized")

        # Show preview
        print("\n" + "=" * 60)
        print("PREVIEW (first 500 chars):")
        print("=" * 60)
        print(summary[:500])
        print("..." if len(summary) > 500 else "")
        print("=" * 60)

except Exception as e:
    print(f"\n❌ ERROR: {str(e)}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
