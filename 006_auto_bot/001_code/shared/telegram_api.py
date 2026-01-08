#!/usr/bin/env python3
"""
Telegram API Client
-------------------
Base Telegram API client for sending messages and receiving updates
"""

import logging
import time
from typing import Optional, List, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class TelegramClient:
    """Base Telegram API client with connection pooling and retry logic"""

    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize Telegram client

        Args:
            bot_token: Telegram Bot API token (from @BotFather)
            chat_id: Target chat/channel ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_base = f"https://api.telegram.org/bot{bot_token}"
        self.consecutive_failures = 0

        # Session with connection pooling and retry
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )
        self.session.mount("https://", adapter)

    def send_message(
        self,
        text: str,
        parse_mode: Optional[str] = "HTML",
        disable_web_page_preview: bool = True,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Send a text message via Telegram

        Args:
            text: Message text (supports HTML/Markdown)
            parse_mode: "HTML", "Markdown", or None for plain text
            disable_web_page_preview: Disable link previews
            max_retries: Maximum retry attempts

        Returns:
            API response dict with 'success' and 'message_id' or 'error'
        """
        for attempt in range(max_retries):
            try:
                url = f"{self.api_base}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "disable_web_page_preview": disable_web_page_preview
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode

                response = self.session.post(url, json=payload, timeout=30)
                result = response.json()

                if result.get("ok"):
                    logger.info("Telegram message sent successfully")
                    return {"success": True, "message_id": result["result"]["message_id"]}
                else:
                    error_msg = result.get("description", "Unknown error")
                    logger.error(f"Telegram API error: {error_msg}")
                    return {"success": False, "error": error_msg}

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    logger.warning(f"Telegram timeout, retrying ({attempt + 1}/{max_retries})...")
                    time.sleep(2 ** attempt)
                    continue
                logger.error("Telegram API timeout after all retries")
                return {"success": False, "error": "Request timeout"}

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Request error, retrying ({attempt + 1}/{max_retries}): {e}")
                    time.sleep(2 ** attempt)
                    continue
                logger.error(f"Failed to send Telegram message: {e}")
                return {"success": False, "error": str(e)}

            except Exception as e:
                logger.error(f"Unexpected error sending message: {e}")
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "Max retries exceeded"}

    def get_updates(
        self,
        offset: Optional[int] = None,
        timeout: int = 30,
        max_retries: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Get new messages using long polling

        Args:
            offset: Update offset to skip processed updates
            timeout: Long polling timeout in seconds
            max_retries: Maximum retry attempts

        Returns:
            List of update objects
        """
        for attempt in range(max_retries):
            try:
                url = f"{self.api_base}/getUpdates"
                params = {"timeout": timeout}
                if offset:
                    params["offset"] = offset

                response = self.session.get(url, params=params, timeout=timeout + 5)
                result = response.json()

                if result.get("ok"):
                    if self.consecutive_failures > 0:
                        logger.info(f"Network recovered (previous failures: {self.consecutive_failures})")
                        self.consecutive_failures = 0
                    return result.get("result", [])
                return []

            except (ConnectionResetError, ConnectionError, ConnectionAbortedError) as e:
                if attempt == 0:
                    logger.debug(f"Connection reset (normal for long polling): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                self.consecutive_failures += 1
                return []

            except requests.exceptions.Timeout:
                # Long polling timeout is normal
                return []

            except requests.exceptions.RequestException as e:
                self.consecutive_failures += 1
                base_wait = min(2 ** attempt, 8)
                extra_wait = min(self.consecutive_failures * 2, 30)
                wait_time = base_wait + extra_wait

                if self.consecutive_failures <= 3:
                    logger.warning(f"Network error (attempt {attempt + 1}/{max_retries}): {e}")
                elif self.consecutive_failures % 10 == 0:
                    logger.warning(f"Network instability continues ({self.consecutive_failures} failures)")

                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                return []

            except Exception as e:
                logger.error(f"Failed to get updates: {e}")
                self.consecutive_failures += 1
                return []

        return []

    def test_connection(self) -> bool:
        """
        Test if bot token and chat_id are valid

        Returns:
            True if connection successful, False otherwise
        """
        try:
            url = f"{self.api_base}/getMe"
            response = self.session.get(url, timeout=10)
            result = response.json()

            if not result.get("ok"):
                logger.error(f"Invalid bot token: {result.get('description')}")
                return False

            bot_name = result["result"]["username"]
            logger.info(f"Telegram bot connected: @{bot_name}")
            return True

        except Exception as e:
            logger.error(f"Telegram connection test failed: {e}")
            return False
