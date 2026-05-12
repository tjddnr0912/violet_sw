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


# ────────────── 1-minute bar persistence (sibling of 5m, isolated path) ──────────────

def _minute_path_for(base, symbol: str, date_str: str) -> Path:
    """`base/<sym>/1m/<year>/<date>.parquet` — kept separate from 5m to avoid clobber."""
    sym = _safe_symbol(symbol)
    year = date_str[:4]
    return Path(base) / sym / "1m" / year / f"{date_str}.parquet"


def save_minute_bars(base, symbol: str, date_str: str, bars: pd.DataFrame, source: str):
    """Atomically persist 1-minute bars for one symbol-day.

    Same schema as save_bars (5m); separate path so 5m and 1m can be
    queried independently. Existing same-day file is overwritten (caller
    is expected to pass the freshest snapshot — partial-day refreshes
    just replace the prior write).
    """
    if bars is None or bars.empty:
        return None
    final_path = _minute_path_for(base, symbol, date_str)
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


def load_minute_bars(base, symbol: str, date_str: str) -> Optional[pd.DataFrame]:
    p = _minute_path_for(base, symbol, date_str)
    if not p.exists():
        return None
    return pd.read_parquet(p)


def has_minute_data(base, symbol: str, date_str: str) -> bool:
    return _minute_path_for(base, symbol, date_str).exists()


# ────────────── Daily bar persistence (one parquet per year) ──────────────

def _daily_path_for(base, symbol: str, year: int) -> Path:
    sym = _safe_symbol(symbol)
    return Path(base) / sym / "daily" / f"{year}.parquet"


def save_daily_bars(base, symbol: str, bars: pd.DataFrame, source: str = "kis"):
    """Save daily bars for one symbol, partitioned by year.

    `bars` is expected to be a DataFrame indexed by date (datetime or date)
    with columns Open/High/Low/Close/Volume. Multiple years are split and
    each year file is rewritten atomically (union of existing + new rows,
    de-duplicated on date, sorted ascending).
    """
    if bars is None or bars.empty:
        return []
    df = bars.copy()
    # Normalise index to tz-naive date for stable grouping
    idx = pd.to_datetime(df.index)
    if hasattr(idx, "tz") and idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    df.index = idx
    df["__year"] = df.index.year
    written: list = []
    for year, sub in df.groupby("__year"):
        sub = sub.drop(columns=["__year"]).copy()
        final_path = _daily_path_for(base, symbol, int(year))
        final_path.parent.mkdir(parents=True, exist_ok=True)

        # Normalise the *new* batch to a canonical OHLCV form
        canon_new = pd.DataFrame({
            "open":   sub["Open"].astype("float32").values,
            "high":   sub["High"].astype("float32").values,
            "low":    sub["Low"].astype("float32").values,
            "close":  sub["Close"].astype("float32").values,
            "volume": (sub["Volume"].fillna(0).astype("int64").values
                       if "Volume" in sub.columns else [0] * len(sub)),
            "source": [source] * len(sub),
        }, index=sub.index)

        # Merge with existing (already in canonical form)
        if final_path.exists():
            old = pd.read_parquet(final_path)
            if "date" in old.columns:
                old = old.set_index(pd.to_datetime(old["date"])).drop(columns=["date"])
            merged = pd.concat([old, canon_new]).sort_index()
            merged = merged[~merged.index.duplicated(keep="last")]
        else:
            merged = canon_new.sort_index()

        out = pd.DataFrame({
            "date":   merged.index.strftime("%Y-%m-%d"),
            "open":   merged["open"].astype("float32").values,
            "high":   merged["high"].astype("float32").values,
            "low":    merged["low"].astype("float32").values,
            "close":  merged["close"].astype("float32").values,
            "volume": merged["volume"].fillna(0).astype("int64").values,
            "source": merged["source"].fillna(source).values,
        })
        tmp = final_path.with_suffix(".tmp")
        out.to_parquet(tmp, engine="pyarrow", compression="snappy", index=False)
        os.replace(tmp, final_path)
        written.append(final_path)
    return written


def load_daily_bars(base, symbol: str, year: int) -> Optional[pd.DataFrame]:
    p = _daily_path_for(base, symbol, year)
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    df.index = pd.to_datetime(df["date"])
    return df


def load_daily_range(base, symbol: str, lookback: int = 60) -> Optional[pd.DataFrame]:
    """Return last `lookback` daily rows for symbol, concatenated across years."""
    from datetime import datetime
    end = datetime.utcnow().date()
    start_year = (end.year - max(1, lookback // 252))
    frames = []
    for y in range(start_year, end.year + 1):
        df = load_daily_bars(base, symbol, y)
        if df is not None:
            frames.append(df)
    if not frames:
        return None
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    return out.tail(lookback)


def daily_last_date(base, symbol: str) -> Optional[str]:
    """Return latest stored date for symbol as 'YYYY-MM-DD', or None."""
    base_p = Path(base) / _safe_symbol(symbol) / "daily"
    if not base_p.exists():
        return None
    years = sorted([int(p.stem) for p in base_p.glob("*.parquet") if p.stem.isdigit()])
    if not years:
        return None
    df = load_daily_bars(base, symbol, years[-1])
    if df is None or df.empty:
        return None
    return df["date"].iloc[-1] if "date" in df.columns else str(df.index[-1].date())


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
