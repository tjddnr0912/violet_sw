"""Tests for market data module (mocked yfinance)."""

import pytest
import pandas as pd
import numpy as np
import pytz
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.data.market_data import (
    get_vix_close, get_qqq_trend_data, get_intraday_bars,
    get_avg_daily_range, get_current_price, _valid_price,
)

ET = pytz.timezone("US/Eastern")


def _make_history(closes, highs=None, lows=None, period_days=None):
    """Create a mock yfinance history DataFrame."""
    n = len(closes)
    dates = pd.date_range("2026-03-01", periods=n, freq="D", tz=ET)
    df = pd.DataFrame({
        "Open": closes,
        "High": highs or [c + 1 for c in closes],
        "Low": lows or [c - 1 for c in closes],
        "Close": closes,
        "Volume": [1000000] * n,
    }, index=dates)
    return df


def _make_intraday_bars(n=20):
    """Create mock intraday 5-min bars."""
    index = pd.date_range("2026-04-06 09:30", periods=n, freq="5min", tz=ET)
    df = pd.DataFrame({
        "Open": [50 + i * 0.5 for i in range(n)],
        "High": [51 + i * 0.5 for i in range(n)],
        "Low": [49.5 + i * 0.5 for i in range(n)],
        "Close": [50.5 + i * 0.5 for i in range(n)],
        "Volume": [1000] * n,
    }, index=index)
    return df


class TestValidPrice:
    def test_valid_positive(self):
        assert _valid_price(55.0) is True

    def test_zero_invalid(self):
        assert _valid_price(0.0) is False

    def test_negative_invalid(self):
        assert _valid_price(-1.0) is False

    def test_nan_invalid(self):
        assert not _valid_price(float("nan"))

    def test_inf_invalid(self):
        assert not _valid_price(float("inf"))

    def test_none_invalid(self):
        assert _valid_price(None) is False


class TestGetVixClose:
    @patch("src.data.market_data.yf.Ticker")
    def test_returns_float(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_history([20.5, 21.0, 19.8, 22.1, 20.0])
        mock_ticker_cls.return_value = mock_ticker

        result = get_vix_close()
        assert result == 20.0

    @patch("src.data.market_data.yf.Ticker")
    def test_empty_history(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        assert get_vix_close() is None

    @patch("src.data.market_data.yf.Ticker")
    def test_nan_value_returns_none(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_history([float("nan")])
        mock_ticker_cls.return_value = mock_ticker

        assert get_vix_close() is None

    @patch("src.data.market_data.yf.Ticker")
    def test_exception_returns_none(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("Network error")
        assert get_vix_close() is None


class TestGetQQQTrendData:
    @patch("src.data.market_data.yf.Ticker")
    def test_returns_close_and_ma(self, mock_ticker_cls):
        closes = list(range(480, 510))  # 30 values
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_history(closes)
        mock_ticker_cls.return_value = mock_ticker

        close, ma = get_qqq_trend_data(ma_period=20)
        assert close is not None
        assert ma is not None
        assert close == 509  # last value

    @patch("src.data.market_data.yf.Ticker")
    def test_not_enough_data(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_history([500, 501])
        mock_ticker_cls.return_value = mock_ticker

        close, ma = get_qqq_trend_data(ma_period=20)
        assert close is None
        assert ma is None


class TestGetIntradayBars:
    @patch("src.data.market_data.yf.Ticker")
    def test_returns_dataframe(self, mock_ticker_cls):
        bars = _make_intraday_bars()
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = bars
        mock_ticker_cls.return_value = mock_ticker

        result = get_intraday_bars("TQQQ")
        assert result is not None
        assert len(result) == 20

    @patch("src.data.market_data.yf.Ticker")
    def test_empty_data(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        assert get_intraday_bars("TQQQ") is None


class TestGetAvgDailyRange:
    @patch("src.data.market_data.yf.Ticker")
    def test_returns_float(self, mock_ticker_cls):
        highs = [52 + i for i in range(25)]
        lows = [48 + i for i in range(25)]
        closes = [50 + i for i in range(25)]
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_history(closes, highs, lows)
        mock_ticker_cls.return_value = mock_ticker

        result = get_avg_daily_range("TQQQ", days=20)
        assert result is not None
        assert result == 4.0  # Each bar has H-L = 4

    @patch("src.data.market_data.yf.Ticker")
    def test_not_enough_data(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = _make_history([50])
        mock_ticker_cls.return_value = mock_ticker

        assert get_avg_daily_range("TQQQ", days=20) is None


class TestGetCurrentPrice:
    @patch("src.data.market_data.yf.Ticker")
    def test_returns_float(self, mock_ticker_cls):
        index = pd.date_range("2026-04-06 09:30", periods=5, freq="1min", tz=ET)
        df = pd.DataFrame({
            "Close": [55.0, 55.5, 55.2, 55.8, 56.0],
        }, index=index)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        result = get_current_price("TQQQ")
        assert result == 56.0

    @patch("src.data.market_data.yf.Ticker")
    def test_empty_returns_none(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        mock_ticker_cls.return_value = mock_ticker

        assert get_current_price("TQQQ") is None

    @patch("src.data.market_data.yf.Ticker")
    def test_nan_price_returns_none(self, mock_ticker_cls):
        index = pd.date_range("2026-04-06 09:30", periods=1, freq="1min", tz=ET)
        df = pd.DataFrame({"Close": [float("nan")]}, index=index)
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker_cls.return_value = mock_ticker

        assert get_current_price("TQQQ") is None
