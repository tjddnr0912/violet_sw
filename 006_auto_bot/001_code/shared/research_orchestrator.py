"""
Multi-round research orchestrator.

Drives Gemini CLI for searching + Claude CLI for evaluation/synthesis
with a 5-dimension gap-check between rounds. Used as the Telegram bot's
default research path; users can opt out of the multi-round flow with
the `/quick` command.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str], None]


@dataclass
class ResearchResult:
    content: str
    title: str
    labels: list[str]
    sources: list[dict]
    rounds_completed: int
    contradictions_noted: list[str] = field(default_factory=list)


DEFAULT_GEMINI_TIMEOUT = 600  # 10 min per round


class GeminiRoundError(RuntimeError):
    """Raised when a Gemini CLI round fails (non-zero exit or empty)."""


def _run_gemini_round(prompt: str, timeout: int = DEFAULT_GEMINI_TIMEOUT) -> str:
    """Invoke `gemini -p <prompt>` and return stdout. Raises GeminiRoundError on failure."""
    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise GeminiRoundError(
            f"gemini exit={result.returncode} stderr={result.stderr.strip()[:300]}"
        )
    out = (result.stdout or "").strip()
    if not out:
        raise GeminiRoundError(f"gemini returned empty stdout (stderr={result.stderr.strip()[:200]})")
    return out


QA_SKILL_FILE = os.path.expanduser('~/.claude/skills/telegram-qa/SKILL.md')


def _load_skill_body(path: str) -> str:
    """Load a skill file with YAML frontmatter stripped."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Skill file not found: {path}")
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    return re.sub(r'^---\s*\n.*?\n---\s*\n?', '', content, count=1, flags=re.DOTALL).strip()


_METADATA_TRAILER = """
---
[중요] 답변 본문 작성 완료 후 반드시 아래 3줄을 포함할 것 (코드블록 없이 플레인 텍스트로):
TITLE: (제목)
LABELS: (키워드 2-3개)
SOURCES: (출처)
"""


def _build_round1_prompt(question: str) -> str:
    skill = _load_skill_body(QA_SKILL_FILE)
    return f"{skill}\n\n# 질문\n\n{question}\n{_METADATA_TRAILER}"


def run_research(
    question: str,
    max_rounds: int = 3,
    progress_callback: Optional[ProgressCallback] = None,
) -> ResearchResult:
    raise NotImplementedError("populated in later tasks")
