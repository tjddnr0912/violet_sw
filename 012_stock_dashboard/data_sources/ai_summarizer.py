"""Gemini AI news summarizer."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass

from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_BATCH_SIZE, GEMINI_TIMEOUT, GEMINI_RPM_LIMIT

logger = logging.getLogger(__name__)


@dataclass
class SummarizedArticle:
    article_id: str
    summary: str
    impact: str  # high, medium, low, unknown
    market: str  # US, EU, Asia, Global


class AISummarizer:
    def __init__(self):
        self._cache: dict[str, SummarizedArticle] = {}  # article_id -> result
        self._semaphore = asyncio.Semaphore(GEMINI_RPM_LIMIT)
        self._call_times: list[float] = []
        self._model = None

    def _init_model(self):
        if self._model is not None:
            return
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY not set, AI summarization disabled")
            return
        try:
            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            self._model = genai.GenerativeModel(GEMINI_MODEL)
        except Exception as e:
            logger.error(f"Gemini init error: {e}")

    def get_cached(self, article_id: str) -> SummarizedArticle | None:
        return self._cache.get(article_id)

    async def summarize_batch(self, articles: list[dict]) -> list[SummarizedArticle]:
        """Summarize a batch of articles using Gemini. Each article: {id, title, source, language}."""
        self._init_model()
        if not self._model:
            return [SummarizedArticle(a["id"], a["title"], "unknown", "Global") for a in articles]

        # Check cache
        uncached = [a for a in articles if a["id"] not in self._cache]
        results = [self._cache[a["id"]] for a in articles if a["id"] in self._cache]

        if not uncached:
            return results

        # Process in batches
        for i in range(0, len(uncached), GEMINI_BATCH_SIZE):
            batch = uncached[i:i + GEMINI_BATCH_SIZE]
            batch_results = await self._call_gemini(batch)
            results.extend(batch_results)

        return results

    async def _call_gemini(self, batch: list[dict]) -> list[SummarizedArticle]:
        """Call Gemini API for a batch of articles."""
        await self._rate_limit()

        articles_text = ""
        for idx, a in enumerate(batch, 1):
            articles_text += f"\n{idx}. [{a['source']}] ({a['language']}) {a['title']}"

        prompt = f"""다음 금융/경제 뉴스 제목들을 한국어로 번역하고 핵심 요약하세요.

규칙:
- 이미 한국어인 뉴스는 그대로 1줄 요약
- 영어/일본어/중국어 뉴스는 한국어로 자연스럽게 번역 후 1줄 요약
- 각 요약은 반드시 한국어, 40자 이내로 간결하게
- 설명 없이 JSON 배열만 반환

형식: [{{"id": 1, "summary": "한국어 1줄 요약", "impact": "high/medium/low", "market": "US/EU/Asia/Global"}}]

뉴스 목록:{articles_text}"""

        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self._sync_generate, prompt),
                timeout=GEMINI_TIMEOUT,
            )
            return self._parse_response(response, batch)
        except asyncio.TimeoutError:
            logger.warning("Gemini timeout, using fallback")
            return self._fallback(batch)
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return self._fallback(batch)

    def _sync_generate(self, prompt: str) -> str:
        response = self._model.generate_content(prompt)
        return response.text

    def _parse_response(self, text: str, batch: list[dict]) -> list[SummarizedArticle]:
        """Parse Gemini JSON response."""
        # Try to extract JSON from response
        json_str = text
        if "```" in text:
            parts = text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("["):
                    json_str = part
                    break

        try:
            items = json.loads(json_str)
        except json.JSONDecodeError:
            # Try to find JSON array in text
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    items = json.loads(text[start:end])
                except json.JSONDecodeError:
                    return self._fallback(batch)
            else:
                return self._fallback(batch)

        results = []
        for i, article in enumerate(batch):
            if i < len(items):
                item = items[i]
                summary = item.get("summary", article["title"])
                impact = item.get("impact", "low")
                market = item.get("market", "Global")
            else:
                summary = article["title"]
                impact = "unknown"
                market = "Global"

            sa = SummarizedArticle(article["id"], summary, impact, market)
            self._cache[article["id"]] = sa
            results.append(sa)

        return results

    def _fallback(self, batch: list[dict]) -> list[SummarizedArticle]:
        results = []
        for a in batch:
            sa = SummarizedArticle(a["id"], a["title"], "unknown", "Global")
            self._cache[a["id"]] = sa
            results.append(sa)
        return results

    async def _rate_limit(self):
        """Ensure max GEMINI_RPM_LIMIT calls per minute."""
        async with self._semaphore:
            now = time.time()
            self._call_times = [t for t in self._call_times if now - t < 60]
            if len(self._call_times) >= GEMINI_RPM_LIMIT:
                wait = 60 - (now - self._call_times[0])
                if wait > 0:
                    await asyncio.sleep(wait)
            self._call_times.append(time.time())
