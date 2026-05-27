"""
Gemini API wrapper with model fallback chain
--------------------------------------------
Replaces the legacy `gemini -p` CLI invocation (deprecated by Google,
shutting down June 2026) with a pure `google-genai` API call. On 429
RESOURCE_EXHAUSTED or 503 UNAVAILABLE, falls through a chain of
progressively older models so the bots keep working even when the
primary model's free-tier quota is exhausted.

Fallback chain (env-configurable):

    GEMINI_MODEL             default: gemini-3.1-flash-lite   ← primary
    GEMINI_FALLBACK_MODELS   default: gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash

All four models support `google_search` grounding per AI Studio docs
(verified 2026-05) except gemini-3-flash-preview, whose grounding
support is undocumented; if a grounded call against that model fails,
the chain continues to the next entry.

Backward compatibility
----------------------
The legacy module exposed `call_gemini_cli`, `is_quota_error`,
`extract_urls`, `is_cli_mode_active`. All four are kept here with the
same signatures so existing importers (news_bot, sector_bot,
research_orchestrator) need no changes — only the implementation moves
from subprocess to the API.

Pricing note: Gemini 3.x grounding is billed per Google Search query
the model decides to issue; Gemini 2.5 is billed per prompt. Heavy
fallback into 2.5 may therefore be cheaper, not more expensive.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)


# -------- Model chain configuration --------

DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
_RAW_FALLBACK = os.getenv(
    "GEMINI_FALLBACK_MODELS",
    "gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash",
)
FALLBACK_MODELS: List[str] = [m.strip() for m in _RAW_FALLBACK.split(",") if m.strip()]


def _client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


# -------- Public helpers --------

def is_quota_error(error: Exception) -> bool:
    """True for retryable Gemini server errors that should trigger model fallback.

    Catches 429 RESOURCE_EXHAUSTED, 503 UNAVAILABLE, and generic 'overloaded'
    messages. Used by callers that still want to react to quota events
    explicitly (e.g., logging / metrics).
    """
    s = str(error)
    if "429" in s or "RESOURCE_EXHAUSTED" in s:
        return True
    if "503" in s or "UNAVAILABLE" in s or "overloaded" in s.lower():
        return True
    return False


def extract_urls(text: str) -> List[str]:
    """Extract HTTP(S) URLs from free-form text (used for CLI-style responses
    that didn't carry structured grounding metadata). Kept for backward compat;
    new code should read GeminiResponse.sources instead."""
    url_pattern = r'https?://[^\s<>\"\'\)\]，。）」』]+'
    urls = re.findall(url_pattern, text)
    return list(dict.fromkeys(urls))


def is_cli_mode_active(*_instances) -> bool:
    """Deprecated. The CLI fallback path was removed in May 2026; quota
    handling is now done in-process via the model fallback chain. Kept as a
    no-op (always False) so sector_bot/orchestrator.py imports keep working
    without clamping max_rounds."""
    return False


# -------- Rich response type --------

@dataclass
class GeminiResponse:
    text: str
    model_used: str
    sources: List[str] = field(default_factory=list)
    finish_reason: Optional[str] = None
    safety_blocked: bool = False


# -------- Primary entrypoint --------

def call_gemini_with_fallback(
    prompt: str,
    *,
    use_grounding: bool = True,
    system_instruction: Optional[str] = None,
    safety_settings: Optional[list] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    models: Optional[List[str]] = None,
) -> GeminiResponse:
    """Run Gemini `generate_content` with automatic model fallback.

    Args:
        prompt: prompt text.
        use_grounding: attach the `google_search` tool. Default True because
            the legacy CLI binary it replaces effectively had web search built
            in; analysis/summarization callers that operate purely on already-
            collected data should pass `use_grounding=False` to avoid the
            per-query grounding charge.
        system_instruction: optional system instruction.
        safety_settings: optional list of types.SafetySetting.
        temperature / max_output_tokens: optional generation params.
        models: optional override of [primary, *fallbacks]. Default is
            [DEFAULT_MODEL] + FALLBACK_MODELS.

    Returns:
        GeminiResponse — `text` is the generated text, `model_used` is which
        model actually answered, `sources` is grounding URIs (empty if
        use_grounding=False), `safety_blocked=True` short-circuits fallback
        (a safety verdict won't differ between models).

    Raises:
        RuntimeError if every model in the chain failed for non-safety reasons.
    """
    chain = models if models else [DEFAULT_MODEL, *FALLBACK_MODELS]
    if not chain:
        raise RuntimeError("Empty Gemini model chain")

    client = _client()

    cfg_kwargs: dict = {}
    if use_grounding:
        cfg_kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
    if system_instruction:
        cfg_kwargs["system_instruction"] = system_instruction
    if safety_settings:
        cfg_kwargs["safety_settings"] = safety_settings
    if temperature is not None:
        cfg_kwargs["temperature"] = temperature
    if max_output_tokens is not None:
        cfg_kwargs["max_output_tokens"] = max_output_tokens
    config = types.GenerateContentConfig(**cfg_kwargs)

    last_err: Optional[Exception] = None
    for idx, model in enumerate(chain):
        try:
            logger.info(
                f"Gemini call [{idx + 1}/{len(chain)}] model={model} "
                f"grounding={use_grounding} prompt_chars={len(prompt)}"
            )
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=config,
            )

            text, finish_reason, safety_blocked, sources = _extract_response(response)

            if safety_blocked:
                # Safety verdict is content-based; trying another model won't change it.
                logger.warning(f"Gemini SAFETY block on {model}; returning empty text")
                return GeminiResponse(
                    text="",
                    model_used=model,
                    sources=sources,
                    finish_reason=finish_reason,
                    safety_blocked=True,
                )

            if not text:
                raise RuntimeError(f"Empty response from {model} (finish={finish_reason})")

            logger.info(
                f"Gemini OK model={model} chars={len(text)} "
                f"sources={len(sources)} finish={finish_reason}"
            )
            return GeminiResponse(
                text=text,
                model_used=model,
                sources=sources,
                finish_reason=finish_reason,
                safety_blocked=False,
            )

        except Exception as e:
            last_err = e
            has_next = idx < len(chain) - 1
            if is_quota_error(e) and has_next:
                logger.warning(f"{model} quota/unavailable ({e}); falling through to next model")
                continue
            if has_next:
                # Non-quota error — try the next model anyway, but log.
                logger.warning(f"{model} failed ({type(e).__name__}: {e}); falling through")
                continue
            raise RuntimeError(
                f"All {len(chain)} Gemini models failed; last error on {model}: {e}"
            ) from e

    raise RuntimeError(f"Gemini chain exhausted unexpectedly. Last error: {last_err}")


def _extract_response(response) -> tuple:
    """Pull text / finish_reason / safety_blocked / grounding sources from a
    google-genai response object. Robust to safety blocks (response.text raises)."""
    finish_reason: Optional[str] = None
    safety_blocked = False
    sources: List[str] = []
    text = ""

    candidates = getattr(response, "candidates", None) or []
    if candidates:
        cand = candidates[0]
        fr = getattr(cand, "finish_reason", None)
        if fr is not None:
            finish_reason = fr.name if hasattr(fr, "name") else str(fr)
        if finish_reason == "SAFETY":
            safety_blocked = True

        # Prefer response.text; fall back to manual parts concatenation if it errors.
        try:
            text = (response.text or "").strip() if hasattr(response, "text") else ""
        except Exception:
            text = ""
        if not text and not safety_blocked:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", None) or []
            collected = []
            for part in parts:
                pt = getattr(part, "text", None)
                if pt:
                    collected.append(pt)
            text = "\n".join(collected).strip()

        # Grounding sources
        gm = getattr(cand, "grounding_metadata", None)
        if gm:
            chunks = getattr(gm, "grounding_chunks", None) or []
            for ch in chunks:
                web = getattr(ch, "web", None)
                uri = getattr(web, "uri", None) if web else None
                if uri:
                    sources.append(uri)
            sources = list(dict.fromkeys(sources))

    return text, finish_reason, safety_blocked, sources


# -------- Backward-compatible legacy entrypoint --------

def call_gemini_cli(prompt: str, timeout: int = None) -> str:
    """Backward-compat: same signature the codebase used during the CLI era.

    Returns plain text (no metadata). Grounding is enabled by default to
    match the behavior of the old `gemini -p` binary, which had the web
    search tool wired in. Callers that don't need grounding should migrate
    to `call_gemini_with_fallback(prompt, use_grounding=False)`.

    `timeout` is accepted for signature compatibility but ignored — the
    SDK manages its own request timeouts.
    """
    _ = timeout  # retained for ABI compatibility
    return call_gemini_with_fallback(prompt, use_grounding=True).text
