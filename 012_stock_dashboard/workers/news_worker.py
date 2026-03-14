"""News worker: RSS + Finnhub collection, 2-phase display (instant title → async AI summary)."""

import asyncio
import logging

from workers.base import BaseWorker
from data_sources.rss_adapter import RSSAdapter
from data_sources.finnhub_adapter import FinnhubAdapter
from data_sources.ai_summarizer import AISummarizer
from tiles.dynamic_rotator import DynamicRotator
from config import RSS_SOURCES, TIER4_INTERVAL, BREAKING_KEYWORDS

logger = logging.getLogger(__name__)


class NewsWorker(BaseWorker):
    def __init__(self, data_store):
        super().__init__(data_store, TIER4_INTERVAL)
        self.rss = RSSAdapter()
        self.finnhub = FinnhubAdapter()
        self.summarizer = AISummarizer()
        self.rotator = DynamicRotator(data_store)
        self._enrich_task: asyncio.Task | None = None

    async def run(self):
        """Start news loop + rotation loop."""
        rotation_task = asyncio.create_task(self.rotator.rotation_loop())
        try:
            await super().run()
        finally:
            rotation_task.cancel()

    async def tick(self):
        # Phase A: Collect news and display immediately with original titles
        rss_articles = await self.rss.fetch_feeds(RSS_SOURCES)

        # Also fetch from Finnhub
        finnhub_news = await self.finnhub.fetch_news()
        for fn in finnhub_news:
            from data_sources.rss_adapter import Article
            rss_articles.append(Article(
                title=fn["title"],
                link=fn["link"],
                source=fn["source"],
                language=fn["language"],
                published=fn["published"],
                summary=fn.get("summary", ""),
            ))

        # Dedupe + sort by time
        seen_ids = set()
        unique = []
        for a in rss_articles:
            if a.article_id not in seen_ids:
                seen_ids.add(a.article_id)
                unique.append(a)
        unique.sort(key=lambda a: a.published, reverse=True)

        # Take top 15
        top_articles = unique[:15]

        if not top_articles:
            return

        # Check breaking keywords (1st filter)
        breaking_map = {}
        for article in top_articles:
            title_lower = article.title.lower()
            breaking_map[article.article_id] = any(kw.lower() in title_lower for kw in BREAKING_KEYWORDS)

        # Push to rotator immediately with original titles
        for article in top_articles:
            cached = self.summarizer.get_cached(article.article_id)
            is_breaking = breaking_map.get(article.article_id, False)
            news_item = {
                "article_id": article.article_id,
                "title": cached.summary if cached else article.title,
                "source": article.source,
                "language": article.language,
                "published": article.published,
                "impact": cached.impact if cached else ("high" if is_breaking else "unknown"),
                "market": cached.market if cached else "Global",
                "ai_ready": cached is not None,
            }
            self.rotator.push(news_item, breaking=is_breaking)

        # Phase B: AI enrichment disabled (Gemini free tier RPD too low)
        # To re-enable: uncomment below and ensure sufficient Gemini quota
        # if self._enrich_task and not self._enrich_task.done():
        #     self._enrich_task.cancel()
        # self._enrich_task = asyncio.create_task(
        #     self._enrich_articles(top_articles)
        # )

    async def _enrich_articles(self, articles):
        """Background task: summarize with Gemini, then update tiles.
        Korean articles skip Gemini (already in Korean) to save free tier quota.
        """
        try:
            # Korean articles: skip Gemini, cache directly with original title
            kr_articles = [a for a in articles if a.language == "KR" and not self.summarizer.get_cached(a.article_id)]
            for a in kr_articles:
                from data_sources.ai_summarizer import SummarizedArticle
                sa = SummarizedArticle(a.article_id, a.title, "low", "Asia")
                self.summarizer._cache[a.article_id] = sa
                self.rotator.enrich(a.article_id, {
                    "title": a.title,
                    "impact": "low",
                    "market": "Asia",
                    "ai_ready": True,
                })

            # Non-Korean articles: send to Gemini for translation
            batch = [
                {"id": a.article_id, "title": a.title, "source": a.source, "language": a.language}
                for a in articles
                if a.language != "KR" and not self.summarizer.get_cached(a.article_id)
            ]

            if not batch:
                return

            results = await self.summarizer.summarize_batch(batch)

            # Update rotator queue items with AI summaries
            for result in results:
                self.rotator.enrich(result.article_id, {
                    "title": result.summary,
                    "impact": result.impact,
                    "market": result.market,
                    "ai_ready": True,
                })

                # 2nd filter: AI impact="high" → promote to breaking
                if result.impact == "high":
                    self.rotator.promote_breaking(result.article_id)

        except Exception as e:
            logger.error(f"AI enrichment error: {e}")

    def stop(self):
        super().stop()
        if self._enrich_task:
            self._enrich_task.cancel()
