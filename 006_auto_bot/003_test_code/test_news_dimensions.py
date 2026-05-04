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
