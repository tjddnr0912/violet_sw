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
from shared.claude_search import ClaudeSearchError
from shared.web_search import web_search

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
    started_at = time.time()
    deadline = started_at + NEWS_HARD_CAP_SECONDS
    claude_caller = claude_caller or _default_claude_caller

    # ---- Round 1: RSS aggregation ----
    logger.info("News orchestrator Round 1: RSS aggregation")
    try:
        raw_items = aggregator.fetch_news(
            hours_limit=24,
            hours_by_category=hours_by_category or {},
        )
    except Exception as e:
        return NewsOrchestrationResult(
            success=False,
            news_items=[],
            rounds_completed=0,
            gap_fills_attempted=0,
            dimensions_passed={d.name: False for d in NEWS_DIMENSIONS},
            elapsed_seconds=time.time() - started_at,
            clamped_to_cli=False,
            error=f"RSS aggregation failed: {e}",
        )

    if not raw_items:
        return NewsOrchestrationResult(
            success=False,
            news_items=[],
            rounds_completed=0,
            gap_fills_attempted=0,
            dimensions_passed={d.name: False for d in NEWS_DIMENSIONS},
            elapsed_seconds=time.time() - started_at,
            clamped_to_cli=False,
            error="No RSS items collected",
        )

    selected = aggregator.select_top_news(max_count)
    rounds_completed = 1
    accumulated: List[dict] = list(selected)

    # ---- Dimension gate ----
    ctx = {
        "hours_by_category": hours_by_category,
        "now": datetime.now(),
    }
    quant_pass = {d.name: d.quantitative_check(accumulated, ctx) for d in NEWS_DIMENSIONS}
    quant_failed = [name for name, ok in quant_pass.items() if not ok]
    logger.info(f"Quant gate: pass={sum(quant_pass.values())}/5, fail={quant_failed}")

    if quant_failed:
        stats = _compute_stats(accumulated)
        judge_pass = claude_judge_news(
            news_items=accumulated,
            stats=stats,
            claude_caller=claude_caller,
        )
        dimensions_passed = {
            name: quant_pass[name] or judge_pass.get(name, True)
            for name in quant_pass
        }
    else:
        dimensions_passed = quant_pass

    failing_dims = [d for d in NEWS_DIMENSIONS if not dimensions_passed.get(d.name, True)]
    logger.info(f"Final gate: failing={[d.name for d in failing_dims]}")

    # ---- Gap-fill loop ----
    gap_fills_attempted = 0
    while (
        failing_dims
        and gap_fills_attempted < max_gap_fills
        and time.time() < deadline
    ):
        target = next((d for d in failing_dims if d.followup_query_template), None)
        if target is None:
            break

        gap_target = _pick_gap_target(target.name, accumulated)
        followup_query = target.followup_query_template.format(
            category=gap_target.get("category", "general"),
            topic=gap_target.get("topic", "today's top stories"),
        )
        logger.info(f"Gap-fill attempt {gap_fills_attempted + 1}: '{target.name}' → {gap_target}")
        logger.debug(f"Followup query: {followup_query!r}")

        gap_items = _gap_fill_via_cli(followup_query, gap_target.get("category"))
        gap_fills_attempted += 1

        if gap_items:
            accumulated.extend(gap_items)
            rounds_completed += 1
            # Re-evaluate just the targeted dimension
            new_pass = target.quantitative_check(accumulated, ctx)
            dimensions_passed[target.name] = new_pass
        else:
            logger.warning(f"Gap-fill on '{target.name}' returned no items")

        failing_dims = [d for d in NEWS_DIMENSIONS if not dimensions_passed.get(d.name, True)]

    if time.time() >= deadline:
        logger.warning("News hard cap elapsed (gap-fill budget exhausted); proceeding to summarizer")

    return NewsOrchestrationResult(
        success=True,
        news_items=accumulated,
        rounds_completed=rounds_completed,
        gap_fills_attempted=gap_fills_attempted,
        dimensions_passed=dimensions_passed,
        elapsed_seconds=time.time() - started_at,
        clamped_to_cli=False,
        stats=_compute_stats(accumulated),
    )


def _compute_stats(news_items: list) -> dict:
    """Aggregate counts used by the Claude judge prompt."""
    if not news_items:
        return {"total": 0}
    by_cat = Counter(item.get("category", "기타") for item in news_items)
    tier1 = sum(1 for item in news_items if item.get("source") in TIER1_SOURCES)
    korean = sum(1 for item in news_items if item.get("source") in KOREAN_SOURCES)
    return {
        "total": len(news_items),
        "by_category": dict(by_cat),
        "tier1_ratio": round(tier1 / len(news_items), 2),
        "korean_ratio": round(korean / len(news_items), 2),
    }


def _pick_gap_target(dim_name: str, news_items: list) -> dict:
    """Choose what {category} or {topic} to fill in the followup query template."""
    if dim_name == "균형":
        # missing or under-represented category
        by_cat = Counter(item.get("category", "기타") for item in news_items)
        missing = [c for c in EXPECTED_CATEGORIES if by_cat.get(c, 0) < 3]
        return {"category": missing[0] if missing else "general", "topic": "today's top stories"}
    if dim_name == "신선도":
        # category with the most stale items
        by_cat = Counter(item.get("category", "기타") for item in news_items)
        worst = max(by_cat, key=by_cat.get) if by_cat else "general"
        return {"category": worst, "topic": "breaking news"}
    if dim_name == "출처신뢰":
        # broadest topic — pick most-represented category
        by_cat = Counter(item.get("category", "기타") for item in news_items)
        top = max(by_cat, key=by_cat.get) if by_cat else "general"
        return {"category": top, "topic": top}
    if dim_name == "글로벌균형":
        return {"category": "international", "topic": "global affairs"}
    return {"category": "general", "topic": "today's top stories"}


def _gap_fill_via_cli(followup_query: str, category: Optional[str]) -> list:
    """
    Run a gap-fill round via web search (agy cascade -> Claude fallback),
    parse a JSON array of news items, and convert to the news_item dict shape
    the rest of the pipeline expects. Returns [] on any failure (gap-fill is
    best-effort).

    Name kept (`_via_cli`) for backward compat. Backend evolution: Gemini API
    -> Claude CLI + WebSearch -> now agy (Gemini) cascade with Claude CLI
    fallback. The Claude fallback stage uses Haiku primary (JSON output is
    simple), Sonnet for overload.
    """
    try:
        response = web_search(
            followup_query,
            model="haiku",
            fallback_model="sonnet",
            timeout=600,
        )
        raw = response.text
    except ClaudeSearchError as e:
        logger.warning(f"Gap-fill Claude WebSearch failed: {e}")
        return []
    except Exception as e:
        logger.warning(f"Gap-fill unexpected error: {e}")
        return []

    # Find a JSON array in the response (Gemini sometimes wraps in prose)
    match = re.search(r"\[\s*\{.*?\}\s*\]", raw, re.DOTALL)
    if not match:
        logger.warning(f"Gap-fill response had no JSON array: {raw[:200]}")
        return []

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        logger.warning(f"Gap-fill JSON parse failed: {e}")
        return []

    items = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        try:
            pub = datetime.strptime(entry.get("date", ""), "%Y-%m-%d") if entry.get("date") else datetime.now()
        except ValueError:
            pub = datetime.now()
        items.append({
            "title": entry.get("title", "Untitled"),
            "link": entry.get("url", ""),
            "description": entry.get("summary", ""),
            "rss_summary": "",
            "full_content": entry.get("summary", ""),
            "published_date": pub,
            "source": entry.get("source", "Gemini CLI"),
            "source_url": entry.get("url", ""),
            "category": category or "기타",
        })
    return items
