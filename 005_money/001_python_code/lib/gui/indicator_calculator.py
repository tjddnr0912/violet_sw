#!/usr/bin/env python3
"""
IndicatorCalculator - Wrapper for technical indicator calculations
Provides standardized interface for all 8 technical indicators
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import logging

# Import existing strategy functions
from ver1.strategy_v1 import (
    calculate_moving_average,
    calculate_rsi,
    calculate_bollinger_bands,
    calculate_macd,
    calculate_atr,
    calculate_stochastic,
    calculate_adx,
    calculate_volume_ratio
)


class IndicatorCalculator:
    """
    Wrapper for technical indicator calculations from strategy.py
    Provides standardized interface and error handling for all indicators
    """

    def __init__(self, config: Dict = None):
        """
        Initialize IndicatorCalculator

        Args:
            config: Configuration dictionary with indicator parameters
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)

    def calculate_ma(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict[str, pd.Series]]:
        """
        Calculate Moving Averages

        Args:
            df: OHLCV DataFrame
            config: Configuration with 'short_ma_window' and 'long_ma_window'

        Returns:
            Dictionary with 'ma_short' and 'ma_long' Series, or None on error
        """
        try:
            cfg = config or self.config
            short_window = cfg.get('short_ma_window', 20)
            long_window = cfg.get('long_ma_window', 50)

            ma_short = calculate_moving_average(df, short_window)
            ma_long = calculate_moving_average(df, long_window)

            return {
                'ma_short': ma_short,
                'ma_long': ma_long
            }

        except Exception as e:
            self.logger.error(f"MA calculation error: {e}")
            return None

    def calculate_rsi_indicator(self, df: pd.DataFrame, config: Dict = None) -> Optional[pd.Series]:
        """
        Calculate RSI (Relative Strength Index)

        Args:
            df: OHLCV DataFrame
            config: Configuration with 'rsi_period'

        Returns:
            RSI Series (0-100), or None on error
        """
        try:
            cfg = config or self.config
            period = cfg.get('rsi_period', 14)

            rsi = calculate_rsi(df, period)
            return rsi

        except Exception as e:
            self.logger.error(f"RSI calculation error: {e}")
            return None

    def calculate_bb(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict[str, pd.Series]]:
        """
        Calculate Bollinger Bands

        Args:
            df: OHLCV DataFrame
            config: Configuration with 'bb_period' and 'bb_std'

        Returns:
            Dictionary with 'upper', 'middle', 'lower' Series, or None on error
        """
        try:
            cfg = config or self.config
            period = cfg.get('bb_period', 20)
            std = cfg.get('bb_std', 2.0)

            upper, middle, lower = calculate_bollinger_bands(df, period, std)

            return {
                'upper': upper,
                'middle': middle,
                'lower': lower
            }

        except Exception as e:
            self.logger.error(f"Bollinger Bands calculation error: {e}")
            return None

    def calculate_macd_indicator(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict[str, pd.Series]]:
        """
        Calculate MACD (Moving Average Convergence Divergence)

        Args:
            df: OHLCV DataFrame
            config: Configuration with 'macd_fast', 'macd_slow', 'macd_signal'

        Returns:
            Dictionary with 'macd_line', 'signal_line', 'histogram' Series, or None on error
        """
        try:
            cfg = config or self.config
            fast = cfg.get('macd_fast', 8)
            slow = cfg.get('macd_slow', 17)
            signal = cfg.get('macd_signal', 9)

            macd_line, signal_line, histogram = calculate_macd(df, fast, slow, signal)

            return {
                'macd_line': macd_line,
                'signal_line': signal_line,
                'histogram': histogram
            }

        except Exception as e:
            self.logger.error(f"MACD calculation error: {e}")
            return None

    def calculate_stoch(self, df: pd.DataFrame, config: Dict = None) -> Optional[Dict[str, pd.Series]]:
        """
        Calculate Stochastic Oscillator

        Args:
            df: OHLCV DataFrame
            config: Configuration with 'stoch_k_period' and 'stoch_d_period'

        Returns:
            Dictionary with 'k' and 'd' Series, or None on error
        """
        try:
            cfg = config or self.config
            k_period = cfg.get('stoch_k_period', 14)
            d_period = cfg.get('stoch_d_period', 3)

            k, d = calculate_stochastic(df, k_period, d_period)

            return {
                'k': k,
                'd': d
            }

        except Exception as e:
            self.logger.error(f"Stochastic calculation error: {e}")
            return None

    def calculate_atr_indicator(self, df: pd.DataFrame, config: Dict = None) -> Optional[pd.Series]:
        """
        Calculate ATR (Average True Range)

        Args:
            df: OHLCV DataFrame
            config: Configuration with 'atr_period'

        Returns:
            ATR Series, or None on error
        """
        try:
            cfg = config or self.config
            period = cfg.get('atr_period', 14)

            atr = calculate_atr(df, period)
            return atr

        except Exception as e:
            self.logger.error(f"ATR calculation error: {e}")
            return None

    def calculate_adx_indicator(self, df: pd.DataFrame, config: Dict = None) -> Optional[pd.Series]:
        """
        Calculate ADX (Average Directional Index)

        Args:
            df: OHLCV DataFrame
            config: Configuration with 'adx_period'

        Returns:
            ADX Series, or None on error
        """
        try:
            cfg = config or self.config
            period = cfg.get('adx_period', 14)

            adx = calculate_adx(df, period)
            return adx

        except Exception as e:
            self.logger.error(f"ADX calculation error: {e}")
            return None

    def get_volume_data(self, df: pd.DataFrame) -> Optional[pd.Series]:
        """
        Get volume data (no calculation needed)

        Args:
            df: OHLCV DataFrame

        Returns:
            Volume Series, or None if not present
        """
        try:
            if 'volume' not in df.columns:
                self.logger.warning("Volume column not found in DataFrame")
                return None

            return df['volume']

        except Exception as e:
            self.logger.error(f"Volume extraction error: {e}")
            return None

    def calculate_all_indicators(self, df: pd.DataFrame, config: Dict = None) -> Dict[str, any]:
        """
        Calculate all indicators at once

        Args:
            df: OHLCV DataFrame
            config: Configuration dictionary

        Returns:
            Dictionary with all indicator results (None for failed calculations)
        """
        results = {
            'ma': self.calculate_ma(df, config),
            'rsi': self.calculate_rsi_indicator(df, config),
            'bb': self.calculate_bb(df, config),
            'macd': self.calculate_macd_indicator(df, config),
            'stochastic': self.calculate_stoch(df, config),
            'atr': self.calculate_atr_indicator(df, config),
            'adx': self.calculate_adx_indicator(df, config),
            'volume': self.get_volume_data(df)
        }

        # Count successful calculations
        success_count = sum(1 for v in results.values() if v is not None)
        self.logger.info(f"Calculated {success_count}/8 indicators successfully")

        return results


# Example usage and testing
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Test with sample data
    from bithumb_api import get_candlestick

    print("Fetching BTC 1h data...")
    df = get_candlestick('BTC', '1h')

    if df is not None:
        print(f"Data shape: {df.shape}")

        # Create calculator with 1h config
        config = {
            'short_ma_window': 20,
            'long_ma_window': 50,
            'rsi_period': 14,
            'bb_period': 20,
            'bb_std': 2.0,
            'macd_fast': 8,
            'macd_slow': 17,
            'macd_signal': 9,
            'atr_period': 14,
            'stoch_k_period': 14,
            'stoch_d_period': 3,
            'adx_period': 14
        }

        calculator = IndicatorCalculator(config)

        # Calculate all indicators
        print("\nCalculating all indicators...")
        results = calculator.calculate_all_indicators(df)

        # Display results
        print("\nResults:")
        for indicator, data in results.items():
            if data is not None:
                if isinstance(data, dict):
                    print(f"  {indicator}: {list(data.keys())}")
                    for key, series in data.items():
                        if isinstance(series, pd.Series):
                            print(f"    {key}: last value = {series.iloc[-1]:.2f}")
                elif isinstance(data, pd.Series):
                    print(f"  {indicator}: last value = {data.iloc[-1]:.2f}")
            else:
                print(f"  {indicator}: FAILED")
    else:
        print("Failed to fetch data")
