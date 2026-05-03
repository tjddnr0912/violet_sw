#!/usr/bin/env python3
"""Tests for sector_bot.orchestrator module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

import inspect
from sector_bot.orchestrator import (
    OrchestrationResult,
    run_sector_research,
    SECTOR_HARD_CAP_SECONDS,
)


def test_orchestration_result_fields():
    r = OrchestrationResult(
        success=True,
        analysis="body",
        sources=[{"url": "https://x"}],
        rounds_completed=2,
        dimensions_passed={"정의": True, "현황": True, "근거": True, "반론": True, "적용": True},
        elapsed_seconds=120.5,
        clamped_to_cli=False,
        error=None,
    )
    assert r.success is True
    assert r.rounds_completed == 2
    assert r.elapsed_seconds == 120.5


def test_run_sector_research_signature():
    sig = inspect.signature(run_sector_research)
    params = list(sig.parameters.keys())
    assert params[0] == "sector"
    assert "searcher" in params
    assert "analyzer" in params
    assert "max_rounds" in params
    assert "claude_caller" in params  # injectable for tests


def test_hard_cap_is_eight_minutes():
    assert SECTOR_HARD_CAP_SECONDS == 480


from unittest.mock import MagicMock
from sector_bot.config import Sector


def _make_sector():
    return Sector(
        id=99,
        name="테스트섹터",
        name_en="test_sector",
        scheduled_time="12:00",
        search_keywords=["test"],
        analysis_focus=["focus"],
    )


def _passing_search_result():
    return {
        "success": True,
        "content": (
            "S&P 500 rose 1.2% on 2026-04-28. NVIDIA gained $5.20 on April 29, 2026. "
            "Korea KOSPI fell 0.8% on 2026-04-30. "
            "Bullish analysts cite upside; bears warn of downside risk. "
            "매수 추천 NVDA, TSM."
        ),
        "sources": [
            {"url": "https://www.bloomberg.com/x"},
            {"url": "https://www.reuters.com/y"},
        ],
    }


def test_round1_only_when_max_rounds_one(monkeypatch):
    sector = _make_sector()

    searcher = MagicMock()
    searcher.search_sector.return_value = _passing_search_result()
    searcher._use_cli_fallback = False

    analyzer = MagicMock()
    analyzer.analyze_sector.return_value = {
        "success": True,
        "analysis": "final analysis text " * 100,
        "sources": _passing_search_result()["sources"],
    }
    analyzer._use_cli_fallback = False

    fake_claude = MagicMock(return_value='{"정의": true, "현황": true, "근거": true, "반론": true, "적용": true}')

    result = run_sector_research(
        sector=sector,
        searcher=searcher,
        analyzer=analyzer,
        max_rounds=1,
        claude_caller=fake_claude,
    )

    assert result.success is True
    assert result.rounds_completed == 1
    assert result.clamped_to_cli is False
    assert all(result.dimensions_passed.values())
    searcher.search_sector.assert_called_once_with(sector)
    analyzer.analyze_sector.assert_called_once()


def test_clamps_to_one_round_when_cli_fallback_active():
    sector = _make_sector()

    searcher = MagicMock()
    searcher.search_sector.return_value = _passing_search_result()
    searcher._use_cli_fallback = True  # fallback active

    analyzer = MagicMock()
    analyzer.analyze_sector.return_value = {
        "success": True,
        "analysis": "x" * 600,
        "sources": [],
    }
    analyzer._use_cli_fallback = False

    fake_claude = MagicMock(return_value='{"정의": false, "현황": false, "근거": false, "반론": false, "적용": false}')

    result = run_sector_research(
        sector=sector,
        searcher=searcher,
        analyzer=analyzer,
        max_rounds=3,  # would normally do gap-fill
        claude_caller=fake_claude,
    )

    assert result.clamped_to_cli is True
    assert result.rounds_completed == 1  # clamped despite max_rounds=3
    assert searcher.search_sector.call_count == 1  # no gap-fill


def test_round1_failure_returns_early_with_zero_rounds():
    sector = _make_sector()

    searcher = MagicMock()
    searcher.search_sector.return_value = {
        "success": False,
        "error": "Gemini quota exhausted",
        "content": "",
        "sources": [],
    }
    searcher._use_cli_fallback = False

    analyzer = MagicMock()
    analyzer._use_cli_fallback = False

    fake_claude = MagicMock(return_value="not used")

    result = run_sector_research(
        sector=sector,
        searcher=searcher,
        analyzer=analyzer,
        max_rounds=2,
        claude_caller=fake_claude,
    )

    assert result.success is False
    assert result.rounds_completed == 0
    assert "Gemini quota exhausted" in result.error
    assert all(v is False for v in result.dimensions_passed.values())
    # Critically: analyze must not be called when round 1 failed
    analyzer.analyze_sector.assert_not_called()
    # Claude judge also must not be called
    fake_claude.assert_not_called()


def test_failed_gap_fill_does_not_consume_rounds_completed_but_does_consume_attempts():
    """
    With max_rounds=3 (so 2 gap-fill attempts available), a failed gap-fill
    should NOT increment rounds_completed but SHOULD count toward the attempt
    budget so we don't loop forever on chained failures.
    """
    sector = _make_sector()

    # Round 1 returns minimal content that fails most quant checks
    minimal_first = {
        "success": True,
        "content": "Some sector text without dates or specific numbers.",
        "sources": [],
    }
    # All gap-fill attempts fail
    failing_gap = {"success": False, "error": "503 service unavailable"}

    searcher = MagicMock()
    searcher.search_sector.side_effect = [minimal_first, failing_gap, failing_gap]
    searcher._use_cli_fallback = False

    analyzer = MagicMock()
    analyzer.analyze_sector.return_value = {
        "success": True,
        "analysis": "x" * 600,
        "sources": [],
    }
    analyzer._use_cli_fallback = False

    # Claude judge says everything fails so gap-fill loop will try
    fake_claude = MagicMock(return_value='{"정의": false, "현황": false, "근거": false, "반론": false, "적용": false}')

    result = run_sector_research(
        sector=sector,
        searcher=searcher,
        analyzer=analyzer,
        max_rounds=3,
        claude_caller=fake_claude,
    )

    assert result.success is True  # final analyze still ran
    # Round 1 succeeded; 2 gap-fill attempts both failed → rounds_completed stays at 1
    assert result.rounds_completed == 1
    # Searcher was called for round 1 + 2 gap-fill attempts (budget = max_rounds-1 = 2)
    assert searcher.search_sector.call_count == 3
