"""
Indicator Calculation Engine - Version 2

This module provides centralized indicator calculations for the 4H execution timeframe
using Backtrader's built-in indicator system.

Indicators Provided:
- Bollinger Bands (20, 2.0 std dev)
- RSI (14 period)
- Stochastic RSI (14 period, K=3, D=3)
- ATR (14 period)

Also provides standalone pandas-based calculation functions for GUI chart display.
"""

import backtrader as bt
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple


class IndicatorCalculator:
    """
    Centralized indicator calculation for 4H timeframe.

    This class encapsulates all technical indicator calculations needed for
    the entry/exit signal generation. All indicators are calculated using
    Backtrader's built-in indicator system for consistency and efficiency.

    Usage:
        indicators = IndicatorCalculator(data_4h, config)
        # Access indicators via:
        #   indicators.bb_upper[0], indicators.rsi[0], etc.
    """

    def __init__(self, data: bt.DataBase, config: Dict[str, Any]):
        """
        Initialize indicator calculator with data feed and configuration.

        Args:
            data: Backtrader data feed (4H timeframe)
            config: Configuration dictionary with indicator parameters
        """
        self.data = data
        self.config = config

        # Extract configuration parameters with defaults
        bb_period = config.get('bb_period', 20)
        bb_std = config.get('bb_std', 2.0)
        rsi_period = config.get('rsi_period', 14)
        stoch_rsi_period = config.get('stoch_rsi_period', 14)
        stoch_k_smooth = config.get('stoch_rsi_k_smooth', 3)
        stoch_d_smooth = config.get('stoch_rsi_d_smooth', 3)
        atr_period = config.get('atr_period', 14)

        # ===== Bollinger Bands =====
        # Used for: Entry trigger (lower band), Exit targets (middle & upper)
        self.bb = bt.indicators.BollingerBands(
            data.close,
            period=bb_period,
            devfactor=bb_std
        )
        self.bb_upper = self.bb.lines.top
        self.bb_mid = self.bb.lines.mid
        self.bb_lower = self.bb.lines.bot

        # ===== RSI =====
        # Used for: Entry confirmation (oversold below 30)
        self.rsi = bt.indicators.RSI(
            data.close,
            period=rsi_period
        )

        # ===== Stochastic RSI =====
        # Used for: Entry timing (bullish crossover in oversold zone)
        # This is the most important timing indicator (worth 2 points)
        self.stoch_rsi = bt.indicators.StochasticRSI(
            data.close,
            period=stoch_rsi_period,
            pfast=stoch_k_smooth,
            pslow=stoch_d_smooth
        )
        self.stoch_k = self.stoch_rsi.lines.percK
        self.stoch_d = self.stoch_rsi.lines.percD

        # ===== ATR (Average True Range) =====
        # Used for: Chandelier Exit calculation, position sizing
        # Critical for dynamic risk management
        self.atr = bt.indicators.ATR(
            data,
            period=atr_period
        )

    def get_latest_values(self) -> Dict[str, float]:
        """
        Get current values of all indicators.

        Returns:
            Dictionary with indicator names and current values
        """
        return {
            'bb_upper': self.bb_upper[0],
            'bb_mid': self.bb_mid[0],
            'bb_lower': self.bb_lower[0],
            'rsi': self.rsi[0],
            'stoch_k': self.stoch_k[0],
            'stoch_d': self.stoch_d[0],
            'atr': self.atr[0],
        }

    def get_indicator_history(self, bars_back: int = 1) -> Dict[str, float]:
        """
        Get historical indicator values.

        Args:
            bars_back: Number of bars to look back (1 = previous bar)

        Returns:
            Dictionary with indicator names and historical values
        """
        return {
            'bb_upper': self.bb_upper[-bars_back],
            'bb_mid': self.bb_mid[-bars_back],
            'bb_lower': self.bb_lower[-bars_back],
            'rsi': self.rsi[-bars_back],
            'stoch_k': self.stoch_k[-bars_back],
            'stoch_d': self.stoch_d[-bars_back],
            'atr': self.atr[-bars_back],
        }

    def is_ready(self) -> bool:
        """
        Check if all indicators have sufficient data for calculation.

        Returns:
            True if all indicators are ready, False otherwise
        """
        # Check if any indicator has NaN values
        try:
            values = self.get_latest_values()
            return all(not pd.isna(v) for v in values.values())
        except:
            return False


# ==================== STANDALONE CALCULATION FUNCTIONS ====================
# These functions are used by the GUI chart widget for display purposes.
# They use pandas/numpy for calculation (not Backtrader).
# =========================================================================

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """
    Calculate Exponential Moving Average.

    Args:
        series: Price series (typically close prices)
        period: EMA period

    Returns:
        EMA values as pandas Series
    """
    return series.ewm(span=period, adjust=False).mean()


def calculate_bollinger_bands(series: pd.Series, period: int = 20, std_dev: float = 2.0) -> Dict[str, pd.Series]:
    """
    Calculate Bollinger Bands.

    Args:
        series: Price series (typically close prices)
        period: Moving average period
        std_dev: Standard deviation multiplier

    Returns:
        Dictionary with 'upper', 'middle', 'lower' bands
    """
    middle = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()

    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)

    return {
        'upper': upper,
        'middle': middle,
        'lower': lower
    }


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate RSI (Relative Strength Index).

    Args:
        series: Price series (typically close prices)
        period: RSI period

    Returns:
        RSI values (0-100) as pandas Series
    """
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    # Prevent division by zero
    loss = loss.replace(0, 1e-10)
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # Clip to valid range and fill NaN
    rsi = rsi.clip(0, 100)
    rsi = rsi.fillna(50)  # Neutral RSI when insufficient data

    return rsi


def calculate_stochastic_rsi(series: pd.Series, rsi_period: int = 14, stoch_period: int = 14,
                             k_smooth: int = 3, d_smooth: int = 3) -> Dict[str, pd.Series]:
    """
    Calculate Stochastic RSI.

    Args:
        series: Price series (typically close prices)
        rsi_period: RSI calculation period
        stoch_period: Stochastic calculation period
        k_smooth: %K smoothing period
        d_smooth: %D smoothing period

    Returns:
        Dictionary with 'k' and 'd' values
    """
    # First calculate RSI
    rsi = calculate_rsi(series, rsi_period)

    # Calculate Stochastic of RSI
    rsi_min = rsi.rolling(window=stoch_period).min()
    rsi_max = rsi.rolling(window=stoch_period).max()

    # Prevent division by zero
    denominator = (rsi_max - rsi_min).replace(0, 1e-10)

    # %K calculation
    stoch_k = 100 * ((rsi - rsi_min) / denominator)

    # Smooth %K
    stoch_k = stoch_k.rolling(window=k_smooth).mean()

    # %D calculation (smoothed %K)
    stoch_d = stoch_k.rolling(window=d_smooth).mean()

    return {
        'k': stoch_k,
        'd': stoch_d
    }


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate ATR (Average True Range).

    Args:
        high: High prices
        low: Low prices
        close: Close prices
        period: ATR period

    Returns:
        ATR values as pandas Series
    """
    # True Range calculation
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    return atr
