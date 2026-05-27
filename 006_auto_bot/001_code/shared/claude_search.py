"""
Claude CLI WebSearch wrapper
----------------------------
Replaces the Gemini `google_search` grounding path for bot use cases that
need live web data. Uses `claude -p --model ... --fallback-model ...` so
the same subprocess pattern the rest of the bot already follows applies
here too — and Claude CLI's built-in WebSearch tool is auto-active in
non-interactive (`-p`) mode.

Why this exists (2026-05-27 migration):
  Gemini 3.x grounding has a separate, very tight quota that the AI
  Studio dashboard doesn't surface. Even with model RPD usage at 10/500,
  google_search grounding calls returned 429 on the entire 3.x family.
  Only gemini-2.5-flash survives because its pricing model groups
  grounding into the per-prompt charge. Rather than scrape by on the one
  surviving model, we route the four grounded call sites (telegram
  quick/deep, news gap-fill, sector search) through Claude WebSearch
  instead, where the quota lives in a different bucket entirely.

The non-grounded call sites (news summarizer, sector analyzer) keep
using shared/gemini_cli.py — they were never the problem.

External contract
-----------------
    response = claude_websearch(
        prompt,
        model="sonnet",
        fallback_model="haiku",
        timeout=900,
    )
    response.text       # markdown body (Claude often appends a Sources: footer)
    response.sources    # list[str] of URLs extracted from that footer + inline links
    response.model_used # which model actually answered (best-effort; may equal
                        # fallback_model if primary was overloaded)
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


DEFAULT_MODEL = os.getenv("CLAUDE_SEARCH_MODEL", "sonnet")
DEFAULT_FALLBACK = os.getenv("CLAUDE_SEARCH_FALLBACK_MODEL", "haiku")
DEFAULT_TIMEOUT = int(os.getenv("CLAUDE_SEARCH_TIMEOUT", "900"))  # 15 min default


class ClaudeSearchError(RuntimeError):
    """Raised when the claude subprocess fails or returns empty stdout."""


@dataclass
class ClaudeSearchResponse:
    text: str
    sources: List[str] = field(default_factory=list)
    model_used: str = ""
    elapsed_seconds: float = 0.0


def claude_websearch(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    fallback_model: Optional[str] = DEFAULT_FALLBACK,
    timeout: int = DEFAULT_TIMEOUT,
) -> ClaudeSearchResponse:
    """Run `claude -p` with the WebSearch tool active.

    Args:
        prompt: full prompt text (multi-line OK).
        model: primary Claude model. Accepts alias (`haiku`/`sonnet`/`opus`)
            or full ID (`claude-sonnet-4-6`, etc.).
        fallback_model: if Claude flags the primary as overloaded or
            unavailable, it transparently retries on this model. Pass
            `None` to disable the CLI's auto-fallback.
        timeout: subprocess timeout in seconds.

    Returns:
        ClaudeSearchResponse with .text (markdown), .sources (URLs), and
        .model_used (the primary model, since the CLI doesn't surface
        which model actually answered when fallback fires).

    Raises:
        ClaudeSearchError on non-zero exit or empty stdout.
    """
    import time

    cmd: List[str] = [
        "claude", "-p",
        "--model", model,
        "--dangerously-skip-permissions",
        "-",
    ]
    if fallback_model:
        # --fallback-model only works with --print (we pass -p), so it's safe here.
        cmd[2:2] = ["--fallback-model", fallback_model]
        # NOTE: we insert before --model so the final order is:
        #   claude -p --fallback-model <fb> --model <primary> --dangerously-skip-permissions -

    logger.info(
        f"claude_websearch model={model} fallback={fallback_model} "
        f"prompt_chars={len(prompt)} timeout={timeout}s"
    )

    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise ClaudeSearchError(
            f"claude subprocess timed out after {timeout}s "
            f"(model={model}, prompt={len(prompt)} chars)"
        ) from e
    elapsed = time.monotonic() - started

    if result.returncode != 0:
        raise ClaudeSearchError(
            f"claude exit={result.returncode} "
            f"stderr={(result.stderr or '').strip()[:400]}"
        )

    text = (result.stdout or "").strip()
    if not text:
        raise ClaudeSearchError(
            f"claude returned empty stdout "
            f"(stderr={(result.stderr or '').strip()[:200]})"
        )

    sources = _extract_sources(text)
    logger.info(
        f"claude_websearch OK chars={len(text)} sources={len(sources)} "
        f"elapsed={elapsed:.1f}s"
    )
    return ClaudeSearchResponse(
        text=text,
        sources=sources,
        model_used=model,
        elapsed_seconds=elapsed,
    )


def _extract_sources(text: str) -> List[str]:
    """Pull URLs from the typical Claude WebSearch response shape.

    Claude responses we observed end with a `Sources:` footer like:

        ...body...

        Sources:
        - [Title](https://example.com/path)
        - [Other Title](https://other.example.com)

    We grab URLs from that footer first (highest signal), then any
    inline markdown links anywhere in the body, then bare http(s) URLs
    as a last resort. Duplicates dropped, order preserved.
    """
    urls: List[str] = []

    # Footer
    m = re.search(
        r"^Sources?\s*:\s*\n(.+?)(?:\n\n|\Z)",
        text,
        re.DOTALL | re.IGNORECASE | re.MULTILINE,
    )
    if m:
        urls += re.findall(r"https?://[^\s\)\]\<\>\"']+", m.group(1))

    # Inline markdown links anywhere
    urls += re.findall(r"\]\((https?://[^\)\s]+)\)", text)

    # Bare URLs as last resort (only if we still have nothing)
    if not urls:
        urls += re.findall(r"https?://[^\s\)\]\<\>\"']+", text)

    # Dedup, preserve order
    return list(dict.fromkeys(urls))


# -------- Convenience: drop-in shape for the Gemini wrapper --------

def call_websearch_like_gemini(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    fallback_model: Optional[str] = DEFAULT_FALLBACK,
    timeout: int = DEFAULT_TIMEOUT,
):
    """Compatibility helper for sites that previously called
    `shared.gemini_cli.call_gemini_with_fallback(..., use_grounding=True)`
    and only cared about `(text, sources)`.

    Returns an object with `.text` and `.sources` attributes — same access
    pattern as the legacy Gemini response, so the migration at each call
    site is just a one-line import swap and an argument rename.
    """
    return claude_websearch(
        prompt,
        model=model,
        fallback_model=fallback_model,
        timeout=timeout,
    )
