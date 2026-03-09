"""Finnhub REST adapter for news and quotes."""

import asyncio
import logging
import time

import aiohttp

from config import FINNHUB_API_KEY

logger = logging.getLogger(__name__)


class FinnhubAdapter:
    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self._semaphore = asyncio.Semaphore(10)  # max concurrent requests
        self._call_times: list[float] = []

    @property
    def enabled(self) -> bool:
        return bool(FINNHUB_API_KEY)

    async def fetch_news(self, category: str = "general") -> list[dict]:
        """Fetch latest news from Finnhub."""
        if not self.enabled:
            return []

        await self._rate_limit()
        try:
            async with aiohttp.ClientSession() as session:
                params = {"category": category, "token": FINNHUB_API_KEY}
                async with session.get(
                    f"{self.BASE_URL}/news",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Finnhub news HTTP {resp.status}")
                        return []
                    data = await resp.json()

            return [
                {
                    "title": item.get("headline", ""),
                    "link": item.get("url", ""),
                    "source": item.get("source", "Finnhub"),
                    "language": "EN",
                    "published": item.get("datetime", time.time()),
                    "summary": item.get("summary", "")[:200],
                }
                for item in data[:15]
            ]

        except Exception as e:
            logger.error(f"Finnhub news error: {e}")
            return []

    async def fetch_quote(self, symbol: str) -> dict | None:
        """Fetch real-time quote for a US stock."""
        if not self.enabled:
            return None

        await self._rate_limit()
        try:
            async with aiohttp.ClientSession() as session:
                params = {"symbol": symbol, "token": FINNHUB_API_KEY}
                async with session.get(
                    f"{self.BASE_URL}/quote",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

            if data.get("c", 0) == 0:
                return None

            return {
                "price": data["c"],
                "change": round(data["c"] - data["pc"], 2),
                "change_pct": round((data["c"] - data["pc"]) / data["pc"] * 100, 2) if data["pc"] else 0,
                "prev_close": data["pc"],
                "high": data["h"],
                "low": data["l"],
            }

        except Exception as e:
            logger.error(f"Finnhub quote error for {symbol}: {e}")
            return None

    async def _rate_limit(self):
        """60 calls/min limit."""
        async with self._semaphore:
            now = time.time()
            self._call_times = [t for t in self._call_times if now - t < 60]
            if len(self._call_times) >= 55:  # leave margin
                wait = 60 - (now - self._call_times[0])
                if wait > 0:
                    await asyncio.sleep(wait)
            self._call_times.append(time.time())
