"""Sector heatmap worker: S&P 500 sector ETFs."""

import logging

from workers.base import BaseWorker
from data_sources.yfinance_adapter import YFinanceAdapter
from config import SECTOR_ETFS, TIER3_INTERVAL

logger = logging.getLogger(__name__)


class SectorWorker(BaseWorker):
    def __init__(self, data_store):
        super().__init__(data_store, TIER3_INTERVAL)
        self.adapter = YFinanceAdapter()

    async def tick(self):
        tickers = list(SECTOR_ETFS.keys())
        quotes = await self.adapter.fetch_quotes(tickers, ttl=100)

        sectors = []
        for ticker, name in SECTOR_ETFS.items():
            if ticker in quotes:
                sectors.append({
                    "ticker": ticker,
                    "name": name,
                    "change_pct": quotes[ticker].get("change_pct", 0),
                    "price": quotes[ticker].get("price", 0),
                })

        if sectors:
            await self.data_store.update("sector", {"sectors": sectors})
