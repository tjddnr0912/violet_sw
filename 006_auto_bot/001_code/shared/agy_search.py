"""Antigravity (`agy`) CLI WebSearch wrapper
-------------------------------------------
Primary web-search backend for the bots, replacing the previous
`claude -p` WebSearch path. `agy -p` is the Antigravity agentic CLI's
non-interactive print mode; with `--dangerously-skip-permissions` it runs
its built-in web-search tool without prompting and prints a clean answer
to stdout (no agent scaffolding).

`agy`'s *default* model auto-routes (observed Claude Sonnet 4.6 on one
call, Gemini 3.1 Pro on the next), so callers MUST pin a model with
`--model "<name>"` for deterministic behavior. Valid names come from
`agy models` (e.g. "Gemini 3.1 Pro (High)", "Gemini 3.5 Flash (Medium)").

The response shape and source extraction are shared with
`shared.claude_search` so the dispatcher in `shared.web_search` can return
one uniform `ClaudeSearchResponse` regardless of backend.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from typing import List

from shared.claude_search import ClaudeSearchResponse, _extract_sources

logger = logging.getLogger(__name__)


class AgySearchError(RuntimeError):
    """Raised on a hard agy failure: non-zero exit, empty stdout, or timeout."""


def _agy_bin() -> str:
    """Resolve the agy executable robustly.

    Production bots may be launched from a shell whose PATH doesn't include
    `~/.local/bin` (e.g. terminal not re-sourced after `agy install`). So:
    env `AGY_BIN` wins, else `which agy`, else the conventional install path.
    Falls back to the bare name "agy" so the error surfaces clearly if truly
    absent.
    """
    env = os.getenv("AGY_BIN")
    if env:
        return env
    found = shutil.which("agy")
    if found:
        return found
    local = os.path.expanduser("~/.local/bin/agy")
    return local if os.path.exists(local) else "agy"


def agy_websearch(
    prompt: str,
    *,
    model: str,
    timeout: int,
) -> ClaudeSearchResponse:
    """Run a single `agy -p` web-search call pinned to one model.

    Args:
        prompt: full prompt text (multi-line OK). Passed as an argv element
            (no shell), so no escaping/quoting concerns.
        model: exact agy model display name (from `agy models`).
        timeout: subprocess timeout in seconds.

    Returns:
        ClaudeSearchResponse with .text, .sources, .model_used="agy:<model>".

    Raises:
        AgySearchError on non-zero exit, empty stdout, or timeout.
    """
    cmd: List[str] = [
        _agy_bin(), "-p", prompt,
        "--model", model,
        "--dangerously-skip-permissions",
    ]

    logger.info(
        f"agy_websearch model={model!r} prompt_chars={len(prompt)} timeout={timeout}s"
    )

    started = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,  # agy -p hangs on an inherited stdin pipe
        )
    except subprocess.TimeoutExpired as e:
        raise AgySearchError(
            f"agy timed out after {timeout}s (model={model!r}, prompt={len(prompt)} chars)"
        ) from e
    except OSError as e:
        # agy missing / not on PATH / not executable -> degrade so the
        # dispatcher falls back to Claude instead of crashing the bot.
        raise AgySearchError(f"agy not runnable ({cmd[0]!r}): {e}") from e
    elapsed = time.monotonic() - started

    if result.returncode != 0:
        raise AgySearchError(
            f"agy exit={result.returncode} model={model!r} "
            f"stderr={(result.stderr or '').strip()[:400]}"
        )

    text = (result.stdout or "").strip()
    if not text:
        raise AgySearchError(
            f"agy returned empty stdout model={model!r} "
            f"(stderr={(result.stderr or '').strip()[:200]})"
        )

    sources = _extract_sources(text)
    logger.info(
        f"agy_websearch OK model={model!r} chars={len(text)} "
        f"sources={len(sources)} elapsed={elapsed:.1f}s"
    )
    return ClaudeSearchResponse(
        text=text,
        sources=sources,
        model_used=f"agy:{model}",
        elapsed_seconds=elapsed,
    )
