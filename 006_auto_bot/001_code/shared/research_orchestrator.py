"""
Multi-round research orchestrator.

Drives Claude CLI + WebSearch for each search round + Claude CLI for
evaluation/synthesis between rounds, with a 5-dimension gap-check.
Used as the Telegram bot's default research path; users can opt out of
the multi-round flow with the `/quick` command.

Migration history:
  - Pre 2026-05-27: each round shelled out to `gemini -p` (deprecated)
  - 2026-05-27 AM: switched to google-genai SDK with model fallback chain
  - 2026-05-27 PM: switched again to Claude CLI + WebSearch — Gemini 3.x
    grounding hit 429 across the entire family even with model RPD usage
    at 10/500, because google_search grounding has a separate quota
    bucket invisible to the AI Studio dashboard. Claude WebSearch lives
    in a different bucket.

The legacy symbol names `_run_gemini_round` and `GeminiRoundError` are
kept verbatim so existing exception handlers and call sites don't need
to change — only the implementation moved.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable, Optional

from shared.claude_search import (
    ClaudeSearchError,
    ClaudeSearchResponse,
)
from shared.web_search import web_search

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


DEFAULT_GEMINI_TIMEOUT = 900  # 15 min — Claude WebSearch with grounding can take a while


class GeminiRoundError(RuntimeError):
    """Raised when a research round fails. Name kept for backward compat;
    actual backend has moved from Gemini API → Claude CLI + WebSearch."""


def _run_gemini_round(prompt: str, timeout: int = DEFAULT_GEMINI_TIMEOUT) -> str:
    """Run one research round via web search (agy cascade -> Claude fallback).

    Primary is the agy Gemini cascade; if exhausted, Claude (Sonnet primary,
    Haiku fallback) answers — multi-round deep research still benefits from
    that analysis depth on the fallback path.

    Returns the response text (may include an inline `Sources:` footer
    that Claude appends automatically). Raises GeminiRoundError on any
    failure so existing except clauses upstream keep working.
    """
    try:
        response: ClaudeSearchResponse = web_search(
            prompt,
            model="sonnet",
            fallback_model="haiku",
            timeout=timeout,
        )
    except ClaudeSearchError as e:
        raise GeminiRoundError(f"web_search failed: {e}") from e
    except Exception as e:
        raise GeminiRoundError(f"research round failed: {e}") from e

    text = (response.text or "").strip()
    if not text:
        raise GeminiRoundError(
            f"claude returned empty text (model={response.model_used})"
        )

    # If WebSearch produced URIs that the prompt didn't already echo back as a
    # SOURCES: trailer, append one so the downstream metadata parser
    # (_parse_metadata_trailer) can pick them up.
    if response.sources and not re.search(r"\bSOURCES?:", text):
        sources_line = ", ".join(response.sources[:8])
        text = f"{text}\n\nSOURCES: {sources_line}"
    return text


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
- **질문은 '주제·의도'로만 사용한다.** 질문에 담긴 전제·가정·수치를 사실로 단정하지 말고,
  조사로 확인되지 않으면 교정하거나 "질문의 전제와 달리 …" 식으로 바로잡아 서술한다.
- **독자는 원 질문을 보지 못한다.** 질문을 인용하거나 되묻지 말고("~라는 질문을 주셨는데" 금지),
  주제에 대한 독립적·자기완결적 기사로 작성한다.
- 본문은 마크다운. 헤더와 목록을 적극 활용.
- 모순이 있으면 그대로 살려서 "자료 A는 X라 하지만 자료 B는 Y라 함" 식으로 명시.
- 근거 없는 추측 금지. 출처는 인라인 인용.
- 기술 주제(아키텍처·프로토콜·SoC·반도체 등)면 **본문에 근거가 있는 경우에 한해** 시각화를
  코드블록으로 직접 포함하라(발행 시 자동으로 이미지로 렌더됨):
  구조·계층 블록도는 ```d2, 신호/클럭 타이밍 파형은 ```wavedrom, 흐름·관계·의사결정은 ```mermaid.
  **d2 문법 주의(틀리면 kroki 컴파일 실패 → 그림이 코드로 그대로 박힌다):** shape은 d2에 실제 있는
  것만 쓴다 — rectangle/square/circle/oval/diamond/hexagon/cylinder/queue/package/stored_data/
  document/cloud/person 등. mermaid의 `database` shape은 d2에 없으므로 DB·메모리는 `cylinder` 또는
  `stored_data`로. 굵게는 CSS `font-weight`가 아니라 style 블록 안의 `bold: true`. 확실치 않은
  shape·스타일 키워드는 아예 쓰지 말 것(억지로 쓰면 전체 그림이 깨진다).
  **근거 없는(지어낸) 다이어그램은 절대 만들지 말 것** — 특히 wavedrom 타이밍은 출처에 실제
  신호 동작이 명시된 경우에만 그린다. 일반 코드 예시는 그냥 일반 코드블록으로 둔다.
  **파형(wavedrom)은 의미론적으로 정확하고 본문 설명과 반드시 일치시켜라.** 레벨 민감 래치는
  enable/clock High 동안 D를 즉시 따라가고(중간 글리치·하강까지 그대로 통과) Low에서 직전 값을
  유지한다; 엣지 트리거 FF는 클럭 엣지 순간의 D만 포착하고 그 외 구간 변화·글리치는 무시한다.
  "Latch가 D를 따라간다"고 써놓고 파형의 Latch가 D 변화를 무시하는 식의 글-그림 모순 금지.
  같은 레벨이 이어지면 리터럴 반복(0000) 대신 '.'(직전 상태 계승)로 그려라.
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
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")
    if max_rounds > 4:
        logger.warning(f"max_rounds={max_rounds} clamped to 4")
        max_rounds = 4

    def report(msg: str):
        if progress_callback:
            try:
                progress_callback(msg)
            except Exception as e:
                logger.warning(f"progress_callback raised: {e}")

    accumulated: list = []
    contradictions: list = []
    rounds_done = 0

    # Round 1
    report(f"Round 1/{max_rounds} — broad sweep…")
    try:
        round1 = _run_gemini_round(_build_round1_prompt(question))
        accumulated.append(("Round 1", round1))
        rounds_done = 1
    except GeminiRoundError as e:
        # subprocess.TimeoutExpired/FileNotFoundError used to be possible when
        # this called the `gemini` CLI binary; post-May-2026 the wrapper raises
        # only GeminiRoundError, which already wraps API failures and timeouts.
        logger.error(f"Round 1 failed: {e}")
        report(f"Round 1 실패: {str(e)[:120]}")
        return _empty_result_with_error(question, str(e))

    # Eval / Round N loop
    next_round = 2
    while next_round <= max_rounds:
        report(f"평가 중 (5차원 체크)…")
        try:
            decision = _evaluate_round(question, accumulated)
        except subprocess.TimeoutExpired:
            logger.warning("eval timed out, treating as pass")
            decision = {"verdict": "pass", "missing_dimensions": [], "next_query": None, "contradictions": []}

        for c in decision.get("contradictions", []) or []:
            if c and c not in contradictions:
                contradictions.append(c)

        verdict = decision.get("verdict")
        if verdict not in ("pass", "continue"):
            logger.warning(f"unexpected verdict {verdict!r}, treating as pass")
            report("평가 결과 비정상 — 종합 작성으로")
            break
        if verdict == "pass":
            report("충분 — 종합 작성 단계로")
            break
        targeted = decision.get("next_query")
        if not targeted:
            report("후속 query 없음 — 종합 작성으로")
            break

        report(f"Round {next_round}/{max_rounds} — 보강 ({', '.join(decision.get('missing_dimensions', []) or ['gap'])})…")
        try:
            body = _run_gemini_round(
                _build_round_n_prompt(question, targeted, next_round)
            )
            accumulated.append((f"Round {next_round}", body))
            rounds_done = next_round
        except GeminiRoundError as e:
            # See Round 1 comment — subprocess exceptions can no longer occur
            # on the Gemini path.
            logger.warning(f"Round {next_round} failed: {e}")
            report(f"Round {next_round} 실패 — 누적 결과로 종합 진행")
            break
        next_round += 1

    # Synthesis
    report("Claude 종합 작성 중…")
    try:
        final_md = _synthesize(question, accumulated, contradictions)
    except subprocess.TimeoutExpired:
        logger.error("synth timed out, using fallback")
        final_md = _fallback_synthesis(accumulated, contradictions)

    content, title, labels, sources = _parse_metadata_trailer(final_md)
    return ResearchResult(
        content=content,
        title=title,
        labels=labels,
        sources=sources,
        rounds_completed=rounds_done,
        contradictions_noted=contradictions,
    )


def _empty_result_with_error(question: str, err: str) -> ResearchResult:
    return ResearchResult(
        content=f"⚠️ 조사 실패: {err[:200]}",
        title=question[:60],
        labels=["오류"],
        sources=[],
        rounds_completed=0,
        contradictions_noted=[],
    )


def _parse_metadata_trailer(text: str):
    """Reuse the same logic as telegram_gemini_bot._parse_response, in-line copy."""
    lines = text.strip().split('\n')
    title = ""
    labels: list = []
    sources: list = []
    content_end = len(lines)
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        if m := re.match(r'^SOURCES?:\s*(.+)$', line, re.IGNORECASE):
            for src in m.group(1).split(','):
                src = src.strip()
                if '|' in src:
                    t, u = src.split('|', 1)
                    if u.strip() and t.strip():
                        sources.append({"title": t.strip(), "url": u.strip()})
                elif src.startswith('http'):
                    sources.append({"title": src, "url": src})
            content_end = min(content_end, i)
        elif m := re.match(r'^LABELS?:\s*(.+)$', line, re.IGNORECASE):
            labels = [s.strip() for s in m.group(1).split(',') if s.strip()]
            content_end = min(content_end, i)
        elif m := re.match(r'^TITLE:\s*(.+)$', line, re.IGNORECASE):
            title = m.group(1).strip()
            content_end = min(content_end, i)
    body_lines = lines[:content_end]
    while body_lines and body_lines[-1].strip() in ('---', ''):
        body_lines.pop()
    if not title:
        title = (text.strip().split('\n', 1)[0][:60]).lstrip('#').strip() or "조사 결과"
    if not labels:
        labels = ["리서치", "분석"]
    return ('\n'.join(body_lines).strip(), title, labels, sources)
