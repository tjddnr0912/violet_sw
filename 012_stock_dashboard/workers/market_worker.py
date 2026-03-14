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
    YIELD_TICKERS, COMMODITY_TICKERS,
    WATCHLIST_FIXED_TICKERS, WATCHLIST_DYNAMIC_COUNT,
    WATCHLIST_DYNAMIC_REFRESH, INDEX_FUTURES_MAP,
)

logger = logging.getLogger(__name__)


class MarketWorker(BaseWorker):
    def __init__(self, data_store, adapter=None):
        super().__init__(data_store, TIER1_INTERVAL)
        self.adapter = adapter or YFinanceAdapter()
        self._tasks: list[asyncio.Task] = []
        self._movers_quotes: dict = {}  # shared with watchlist for dynamic picks

    async def run(self):
        """Start tier1, tier2, global, movers, extra tiles, and watchlist loops."""
        self._tasks = [
            asyncio.create_task(self._tier1_loop()),
            asyncio.create_task(self._tier2_loop()),
            asyncio.create_task(self._global_loop()),
            asyncio.create_task(self._movers_loop()),
            asyncio.create_task(self._extra_tiles_loop()),
            asyncio.create_task(self._watchlist_loop()),
        ]
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _tier1_loop(self):
        """30s: S&P 500, NASDAQ, Dow, Bitcoin. Uses futures (ES/NQ/YM) when market closed."""
        # Reverse map: futures ticker -> tile_id
        futures_to_tile = {v: TICKER_TO_TILE[k] for k, v in INDEX_FUTURES_MAP.items()}

        while self._running:
            try:
                us_open = is_us_market_hours()
                interval = TIER1_INTERVAL if us_open else OFF_HOURS_INTERVAL

                # Choose index or futures tickers based on market hours
                if us_open:
                    idx_tickers = ["^GSPC", "^IXIC", "^DJI"]
                    source = "index"
                else:
                    idx_tickers = list(INDEX_FUTURES_MAP.values())  # ES=F, NQ=F, YM=F
                    source = "futures"

                crypto_tickers = ["BTC-USD"]
                idx_quotes, crypto_quotes = await asyncio.gather(
                    self.adapter.fetch_quotes(idx_tickers, ttl=interval * 0.8),
                    self.adapter.fetch_quotes(crypto_tickers, ttl=interval * 0.8),
                )
                quotes = {**idx_quotes, **crypto_quotes}

                for ticker, data in quotes.items():
                    if source == "futures" and ticker in futures_to_tile:
                        tile_id = futures_to_tile[ticker]
                    else:
                        tile_id = TICKER_TO_TILE.get(ticker)
                    if not tile_id:
                        continue

                    tile_data = {**data, "source": source}
                    if ticker == "BTC-USD":
                        sparkline = await self.adapter.fetch_intraday(ticker, period="1d", interval="15m")
                        if sparkline:
                            tile_data["sparkline"] = [p["value"] for p in sparkline]
                    await self.data_store.update(tile_id, tile_data)

                # Fetch intraday for chart tiles
                for ticker in idx_tickers:
                    if source == "futures":
                        tile_id = futures_to_tile.get(ticker)
                    else:
                        tile_id = TICKER_TO_TILE.get(ticker)
                    if tile_id:
                        intraday = await self.adapter.fetch_intraday(ticker)
                        if intraday:
                            await self.data_store.update(f"{tile_id}_chart", {
                                "points": intraday,
                                **quotes.get(ticker, {}),
                                "source": source,
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
                # ^VIX excluded: yfinance intraday unreliable for VIX index
                spark_tickers = ["^TNX", "DX-Y.NYB", "GC=F", "CL=F"]
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
                self._movers_quotes = quotes  # share with watchlist
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

    async def _extra_tiles_loop(self):
        """60s: Yield Curve, Commodities (Silver/Copper/NatGas)."""
        await asyncio.sleep(8)  # stagger start
        yield_names = {"^IRX": "3M", "^FVX": "5Y", "^TNX": "10Y", "^TYX": "30Y"}
        commodity_names = {"SI=F": "Silver", "HG=F": "Copper", "NG=F": "Nat Gas"}

        while self._running:
            try:
                # --- Yield Curve ---
                yld_quotes = await self.adapter.fetch_quotes(YIELD_TICKERS, ttl=50)
                yields = {}
                for ticker in YIELD_TICKERS:
                    if ticker in yld_quotes:
                        yields[yield_names[ticker]] = yld_quotes[ticker]
                spread = None
                inverted = False
                tnx = yld_quotes.get("^TNX", {}).get("price")
                irx = yld_quotes.get("^IRX", {}).get("price")
                if tnx is not None and irx is not None:
                    spread = round(tnx - irx, 2)
                    inverted = spread < 0

                if yields:
                    await self.data_store.update("yieldcurve", {
                        "yields": yields,
                        "spread_10y3m": spread,
                        "inverted": inverted,
                    })

                # --- Commodities ---
                cmd_quotes = await self.adapter.fetch_quotes(COMMODITY_TICKERS, ttl=50)
                cmd_data = {}
                for ticker in COMMODITY_TICKERS:
                    if ticker in cmd_quotes:
                        cmd_data[commodity_names[ticker]] = cmd_quotes[ticker]
                if cmd_data:
                    await self.data_store.update("commodities", {"items": cmd_data})

            except Exception as e:
                logger.error(f"Extra tiles loop error: {e}")
            await asyncio.sleep(TIER2_INTERVAL if is_us_market_hours() else OFF_HOURS_INTERVAL)

    async def _watchlist_loop(self):
        """60s: Fixed watchlist (O, SCHD, QQQ, GOOGL, SPY) + 3 dynamic biggest movers."""
        await asyncio.sleep(20)  # stagger after movers loop (15s)
        import time as _time
        dynamic_tickers: list[str] = []
        last_dynamic_refresh = 0.0

        while self._running:
            try:
                now = _time.time()
                # Re-evaluate dynamic picks every WATCHLIST_DYNAMIC_REFRESH seconds
                if now - last_dynamic_refresh >= WATCHLIST_DYNAMIC_REFRESH:
                    dynamic_tickers = self._pick_dynamic_movers()
                    last_dynamic_refresh = now
                    if dynamic_tickers:
                        logger.info(f"Watchlist dynamic picks: {dynamic_tickers}")

                all_tickers = WATCHLIST_FIXED_TICKERS + dynamic_tickers
                quotes = await self.adapter.fetch_quotes(all_tickers, ttl=50)

                items = []
                for ticker in all_tickers:
                    if ticker in quotes:
                        items.append({
                            "symbol": ticker,
                            "dynamic": ticker in dynamic_tickers,
                            **quotes[ticker],
                        })

                if items:
                    await self.data_store.update("watchlist", {"items": items})

            except Exception as e:
                logger.error(f"Watchlist loop error: {e}")
            await asyncio.sleep(TIER2_INTERVAL if is_us_market_hours() else OFF_HOURS_INTERVAL)

    def _pick_dynamic_movers(self) -> list[str]:
        """Pick top N stocks by abs(change_pct) from movers data (no extra API call)."""
        if not self._movers_quotes:
            return []
        exclude = set(WATCHLIST_FIXED_TICKERS)
        candidates = [
            (t, abs(d.get("change_pct", 0)))
            for t, d in self._movers_quotes.items()
            if t not in exclude and "change_pct" in d
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [t for t, _ in candidates[:WATCHLIST_DYNAMIC_COUNT]]

    def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()

    async def tick(self):
        pass  # Not used; run() manages its own loops
