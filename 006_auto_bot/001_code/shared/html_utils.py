#!/usr/bin/env python3
"""
HTML Utilities for Telegram
---------------------------
Common HTML processing functions for Telegram message formatting
"""

import re
from typing import Optional


class HtmlUtils:
    """HTML utility functions for Telegram messages"""

    # Telegram supported HTML tags
    SIMPLE_TAGS = ['b', 'i', 'u', 's', 'code', 'pre']

    @staticmethod
    def fix_unclosed_tags(text: str) -> str:
        """
        Fix unclosed HTML tags to prevent Telegram API parsing errors

        Args:
            text: HTML text to validate

        Returns:
            Text with properly closed HTML tags
        """
        # Handle simple tags (b, i, u, s, code, pre)
        for tag in HtmlUtils.SIMPLE_TAGS:
            open_pattern = f'<{tag}>'
            close_pattern = f'</{tag}>'

            open_count = text.lower().count(open_pattern)
            close_count = text.lower().count(close_pattern)

            # Add missing closing tags at the end
            if open_count > close_count:
                text += close_pattern * (open_count - close_count)
            # Remove orphan closing tags
            elif close_count > open_count:
                for _ in range(close_count - open_count):
                    text = re.sub(f'</{tag}>', '', text, count=1, flags=re.IGNORECASE)

        # Handle <a> tags separately (they have href attribute)
        open_a = len(re.findall(r'<a\s+href=', text, re.IGNORECASE))
        close_a = text.lower().count('</a>')

        if open_a > close_a:
            text += '</a>' * (open_a - close_a)
        elif close_a > open_a:
            for _ in range(close_a - open_a):
                text = re.sub(r'</a>', '', text, count=1, flags=re.IGNORECASE)

        return text

    @staticmethod
    def escape_for_telegram(text: str) -> str:
        """
        Escape special HTML characters for Telegram HTML mode

        Args:
            text: Text to escape

        Returns:
            Escaped text safe for Telegram HTML parsing
        """
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        return text

    @staticmethod
    def markdown_to_telegram_html(markdown_text: str) -> str:
        """
        Convert markdown to Telegram HTML format

        Args:
            markdown_text: Original markdown content

        Returns:
            Telegram-friendly HTML text
        """
        text = markdown_text

        # Escape HTML special characters first
        text = HtmlUtils.escape_for_telegram(text)

        # Remove image links ![alt](url)
        text = re.sub(r'!\[.*?\]\(.*?\)', '', text)

        # Convert markdown links [text](url) to HTML
        text = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'<a href="\2">\1</a>', text)

        # Convert bold **text** to <b>text</b>
        text = re.sub(r'\*\*([^\*]+)\*\*', r'<b>\1</b>', text)

        # Convert italic *text* to <i>text</i> (but not ** which is bold)
        text = re.sub(r'(?<!\*)\*([^\*]+)\*(?!\*)', r'<i>\1</i>', text)

        # Convert headers # to bold
        text = re.sub(r'^#{1,6}\s+(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

        # Convert code blocks ```code``` to <code>code</code>
        text = re.sub(r'```[^\n]*\n(.*?)```', r'<code>\1</code>', text, flags=re.DOTALL)

        # Convert inline code `code` to <code>code</code>
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

        # Clean up excessive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Remove horizontal rules
        text = re.sub(r'^-{3,}$', '\u2500' * 20, text, flags=re.MULTILINE)

        # Fix unclosed tags
        text = HtmlUtils.fix_unclosed_tags(text)

        return text.strip()

    @staticmethod
    def truncate_with_tag_fix(text: str, max_length: int = 4000, suffix: str = "\n\n... (내용이 길어 일부 생략)") -> str:
        """
        Truncate text to max_length and fix any broken HTML tags

        Args:
            text: Text to truncate
            max_length: Maximum length (default 4000 for Telegram)
            suffix: Suffix to add when truncated

        Returns:
            Truncated text with fixed HTML tags
        """
        if len(text) <= max_length:
            return text

        truncated = text[:max_length - len(suffix)] + suffix
        return HtmlUtils.fix_unclosed_tags(truncated)
