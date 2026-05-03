# Sector Bot Mini-Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the existing `searcher` + `analyzer` chain in a sector-specific mini-orchestrator that applies a 5-dimension Claude verification gate, performs targeted Gemini gap-fill rounds, surfaces source contradictions, and clamps work when the CLI fallback is active. Apply the same gate to the comprehensive weekly report.

**Architecture:**
- New `sector_bot/dimensions.py` defines the 5 verification dimensions with regex-based quantitative checks + Claude qualitative judge.
- New `sector_bot/orchestrator.py` (`run_sector_research`) sequences `searcher` → 5-dim gate → 1 targeted gap-fill round → `analyzer`, with an 8-minute hard cap and CLI-fallback clamp.
- `weekly_sector_bot.process_sector` calls orchestrator instead of searcher/analyzer directly.
- Schedule moves to 12:00 start, 40-min interval, telegram summary 19:20, comprehensive 19:40.
- `comprehensive_report.generate_report` applies a comprehensive-variant gate with one re-synthesis attempt on failure.
- Two SKILL.md files get a "모순 명시" constraint appended (zero code change).

**Tech Stack:** Python 3.11+, existing `google-genai` SDK, existing Claude CLI (`claude -p`), existing Gemini CLI fallback, `pytest` for tests, `schedule` lib for scheduling.

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `001_code/sector_bot/dimensions.py` | **Create** | 5 dimension definitions, quantitative pass-checks, Claude judge call |
| `001_code/sector_bot/orchestrator.py` | **Create** | `run_sector_research()` + comprehensive gate runner |
| `001_code/sector_bot/gemini_cli.py` | Modify | Add `is_cli_mode_active(*instances)` helper |
| `001_code/sector_bot/config.py` | Modify | Change `scheduled_time` for all 11 sectors |
| `001_code/weekly_sector_bot.py` | Modify | `process_sector` calls orchestrator; scheduler uses new times; `--deep` flag |
| `001_code/sector_bot/comprehensive_report.py` | Modify | Apply gate after Claude call, 1 re-synthesis on fail |
| `~/.claude/skills/sector-analysis/SKILL.md` | Modify | Append constraint #10 모순 명시 |
| `~/.claude/skills/sector-comprehensive/SKILL.md` | Modify | Append same constraint |
| `003_test_code/test_sector_dimensions.py` | **Create** | Tests for `dimensions.py` |
| `003_test_code/test_sector_orchestrator.py` | **Create** | Tests for `orchestrator.py` (mocking external calls) |
| `003_test_code/test_gemini_cli_helpers.py` | **Create** | Tests for `is_cli_mode_active` |
| `docs/SECTOR_BOT.md` | Modify | Document orchestrator + new schedule + gate behaviour |

---

## Phase 1 — Skill File Constraints (no code)

### Task 1: Append 모순 명시 constraint to sector-analysis SKILL

**Files:**
- Modify: `~/.claude/skills/sector-analysis/SKILL.md` (append after constraint #9)

- [ ] **Step 1: Read current constraints section to confirm last item is #9**

Run: `grep -n "^[0-9]\." ~/.claude/skills/sector-analysis/SKILL.md | tail -5`
Expected: Last numbered item is `9. **AI 언급 금지**: ...`

- [ ] **Step 2: Append constraint #10**

Append exactly this block to the end of `~/.claude/skills/sector-analysis/SKILL.md`:

```markdown
10. **모순 명시**: 두 자료가 충돌하는 수치·방향성을 보고하면 한쪽만 채택하지 말고 둘 다 인용한 뒤, 차이의 원인(측정 시점·방법론·범위)을 1줄로 명시한다. 예: "Bloomberg는 +5.2%, Reuters는 +3.8% — 환율 적용 시점 차이로 추정". 모순이 발견된 항목은 본문 말미의 `## 📌 자료 간 차이` 섹션에 별도로 모은다.
```

- [ ] **Step 3: Verify**

Run: `grep -A1 "^10\." ~/.claude/skills/sector-analysis/SKILL.md`
Expected: Output shows the new constraint.

- [ ] **Step 4: Commit**

```bash
git add ~/.claude/skills/sector-analysis/SKILL.md
git commit -m "Update sector-analysis skill: add 모순 명시 constraint"
```

---

### Task 2: Append same constraint to sector-comprehensive SKILL

**Files:**
- Modify: `~/.claude/skills/sector-comprehensive/SKILL.md` (append to constraints section)

- [ ] **Step 1: Locate current constraints section**

Run: `grep -n "^## 제약사항\|^[0-9]\." ~/.claude/skills/sector-comprehensive/SKILL.md | tail -10`
Expected: Last item is `9. **AI 언급 금지**: ...`

- [ ] **Step 2: Append constraint #10 (variant for comprehensive)**

Append to end of `~/.claude/skills/sector-comprehensive/SKILL.md`:

```markdown
10. **모순 명시**: 11개 섹터 보고서 사이에 시장 방향성·종목 평가가 충돌하면 한쪽만 채택하지 말고 둘 다 인용한 뒤 어떤 섹터 관점에서 그렇게 보는지 명시한다. 보고서 말미의 `## 📌 섹터 간 시각 차이` 섹션에 모순 항목을 모은다.
```

- [ ] **Step 3: Verify**

Run: `grep -A1 "^10\." ~/.claude/skills/sector-comprehensive/SKILL.md`
Expected: New constraint visible.

- [ ] **Step 4: Commit**

```bash
git add ~/.claude/skills/sector-comprehensive/SKILL.md
git commit -m "Update sector-comprehensive skill: add 섹터 간 시각 차이 constraint"
```

---

## Phase 2 — Dimensions Module (TDD)

### Task 3: Create dimensions data structure

**Files:**
- Create: `001_code/sector_bot/dimensions.py`
- Test: `003_test_code/test_sector_dimensions.py`

- [ ] **Step 1: Write failing test for dimension data**

Create `003_test_code/test_sector_dimensions.py`:

```python
#!/usr/bin/env python3
"""Tests for sector_bot.dimensions module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from sector_bot.dimensions import SECTOR_DIMENSIONS, Dimension


def test_five_dimensions_defined():
    names = [d.name for d in SECTOR_DIMENSIONS]
    assert names == ["정의", "현황", "근거", "반론", "적용"]


def test_each_dimension_has_required_fields():
    for d in SECTOR_DIMENSIONS:
        assert isinstance(d, Dimension)
        assert d.name
        assert d.check_description
        assert callable(d.quantitative_check)
        # 적용 has no follow-up template (handled in analyzer); others must
        if d.name != "적용":
            assert d.followup_query_template
            assert "{sector}" in d.followup_query_template


def test_tier1_domains_constant():
    from sector_bot.dimensions import TIER1_DOMAINS
    assert "bloomberg.com" in TIER1_DOMAINS
    assert "reuters.com" in TIER1_DOMAINS
    assert "ft.com" in TIER1_DOMAINS
    assert "wsj.com" in TIER1_DOMAINS
    assert "sec.gov" in TIER1_DOMAINS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_dimensions.py -v`
Expected: FAIL with `ModuleNotFoundError: sector_bot.dimensions` or `ImportError`.

- [ ] **Step 3: Create `001_code/sector_bot/dimensions.py`**

```python
"""
Sector Verification Dimensions
------------------------------
5-dimension checklist applied to each sector's research output.
Each dimension provides:
  - quantitative_check: regex-based pass/fail on raw search content
  - followup_query_template: Gemini query when dimension fails
  - check_description: text passed to Claude judge for 2nd-pass validation
"""

import re
from dataclasses import dataclass
from typing import Callable, List, Optional


TIER1_DOMAINS = (
    "bloomberg.com",
    "reuters.com",
    "ft.com",
    "wsj.com",
    "sec.gov",
    "cnbc.com",
    "marketwatch.com",
)


@dataclass
class Dimension:
    name: str
    check_description: str
    quantitative_check: Callable[[str, list], bool]
    followup_query_template: Optional[str]


# --- quantitative checks ---

_DATE_PATTERN = re.compile(
    r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|"
    r"\d{1,2}\s?(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s?20\d{2}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s\d{1,2},?\s20\d{2})\b",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z])([+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?%|"
    r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?(?:\s?(?:billion|million|bn|mn|B|M))?|"
    r"\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?(?:bps|basis points))",
    re.IGNORECASE,
)


def _check_definition(content: str, sources: list) -> bool:
    # require ≥2 named driving variables (proxy: ≥2 occurrences of "driver"/"변수"/"factor"
    # OR a bullet-style list of 2+ items in the content head)
    head = content[:1500].lower()
    keyword_hits = sum(head.count(k) for k in ("driver", "factor", "변수", "동인", "key trend"))
    bullet_lines = sum(1 for line in content.splitlines()[:30] if re.match(r"^\s*[-*•]\s+\S", line))
    return keyword_hits >= 2 or bullet_lines >= 2


def _check_status(content: str, sources: list) -> bool:
    # ≥3 (number, date) pairs anywhere in the content
    numbers = _NUMBER_PATTERN.findall(content)
    dates = _DATE_PATTERN.findall(content)
    return len(numbers) >= 3 and len(dates) >= 3


def _check_evidence(content: str, sources: list) -> bool:
    # ≥2 source URLs match a Tier-1 domain
    if not sources:
        return False
    tier1_count = 0
    for src in sources:
        url = src.get("url", "") if isinstance(src, dict) else str(src)
        if any(dom in url.lower() for dom in TIER1_DOMAINS):
            tier1_count += 1
    return tier1_count >= 2


def _check_counterargument(content: str, sources: list) -> bool:
    # both bullish AND bearish vocabulary present
    text = content.lower()
    bull_terms = ("bull", "upside", "outperform", "buy rating", "강세", "상승")
    bear_terms = ("bear", "downside", "underperform", "sell rating", "약세", "하락", "리스크", "risk")
    has_bull = any(t in text for t in bull_terms)
    has_bear = any(t in text for t in bear_terms)
    return has_bull and has_bear


def _check_application(content: str, sources: list) -> bool:
    # action verb + at least one ticker-like token; this dimension is mostly
    # enforced in the analyzer prompt so this is intentionally permissive.
    action_terms = ("매수", "매도", "관망", "비중", "보유", "buy", "sell", "hold", "watch")
    has_action = any(t in content.lower() for t in action_terms)
    has_ticker = bool(re.search(r"\b[A-Z]{2,5}\b", content))
    return has_action and has_ticker


SECTOR_DIMENSIONS: List[Dimension] = [
    Dimension(
        name="정의",
        check_description="이번 주 이 섹터의 주요 동인(driver) 2개 이상이 명시됐는가?",
        quantitative_check=_check_definition,
        followup_query_template=(
            "Use web search. List the top 2-3 driving variables for the {sector} sector "
            "this week. One sentence of context per variable. Cite a source URL for each."
        ),
    ),
    Dimension(
        name="현황",
        check_description="구체 수치 + 날짜가 표시된 사실이 3개 이상인가?",
        quantitative_check=_check_status,
        followup_query_template=(
            "Use web search. Find 3 or more specific data points (price, percentage move, "
            "volume, earnings figure) for the {sector} sector from the past 7 days. "
            "Each data point MUST include the figure, the exact date (YYYY-MM-DD), and a source URL."
        ),
    ),
    Dimension(
        name="근거",
        check_description="Tier 1 (Bloomberg/Reuters/FT/WSJ/SEC) 출처가 2개 이상인가?",
        quantitative_check=_check_evidence,
        followup_query_template=(
            "Use web search. Find primary-source coverage from Bloomberg, Reuters, the Financial Times, "
            "the Wall Street Journal, or SEC filings for the key {sector} stories this week. "
            "Provide direct URLs and a one-sentence summary per source."
        ),
    ),
    Dimension(
        name="반론",
        check_description="강세 의견과 약세 의견 양쪽이 모두 인용됐는가?",
        quantitative_check=_check_counterargument,
        followup_query_template=(
            "Use web search. What are the main bear-case arguments and bull-case arguments "
            "for the {sector} sector this week? Provide at least one expert quote for each side, "
            "each with the analyst/firm name and a source URL."
        ),
    ),
    Dimension(
        name="적용",
        check_description="한국 투자자가 즉시 행동 가능한 액션(매수/매도/관망 + 종목 또는 ETF)이 있는가?",
        quantitative_check=_check_application,
        followup_query_template=None,
    ),
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_dimensions.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add 001_code/sector_bot/dimensions.py 003_test_code/test_sector_dimensions.py
git commit -m "Add sector_bot.dimensions: 5-dimension verification data + quantitative checks"
```

---

### Task 4: Add quantitative_check unit tests for each dimension

**Files:**
- Test: `003_test_code/test_sector_dimensions.py` (extend)

- [ ] **Step 1: Append tests for each check function**

Append to `003_test_code/test_sector_dimensions.py`:

```python
from sector_bot.dimensions import (
    _check_definition, _check_status, _check_evidence,
    _check_counterargument, _check_application,
)


def test_check_definition_passes_with_bullet_list():
    content = "- AI capex surge\n- Memory cycle bottom\n- Korea export rebound\n"
    assert _check_definition(content, []) is True


def test_check_definition_fails_with_plain_paragraph():
    content = "The market is doing things this week with no specific structure."
    assert _check_definition(content, []) is False


def test_check_status_passes_with_three_number_date_pairs():
    content = (
        "S&P 500 rose 1.2% on 2026-04-28. NVIDIA gained $5.20 on April 29, 2026. "
        "Korea KOSPI fell 0.8% on 2026-04-30. Treasury yields up 12 bps."
    )
    assert _check_status(content, []) is True


def test_check_status_fails_with_only_numbers():
    content = "Stocks moved 1.2%, then 0.8%, then 5.5%, with no dates given."
    assert _check_status(content, []) is False


def test_check_evidence_passes_with_two_tier1():
    sources = [
        {"url": "https://www.bloomberg.com/news/x"},
        {"url": "https://www.reuters.com/markets/y"},
        {"url": "https://example.com/z"},
    ]
    assert _check_evidence("body", sources) is True


def test_check_evidence_fails_with_only_one_tier1():
    sources = [{"url": "https://www.bloomberg.com/news/x"}, {"url": "https://blog.example.com"}]
    assert _check_evidence("body", sources) is False


def test_check_counterargument_passes_with_both_sides():
    content = "Analyst bullish on AI semis, citing upside; bears warn of downside risk in memory."
    assert _check_counterargument(content, []) is True


def test_check_counterargument_fails_with_one_side():
    content = "Everyone is bullish, with strong buy ratings across the board."
    assert _check_counterargument(content, []) is False


def test_check_application_passes_with_action_and_ticker():
    content = "매수 추천: NVDA, TSM, AMD on the dip."
    assert _check_application(content, []) is True


def test_check_application_fails_with_no_action():
    content = "Many companies exist in this sector including NVDA and AMD."
    assert _check_application(content, []) is False
```

- [ ] **Step 2: Run all dimension tests**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_dimensions.py -v`
Expected: 13 tests pass.

- [ ] **Step 3: Commit**

```bash
git add 003_test_code/test_sector_dimensions.py
git commit -m "Add unit tests for all 5 dimension quantitative checks"
```

---

### Task 5: Add Claude judge function (2nd-pass qualitative check)

**Files:**
- Modify: `001_code/sector_bot/dimensions.py`
- Test: `003_test_code/test_sector_dimensions.py`

- [ ] **Step 1: Write failing test for `claude_judge_dimensions`**

Append to `003_test_code/test_sector_dimensions.py`:

```python
def test_claude_judge_dimensions_signature():
    from sector_bot.dimensions import claude_judge_dimensions
    import inspect
    sig = inspect.signature(claude_judge_dimensions)
    params = list(sig.parameters.keys())
    assert params[:3] == ["sector_name", "content", "sources"]
    assert "claude_caller" in params  # injectable for tests


def test_claude_judge_dimensions_uses_injected_caller(monkeypatch):
    from sector_bot.dimensions import claude_judge_dimensions

    captured = {}
    def fake_caller(prompt: str) -> str:
        captured["prompt"] = prompt
        return '{"정의": true, "현황": false, "근거": true, "반론": false, "적용": true}'

    result = claude_judge_dimensions(
        sector_name="반도체",
        content="some sector content",
        sources=[{"url": "https://www.bloomberg.com/x"}],
        claude_caller=fake_caller,
    )
    assert result == {"정의": True, "현황": False, "근거": True, "반론": False, "적용": True}
    assert "반도체" in captured["prompt"]
    assert "정의" in captured["prompt"]


def test_claude_judge_dimensions_falls_back_on_invalid_json():
    from sector_bot.dimensions import claude_judge_dimensions

    def bad_caller(prompt: str) -> str:
        return "not json at all"

    result = claude_judge_dimensions(
        sector_name="반도체",
        content="x",
        sources=[],
        claude_caller=bad_caller,
    )
    # all-pass fallback so we don't trigger spurious gap-fill on Claude error
    assert result == {"정의": True, "현황": True, "근거": True, "반론": True, "적용": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_dimensions.py -k claude_judge -v`
Expected: 3 tests fail with `ImportError`.

- [ ] **Step 3: Append `claude_judge_dimensions` to `dimensions.py`**

```python
import json
import logging

logger = logging.getLogger(__name__)


def _build_judge_prompt(sector_name: str, content: str, sources: list) -> str:
    sources_str = "\n".join(
        f"- {s.get('url', s) if isinstance(s, dict) else s}" for s in sources[:10]
    )
    dim_lines = "\n".join(f'- "{d.name}": {d.check_description}' for d in SECTOR_DIMENSIONS)
    return f"""You are evaluating whether a sector research output meets a 5-dimension checklist.

Sector: {sector_name}

Dimensions to check:
{dim_lines}

Research content (truncated to 6000 chars):
{content[:6000]}

Sources:
{sources_str}

For each dimension, decide if the content + sources together pass the dimension's criterion.
Be strict: missing dates, vague generalities, single-sided opinions all fail.

Respond with ONLY a JSON object on a single line, no prose, no code fences:
{{"정의": true|false, "현황": true|false, "근거": true|false, "반론": true|false, "적용": true|false}}
"""


def claude_judge_dimensions(
    sector_name: str,
    content: str,
    sources: list,
    claude_caller,
) -> dict:
    """
    Call Claude (via injected callable) to judge each dimension.
    On any error or invalid JSON, returns all-True (fail-open) so we don't
    trigger spurious gap-fill rounds on Claude infrastructure problems.
    """
    prompt = _build_judge_prompt(sector_name, content, sources)
    try:
        raw = claude_caller(prompt)
        # extract first {...} block in case Claude wraps it
        match = re.search(r"\{[^{}]*\}", raw)
        if not match:
            raise ValueError("no JSON object in Claude response")
        parsed = json.loads(match.group(0))
        return {d.name: bool(parsed.get(d.name, True)) for d in SECTOR_DIMENSIONS}
    except Exception as e:
        logger.warning(f"Claude judge failed for {sector_name}: {e}; falling back to all-pass")
        return {d.name: True for d in SECTOR_DIMENSIONS}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_dimensions.py -v`
Expected: 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add 001_code/sector_bot/dimensions.py 003_test_code/test_sector_dimensions.py
git commit -m "Add claude_judge_dimensions: 2nd-pass qualitative dimension check"
```

---

## Phase 3 — Gemini CLI Helper

### Task 6: Add `is_cli_mode_active` helper to `gemini_cli.py`

**Files:**
- Modify: `001_code/sector_bot/gemini_cli.py`
- Test: `003_test_code/test_gemini_cli_helpers.py`

- [ ] **Step 1: Write failing test**

Create `003_test_code/test_gemini_cli_helpers.py`:

```python
#!/usr/bin/env python3
"""Tests for sector_bot.gemini_cli helper functions."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '001_code'))

from sector_bot.gemini_cli import is_cli_mode_active


class _FakeFlagHolder:
    def __init__(self, flag: bool):
        self._use_cli_fallback = flag


def test_is_cli_mode_active_true_when_any_instance_in_fallback():
    a = _FakeFlagHolder(False)
    b = _FakeFlagHolder(True)
    assert is_cli_mode_active(a, b) is True


def test_is_cli_mode_active_false_when_all_normal():
    a = _FakeFlagHolder(False)
    b = _FakeFlagHolder(False)
    assert is_cli_mode_active(a, b) is False


def test_is_cli_mode_active_handles_missing_attribute():
    class NoAttr:
        pass
    assert is_cli_mode_active(NoAttr()) is False


def test_is_cli_mode_active_empty_args():
    assert is_cli_mode_active() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_gemini_cli_helpers.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Append `is_cli_mode_active` to `001_code/sector_bot/gemini_cli.py`**

Append at end of file:

```python
def is_cli_mode_active(*instances) -> bool:
    """
    Returns True if any of the given searcher/analyzer instances has been
    flipped into Gemini CLI fallback mode. Used by the orchestrator to
    clamp max_rounds=1 when API quota is exhausted.
    """
    for inst in instances:
        if getattr(inst, "_use_cli_fallback", False):
            return True
    return False
```

- [ ] **Step 4: Run tests**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_gemini_cli_helpers.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add 001_code/sector_bot/gemini_cli.py 003_test_code/test_gemini_cli_helpers.py
git commit -m "Add is_cli_mode_active helper for orchestrator fallback detection"
```

---

## Phase 4 — Orchestrator Module (TDD)

### Task 7: Create orchestrator module skeleton + result dataclass

**Files:**
- Create: `001_code/sector_bot/orchestrator.py`
- Test: `003_test_code/test_sector_orchestrator.py`

- [ ] **Step 1: Write failing test for `OrchestrationResult`**

Create `003_test_code/test_sector_orchestrator.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_orchestrator.py -v`
Expected: FAIL with `ImportError: cannot import name 'OrchestrationResult'`.

- [ ] **Step 3: Create `001_code/sector_bot/orchestrator.py`**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_orchestrator.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add 001_code/sector_bot/orchestrator.py 003_test_code/test_sector_orchestrator.py
git commit -m "Add sector_bot.orchestrator skeleton with OrchestrationResult dataclass"
```

---

### Task 8: Implement Round 1 (search) + dimension evaluation step

**Files:**
- Modify: `001_code/sector_bot/orchestrator.py`
- Test: `003_test_code/test_sector_orchestrator.py`

- [ ] **Step 1: Write failing test for Round 1 only (max_rounds=1, all dimensions pass)**

Append to `003_test_code/test_sector_orchestrator.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_orchestrator.py -v`
Expected: 2 new tests FAIL with `NotImplementedError`.

- [ ] **Step 3: Replace `run_sector_research` body in `001_code/sector_bot/orchestrator.py`**

Replace the `raise NotImplementedError(...)` line with:

```python
    started_at = time.time()
    deadline = started_at + SECTOR_HARD_CAP_SECONDS
    claude_caller = claude_caller or _default_claude_caller

    # CLI fallback clamp
    clamped = is_cli_mode_active(searcher, analyzer)
    effective_max_rounds = 1 if clamped else max(1, max_rounds)
    if clamped:
        logger.warning(
            f"[{sector.name}] CLI fallback active → max_rounds clamped to 1"
        )

    # ---- Round 1: initial search ----
    logger.info(f"[{sector.name}] Orchestrator Round 1: search")
    accumulated_content = ""
    accumulated_sources: List[dict] = []

    round1 = searcher.search_sector(sector)
    if not round1.get("success"):
        return OrchestrationResult(
            success=False,
            analysis="",
            sources=[],
            rounds_completed=0,
            dimensions_passed={d.name: False for d in SECTOR_DIMENSIONS},
            elapsed_seconds=time.time() - started_at,
            clamped_to_cli=clamped,
            error=f"Round 1 search failed: {round1.get('error')}",
        )

    accumulated_content += round1.get("content", "")
    accumulated_sources.extend(round1.get("sources", []))
    rounds_completed = 1

    # ---- Dimension gate ----
    quant_pass = {
        d.name: d.quantitative_check(accumulated_content, accumulated_sources)
        for d in SECTOR_DIMENSIONS
    }
    quant_failed = [name for name, ok in quant_pass.items() if not ok]
    logger.info(f"[{sector.name}] Quant gate: pass={list(quant_pass.values()).count(True)}/5, fail={quant_failed}")

    if quant_failed:
        # Always run Claude 2nd-pass (Q4 = a) on dimensions that quant flagged
        judge_pass = claude_judge_dimensions(
            sector_name=sector.name,
            content=accumulated_content,
            sources=accumulated_sources,
            claude_caller=claude_caller,
        )
        # combine: a dimension passes if EITHER check says so (Claude can rescue
        # quant false-negatives like content with non-standard date formats)
        dimensions_passed = {
            name: quant_pass[name] or judge_pass.get(name, True)
            for name in quant_pass
        }
    else:
        dimensions_passed = quant_pass

    failing_dims = [d for d in SECTOR_DIMENSIONS if not dimensions_passed.get(d.name, True)]
    logger.info(f"[{sector.name}] Final gate: failing={[d.name for d in failing_dims]}")

    # ---- Round 2+: gap-fill (if budget allows) ----
    while (
        failing_dims
        and rounds_completed < effective_max_rounds
        and time.time() < deadline
    ):
        # pick the highest-priority failing dim that has a follow-up template
        target = next((d for d in failing_dims if d.followup_query_template), None)
        if target is None:
            break

        followup_query = target.followup_query_template.format(sector=sector.name)
        logger.info(f"[{sector.name}] Round {rounds_completed + 1}: gap-fill on '{target.name}'")

        gap_result = _gap_fill_round(searcher, sector, followup_query, deadline)
        rounds_completed += 1

        if gap_result.get("success"):
            accumulated_content += "\n\n--- gap-fill: " + target.name + " ---\n"
            accumulated_content += gap_result.get("content", "")
            accumulated_sources.extend(gap_result.get("sources", []))
            # re-evaluate just this dimension
            new_pass = target.quantitative_check(accumulated_content, accumulated_sources)
            dimensions_passed[target.name] = new_pass

        failing_dims = [d for d in SECTOR_DIMENSIONS if not dimensions_passed.get(d.name, True)]

    # ---- Final analyze ----
    if time.time() >= deadline:
        logger.warning(f"[{sector.name}] Hard cap reached before analyze; proceeding anyway")

    enriched_search = {
        "success": True,
        "content": accumulated_content,
        "sources": accumulated_sources,
    }
    analysis_result = analyzer.analyze_sector(sector, enriched_search)

    if not analysis_result.get("success"):
        return OrchestrationResult(
            success=False,
            analysis="",
            sources=accumulated_sources,
            rounds_completed=rounds_completed,
            dimensions_passed=dimensions_passed,
            elapsed_seconds=time.time() - started_at,
            clamped_to_cli=clamped,
            error=f"Analyze failed: {analysis_result.get('error')}",
        )

    contradictions = _extract_contradictions(analysis_result.get("analysis", ""))

    return OrchestrationResult(
        success=True,
        analysis=analysis_result["analysis"],
        sources=accumulated_sources,
        rounds_completed=rounds_completed,
        dimensions_passed=dimensions_passed,
        elapsed_seconds=time.time() - started_at,
        clamped_to_cli=clamped,
        contradictions=contradictions,
    )


def _gap_fill_round(searcher, sector: Sector, followup_query: str, deadline: float) -> dict:
    """
    Issue a follow-up search by temporarily overriding the sector's search_keywords.
    Reuses searcher.search_sector so all retry/CLI-fallback logic stays in one place.
    """
    if time.time() >= deadline:
        return {"success": False, "error": "deadline reached"}

    original_keywords = list(sector.search_keywords)
    # Inject followup query as the primary keyword
    sector.search_keywords = [followup_query] + original_keywords[:3]
    try:
        return searcher.search_sector(sector)
    finally:
        sector.search_keywords = original_keywords


_CONTRADICTION_HEADER_RE = re.compile(r"##\s+📌\s+(?:자료|섹터)\s*간\s*(?:차이|시각\s*차이)", re.IGNORECASE)


def _extract_contradictions(analysis_text: str) -> List[str]:
    """Pull bullet items out of the '📌 자료 간 차이' or '📌 섹터 간 시각 차이' section if present."""
    match = _CONTRADICTION_HEADER_RE.search(analysis_text)
    if not match:
        return []
    tail = analysis_text[match.end():]
    items: List[str] = []
    for line in tail.splitlines():
        if line.startswith("## "):
            break
        stripped = line.strip()
        if stripped.startswith(("-", "*", "•")):
            items.append(stripped.lstrip("-*•").strip())
    return items
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_orchestrator.py -v`
Expected: 5 tests pass (3 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add 001_code/sector_bot/orchestrator.py 003_test_code/test_sector_orchestrator.py
git commit -m "Implement run_sector_research: 5-dim gate + CLI fallback clamp"
```

---

### Task 9: Test gap-fill flow when a dimension fails and gets rescued

**Files:**
- Test: `003_test_code/test_sector_orchestrator.py`

- [ ] **Step 1: Append gap-fill flow test**

Append to `003_test_code/test_sector_orchestrator.py`:

```python
def test_gap_fill_runs_when_dimension_fails_and_budget_allows():
    sector = _make_sector()

    failing_first = {
        "success": True,
        "content": "vague intro text without numbers or dates",
        "sources": [],  # fails 근거 dimension
    }
    rich_second = {
        "success": True,
        "content": (
            "S&P 500 rose 1.2% on 2026-04-28. NVIDIA gained $5.20 on April 29, 2026. "
            "Korea KOSPI fell 0.8% on 2026-04-30."
        ),
        "sources": [
            {"url": "https://www.bloomberg.com/x"},
            {"url": "https://www.reuters.com/y"},
        ],
    }

    searcher = MagicMock()
    searcher.search_sector.side_effect = [failing_first, rich_second]
    searcher._use_cli_fallback = False

    analyzer = MagicMock()
    analyzer.analyze_sector.return_value = {
        "success": True,
        "analysis": "x" * 600,
        "sources": rich_second["sources"],
    }
    analyzer._use_cli_fallback = False

    # Claude judge: fails everything → forces gap-fill on first failing dim with template
    fake_claude = MagicMock(return_value='{"정의": false, "현황": false, "근거": false, "반론": false, "적용": false}')

    result = run_sector_research(
        sector=sector,
        searcher=searcher,
        analyzer=analyzer,
        max_rounds=2,
        claude_caller=fake_claude,
    )

    assert searcher.search_sector.call_count == 2  # round1 + 1 gap-fill
    assert result.rounds_completed == 2
    assert result.success is True


def test_extracts_contradictions_from_analysis():
    from sector_bot.orchestrator import _extract_contradictions

    text = """## Analysis Body

Some content.

## 📌 자료 간 차이

- Bloomberg는 +5.2%, Reuters는 +3.8% — 환율 시점 차이
- IDC는 점유율 30%, Gartner는 28% — 카테고리 정의 차이

## 면책

disclaimer
"""
    items = _extract_contradictions(text)
    assert len(items) == 2
    assert "Bloomberg" in items[0]
    assert "IDC" in items[1]


def test_extracts_no_contradictions_when_section_absent():
    from sector_bot.orchestrator import _extract_contradictions
    assert _extract_contradictions("## 일반 분석\n\n본문\n") == []
```

- [ ] **Step 2: Run tests**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_orchestrator.py -v`
Expected: 8 tests pass.

- [ ] **Step 3: Commit**

```bash
git add 003_test_code/test_sector_orchestrator.py
git commit -m "Add gap-fill and contradiction extraction tests for orchestrator"
```

---

## Phase 5 — Wire Orchestrator into weekly_sector_bot

### Task 10: Update sector config schedule times to 12:00 + 40-min interval

**Files:**
- Modify: `001_code/sector_bot/config.py:32,53,75,96,117,138,159,180,201,222,245`

- [ ] **Step 1: Update each `scheduled_time` value**

Edit `001_code/sector_bot/config.py`. Replace these exact strings (one at a time to keep them unique):

| Sector ID | Old time | New time |
|---|---|---|
| 1 | `"13:00"` | `"12:00"` |
| 2 | `"13:30"` | `"12:40"` |
| 3 | `"14:00"` | `"13:20"` |
| 4 | `"14:30"` | `"14:00"` |
| 5 | `"15:00"` | `"14:40"` |
| 6 | `"15:30"` | `"15:20"` |
| 7 | `"16:00"` | `"16:00"` (unchanged — but reorder check: actually new = 16:00, same value) |
| 8 | `"16:30"` | `"16:40"` |
| 9 | `"17:00"` | `"17:20"` |
| 10 | `"17:30"` | `"18:00"` |
| 11 | `"18:00"` | `"18:40"` |

For sector 7 the old and new value are both "16:00" — no edit needed for that line.

**Note:** because `scheduled_time` strings repeat across the file, edit each within the matching `Sector(id=N, ...)` block. Use the Edit tool with enough surrounding context (e.g. include `id=N,` and `name="..."` lines) to make `old_string` unique.

- [ ] **Step 2: Verify all times**

Run: `grep -n "scheduled_time=" 001_code/sector_bot/config.py`
Expected: Times match the "New time" column above.

- [ ] **Step 3: Commit**

```bash
git add 001_code/sector_bot/config.py
git commit -m "Update sector schedule: start 12:00, 40-min interval"
```

---

### Task 11: Update weekly_sector_bot scheduler for 19:20 telegram + 19:40 comprehensive

**Files:**
- Modify: `001_code/weekly_sector_bot.py:250,253-254`

- [ ] **Step 1: Update telegram summary time from 18:30 to 19:20**

Edit `001_code/weekly_sector_bot.py`. Replace:

```python
        # 일요일 18:30에 전체 완료 알림
        schedule.every().sunday.at("18:30").do(self._send_weekly_summary)
```

with:

```python
        # 일요일 19:20에 전체 완료 알림 (마지막 섹터 18:40 + 40분 여유)
        schedule.every().sunday.at("19:20").do(self._send_weekly_summary)
```

- [ ] **Step 2: Update comprehensive report time from 19:00 to 19:40**

Edit. Replace:

```python
        # 일요일 19:00에 종합 투자 평가 보고서 생성
        schedule.every().sunday.at("19:00").do(self._scheduled_comprehensive_report)
        logger.info("Scheduled: Comprehensive Report at Sunday 19:00")
```

with:

```python
        # 일요일 19:40에 종합 투자 평가 보고서 생성 (텔레그램 알림 후 20분 여유)
        schedule.every().sunday.at("19:40").do(self._scheduled_comprehensive_report)
        logger.info("Scheduled: Comprehensive Report at Sunday 19:40")
```

- [ ] **Step 3: Verify**

Run: `grep -n "schedule.every().sunday.at" 001_code/weekly_sector_bot.py`
Expected: Three lines — sector loop (uses `sector.scheduled_time`), `19:20`, `19:40`.

- [ ] **Step 4: Commit**

```bash
git add 001_code/weekly_sector_bot.py
git commit -m "Reschedule telegram summary to 19:20 and comprehensive report to 19:40"
```

---

### Task 12: Replace `process_sector` search/analyze chain with orchestrator call

**Files:**
- Modify: `001_code/weekly_sector_bot.py:105-204`

- [ ] **Step 1: Add import at top of file**

After existing `sector_bot` imports near top of `001_code/weekly_sector_bot.py`, add:

```python
from sector_bot.orchestrator import run_sector_research, OrchestrationResult
```

- [ ] **Step 2: Add `--deep` flag handling — store on `WeeklySectorBot` constructor**

Locate `class WeeklySectorBot` `__init__`. Add a parameter `deep_mode: bool = False` and store as `self.deep_mode = deep_mode`. The `__init__` signature is around the start of the class — check with:

Run: `grep -n "def __init__" 001_code/weekly_sector_bot.py`

Then update the constructor body to include `self.deep_mode = deep_mode`.

- [ ] **Step 3: Replace step 1 + step 2 in `process_sector`**

In `process_sector` (around line 126-143), replace these lines:

```python
        try:
            # 1. 검색
            logger.info(f"[{sector.name}] Step 1: Searching...")
            search_result = self.searcher.search_sector(sector)

            if not search_result['success']:
                raise Exception(f"Search failed: {search_result.get('error')}")

            logger.info(f"[{sector.name}] Search: {len(search_result['content'])} chars, {len(search_result['sources'])} sources")

            # 2. 분석
            logger.info(f"[{sector.name}] Step 2: Analyzing...")
            analysis_result = self.analyzer.analyze_sector(sector, search_result)

            if not analysis_result['success']:
                raise Exception(f"Analysis failed: {analysis_result.get('error')}")

            logger.info(f"[{sector.name}] Analysis: {len(analysis_result['analysis'])} chars")
```

with:

```python
        try:
            # 1+2. 오케스트레이터: 검색 → 5차원 게이트 → 갭필 → 분석
            max_rounds = 3 if self.deep_mode else 2
            logger.info(f"[{sector.name}] Orchestrating (max_rounds={max_rounds})...")

            orch: OrchestrationResult = run_sector_research(
                sector=sector,
                searcher=self.searcher,
                analyzer=self.analyzer,
                max_rounds=max_rounds,
            )

            if not orch.success:
                raise Exception(f"Orchestration failed: {orch.error}")

            logger.info(
                f"[{sector.name}] Orchestration done: rounds={orch.rounds_completed}, "
                f"clamped={orch.clamped_to_cli}, elapsed={orch.elapsed_seconds:.1f}s, "
                f"dims={sum(orch.dimensions_passed.values())}/5, "
                f"contradictions={len(orch.contradictions)}"
            )

            # 하위 호환: 기존 코드는 analysis_result['analysis']를 기대
            analysis_result = {
                'success': True,
                'analysis': orch.analysis,
                'sources': orch.sources,
            }
```

- [ ] **Step 4: Verify weekly_sector_bot.py imports and runs at module level**

Run: `cd 006_auto_bot && python -c "from weekly_sector_bot import WeeklySectorBot; print('OK')"`
Expected: prints `OK` (no import errors).

- [ ] **Step 5: Commit**

```bash
git add 001_code/weekly_sector_bot.py
git commit -m "Wire orchestrator into process_sector; add deep_mode flag"
```

---

### Task 13: Add `--deep` CLI flag

**Files:**
- Modify: `001_code/weekly_sector_bot.py` (CLI argparse section near bottom)

- [ ] **Step 1: Locate argparse section**

Run: `grep -n "argparse\|add_argument\|ArgumentParser" 001_code/weekly_sector_bot.py | head -10`
Note the file path:line for the `argparse.ArgumentParser` block.

- [ ] **Step 2: Add `--deep` argument to the parser**

Inside the `ArgumentParser` block (after other `add_argument` calls, before `parse_args()`), add:

```python
    parser.add_argument(
        '--deep',
        action='store_true',
        help='Deep mode: max 3 orchestrator rounds (default 2)',
    )
```

- [ ] **Step 3: Pass `deep_mode=args.deep` to `WeeklySectorBot(...)` instantiation**

Locate where `WeeklySectorBot(...)` is constructed in `main()`. Add `deep_mode=args.deep` to the kwargs.

- [ ] **Step 4: Verify**

Run: `cd 006_auto_bot && python 001_code/weekly_sector_bot.py --help | grep deep`
Expected: shows `--deep   Deep mode: max 3 orchestrator rounds (default 2)`.

- [ ] **Step 5: Commit**

```bash
git add 001_code/weekly_sector_bot.py
git commit -m "Add --deep CLI flag for 3-round orchestration"
```

---

## Phase 6 — Comprehensive Report Gate

### Task 14: Add comprehensive variant of dimension check

**Files:**
- Modify: `001_code/sector_bot/dimensions.py`
- Test: `003_test_code/test_sector_dimensions.py`

- [ ] **Step 1: Write failing test for `claude_judge_comprehensive`**

Append to `003_test_code/test_sector_dimensions.py`:

```python
def test_claude_judge_comprehensive_signature():
    from sector_bot.dimensions import claude_judge_comprehensive
    import inspect
    sig = inspect.signature(claude_judge_comprehensive)
    params = list(sig.parameters.keys())
    assert params[0] == "report_text"
    assert "sector_count" in params
    assert "claude_caller" in params


def test_claude_judge_comprehensive_returns_dict_of_five():
    from sector_bot.dimensions import claude_judge_comprehensive

    def fake_caller(p):
        return '{"정의": true, "현황": true, "근거": false, "반론": true, "적용": true}'

    result = claude_judge_comprehensive(
        report_text="some report",
        sector_count=10,
        claude_caller=fake_caller,
    )
    assert set(result.keys()) == {"정의", "현황", "근거", "반론", "적용"}
    assert result["근거"] is False
```

- [ ] **Step 2: Run failing tests**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_dimensions.py -k comprehensive -v`
Expected: 2 tests fail with ImportError.

- [ ] **Step 3: Append `claude_judge_comprehensive` to `dimensions.py`**

```python
def _build_comprehensive_judge_prompt(report_text: str, sector_count: int) -> str:
    return f"""You are evaluating a comprehensive weekly investment report that synthesizes {sector_count} sector reports.

Apply this 5-dimension checklist (variant for cross-sector synthesis):

- "정의": Market regime (Bull / Bear / Neutral, Risk-On / Risk-Off) is explicitly named.
- "현황": At least 8 of the {sector_count} sectors are cited with specific data (numbers + dates).
- "근거": Each recommended stock/ETF in "Top Picks" cites at least one source sector report.
- "반론": "Risk Factors and Hedge Strategies" section lists 3+ risks with hedge instruments.
- "적용": All three portfolio profiles (보수형/중립형/공격형) have sector weights summing to 100%.

Report (truncated to 8000 chars):
{report_text[:8000]}

Respond with ONLY a JSON object on a single line:
{{"정의": true|false, "현황": true|false, "근거": true|false, "반론": true|false, "적용": true|false}}
"""


def claude_judge_comprehensive(
    report_text: str,
    sector_count: int,
    claude_caller,
) -> dict:
    """
    Comprehensive-report variant of claude_judge_dimensions.
    Same fail-open semantics on JSON parse errors.
    """
    prompt = _build_comprehensive_judge_prompt(report_text, sector_count)
    try:
        raw = claude_caller(prompt)
        match = re.search(r"\{[^{}]*\}", raw)
        if not match:
            raise ValueError("no JSON object in Claude response")
        parsed = json.loads(match.group(0))
        return {d.name: bool(parsed.get(d.name, True)) for d in SECTOR_DIMENSIONS}
    except Exception as e:
        logger.warning(f"Comprehensive judge failed: {e}; falling back to all-pass")
        return {d.name: True for d in SECTOR_DIMENSIONS}
```

- [ ] **Step 4: Run tests**

Run: `cd 006_auto_bot && python -m pytest 003_test_code/test_sector_dimensions.py -v`
Expected: 18 tests pass.

- [ ] **Step 5: Commit**

```bash
git add 001_code/sector_bot/dimensions.py 003_test_code/test_sector_dimensions.py
git commit -m "Add claude_judge_comprehensive for cross-sector report gate"
```

---

### Task 15: Apply gate to `comprehensive_report.generate_report` with 1 re-synthesis

**Files:**
- Modify: `001_code/sector_bot/comprehensive_report.py:85-123`

- [ ] **Step 1: Add import at top of `comprehensive_report.py`**

Near other `from .` imports add:

```python
from .dimensions import claude_judge_comprehensive
```

- [ ] **Step 2: Replace the `generate_report` body to apply the gate**

Replace the existing `generate_report` method body (lines ~85-123) with:

```python
    def generate_report(self, date: datetime = None) -> Dict:
        """
        종합 투자 평가 보고서 생성.
        1차 합성 → 5차원 게이트 → 미달 시 1회 재합성.
        """
        if date is None:
            date = datetime.now()

        # 1. 섹터 파일 수집
        collected = self.collect_sector_files(date)
        if not collected['success']:
            return {'success': False, 'error': collected['error']}

        sector_count = len(collected['sectors'])

        # 2. 1차 합성
        prompt = self._build_comprehensive_prompt(collected['sectors'], collected['missing'], date)
        logger.info(f"Comprehensive prompt: {len(prompt)} chars")

        try:
            analysis = self._call_claude(prompt)
        except Exception as e:
            return {'success': False, 'error': str(e)}

        # 3. 게이트 평가 (Claude judge)
        gate = claude_judge_comprehensive(
            report_text=analysis,
            sector_count=sector_count,
            claude_caller=self._call_claude,
        )
        failed_dims = [name for name, ok in gate.items() if not ok]
        logger.info(f"Comprehensive gate: pass={sum(gate.values())}/5, fail={failed_dims}")

        # 4. 미달 시 1회 재합성 (instruction 추가)
        if failed_dims:
            logger.info(f"Re-synthesizing once to address: {failed_dims}")
            patch_instructions = "\n".join(
                f"- {name} 차원이 미달입니다. 보고서를 다시 작성하되 이 부분을 강화해 주세요."
                for name in failed_dims
            )
            patched_prompt = (
                prompt
                + "\n\n# 재합성 지시 (이전 판본의 보완점)\n"
                + patch_instructions
                + "\n\n위 미달 차원을 반드시 충족하도록 새 보고서를 출력하세요."
            )
            try:
                analysis = self._call_claude(patched_prompt)
            except Exception as e:
                logger.warning(f"Re-synthesis failed, keeping first draft: {e}")

        # 5. 마크다운 저장
        report_content = self._build_report_markdown(analysis, date)
        filepath = os.path.join(collected['date_dir'], 'comprehensive_report.md')

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)

        logger.info(f"Comprehensive report saved: {filepath} ({len(report_content)} chars)")

        return {
            'success': True,
            'content': report_content,
            'filepath': filepath,
            'gate_results': gate,
            'failed_dimensions': failed_dims,
        }
```

- [ ] **Step 3: Verify import resolves**

Run: `cd 006_auto_bot && python -c "from sector_bot.comprehensive_report import ComprehensiveReportGenerator; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add 001_code/sector_bot/comprehensive_report.py
git commit -m "Apply 5-dim gate to comprehensive report with 1 re-synthesis"
```

---

## Phase 7 — Documentation

### Task 16: Update `docs/SECTOR_BOT.md` with orchestrator + new schedule

**Files:**
- Modify: `006_auto_bot/docs/SECTOR_BOT.md`

- [ ] **Step 1: Update the schedule table**

In `docs/SECTOR_BOT.md`, find the existing 11-sector schedule table (with `13:00`, `13:30`, etc.) and replace with the new times (12:00, 12:40, 13:20, 14:00, 14:40, 15:20, 16:00, 16:40, 17:20, 18:00, 18:40).

- [ ] **Step 2: Add new section "오케스트레이터 (5차원 검증)"**

After the existing "## 분석 프롬프트" section, add:

```markdown
## 오케스트레이터 (5차원 검증)

`sector_bot/orchestrator.py`가 검색 → 5차원 게이트 → 1회 갭필 → 분석을 시퀀싱한다. 기존 `searcher`/`analyzer`는 변경 없이 재사용.

### 5차원 체크리스트

| 차원 | 통과 기준 (정량 1차) | Claude 2차 |
|------|------------------|----------|
| 정의 | 동인 키워드 ≥2 또는 head bullet ≥2 | 항상 실행 (Q4=a) |
| 현황 | (수치, 날짜) 페어 ≥3 | ↑ |
| 근거 | Tier 1 도메인 출처 ≥2 (Bloomberg/Reuters/FT/WSJ/SEC/CNBC/MarketWatch) | ↑ |
| 반론 | 강세/약세 어휘 양쪽 출현 | ↑ |
| 적용 | 액션 동사 + 티커 패턴 | ↑ (갭필 없음 — analyzer 책임) |

### 라운드 예산

- 정상: 2 라운드 (검색 + 갭필 1회)
- `--deep`: 3 라운드
- CLI fallback 활성: 강제 1 라운드 (갭필 스킵)
- 섹터당 hard cap: 8분 — 초과 시 갭필 중단하고 분석으로 진행

### 모순 명시

분석 결과에 `## 📌 자료 간 차이` 섹션이 있으면 orchestrator가 bullet 항목을 파싱하여 `OrchestrationResult.contradictions`에 적재. 종합 보고서는 `## 📌 섹터 간 시각 차이` 변형 사용.

## 종합 보고서 게이트

`comprehensive_report.generate_report`도 동일한 5차원 게이트 적용 (변형판: "현황"=8 섹터 이상 인용, "적용"=3 포트폴리오 비중 100%). 미달 시 1회 재합성.
```

- [ ] **Step 3: Commit**

```bash
git add docs/SECTOR_BOT.md
git commit -m "Document orchestrator, 5-dim gate, and new sector schedule"
```

---

## Phase 8 — Integration Smoke Test

### Task 17: Manual smoke test — single sector with `--once --test --sector 1`

**Files:** none (manual run)

- [ ] **Step 1: Confirm `.env` has `GEMINI_API_KEY` and Claude CLI is available**

Run: `cd 006_auto_bot && grep -E "^GEMINI_API_KEY=" 001_code/.env >/dev/null && command -v claude && echo OK`
Expected: `OK` printed.

- [ ] **Step 2: Run single sector in test mode**

Run: `cd 006_auto_bot && ./run_weekly_sector.sh --sector 1 --test 2>&1 | tee /tmp/sector_smoke.log`

Expected log lines (search for them):
- `Orchestrating (max_rounds=2)`
- `Quant gate: pass=N/5`
- `Final gate: failing=[...]`
- `Orchestration done: rounds=N`

If any dimension fails, expect a `Round 2: gap-fill on '<dim>'` line.

- [ ] **Step 3: Inspect output markdown**

Run: `ls -la 006_auto_bot/004_Sector_Weekly/$(date +%Y%m%d)/sector_01_*.md`
Expected: file exists, ≥2000 chars.

Run: `grep -c "📌 자료 간 차이" 006_auto_bot/004_Sector_Weekly/$(date +%Y%m%d)/sector_01_*.md || true`
Expected: 0 or 1 (depends on whether Gemini detected contradictions).

- [ ] **Step 4: Commit log artifact (optional)**

If you want to keep the smoke log:

```bash
mkdir -p 006_auto_bot/docs/superpowers/runs
cp /tmp/sector_smoke.log 006_auto_bot/docs/superpowers/runs/$(date +%Y-%m-%d)-sector-1-smoke.log
git add 006_auto_bot/docs/superpowers/runs/
git commit -m "Add smoke-test log for sector 1 orchestrator run"
```

---

### Task 18: Manual smoke test — comprehensive report gate

**Files:** none (manual run)

- [ ] **Step 1: Run comprehensive in test mode**

Run: `cd 006_auto_bot && ./run_weekly_sector.sh --comprehensive 2>&1 | tee /tmp/comp_smoke.log`
Expected log lines:
- `Comprehensive prompt: N chars`
- `Comprehensive gate: pass=N/5, fail=[...]`
- If any failed: `Re-synthesizing once to address: [...]`

- [ ] **Step 2: Inspect comprehensive_report.md**

Run: `wc -c 006_auto_bot/004_Sector_Weekly/$(date +%Y%m%d)/comprehensive_report.md`
Expected: ≥5000 chars.

- [ ] **Step 3: If smoke OK, commit log (optional)**

```bash
cp /tmp/comp_smoke.log 006_auto_bot/docs/superpowers/runs/$(date +%Y-%m-%d)-comprehensive-smoke.log
git add 006_auto_bot/docs/superpowers/runs/
git commit -m "Add smoke-test log for comprehensive report gate"
```

---

## Self-Review Notes

**Spec coverage:**
- 경로 C (sector mini-orchestrator): Tasks 3-9 (dimensions + orchestrator)
- 부수 #1 (모순 명시): Tasks 1-2 (SKILL files) + Task 8/9 (`_extract_contradictions`)
- 부수 #4 (종합 보고서 게이트): Tasks 14-15
- 부수 #5 (CLI fallback 가드): Task 6 (`is_cli_mode_active`) + Task 8 clamp logic
- 새 스케줄 (12:00, 40분 간격, 19:20/19:40): Tasks 10-11
- Q1 hard cap 8분: Task 7 `SECTOR_HARD_CAP_SECONDS=480`, Task 8 deadline check
- Q2 Claude CLI: Task 7 `_default_claude_caller` uses `claude -p`
- Q3 로그만: dimensions_passed appears only in `logger.info` (no state.json write)
- Q4 항상 Claude 2차: Task 8 `if quant_failed: claude_judge_dimensions(...)` always runs

**Type consistency:**
- `OrchestrationResult.dimensions_passed` is `Dict[str, bool]` everywhere.
- `claude_caller` is `Callable[[str], str]` in `dimensions.py`, `orchestrator.py`, and `comprehensive_report.py`.
- `Sector.search_keywords` is mutated in `_gap_fill_round` and restored in `finally` — verified by `searcher.search_sector` reading current `sector.search_keywords` each call (see `searcher.py:209`).

**Placeholder scan:** No TODO/TBD/placeholder text. All code blocks are complete.
