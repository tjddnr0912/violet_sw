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


import json
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

    # Monkeypatch claude_websearch (gap-fill backend post-2026-05-27 PM) to
    # return a JSON gap-fill result. Function name `_gap_fill_via_cli` retained
    # for backward compat but internally calls claude_websearch now.
    from shared.claude_search import ClaudeSearchResponse
    cli_response = json.dumps([
        {"title": "Crypto big news 1", "summary": "x", "url": "https://reuters.com/c1", "date": "2026-05-04", "source": "Reuters"},
        {"title": "Crypto big news 2", "summary": "y", "url": "https://bloomberg.com/c2", "date": "2026-05-04", "source": "Bloomberg"},
        {"title": "Crypto big news 3", "summary": "z", "url": "https://coindesk.com/c3", "date": "2026-05-04", "source": "CoinDesk"},
    ])
    monkeypatch.setattr(
        orch_mod,
        "claude_websearch",
        lambda prompt, **kw: ClaudeSearchResponse(text=cli_response, sources=[], model_used="haiku"),
    )

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
