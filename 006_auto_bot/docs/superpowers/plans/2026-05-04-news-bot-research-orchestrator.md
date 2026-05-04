# News Bot Research-Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing RSS aggregator with a 5-dimension Claude verification gate and Gemini-CLI gap-fill loop, so the daily news pipeline auto-detects category gaps, source-trust shortfalls, and freshness staleness — then fills them with targeted Gemini searches before summarization.

**Architecture:**
- New `news_bot/dimensions.py` defines 5 collection-level dimensions (`균형`, `신선도`, `다양성`, `출처신뢰`, `글로벌균형`) with regex-based quantitative checks + Claude JSON judge.
- New `news_bot/orchestrator.py` (`run_news_research`) sequences `aggregator.fetch_news` → 5-dim gate → targeted Gemini-CLI gap-fill → enriched news pool → existing `AISummarizer.create_blog_summary`.
- `sector_bot/gemini_cli.py` is moved to `shared/gemini_cli.py` so both bots share one CLI fallback implementation.
- `news_bot/config.py` gets `HOURS_LIMIT_BY_CATEGORY` for category-specific freshness limits.
- `news_bot/summarizer.py` gets a Gemini→CLI fallback path (sector-bot pattern).
- `main.py:run_daily_task` swaps the direct `aggregator.get_daily_news()` call for `orchestrator.run_news_research()`.
- `~/.claude/skills/news-summarizer/SKILL.md` gets a 모순 명시 constraint appended.
- Hard cap: 12 minutes per daily run (RSS step itself is ~3 min so larger budget than sector bot's 8 min).
- Q7 = a: only `run_daily_task` gets the gate. Weekly (`run_weekly_task`) and monthly (`run_monthly_task`) keep their existing single-pass flow because they reaggregate already-validated daily summaries.

**Tech Stack:** Python 3.11+, existing `feedparser`/`newspaper3k`, `google-genai` SDK, `gemini -p` CLI, `claude -p` CLI, `pytest` for tests.

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `001_code/shared/gemini_cli.py` | **Create (moved)** | CLI fallback wrapper — was at `sector_bot/gemini_cli.py` |
| `001_code/sector_bot/gemini_cli.py` | **Delete** | Moved to shared |
| `001_code/sector_bot/searcher.py` | Modify (1 import) | `from .gemini_cli` → `from shared.gemini_cli` |
| `001_code/sector_bot/analyzer.py` | Modify (1 import) | Same |
| `001_code/sector_bot/orchestrator.py` | Modify (1 import) | Same |
| `001_code/news_bot/dimensions.py` | **Create** | 5 dimension definitions, quant checks, Claude judge, gap-fill query templates |
| `001_code/news_bot/orchestrator.py` | **Create** | `run_news_research()` + helpers |
| `001_code/news_bot/config.py` | Modify | Add `HOURS_LIMIT_BY_CATEGORY` and `EXPECTED_CATEGORIES` |
| `001_code/news_bot/aggregator.py` | Modify | `fetch_news` accepts `hours_by_category: dict` overriding the global limit |
| `001_code/news_bot/summarizer.py` | Modify | Add `_use_cli_fallback` flag + Gemini→CLI path on quota errors |
| `001_code/main.py` | Modify | `run_daily_task` calls `orchestrator.run_news_research()` instead of `aggregator.get_daily_news()` |
| `~/.claude/skills/news-summarizer/SKILL.md` | Modify | Append constraint #7 모순 명시 |
| `003_test_code/test_shared_gemini_cli.py` | **Create** | Move tests from `test_gemini_cli_helpers.py`; add new tests |
| `003_test_code/test_gemini_cli_helpers.py` | **Delete** | Replaced by test_shared_gemini_cli.py |
| `003_test_code/test_news_dimensions.py` | **Create** | Tests for `news_bot.dimensions` |
| `003_test_code/test_news_orchestrator.py` | **Create** | Tests for `news_bot.orchestrator` (mocking external calls) |
| `006_auto_bot/CLAUDE.md` | Modify | Note daily news bot now uses orchestrator + 5-dim gate |
| `006_auto_bot/docs/NEWS_BOT.md` | **Create** | Document the new daily flow + 5-dim gate semantics |

---

## Phase 1 — Move `gemini_cli` to `shared/` (foundational, no behavior change)

### Task 1: Move file + update sector_bot imports + verify all sector tests pass

**Files:**
- Move: `001_code/sector_bot/gemini_cli.py` → `001_code/shared/gemini_cli.py`
- Modify: `001_code/sector_bot/searcher.py` (1 import line)
- Modify: `001_code/sector_bot/analyzer.py` (1 import line)
- Modify: `001_code/sector_bot/orchestrator.py` (1 import line)
- Move: `003_test_code/test_gemini_cli_helpers.py` → `003_test_code/test_shared_gemini_cli.py`
- Modify: `003_test_code/test_shared_gemini_cli.py` (1 import line)

- [ ] **Step 1: Move the file with `git mv`**

```bash
cd /Users/seongwookjang/project/git/violet_sw
git mv 006_auto_bot/001_code/sector_bot/gemini_cli.py 006_auto_bot/001_code/shared/gemini_cli.py
git mv 006_auto_bot/003_test_code/test_gemini_cli_helpers.py 006_auto_bot/003_test_code/test_shared_gemini_cli.py
```

- [ ] **Step 2: Update `sector_bot/searcher.py` import**

In `006_auto_bot/001_code/sector_bot/searcher.py`, find the line:

```python
from .gemini_cli import is_quota_error, call_gemini_cli
```

Replace with:

```python
from shared.gemini_cli import is_quota_error, call_gemini_cli
```

- [ ] **Step 3: Update `sector_bot/analyzer.py` import**

Same change:

```python
from .gemini_cli import is_quota_error, call_gemini_cli
```

→

```python
from shared.gemini_cli import is_quota_error, call_gemini_cli
```

- [ ] **Step 4: Update `sector_bot/orchestrator.py` import**

Find:

```python
from .gemini_cli import is_cli_mode_active
```

Replace with:

```python
from shared.gemini_cli import is_cli_mode_active
```

- [ ] **Step 5: Update test file's import (now `test_shared_gemini_cli.py`)**

Find:

```python
from sector_bot.gemini_cli import is_cli_mode_active
```

Replace with:

```python
from shared.gemini_cli import is_cli_mode_active
```

- [ ] **Step 6: Verify all tests pass (no behavior change)**

```bash
cd /Users/seongwookjang/project/git/violet_sw
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/ --ignore=006_auto_bot/003_test_code/test_news_fetch.py -v 2>&1 | tail -10
```

Expected: 49 tests pass (33 sector + 16 research_orchestrator pre-existing).

- [ ] **Step 7: Commit**

```bash
git add 006_auto_bot/001_code/shared/gemini_cli.py \
        006_auto_bot/001_code/sector_bot/searcher.py \
        006_auto_bot/001_code/sector_bot/analyzer.py \
        006_auto_bot/001_code/sector_bot/orchestrator.py \
        006_auto_bot/003_test_code/test_shared_gemini_cli.py
git commit -m "Move gemini_cli to shared/ for cross-bot reuse"
```

---

## Phase 2 — News Dimensions Module (TDD)

### Task 2: Create `news_bot/dimensions.py` data structure

**Files:**
- Create: `001_code/news_bot/dimensions.py`
- Test: `003_test_code/test_news_dimensions.py`

- [ ] **Step 1: Write failing test for dimension data**

Create `003_test_code/test_news_dimensions.py`:

```python
#!/usr/bin/env python3
"""Tests for news_bot.dimensions module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from news_bot.dimensions import (
    NEWS_DIMENSIONS, NewsDimension, TIER1_SOURCES, KOREAN_SOURCES, EXPECTED_CATEGORIES
)


def test_five_dimensions_defined():
    names = [d.name for d in NEWS_DIMENSIONS]
    assert names == ["균형", "신선도", "다양성", "출처신뢰", "글로벌균형"]


def test_each_dimension_has_required_fields():
    for d in NEWS_DIMENSIONS:
        assert isinstance(d, NewsDimension)
        assert d.name
        assert d.check_description
        assert callable(d.quantitative_check)
        # 다양성 has no follow-up template (handled in aggregator dedup)
        if d.name != "다양성":
            assert d.followup_query_template
            # template must accept either {category} or {topic}
            assert "{category}" in d.followup_query_template or "{topic}" in d.followup_query_template


def test_tier1_and_korean_source_constants():
    assert "Bloomberg" in TIER1_SOURCES
    assert "Reuters" in TIER1_SOURCES
    assert "Financial Times" in TIER1_SOURCES
    assert "연합뉴스" in TIER1_SOURCES
    assert "SBS" in KOREAN_SOURCES
    assert "YTN" in KOREAN_SOURCES


def test_expected_categories():
    expected = {"정치", "경제", "사회", "국제", "문화", "IT/과학", "주식", "암호화폐"}
    assert set(EXPECTED_CATEGORIES) == expected
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/seongwookjang/project/git/violet_sw
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_dimensions.py -v
```

Expected: FAIL with `ModuleNotFoundError: news_bot.dimensions`.

- [ ] **Step 3: Create `001_code/news_bot/dimensions.py`**

```python
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
            '{"title", "summary", "url", "date", "source"} objects.'
        ),
    ),
    NewsDimension(
        name="신선도",
        check_description="80% 이상의 뉴스가 카테고리별 시간 한도(정치/주식/암호화폐 6h, 경제/사회/국제/IT 12h, 문화 24h) 안에 있는가?",
        quantitative_check=_check_freshness,
        followup_query_template=(
            "Use web search. Find the most recent {category} news from the last 6 hours only. "
            "Return JSON array of {\"title\", \"summary\", \"url\", \"date\", \"source\"} objects, "
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
            "{\"title\", \"summary\", \"url\", \"date\", \"source\"} objects, minimum 3 items."
        ),
    ),
    NewsDimension(
        name="글로벌균형",
        check_description="한국 매체 비율이 40~60% 범위인가? (지나친 국내 편향 또는 해외 편향 방지)",
        quantitative_check=_check_global_balance,
        followup_query_template=(
            "Use web search. Find international (non-Korean) perspectives on today's top global news "
            "topics (focus areas: {topic}). Return JSON array of "
            "{\"title\", \"summary\", \"url\", \"date\", \"source\"} objects, minimum 3 items."
        ),
    ),
]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_dimensions.py -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add 006_auto_bot/001_code/news_bot/dimensions.py 006_auto_bot/003_test_code/test_news_dimensions.py
git commit -m "Add news_bot.dimensions: 5 collection-level dimensions + quantitative checks"
```

---

### Task 3: Add unit tests for each `_check_*` function

**Files:**
- Test: `003_test_code/test_news_dimensions.py` (extend)

- [ ] **Step 1: Append tests for each check function**

Append to `003_test_code/test_news_dimensions.py`:

```python


from datetime import datetime, timedelta
from news_bot.dimensions import (
    _check_balance, _check_freshness, _check_diversity,
    _check_source_trust, _check_global_balance,
)


def _item(category="경제", source="SBS", title="X", hours_old=2):
    return {
        "category": category,
        "source": source,
        "title": title,
        "published_date": datetime.now() - timedelta(hours=hours_old),
    }


def test_balance_passes_with_three_per_category():
    items = []
    for cat in ("정치", "경제", "사회", "국제", "문화", "IT/과학", "주식", "암호화폐"):
        for _ in range(3):
            items.append(_item(category=cat))
    assert _check_balance(items, {}) is True


def test_balance_fails_when_one_category_has_two():
    items = []
    for cat in ("정치", "경제", "사회", "국제", "문화", "IT/과학", "주식", "암호화폐"):
        n = 2 if cat == "IT/과학" else 3
        for _ in range(n):
            items.append(_item(category=cat))
    assert _check_balance(items, {}) is False


def test_freshness_passes_when_majority_within_limits():
    # 8 fresh + 2 stale = 80% fresh (passes)
    items = [_item(category="경제", hours_old=2) for _ in range(8)] + \
            [_item(category="경제", hours_old=48) for _ in range(2)]
    assert _check_freshness(items, {}) is True


def test_freshness_fails_when_majority_stale():
    # 3 fresh + 7 stale = 30% (fails)
    items = [_item(category="경제", hours_old=2) for _ in range(3)] + \
            [_item(category="경제", hours_old=48) for _ in range(7)]
    assert _check_freshness(items, {}) is False


def test_diversity_passes_with_unique_titles():
    items = [
        _item(title="Trump tariff news"),
        _item(title="Fed rate decision"),
        _item(title="Bitcoin price surge"),
    ]
    assert _check_diversity(items, {}) is True


def test_diversity_fails_with_three_repeats():
    items = [
        _item(title="Trump tariff announcement Korea"),
        _item(title="Trump tariff announcement reaction"),
        _item(title="Trump tariff announcement details"),
    ]
    assert _check_diversity(items, {}) is False


def test_source_trust_passes_with_forty_percent_tier1():
    items = [_item(source="Bloomberg") for _ in range(4)] + \
            [_item(source="Random Blog") for _ in range(6)]
    assert _check_source_trust(items, {}) is True


def test_source_trust_fails_with_thirty_percent_tier1():
    items = [_item(source="Reuters") for _ in range(3)] + \
            [_item(source="Random Blog") for _ in range(7)]
    assert _check_source_trust(items, {}) is False


def test_global_balance_passes_at_fifty_fifty():
    items = [_item(source="SBS") for _ in range(5)] + \
            [_item(source="Bloomberg") for _ in range(5)]
    assert _check_global_balance(items, {}) is True


def test_global_balance_fails_at_seventy_korean():
    items = [_item(source="SBS") for _ in range(7)] + \
            [_item(source="Bloomberg") for _ in range(3)]
    assert _check_global_balance(items, {}) is False
```

- [ ] **Step 2: Run all dimension tests**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_dimensions.py -v
```

Expected: 14 tests pass (4 + 10 new).

- [ ] **Step 3: Commit**

```bash
git add 006_auto_bot/003_test_code/test_news_dimensions.py
git commit -m "Add unit tests for all 5 news dimension quantitative checks"
```

---

### Task 4: Add `claude_judge_news` function (2nd-pass collection-level judge)

**Files:**
- Modify: `001_code/news_bot/dimensions.py`
- Test: `003_test_code/test_news_dimensions.py`

- [ ] **Step 1: Write failing tests**

Append to `003_test_code/test_news_dimensions.py`:

```python


def test_claude_judge_news_signature():
    from news_bot.dimensions import claude_judge_news
    import inspect
    sig = inspect.signature(claude_judge_news)
    params = list(sig.parameters.keys())
    assert params[:2] == ["news_items", "stats"]
    assert "claude_caller" in params


def test_claude_judge_news_uses_injected_caller(monkeypatch):
    from news_bot.dimensions import claude_judge_news

    captured = {}
    def fake_caller(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"균형": true, "신선도": false, "다양성": true, "출처신뢰": true, "글로벌균형": true}'

    items = [_item(category="경제") for _ in range(5)]
    stats = {"by_category": {"경제": 5}, "tier1_ratio": 0.4, "korean_ratio": 0.5}
    result = claude_judge_news(
        news_items=items,
        stats=stats,
        claude_caller=fake_caller,
    )
    assert result == {"균형": True, "신선도": False, "다양성": True, "출처신뢰": True, "글로벌균형": True}
    assert "균형" in captured["prompt"]
    # stats summary must reach Claude
    assert "tier1_ratio" in captured["prompt"] or "0.4" in captured["prompt"]


def test_claude_judge_news_falls_back_on_invalid_json():
    from news_bot.dimensions import claude_judge_news

    def bad_caller(prompt: str) -> str:
        return "not json at all"

    result = claude_judge_news(
        news_items=[],
        stats={},
        claude_caller=bad_caller,
    )
    # all-pass fallback
    assert result == {"균형": True, "신선도": True, "다양성": True, "출처신뢰": True, "글로벌균형": True}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_dimensions.py -k claude_judge -v
```

Expected: 3 tests fail with ImportError.

- [ ] **Step 3: Append `claude_judge_news` to `dimensions.py`**

Append at end of `001_code/news_bot/dimensions.py`:

```python


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
```

- [ ] **Step 4: Run tests**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_dimensions.py -v
```

Expected: 17 tests pass (14 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add 006_auto_bot/001_code/news_bot/dimensions.py 006_auto_bot/003_test_code/test_news_dimensions.py
git commit -m "Add claude_judge_news: 2nd-pass qualitative dimension check"
```

---

## Phase 3 — Config (category-specific freshness)

### Task 5: Add `HOURS_LIMIT_BY_CATEGORY` and `EXPECTED_CATEGORIES` to news_bot config

**Files:**
- Modify: `001_code/news_bot/config.py`

- [ ] **Step 1: Read current config to find insertion point**

```bash
grep -n "NEWS_HOURS_LIMIT\|class Config\|MAX_NEWS_COUNT" /Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/news_bot/config.py
```

- [ ] **Step 2: Add the new constants right after `NEWS_HOURS_LIMIT`**

In `001_code/news_bot/config.py`, find:

```python
    # News Fetching Settings
    NEWS_HOURS_LIMIT = int(os.getenv('NEWS_HOURS_LIMIT', '24'))  # Default: 24 hours
```

Append directly under it:

```python

    # Per-category freshness limits (hours). Falls back to NEWS_HOURS_LIMIT if not listed.
    HOURS_LIMIT_BY_CATEGORY = {
        '정치': int(os.getenv('NEWS_HOURS_정치', '6')),
        '경제': int(os.getenv('NEWS_HOURS_경제', '12')),
        '사회': int(os.getenv('NEWS_HOURS_사회', '12')),
        '국제': int(os.getenv('NEWS_HOURS_국제', '12')),
        '문화': int(os.getenv('NEWS_HOURS_문화', '24')),
        'IT/과학': int(os.getenv('NEWS_HOURS_IT', '12')),
        '주식': int(os.getenv('NEWS_HOURS_주식', '6')),
        '암호화폐': int(os.getenv('NEWS_HOURS_암호화폐', '6')),
    }

    # Categories the orchestrator's balance check expects (must match dimensions.py EXPECTED_CATEGORIES).
    EXPECTED_CATEGORIES = (
        '정치', '경제', '사회', '국제', '문화', 'IT/과학', '주식', '암호화폐',
    )
```

- [ ] **Step 3: Verify import still works**

```bash
cd /Users/seongwookjang/project/git/violet_sw/.worktrees/news-orchestrator/006_auto_bot 2>/dev/null || cd /Users/seongwookjang/project/git/violet_sw/006_auto_bot
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -c "import sys; sys.path.insert(0, '001_code'); from news_bot.config import Config; print(Config.HOURS_LIMIT_BY_CATEGORY); print(Config.EXPECTED_CATEGORIES)"
```

Expected: dict prints with 8 entries, tuple prints with 8 categories.

- [ ] **Step 4: Commit**

```bash
git add 006_auto_bot/001_code/news_bot/config.py
git commit -m "Add per-category freshness limits and EXPECTED_CATEGORIES to news_bot config"
```

---

## Phase 4 — Aggregator: support per-category hours limit

### Task 6: Modify `aggregator.fetch_news` to accept `hours_by_category`

**Files:**
- Modify: `001_code/news_bot/aggregator.py`

- [ ] **Step 1: Replace the `fetch_news` signature and the per-entry filter logic**

In `001_code/news_bot/aggregator.py`, find the existing method:

```python
    def fetch_news(self, hours_limit: int = 24) -> List[Dict]:
        """
        Fetch news from all RSS feeds

        Args:
            hours_limit: Only include news published within this many hours (default: 24)

        Returns:
            List of news items as dictionaries
        """
        self.news_items = []
        cutoff_time = datetime.now() - timedelta(hours=hours_limit)

        for feed_url in self.rss_feeds:
            try:
                logger.info(f"Fetching news from: {feed_url}")
                feed = feedparser.parse(feed_url)

                for entry in feed.entries[:10]:  # Get top 10 from each source (increased from 5)
                    news_item = self._parse_entry(entry, feed_url)
                    if news_item:
                        # Filter by publication date (only recent news)
                        pub_date = news_item.get('published_date')
                        if pub_date and pub_date >= cutoff_time:
                            self.news_items.append(news_item)
                            logger.debug(f"Added news: {news_item['title'][:50]}... (published: {pub_date})")
                        else:
                            logger.debug(f"Skipped old news: {news_item['title'][:50]}... (published: {pub_date})")

            except Exception as e:
                logger.error(f"Error fetching from {feed_url}: {str(e)}")
                continue

        logger.info(f"Total news items fetched (within {hours_limit}h): {len(self.news_items)}")
        return self.news_items
```

Replace with:

```python
    def fetch_news(self, hours_limit: int = 24, hours_by_category: Dict[str, int] = None) -> List[Dict]:
        """
        Fetch news from all RSS feeds.

        Args:
            hours_limit: Default hours window for any category not listed in hours_by_category.
            hours_by_category: Optional per-category override (e.g. {'정치': 6, '문화': 24}).

        Returns:
            List of news items as dictionaries
        """
        self.news_items = []
        hours_by_category = hours_by_category or {}
        now = datetime.now()

        for feed_url in self.rss_feeds:
            try:
                logger.info(f"Fetching news from: {feed_url}")
                feed = feedparser.parse(feed_url)

                category = self.category_map.get(feed_url, '기타')
                effective_limit = hours_by_category.get(category, hours_limit)
                cutoff_time = now - timedelta(hours=effective_limit)

                for entry in feed.entries[:10]:
                    news_item = self._parse_entry(entry, feed_url)
                    if news_item:
                        pub_date = news_item.get('published_date')
                        if pub_date and pub_date >= cutoff_time:
                            self.news_items.append(news_item)
                            logger.debug(f"Added news: {news_item['title'][:50]}... (cat={category}, limit={effective_limit}h)")
                        else:
                            logger.debug(f"Skipped old news: {news_item['title'][:50]}... (cat={category}, limit={effective_limit}h)")

            except Exception as e:
                logger.error(f"Error fetching from {feed_url}: {str(e)}")
                continue

        logger.info(f"Total news items fetched: {len(self.news_items)} (per-category limits applied)")
        return self.news_items
```

- [ ] **Step 2: Update `get_daily_news` to forward the per-category dict**

In the same file, find:

```python
    def get_daily_news(self, count: int = 10, hours_limit: int = 24) -> List[Dict]:
        """
        Fetch and select daily news

        Args:
            count: Number of news items to select
            hours_limit: Only include news published within this many hours

        Returns:
            List of selected news items
        """
        self.fetch_news(hours_limit=hours_limit)
        return self.select_top_news(count)
```

Replace with:

```python
    def get_daily_news(
        self,
        count: int = 10,
        hours_limit: int = 24,
        hours_by_category: Dict[str, int] = None,
    ) -> List[Dict]:
        """
        Fetch and select daily news with optional per-category freshness limits.
        """
        self.fetch_news(hours_limit=hours_limit, hours_by_category=hours_by_category)
        return self.select_top_news(count)
```

- [ ] **Step 3: Verify import still works**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -c "import sys; sys.path.insert(0, '006_auto_bot/001_code'); from news_bot.aggregator import NewsAggregator; import inspect; print(inspect.signature(NewsAggregator.fetch_news))"
```

Expected: shows the new signature with `hours_by_category` parameter.

- [ ] **Step 4: Commit**

```bash
git add 006_auto_bot/001_code/news_bot/aggregator.py
git commit -m "Support per-category freshness limits in NewsAggregator"
```

---

## Phase 5 — Summarizer: Gemini → CLI fallback

### Task 7: Add `_use_cli_fallback` flag and fallback path to `AISummarizer.create_blog_summary`

**Files:**
- Modify: `001_code/news_bot/summarizer.py`

- [ ] **Step 1: Add fallback import + flag in `__init__`**

In `001_code/news_bot/summarizer.py`, find the existing imports near top. Add this import:

```python
from shared.gemini_cli import is_quota_error, call_gemini_cli
```

Then in `AISummarizer.__init__`, after the existing assignments (e.g., `self.client = ...`), add:

```python
        self._use_cli_fallback = False  # flips to True after first quota error
```

- [ ] **Step 2: Wrap the API call in `create_blog_summary` with fallback logic**

Find the existing `try:` block in `create_blog_summary` that calls `self.client.models.generate_content`. The current structure is roughly:

```python
        try:
            ...
            response = self.client.models.generate_content(...)
            ...
        except Exception as e:
            logger.error(f"Error creating blog summary: {str(e)}")
            return self._create_fallback_summary(raw_markdown)
```

We will:
1. Detect quota errors and flip `_use_cli_fallback`.
2. When `_use_cli_fallback` is True, route through `call_gemini_cli` instead.

Modify the method body. Find the line at the very start of the method's `try` block:

```python
        try:
            logger.info("Creating blog-style summary with Gemini API...")

            skill_content = load_news_skill()
            prompt = f"""{skill_content}
```

Insert the following BEFORE that `try`:

```python
        skill_content = load_news_skill()
        prompt = f"""{skill_content}

# 요약 모드: Daily (일간 요약)

아래 뉴스 원문을 일간 요약 규칙에 따라 요약하세요.
형식: 마크다운. 설명 없이 본문만 반환.

# 뉴스 원문 데이터

{raw_markdown}
"""
        logger.info(f"Input prompt size: {len(prompt)} characters")
        logger.info(f"Raw markdown size: {len(raw_markdown)} characters")

        # CLI fallback path: skip API entirely once quota was hit
        if self._use_cli_fallback:
            return self._summarize_via_cli(prompt, raw_markdown)
```

Then DELETE the now-duplicate prompt building inside the `try:` block. The remaining `try:` should look like:

```python
        try:
            logger.info("Calling Gemini API with safety OFF for verified news journalism...")

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.7,
                    max_output_tokens=8000,
                    safety_settings=self.safety_settings,
                ),
            )
            # ... existing response handling unchanged ...
```

And modify the outer `except Exception as e:` block:

```python
        except Exception as e:
            if is_quota_error(e):
                logger.warning(f"API quota exhausted, switching to Gemini CLI: {e}")
                self._use_cli_fallback = True
                return self._summarize_via_cli(prompt, raw_markdown)
            logger.error(f"Error creating blog summary: {str(e)}")
            return self._create_fallback_summary(raw_markdown)
```

- [ ] **Step 3: Add `_summarize_via_cli` helper method**

Add this method right after `create_blog_summary` (and before `_create_fallback_summary`):

```python
    def _summarize_via_cli(self, prompt: str, raw_markdown: str) -> str:
        """Run Gemini summarization via CLI fallback. Returns markdown summary or fallback text."""
        logger.info("[CLI Fallback] Summarizing via gemini -p...")
        try:
            text = call_gemini_cli(prompt)
            if not text or len(text) < 200:
                logger.warning(f"[CLI Fallback] Insufficient response: {len(text)} chars")
                return self._create_fallback_summary(raw_markdown)
            cleaned = self._remove_footer(text.strip())
            logger.info(f"[CLI Fallback] Summary completed ({len(cleaned)} chars)")
            return cleaned
        except Exception as e:
            logger.error(f"[CLI Fallback] Failed: {e}")
            return self._create_fallback_summary(raw_markdown)
```

- [ ] **Step 4: Verify module imports cleanly**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -c "import sys; sys.path.insert(0, '006_auto_bot/001_code'); from news_bot.summarizer import AISummarizer; print('OK')"
```

Expected: `OK`.

- [ ] **Step 5: Commit**

```bash
git add 006_auto_bot/001_code/news_bot/summarizer.py
git commit -m "Add Gemini quota → CLI fallback path in AISummarizer"
```

---

## Phase 6 — Orchestrator (TDD)

### Task 8: Create orchestrator skeleton + `NewsOrchestrationResult`

**Files:**
- Create: `001_code/news_bot/orchestrator.py`
- Test: `003_test_code/test_news_orchestrator.py`

- [ ] **Step 1: Write failing tests**

Create `003_test_code/test_news_orchestrator.py`:

```python
#!/usr/bin/env python3
"""Tests for news_bot.orchestrator module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

import inspect
from news_bot.orchestrator import (
    NewsOrchestrationResult,
    run_news_research,
    NEWS_HARD_CAP_SECONDS,
)


def test_news_orchestration_result_fields():
    r = NewsOrchestrationResult(
        success=True,
        news_items=[{"title": "a"}],
        rounds_completed=1,
        gap_fills_attempted=0,
        dimensions_passed={"균형": True, "신선도": True, "다양성": True, "출처신뢰": True, "글로벌균형": True},
        elapsed_seconds=12.0,
        clamped_to_cli=False,
        error=None,
    )
    assert r.success is True
    assert len(r.news_items) == 1


def test_run_news_research_signature():
    sig = inspect.signature(run_news_research)
    params = list(sig.parameters.keys())
    assert params[0] == "aggregator"
    assert "max_count" in params
    assert "hours_by_category" in params
    assert "max_gap_fills" in params
    assert "claude_caller" in params


def test_hard_cap_is_twelve_minutes():
    assert NEWS_HARD_CAP_SECONDS == 720
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_orchestrator.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Create `001_code/news_bot/orchestrator.py`**

```python
"""
News Bot Research Orchestrator
------------------------------
Wraps the RSS aggregator with a 5-dimension Claude verification gate
and targeted Gemini-CLI gap-fill rounds. Produces an enriched news pool
before the existing AISummarizer is called.

Hard cap: 12 minutes per daily run (RSS step itself takes ~3 min).
Q6 = a: gap-fill results are converted to news_item dicts and merged into the pool.
"""

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from .dimensions import (
    NEWS_DIMENSIONS, claude_judge_news,
    TIER1_SOURCES, KOREAN_SOURCES, EXPECTED_CATEGORIES,
)
from shared.gemini_cli import call_gemini_cli

logger = logging.getLogger(__name__)


NEWS_HARD_CAP_SECONDS = 720  # 12 minutes per daily run
CLAUDE_JUDGE_TIMEOUT = 120
DEFAULT_MAX_GAP_FILLS = 4  # max number of gap-fill attempts per run


@dataclass
class NewsOrchestrationResult:
    success: bool
    news_items: List[dict]
    rounds_completed: int
    gap_fills_attempted: int
    dimensions_passed: Dict[str, bool]
    elapsed_seconds: float
    clamped_to_cli: bool
    error: Optional[str] = None
    stats: dict = field(default_factory=dict)


def _default_claude_caller(prompt: str) -> str:
    """Invoke `claude -p` via stdin. Returns stdout."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        f.write(prompt)
        temp_file = f.name
    try:
        with open(temp_file, "r", encoding="utf-8") as f:
            result = subprocess.run(
                ["claude", "-p", "--dangerously-skip-permissions", "-"],
                stdin=f,
                capture_output=True,
                text=True,
                timeout=CLAUDE_JUDGE_TIMEOUT,
            )
        return result.stdout or ""
    finally:
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def run_news_research(
    aggregator,
    max_count: int = 50,
    hours_by_category: Optional[Dict[str, int]] = None,
    max_gap_fills: int = DEFAULT_MAX_GAP_FILLS,
    claude_caller: Optional[Callable[[str], str]] = None,
) -> NewsOrchestrationResult:
    """
    Sequence: RSS aggregate → 5-dim gate → optional CLI gap-fills → enriched pool.
    Returns NewsOrchestrationResult with the final news_items list.
    """
    raise NotImplementedError("filled in by Task 9")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_orchestrator.py -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add 006_auto_bot/001_code/news_bot/orchestrator.py 006_auto_bot/003_test_code/test_news_orchestrator.py
git commit -m "Add news_bot.orchestrator skeleton with NewsOrchestrationResult dataclass"
```

---

### Task 9: Implement `run_news_research` body (gate + gap-fill + JSON parse)

**Files:**
- Modify: `001_code/news_bot/orchestrator.py`
- Test: `003_test_code/test_news_orchestrator.py`

- [ ] **Step 1: Append failing tests for the full pipeline**

Append to `003_test_code/test_news_orchestrator.py`:

```python


from datetime import datetime, timedelta
from unittest.mock import MagicMock


def _passing_items():
    """A balanced collection that should pass all 5 dimensions."""
    items = []
    cats = ("정치", "경제", "사회", "국제", "문화", "IT/과학", "주식", "암호화폐")
    sources = ("Bloomberg", "Reuters", "SBS", "YTN", "연합뉴스", "Financial Times")
    now = datetime.now()
    for i, cat in enumerate(cats):
        for j in range(3):  # 3 per category
            items.append({
                "title": f"Topic {cat} {j} variant",
                "category": cat,
                "source": sources[(i + j) % len(sources)],
                "published_date": now - timedelta(hours=2),
                "link": f"https://example.com/{cat}/{j}",
                "description": "x",
            })
    return items


def test_round1_passes_when_all_dimensions_satisfied():
    aggregator = MagicMock()
    aggregator.fetch_news.return_value = _passing_items()
    aggregator.select_top_news.return_value = _passing_items()

    fake_claude = MagicMock(return_value='{"균형": true, "신선도": true, "다양성": true, "출처신뢰": true, "글로벌균형": true}')

    result = run_news_research(
        aggregator=aggregator,
        max_count=50,
        max_gap_fills=4,
        claude_caller=fake_claude,
    )
    assert result.success is True
    assert result.gap_fills_attempted == 0
    assert all(result.dimensions_passed.values())


def test_failed_dim_triggers_gap_fill_via_cli(monkeypatch):
    """When 균형 fails on round 1, orchestrator should call gemini CLI for the missing category."""
    from news_bot import orchestrator as orch_mod

    # Aggregator returns items missing the '암호화폐' category (1 item only)
    items = [
        item for item in _passing_items()
        if item["category"] != "암호화폐"
    ]
    items.append({
        "title": "Bitcoin update",
        "category": "암호화폐",
        "source": "CoinDesk",
        "published_date": datetime.now() - timedelta(hours=2),
        "link": "https://example.com/x",
        "description": "x",
    })
    aggregator = MagicMock()
    aggregator.fetch_news.return_value = items
    aggregator.select_top_news.return_value = items

    # Force claude to confirm failure on 균형 dim
    fake_claude = MagicMock(return_value='{"균형": false, "신선도": true, "다양성": true, "출처신뢰": true, "글로벌균형": true}')

    # Monkeypatch the CLI call to return a JSON gap-fill result
    cli_response = json.dumps([
        {"title": "Crypto big news 1", "summary": "x", "url": "https://reuters.com/c1", "date": "2026-05-04", "source": "Reuters"},
        {"title": "Crypto big news 2", "summary": "y", "url": "https://bloomberg.com/c2", "date": "2026-05-04", "source": "Bloomberg"},
        {"title": "Crypto big news 3", "summary": "z", "url": "https://coindesk.com/c3", "date": "2026-05-04", "source": "CoinDesk"},
    ])
    monkeypatch.setattr(orch_mod, "call_gemini_cli", lambda prompt, timeout=600: cli_response)

    result = run_news_research(
        aggregator=aggregator,
        max_count=50,
        max_gap_fills=4,
        claude_caller=fake_claude,
    )
    assert result.gap_fills_attempted >= 1
    # After gap-fill, total items should include the 3 new entries
    assert len(result.news_items) >= len(items) + 3
    # Crypto items should now be sufficient
    crypto_count = sum(1 for it in result.news_items if it["category"] == "암호화폐")
    assert crypto_count >= 4


import json  # used by the test above
```

- [ ] **Step 2: Run tests to verify failure**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_orchestrator.py -v
```

Expected: 2 new tests fail with `NotImplementedError`.

- [ ] **Step 3: Replace the body of `run_news_research`**

In `001_code/news_bot/orchestrator.py`, replace this line:

```python
    raise NotImplementedError("filled in by Task 9")
```

with:

```python
    started_at = time.time()
    deadline = started_at + NEWS_HARD_CAP_SECONDS
    claude_caller = claude_caller or _default_claude_caller

    # ---- Round 1: RSS aggregation ----
    logger.info("News orchestrator Round 1: RSS aggregation")
    try:
        raw_items = aggregator.fetch_news(
            hours_limit=24,
            hours_by_category=hours_by_category or {},
        )
    except Exception as e:
        return NewsOrchestrationResult(
            success=False,
            news_items=[],
            rounds_completed=0,
            gap_fills_attempted=0,
            dimensions_passed={d.name: False for d in NEWS_DIMENSIONS},
            elapsed_seconds=time.time() - started_at,
            clamped_to_cli=False,
            error=f"RSS aggregation failed: {e}",
        )

    if not raw_items:
        return NewsOrchestrationResult(
            success=False,
            news_items=[],
            rounds_completed=0,
            gap_fills_attempted=0,
            dimensions_passed={d.name: False for d in NEWS_DIMENSIONS},
            elapsed_seconds=time.time() - started_at,
            clamped_to_cli=False,
            error="No RSS items collected",
        )

    selected = aggregator.select_top_news(max_count)
    rounds_completed = 1
    accumulated: List[dict] = list(selected)

    # ---- Dimension gate ----
    ctx = {
        "hours_by_category": hours_by_category,
        "now": datetime.now(),
    }
    quant_pass = {d.name: d.quantitative_check(accumulated, ctx) for d in NEWS_DIMENSIONS}
    quant_failed = [name for name, ok in quant_pass.items() if not ok]
    logger.info(f"Quant gate: pass={sum(quant_pass.values())}/5, fail={quant_failed}")

    if quant_failed:
        stats = _compute_stats(accumulated)
        judge_pass = claude_judge_news(
            news_items=accumulated,
            stats=stats,
            claude_caller=claude_caller,
        )
        dimensions_passed = {
            name: quant_pass[name] or judge_pass.get(name, True)
            for name in quant_pass
        }
    else:
        dimensions_passed = quant_pass

    failing_dims = [d for d in NEWS_DIMENSIONS if not dimensions_passed.get(d.name, True)]
    logger.info(f"Final gate: failing={[d.name for d in failing_dims]}")

    # ---- Gap-fill loop ----
    gap_fills_attempted = 0
    while (
        failing_dims
        and gap_fills_attempted < max_gap_fills
        and time.time() < deadline
    ):
        target = next((d for d in failing_dims if d.followup_query_template), None)
        if target is None:
            break

        gap_target = _pick_gap_target(target.name, accumulated)
        followup_query = target.followup_query_template.format(
            category=gap_target.get("category", "general"),
            topic=gap_target.get("topic", "today's top stories"),
        )
        logger.info(f"Gap-fill attempt {gap_fills_attempted + 1}: '{target.name}' → {gap_target}")
        logger.debug(f"Followup query: {followup_query!r}")

        gap_items = _gap_fill_via_cli(followup_query, gap_target.get("category"))
        gap_fills_attempted += 1

        if gap_items:
            accumulated.extend(gap_items)
            rounds_completed += 1
            # Re-evaluate just the targeted dimension
            new_pass = target.quantitative_check(accumulated, ctx)
            dimensions_passed[target.name] = new_pass
        else:
            logger.warning(f"Gap-fill on '{target.name}' returned no items")

        failing_dims = [d for d in NEWS_DIMENSIONS if not dimensions_passed.get(d.name, True)]

    if time.time() >= deadline:
        logger.warning("News hard cap elapsed (gap-fill budget exhausted); proceeding to summarizer")

    return NewsOrchestrationResult(
        success=True,
        news_items=accumulated,
        rounds_completed=rounds_completed,
        gap_fills_attempted=gap_fills_attempted,
        dimensions_passed=dimensions_passed,
        elapsed_seconds=time.time() - started_at,
        clamped_to_cli=False,
        stats=_compute_stats(accumulated),
    )
```

Then add the three module-level helpers AFTER `run_news_research`:

```python
def _compute_stats(news_items: list) -> dict:
    """Aggregate counts used by the Claude judge prompt."""
    if not news_items:
        return {"total": 0}
    by_cat = Counter(item.get("category", "기타") for item in news_items)
    tier1 = sum(1 for item in news_items if item.get("source") in TIER1_SOURCES)
    korean = sum(1 for item in news_items if item.get("source") in KOREAN_SOURCES)
    return {
        "total": len(news_items),
        "by_category": dict(by_cat),
        "tier1_ratio": round(tier1 / len(news_items), 2),
        "korean_ratio": round(korean / len(news_items), 2),
    }


def _pick_gap_target(dim_name: str, news_items: list) -> dict:
    """Choose what {category} or {topic} to fill in the followup query template."""
    if dim_name == "균형":
        # missing or under-represented category
        by_cat = Counter(item.get("category", "기타") for item in news_items)
        missing = [c for c in EXPECTED_CATEGORIES if by_cat.get(c, 0) < 3]
        return {"category": missing[0] if missing else "general", "topic": "today's top stories"}
    if dim_name == "신선도":
        # category with the most stale items
        by_cat = Counter(item.get("category", "기타") for item in news_items)
        worst = max(by_cat, key=by_cat.get) if by_cat else "general"
        return {"category": worst, "topic": "breaking news"}
    if dim_name == "출처신뢰":
        # broadest topic — pick most-represented category
        by_cat = Counter(item.get("category", "기타") for item in news_items)
        top = max(by_cat, key=by_cat.get) if by_cat else "general"
        return {"category": top, "topic": top}
    if dim_name == "글로벌균형":
        return {"category": "international", "topic": "global affairs"}
    return {"category": "general", "topic": "today's top stories"}


def _gap_fill_via_cli(followup_query: str, category: Optional[str]) -> list:
    """
    Invoke `gemini -p` via shared.gemini_cli, parse JSON array of news items,
    convert to the news_item dict shape expected by the rest of the pipeline.
    Returns [] on any failure (gap-fill is best-effort).
    """
    try:
        raw = call_gemini_cli(followup_query, timeout=600)
    except Exception as e:
        logger.warning(f"Gap-fill CLI call failed: {e}")
        return []

    # Find a JSON array in the response (Gemini sometimes wraps in prose)
    match = re.search(r"\[\s*\{.*?\}\s*\]", raw, re.DOTALL)
    if not match:
        logger.warning(f"Gap-fill response had no JSON array: {raw[:200]}")
        return []

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.warning(f"Gap-fill JSON parse failed: {e}")
        return []

    items = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        try:
            pub = datetime.strptime(entry.get("date", ""), "%Y-%m-%d") if entry.get("date") else datetime.now()
        except ValueError:
            pub = datetime.now()
        items.append({
            "title": entry.get("title", "Untitled"),
            "link": entry.get("url", ""),
            "description": entry.get("summary", ""),
            "rss_summary": "",
            "full_content": entry.get("summary", ""),
            "published_date": pub,
            "source": entry.get("source", "Gemini CLI"),
            "source_url": entry.get("url", ""),
            "category": category or "기타",
        })
    return items
```

- [ ] **Step 4: Run all tests**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/test_news_orchestrator.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Run full suite (no regression)**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -m pytest 006_auto_bot/003_test_code/ --ignore=006_auto_bot/003_test_code/test_news_fetch.py 2>&1 | tail -3
```

Expected: 49 + 17 + 5 = 71 tests pass (49 from sector + research_orchestrator existing, 17 from news_dimensions, 5 from news_orchestrator).

- [ ] **Step 6: Commit**

```bash
git add 006_auto_bot/001_code/news_bot/orchestrator.py 006_auto_bot/003_test_code/test_news_orchestrator.py
git commit -m "Implement run_news_research: 5-dim gate + gemini CLI gap-fill"
```

---

## Phase 7 — Wire orchestrator into main.py

### Task 10: Replace `aggregator.get_daily_news()` call in `run_daily_task` with `run_news_research()`

**Files:**
- Modify: `001_code/main.py` (around lines 78-100)

- [ ] **Step 1: Add import near other news_bot imports at top of file**

```bash
grep -n "from news_bot" /Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/main.py
```

After the last `from news_bot.` import, add:

```python
from news_bot.orchestrator import run_news_research, NewsOrchestrationResult
```

- [ ] **Step 2: Replace Step 1 of `run_daily_task`**

In `001_code/main.py`, find:

```python
            # Step 1: Fetch and select top news
            logger.info(f"Step 1: Fetching top {self.config.MAX_NEWS_COUNT} news articles (within {self.config.NEWS_HOURS_LIMIT}h)...")
            news_items = self.news_aggregator.get_daily_news(
                count=self.config.MAX_NEWS_COUNT,
                hours_limit=self.config.NEWS_HOURS_LIMIT
            )

            if not news_items:
                logger.warning("No news items found. Aborting task.")
                return

            logger.info(f"Successfully fetched {len(news_items)} news articles")
```

Replace with:

```python
            # Step 1: Orchestrated fetch (RSS → 5-dim gate → CLI gap-fill)
            logger.info(f"Step 1: Orchestrating news collection (max {self.config.MAX_NEWS_COUNT}, per-category freshness)...")
            orch: NewsOrchestrationResult = run_news_research(
                aggregator=self.news_aggregator,
                max_count=self.config.MAX_NEWS_COUNT,
                hours_by_category=self.config.HOURS_LIMIT_BY_CATEGORY,
                max_gap_fills=4,
            )

            if not orch.success or not orch.news_items:
                logger.warning(f"Orchestration failed or empty: {orch.error}. Aborting task.")
                return

            news_items = orch.news_items
            logger.info(
                f"Orchestrator done: {len(news_items)} items, "
                f"rounds={orch.rounds_completed}, gap_fills={orch.gap_fills_attempted}, "
                f"elapsed={orch.elapsed_seconds:.1f}s, "
                f"dims={sum(orch.dimensions_passed.values())}/5"
            )
```

- [ ] **Step 3: Verify module imports cleanly**

```bash
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python -c "import sys; sys.path.insert(0, '006_auto_bot/001_code'); from main import NewsAutomation; print('OK')"
```

Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add 006_auto_bot/001_code/main.py
git commit -m "Wire news orchestrator into run_daily_task with per-category freshness"
```

---

## Phase 8 — Skill file (모순 명시)

### Task 11: Append constraint to `news-summarizer/SKILL.md`

**Files:**
- Modify: `~/.claude/skills/news-summarizer/SKILL.md`

- [ ] **Step 1: Verify current last constraint number**

```bash
grep -n "^[0-9]\." ~/.claude/skills/news-summarizer/SKILL.md | tail -5
```

Note the highest existing number (likely `5.` based on the SKILL excerpt). The new constraint will be the NEXT number after that.

- [ ] **Step 2: Append the new constraint to end of file**

Append exactly this block to the END of `~/.claude/skills/news-summarizer/SKILL.md` (use the next number — likely 6, but verify in step 1):

```markdown

## 추가 제약 (Orchestrator 도입 후)

- **모순 명시**: 같은 사건을 여러 매체가 다르게 보도하면(국내 vs 해외, 보수 vs 진보 등) 한쪽만 채택하지 말고 둘 다 인용한 뒤, 차이의 원인(매체 성향·취재 시점·해석 차이)을 1줄로 명시한다. 모순이 발견된 항목은 본문 말미에 `## 📌 매체 간 시각 차이` 섹션으로 별도로 모은다.
```

- [ ] **Step 3: Verify**

```bash
grep -A1 "모순 명시" ~/.claude/skills/news-summarizer/SKILL.md
```

Expected: shows the new constraint.

- [ ] **Step 4: No commit (file is outside the repo)**

The SKILL file lives in `~/.claude/skills/`, outside the git repo. Skip git commit for this task.

---

## Phase 9 — Documentation

### Task 12: Create `docs/NEWS_BOT.md` documenting the new flow + update `CLAUDE.md`

**Files:**
- Create: `006_auto_bot/docs/NEWS_BOT.md`
- Modify: `006_auto_bot/CLAUDE.md` (1 row in 핵심 참조 table)

- [ ] **Step 1: Create `006_auto_bot/docs/NEWS_BOT.md`**

```markdown
# News Bot

매일 06:00 RSS 수집 → 5차원 검증 게이트 → Gemini CLI 갭필 → AI 요약 → Blogger 업로드.

## 실행

```bash
python main.py --mode daily       # 일간 즉시 1회
python main.py --mode weekly      # 주간 (게이트 적용 안 함)
python main.py --mode monthly     # 월간 (게이트 적용 안 함)
```

## 8개 카테고리

정치, 경제, 사회, 국제, 문화, IT/과학, 주식, 암호화폐 — 각 카테고리당 3-8개 RSS feed.

## 오케스트레이터 (5차원 검증)

`news_bot/orchestrator.py`가 RSS 수집 → 5차원 게이트 → Gemini CLI 갭필 → 요약을 시퀀싱한다.

### 5차원 체크리스트 (collection-level)

| 차원 | 통과 기준 (정량) | Claude 2차 | 갭필 채널 |
|------|---------------|-----------|----------|
| 균형 | 8개 카테고리 모두 ≥3개 항목 | 항상 (quant fail 시) | gemini -p (missing 카테고리 검색) |
| 신선도 | ≥80% 항목이 카테고리별 한도 내 | ↑ | gemini -p (6시간 내 breaking news) |
| 다양성 | 같은 주제 매체 중복 ≤2개 | ↑ | (갭필 없음 — aggregator dedup) |
| 출처신뢰 | Tier-1 출처(Bloomberg/Reuters/FT/WSJ/연합뉴스/SBS/YTN) ≥40% | ↑ | gemini -p (Tier-1 source coverage) |
| 글로벌균형 | 한국 매체 비율 40~60% | ↑ | gemini -p (국제 시각) |

OR-semantics: 한 차원이 정량 OR Claude 중 하나라도 통과하면 그 차원은 통과 처리.

### 카테고리별 신선도 한도 (`HOURS_LIMIT_BY_CATEGORY`)

| 카테고리 | 한도 (h) | 환경변수 |
|---------|---------|---------|
| 정치 | 6 | `NEWS_HOURS_정치` |
| 경제 | 12 | `NEWS_HOURS_경제` |
| 사회 | 12 | `NEWS_HOURS_사회` |
| 국제 | 12 | `NEWS_HOURS_국제` |
| 문화 | 24 | `NEWS_HOURS_문화` |
| IT/과학 | 12 | `NEWS_HOURS_IT` |
| 주식 | 6 | `NEWS_HOURS_주식` |
| 암호화폐 | 6 | `NEWS_HOURS_암호화폐` |

### 라운드 예산

- Round 1: RSS 수집 (3-5분)
- Gap-fill: 카테고리별 1회씩, 최대 4회 (`max_gap_fills`)
- Hard cap: **12분** (총 wall time)

### 갭필 결과 통합

Gemini CLI는 JSON 배열로 응답:
```json
[{"title": "...", "summary": "...", "url": "...", "date": "YYYY-MM-DD", "source": "..."}, ...]
```

Orchestrator가 이를 news_item dict로 변환해 기존 풀에 합침 (Q6=a). 별도 섹션 없음.

### 모순 명시

요약 출력에 `## 📌 매체 간 시각 차이` 섹션이 자동 생성됨 (`news-summarizer/SKILL.md`의 추가 제약).

## Gemini CLI Fallback

Gemini API 429 RESOURCE_EXHAUSTED 발생 시 `shared/gemini_cli.py`로 자동 전환 (sector_bot과 공유).
```

- [ ] **Step 2: Update `006_auto_bot/CLAUDE.md` 핵심 참조 table**

In `006_auto_bot/CLAUDE.md`, find the row mentioning daily news scheduling. The table contains a 뉴스봇 row similar to:

```
| 뉴스봇 | Daily 06:00, Weekly 일요일 07:00, Monthly 1일 07:30 |
```

Replace with:

```
| 뉴스봇 | Daily 06:00 (orchestrator + 5차원 게이트), Weekly 일요일 07:00, Monthly 1일 07:30. `news_bot/orchestrator.py`가 균형/신선도/다양성/출처신뢰/글로벌균형 검증 + Gemini CLI 갭필 |
```

Also in the 상세 문서 table, add a new row:

```
| 뉴스봇 상세 | [docs/NEWS_BOT.md](docs/NEWS_BOT.md) |
```

- [ ] **Step 3: Commit**

```bash
git add 006_auto_bot/docs/NEWS_BOT.md 006_auto_bot/CLAUDE.md
git commit -m "Document news_bot orchestrator: 5-dim gate, gap-fill, category freshness"
```

---

## Phase 10 — Smoke Test

### Task 13: Manual smoke test — single daily run

**Files:** none (manual run)

- [ ] **Step 1: Confirm `.env` is in place and `claude` + `gemini` CLIs exist**

```bash
ls /Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.env
which claude
which gemini
```

Expected: env file exists, both CLIs found in PATH.

- [ ] **Step 2: Run daily mode in once-only**

```bash
cd /Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code
/Users/seongwookjang/project/git/violet_sw/006_auto_bot/001_code/.venv/bin/python main.py --mode daily 2>&1 | tee /tmp/news_smoke_$(date +%Y%m%d_%H%M%S).log | tail -100
```

Expected log lines (search for them):
- `Step 1: Orchestrating news collection`
- `Quant gate: pass=N/5, fail=[...]`
- `Final gate: failing=[...]`
- (if any failures) `Gap-fill attempt N: '<dim>'`
- `Orchestrator done: N items, rounds=N, gap_fills=N`
- `Step 3: Creating AI blog summary`
- `Step 6: Sending Telegram notification` (if enabled)

- [ ] **Step 3: Inspect saved markdown**

```bash
ls -la /Users/seongwookjang/project/git/violet_sw/006_auto_bot/004_News_paper/$(date +%Y%m%d)/
```

Expected: at least 2 files — raw category markdown + blog summary.

- [ ] **Step 4: Verify the 모순 명시 section appears in the blog summary**

```bash
grep -c "📌 매체 간 시각 차이" /Users/seongwookjang/project/git/violet_sw/006_auto_bot/004_News_paper/$(date +%Y%m%d)/blog_summary*.md || true
```

Expected: 0 or 1 (depends on whether Gemini detected outlet conflicts in today's news — both are valid outcomes).

- [ ] **Step 5: Commit smoke log (optional)**

```bash
mkdir -p 006_auto_bot/docs/superpowers/runs
cp /tmp/news_smoke_*.log 006_auto_bot/docs/superpowers/runs/$(date +%Y-%m-%d)-news-daily-smoke.log
git add 006_auto_bot/docs/superpowers/runs/
git commit -m "Add smoke-test log for news orchestrator daily run"
```

---

## Self-Review Notes

**Spec coverage:**
- Path B (RSS → 5-dim gate → CLI gap-fill → summarize): Tasks 8-10
- Q2 = a (Claude CLI reuse): Task 8 `_default_claude_caller` uses `claude -p`
- Q3 = b (Gemini CLI for gap-fill): Task 9 `_gap_fill_via_cli` uses `call_gemini_cli`
- Q5 = b (shared/gemini_cli.py): Task 1 moves the file
- Q6 = a (gap-fill → news_items in pool): Task 9 `_gap_fill_via_cli` returns dicts merged via `accumulated.extend(gap_items)`
- Q7 = a (daily only): Task 10 modifies `run_daily_task` only; weekly/monthly untouched
- Q8 = b (12 min hard cap): Task 8 `NEWS_HARD_CAP_SECONDS = 720`
- 부수 #1 모순 명시: Task 11 appends constraint to news-summarizer SKILL
- 부수 #2 카테고리별 신선도: Tasks 5, 6, 9 (config + aggregator + orchestrator pass-through)
- 부수 #3 Gemini → CLI fallback: Task 7 adds fallback to AISummarizer

**Type consistency:**
- `NewsOrchestrationResult.dimensions_passed` is `Dict[str, bool]` everywhere.
- `claude_caller` is `Callable[[str], str]` in dimensions.py and orchestrator.py.
- Aggregator `fetch_news` and `get_daily_news` both accept `hours_by_category: Dict[str, int]` (Task 6).
- Orchestrator `run_news_research(aggregator, ...)` signature matches main.py call site (Task 10).
- Gap-fill items use the same dict shape as RSS items (title/link/description/published_date/source/category) so downstream `MarkdownWriter.save_raw_news_by_category` doesn't need changes.

**Placeholder scan:** No TODO/TBD/placeholder text. All code blocks are complete.

**Cross-bot import note:** Task 1 moves `gemini_cli` to `shared/`. After Task 1, sector_bot's tests must still pass (they're updated to use the new import). The verify step in Task 1 confirms this. Subsequent tasks on news_bot import directly from `shared.gemini_cli` without further movement.
