"""
Multi-round research orchestrator.

Drives Gemini CLI for searching + Claude CLI for evaluation/synthesis
with a 5-dimension gap-check between rounds. Used by the Telegram bot's
`/deep` mode to replace single-shot Gemini calls.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


@dataclass
class ResearchResult:
    content: str
    title: str
    labels: list
    sources: list
    rounds_completed: int
    contradictions_noted: list = field(default_factory=list)


def run_research(
    question: str,
    max_rounds: int = 3,
    progress_callback: Optional[ProgressCallback] = None,
) -> ResearchResult:
    raise NotImplementedError("populated in later tasks")
