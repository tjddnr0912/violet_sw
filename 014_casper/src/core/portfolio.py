"""Multi-bucket portfolio manager for Casper Trading Bot.

Splits a single KIS USD account into independently-managed buckets:

  • SPMO   — long-only momentum ETF (buy-and-hold, quarterly drift check)
  • GEM    — Antonacci dual momentum (SPY / VEU / AGG, monthly rotation)
  • CASPER — ORB+FVG intraday TQQQ/SQQQ (the existing bot logic)
  • MTUM / QUAL — extra factor ETFs unlocked at higher capital tiers
  • CLENOW — momentum stock screen (top-N S&P 500)  ($10k+ tier)
  • TQQQ_SMA — single-asset 200-day SMA trend  ($10k+ tier)

Bucket weights are *automatically* selected from the current total
portfolio value via `tier_for_capital()`. This is the P4 auto-enable:
as the account grows, new buckets switch on without manual config edits.

Drift detection (P3):
  Each bucket's actual USD value is compared to its target USD value
  (total × target_weight). If |drift_pct| > drift_threshold AND today is
  a quarter-end trading day, the bot rebalances by selling the over-
  allocated bucket and buying the under-allocated one.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional

from src.utils import time_utils

logger = logging.getLogger("casper")

PORTFOLIO_STATE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "portfolio_state.json"
)

# ─────────────────────────────────────────────────────────────────────
# Tier table — P4 auto-enable
# ─────────────────────────────────────────────────────────────────────
# Why a *function* and not a static JSON:
#   The bot re-evaluates tier on every daily tick. When capital crosses
#   $5,000 or $10,000, the new bucket activates immediately on the next
#   quarterly rebalance — no manual config edit needed. JSON would
#   demand a deploy.
#
# Why these tiers in particular:
#   $3,000  — single ETF positions still meaningful ($600 × 3 buckets).
#             Clenow's 20-stock screen would put only $30/stock — useless,
#             so it's withheld until $10k.
#   $5,000  — adds MTUM + QUAL slices so the "factor core" diversifies
#             beyond SPMO's heavy AI-mega-cap tilt.
#   $10,000 — Clenow becomes feasible: $2,500 / 25 stocks ≈ $100/stock
#             which buys 1+ share of most S&P 500 names.

def tier_for_capital(total_usd: float) -> dict:
    """Return target bucket weights for the current account size.

    Each value sums to 1.0. Unused buckets (not in the dict) are simply
    absent — the bot treats them as 0%.
    """
    if total_usd < 3000:
        # Pre-seed tier: just GEM (lowest cost, simplest, lowest MaxDD).
        return {"gem": 1.00}
    if total_usd < 5000:
        return {"spmo": 0.50, "gem": 0.30, "casper": 0.20}
    if total_usd < 10000:
        return {"spmo": 0.40, "mtum": 0.10, "qual": 0.10,
                "gem": 0.20, "casper": 0.20}
    # $10,000+: 6 buckets, max diversification.
    return {"spmo": 0.30, "mtum": 0.10, "qual": 0.10,
            "clenow": 0.20, "tqqq_sma": 0.10,
            "gem": 0.15, "casper": 0.05}


# Symbol mapping per bucket — used by the rebalancer when it must pick
# a default ticker. GEM's actual target rotates per-month (see gem.py)
# so its symbol is None here.
BUCKET_DEFAULT_SYMBOL = {
    "spmo":     "SPMO",
    "mtum":     "MTUM",
    "qual":     "QUAL",
    "clenow":   None,        # multi-stock screen — handled separately
    "tqqq_sma": "TQQQ",      # actual holding alternates with BIL
    "gem":      None,        # rotates SPY/VEU/AGG
    "casper":   None,        # rotates TQQQ/SQQQ intraday
}


# Ticker → KIS exchange code. KIS rejects price + order requests when
# the exchange doesn't match the ticker's listing venue:
#   * NASD = NASDAQ-listed (TQQQ family, QQQ)
#   * AMEX = NYSE Arca-listed (factor ETFs, GEM rotation universe).
# The bot's original code defaulted everything to NASD because that
# was correct for the original TQQQ/SQQQ-only universe. Multi-bucket
# adds Arca-listed names, so each call site must pass the right venue.
TICKER_EXCHANGE = {
    "TQQQ": "NASD", "SQQQ": "NASD", "QQQ": "NASD",
    "SPMO": "AMEX", "MTUM": "AMEX", "QUAL": "AMEX",
    "SPY":  "AMEX", "VEU":  "AMEX", "AGG":  "AMEX", "BIL": "AMEX",
}


def exchange_for(symbol: str) -> str:
    """KIS exchange code for a given ticker. Defaults to NASD so unknown
    symbols don't silently swap venues — calling code can detect a wrong
    default via a failed price fetch and add the symbol to TICKER_EXCHANGE.
    """
    return TICKER_EXCHANGE.get((symbol or "").upper(), "NASD")


# ─────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────


@dataclass
class Bucket:
    """One allocation slice of the account.

    Stored fields are *targets* and *snapshots*; actual holdings come
    from the KIS balance API (live source of truth).
    """
    name: str
    target_weight: float        # 0.0 ~ 1.0
    target_usd: float = 0.0     # computed from total × weight
    current_value_usd: float = 0.0
    current_symbol: Optional[str] = None
    last_rebalance_date: Optional[str] = None

    @property
    def drift_pct(self) -> float:
        """How far the bucket value is from its target, in percentage points
        of total portfolio.  +ve = over-allocated, -ve = under-allocated."""
        if self.target_usd <= 0:
            return 0.0
        return (self.current_value_usd - self.target_usd) / self.target_usd


@dataclass
class PortfolioState:
    """Persisted snapshot of last evaluation.

    NOT the source of truth for holdings — KIS balance is. This is a
    cache + tier-transition trace so we can log "tier changed $4,800 → $5,100".

    `seeded_at` is the one-shot guard for the initial-seed step (first-run
    auto-allocation). Once non-None the bot will never auto-buy a bucket
    from cash again — only quarterly drift rebalances will fire.
    """
    last_eval_date: Optional[str] = None
    last_total_usd: float = 0.0
    last_tier_key: Optional[str] = None
    buckets: dict = field(default_factory=dict)
    seeded_at: Optional[str] = None    # ISO date or None

    @classmethod
    def load(cls, path: str = PORTFOLIO_STATE_FILE) -> "PortfolioState":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return cls(
                last_eval_date=data.get("last_eval_date"),
                last_total_usd=float(data.get("last_total_usd", 0)),
                last_tier_key=data.get("last_tier_key"),
                buckets=data.get("buckets", {}),
                seeded_at=data.get("seeded_at"),
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Portfolio state load failed ({e}) — fresh init")
            return cls()

    def save(self, path: str = PORTFOLIO_STATE_FILE) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)


# Cash threshold for "this account is mostly cash" detection (90%).
# Above this, initial-seed runs. Below, we assume the user already has
# positions and skip the seed (only quarterly drift will fire).
CASH_RATIO_FOR_SEED = 0.90


def needs_initial_seed(total_usd: float,
                       holdings: dict,
                       state: PortfolioState) -> bool:
    """Decide if first-run auto-allocation should fire.

    Conditions (ALL must hold):
      1. state.seeded_at is None (never seeded before)
      2. cash ratio >= 90% (account is mostly cash)
      3. total_usd >= $100 (not a phantom $0 account)

    The cash-ratio guard prevents the bot from over-buying when the user
    already has positions from a previous setup or different strategy.
    """
    if state.seeded_at is not None:
        return False
    if total_usd < 100:
        return False
    position_value = sum(
        float(h.get("value_usd", 0)) for h in holdings.values()
    )
    cash = total_usd - position_value
    if total_usd <= 0:
        return False
    cash_ratio = cash / total_usd
    return cash_ratio >= CASH_RATIO_FOR_SEED


# ─────────────────────────────────────────────────────────────────────
# Manager
# ─────────────────────────────────────────────────────────────────────


def tier_key(weights: dict) -> str:
    """Compact stable key for a tier (used to detect tier changes)."""
    return ",".join(f"{k}={v:.2f}" for k, v in sorted(weights.items()))


def evaluate_portfolio(total_usd: float,
                       holdings: dict[str, dict],
                       state: Optional[PortfolioState] = None,
                       today: Optional[date] = None) -> tuple[list[Bucket], dict]:
    """Compute current bucket allocation vs targets.

    Args:
      total_usd: Total KIS USD account value (cash + market value of all
                 positions). Source: `KISClient.get_balance()`.
      holdings:  Per-symbol holding info as returned by the KIS balance
                 endpoint, e.g.
                 {"SPMO": {"qty": 12, "value_usd": 1450.0},
                  "TQQQ": {"qty": 8,  "value_usd": 320.0}, ...}
                 Cash is NOT a holding — it's implicit in total_usd.
      state:     Optional previous PortfolioState (load from disk if None).
      today:     Override for testing (default = ET today).

    Returns:
      (buckets: list[Bucket], info: dict)
      info contains: tier_changed (bool), prev_tier, new_tier,
                     symbols_by_bucket (mapping for the rebalancer).
    """
    if state is None:
        state = PortfolioState.load()
    if today is None:
        today = time_utils.today_et()

    weights = tier_for_capital(total_usd)
    new_tier = tier_key(weights)
    tier_changed = (state.last_tier_key is not None
                    and state.last_tier_key != new_tier)

    if tier_changed:
        logger.info(
            f"Portfolio tier changed: total=${total_usd:.2f} "
            f"prev={state.last_tier_key} → new={new_tier}"
        )

    # Build buckets list with current values.
    # SPMO/MTUM/QUAL/TQQQ_SMA — single-symbol value lookup.
    # GEM — value held in whichever of SPY/VEU/AGG is currently in this account.
    # CASPER — value held in TQQQ or SQQQ (the bot's working asset).
    # CLENOW — sum of holdings outside of the symbols claimed by other buckets.

    buckets: list[Bucket] = []
    claimed_symbols: set[str] = set()

    def _bucket_value(name: str) -> tuple[float, Optional[str]]:
        """Resolve the current USD value + symbol for a bucket."""
        if name == "gem":
            for sym in ("SPY", "VEU", "AGG"):
                h = holdings.get(sym, {})
                if h.get("qty", 0) > 0:
                    claimed_symbols.add(sym)
                    return float(h.get("value_usd", 0)), sym
            return 0.0, None
        if name == "casper":
            for sym in ("TQQQ", "SQQQ"):
                h = holdings.get(sym, {})
                if h.get("qty", 0) > 0:
                    claimed_symbols.add(sym)
                    return float(h.get("value_usd", 0)), sym
            return 0.0, None
        if name == "tqqq_sma":
            for sym in ("TQQQ", "BIL"):
                h = holdings.get(sym, {})
                if h.get("qty", 0) > 0:
                    claimed_symbols.add(sym)
                    return float(h.get("value_usd", 0)), sym
            return 0.0, None
        if name == "clenow":
            # Will be filled after other buckets claim their symbols.
            return 0.0, None
        sym = BUCKET_DEFAULT_SYMBOL.get(name)
        if sym is None:
            return 0.0, None
        h = holdings.get(sym, {})
        if h.get("qty", 0) > 0:
            claimed_symbols.add(sym)
            return float(h.get("value_usd", 0)), sym
        return 0.0, sym

    for name, w in weights.items():
        val, sym = _bucket_value(name)
        b = Bucket(
            name=name,
            target_weight=w,
            target_usd=round(total_usd * w, 2),
            current_value_usd=round(val, 2),
            current_symbol=sym,
            last_rebalance_date=state.buckets.get(name, {}).get("last_rebalance_date"),
        )
        buckets.append(b)

    # Clenow gets the residual stock holdings (everything not yet claimed)
    for b in buckets:
        if b.name != "clenow":
            continue
        residual = 0.0
        for sym, h in holdings.items():
            if sym in claimed_symbols:
                continue
            if h.get("qty", 0) > 0:
                residual += float(h.get("value_usd", 0))
        b.current_value_usd = round(residual, 2)

    info = {
        "tier_changed": tier_changed,
        "prev_tier": state.last_tier_key,
        "new_tier": new_tier,
        "weights": weights,
    }
    return buckets, info


def needs_rebalance(buckets: list[Bucket],
                    drift_threshold: float = 0.10,
                    today: Optional[date] = None) -> list[Bucket]:
    """Return buckets whose drift exceeds the threshold AND eligible to
    rebalance today.

    Eligibility rule:
      * SPMO/MTUM/QUAL/TQQQ_SMA — only on quarter-end (Mar/Jun/Sep/Dec
        last trading day).  Buy-and-hold philosophy: avoid over-trading.
      * CLENOW — same as above (quarter-end). Weekly bucket-internal
        rebalance is handled inside the Clenow module, not here.
      * GEM    — never via this path (its own monthly scheduler handles it).
      * CASPER — never via this path (its own daily bot loop handles it).
    """
    if today is None:
        today = time_utils.today_et()
    if not time_utils.is_last_trading_day_of_quarter(today):
        return []

    drifted = []
    for b in buckets:
        if b.name in ("gem", "casper"):
            continue   # owned by their own scheduler
        if b.target_usd <= 0:
            continue
        if abs(b.drift_pct) >= drift_threshold:
            drifted.append(b)
    return drifted


def save_evaluation(buckets: list[Bucket],
                    total_usd: float,
                    state: PortfolioState,
                    info: dict,
                    today: Optional[date] = None) -> None:
    """Persist the evaluation snapshot (cache + audit)."""
    if today is None:
        today = time_utils.today_et()
    state.last_eval_date = today.isoformat()
    state.last_total_usd = float(total_usd)
    state.last_tier_key = info["new_tier"]
    state.buckets = {
        b.name: {
            "target_weight": b.target_weight,
            "target_usd": b.target_usd,
            "current_value_usd": b.current_value_usd,
            "current_symbol": b.current_symbol,
            "drift_pct": round(b.drift_pct, 4),
            "last_rebalance_date": b.last_rebalance_date,
        }
        for b in buckets
    }
    state.save()
