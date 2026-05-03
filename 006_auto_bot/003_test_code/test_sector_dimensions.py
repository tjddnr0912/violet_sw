#!/usr/bin/env python3
"""Tests for sector_bot.dimensions module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from sector_bot.dimensions import SECTOR_DIMENSIONS, Dimension


def test_five_dimensions_defined():
    names = [d.name for d in SECTOR_DIMENSIONS]
    assert names == ["정의", "현황", "근거", "반론", "적용"]


def test_each_dimension_has_required_fields():
    for d in SECTOR_DIMENSIONS:
        assert isinstance(d, Dimension)
        assert d.name
        assert d.check_description
        assert callable(d.quantitative_check)
        # 적용 has no follow-up template (handled in analyzer); others must
        if d.name != "적용":
            assert d.followup_query_template
            assert "{sector}" in d.followup_query_template


def test_tier1_domains_constant():
    from sector_bot.dimensions import TIER1_DOMAINS
    assert "bloomberg.com" in TIER1_DOMAINS
    assert "reuters.com" in TIER1_DOMAINS
    assert "ft.com" in TIER1_DOMAINS
    assert "wsj.com" in TIER1_DOMAINS
    assert "sec.gov" in TIER1_DOMAINS
