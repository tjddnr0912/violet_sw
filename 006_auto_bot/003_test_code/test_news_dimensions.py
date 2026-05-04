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
