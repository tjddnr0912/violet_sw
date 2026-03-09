"""Sentiment worker: Fear & Greed, Market Breadth."""

import logging

from workers.base import BaseWorker
from data_sources.fear_greed import fetch_fear_greed
from data_sources.yfinance_adapter import YFinanceAdapter
from config import TIER5_INTERVAL

logger = logging.getLogger(__name__)


class SentimentWorker(BaseWorker):
    def __init__(self, data_store):
        super().__init__(data_store, TIER5_INTERVAL)
        self.adapter = YFinanceAdapter()

    async def tick(self):
        # Fear & Greed
        fg = await fetch_fear_greed()
        await self.data_store.update("feargreed", fg)

        # Market Breadth: use sector ETFs as proxy
        # Advance/Decline approximation from sector data
        try:
            from config import SECTOR_ETFS
            tickers = list(SECTOR_ETFS.keys())
            quotes = await self.adapter.fetch_quotes(tickers, ttl=300)
            advancing = sum(1 for q in quotes.values() if q.get("change_pct", 0) > 0)
            declining = sum(1 for q in quotes.values() if q.get("change_pct", 0) < 0)
            unchanged = len(quotes) - advancing - declining

            await self.data_store.update("breadth", {
                "advancing": advancing,
                "declining": declining,
                "unchanged": unchanged,
                "total": len(quotes),
                "ratio": round(advancing / max(declining, 1), 2),
            })
        except Exception as e:
            logger.error(f"Market breadth error: {e}")
