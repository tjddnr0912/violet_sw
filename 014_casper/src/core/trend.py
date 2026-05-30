"""Low-frequency TQQQ Vol-Target trend sleeve — monthly signal.

Algorithm (matches scripts/strategy_zoo_backtest.make_voltarget_lev):
  regime = QQQ.close > SMA(QQQ.close, sma_period)
  if not regime:  target = safe_asset (BIL), exposure = 0
  else:           realized_vol = std(TQQQ daily returns, vol_lookback) * sqrt(252)
                  exposure = min(1.0, target_vol / realized_vol)
                  target = asset (TQQQ) at `exposure` of the sleeve, rest in safe_asset

Pure logic: no KIS calls. The bot wires compute_trend_signal() into kis_order.
State (last signal date + held asset + exposure) lives in data/trend_state.json.
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, asdict, field
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from src.utils import time_utils

logger = logging.getLogger("casper")

TREND_STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "trend_state.json"
)
GRACE_TRADING_DAYS = 3
TRADING_DAYS = 252

DEFAULT_PARAMS = {
    "signal_symbol": "QQQ", "sma_period": 200, "asset": "TQQQ",
    "safe_asset": "BIL", "target_vol": 0.40, "vol_lookback": 20,
}


@dataclass
class TrendSignal:
    signal_date: str
    target_symbol: str       # "TQQQ" | "BIL"
    exposure: float          # 0.0 .. 1.0 (fraction of the sleeve in `asset`)
    regime: bool             # QQQ > SMA200
    realized_vol: float      # annualized
    reason: str
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _download_daily(symbol: str, today: date, lookback_days: int) -> Optional[pd.DataFrame]:
    """yfinance daily Close frame (auto_adjust). Returns None on failure."""
    try:
        import yfinance as yf
    except Exception as e:                       # pragma: no cover
        logger.error(f"trend: yfinance import failed: {e}")
        return None
    start = today - timedelta(days=lookback_days)
    try:
        df = yf.download(symbol, start=start.isoformat(),
                         end=(today + timedelta(days=1)).isoformat(),
                         auto_adjust=True, progress=False, threads=False)
    except Exception as e:
        logger.error(f"trend: yfinance download {symbol} failed: {e}")
        return None
    if df is None or len(df) == 0:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df[["Close"]]


def compute_trend_signal(today: Optional[date] = None,
                         params: Optional[dict] = None,
                         data: Optional[dict] = None) -> TrendSignal:
    """Compute the trend signal as of `today`'s close.

    `data` (optional): {symbol: DataFrame with 'Close'} for offline/testing.
    When None, downloads QQQ + TQQQ daily history via yfinance.
    Any data shortfall biases to the safe asset (defensive, like gem.py).
    """
    if today is None:
        today = time_utils.today_et()
    p = {**DEFAULT_PARAMS, **(params or {})}
    sig_sym, asset, safe = p["signal_symbol"], p["asset"], p["safe_asset"]
    sma_n, vol_n, tvol = int(p["sma_period"]), int(p["vol_lookback"]), float(p["target_vol"])

    def _close(sym: str) -> Optional[pd.Series]:
        if data is not None:
            df = data.get(sym)
        else:
            df = _download_daily(sym, today, lookback_days=int(sma_n * 1.8) + 60)
        if df is None or "Close" not in df.columns:
            return None
        s = df["Close"].dropna()
        return s if len(s) else None

    qqq = _close(sig_sym)
    tqqq = _close(asset)

    def _safe(reason: str) -> TrendSignal:
        return TrendSignal(today.isoformat(), safe, 0.0, False, float("nan"), reason, p)

    if qqq is None or len(qqq) < sma_n + 1:
        return _safe(f"insufficient {sig_sym} data → {safe}")
    if tqqq is None or len(tqqq) < vol_n + 1:
        return _safe(f"insufficient {asset} data → {safe}")

    sma = qqq.rolling(sma_n).mean().iloc[-1]
    last = float(qqq.iloc[-1])
    regime = bool(last > float(sma))
    if not regime:
        return TrendSignal(today.isoformat(), safe, 0.0, False, float("nan"),
                           f"{sig_sym} {last:.2f} <= SMA{sma_n} {float(sma):.2f} → {safe}", p)

    rv = float(tqqq.pct_change().rolling(vol_n).std().iloc[-1]) * math.sqrt(TRADING_DAYS)
    if not (rv > 0):
        return _safe(f"{asset} realized_vol unavailable → {safe}")
    exposure = min(1.0, tvol / rv)
    return TrendSignal(
        today.isoformat(), asset, round(exposure, 4), True, round(rv, 4),
        f"{sig_sym} > SMA{sma_n}; {asset} vol {rv:.2f} → exposure {exposure:.2f}", p,
    )
