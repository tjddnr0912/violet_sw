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
