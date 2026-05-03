"""
Sector Research Orchestrator
----------------------------
Wraps searcher + analyzer with a 5-dimension Claude verification gate
and one targeted Gemini gap-fill round. Produces a richer search context
before the final analyzer call without modifying searcher/analyzer themselves.

Hard cap: 8 minutes per sector. CLI fallback active → max_rounds clamped to 1.
"""

import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .config import Sector
from .dimensions import SECTOR_DIMENSIONS, claude_judge_dimensions
from .gemini_cli import is_cli_mode_active

logger = logging.getLogger(__name__)


SECTOR_HARD_CAP_SECONDS = 480  # 8 minutes per sector
CLAUDE_JUDGE_TIMEOUT = 120     # seconds
DEFAULT_MAX_ROUNDS = 2


@dataclass
class OrchestrationResult:
    success: bool
    analysis: str
    sources: List[dict]
    rounds_completed: int
    dimensions_passed: Dict[str, bool]
    elapsed_seconds: float
    clamped_to_cli: bool
    error: Optional[str] = None
    contradictions: List[str] = field(default_factory=list)


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
        os.unlink(temp_file)


def run_sector_research(
    sector: Sector,
    searcher,
    analyzer,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    claude_caller: Optional[Callable[[str], str]] = None,
) -> OrchestrationResult:
    """
    Sequence: search → 5-dim gate → optional gap-fill → analyze.
    Returns OrchestrationResult capturing dimension scores and timing.
    """
    raise NotImplementedError("filled in by Task 8-11")
