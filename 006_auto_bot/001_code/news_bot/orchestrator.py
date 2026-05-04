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
