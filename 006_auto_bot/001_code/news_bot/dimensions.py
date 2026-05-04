"""
News Bot Verification Dimensions
--------------------------------
5-dimension checklist applied to the aggregated news collection.
Unlike sector_bot's per-sector dimensions, these evaluate the COLLECTION as a whole:
  - 균형: every expected category has enough items
  - 신선도: enough items are fresh per category-specific limits
  - 다양성: same topic isn't repeated by too many outlets
  - 출처신뢰: enough Tier-1 sources represented
  - 글로벌균형: Korean / international source balance is within range
"""

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


EXPECTED_CATEGORIES = (
    "정치", "경제", "사회", "국제", "문화", "IT/과학", "주식", "암호화폐",
)

TIER1_SOURCES = (
    "Bloomberg", "Reuters", "Financial Times", "Wall Street Journal",
    "The New York Times", "BBC", "CNN", "CNBC", "MarketWatch",
    "연합뉴스", "연합뉴스TV", "SBS", "YTN", "한국경제",
)

KOREAN_SOURCES = (
    "SBS", "YTN", "연합뉴스", "연합뉴스TV",
    "한국경제", "매일경제", "서울경제", "연합인포맥스",
    "블록미디어", "디센터",
)

# Default per-category freshness in hours (overridable from config)
DEFAULT_HOURS_BY_CATEGORY = {
    "정치": 6,
    "경제": 12,
    "사회": 12,
    "국제": 12,
    "문화": 24,
    "IT/과학": 12,
    "주식": 6,
    "암호화폐": 6,
}


@dataclass
class NewsDimension:
    name: str
    check_description: str
    quantitative_check: Callable[[list, dict], bool]
    followup_query_template: Optional[str]


def _check_balance(news_items: list, ctx: dict) -> bool:
    """Every expected category has at least 3 items."""
    if not news_items:
        return False
    by_cat = Counter(item.get("category", "기타") for item in news_items)
    return all(by_cat.get(cat, 0) >= 3 for cat in EXPECTED_CATEGORIES)


def _check_freshness(news_items: list, ctx: dict) -> bool:
    """At least 80% of items are within their category's hour limit."""
    if not news_items:
        return False
    hours_by_cat = ctx.get("hours_by_category") or DEFAULT_HOURS_BY_CATEGORY
    now = ctx.get("now") or datetime.now()
    fresh = 0
    for item in news_items:
        pub = item.get("published_date")
        if not isinstance(pub, datetime):
            continue
        limit_h = hours_by_cat.get(item.get("category"), 24)
        age_h = (now - pub).total_seconds() / 3600.0
        if age_h <= limit_h:
            fresh += 1
    return fresh / len(news_items) >= 0.8


def _check_diversity(news_items: list, ctx: dict) -> bool:
    """No 3-word title prefix appears in more than 2 items."""
    if len(news_items) < 3:
        return True
    keys = []
    for item in news_items:
        title = (item.get("title") or "").lower()
        words = re.split(r"\s+", title.strip())[:3]
        if len(words) >= 2:
            keys.append(" ".join(words))
    counts = Counter(keys)
    return all(c <= 2 for c in counts.values())


def _check_source_trust(news_items: list, ctx: dict) -> bool:
    """At least 40% of items are from Tier-1 sources."""
    if not news_items:
        return False
    tier1 = sum(1 for item in news_items if item.get("source") in TIER1_SOURCES)
    return tier1 / len(news_items) >= 0.4


def _check_global_balance(news_items: list, ctx: dict) -> bool:
    """Korean source ratio is within 0.4–0.6."""
    if not news_items:
        return False
    korean = sum(1 for item in news_items if item.get("source") in KOREAN_SOURCES)
    ratio = korean / len(news_items)
    return 0.4 <= ratio <= 0.6


NEWS_DIMENSIONS: List[NewsDimension] = [
    NewsDimension(
        name="균형",
        check_description="8개 카테고리(정치/경제/사회/국제/문화/IT·과학/주식/암호화폐)에 각각 3개 이상의 뉴스가 있는가?",
        quantitative_check=_check_balance,
        followup_query_template=(
            "Use web search. List the top 3 {category} news items from the past 24 hours. "
            "For each: (1) headline, (2) one-paragraph summary, (3) primary source URL, "
            "(4) publication date in YYYY-MM-DD format. Return as JSON array of "
            '{{"title", "summary", "url", "date", "source"}} objects.'
        ),
    ),
    NewsDimension(
        name="신선도",
        check_description="80% 이상의 뉴스가 카테고리별 시간 한도(정치/주식/암호화폐 6h, 경제/사회/국제/IT 12h, 문화 24h) 안에 있는가?",
        quantitative_check=_check_freshness,
        followup_query_template=(
            "Use web search. Find the most recent {category} news from the last 6 hours only. "
            "Return JSON array of {{\"title\", \"summary\", \"url\", \"date\", \"source\"}} objects, "
            "minimum 3 items, all with timestamps within the last 6 hours."
        ),
    ),
    NewsDimension(
        name="다양성",
        check_description="같은 주제(타이틀 첫 3단어 기준)가 3개 이상 매체에 중복되지 않는가?",
        quantitative_check=_check_diversity,
        followup_query_template=None,  # handled by select_top_news dedup, no gap-fill
    ),
    NewsDimension(
        name="출처신뢰",
        check_description="Tier-1 출처(Bloomberg/Reuters/FT/WSJ/연합뉴스/SBS/YTN 등) 비중이 40% 이상인가?",
        quantitative_check=_check_source_trust,
        followup_query_template=(
            "Use web search. Find Tier-1 source coverage (Bloomberg, Reuters, Financial Times, "
            "Wall Street Journal, 연합뉴스, SBS) of today's top {topic} stories. Return JSON array of "
            "{{\"title\", \"summary\", \"url\", \"date\", \"source\"}} objects, minimum 3 items."
        ),
    ),
    NewsDimension(
        name="글로벌균형",
        check_description="한국 매체 비율이 40~60% 범위인가? (지나친 국내 편향 또는 해외 편향 방지)",
        quantitative_check=_check_global_balance,
        followup_query_template=(
            "Use web search. Find international (non-Korean) perspectives on today's top global news "
            "topics (focus areas: {topic}). Return JSON array of "
            "{{\"title\", \"summary\", \"url\", \"date\", \"source\"}} objects, minimum 3 items."
        ),
    ),
]


def _build_judge_prompt(news_items: list, stats: dict) -> str:
    """Build a Claude prompt that asks for a one-line JSON dimension verdict."""
    sample_titles = "\n".join(
        f"- [{item.get('category', '?')}] [{item.get('source', '?')}] {item.get('title', '')[:80]}"
        for item in news_items[:30]
    )
    dim_lines = "\n".join(f'- "{d.name}": {d.check_description}' for d in NEWS_DIMENSIONS)
    stats_str = json.dumps(stats, ensure_ascii=False, default=str)
    return f"""You are evaluating whether a daily news collection meets a 5-dimension quality checklist.

Dimensions to check:
{dim_lines}

Aggregate statistics:
{stats_str}

Sample of titles ({min(len(news_items), 30)} of {len(news_items)} items):
{sample_titles}

For each dimension, decide if the collection passes the dimension's criterion.
Be strict: missing categories, dominant single-source, repeated stories, source-trust below the bar all fail.

Respond with ONLY a JSON object on a single line, no prose, no code fences:
{{"균형": true|false, "신선도": true|false, "다양성": true|false, "출처신뢰": true|false, "글로벌균형": true|false}}
"""


def claude_judge_news(
    news_items: list,
    stats: dict,
    claude_caller: Callable[[str], str],
) -> dict:
    """
    Call Claude to judge each dimension on the assembled news collection.
    On any error or invalid JSON, returns all-True (fail-open) so we don't
    trigger spurious gap-fill rounds on Claude infrastructure problems.
    """
    prompt = _build_judge_prompt(news_items, stats)
    try:
        raw = claude_caller(prompt)
        # schema is flat (no nested braces) — see _build_judge_prompt template
        match = re.search(r"\{[^{}]*\}", raw)
        if not match:
            raise ValueError("no JSON object in Claude response")
        parsed = json.loads(match.group(0))
        missing = [d.name for d in NEWS_DIMENSIONS if d.name not in parsed]
        if missing:
            logger.warning(
                f"News judge response missing dimension keys {missing}; "
                f"defaulting missing to True"
            )
        return {d.name: bool(parsed.get(d.name, True)) for d in NEWS_DIMENSIONS}
    except Exception as e:
        logger.warning(f"News judge failed: {e}; falling back to all-pass")
        return {d.name: True for d in NEWS_DIMENSIONS}
