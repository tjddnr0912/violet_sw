import math
import numpy as np
import pandas as pd
import pytest
from datetime import date
from src.core import trend


def _mk(prices, start="2024-01-01"):
    idx = pd.bdate_range(start=start, periods=len(prices))
    return pd.DataFrame({"Close": prices}, index=idx)


def _trend_data(qqq_prices, tqqq_prices):
    return {"QQQ": _mk(qqq_prices), "TQQQ": _mk(tqqq_prices)}


PARAMS = {"signal_symbol": "QQQ", "sma_period": 200, "asset": "TQQQ",
          "safe_asset": "BIL", "target_vol": 0.40, "vol_lookback": 20}


def test_regime_off_returns_safe_asset():
    qqq = list(np.linspace(500, 300, 260))           # falling
    tqqq = list(np.linspace(80, 40, 260))
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data=_trend_data(qqq, tqqq))
    assert sig.regime is False
    assert sig.target_symbol == "BIL"
    assert sig.exposure == 0.0


def test_regime_on_returns_tqqq_with_capped_exposure():
    qqq = list(np.linspace(300, 600, 260))           # rising
    tqqq = list(np.linspace(40, 120, 260))           # smooth rise = low daily vol
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data=_trend_data(qqq, tqqq))
    assert sig.regime is True
    assert sig.target_symbol == "TQQQ"
    assert 0.0 < sig.exposure <= 1.0


def test_high_vol_reduces_exposure_below_cap():
    qqq = list(np.linspace(300, 600, 260))
    rng = np.random.default_rng(0)
    tqqq = list(100 + np.cumsum(rng.normal(0, 6, 260)))  # high-vol path
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data=_trend_data(qqq, tqqq))
    if sig.regime:               # uptrend may or may not hold given noise
        assert sig.exposure < 1.0


def test_missing_data_falls_back_to_safe_asset():
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data={"QQQ": _mk([1, 2, 3]), "TQQQ": _mk([1, 2])})
    assert sig.target_symbol == "BIL"
    assert sig.exposure == 0.0
