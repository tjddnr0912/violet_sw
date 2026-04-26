# Research Orchestrator — Telegram QA Bot Enhancement Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make multi-round, self-verifying research the default for the Telegram QA bot — every plain-text message goes through an orchestrated Gemini × Claude pipeline because everything ends up on a blog where fact-checking matters. A `/quick` opt-out keeps the legacy single-shot Gemini path available for casual queries or short-time-budget cases.

**Architecture:** New Python module `shared/research_orchestrator.py` runs N rounds of Gemini search (broad sweep → targeted gap-fill) with Claude evaluating each round against a 5-dimension checklist (definition / status / evidence / counter-arguments / application). A final Claude synthesis pass produces telegram-qa-style markdown with TITLE/LABELS/SOURCES metadata. `telegram_gemini_bot.py` routes by mode: plain text → `mode="deep"` (orchestrator), text starting with the configurable opt-out command (default `/quick`) → `mode="quick"` (legacy single-shot). Both modes share the same multi-blog selection UI, HTML conversion, and Blogger upload paths — only the research stage differs.

**Tech Stack:** Python 3.13+, `subprocess` only (no new deps), Gemini CLI (existing `~/.claude/skills/research/scripts/ask_gemini.sh`), Claude CLI (existing `claude -p`), shared modules already in `001_code/shared/`.

---

## 1. Change Summary

Drop a new orchestrator module beside `claude_html_converter.py` and route it as the **default** research path in the Telegram bot. Add a `mode` field to the existing `pending_uploads` dict so the multi-blog selection UI works unchanged for both modes; the only branch is at the research call site (`run_research` vs legacy `run_gemini`). HTML conversion and Blogger upload stages are reused as-is. A `/quick <질문>` opt-out preserves the legacy single-shot flow for casual queries or when a short-time-budget answer is preferred. (Gemini quota is a non-issue in practice — operator runs on Google One AI Pro Code Assist tier; details in §7.)

## 2. File Inventory (Create / Modify)

| Action | Path | Lines | Responsibility |
|---|---|---|---|
| Create | `001_code/shared/research_orchestrator.py` | ~280 LOC | `run_research()` entry point, round dispatcher, Claude eval+synth wrappers, `ResearchResult` dataclass |
| Modify | `001_code/telegram_gemini_bot.py` (`__init__`, ~75-92) | +3 lines | Read `RESEARCH_QUICK_COMMAND`, `RESEARCH_MAX_ROUNDS` from env |
| Modify | `001_code/telegram_gemini_bot.py:311-336` | `process_message()` — classify `mode = "quick"` vs `mode = "deep"`, pass through to existing single-blog or multi-blog flows |
| Modify | `001_code/telegram_gemini_bot.py:338-392` | `_show_blog_selection_first()` — accept `mode`, persist into `pending_uploads` |
| Modify | `001_code/telegram_gemini_bot.py:394-443` | `_process_and_upload_single()` — accept `mode`, branch research call |
| Modify | `001_code/telegram_gemini_bot.py:445-480` | `_handle_callback_query()` — read `mode` from pending, forward to selection handler |
| Modify | `001_code/telegram_gemini_bot.py:482-540` | `_process_after_selection()` — accept `mode`, branch research call |
| Modify | `001_code/telegram_gemini_bot.py:542-561` | `_check_pending_timeouts()` — preserve `mode` when timing out to default-only |
| Modify | `001_code/telegram_gemini_bot.py:749-788` | `_handle_command()` — extend `/help` and `/status` text |
| Modify | `001_code/telegram_gemini_bot.py` (new method) | ~50 LOC | `_run_research_stage(question, message_id, mode) -> tuple` — single helper that returns `(success, content, title, labels, sources)` regardless of mode, so downstream stays uniform |
| Create | `003_test_code/test_research_orchestrator.py` | ~180 LOC | Unit tests with stubbed subprocess; integration smoke test gated by env var |
| Modify | `001_code/.env.example` (or `docs/`) | +2 lines | Document `RESEARCH_QUICK_COMMAND`, `RESEARCH_MAX_ROUNDS` |
| Modify | `docs/TELEGRAM_BOT.md` | +1 section | Document new default = deep, `/quick` opt-out, latency, quota implications |

**Files NOT touched:**
- `shared/claude_html_converter.py` — orchestrator output is markdown with the same metadata trailer the converter already expects.
- `shared/blogger_uploader.py` — unchanged.
- `shared/telegram_api.py` — unchanged.
- `~/.claude/skills/research/` — read-only reference; orchestrator does NOT depend on the shell script (re-implements the loop in Python for testability).
- `~/.claude/skills/telegram-qa/SKILL.md` — reused verbatim as the Round-1 prompt; never edited.

## 3. Data Flow

```
TG message ──► process_message()
                   │
                   ├── starts with "/quick " ? ──► mode = "quick"
                   │
                   └── otherwise ────────────────► mode = "deep"   (DEFAULT)
                                  │
                                  ▼
                  ┌── single blog ──┐    ┌── multi blog ──┐
                  │                 │    │                │
                  │  _process_and_  │    │ _show_blog_    │
                  │  upload_single  │    │ selection_     │
                  │  (mode)         │    │ first(mode)    │
                  │                 │    │   │            │
                  │                 │    │   ▼            │
                  │                 │    │ pending_       │
                  │                 │    │ uploads[mid] = │
                  │                 │    │ {q, mode, ...} │
                  │                 │    │   │            │
                  │                 │    │   ▼            │
                  │                 │    │ user clicks    │
                  │                 │    │   │            │
                  │                 │    │   ▼            │
                  │                 │    │ _process_after_│
                  │                 │    │ selection(mode)│
                  │                 │    │                │
                  └────────┬────────┘    └────────┬───────┘
                           │                      │
                           └──────────┬───────────┘
                                      ▼
                       _run_research_stage(mode)
                                      │
                          ┌───────────┴───────────┐
                          │                       │
                     mode==quick              mode==deep
                          │                       │
                          ▼                       ▼
                     run_gemini()         run_research()
                     (1 round)            ┌─────────────────────────┐
                          │               │ Round 1: broad sweep    │
                          │               │   ↓                     │
                          │               │ Eval: Claude 5-dim JSON │
                          │               │   ↓                     │
                          │               │ pass? ─yes─► synth      │
                          │               │   no                    │
                          │               │   ↓                     │
                          │               │ Round N: targeted       │
                          │               │   ↓ (loop ≤ max_rounds) │
                          │               │ Synth: Claude markdown  │
                          │               │   + TITLE/LABELS/SRC    │
                          │               └───────────┬─────────────┘
                          │                           │
                          └───────────────┬───────────┘
                                          ▼
                                Claude HTML conversion
                                          │
                                          ▼
                            Blogger upload (default or dual)
                                          │
                                          ▼
                                   TG result message
```

Progress callbacks fire at: round start, eval result, synth start, done. Each callback edits the same Telegram message via `edit_message_text`. In `quick` mode no progress callback is needed (existing single status update is preserved).

## 4. Implementation Tasks

### Task 1: Stub `ResearchResult` and `run_research` signature with failing tests

**Files:**
- Create: `001_code/shared/research_orchestrator.py`
- Create: `003_test_code/test_research_orchestrator.py`

- [ ] **Step 1: Write failing test for module import + signature**

```python
# 003_test_code/test_research_orchestrator.py
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from shared.research_orchestrator import ResearchResult, run_research


def test_research_result_fields():
    r = ResearchResult(
        content="body",
        title="t",
        labels=["a"],
        sources=[{"title": "s", "url": "https://x"}],
        rounds_completed=1,
        contradictions_noted=[],
    )
    assert r.content == "body"
    assert r.rounds_completed == 1
    assert r.contradictions_noted == []


def test_run_research_signature():
    # Should accept question, max_rounds, progress_callback
    import inspect
    sig = inspect.signature(run_research)
    params = list(sig.parameters.keys())
    assert params[0] == "question"
    assert "max_rounds" in params
    assert "progress_callback" in params


if __name__ == "__main__":
    test_research_result_fields()
    test_run_research_signature()
    print("OK")
```

- [ ] **Step 2: Run test — expect ImportError**

Run: `cd /Users/seongwookjang/project/git/violet_sw/006_auto_bot && python 003_test_code/test_research_orchestrator.py`
Expected: `ModuleNotFoundError: No module named 'shared.research_orchestrator'`

- [ ] **Step 3: Create skeleton module**

```python
# 001_code/shared/research_orchestrator.py
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
```

- [ ] **Step 4: Run test — expect PASS on the two stub tests**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add 001_code/shared/research_orchestrator.py 003_test_code/test_research_orchestrator.py
git commit -m "Add research orchestrator skeleton (ResearchResult + run_research stub)"
```

---

### Task 2: Implement Gemini round runner with subprocess + timeout

**Files:**
- Modify: `001_code/shared/research_orchestrator.py` (add `_run_gemini_round`)
- Modify: `003_test_code/test_research_orchestrator.py` (add stubbing test)

- [ ] **Step 1: Write failing test using monkey-patched subprocess**

```python
# Append to 003_test_code/test_research_orchestrator.py
def test_gemini_round_returns_stdout_on_success():
    from shared import research_orchestrator as ro

    class FakeCompleted:
        returncode = 0
        stdout = "round 1 output"
        stderr = ""

    captured = {}
    def fake_run(cmd, capture_output, text, timeout):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        return FakeCompleted()

    original = ro.subprocess.run
    ro.subprocess.run = fake_run
    try:
        text = ro._run_gemini_round("hello world prompt", timeout=42)
    finally:
        ro.subprocess.run = original

    assert text == "round 1 output"
    assert captured["cmd"][0] == "gemini"
    assert captured["timeout"] == 42


def test_gemini_round_raises_on_failure():
    from shared import research_orchestrator as ro

    class FakeCompleted:
        returncode = 1
        stdout = ""
        stderr = "429 quota"

    original = ro.subprocess.run
    ro.subprocess.run = lambda *a, **kw: FakeCompleted()
    try:
        try:
            ro._run_gemini_round("p", timeout=10)
            assert False, "should have raised"
        except ro.GeminiRoundError as e:
            assert "429" in str(e)
    finally:
        ro.subprocess.run = original
```

Add the new test calls at the bottom `__main__` block.

- [ ] **Step 2: Run test — expect AttributeError on `_run_gemini_round`**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `AttributeError: module ... has no attribute '_run_gemini_round'`

- [ ] **Step 3: Implement Gemini runner**

Add to `research_orchestrator.py`:

```python
import subprocess

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
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add 001_code/shared/research_orchestrator.py 003_test_code/test_research_orchestrator.py
git commit -m "Add _run_gemini_round subprocess wrapper with timeout"
```

---

### Task 3: Implement Round-1 prompt builder reusing telegram-qa skill

**Files:**
- Modify: `001_code/shared/research_orchestrator.py`
- Modify: `003_test_code/test_research_orchestrator.py`

- [ ] **Step 1: Write failing test**

```python
def test_round1_prompt_includes_question_and_skill():
    from shared.research_orchestrator import _build_round1_prompt
    p = _build_round1_prompt("티스토리 API 종료 현황")
    assert "티스토리 API 종료 현황" in p
    # Skill content marker — telegram-qa SKILL.md contains this Korean phrase
    assert "싱크탱크" in p or "리서치" in p
    # Metadata trailer instruction
    assert "TITLE:" in p
    assert "LABELS:" in p
    assert "SOURCES:" in p
```

- [ ] **Step 2: Run test — expect AttributeError**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `AttributeError: ... '_build_round1_prompt'`

- [ ] **Step 3: Implement prompt builder**

```python
import os
import re

QA_SKILL_FILE = os.path.expanduser('~/.claude/skills/telegram-qa/SKILL.md')


def _load_skill_body(path: str) -> str:
    """Load a skill file with YAML frontmatter stripped."""
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
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add 001_code/shared/research_orchestrator.py 003_test_code/test_research_orchestrator.py
git commit -m "Add round-1 prompt builder reusing telegram-qa skill"
```

---

### Task 4: Implement Claude evaluator (5-dimension check, JSON output)

**Files:**
- Modify: `001_code/shared/research_orchestrator.py`
- Modify: `003_test_code/test_research_orchestrator.py`

- [ ] **Step 1: Write failing test (stubbed Claude subprocess)**

```python
def test_evaluate_round_parses_pass_decision():
    from shared import research_orchestrator as ro

    fake_json = '''
    Some preamble.
    ```json
    {
      "verdict": "pass",
      "missing_dimensions": [],
      "next_query": null,
      "contradictions": ["A claims X, B claims Y"]
    }
    ```
    trailing noise.
    '''

    class FakeCompleted:
        returncode = 0
        stdout = fake_json
        stderr = ""

    original = ro.subprocess.run
    ro.subprocess.run = lambda *a, **kw: FakeCompleted()
    try:
        decision = ro._evaluate_round(
            question="q",
            accumulated_rounds=[("Round 1", "content...")],
        )
    finally:
        ro.subprocess.run = original

    assert decision["verdict"] == "pass"
    assert decision["missing_dimensions"] == []
    assert decision["contradictions"] == ["A claims X, B claims Y"]


def test_evaluate_round_parses_continue_with_query():
    from shared import research_orchestrator as ro

    fake_json = '''```json
{"verdict": "continue", "missing_dimensions": ["evidence"], "next_query": "Find primary source for X", "contradictions": []}
```'''

    class FakeCompleted:
        returncode = 0
        stdout = fake_json
        stderr = ""

    original = ro.subprocess.run
    ro.subprocess.run = lambda *a, **kw: FakeCompleted()
    try:
        decision = ro._evaluate_round(question="q", accumulated_rounds=[("R1", "x")])
    finally:
        ro.subprocess.run = original

    assert decision["verdict"] == "continue"
    assert decision["next_query"] == "Find primary source for X"
```

- [ ] **Step 2: Run test — expect AttributeError on `_evaluate_round`**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: AttributeError.

- [ ] **Step 3: Implement evaluator**

```python
import json

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
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add 001_code/shared/research_orchestrator.py 003_test_code/test_research_orchestrator.py
git commit -m "Add Claude 5-dimension round evaluator with JSON parsing"
```

---

### Task 5: Implement Round-N targeted prompt builder

**Files:**
- Modify: `001_code/shared/research_orchestrator.py`
- Modify: `003_test_code/test_research_orchestrator.py`

- [ ] **Step 1: Write failing test**

```python
def test_round_n_prompt_includes_targeted_query():
    from shared.research_orchestrator import _build_round_n_prompt
    p = _build_round_n_prompt(
        original_question="티스토리 API 종료",
        targeted_query="공식 공지의 정확한 종료일을 찾아라",
        round_number=2,
    )
    assert "Round 2" in p or "라운드 2" in p
    assert "공식 공지의 정확한 종료일을 찾아라" in p
    assert "티스토리 API 종료" in p
```

- [ ] **Step 2: Run test — expect AttributeError**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: AttributeError.

- [ ] **Step 3: Implement Round-N builder**

```python
def _build_round_n_prompt(original_question: str, targeted_query: str, round_number: int) -> str:
    return (
        f"# 후속 조사 — Round {round_number}\n\n"
        f"## 원래 질문\n{original_question}\n\n"
        f"## 이번 라운드의 좁힌 질문\n{targeted_query}\n\n"
        "이전 라운드의 broad sweep을 반복하지 말고, 위 좁힌 질문에만 답하라. "
        "출처 URL과 날짜를 인용하라. 한국어로 답하되, 1차 자료가 영어면 인용은 영어 그대로."
    )
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add 001_code/shared/research_orchestrator.py 003_test_code/test_research_orchestrator.py
git commit -m "Add round-N targeted prompt builder"
```

---

### Task 6: Implement Claude synthesizer (final markdown + metadata)

**Files:**
- Modify: `001_code/shared/research_orchestrator.py`
- Modify: `003_test_code/test_research_orchestrator.py`

- [ ] **Step 1: Write failing test**

```python
def test_synthesize_returns_markdown_with_metadata():
    from shared import research_orchestrator as ro

    fake_md = """# 정리

본문 내용입니다.

TITLE: 티스토리 API 종료 정리
LABELS: 티스토리, API, 자동화
SOURCES: 공식 공지|https://notice.tistory.com/2664
"""
    class FakeCompleted:
        returncode = 0
        stdout = fake_md
        stderr = ""

    original = ro.subprocess.run
    ro.subprocess.run = lambda *a, **kw: FakeCompleted()
    try:
        md = ro._synthesize(
            question="q",
            accumulated_rounds=[("R1", "x")],
            contradictions=["사례 충돌 1"],
        )
    finally:
        ro.subprocess.run = original

    assert "TITLE:" in md
    assert "LABELS:" in md
    assert "SOURCES:" in md
    assert "본문 내용입니다." in md
```

- [ ] **Step 2: Run test — expect AttributeError**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: AttributeError.

- [ ] **Step 3: Implement synthesizer**

```python
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
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add 001_code/shared/research_orchestrator.py 003_test_code/test_research_orchestrator.py
git commit -m "Add Claude synthesizer with fallback for telegram-qa style markdown"
```

---

### Task 7: Wire `run_research` end-to-end with progress callback + early-stop

**Files:**
- Modify: `001_code/shared/research_orchestrator.py`
- Modify: `003_test_code/test_research_orchestrator.py`

- [ ] **Step 1: Write failing integration test (all subprocess stubbed)**

```python
def test_run_research_pass_after_round1():
    from shared import research_orchestrator as ro

    call_log = []

    def fake_run(cmd, capture_output, text, timeout):
        class C:
            returncode = 0
            stderr = ""
        if cmd[0] == "gemini":
            call_log.append(("gemini", cmd[1][:30]))
            C.stdout = "Round 1 broad output\nTITLE: t\nLABELS: a,b\nSOURCES: s|https://x"
        elif cmd[0] == "claude":
            call_log.append(("claude", "eval-or-synth"))
            if "verdict" in cmd[1]:
                C.stdout = '```json\n{"verdict":"pass","missing_dimensions":[],"next_query":null,"contradictions":[]}\n```'
            else:
                C.stdout = "최종 본문\n\nTITLE: 최종\nLABELS: x,y\nSOURCES: s1|https://a"
        return C()

    progress = []
    original = ro.subprocess.run
    ro.subprocess.run = fake_run
    try:
        result = ro.run_research(
            "테스트 질문",
            max_rounds=3,
            progress_callback=lambda msg: progress.append(msg),
        )
    finally:
        ro.subprocess.run = original

    gemini_calls = [c for c in call_log if c[0] == "gemini"]
    assert len(gemini_calls) == 1, f"early-stop expected, got {len(gemini_calls)} gemini calls"
    assert result.rounds_completed == 1
    assert result.title == "최종"
    assert "x" in result.labels
    assert any("Round 1" in p for p in progress)


def test_run_research_runs_two_rounds_then_synthesizes():
    from shared import research_orchestrator as ro

    state = {"claude_eval_calls": 0}

    def fake_run(cmd, capture_output, text, timeout):
        class C:
            returncode = 0
            stderr = ""
        if cmd[0] == "gemini":
            C.stdout = "gemini output"
        elif cmd[0] == "claude":
            if "verdict" in cmd[1]:
                state["claude_eval_calls"] += 1
                if state["claude_eval_calls"] == 1:
                    C.stdout = '```json\n{"verdict":"continue","missing_dimensions":["근거"],"next_query":"find primary","contradictions":["A vs B"]}\n```'
                else:
                    C.stdout = '```json\n{"verdict":"pass","missing_dimensions":[],"next_query":null,"contradictions":[]}\n```'
            else:
                C.stdout = "본문\n\nTITLE: 최종2\nLABELS: a\nSOURCES: "
        return C()

    original = ro.subprocess.run
    ro.subprocess.run = fake_run
    try:
        result = ro.run_research("q", max_rounds=3)
    finally:
        ro.subprocess.run = original

    assert result.rounds_completed == 2
    assert "A vs B" in result.contradictions_noted
```

- [ ] **Step 2: Run test — expect NotImplementedError**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: NotImplementedError from skeleton.

- [ ] **Step 3: Replace `run_research` body with full loop**

```python
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
    except (GeminiRoundError, subprocess.TimeoutExpired) as e:
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

        if decision.get("verdict") == "pass":
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
        except (GeminiRoundError, subprocess.TimeoutExpired) as e:
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
```

- [ ] **Step 4: Run test — expect PASS**

Run: `python 003_test_code/test_research_orchestrator.py`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add 001_code/shared/research_orchestrator.py 003_test_code/test_research_orchestrator.py
git commit -m "Implement run_research orchestration loop with early-stop and fallback"
```

---

### Task 8: Wire deep-by-default routing with `/quick` opt-out

**Files:**
- Modify: `001_code/telegram_gemini_bot.py` (`__init__`, `process_message`, `_show_blog_selection_first`, `_handle_callback_query`, `_process_after_selection`, `_process_and_upload_single`, `_check_pending_timeouts`, plus new helper `_run_research_stage`)

The change is mode-threading: a single string `mode in {"quick","deep"}` flows through the existing functions so the rest of the pipeline (HTML, upload) stays uniform.

- [ ] **Step 1: Confirm exact current line ranges before editing**

Run: `grep -n "def \(process_message\|_show_blog_selection_first\|_handle_callback_query\|_process_after_selection\|_process_and_upload_single\|_check_pending_timeouts\)" 001_code/telegram_gemini_bot.py`

Note: line numbers may have drifted from this plan during prior tasks. Use the actual numbers from this grep output for the edits below.

- [ ] **Step 2: Add config in `__init__`**

In `TelegramGeminiBot.__init__` (currently around line 75-92), add right after `self.last_update_id = 0`:

```python
        # Quick-mode opt-out command (deep research is the default)
        self.quick_command = os.getenv("RESEARCH_QUICK_COMMAND", "/quick")
        self.research_max_rounds = int(os.getenv("RESEARCH_MAX_ROUNDS", "3"))
```

- [ ] **Step 3: Replace `process_message` body**

Replace the existing `process_message` body (currently lines ~311-336) with mode-classifying logic:

```python
    def process_message(self, message: dict) -> None:
        """Process received message"""
        text = message.get("text", "")
        chat = message.get("chat", {})

        # Only process allowed chat_id
        if str(chat.get("id")) != self.chat_id:
            logger.warning(f"Unauthorized chat_id: {chat.get('id')}")
            return

        # Slash commands like /start, /help, /status — but NOT the quick-mode command
        if text.startswith("/") and not self._is_quick_command(text):
            self._handle_command(text)
            return

        if not text:
            return

        # Mode classification: /quick = legacy single-shot; everything else = deep research
        if self._is_quick_command(text):
            question = self._strip_quick_prefix(text)
            if not question:
                self.send_message(f"Usage: {self.quick_command} <질문>")
                return
            mode = "quick"
        else:
            question = text
            mode = "deep"

        logger.info(f"Question received (mode={mode}, length={len(question)}): {question[:100]}{'...' if len(question) > 100 else ''}")

        # Multi-blog → show selection first; single-blog → process directly
        if len(self.blogs) > 1 and self.upload_to_blog:
            self._show_blog_selection_first(question=question, mode=mode)
        else:
            self._process_and_upload_single(question=question, mode=mode)
```

Add the helper methods near the bottom of the class (e.g. just before `def run`):

```python
    def _is_quick_command(self, text: str) -> bool:
        return text.startswith(self.quick_command + " ") or text.strip() == self.quick_command

    def _strip_quick_prefix(self, text: str) -> str:
        return text[len(self.quick_command):].strip()
```

- [ ] **Step 4: Thread `mode` through `_show_blog_selection_first`**

Change the signature and persist `mode` into `pending_uploads`:

```python
    def _show_blog_selection_first(self, question: str, mode: str = "deep") -> None:
        # ... existing keyboard build code unchanged ...

        # ... existing send_message_with_inline_keyboard call unchanged ...

        if result.get("success"):
            message_id = result["message_id"]
            self.pending_uploads[message_id] = {
                "question": question,
                "mode": mode,                        # <-- new field
                "created_at": time.time()
            }
            logger.info(f"Blog selection pending (msg_id: {message_id}, mode: {mode}, timeout: {timeout_min}min)")
        else:
            logger.warning("Failed to send selection UI, processing with default only")
            self._process_and_upload_single(question=question, mode=mode)
```

Also add `mode` to the message preview text so users see which mode they're in. Replace the existing `msg_text` formatting block with:

```python
        mode_label = "🔎 Deep research" if mode == "deep" else "⚡ Quick"
        msg_text = f"""<b>Question received! ({mode_label})</b>

<b>Question:</b>
{question_preview}

<b>Select blog to upload:</b>
(Auto-upload to {default_blog_name} only after {timeout_min} min)"""
```

- [ ] **Step 5: Update `_handle_callback_query` to forward `mode`**

In the existing function (around line 445-480), extend the call into `_process_after_selection`:

```python
        pending = self.pending_uploads.pop(message_id)
        self.answer_callback_query(callback_id, "Processing started...")
        self._process_after_selection(
            question=pending["question"],
            blog_key=blog_key,
            message_id=message_id,
            mode=pending.get("mode", "deep"),    # <-- pull mode out
        )
```

- [ ] **Step 6: Add `_run_research_stage` helper**

Insert this method right after `run_gemini` (around line 184):

```python
    def _run_research_stage(
        self,
        question: str,
        message_id: Optional[int],
        mode: str,
    ) -> Tuple[bool, str, str, list, list, list]:
        """
        Unified research call. Returns the same shape regardless of mode,
        plus a contradictions list (empty in quick mode).

        Returns: (success, content, title, labels, sources, contradictions)
        """
        if mode == "quick":
            success, content, title, labels, sources = self.run_gemini(question)
            return success, content, title, labels, sources, []

        # mode == "deep"
        from shared.research_orchestrator import run_research, ResearchResult

        def progress(msg: str):
            if message_id:
                preview = question[:120] + ("…" if len(question) > 120 else "")
                self.edit_message_text(message_id, f"🔎 {msg}\n질문: {preview}")

        try:
            result: ResearchResult = run_research(
                question,
                max_rounds=self.research_max_rounds,
                progress_callback=progress,
            )
        except Exception as e:
            logger.error(f"run_research raised: {e}", exc_info=True)
            return False, f"⚠️ Deep research 오류: {str(e)[:300]}", "", [], [], []

        if result.rounds_completed == 0:
            return False, result.content, result.title, result.labels, result.sources, []

        return True, result.content, result.title, result.labels, result.sources, result.contradictions_noted
```

- [ ] **Step 7: Refactor `_process_after_selection` to use mode + helper**

Replace the body (currently lines ~482-540) with:

```python
    def _process_after_selection(
        self,
        question: str,
        blog_key: str,
        message_id: int,
        mode: str = "deep",
    ) -> None:
        """Process question after blog selection (research → Claude HTML → Upload)."""
        opening = "🔎 Deep research 시작…" if mode == "deep" else "⚡ Asking Gemini…"
        self.edit_message_text(message_id, opening)
        logger.info(f"Processing after selection (blog={blog_key}, mode={mode})")

        success, content, title_hint, labels, sources, contradictions = \
            self._run_research_stage(question, message_id, mode)

        if not success:
            self.edit_message_text(message_id, content[:4000])
            return

        # Sources + optional contradictions section
        sources_section = self._format_sources_section(sources)
        full_md_content = content + sources_section
        if contradictions:
            full_md_content += "\n\n## 라운드 간 모순\n" + "\n".join(f"- {c}" for c in contradictions)

        # Claude HTML conversion
        self.edit_message_text(message_id, "Claude HTML 생성 중…")
        html_content = None
        claude_title = ""
        try:
            from shared.claude_html_converter import convert_md_to_html_via_claude
            html_content, claude_title = convert_md_to_html_via_claude(full_md_content)
            logger.info(f"Claude HTML done ({len(html_content)} chars)")
        except Exception as e:
            logger.warning(f"Claude HTML failed: {e}")

        final_title = claude_title or title_hint

        # Upload
        self.edit_message_text(message_id, "Uploading to blog…")
        if blog_key == "default_only":
            self._upload_default_only(
                md_content=full_md_content,
                html_content=html_content,
                title=final_title,
                labels=labels,
                sources=sources,
                message_id=message_id,
            )
        else:
            self._upload_dual(
                blog_key=blog_key,
                md_content=full_md_content,
                html_content=html_content,
                title=final_title,
                labels=labels,
                sources=sources,
                message_id=message_id,
            )
```

- [ ] **Step 8: Refactor `_process_and_upload_single` to use mode + helper**

Replace the body (currently lines ~394-443) with:

```python
    def _process_and_upload_single(
        self,
        question: str,
        message_id: Optional[int] = None,
        mode: str = "deep",
    ) -> None:
        """Process question and upload to default blog only (single-blog mode)."""
        opening = "🔎 Deep research 시작…" if mode == "deep" else "⚡ Asking Gemini…"
        if message_id:
            self.edit_message_text(message_id, opening)
        else:
            init = self.send_message(opening)
            if isinstance(init, dict):
                message_id = init.get("message_id")

        success, content, title_hint, labels, sources, contradictions = \
            self._run_research_stage(question, message_id, mode)

        if not success:
            err = content[:4000]
            if message_id:
                self.edit_message_text(message_id, err)
            else:
                self.send_message(err)
            return

        if message_id:
            self.edit_message_text(message_id, "Claude HTML 생성 중…")

        sources_section = self._format_sources_section(sources)
        full_md_content = content + sources_section
        if contradictions:
            full_md_content += "\n\n## 라운드 간 모순\n" + "\n".join(f"- {c}" for c in contradictions)

        html_content = None
        claude_title = ""
        try:
            from shared.claude_html_converter import convert_md_to_html_via_claude
            html_content, claude_title = convert_md_to_html_via_claude(full_md_content)
        except Exception as e:
            logger.warning(f"Claude HTML failed: {e}")

        final_title = claude_title or title_hint

        self._upload_default_only(
            md_content=full_md_content,
            html_content=html_content,
            title=final_title,
            labels=labels,
            sources=sources,
            message_id=message_id,
        )
```

- [ ] **Step 9: Preserve `mode` on selection timeout**

In `_check_pending_timeouts` (currently lines ~542-561), pass `mode` through:

```python
        for message_id in expired_ids:
            pending = self.pending_uploads.pop(message_id)
            logger.info(f"Selection timeout, processing with default only (msg_id: {message_id}, mode: {pending.get('mode', 'deep')})")

            self._process_after_selection(
                question=pending["question"],
                blog_key="default_only",
                message_id=message_id,
                mode=pending.get("mode", "deep"),
            )
```

- [ ] **Step 10: Manual smoke test (test mode, both paths)**

Run: `python 001_code/telegram_gemini_bot.py --test`

From Telegram send:
1. `What is GIL?` (no prefix) — expect status "🔎 Deep research 시작…" then round-by-round updates, finally "Test mode - upload skipped".
2. `/quick What is GIL?` — expect status "⚡ Asking Gemini…" then "Test mode - upload skipped" within ~30s.
3. `/help` — confirm new lines appear (set in Task 9, but legacy command response still works here).
4. `/start` — unchanged.

If any path errors out, capture the stack trace from `logs/telegram_bot_<date>.log` before fixing.

- [ ] **Step 11: Commit**

```bash
git add 001_code/telegram_gemini_bot.py
git commit -m "Route plain messages through research orchestrator (deep default + /quick opt-out)"
```

---

### Task 9: Update `/help` and `/status` to reflect deep-by-default

**Files:**
- Modify: `001_code/telegram_gemini_bot.py:749-788` (`_handle_command`)

- [ ] **Step 1: Update `/help` text**

Replace the body of the `/help` branch with:
```python
        elif cmd == "/help":
            self.send_message(f"""<b>Usage</b>
- 기본 (Deep research): 그냥 메시지 입력 → 다라운드 Gemini + Claude 검증 (~1~5min)
- 빠른 답변 (Quick): <code>{self.quick_command} 질문</code> → 단발 Gemini (~30s, quota 절약)

Examples:
- 티스토리 API 종료 이후 자동 포스팅 현황    ← Deep 모드 (기본)
- {self.quick_command} What is list comprehension in Python?    ← Quick 모드""")
```

- [ ] **Step 2: Update `/status` text**

Replace the `/status` branch with:
```python
        elif cmd == "/status":
            upload_status = "Enabled" if self.upload_to_blog else "Test mode"
            blogs_list = "\n".join([f"  - {k}: {v['name']}" for k, v in self.blogs.items()])
            pending_count = len(self.pending_uploads)
            self.send_message(f"""<b>Bot Status</b>
- Default mode: Deep research (multi-round)
- Quick opt-out: {self.quick_command}
- Deep max rounds: {self.research_max_rounds}
- Blog upload: {upload_status}
- Blogs configured: {len(self.blogs)}
{blogs_list}
- Default blog: {self.default_blog_key}
- Selection timeout: {self.selection_timeout // 60} min
- Pending selections: {pending_count}
- Last update ID: {self.last_update_id}""")
```

- [ ] **Step 3: Manual sanity check**

Run: `python 001_code/telegram_gemini_bot.py --test` then send `/help` and `/status` from Telegram.
Expected: New text shows Deep as default and `/quick` as opt-out.

- [ ] **Step 4: Commit**

```bash
git add 001_code/telegram_gemini_bot.py
git commit -m "Update /help and /status: deep research is default, /quick is opt-out"
```

---

### Task 10: Document new env vars and update TELEGRAM_BOT.md

**Files:**
- Modify: `006_auto_bot/docs/TELEGRAM_BOT.md`

- [ ] **Step 1: Read current doc tail to find a sensible insertion point**

Run: `tail -40 006_auto_bot/docs/TELEGRAM_BOT.md`

- [ ] **Step 2: Append a "Research Modes" section**

Add at the end of the file:

```markdown
## Research Modes (Deep default, `/quick` opt-out)

봇은 **모든 평문 메시지를 다라운드 deep research로 처리**합니다. 결과가 블로그에 게시되므로 사실관계 검증이 항상 가치 있다는 판단입니다. 가벼운 질문이나 Gemini quota가 빠듯할 때는 `/quick <질문>`으로 기존 단발 모드를 사용할 수 있습니다.

### Deep 모드 (기본)

| 단계 | 도구 | 역할 |
|---|---|---|
| Round 1 | Gemini CLI | broad sweep (telegram-qa 스킬 프롬프트 그대로) |
| Eval | Claude CLI | 5차원(정의/현황/근거/반론/적용) 체크, JSON 반환 |
| Round 2~N | Gemini CLI | 평가가 지목한 빈 차원만 좁힌 query로 재호출 |
| Synth | Claude CLI | 누적 라운드를 telegram-qa 톤의 마크다운으로 종합 + TITLE/LABELS/SOURCES |

**예상 시간:** 60~300초. Gemini quota 소진 시 누적 결과로 fallback 종합.

### Quick 모드 (`/quick <질문>`)

기존 단발 Gemini 흐름. ~30초. Quota 1회만 소비.

### 환경변수

- `RESEARCH_QUICK_COMMAND` (default: `/quick`) — 단발 모드 트리거 문자열
- `RESEARCH_MAX_ROUNDS` (default: `3`, 상한 4) — Deep 모드 라운드 최대 횟수

### 운영상 주의

- Gemini 호출 횟수가 단발 대비 평균 3배지만, 운영자가 **Gemini Code Assist (Google One AI Pro) tier**라 일일 한도는 충분히 여유 있음 (예상 사용량의 30배 이상). 분당 RPM 버스트 throttle은 가끔 발생할 수 있으나 오케스트레이터가 누적 결과로 자동 fallback 종합하므로 게시는 끊기지 않음.
- 다중 블로그 사용자는 두 모드 모두 동일한 블로그 선택 UI를 거침. 선택 후 모드별 흐름이 갈라짐.
- 운영 중 Quick으로 강제 전환하려면 `RESEARCH_QUICK_COMMAND=` (빈 문자열) 대신 봇 측에서 deep을 비활성화하는 별도 작업이 필요. 현재는 환경변수만으로 디폴트 뒤집기 불가 (의도적).
```

- [ ] **Step 3: Commit**

```bash
git add 006_auto_bot/docs/TELEGRAM_BOT.md
git commit -m "Document /deep research mode and new env vars"
```

---

### Task 11: Optional integration smoke test (env-gated)

**Files:**
- Modify: `003_test_code/test_research_orchestrator.py`

- [ ] **Step 1: Add gated live test**

Append:

```python
def test_live_smoke():
    """Live end-to-end against real gemini + claude. Skipped unless RESEARCH_LIVE=1."""
    if os.getenv("RESEARCH_LIVE") != "1":
        print("skip live smoke (set RESEARCH_LIVE=1 to run)")
        return
    from shared.research_orchestrator import run_research
    progress = []
    result = run_research(
        "Python의 GIL이란 무엇이며 3.13에서 어떻게 바뀌었나",
        max_rounds=2,
        progress_callback=lambda m: progress.append(m),
    )
    assert result.rounds_completed >= 1
    assert len(result.content) > 200
    assert result.title
    print(f"live smoke OK: rounds={result.rounds_completed}, title={result.title}")


if __name__ == "__main__":
    # ... existing calls ...
    test_live_smoke()
    print("OK")
```

- [ ] **Step 2: Run gated test (only if you want a real-call check)**

Run: `RESEARCH_LIVE=1 python 003_test_code/test_research_orchestrator.py`
Expected (when running): `live smoke OK: rounds=N, title=...`

- [ ] **Step 3: Commit**

```bash
git add 003_test_code/test_research_orchestrator.py
git commit -m "Add env-gated live integration smoke test"
```

---

## 5. Test Strategy

**Unit (offline, default):**
- All tests in `003_test_code/test_research_orchestrator.py` stub `subprocess.run` to avoid real CLI calls.
- Coverage: result dataclass, gemini wrapper success/failure, prompt builders, eval JSON parsing (codeblock and bare), synth happy path, full `run_research` early-stop and continue-then-pass scenarios.
- Run command: `python 003_test_code/test_research_orchestrator.py`

**Integration (live, gated):**
- `RESEARCH_LIVE=1 python 003_test_code/test_research_orchestrator.py` runs one real end-to-end query. Costs Gemini quota and Claude calls; do not run on CI.

**Manual Telegram scenarios (after Task 9):**
1. **Default deep path:** Send "티스토리 API 종료 이후 자동 포스팅 현황" without prefix. Expect: status message edits through "🔎 Deep research 시작 → Round 1 → 평가 → (continue/pass) → Synth → HTML → Upload"; final blog post contains TITLE/LABELS/SOURCES and any contradictions section. Total ≤5min.
2. **Quick opt-out:** Send `/quick What is GIL?`. Expect: "⚡ Asking Gemini…" → upload → result within ~30s. No round-by-round status edits.
3. **Multi-blog × deep:** With ≥2 blogs configured, send a plain question. Expect: blog selection UI appears with "Question received! (🔎 Deep research)" header; after click, deep research runs then dual upload.
4. **Multi-blog × quick:** With ≥2 blogs configured, send `/quick <question>`. Expect: selection UI labeled "(⚡ Quick)"; after click, single-shot Gemini then dual upload.
5. **Selection timeout preserves mode:** Plain question with ≥2 blogs, do not click. After `BLOG_SELECTION_TIMEOUT` (default 600s) wait, expect: deep research runs against default blog only.
6. **Quota exhaustion (deep):** Trigger by running multiple deep queries in a minute. Expect: partial result with rounds_completed≥1 and graceful fallback synth. Never full failure.
7. **Slash commands:** `/help`, `/status`, `/start` — confirm new lines appear (Deep default + `/quick` opt-out).
8. **Empty quick call:** Send `/quick` (no argument). Expect: usage hint message.

## 6. Rollback Strategy

This change makes deep research the default — rollback is more consequential than the original toggle plan. Three escalation levels:

**Level 1 — Per-message workaround (no code change):**
- Tell users to prefix with `/quick` for every message. Not a real rollback but instant.

**Level 2 — Re-bind default to quick (one-line .env hack):**
- Plan-as-written does NOT support env-only flip. If we want a runtime kill switch, add an extra check at the top of `process_message`: `if os.getenv("RESEARCH_FORCE_QUICK") == "1": mode = "quick"`. Not part of the initial implementation — add only if Level 1 proves insufficient.

**Level 3 — Full revert:**
```bash
git revert <task-8-commit-hash>..<task-10-commit-hash>
```
Restores the original deep-as-opt-in plan or the pre-orchestrator code (depending on how far back you revert).

**Notes:**
- The orchestrator module (`shared/research_orchestrator.py`) is referenced only inside `_run_research_stage` of the bot, so deleting the module after a revert breaks nothing else.
- After Level 3 revert, the `pending_uploads` dict's `mode` field becomes vestigial but harmless until the next bot restart.

## 7. Known Risks / Open Questions

1. **User-perceived regression on default UX.** Plain messages now take 1~5 min instead of ~30s. Some users may find the wait surprising. Mitigation: Task 8's first edit_message_text fires within seconds with "🔎 Deep research 시작…" so the bot signals it's working immediately. Still, document this prominently in `/help` (Task 9) and TELEGRAM_BOT.md (Task 10).
2. **Gemini quota — minor.** Sole operator runs `gemini` CLI on the **Gemini Code Assist (Google One AI Pro)** tier (verified via `gemini /about`: Auth = Google OAuth, Tier = "Gemini Code Assist in Google One AI Pro"). Daily ceiling is ~10× the free OAuth tier and well above the bot's expected 10~30 calls/day even with deep as default (~3 Gemini calls per question × ~10 questions/day ≈ ~3% of daily allowance). The throttle observed in the design session ("quota will reset after 1s") was a per-minute RPM burst limit, not a daily exhaustion — orchestrator's fallback synth already handles burst throttling gracefully so the user only sees a slightly degraded result, not a failure. Re-evaluate after one week of production use; revisit only if daily-limit errors actually appear. Exact ceilings vary with Google policy and are not asserted here.
3. **Claude CLI invocation contract.** This plan assumes `claude -p "<prompt>"` runs headless and returns stdout. If the installed Claude CLI uses a different flag (e.g. `--prompt`, `--print`), Tasks 4 and 6 must adjust the `subprocess.run(["claude", ...])` argv. Verify with `claude --help` before Task 4.
4. **Gemini CLI flag.** Existing code in `telegram_gemini_bot.py:151` calls `gemini` with the prompt as argv[1] (no `-p`). The research skill's `ask_gemini.sh` uses `gemini -p`. Task 2 standardizes on `gemini -p` for consistency with the skill — confirm both forms work, otherwise drop the `-p`.
5. **Concurrent calls block polling.** A second message arriving while a deep round is in flight will queue behind the synchronous subprocess. With deep-by-default this matters more than the toggle version because the typical message takes minutes. Acceptable for the single-user bot today, but document it. If multi-user is added later, route to a worker thread.
6. **Telegram message length.** A long synthesis can exceed 4096 chars in `edit_message_text`. The existing code already truncates to `[:4000]` for errors but the success path posts to Blogger and the Telegram message is just the URL — so no overflow expected. Re-check after Task 8 manual test.
7. **Round logging path.** Unlike `ask_gemini.sh`, this Python implementation does NOT write per-round logs to `/tmp/research-*`. If postmortem on a specific run is needed later, add a `logger.info` of each round body's first 500 chars. Out of scope for this plan.
8. **Skill file dependency.** `_load_skill_body` reads `~/.claude/skills/telegram-qa/SKILL.md` synchronously. If the file is missing, Round 1 raises `FileNotFoundError`. Since deep is now the default, *every* plain message hits this read. Mitigation: add a startup-time check that loads the skill once and caches it; surface clearer error if missing. (Out of scope here, but consider adding before merge.)
9. **Multi-blog selection UX with deep mode.** Selection UI now sits in front of a 1~5 min process. Users may forget they have a pending selection. The existing 10-min `BLOG_SELECTION_TIMEOUT` already covers this — verify in scenario test #5.
10. **Environment variable naming.** Plan uses `RESEARCH_QUICK_COMMAND` and `RESEARCH_MAX_ROUNDS`. Confirm these don't collide with anything in `.env` of other bots in the same repo before Task 8.

---

Plan complete and saved to `006_auto_bot/docs/superpowers/plans/2026-04-26-research-orchestrator.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
