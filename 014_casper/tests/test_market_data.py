"""Tests for market data module — KIS primary, yfinance fallback."""

import pytest
import pandas as pd
import numpy as np
import pytz
from datetime import datetime
from unittest.mock import patch, MagicMock

from src.data.market_data import (
    get_vix_close, get_qqq_trend_data, get_intraday_bars,
    get_avg_daily_range, get_current_price, _valid_price,
    set_kis_client, _kis_bars_to_dataframe,
)

ET = pytz.timezone("US/Eastern")


def _make_yf_history(closes, highs=None, lows=None):
    n = len(closes)
    dates = pd.date_range("2026-03-01", periods=n, freq="D", tz=ET)
    return pd.DataFrame({
        "Open": closes, "Close": closes,
        "High": highs or [c + 1 for c in closes],
        "Low": lows or [c - 1 for c in closes],
        "Volume": [1000000] * n,
    }, index=dates)


@pytest.fixture(autouse=True)
def reset_kis_client():
    """Ensure KIS client is reset between tests."""
    set_kis_client(None)
    yield
    set_kis_client(None)


# ─── _valid_price ───

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


# ─── VIX (yfinance only) ───

class TestGetVixClose:
    @patch("src.data.market_data.yf.Ticker")
    def test_returns_float(self, mock_cls):
        mock_t = MagicMock()
        mock_t.history.return_value = _make_yf_history([20.5, 21.0, 19.8, 22.1, 20.0])
        mock_cls.return_value = mock_t
        assert get_vix_close() == 20.0

    @patch("src.data.market_data.yf.Ticker")
    def test_empty_returns_none(self, mock_cls):
        mock_t = MagicMock()
        mock_t.history.return_value = pd.DataFrame()
        mock_cls.return_value = mock_t
        assert get_vix_close() is None

    @patch("src.data.market_data.yf.Ticker")
    def test_nan_returns_none(self, mock_cls):
        mock_t = MagicMock()
        mock_t.history.return_value = _make_yf_history([float("nan")])
        mock_cls.return_value = mock_t
        assert get_vix_close() is None

    @patch("src.data.market_data.yf.Ticker")
    def test_exception_returns_none(self, mock_cls):
        mock_cls.side_effect = Exception("Network")
        assert get_vix_close() is None

    def test_vix_ignores_kis_client(self):
        """VIX always uses yfinance, even if KIS client is set."""
        mock_kis = MagicMock()
        set_kis_client(mock_kis)
        with patch("src.data.market_data.yf.Ticker") as mock_cls:
            mock_t = MagicMock()
            mock_t.history.return_value = _make_yf_history([22.0])
            mock_cls.return_value = mock_t
            result = get_vix_close()
            assert result == 22.0
            # KIS should NOT be called for VIX
            mock_kis.get_us_daily_chart.assert_not_called()


# ─── QQQ Trend (KIS → yfinance) ───

class TestGetQQQTrendData:
    def test_kis_primary(self):
        mock_kis = MagicMock()
        mock_kis.get_us_daily_chart.return_value = [
            {"date": f"2026030{i}", "open": 490+i, "high": 492+i,
             "low": 488+i, "close": 490+i, "volume": 1000}
            for i in range(25)
        ]
        set_kis_client(mock_kis)
        close, ma = get_qqq_trend_data(20)
        assert close is not None
        assert ma is not None
        mock_kis.get_us_daily_chart.assert_called_once()

    @patch("src.data.market_data._get_qqq_trend_yf")
    def test_fallback_to_yfinance(self, mock_yf):
        mock_kis = MagicMock()
        mock_kis.get_us_daily_chart.return_value = None  # KIS fails
        set_kis_client(mock_kis)
        mock_yf.return_value = (500.0, 495.0)

        close, ma = get_qqq_trend_data(20)
        assert close == 500.0
        mock_yf.assert_called_once()

    @patch("src.data.market_data.yf.Ticker")
    def test_yfinance_only_when_no_kis(self, mock_cls):
        mock_t = MagicMock()
        mock_t.history.return_value = _make_yf_history(list(range(480, 510)))
        mock_cls.return_value = mock_t
        close, ma = get_qqq_trend_data(20)
        assert close is not None


# ─── Intraday Bars (KIS → yfinance) ───

class TestGetIntradayBars:
    def test_kis_primary(self):
        mock_kis = MagicMock()
        mock_kis.get_us_minute_chart.return_value = [
            {"date": "20260406", "time": f"09{30+i*5:02d}00",
             "open": 50+i, "high": 51+i, "low": 49+i,
             "close": 50.5+i, "volume": 1000}
            for i in range(6)
        ]
        set_kis_client(mock_kis)
        result = get_intraday_bars("TQQQ")
        assert result is not None
        assert len(result) == 6
        assert "Open" in result.columns

    @patch("src.data.market_data._get_intraday_yf")
    def test_fallback_to_yfinance(self, mock_yf):
        mock_kis = MagicMock()
        mock_kis.get_us_minute_chart.return_value = None
        set_kis_client(mock_kis)

        idx = pd.date_range("2026-04-06 09:30", periods=5, freq="5min", tz=ET)
        mock_yf.return_value = pd.DataFrame({
            "Open": [50]*5, "High": [51]*5, "Low": [49]*5,
            "Close": [50.5]*5, "Volume": [1000]*5,
        }, index=idx)

        result = get_intraday_bars("TQQQ")
        assert result is not None
        mock_yf.assert_called_once()

    @patch("src.data.market_data.yf.Ticker")
    def test_yfinance_only(self, mock_cls):
        idx = pd.date_range("2026-04-06 09:30", periods=5, freq="5min", tz=ET)
        mock_t = MagicMock()
        mock_t.history.return_value = pd.DataFrame({
            "Open": [50]*5, "High": [51]*5, "Low": [49]*5,
            "Close": [50.5]*5, "Volume": [1000]*5,
        }, index=idx)
        mock_cls.return_value = mock_t
        result = get_intraday_bars("TQQQ")
        assert result is not None


# ─── KIS Bars → DataFrame Conversion ───

class TestKisBarsToDataframe:
    def test_converts_correctly(self):
        bars = [
            {"date": "20260406", "time": "093000", "open": 50, "high": 51,
             "low": 49, "close": 50.5, "volume": 1000},
            {"date": "20260406", "time": "093500", "open": 50.5, "high": 52,
             "low": 50, "close": 51.5, "volume": 1200},
        ]
        df = _kis_bars_to_dataframe(bars)
        assert df is not None
        assert len(df) == 2
        assert df.iloc[0]["Close"] == 50.5
        assert df.index[0].hour == 9
        assert df.index[0].minute == 30

    def test_empty_returns_none(self):
        assert _kis_bars_to_dataframe([]) is None
        assert _kis_bars_to_dataframe(None) is None

    def test_skips_invalid_bars(self):
        bars = [
            {"date": "bad", "time": "bad", "open": 50, "high": 51,
             "low": 49, "close": 50.5, "volume": 1000},
            {"date": "20260406", "time": "093000", "open": 50, "high": 51,
             "low": 49, "close": 50.5, "volume": 1000},
        ]
        df = _kis_bars_to_dataframe(bars)
        assert df is not None
        assert len(df) == 1


# ─── ADR (KIS → yfinance) ───

class TestGetAvgDailyRange:
    def test_kis_primary(self):
        mock_kis = MagicMock()
        mock_kis.get_us_daily_chart.return_value = [
            {"date": f"2026030{i}", "open": 50, "high": 54,
             "low": 50, "close": 52, "volume": 1000}
            for i in range(25)
        ]
        set_kis_client(mock_kis)
        result = get_avg_daily_range("TQQQ", 20)
        assert result is not None
        assert result == 4.0  # high-low = 54-50

    @patch("src.data.market_data._get_adr_yf")
    def test_fallback(self, mock_yf):
        mock_kis = MagicMock()
        mock_kis.get_us_daily_chart.return_value = None
        set_kis_client(mock_kis)
        mock_yf.return_value = 3.5

        result = get_avg_daily_range("TQQQ", 20)
        assert result == 3.5


# ─── Current Price (KIS → yfinance) ───

class TestGetCurrentPrice:
    def test_kis_primary(self):
        mock_kis = MagicMock()
        mock_kis.get_us_price.return_value = {"price": 55.5, "high": 56, "low": 54}
        set_kis_client(mock_kis)
        assert get_current_price("TQQQ") == 55.5

    @patch("src.data.market_data._get_price_yf")
    def test_fallback(self, mock_yf):
        mock_kis = MagicMock()
        mock_kis.get_us_price.return_value = None
        set_kis_client(mock_kis)
        mock_yf.return_value = 55.0

        assert get_current_price("TQQQ") == 55.0

    @patch("src.data.market_data.yf.Ticker")
    def test_yfinance_only(self, mock_cls):
        idx = pd.date_range("2026-04-06 09:30", periods=1, freq="1min", tz=ET)
        mock_t = MagicMock()
        mock_t.history.return_value = pd.DataFrame({"Close": [56.0]}, index=idx)
        mock_cls.return_value = mock_t
        assert get_current_price("TQQQ") == 56.0

    @patch("src.data.market_data.yf.Ticker")
    def test_nan_returns_none(self, mock_cls):
        idx = pd.date_range("2026-04-06 09:30", periods=1, freq="1min", tz=ET)
        mock_t = MagicMock()
        mock_t.history.return_value = pd.DataFrame({"Close": [float("nan")]}, index=idx)
        mock_cls.return_value = mock_t
        assert get_current_price("TQQQ") is None


# ─── Dual Source Integration ───

class TestDualSource:
    def test_kis_set_and_cleared(self):
        mock_kis = MagicMock()
        set_kis_client(mock_kis)

        from src.data import market_data
        assert market_data._kis_client is mock_kis

        set_kis_client(None)
        assert market_data._kis_client is None
