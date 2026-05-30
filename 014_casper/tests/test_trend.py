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
    # Strong uptrend (regime stays ON) but very choppy TQQQ -> high realized vol
    # -> exposure must be capped BELOW 1.0. Steep ramp dominates the noise so
    # the regime is deterministically on, making the cap assertion non-vacuous.
    qqq = list(np.linspace(300, 900, 260))
    rng = np.random.default_rng(0)
    noise = np.cumsum(rng.normal(0, 7, 260))
    tqqq = list(np.linspace(40, 200, 260) + noise)  # steep ramp + chop
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data=_trend_data(qqq, tqqq))
    assert sig.regime is True      # fixture constructed to stay in uptrend
    assert 0.0 < sig.exposure < 1.0


def test_missing_data_falls_back_to_safe_asset():
    sig = trend.compute_trend_signal(today=date(2024, 12, 31),
                                     params=PARAMS,
                                     data={"QQQ": _mk([1, 2, 3]), "TQQQ": _mk([1, 2])})
    assert sig.target_symbol == "BIL"
    assert sig.exposure == 0.0


from datetime import date as _date
import src.utils.time_utils as tu


def test_state_roundtrip(tmp_path):
    p = tmp_path / "trend_state.json"
    st = trend.TrendState(last_signal_date="2026-05-29",
                          current_holding="TQQQ", last_exposure=0.6,
                          last_target="TQQQ")
    st.save(str(p))
    st2 = trend.TrendState.load(str(p))
    assert st2.current_holding == "TQQQ"
    assert st2.last_exposure == 0.6
    assert st2.last_target == "TQQQ"


def test_should_run_on_last_trading_day_of_month(monkeypatch):
    d = _date(2026, 5, 29)  # a month-end trading day
    monkeypatch.setattr(tu, "is_last_trading_day_of_month", lambda x: x == d)
    monkeypatch.setattr(tu, "was_last_trading_day_of_month_within",
                        lambda days_back, today: None)
    run, sd = trend.should_run_trend(today=d, state=trend.TrendState())
    assert run is True and sd == d


def test_should_not_run_when_already_done(monkeypatch):
    d = _date(2026, 5, 29)
    monkeypatch.setattr(tu, "is_last_trading_day_of_month", lambda x: x == d)
    st = trend.TrendState(last_signal_date=d.isoformat())
    run, sd = trend.should_run_trend(today=d, state=st)
    assert run is False


def test_should_run_in_grace_window(monkeypatch):
    # Not a month-end day, but a recent month-end was missed within the grace
    # window -> the scheduler should fire for that missed date.
    d = _date(2026, 6, 2)
    missed = _date(2026, 5, 29)
    monkeypatch.setattr(tu, "is_last_trading_day_of_month", lambda x: False)
    monkeypatch.setattr(tu, "was_last_trading_day_of_month_within",
                        lambda days_back, today: missed)
    run, sd = trend.should_run_trend(today=d, state=trend.TrendState())
    assert run is True and sd == missed


def test_grace_window_respects_already_done(monkeypatch):
    # Same missed month-end, but we already executed it -> no re-run.
    d = _date(2026, 6, 2)
    missed = _date(2026, 5, 29)
    monkeypatch.setattr(tu, "is_last_trading_day_of_month", lambda x: False)
    monkeypatch.setattr(tu, "was_last_trading_day_of_month_within",
                        lambda days_back, today: missed)
    st = trend.TrendState(last_signal_date=missed.isoformat())
    run, sd = trend.should_run_trend(today=d, state=st)
    assert run is False


def test_state_load_corrupt_json_returns_fresh(tmp_path):
    p = tmp_path / "trend_state.json"
    p.write_text("{not valid json")
    st = trend.TrendState.load(str(p))
    assert st.last_signal_date is None
    assert st.current_holding is None
    assert st.last_exposure == 0.0
