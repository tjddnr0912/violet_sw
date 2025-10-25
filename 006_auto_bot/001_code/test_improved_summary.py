#!/usr/bin/env python3
"""
Test improved AI summary with all articles and English translation
"""

import os
os.environ['GRPC_VERBOSITY'] = 'ERROR'
os.environ['GLOG_minloglevel'] = '2'

from v3.ai_summarizer import AISummarizer
from v3.config import config

# Sample markdown with Korean and English news
sample_markdown = """# 원본 뉴스 기사 모음 (카테고리별)

> 수집 일시: 2025년 10월 26일 01:00:00

---

## 📰 카테고리별 뉴스 기사

## 🏛️ 정치

### 1. 이상경 국토차관 사의 표명

**출처:** SBS
**발행일:** 2025-10-25 13:41
**링크:** https://news.sbs.co.kr/news/endPage.do?news_id=N1008305546

#### 원문 내용

'돈 모아서 집값 떨어지면 사라'는 발언과 함께 '갭투자' 논란을 빚었던 이상경 국토교통부 1차관이 결국 사의를 표명했습니다. 이재명 대통령은 하루 만에 이 차관의 사표를 수리했습니다.

---

### 2. 장동혁 대표 부동산 논란

**출처:** SBS
**발행일:** 2025-10-25 13:45
**링크:** https://news.sbs.co.kr/news/endPage.do?news_id=N1008305547

#### 원문 내용

국민의힘은 부동산 대책을 전면 수정하라고 요구했습니다. 민주당은 국민의힘 장동혁 대표의 부동산을 거론하며 역공에 나섰습니다. 장 대표는 "실거주 아파트와 의정 활동 명목으로 산 주택, 상속받은 아파트 지분 일부까지 보유한 주택 6채를 모두 합해도 8억 5천만 원 수준"이라며 투기 용도는 아니라고 맞받았습니다.

---

## 📈 주식

### 1. GM Layoffs and Job Cuts

**출처:** CNBC
**발행일:** 2025-10-24 15:30
**링크:** https://www.cnbc.com/2025/10/24/gm-layoffs-job-cuts.html

#### 원문 내용

General Motors announced significant layoffs affecting approximately 1,000 employees across its global workforce. The cuts are part of a restructuring effort to streamline operations and focus on electric vehicle production. The company stated that these difficult decisions are necessary to remain competitive in the rapidly evolving automotive industry. Affected employees will receive severance packages and outplacement services.

---

### 2. Deckers Stock Surges on Strong Earnings

**출처:** CNBC
**발행일:** 2025-10-24 16:15
**링크:** https://www.cnbc.com/2025/10/24/deckers-stock-deck-hoka-ugg.html

#### 원문 내용

Deckers Outdoor Corporation, known for its Hoka and UGG brands, saw its stock jump 12% after reporting better-than-expected quarterly earnings. The company's revenue grew 25% year-over-year, driven by strong demand for Hoka running shoes and continued strength in the UGG lifestyle category. CEO David Powers attributed the success to innovative product launches and expanding international markets.

---

## 💎 암호화폐

### 1. 고래들이 매입한 3개 암호화폐

**출처:** 블록미디어
**발행일:** 2025-10-25 12:41
**링크:** https://www.blockmedia.co.kr/archives/996043

#### 원문 내용

CPI 발표 후 대형 투자자들이 집중적으로 매입한 암호화폐가 주목받고 있다. 이더리움, 솔라나, 폴카닷이 주요 매수 대상이었으며, 특히 이더리움의 경우 고래 지갑으로 대량 유입이 확인됐다.

---

### 2. Stablecoin Use for Payments Jumps 70%

**출처:** Bloomberg
**발행일:** 2025-10-25 10:20
**링크:** https://www.bloomberg.com/news/articles/2025-10-25/stablecoin-use

#### 원문 내용

Stablecoin usage for payments has surged 70% since new US regulations were introduced earlier this year. The regulatory clarity has encouraged businesses to adopt digital dollar alternatives like USDC and Tether for cross-border transactions. Payment processors report significant growth in stablecoin settlement volumes, particularly in emerging markets where traditional banking infrastructure is limited.

---

*원본 뉴스 수집 by Automated News Bot (Version 3)*
"""

print("=" * 60)
print("Testing Improved AI Summary")
print("=" * 60)

# Initialize AI summarizer
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ GEMINI_API_KEY not set")
    exit(1)

summarizer = AISummarizer(api_key)

print("\n📝 Input:")
print(f"- Categories: 정치, 주식, 암호화폐")
print(f"- Total articles: 6 (3 Korean, 3 English)")
print(f"- Korean articles: 3")
print(f"- English articles: 3")

print("\n🤖 Generating AI summary...")
print("Expected behavior:")
print("  ✓ Summarize ALL 6 articles")
print("  ✓ Translate English articles to Korean")
print("  ✓ Maintain article count (not reduce)")
print()

summary = summarizer.create_blog_summary(sample_markdown)

print("\n" + "=" * 60)
print("📄 GENERATED SUMMARY")
print("=" * 60)
print(summary)
print("=" * 60)

# Verify results
korean_count = summary.count("### ") or summary.count("**1.")
print(f"\n✓ Articles in summary: ~{korean_count} items")

if "GM" in summary or "Deckers" in summary or "제너럴" in summary or "데커스" in summary:
    print("✓ English stock news translated: YES")
else:
    print("⚠ English stock news translated: NOT DETECTED")

if "Stablecoin" in summary or "스테이블코인" in summary:
    print("✓ English crypto news translated: YES")
else:
    print("⚠ English crypto news translated: NOT DETECTED")

print("\n" + "=" * 60)
