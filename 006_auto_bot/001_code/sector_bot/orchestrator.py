"""
Sector Research Orchestrator
----------------------------
Wraps searcher + analyzer with a 5-dimension Claude verification gate
and targeted Gemini gap-fill rounds. Produces a richer search context
before the final analyzer call without modifying searcher/analyzer themselves.

Time budget: SECTOR_HARD_CAP_SECONDS (480s, 8 min) gates the gap-fill loop;
once elapsed, no new gap-fills start but the final analyze still runs (the
analyze step is a single API call we do not interrupt mid-flight).

CLI fallback active (searcher or analyzer in `_use_cli_fallback=True` mode)
→ max_rounds clamped to 1, skipping gap-fill entirely.
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
    # gap_fills_attempted gates the loop (so a chain of failed gap-fills cannot loop forever);
    # rounds_completed only counts successful content-producing rounds (reported to caller).
    gap_fills_attempted = 0
    max_gap_fills = max(0, effective_max_rounds - 1)  # round 1 is the initial search

    while (
        failing_dims
        and gap_fills_attempted < max_gap_fills
        and time.time() < deadline
    ):
        # pick the highest-priority failing dim that has a follow-up template
        target = next((d for d in failing_dims if d.followup_query_template), None)
        if target is None:
            break

        followup_query = target.followup_query_template.format(sector=sector.name)
        logger.info(f"[{sector.name}] Gap-fill attempt {gap_fills_attempted + 1}: '{target.name}'")
        logger.debug(f"[{sector.name}] Followup query: {followup_query!r}")

        gap_result = _gap_fill_round(searcher, sector, followup_query, deadline)
        gap_fills_attempted += 1

        if gap_result.get("success"):
            rounds_completed += 1
            accumulated_content += "\n\n--- gap-fill: " + target.name + " ---\n"
            accumulated_content += gap_result.get("content", "")
            accumulated_sources.extend(gap_result.get("sources", []))
            # Full re-sweep: gap-fill content may rescue dims beyond the targeted one
            # (e.g. a 근거 fill that brings new sources also satisfies 현황).
            quant_pass = {
                d.name: d.quantitative_check(accumulated_content, accumulated_sources)
                for d in SECTOR_DIMENSIONS
            }
            dimensions_passed = {
                name: quant_pass[name] or dimensions_passed.get(name, False)
                for name in quant_pass
            }
        else:
            logger.warning(f"[{sector.name}] Gap-fill on '{target.name}' failed: {gap_result.get('error')}")

        failing_dims = [d for d in SECTOR_DIMENSIONS if not dimensions_passed.get(d.name, True)]

    # ---- Final analyze ----
    if time.time() >= deadline:
        # Hard cap governs gap-fill budget; final analyze always runs (see module docstring).
        logger.warning(
            f"[{sector.name}] Hard cap elapsed (gap-fill budget exhausted); "
            f"proceeding to final analyze"
        )

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

    Contract: `followup_query` is a multi-sentence English instruction (from
    Dimension.followup_query_template). The searcher must treat search_keywords[0]
    as instruction text — see sector_bot/dimensions.py templates for examples.
    """
    if time.time() >= deadline:
        return {"success": False, "error": "deadline reached"}

    original_keywords = list(sector.search_keywords)
    # Inject followup as primary keyword; keep up to 3 original keywords as supporting context.
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
