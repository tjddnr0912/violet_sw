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

    def __init__(self, app_key: str, app_secret: str, base_url: str):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url
        self.is_virtual = "openapivts" in base_url
        self._token: Optional[str] = None
        self._token_expires: float = 0

    @property
    def token(self) -> str:
        """Get valid access token, refreshing if needed."""
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

        # Request new token
        self._request_new_token()
        return self._token or ""

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
        """Request a new OAuth2 token from KIS."""
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
                return
            self._token = token
            # Token valid for ~24h, set expiry to 23h
            self._token_expires = time.time() + 23 * 3600
            self._save_cached_token()
            logger.info("KIS Auth: New token acquired")
        except Exception as e:
            logger.error(f"KIS Auth: Token request failed: {e}")

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
