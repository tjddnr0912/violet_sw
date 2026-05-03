"""
Sector Verification Dimensions
------------------------------
5-dimension checklist applied to each sector's research output.
Each dimension provides:
  - quantitative_check: regex-based pass/fail on raw search content
  - followup_query_template: Gemini query when dimension fails
  - check_description: text passed to Claude judge for 2nd-pass validation
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


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
    claude_caller: Callable[[str], str],
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
        # schema is flat (no nested braces) — see _build_judge_prompt template
        match = re.search(r"\{[^{}]*\}", raw)
        if not match:
            raise ValueError("no JSON object in Claude response")
        parsed = json.loads(match.group(0))
        missing = [d.name for d in SECTOR_DIMENSIONS if d.name not in parsed]
        if missing:
            logger.warning(
                f"Claude judge response missing dimension keys {missing} for {sector_name}; "
                f"defaulting missing to True"
            )
        return {d.name: bool(parsed.get(d.name, True)) for d in SECTOR_DIMENSIONS}
    except Exception as e:
        logger.warning(f"Claude judge failed for {sector_name}: {e}; falling back to all-pass")
        return {d.name: True for d in SECTOR_DIMENSIONS}


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
    claude_caller: Callable[[str], str],
) -> dict:
    """
    Comprehensive-report variant of claude_judge_dimensions.
    Same fail-open semantics on JSON parse errors.
    """
    prompt = _build_comprehensive_judge_prompt(report_text, sector_count)
    try:
        raw = claude_caller(prompt)
        # schema is flat (no nested braces) — see _build_comprehensive_judge_prompt template
        match = re.search(r"\{[^{}]*\}", raw)
        if not match:
            raise ValueError("no JSON object in Claude response")
        parsed = json.loads(match.group(0))
        missing = [d.name for d in SECTOR_DIMENSIONS if d.name not in parsed]
        if missing:
            logger.warning(
                f"Comprehensive judge response missing dimension keys {missing}; "
                f"defaulting missing to True"
            )
        return {d.name: bool(parsed.get(d.name, True)) for d in SECTOR_DIMENSIONS}
    except Exception as e:
        logger.warning(f"Comprehensive judge failed: {e}; falling back to all-pass")
        return {d.name: True for d in SECTOR_DIMENSIONS}
