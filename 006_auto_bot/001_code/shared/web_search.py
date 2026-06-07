"""Web-search dispatcher: agy model cascade -> Claude fallback
-------------------------------------------------------------
Single entry point the bots call for live web data. Tries the Antigravity
(`agy`) CLI across a cascade of Gemini models in order, degrading to the
next on any *hard* failure (non-zero exit / empty stdout / timeout). If the
whole agy cascade is exhausted, it falls back to `claude_websearch`
(Claude CLI + WebSearch), preserving the exact pre-migration behavior.

Cascade (default, override via env `AGY_SEARCH_MODELS`, pipe-delimited):
    Gemini 3.1 Pro (High)  ->  Gemini 3.5 Flash (High)  ->  Gemini 3.5 Flash (Medium)
    -> claude_websearch(model=<caller>, fallback_model=<caller>)

Each agy stage is bounded by `AGY_SEARCH_TIMEOUT` (default 300s; observed
real latency is ~15-25s) so the cascade fails fast; the Claude fallback
keeps the caller's longer timeout. The return type is always
`ClaudeSearchResponse`, so existing call sites need only swap the function
name — `.text` / `.sources` / `.model_used` / `.elapsed_seconds` are
identical across backends.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from shared.agy_search import agy_websearch, AgySearchError
from shared.claude_search import ClaudeSearchResponse, claude_websearch

logger = logging.getLogger(__name__)


DEFAULT_AGY_MODELS: List[str] = [
    "Gemini 3.1 Pro (High)",
    "Gemini 3.5 Flash (High)",
    "Gemini 3.5 Flash (Medium)",
]

# Per-agy-stage subprocess timeout. Short because agy web search is fast;
# a hung model should yield to the next quickly rather than burn the
# caller's full (minutes-long) budget.
AGY_SEARCH_TIMEOUT = int(os.getenv("AGY_SEARCH_TIMEOUT", "300"))


def _agy_models() -> List[str]:
    """Cascade model list — env `AGY_SEARCH_MODELS` (pipe-delimited) or default.

    Pipe-delimited because the display names contain spaces and parentheses
    (e.g. "Gemini 3.1 Pro (High)") but never a pipe.
    """
    raw = os.getenv("AGY_SEARCH_MODELS")
    if raw:
        models = [m.strip() for m in raw.split("|") if m.strip()]
        if models:
            return models
    return list(DEFAULT_AGY_MODELS)


def web_search(
    prompt: str,
    *,
    model: str = "sonnet",
    fallback_model: Optional[str] = "haiku",
    timeout: int = 900,
) -> ClaudeSearchResponse:
    """Run a web search via the agy cascade, falling back to Claude.

    Args:
        prompt: full prompt text.
        model: Claude model for the *fallback* stage (alias or full id).
        fallback_model: Claude CLI auto-fallback model for the fallback stage.
        timeout: subprocess timeout for the Claude fallback stage. The agy
            stages use `AGY_SEARCH_TIMEOUT` instead.

    Returns:
        ClaudeSearchResponse from the first backend that succeeds.

    Raises:
        Whatever `claude_websearch` raises (ClaudeSearchError) if every agy
        model AND the Claude fallback fail.
    """
    for m in _agy_models():
        try:
            return agy_websearch(prompt, model=m, timeout=AGY_SEARCH_TIMEOUT)
        except AgySearchError as e:
            logger.warning(f"agy model {m!r} failed, trying next: {e}")
            continue

    logger.info(
        f"agy cascade exhausted -> claude fallback (model={model}, fallback={fallback_model})"
    )
    return claude_websearch(
        prompt,
        model=model,
        fallback_model=fallback_model,
        timeout=timeout,
    )
