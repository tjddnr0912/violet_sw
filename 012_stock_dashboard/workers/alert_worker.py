"""Alert worker: detects intraday surge/drop (1h ±3%) for US + KR stocks."""

import asyncio
import logging
import time
from collections import deque

from workers.base import BaseWorker
from data_sources.yfinance_adapter import YFinanceAdapter
from data_sources.market_calendar import is_market_open
from config import (
    TOP_MOVERS_TICKERS, KR_ALERT_TICKERS, KR_TICKER_NAMES,
    ALERT_DAILY_PREFILTER_PCT, ALERT_1H_SURGE_PCT,
    ALERT_COOLDOWN_SECONDS, ALERT_MAX_ACTIVE, ALERT_SCAN_INTERVAL,
)

logger = logging.getLogger(__name__)


class AlertWorker(BaseWorker):
    def __init__(self, data_store, adapter=None):
        super().__init__(data_store, interval=ALERT_SCAN_INTERVAL)
        self.yf = adapter or YFinanceAdapter()
        self._alerts: deque = deque(maxlen=ALERT_MAX_ACTIVE)
        self._cooldowns: dict[str, float] = {}  # ticker -> expiry timestamp
        self._decay_task: asyncio.Task | None = None

    async def run(self):
        self._decay_task = asyncio.create_task(self._decay_loop())
        await super().run()

    def stop(self):
        super().stop()
        if self._decay_task:
            self._decay_task.cancel()

    async def tick(self):
        us_open = is_market_open("US")
        kr_open = is_market_open("KR")

        if not us_open and not kr_open:
            return

        await self._scan_cycle(us_open, kr_open)

    async def _scan_cycle(self, us_open: bool, kr_open: bool):
        """Phase 1: batch daily quotes → filter → Phase 2: intraday check."""
        candidates = []

        # Phase 1: US stocks
        if us_open:
            us_candidates = await self._phase1_filter(TOP_MOVERS_TICKERS, "US")
            candidates.extend(us_candidates)

        # Phase 1: KR stocks
        if kr_open:
            kr_candidates = await self._phase1_filter(KR_ALERT_TICKERS, "KR")
            candidates.extend(kr_candidates)

        if not candidates:
            return

        logger.info(f"Alert Phase 1: {len(candidates)} candidates from daily filter")

        # Phase 2: intraday check for candidates only
        for ticker, daily_pct, market in candidates:
            if self._is_cooled_down(ticker):
                continue
            await self._phase2_check(ticker, daily_pct, market)

        await self._broadcast_alerts()

    async def _phase1_filter(self, tickers: list[str], market: str) -> list[tuple]:
        """Batch fetch daily quotes, return tickers with |daily_pct| >= threshold."""
        try:
            quotes = await self.yf.fetch_quotes(tickers, ttl=60)
        except Exception as e:
            logger.error(f"Alert Phase 1 ({market}) error: {e}")
            return []

        candidates = []
        for ticker in tickers:
            quote = quotes.get(ticker)
            if not quote:
                continue
            daily_pct = quote.get("change_pct", 0)
            if abs(daily_pct) >= ALERT_DAILY_PREFILTER_PCT:
                candidates.append((ticker, daily_pct, market))

        return candidates

    async def _phase2_check(self, ticker: str, daily_pct: float, market: str):
        """Fetch 5m intraday candles, compute 1h change, fire alert if threshold met."""
        try:
            candles = await self.yf.fetch_intraday(ticker, period="1d", interval="5m")
        except Exception as e:
            logger.warning(f"Alert Phase 2 intraday error for {ticker}: {e}")
            return

        if not candles or len(candles) < 2:
            return

        # Last 12 candles = 1 hour of 5m data
        recent = candles[-12:] if len(candles) >= 12 else candles
        start_price = recent[0]["value"]
        end_price = recent[-1]["value"]

        if start_price == 0:
            return

        change_1h_pct = ((end_price - start_price) / start_price) * 100

        if abs(change_1h_pct) >= ALERT_1H_SURGE_PCT:
            self._fire_alert(ticker, change_1h_pct, daily_pct, end_price, market)

    def _fire_alert(self, ticker: str, change_1h: float, daily_pct: float,
                    price: float, market: str):
        """Add alert to deque and set cooldown."""
        alert_type = "SURGE" if change_1h > 0 else "DROP"
        severity = "critical" if abs(change_1h) >= 5.0 else "warning"

        # Display name: use Korean name for KR tickers, ticker symbol for US
        if market == "KR":
            name = KR_TICKER_NAMES.get(ticker, ticker)
        else:
            name = ticker

        alert = {
            "ticker": ticker,
            "name": name,
            "type": alert_type,
            "severity": severity,
            "change_1h_pct": round(change_1h, 2),
            "change_daily_pct": round(daily_pct, 2),
            "price": round(price, 2),
            "market": market,
            "timestamp": int(time.time()),
        }

        # Remove existing alert for same ticker if any
        self._alerts = deque(
            (a for a in self._alerts if a["ticker"] != ticker),
            maxlen=ALERT_MAX_ACTIVE,
        )
        self._alerts.append(alert)

        # Set cooldown
        self._cooldowns[ticker] = time.time() + ALERT_COOLDOWN_SECONDS

        logger.info(
            f"ALERT: {name} {alert_type} {change_1h:+.1f}% (1h), "
            f"daily {daily_pct:+.1f}%, price={price}, market={market}, "
            f"severity={severity}"
        )

    def _is_cooled_down(self, ticker: str) -> bool:
        expiry = self._cooldowns.get(ticker, 0)
        return time.time() < expiry

    async def _decay_loop(self):
        """Remove alerts older than 30 minutes, every 60s."""
        while self._running:
            try:
                await asyncio.sleep(60)
                now = time.time()
                before = len(self._alerts)
                self._alerts = deque(
                    (a for a in self._alerts if now - a["timestamp"] < 1800),
                    maxlen=ALERT_MAX_ACTIVE,
                )
                removed = before - len(self._alerts)
                if removed > 0:
                    logger.info(f"Alert decay: removed {removed} expired alerts")
                    await self._broadcast_alerts()

                # Clean expired cooldowns
                expired = [t for t, exp in self._cooldowns.items() if now >= exp]
                for t in expired:
                    del self._cooldowns[t]
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert decay error: {e}")

    async def _broadcast_alerts(self):
        alerts_list = list(self._alerts)
        await self.data_store.update("alerts", {
            "alerts": alerts_list,
            "count": len(alerts_list),
        })
