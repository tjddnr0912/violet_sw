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
