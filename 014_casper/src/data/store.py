"""Parquet-based 5-min bar persistence.

Atomic write: writes to *.tmp then renames into place. One file per
(symbol, day). Symbols starting with '^' are mapped to '_' on disk to
keep paths filesystem-safe.

Schema (Parquet, Snappy-compressed):
    timestamp : int64   (epoch milliseconds, UTC)
    open      : float32
    high      : float32
    low       : float32
    close     : float32
    volume    : int64
    source    : string  ("kis" or "yfinance")
"""

import os
from pathlib import Path
from typing import Optional

import pandas as pd


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "_")


def _path_for(base, symbol: str, date_str: str) -> Path:
    sym = _safe_symbol(symbol)
    year = date_str[:4]
    return Path(base) / sym / year / f"{date_str}.parquet"


def save_bars(base, symbol: str, date_str: str, bars: pd.DataFrame, source: str):
    """Save bars for one day atomically.

    Args:
        base: root directory (e.g. data/marketdata)
        symbol: e.g. "TQQQ" or "^VIX"
        date_str: "YYYY-MM-DD"
        bars: DataFrame with columns Open/High/Low/Close/Volume, datetime index (any tz)
        source: "kis" or "yfinance"

    Returns:
        Path to the written file, or None if bars is empty.
    """
    if bars is None or bars.empty:
        return None
    final_path = _path_for(base, symbol, date_str)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_suffix(".tmp")

    idx = bars.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")

    out = pd.DataFrame({
        "timestamp": (idx.view("int64") // 1_000_000).astype("int64"),
        "open":   bars["Open"].astype("float32").values,
        "high":   bars["High"].astype("float32").values,
        "low":    bars["Low"].astype("float32").values,
        "close":  bars["Close"].astype("float32").values,
        "volume": bars["Volume"].astype("int64").values,
        "source": [source] * len(bars),
    })

    out.to_parquet(tmp_path, engine="pyarrow", compression="snappy", index=False)
    os.replace(tmp_path, final_path)
    return final_path


def load_bars(base, symbol: str, date_str: str) -> Optional[pd.DataFrame]:
    """Load one day's bars. Returns None if file does not exist."""
    p = _path_for(base, symbol, date_str)
    if not p.exists():
        return None
    return pd.read_parquet(p)


def has_data(base, symbol: str, date_str: str) -> bool:
    return _path_for(base, symbol, date_str).exists()


def stats(base) -> dict:
    """Aggregate stats for the marketdata directory.

    Returns dict with total_files / total_bytes / symbols breakdown.
    """
    base = Path(base)
    if not base.exists():
        return {"total_files": 0, "total_bytes": 0, "symbols": {}}
    total_files = 0
    total_bytes = 0
    sym_stat: dict = {}
    for sym_dir in sorted(base.iterdir()):
        if not sym_dir.is_dir():
            continue
        files = list(sym_dir.rglob("*.parquet"))
        sz = sum(f.stat().st_size for f in files)
        sym_stat[sym_dir.name] = {"days": len(files), "bytes": sz}
        total_files += len(files)
        total_bytes += sz
    return {"total_files": total_files, "total_bytes": total_bytes, "symbols": sym_stat}
