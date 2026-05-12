"""Persistent trade history storage.

Stores all trades in JSON files (one per year). Never deletes data.
Loaded on startup to restore circuit breaker state and cumulative stats.
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger("casper")

TRADES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "trades")


def _ensure_dir():
    os.makedirs(TRADES_DIR, exist_ok=True)


def _get_filepath(year: Optional[int] = None) -> str:
    if year is None:
        year = datetime.now().year
    return os.path.join(TRADES_DIR, f"trades_{year}.json")


def load_trades(year: Optional[int] = None) -> List[dict]:
    """Load all trades for a given year."""
    _ensure_dir()
    filepath = _get_filepath(year)
    if not os.path.exists(filepath):
        return []
    try:
        with open(filepath, "r") as f:
            trades = json.load(f)
        logger.info(f"TradeStore: Loaded {len(trades)} trades from {os.path.basename(filepath)}")
        return trades
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"TradeStore: Error loading {filepath}: {e}")
        return []


def save_trade(trade: dict, year: Optional[int] = None) -> None:
    """Append a single trade to the year's file (atomic write)."""
    _ensure_dir()
    trades = load_trades(year)
    trades.append(trade)
    filepath = _get_filepath(year)
    try:
        tmp = filepath + ".tmp"
        with open(tmp, "w") as f:
            json.dump(trades, f, indent=2, default=str)
        os.replace(tmp, filepath)
        logger.info(f"TradeStore: Saved trade #{len(trades)} to {os.path.basename(filepath)}")
    except IOError as e:
        logger.error(f"TradeStore: Error saving to {filepath}: {e}")


def trade_from_position(position, ict_meta: Optional[dict] = None) -> dict:
    """Convert a closed Position object to a trade dict for storage.

    Args:
        position: closed Position object.
        ict_meta: optional dict with ICT-phase computed indicators captured
                  at signal time. Keys recognised (all optional):
                    killzone               : 'AM_MACRO' | 'AM_LATE' | ...
                    displacement_passed    : bool
                    disp_body_atr_ratio    : float
                    disp_wick_ratio        : float
                    sweep_choch_passed     : bool
                    sweep_level            : float
                    sweep_breach_pct       : float
                    daily_bias_direction   : 'bull' | 'bear' | 'neutral'
                    daily_bias_score       : int
                    filters_active         : list[str]   # which gates were ON
    """
    from src.utils.time_utils import get_week_number
    base = {
        "date": position.signal.orb.date,
        "week": get_week_number(),
        "symbol": position.symbol,
        "direction": position.direction,
        "entry_price": position.entry_price,
        "stop_loss": position.original_stop,
        "take_profit": position.take_profit,
        "exit_price": position.exit_price,
        "exit_reason": position.exit_reason,
        "shares": position.shares,
        "risk_per_share": position.risk_per_share,
        "gross_pnl": round(position.gross_pnl, 2),
        "commission": round(position.commission, 2),
        "net_pnl": round(position.net_pnl, 2),
        "r_multiple": round(position.r_multiple, 2),
        "result": position.result,
        "entry_time": position.entry_time,
        "exit_time": position.exit_time,
        "orb_high": position.signal.orb.high,
        "orb_low": position.signal.orb.low,
        "fvg_top": position.signal.fvg.top,
        "fvg_bottom": position.signal.fvg.bottom,
        "trend": position.direction,
        "capital_after": None,
    }
    if ict_meta:
        # nest under "ict" to keep top-level schema stable; old readers ignore it
        base["ict"] = {k: v for k, v in ict_meta.items() if v is not None}
    return base


def update_last_trade(updates: dict, year: Optional[int] = None) -> None:
    """Update the most recent trade with broker settlement data."""
    _ensure_dir()
    trades = load_trades(year)
    if not trades:
        logger.warning("TradeStore: No trades to update")
        return
    trades[-1].update(updates)
    filepath = _get_filepath(year)
    try:
        tmp = filepath + ".tmp"
        with open(tmp, "w") as f:
            json.dump(trades, f, indent=2, default=str)
        os.replace(tmp, filepath)
        logger.info(f"TradeStore: Updated last trade with broker data")
    except IOError as e:
        logger.error(f"TradeStore: Error updating {filepath}: {e}")


def get_cumulative_stats(trades: List[dict]) -> dict:
    """Calculate cumulative statistics from trade history."""
    if not trades:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "bes": 0,
            "win_rate": 0.0, "total_pnl": 0.0, "profit_factor": 0.0,
        }

    wins = [t for t in trades if t["result"] == "WIN"]
    losses = [t for t in trades if t["result"] == "LOSS"]
    bes = [t for t in trades if t["result"] == "BE"]

    total_wins = sum(t["net_pnl"] for t in wins)
    total_losses = abs(sum(t["net_pnl"] for t in losses))
    pf = total_wins / total_losses if total_losses > 0 else float("inf")
    n = len(trades)
    wr = len(wins) / n * 100 if n > 0 else 0.0

    return {
        "total_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "bes": len(bes),
        "win_rate": round(wr, 1),
        "total_pnl": round(sum(t["net_pnl"] for t in trades), 2),
        "profit_factor": round(pf, 2),
    }
