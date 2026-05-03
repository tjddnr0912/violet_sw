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


from sector_bot.dimensions import (
    _check_definition, _check_status, _check_evidence,
    _check_counterargument, _check_application,
)


def test_check_definition_passes_with_bullet_list():
    content = "- AI capex surge\n- Memory cycle bottom\n- Korea export rebound\n"
    assert _check_definition(content, []) is True


def test_check_definition_fails_with_plain_paragraph():
    content = "The market is doing things this week with no specific structure."
    assert _check_definition(content, []) is False


def test_check_status_passes_with_three_number_date_pairs():
    content = (
        "S&P 500 rose 1.2% on 2026-04-28. NVIDIA gained $5.20 on April 29, 2026. "
        "Korea KOSPI fell 0.8% on 2026-04-30. Treasury yields up 12 bps."
    )
    assert _check_status(content, []) is True


def test_check_status_fails_with_only_numbers():
    content = "Stocks moved 1.2%, then 0.8%, then 5.5%, with no dates given."
    assert _check_status(content, []) is False


def test_check_evidence_passes_with_two_tier1():
    sources = [
        {"url": "https://www.bloomberg.com/news/x"},
        {"url": "https://www.reuters.com/markets/y"},
        {"url": "https://example.com/z"},
    ]
    assert _check_evidence("body", sources) is True


def test_check_evidence_fails_with_only_one_tier1():
    sources = [{"url": "https://www.bloomberg.com/news/x"}, {"url": "https://blog.example.com"}]
    assert _check_evidence("body", sources) is False


def test_check_counterargument_passes_with_both_sides():
    content = "Analyst bullish on AI semis, citing upside; bears warn of downside risk in memory."
    assert _check_counterargument(content, []) is True


def test_check_counterargument_fails_with_one_side():
    content = "Everyone is bullish, with strong buy ratings across the board."
    assert _check_counterargument(content, []) is False


def test_check_application_passes_with_action_and_ticker():
    content = "매수 추천: NVDA, TSM, AMD on the dip."
    assert _check_application(content, []) is True


def test_check_application_fails_with_no_action():
    content = "Many companies exist in this sector including NVDA and AMD."
    assert _check_application(content, []) is False


def test_claude_judge_dimensions_signature():
    from sector_bot.dimensions import claude_judge_dimensions
    import inspect
    sig = inspect.signature(claude_judge_dimensions)
    params = list(sig.parameters.keys())
    assert params[:3] == ["sector_name", "content", "sources"]
    assert "claude_caller" in params  # injectable for tests


def test_claude_judge_dimensions_uses_injected_caller(monkeypatch):
    from sector_bot.dimensions import claude_judge_dimensions

    captured = {}
    def fake_caller(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"정의": true, "현황": false, "근거": true, "반론": false, "적용": true}'

    result = claude_judge_dimensions(
        sector_name="반도체",
        content="some sector content",
        sources=[{"url": "https://www.bloomberg.com/x"}],
        claude_caller=fake_caller,
    )
    assert result == {"정의": True, "현황": False, "근거": True, "반론": False, "적용": True}
    assert "반도체" in captured["prompt"]
    assert "정의" in captured["prompt"]


def test_claude_judge_dimensions_falls_back_on_invalid_json():
    from sector_bot.dimensions import claude_judge_dimensions

    def bad_caller(prompt: str) -> str:
        return "not json at all"

    result = claude_judge_dimensions(
        sector_name="반도체",
        content="x",
        sources=[],
        claude_caller=bad_caller,
    )
    # all-pass fallback so we don't trigger spurious gap-fill on Claude error
    assert result == {"정의": True, "현황": True, "근거": True, "반론": True, "적용": True}


def test_claude_judge_dimensions_partial_keys_default_to_true(caplog):
    import logging
    from sector_bot.dimensions import claude_judge_dimensions

    def partial_caller(prompt: str) -> str:
        # Only 2 of 5 dimensions present
        return '{"정의": false, "현황": true}'

    with caplog.at_level(logging.WARNING, logger="sector_bot.dimensions"):
        result = claude_judge_dimensions(
            sector_name="반도체",
            content="x",
            sources=[],
            claude_caller=partial_caller,
        )

    # Present keys honored
    assert result["정의"] is False
    assert result["현황"] is True
    # Missing keys default to True
    assert result["근거"] is True
    assert result["반론"] is True
    assert result["적용"] is True
    # Warning was emitted
    assert any("missing dimension keys" in rec.message for rec in caplog.records)
