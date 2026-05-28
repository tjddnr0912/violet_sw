"""
Image generator wrapper with multi-backend support
--------------------------------------------------
Generates blog illustration images via a swappable backend, returning raw
bytes the rest of the pipeline (`shared/image_uploader.py` →
`shared/blogger_html_inject.py`) consumes uniformly.

Backends (env-selectable):
    IMAGE_GEN_BACKEND      default: 'pollinations'
                           values:  'pollinations' | 'imagen'

Backend comparison (2026-05-28 research):
    pollinations    — open-source, real free tier, REST + URL endpoint,
                      no paid wall. SLA not guaranteed (open-source service).
                      Recommended starting point.
    imagen          — Google Imagen 4 via google-genai SDK. **Paid only**
                      as of 2026-05 (free RPD shown in AI Studio dashboard
                      but actual call returns 400 INVALID_ARGUMENT
                      "Imagen is only available on paid plans"). Quality
                      and stability highest, but requires Google billing.

Both backends return an `ImagenResponse` (name kept for backward compat with
existing callers) so swapping is a one-env-var change. Adding another
backend (e.g. HuggingFace Inference) means appending a single dispatcher
branch in `generate_image`.

Migration / context (2026-05-28):
    Bots upload posts to Blogger as HTML. To embed illustrations we need
    a public URL, but model output is local bytes. This module is step 1
    (bytes generation). Step 2 (upload to CDN) is in `shared/image_uploader.py`.
    Step 3 (inject into HTML) is in `shared/blogger_html_inject.py`.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


# -------- Backend selector --------

BACKEND = os.getenv("IMAGE_GEN_BACKEND", "pollinations").lower().strip()


# -------- Imagen (Google Imagen 4) backend config --------

IMAGEN_DEFAULT_MODEL = os.getenv("IMAGEN_MODEL", "imagen-4.0-fast-generate-001")
_IMAGEN_RAW_FALLBACK = os.getenv(
    "IMAGEN_FALLBACK_MODELS",
    "imagen-4.0-generate-001,imagen-4.0-ultra-generate-001",
)
IMAGEN_FALLBACK_MODELS: List[str] = [
    m.strip() for m in _IMAGEN_RAW_FALLBACK.split(",") if m.strip()
]


# -------- Pollinations backend config --------

POLLINATIONS_BASE = os.getenv(
    "POLLINATIONS_BASE_URL", "https://gen.pollinations.ai"
).rstrip("/")
POLLINATIONS_MODEL = os.getenv("POLLINATIONS_MODEL", "flux")
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY")  # optional but recommended
POLLINATIONS_TIMEOUT = int(os.getenv("POLLINATIONS_TIMEOUT", "120"))


# -------- Aspect ratio presets --------

ASPECT_HERO = "16:9"
ASPECT_INLINE = "16:9"
ASPECT_SQUARE = "1:1"
ASPECT_PORTRAIT = "3:4"

# Aspect-to-pixel resolution for Pollinations (which takes width/height, not ratio).
_ASPECT_DIMS = {
    "16:9": (1280, 720),
    "1:1": (1024, 1024),
    "3:4": (864, 1152),
    "4:3": (1152, 864),
    "9:16": (720, 1280),
}


class ImagenError(RuntimeError):
    """Raised when every model/attempt in the active backend failed."""


@dataclass
class ImagenResponse:
    """Backend-agnostic response. Name kept for backward compat with callers
    that previously imported it from the Imagen-only version."""
    image_bytes: bytes
    model_used: str
    aspect_ratio: str
    backend: str = "unknown"
    mime_type: str = "image/png"


# -------- Public entrypoint (dispatcher) --------

def generate_image(
    prompt: str,
    *,
    aspect_ratio: str = ASPECT_INLINE,
    person_generation: str = "allow_adult",
    models: Optional[List[str]] = None,
) -> ImagenResponse:
    """Generate a single image via the active backend.

    Args:
        prompt: English description (both backends prefer English).
            Max ~480 tokens for Imagen, similar limit for Pollinations.
        aspect_ratio: '1:1' | '3:4' | '4:3' | '9:16' | '16:9'. Default 16:9.
        person_generation: Imagen-only ('dont_allow' | 'allow_adult' | 'allow_all').
            Ignored for Pollinations.
        models: optional override of [primary, *fallbacks]. Imagen-only.

    Returns:
        ImagenResponse with raw bytes + which backend/model answered.

    Raises:
        ImagenError on backend failure (or unknown backend name).
    """
    if BACKEND == "pollinations":
        return _generate_via_pollinations(prompt, aspect_ratio=aspect_ratio)
    if BACKEND == "imagen":
        return _generate_via_imagen(
            prompt,
            aspect_ratio=aspect_ratio,
            person_generation=person_generation,
            models=models,
        )
    raise ImagenError(
        f"Unknown IMAGE_GEN_BACKEND={BACKEND!r}. "
        f"Supported: 'pollinations' (default), 'imagen'."
    )


# -------- Backend: Pollinations.ai --------

def _generate_via_pollinations(
    prompt: str,
    *,
    aspect_ratio: str = ASPECT_INLINE,
) -> ImagenResponse:
    """Call Pollinations.ai's REST endpoint and return PNG/JPG bytes directly.

    Endpoint: GET /image/{prompt} → image bytes
    Auth: optional `?key=...` query parameter (anonymous works but rate-limited).

    Docs verified 2026-05-28 against:
        https://github.com/pollinations/pollinations/blob/main/APIDOCS.md
    """
    import requests
    from urllib.parse import quote

    width, height = _ASPECT_DIMS.get(aspect_ratio, _ASPECT_DIMS["16:9"])
    url = f"{POLLINATIONS_BASE}/image/{quote(prompt, safe='')}"
    params = {
        "model": POLLINATIONS_MODEL,
        "width": width,
        "height": height,
        "nologo": "true",  # remove watermark if model supports
    }
    if POLLINATIONS_API_KEY:
        params["key"] = POLLINATIONS_API_KEY

    logger.info(
        f"Pollinations call model={POLLINATIONS_MODEL} "
        f"size={width}x{height} prompt_chars={len(prompt)} "
        f"keyed={bool(POLLINATIONS_API_KEY)}"
    )

    try:
        r = requests.get(url, params=params, timeout=POLLINATIONS_TIMEOUT)
    except requests.RequestException as e:
        raise ImagenError(f"Pollinations request failed: {e}") from e

    if r.status_code != 200:
        # Common: 429 RATE_LIMITED (no key or anon limit hit), 5xx (service down)
        snippet = (r.text or "")[:200]
        raise ImagenError(
            f"Pollinations HTTP {r.status_code}: {snippet}"
        )

    content_type = r.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        snippet = (r.text or r.content[:200].decode("utf-8", errors="replace"))[:200]
        raise ImagenError(
            f"Pollinations returned non-image content ({content_type}): {snippet}"
        )

    img_bytes = r.content
    if not img_bytes:
        raise ImagenError("Pollinations returned empty body")

    mime_type = content_type.split(";")[0].strip() or "image/png"
    logger.info(
        f"Pollinations OK bytes={len(img_bytes)} mime={mime_type} "
        f"aspect={aspect_ratio}"
    )
    return ImagenResponse(
        image_bytes=img_bytes,
        model_used=POLLINATIONS_MODEL,
        aspect_ratio=aspect_ratio,
        backend="pollinations",
        mime_type=mime_type,
    )


# -------- Backend: Google Imagen 4 --------

def _generate_via_imagen(
    prompt: str,
    *,
    aspect_ratio: str = ASPECT_INLINE,
    person_generation: str = "allow_adult",
    models: Optional[List[str]] = None,
) -> ImagenResponse:
    """Original Imagen 4 backend via google-genai SDK.

    Currently paid-only in Google AI Studio (verified 2026-05-28 — free RPD
    shown in dashboard but actual call returns
    `400 INVALID_ARGUMENT: Imagen is only available on paid plans`).
    Activate by enabling billing at https://ai.dev/projects.

    Same fallback chain logic as before; kept for users who prefer Google's
    quality/stability and accept the per-image cost.
    """
    from google import genai
    from google.genai import types

    if not os.getenv("GEMINI_API_KEY"):
        raise ImagenError("GEMINI_API_KEY not set (export in ~/.zshenv)")

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    chain = models if models else [IMAGEN_DEFAULT_MODEL, *IMAGEN_FALLBACK_MODELS]
    if not chain:
        raise ImagenError("Empty Imagen model chain")

    config = types.GenerateImagesConfig(
        number_of_images=1,
        aspect_ratio=aspect_ratio,
        person_generation=person_generation,
    )

    last_err: Optional[Exception] = None
    for idx, model in enumerate(chain):
        try:
            logger.info(
                f"Imagen call [{idx + 1}/{len(chain)}] model={model} "
                f"aspect={aspect_ratio} prompt_chars={len(prompt)}"
            )
            response = client.models.generate_images(
                model=model,
                prompt=prompt,
                config=config,
            )
            generated = getattr(response, "generated_images", None) or []
            if not generated:
                raise ImagenError(f"Empty generated_images from {model}")

            img_obj = generated[0]
            img_bytes = None
            inner = getattr(img_obj, "image", None)
            if inner is not None:
                img_bytes = getattr(inner, "image_bytes", None)
            if not img_bytes:
                raise ImagenError(f"No image_bytes in response from {model}")

            logger.info(
                f"Imagen OK model={model} bytes={len(img_bytes)} aspect={aspect_ratio}"
            )
            return ImagenResponse(
                image_bytes=img_bytes,
                model_used=model,
                aspect_ratio=aspect_ratio,
                backend="imagen",
            )

        except Exception as e:
            last_err = e
            has_next = idx < len(chain) - 1
            es = str(e)
            retryable = "429" in es or "RESOURCE_EXHAUSTED" in es or "503" in es
            if retryable and has_next:
                logger.warning(f"{model} retryable ({type(e).__name__}); falling through")
                continue
            if has_next:
                logger.warning(
                    f"{model} failed ({type(e).__name__}: {es[:200]}); trying next anyway"
                )
                continue
            raise ImagenError(
                f"All {len(chain)} Imagen models failed; last on {model}: {e}"
            ) from e

    raise ImagenError(f"Chain exhausted unexpectedly. Last: {last_err}")
