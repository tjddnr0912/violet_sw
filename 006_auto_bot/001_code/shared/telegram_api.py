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

    def send_message_with_inline_keyboard(
        self,
        text: str,
        inline_keyboard: List[List[Dict[str, str]]],
        parse_mode: Optional[str] = "HTML",
        disable_web_page_preview: bool = True,
        max_retries: int = 3
    ) -> Dict[str, Any]:
        """
        Send a message with inline keyboard buttons

        Args:
            text: Message text
            inline_keyboard: 2D array of button objects
                [[{"text": "Button 1", "callback_data": "data1"}, ...], ...]
            parse_mode: "HTML", "Markdown", or None
            disable_web_page_preview: Disable link previews
            max_retries: Maximum retry attempts

        Returns:
            API response dict with 'success', 'message_id' or 'error'
        """
        for attempt in range(max_retries):
            try:
                url = f"{self.api_base}/sendMessage"
                payload = {
                    "chat_id": self.chat_id,
                    "text": text,
                    "reply_markup": {"inline_keyboard": inline_keyboard},
                    "disable_web_page_preview": disable_web_page_preview
                }
                if parse_mode:
                    payload["parse_mode"] = parse_mode

                response = self.session.post(url, json=payload, timeout=30)
                result = response.json()

                if result.get("ok"):
                    logger.info("Telegram message with inline keyboard sent")
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
                return {"success": False, "error": "Request timeout"}

            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return {"success": False, "error": str(e)}

            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "Max retries exceeded"}

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False
    ) -> Dict[str, Any]:
        """
        Answer a callback query (button click response)

        Telegram requires response within 30 seconds, otherwise shows loading icon

        Args:
            callback_query_id: ID from callback_query update
            text: Optional notification text (toast message)
            show_alert: If True, show alert popup instead of toast

        Returns:
            API response dict with 'success' or 'error'
        """
        try:
            url = f"{self.api_base}/answerCallbackQuery"
            payload = {
                "callback_query_id": callback_query_id,
                "show_alert": show_alert
            }
            if text:
                payload["text"] = text

            response = self.session.post(url, json=payload, timeout=10)
            result = response.json()

            if result.get("ok"):
                return {"success": True}
            else:
                error_msg = result.get("description", "Unknown error")
                logger.error(f"answerCallbackQuery error: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Failed to answer callback query: {e}")
            return {"success": False, "error": str(e)}

    def edit_message_text(
        self,
        message_id: int,
        text: str,
        parse_mode: Optional[str] = "HTML",
        reply_markup: Optional[Dict] = None,
        disable_web_page_preview: bool = True
    ) -> Dict[str, Any]:
        """
        Edit text of a previously sent message

        Used to remove inline keyboard after selection or update status

        Args:
            message_id: ID of the message to edit
            text: New message text
            parse_mode: "HTML", "Markdown", or None
            reply_markup: Optional new inline keyboard (or omit to remove)
            disable_web_page_preview: Disable link previews

        Returns:
            API response dict with 'success' or 'error'
        """
        try:
            url = f"{self.api_base}/editMessageText"
            payload = {
                "chat_id": self.chat_id,
                "message_id": message_id,
                "text": text,
                "disable_web_page_preview": disable_web_page_preview
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if reply_markup:
                payload["reply_markup"] = reply_markup

            response = self.session.post(url, json=payload, timeout=30)
            result = response.json()

            if result.get("ok"):
                logger.info(f"Message {message_id} edited successfully")
                return {"success": True}
            else:
                error_msg = result.get("description", "Unknown error")
                logger.error(f"editMessageText error: {error_msg}")
                return {"success": False, "error": error_msg}

        except Exception as e:
            logger.error(f"Failed to edit message: {e}")
            return {"success": False, "error": str(e)}
