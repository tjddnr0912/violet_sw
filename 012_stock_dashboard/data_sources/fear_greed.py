"""CNN Fear & Greed Index scraper."""

import logging
import aiohttp

logger = logging.getLogger(__name__)

FEAR_GREED_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://edition.cnn.com/",
}

_last_result = None
_session: aiohttp.ClientSession | None = None


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(headers=HEADERS)
    return _session


async def fetch_fear_greed() -> dict:
    """Fetch CNN Fear & Greed index. Returns {"score": int, "rating": str}."""
    global _last_result
    try:
        session = await _get_session()
        async with session.get(FEAR_GREED_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    logger.warning(f"Fear & Greed HTTP {resp.status}")
                    return _last_result or {"score": 50, "rating": "neutral"}
                data = await resp.json()

        score = int(data.get("fear_and_greed", {}).get("score", 50))
        rating = data.get("fear_and_greed", {}).get("rating", "neutral")

        _last_result = {"score": score, "rating": rating}
        return _last_result

    except Exception as e:
        logger.error(f"Fear & Greed error: {e}")
        return _last_result or {"score": 50, "rating": "neutral"}
