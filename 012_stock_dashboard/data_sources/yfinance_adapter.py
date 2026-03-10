"""yfinance async wrapper with caching."""

import asyncio
import logging
import time
import yfinance as yf

logger = logging.getLogger(__name__)


class YFinanceAdapter:
    def __init__(self):
        self._cache: dict = {}  # {ticker: {"data": ..., "expires_at": float}}
        self._lkg_cache: dict = {}  # Last-Known-Good: never expires, display fallback

    def _is_cached(self, ticker: str) -> bool:
        entry = self._cache.get(ticker)
        return entry is not None and time.time() < entry["expires_at"]

    def _get_cached(self, ticker: str):
        entry = self._cache.get(ticker)
        if entry:
            return entry["data"]
        return None

    def _set_cache(self, ticker: str, data, ttl: float = 25):
        self._cache[ticker] = {"data": data, "expires_at": time.time() + ttl}
        self._lkg_cache[ticker] = data  # Always update LKG on success

    async def fetch_quotes(self, tickers: list[str], ttl: float = 25) -> dict:
        """Fetch current quotes for multiple tickers."""
        uncached = [t for t in tickers if not self._is_cached(t)]
        results = {}

        for t in tickers:
            if self._is_cached(t):
                results[t] = self._get_cached(t)

        if not uncached:
            return results

        try:
            data = await asyncio.to_thread(self._sync_fetch_quotes, uncached)
            for ticker, quote in data.items():
                self._set_cache(ticker, quote, ttl)
                results[ticker] = quote

            # Check for missing tickers and use LKG fallback
            missing = [t for t in uncached if t not in results]
            if missing:
                logger.warning(f"yfinance batch missing {len(missing)} tickers: {missing}")
                for t in missing:
                    lkg = self._lkg_cache.get(t)
                    if lkg:
                        results[t] = lkg
                        logger.info(f"Using LKG cache for {t}")
        except Exception as e:
            logger.error(f"yfinance fetch_quotes error: {e}")
            for t in uncached:
                cached = self._get_cached(t) or self._lkg_cache.get(t)
                if cached:
                    results[t] = cached

        return results

    def _sync_fetch_quotes(self, tickers: list[str]) -> dict:
        results = {}
        ticker_str = " ".join(tickers)
        try:
            data = yf.download(ticker_str, period="5d", interval="1d", progress=False, threads=True)
        except Exception as e:
            logger.error(f"yf.download batch failed: {e}")
            data = None

        if data is not None and not data.empty:
            for ticker in tickers:
                try:
                    # yfinance v1.2.0: always MultiIndex (Price, Ticker)
                    close_col = ("Close", ticker)
                    if close_col not in data.columns:
                        continue
                    close_series = data[close_col]
                    close_vals = close_series.dropna()
                    if len(close_vals) < 1:
                        continue

                    current = float(close_vals.iloc[-1])
                    prev = float(close_vals.iloc[-2]) if len(close_vals) >= 2 else current
                    change = current - prev
                    change_pct = (change / prev * 100) if prev != 0 else 0

                    results[ticker] = {
                        "price": round(current, 2),
                        "change": round(change, 2),
                        "change_pct": round(change_pct, 2),
                        "prev_close": round(prev, 2),
                    }
                except Exception as e:
                    logger.warning(f"Error parsing {ticker}: {e}")

        # Fallback: fetch missing tickers individually
        missing = [t for t in tickers if t not in results]
        if missing:
            logger.info(f"Batch missed {len(missing)}/{len(tickers)} tickers, trying individual fetch...")
            for ticker in missing:
                try:
                    t = yf.Ticker(ticker)
                    hist = t.history(period="5d")
                    if hist.empty or len(hist) < 1:
                        logger.warning(f"Individual fetch empty for {ticker}")
                        continue
                    close_vals = hist["Close"].dropna()
                    if len(close_vals) < 1:
                        continue
                    current = float(close_vals.iloc[-1])
                    prev = float(close_vals.iloc[-2]) if len(close_vals) >= 2 else current
                    change = current - prev
                    change_pct = (change / prev * 100) if prev != 0 else 0
                    results[ticker] = {
                        "price": round(current, 2),
                        "change": round(change, 2),
                        "change_pct": round(change_pct, 2),
                        "prev_close": round(prev, 2),
                    }
                    logger.info(f"Individual fetch OK for {ticker}")
                except Exception as e:
                    logger.warning(f"Individual fetch failed for {ticker}: {e}")

        return results

    async def fetch_intraday(self, ticker: str, period: str = "1d", interval: str = "5m") -> list[dict]:
        """Fetch intraday OHLCV data for chart rendering."""
        cache_key = f"{ticker}_intraday_{period}_{interval}"
        if self._is_cached(cache_key):
            return self._get_cached(cache_key)

        try:
            data = await asyncio.to_thread(
                self._sync_fetch_intraday, ticker, period, interval
            )
            self._set_cache(cache_key, data, ttl=25)
            return data
        except Exception as e:
            logger.error(f"yfinance fetch_intraday error for {ticker}: {e}")
            return self._get_cached(cache_key) or []

    def _sync_fetch_intraday(self, ticker: str, period: str, interval: str) -> list[dict]:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval)
        if df.empty:
            return []

        points = []
        for idx, row in df.iterrows():
            ts = int(idx.timestamp())
            points.append({
                "time": ts,
                "value": round(float(row["Close"]), 2),
            })
        return points
