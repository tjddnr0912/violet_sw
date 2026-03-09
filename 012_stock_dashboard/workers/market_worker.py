"""Market data worker: indices, commodities, FX, global markets."""

import asyncio
import logging

from workers.base import BaseWorker
from data_sources.yfinance_adapter import YFinanceAdapter
from data_sources.market_calendar import is_us_market_hours
from config import (
    TIER1_TICKERS, TIER2_TICKERS, EU_TICKERS, ASIA_TICKERS,
    TIER1_INTERVAL, TIER2_INTERVAL, OFF_HOURS_INTERVAL,
    TICKER_TO_TILE, TOP_MOVERS_TICKERS,
)

logger = logging.getLogger(__name__)


class MarketWorker(BaseWorker):
    def __init__(self, data_store):
        super().__init__(data_store, TIER1_INTERVAL)
        self.adapter = YFinanceAdapter()
        self._tasks: list[asyncio.Task] = []

    async def run(self):
        """Start tier1, tier2, and global loops as separate tasks."""
        self._tasks = [
            asyncio.create_task(self._tier1_loop()),
            asyncio.create_task(self._tier2_loop()),
            asyncio.create_task(self._global_loop()),
            asyncio.create_task(self._movers_loop()),
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _tier1_loop(self):
        """30s: S&P 500, NASDAQ, Dow, Bitcoin."""
        while self._running:
            try:
                interval = TIER1_INTERVAL if is_us_market_hours() else OFF_HOURS_INTERVAL
                # Fetch indices and crypto separately (date alignment differs)
                index_tickers = ["^GSPC", "^IXIC", "^DJI"]
                crypto_tickers = ["BTC-USD"]

                idx_quotes, crypto_quotes = await asyncio.gather(
                    self.adapter.fetch_quotes(index_tickers, ttl=interval * 0.8),
                    self.adapter.fetch_quotes(crypto_tickers, ttl=interval * 0.8),
                )
                quotes = {**idx_quotes, **crypto_quotes}

                for ticker, data in quotes.items():
                    tile_id = TICKER_TO_TILE.get(ticker)
                    if tile_id:
                        # Add sparkline for Bitcoin numeric tile
                        if ticker == "BTC-USD":
                            sparkline = await self.adapter.fetch_intraday(ticker, period="1d", interval="15m")
                            if sparkline:
                                data = {**data, "sparkline": [p["value"] for p in sparkline]}
                        await self.data_store.update(tile_id, data)

                # Fetch intraday for chart tiles
                for ticker in index_tickers:
                    tile_id = TICKER_TO_TILE.get(ticker)
                    if tile_id:
                        intraday = await self.adapter.fetch_intraday(ticker)
                        if intraday:
                            await self.data_store.update(f"{tile_id}_chart", {
                                "points": intraday,
                                **quotes.get(ticker, {}),
                            })
            except Exception as e:
                logger.error(f"Tier1 error: {e}")
            await asyncio.sleep(TIER1_INTERVAL if is_us_market_hours() else OFF_HOURS_INTERVAL)

    async def _tier2_loop(self):
        """60s: VIX, 10Y, DXY, Gold, Oil, FX + sparkline data."""
        await asyncio.sleep(5)  # stagger start
        while self._running:
            try:
                interval = TIER2_INTERVAL if is_us_market_hours() else OFF_HOURS_INTERVAL
                quotes = await self.adapter.fetch_quotes(TIER2_TICKERS, ttl=interval * 0.8)

                # Fetch sparkline data for numeric tiles
                spark_tickers = ["^VIX", "^TNX", "DX-Y.NYB", "GC=F", "CL=F", "BTC-USD"]
                for ticker in spark_tickers:
                    tile_id = TICKER_TO_TILE.get(ticker)
                    if not tile_id:
                        continue
                    sparkline = await self.adapter.fetch_intraday(ticker, period="1d", interval="15m")
                    quote = quotes.get(ticker, {})
                    tile_data = {**quote}
                    if sparkline:
                        tile_data["sparkline"] = [p["value"] for p in sparkline]
                    await self.data_store.update(tile_id, tile_data)

                # Update remaining tier2 tickers without sparkline (FX)
                for ticker in TIER2_TICKERS:
                    if ticker in spark_tickers:
                        continue
                    tile_id = TICKER_TO_TILE.get(ticker)
                    if tile_id and ticker in quotes:
                        await self.data_store.update(tile_id, quotes[ticker])

                # FX tile aggregation
                fx_data = {}
                fx_map = {"EURUSD=X": "EUR/USD", "JPY=X": "USD/JPY", "KRW=X": "USD/KRW"}
                for ticker, label in fx_map.items():
                    if ticker in quotes:
                        fx_data[label] = quotes[ticker]
                if fx_data:
                    await self.data_store.update("fx", {"pairs": fx_data})

            except Exception as e:
                logger.error(f"Tier2 error: {e}")
            await asyncio.sleep(TIER2_INTERVAL if is_us_market_hours() else OFF_HOURS_INTERVAL)

    async def _global_loop(self):
        """60s: EU + Asia indices."""
        await asyncio.sleep(10)  # stagger start
        while self._running:
            try:
                all_global = EU_TICKERS + ASIA_TICKERS
                quotes = await self.adapter.fetch_quotes(all_global, ttl=50)

                eu_data = {}
                eu_names = {"^FTSE": "FTSE 100", "^GDAXI": "DAX", "^FCHI": "CAC 40"}
                for t in EU_TICKERS:
                    if t in quotes:
                        eu_data[eu_names.get(t, t)] = quotes[t]
                if eu_data:
                    await self.data_store.update("europe", {"indices": eu_data})

                asia_data = {}
                asia_names = {"^N225": "Nikkei", "000001.SS": "Shanghai", "^KS11": "KOSPI", "^HSI": "Hang Seng"}
                for t in ASIA_TICKERS:
                    if t in quotes:
                        asia_data[asia_names.get(t, t)] = quotes[t]
                if asia_data:
                    await self.data_store.update("asia", {"indices": asia_data})

            except Exception as e:
                logger.error(f"Global loop error: {e}")
            await asyncio.sleep(TIER2_INTERVAL if is_us_market_hours() else OFF_HOURS_INTERVAL)

    async def _movers_loop(self):
        """120s: Top movers from S&P 500 sample."""
        await asyncio.sleep(15)  # stagger start
        while self._running:
            try:
                quotes = await self.adapter.fetch_quotes(TOP_MOVERS_TICKERS, ttl=100)
                if quotes:
                    sorted_by_change = sorted(
                        [(t, d) for t, d in quotes.items() if "change_pct" in d],
                        key=lambda x: x[1]["change_pct"],
                        reverse=True,
                    )
                    gainers = [{"symbol": t, **d} for t, d in sorted_by_change[:5]]
                    losers = [{"symbol": t, **d} for t, d in sorted_by_change[-5:]]
                    await self.data_store.update("movers", {
                        "gainers": gainers,
                        "losers": losers,
                    })
            except Exception as e:
                logger.error(f"Movers loop error: {e}")
            await asyncio.sleep(120)

    def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()

    async def tick(self):
        pass  # Not used; run() manages its own loops
