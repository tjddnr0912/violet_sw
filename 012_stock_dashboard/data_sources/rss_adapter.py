"""RSS feed parser with multi-language support."""

import asyncio
import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import aiohttp
import feedparser

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    link: str
    source: str
    language: str
    published: float  # unix timestamp
    summary: str = ""
    article_id: str = ""

    def __post_init__(self):
        if not self.article_id:
            self.article_id = hashlib.md5(self.link.encode()).hexdigest()[:12]


class RSSAdapter:
    def __init__(self):
        self._seen_ids: set[str] = set()

    async def fetch_feeds(self, sources: list[dict]) -> list[Article]:
        """Fetch articles from multiple RSS sources in parallel."""
        tasks = [self._fetch_single(s) for s in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        articles = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"RSS fetch error: {result}")
                continue
            articles.extend(result)

        # Deduplicate by article_id
        seen = set()
        unique = []
        for a in articles:
            if a.article_id not in seen:
                seen.add(a.article_id)
                unique.append(a)

        # Filter: last 6 hours only
        cutoff = time.time() - 6 * 3600
        recent = [a for a in unique if a.published > cutoff]

        # Sort by published time (newest first)
        recent.sort(key=lambda a: a.published, reverse=True)

        return recent

    async def _fetch_single(self, source: dict) -> list[Article]:
        url = source["url"]
        src_name = source["source"]
        lang = source["lang"]

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (compatible; StockDashboard/1.0)"
                }
                async with session.get(url, headers=headers,
                                       timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"RSS {src_name} HTTP {resp.status}")
                        return []
                    text = await resp.text()

            feed = feedparser.parse(text)
            if feed.bozo and not feed.entries:
                logger.warning(f"RSS {src_name} bozo error: {feed.bozo_exception}")
                return []

            articles = []
            for entry in feed.entries[:15]:  # Max 15 per source
                pub_time = self._parse_time(entry)
                articles.append(Article(
                    title=entry.get("title", "").strip(),
                    link=entry.get("link", ""),
                    source=src_name,
                    language=lang,
                    published=pub_time,
                    summary=entry.get("summary", "")[:200],
                ))

            return articles

        except Exception as e:
            logger.error(f"RSS {src_name} error: {e}")
            return []

    def _parse_time(self, entry) -> float:
        """Parse entry published time to unix timestamp."""
        for field_name in ("published_parsed", "updated_parsed"):
            parsed = entry.get(field_name)
            if parsed:
                try:
                    from calendar import timegm
                    return float(timegm(parsed))
                except Exception:
                    pass
        return time.time()
