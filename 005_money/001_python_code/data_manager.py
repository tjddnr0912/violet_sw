#!/usr/bin/env python3
"""
DataManager - Centralized API caching layer for multi-timeframe charts
Handles rate limiting, cache management, and data staleness detection
"""

import pandas as pd
import time
from typing import Dict, List, Optional
from datetime import datetime
import logging
from bithumb_api import get_candlestick

class DataManager:
    """
    Centralized data management for multiple timeframe charts.
    Features:
    - API response caching with TTL (time-to-live)
    - Rate limiting to prevent API abuse
    - Staleness detection and automatic refresh
    - Error handling with exponential backoff
    """

    def __init__(self, coin_symbol: str, cache_ttl_seconds: int = 15,
                 rate_limit_seconds: float = 1.0):
        """
        Initialize DataManager

        Args:
            coin_symbol: Cryptocurrency symbol (e.g., 'BTC', 'ETH')
            cache_ttl_seconds: Cache time-to-live in seconds (default: 15)
            rate_limit_seconds: Minimum gap between API calls (default: 1.0)
        """
        self.coin_symbol = coin_symbol
        self.cache_ttl = cache_ttl_seconds
        self.rate_limit = rate_limit_seconds
        self.logger = logging.getLogger(__name__)

        # Cache structure: {interval: {'data': DataFrame, 'timestamp': float}}
        self.cache: Dict[str, Dict] = {}

        # Rate limiting
        self.last_api_call = 0.0

        # Error tracking for exponential backoff
        self.error_count = 0
        self.max_retries = 3
        self.base_backoff = 2.0  # seconds

        self.logger.info(f"DataManager initialized for {coin_symbol} "
                        f"(TTL={cache_ttl_seconds}s, Rate={rate_limit_seconds}s)")

    def get_cached_data(self, interval: str) -> Optional[pd.DataFrame]:
        """
        Get data from cache if available and fresh

        Args:
            interval: Candlestick interval (e.g., '1h', '4h', '24h')

        Returns:
            DataFrame if cache hit and fresh, None otherwise
        """
        if interval not in self.cache:
            return None

        cached_item = self.cache[interval]
        age = time.time() - cached_item['timestamp']

        if age > self.cache_ttl:
            self.logger.debug(f"Cache stale for {interval} (age={age:.1f}s)")
            return None

        self.logger.debug(f"Cache hit for {interval} (age={age:.1f}s)")
        return cached_item['data']

    def _enforce_rate_limit(self):
        """Ensure minimum gap between API calls"""
        elapsed = time.time() - self.last_api_call
        if elapsed < self.rate_limit:
            sleep_time = self.rate_limit - elapsed
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)

    def _fetch_from_api(self, interval: str) -> Optional[pd.DataFrame]:
        """
        Fetch data from Bithumb API with error handling

        Args:
            interval: Candlestick interval

        Returns:
            DataFrame on success, None on failure
        """
        try:
            self._enforce_rate_limit()

            self.logger.info(f"Fetching {self.coin_symbol} data for {interval} from API")
            df = get_candlestick(self.coin_symbol, interval)

            self.last_api_call = time.time()

            if df is None or df.empty:
                self.logger.warning(f"API returned empty data for {interval}")
                return None

            # Limit to last 200 candles for memory efficiency
            if len(df) > 200:
                df = df.tail(200)

            # Reset error count on success
            self.error_count = 0

            self.logger.info(f"Successfully fetched {len(df)} candles for {interval}")
            return df

        except Exception as e:
            self.error_count += 1
            self.logger.error(f"API fetch error for {interval}: {e}")

            # Exponential backoff
            if self.error_count <= self.max_retries:
                backoff_time = self.base_backoff ** self.error_count
                self.logger.warning(f"Will retry with {backoff_time:.1f}s backoff "
                                   f"(attempt {self.error_count}/{self.max_retries})")
                time.sleep(backoff_time)

            return None

    def fetch_data(self, interval: str, force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        Fetch data with smart caching

        Args:
            interval: Candlestick interval
            force_refresh: Bypass cache and force API call

        Returns:
            DataFrame on success, None on failure
        """
        # Check cache first (unless force refresh)
        if not force_refresh:
            cached_data = self.get_cached_data(interval)
            if cached_data is not None:
                return cached_data

        # Fetch from API
        df = self._fetch_from_api(interval)

        if df is not None:
            # Update cache
            self.cache[interval] = {
                'data': df,
                'timestamp': time.time()
            }
            self.logger.debug(f"Cache updated for {interval}")

        return df

    def fetch_multiple_intervals(self, intervals: List[str]) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple intervals efficiently

        Args:
            intervals: List of candlestick intervals

        Returns:
            Dictionary mapping interval to DataFrame
        """
        results = {}

        for interval in intervals:
            df = self.fetch_data(interval)
            if df is not None:
                results[interval] = df
            else:
                self.logger.warning(f"Failed to fetch data for {interval}")

        return results

    def refresh_intervals(self, intervals: List[str]) -> List[str]:
        """
        Check which intervals need refresh and update them

        Args:
            intervals: List of intervals to check

        Returns:
            List of intervals that were actually refreshed
        """
        refreshed = []

        for interval in intervals:
            # Check if stale
            if interval not in self.cache:
                needs_refresh = True
            else:
                age = time.time() - self.cache[interval]['timestamp']
                needs_refresh = age > self.cache_ttl

            if needs_refresh:
                df = self.fetch_data(interval, force_refresh=True)
                if df is not None:
                    refreshed.append(interval)
                    self.logger.debug(f"Refreshed {interval}")

        if refreshed:
            self.logger.info(f"Refreshed {len(refreshed)} intervals: {refreshed}")
        else:
            self.logger.debug("No intervals needed refresh")

        return refreshed

    def clear_cache(self, interval: Optional[str] = None):
        """
        Clear cache for specific interval or all

        Args:
            interval: Specific interval to clear, or None for all
        """
        if interval:
            if interval in self.cache:
                del self.cache[interval]
                self.logger.info(f"Cache cleared for {interval}")
        else:
            self.cache.clear()
            self.logger.info("All cache cleared")

    def get_cache_info(self) -> Dict[str, Dict]:
        """
        Get cache status information

        Returns:
            Dictionary with cache statistics
        """
        info = {}
        current_time = time.time()

        for interval, cached_item in self.cache.items():
            age = current_time - cached_item['timestamp']
            is_fresh = age <= self.cache_ttl
            info[interval] = {
                'age_seconds': age,
                'is_fresh': is_fresh,
                'candle_count': len(cached_item['data']),
                'timestamp': datetime.fromtimestamp(cached_item['timestamp']).strftime('%H:%M:%S')
            }

        return info


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Create manager for BTC
    manager = DataManager('BTC', cache_ttl_seconds=15, rate_limit_seconds=1.0)

    # Fetch multiple intervals
    print("Fetching multiple intervals...")
    data = manager.fetch_multiple_intervals(['1h', '4h', '24h'])

    for interval, df in data.items():
        print(f"{interval}: {len(df)} candles, latest close: {df['close'].iloc[-1]:,.0f}")

    # Check cache
    print("\nCache info:")
    for interval, info in manager.get_cache_info().items():
        print(f"  {interval}: {info['candle_count']} candles, "
              f"age={info['age_seconds']:.1f}s, fresh={info['is_fresh']}")

    # Wait for cache to expire
    print("\nWaiting 5 seconds...")
    time.sleep(5)

    # Refresh stale data
    print("\nRefreshing stale intervals...")
    refreshed = manager.refresh_intervals(['1h', '4h', '24h'])
    print(f"Refreshed: {refreshed}")
