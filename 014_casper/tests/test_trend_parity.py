import os
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
CACHE = os.path.join(SCRIPTS, "out", "zoo_data")

pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join(CACHE, "TQQQ.parquet")),
    reason="requires cached zoo data (run scripts/strategy_zoo_backtest.py once)")


def _load(sym):
    df = pd.read_parquet(os.path.join(CACHE, f"{sym}.parquet"))
    df.index = pd.to_datetime(df.index)
    # Normalize to expose a single 'Close' column regardless of stored schema.
    if "Close" not in df.columns:
        for cand in ("close", "Adj Close", "adj_close", "Adj_Close"):
            if cand in df.columns:
                df = df.rename(columns={cand: "Close"})
                break
    return df


def test_signal_matches_harness_on_month_ends():
    from src.core import trend
    qqq, tqqq = _load("QQQ"), _load("TQQQ")
    PARAMS = {"signal_symbol": "QQQ", "sma_period": 200, "asset": "TQQQ",
              "safe_asset": "BIL", "target_vol": 0.40, "vol_lookback": 20}
    idx = qqq.index
    me = idx.to_series().groupby([idx.year, idx.month]).max()
    sample = [d for d in me if 2018 <= d.year <= 2024][::6][:10]
    assert sample, "no month-end sample dates found"
    n_on = n_off = 0
    for d in sample:
        # feed only history up to and including d (no look-ahead)
        sub = {"QQQ": qqq.loc[:d, ["Close"]], "TQQQ": tqqq.loc[:d, ["Close"]]}
        sig = trend.compute_trend_signal(today=d.date(), params=PARAMS, data=sub)
        # harness logic, recomputed inline:
        sma = qqq["Close"].loc[:d].rolling(200).mean().iloc[-1]
        regime = bool(qqq["Close"].loc[:d].iloc[-1] > sma)
        assert sig.regime == regime, f"{d}: regime mismatch"
        if regime:
            n_on += 1
            rv = tqqq["Close"].loc[:d].pct_change().rolling(20).std().iloc[-1] * (252 ** 0.5)
            # trend.py stores exposure as round(exposure, 4); allow that quantization.
            assert abs(sig.exposure - min(1.0, 0.40 / rv)) < 1e-4, f"{d}: exposure mismatch"
        else:
            n_off += 1
            assert sig.target_symbol == "BIL", f"{d}: regime-off should be BIL"
            assert sig.exposure == 0.0, f"{d}: regime-off exposure must be 0"
    # Guard against the sample silently collapsing to a single regime again:
    assert n_on > 0, "sample covers no regime-ON month-ends"
    assert n_off > 0, "sample covers no regime-OFF month-ends"
