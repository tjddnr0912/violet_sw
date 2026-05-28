"""
Cloudinary uploader for blog illustration images
------------------------------------------------
Takes local image bytes (typically from `shared.image_generator.generate_image`)
and uploads to Cloudinary CDN, returning a public secure_url that can be
embedded in Blogger HTML as `<img src="...">`.

Setup (one-time, user):
    1. Sign up at https://cloudinary.com (free tier 25GB storage + 25GB/month bandwidth)
    2. Get credentials from Dashboard > "Product Environment Credentials"
    3. Add to ~/.zshenv:
         export CLOUDINARY_CLOUD_NAME='...'
         export CLOUDINARY_API_KEY='...'
         export CLOUDINARY_API_SECRET='...'
    4. pip install cloudinary
       (in 006_auto_bot/001_code/.venv)

Why Cloudinary:
    - CDN dedicated to images → hotlink stability over Google Drive
    - Auto webp/resize → mobile blog readability
    - Free tier sufficient for bot scale (~500 images/month)
    - Per-folder organization keeps run-id grouping

The output URL is a permanent, public, hot-linkable HTTPS URL.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


DEFAULT_FOLDER = os.getenv("CLOUDINARY_FOLDER", "006_auto_bot")
DEFAULT_FORMAT = os.getenv("CLOUDINARY_FORMAT", "webp")  # webp is ~30% smaller than png
DEFAULT_QUALITY = os.getenv("CLOUDINARY_QUALITY", "auto:good")


class CloudinaryError(RuntimeError):
    """Raised when Cloudinary upload fails."""


@dataclass
class UploadResult:
    secure_url: str          # https://res.cloudinary.com/...
    public_id: str           # Cloudinary internal ID (for delete)
    width: int
    height: int
    bytes: int
    format: str


def _configure_once():
    """Lazy-configure Cloudinary on first use. Reads env vars."""
    import cloudinary

    if not cloudinary.config().cloud_name:
        name = os.getenv("CLOUDINARY_CLOUD_NAME")
        key = os.getenv("CLOUDINARY_API_KEY")
        secret = os.getenv("CLOUDINARY_API_SECRET")
        if not all([name, key, secret]):
            missing = [k for k, v in [
                ("CLOUDINARY_CLOUD_NAME", name),
                ("CLOUDINARY_API_KEY", key),
                ("CLOUDINARY_API_SECRET", secret),
            ] if not v]
            raise CloudinaryError(
                f"Cloudinary credentials missing: {missing}. "
                f"Set in ~/.zshenv (see shared/image_uploader.py docstring)."
            )
        cloudinary.config(
            cloud_name=name,
            api_key=key,
            api_secret=secret,
            secure=True,  # HTTPS URLs
        )


def upload_to_cdn(
    image_bytes: bytes,
    public_id: str,
    *,
    folder: str = DEFAULT_FOLDER,
    format: str = DEFAULT_FORMAT,
    quality: str = DEFAULT_QUALITY,
    overwrite: bool = False,
) -> UploadResult:
    """Upload raw image bytes to Cloudinary and return public URL.

    Args:
        image_bytes: raw PNG/JPG bytes (typically from Imagen).
        public_id: stable identifier within the folder (e.g. run_id_1).
            Cloudinary supports nesting via slashes, but `folder=` param is
            preferred for organization.
        folder: top-level Cloudinary folder. Default '006_auto_bot'.
            Per-bot subfolders recommended (e.g. '006_auto_bot/news/2026-05-28').
        format: 'webp' (recommended) | 'png' | 'jpg'. Cloudinary auto-converts.
        quality: Cloudinary quality string. 'auto:good' is the sweet spot.
        overwrite: if False (default), Cloudinary rejects duplicate public_id.
            Set True for re-uploads (e.g. content edits).

    Returns:
        UploadResult with secure_url ready to embed in HTML.

    Raises:
        CloudinaryError on auth/network/quota failure.
    """
    import cloudinary.uploader

    _configure_once()

    if not image_bytes:
        raise CloudinaryError("Empty image_bytes")

    try:
        logger.info(
            f"Cloudinary upload bytes={len(image_bytes)} "
            f"folder={folder} public_id={public_id} format={format}"
        )
        result = cloudinary.uploader.upload(
            image_bytes,
            public_id=public_id,
            folder=folder,
            format=format,
            quality=quality,
            overwrite=overwrite,
            resource_type="image",
        )
    except Exception as e:
        raise CloudinaryError(f"Cloudinary upload failed: {e}") from e

    secure_url = result.get("secure_url")
    if not secure_url:
        raise CloudinaryError(f"Cloudinary returned no secure_url: {result}")

    upload_result = UploadResult(
        secure_url=secure_url,
        public_id=result.get("public_id", public_id),
        width=int(result.get("width", 0)),
        height=int(result.get("height", 0)),
        bytes=int(result.get("bytes", len(image_bytes))),
        format=result.get("format", format),
    )
    logger.info(
        f"Cloudinary OK url={secure_url[:80]}... "
        f"{upload_result.width}x{upload_result.height} {upload_result.bytes}B"
    )
    return upload_result


def delete_from_cdn(public_id: str, folder: str = DEFAULT_FOLDER) -> bool:
    """Delete a previously-uploaded image. Returns True on success."""
    import cloudinary.uploader

    _configure_once()
    full_id = f"{folder}/{public_id}" if folder and not public_id.startswith(folder) else public_id
    try:
        result = cloudinary.uploader.destroy(full_id, resource_type="image")
        ok = result.get("result") == "ok"
        logger.info(f"Cloudinary delete {full_id} → {result.get('result')}")
        return ok
    except Exception as e:
        logger.warning(f"Cloudinary delete failed: {e}")
        return False
