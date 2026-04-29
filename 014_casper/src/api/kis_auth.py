"""KIS API authentication and token management.

Handles OAuth2 token issuance and automatic refresh.
"""

import json
import logging
import os
import time
from typing import Optional

import requests

logger = logging.getLogger("casper")

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "config", "token.json")


class KISAuth:
    """KIS API authentication manager."""

    # Token-issuance backoff schedule (seconds). KIS rate-limits tokenP at
    # roughly one call per minute per app; sustained violations escalate to
    # multi-hour 403 (EGW00103) lockouts. A failed request must therefore
    # gate subsequent attempts, otherwise the bot's scan loop walks straight
    # into a punitive cooldown.
    _BACKOFF_SCHEDULE = (60, 300, 900, 1800, 3600)  # 1m → 5m → 15m → 30m → 1h

    def __init__(self, app_key: str, app_secret: str, base_url: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url
        self.is_virtual = "openapivts" in base_url
        self._token: Optional[str] = None
        self._token_expires: float = 0
        self._failure_count: int = 0
        self._next_retry_at: float = 0

    @property
    def token(self) -> str:
        """Get valid access token, refreshing if needed.

        When refresh is gated by backoff and no valid cached token remains,
        return an empty string and log CRITICAL so the operator sees the
        cascade root cause rather than a stream of opaque KIS 401s. KIS
        rejects empty Bearer headers cleanly, so the cascade fails fast.
        """
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        # Try loading from file
        cached = self._load_cached_token()
        if cached:
            self._token = cached["token"]
            self._token_expires = cached["expires"]
            if time.time() < self._token_expires - 60:
                logger.debug("KIS Auth: Using cached token")
                return self._token

        # Request new token (may be gated by backoff)
        self._request_new_token()

        # Verify we have a valid token after the refresh attempt; if not
        # (backoff blocked the request), surface the failure explicitly.
        if not self._token or time.time() >= self._token_expires - 60:
            if self._next_retry_at > time.time():
                wait = self._next_retry_at - time.time()
                logger.critical(
                    f"KIS Auth: No valid token; in backoff for {wait:.0f}s. "
                    f"All KIS API calls will fail until backoff clears."
                )
            return ""
        return self._token

    @property
    def headers(self) -> dict:
        """Standard KIS API request headers."""
        return {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }

    def _request_new_token(self) -> None:
        """Request a new OAuth2 token from KIS, gated by backoff after failures."""
        now = time.time()
        if now < self._next_retry_at:
            wait = self._next_retry_at - now
            logger.warning(
                f"KIS Auth: Skipping token request, in backoff for {wait:.0f}s "
                f"(consecutive failures: {self._failure_count})"
            )
            return

        url = f"{self.base_url}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        try:
            resp = requests.post(url, json=body, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            token = data.get("access_token", "")
            if not token:
                logger.error("KIS Auth: Empty access_token in response")
                self._note_failure()
                return
            self._token = token
            # Token valid for ~24h, set expiry to 23h
            self._token_expires = time.time() + 23 * 3600
            self._save_cached_token()
            self._failure_count = 0
            self._next_retry_at = 0
            logger.info("KIS Auth: New token acquired")
        except Exception as e:
            logger.error(f"KIS Auth: Token request failed: {e}")
            self._note_failure()

    def _note_failure(self) -> None:
        """Record a token-issuance failure and schedule the next allowed retry."""
        self._failure_count += 1
        idx = min(self._failure_count - 1, len(self._BACKOFF_SCHEDULE) - 1)
        delay = self._BACKOFF_SCHEDULE[idx]
        self._next_retry_at = time.time() + delay
        logger.warning(
            f"KIS Auth: Backing off {delay}s before next token attempt "
            f"(failure #{self._failure_count})"
        )

    def _load_cached_token(self) -> Optional[dict]:
        """Load token from cache file."""
        if not os.path.exists(TOKEN_FILE):
            return None
        try:
            with open(TOKEN_FILE, "r") as f:
                data = json.load(f)
            # Reject cached token if environment mismatch (live vs paper)
            if data.get("is_virtual") != self.is_virtual:
                logger.info("KIS Auth: Token cache env mismatch, requesting new token")
                return None
            return data
        except (json.JSONDecodeError, IOError):
            return None

    def _save_cached_token(self) -> None:
        """Save token to cache file."""
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        try:
            with open(TOKEN_FILE, "w") as f:
                json.dump({
                    "token": self._token,
                    "expires": self._token_expires,
                    "is_virtual": self.is_virtual,
                }, f)
            os.chmod(TOKEN_FILE, 0o600)
        except IOError as e:
            logger.error(f"KIS Auth: Token save failed: {e}")
