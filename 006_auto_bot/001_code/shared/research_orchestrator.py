"""
Multi-round research orchestrator.

Drives Gemini CLI for searching + Claude CLI for evaluation/synthesis
with a 5-dimension gap-check between rounds. Used as the Telegram bot's
default research path; users can opt out of the multi-round flow with
the `/quick` command.
"""

from __future__ import annotations

import json
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


DEFAULT_CLAUDE_TIMEOUT = 240

_EVAL_PROMPT_TEMPLATE = """다음은 사용자 질문과 그에 대한 다라운드 조사 결과다.
5차원 체크리스트로 평가하고 JSON으로만 답하라.

질문:
{question}

누적 조사 결과:
{rounds_dump}

차원:
1. 정의 — 주제와 핵심 용어가 명확한가
2. 현황 — 수치/날짜/주체가 있는 구체 사실 3개 이상 있는가
3. 근거 — 신뢰할 만한 1차/주류 출처 2개 이상 있는가
4. 반론 — 한계·반대 시각·리스크가 1개 이상 다뤄졌는가
5. 적용 — 사용자에게 의미 있는 함의가 있는가

JSON 스키마(반드시 이 키들만):
{{
  "verdict": "pass" | "continue",
  "missing_dimensions": ["정의" | "현황" | "근거" | "반론" | "적용", ...],
  "next_query": "다음 라운드에 Gemini로 던질 한국어 또는 영어 검색 query (continue일 때만, 아니면 null)",
  "contradictions": ["라운드 간 충돌이 보이면 한 줄씩, 없으면 빈 배열"]
}}

설명 없이 ```json 코드블록만 출력하라."""


def _evaluate_round(
    question: str,
    accumulated_rounds: list,
    timeout: int = DEFAULT_CLAUDE_TIMEOUT,
) -> dict:
    rounds_dump = "\n\n".join(
        f"=== {label} ===\n{body}" for label, body in accumulated_rounds
    )
    prompt = _EVAL_PROMPT_TEMPLATE.format(
        question=question, rounds_dump=rounds_dump
    )

    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        logger.warning(f"claude eval exit={result.returncode}: {result.stderr[:300]}")
        return {"verdict": "pass", "missing_dimensions": [], "next_query": None, "contradictions": []}

    return _extract_eval_json(result.stdout)


def _extract_eval_json(raw: str) -> dict:
    m = re.search(r'```json\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if not m:
        m = re.search(r'(\{[^{}]*"verdict"[^{}]*\})', raw, re.DOTALL)
    if not m:
        logger.warning("no JSON found in claude eval output, defaulting to pass")
        return {"verdict": "pass", "missing_dimensions": [], "next_query": None, "contradictions": []}
    try:
        decision = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        logger.warning(f"json parse failed: {e}; defaulting to pass")
        return {"verdict": "pass", "missing_dimensions": [], "next_query": None, "contradictions": []}

    decision.setdefault("verdict", "pass")
    decision.setdefault("missing_dimensions", [])
    decision.setdefault("next_query", None)
    decision.setdefault("contradictions", [])
    return decision


def _build_round_n_prompt(original_question: str, targeted_query: str, round_number: int) -> str:
    return (
        f"# 후속 조사 — Round {round_number}\n\n"
        f"## 원래 질문\n{original_question}\n\n"
        f"## 이번 라운드의 좁힌 질문\n{targeted_query}\n\n"
        "이전 라운드의 broad sweep을 반복하지 말고, 위 좁힌 질문에만 답하라. "
        "출처 URL과 날짜를 인용하라. 한국어로 답하되, 1차 자료가 영어면 인용은 영어 그대로."
    )


_SYNTH_PROMPT_TEMPLATE = """다음은 사용자 질문과 그에 대한 다라운드 조사 결과, 그리고 라운드 간 모순 목록이다.
이를 종합해 telegram-qa 스킬의 톤(싱크탱크 수석 연구원 페르소나, 한국어, 마크다운, 최소 1500자, 근거-기반)으로 최종 보고서를 작성하라.

질문:
{question}

누적 조사 결과:
{rounds_dump}

라운드 간 발견된 모순(있으면 본문에 명시):
{contradictions_dump}

요구사항:
- 본문은 마크다운. 헤더와 목록을 적극 활용.
- 모순이 있으면 그대로 살려서 "자료 A는 X라 하지만 자료 B는 Y라 함" 식으로 명시.
- 근거 없는 추측 금지. 출처는 인라인 인용.
- 본문 마지막에 빈 줄 하나 두고, 코드블록 없이 정확히 아래 3줄을 출력:

TITLE: (제목)
LABELS: (키워드 2-3개, 쉼표 구분)
SOURCES: (제목|URL 형태, 쉼표 구분)
"""


def _synthesize(
    question: str,
    accumulated_rounds: list,
    contradictions: list,
    timeout: int = DEFAULT_CLAUDE_TIMEOUT,
) -> str:
    rounds_dump = "\n\n".join(
        f"=== {label} ===\n{body}" for label, body in accumulated_rounds
    )
    contradictions_dump = (
        "\n".join(f"- {c}" for c in contradictions) if contradictions else "(없음)"
    )
    prompt = _SYNTH_PROMPT_TEMPLATE.format(
        question=question,
        rounds_dump=rounds_dump,
        contradictions_dump=contradictions_dump,
    )

    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        logger.error(f"claude synth failed: {result.stderr[:300]}")
        return _fallback_synthesis(accumulated_rounds, contradictions)
    return result.stdout.strip()


def _fallback_synthesis(accumulated_rounds: list, contradictions: list) -> str:
    """If Claude synth fails, return a concatenated dump as last resort."""
    body = "\n\n".join(f"## {label}\n{body}" for label, body in accumulated_rounds)
    if contradictions:
        body += "\n\n## 발견된 모순\n" + "\n".join(f"- {c}" for c in contradictions)
    body += "\n\nTITLE: 조사 결과\nLABELS: 리서치, 분석\nSOURCES: \n"
    return body


def run_research(
    question: str,
    max_rounds: int = 3,
    progress_callback: Optional[ProgressCallback] = None,
) -> ResearchResult:
    raise NotImplementedError("populated in later tasks")
