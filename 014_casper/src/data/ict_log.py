"""ICT decision logger — persistent audit trail of every filter outcome.

Why: when ICT phase 1~4 filters reject most bars (KZ, Displacement,
Sweep+CHoCH, Unicorn, OTE, Multi-TF SL, Daily Bias), we need to know
**which gate killed a candidate and why** — not just that no trade
happened. This logger writes one JSON line per decision to a daily
file under `data/ict_decisions/`.

Format: JSONL (`.jsonl`) — one JSON object per line, easy to grep,
tail, or load with pandas (`pd.read_json(path, lines=True)`).

Safety:
- All writes go through `record()` which is non-raising — failures are
  swallowed with a debug log.
- File is opened in append mode every call (so a crashed process
  doesn't lose previous lines).
- All values are JSON-serialisable (timestamps stringified).
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("casper")


def _default_base() -> Path:
    root = Path(__file__).resolve().parent.parent.parent
    return root / "data" / "ict_decisions"


def _coerce(v: Any) -> Any:
    """Make a value JSON-safe."""
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    if isinstance(v, (list, tuple)):
        return [_coerce(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _coerce(val) for k, val in v.items()}
    return str(v)


def record(
    event: str,
    symbol: Optional[str] = None,
    bar_time: Optional[Any] = None,
    passed: Optional[bool] = None,
    reason: Optional[str] = None,
    details: Optional[dict] = None,
    base: Optional[Path] = None,
) -> None:
    """Append a single decision line to today's ICT decision log.

    Args:
        event: identifier of the gate / event, e.g. "killzone_check",
               "displacement_check", "sweep_choch_check", "unicorn_check",
               "ote_apply", "mtf_sl_apply", "daily_bias", "signal_emit".
        symbol: which symbol the decision is about.
        bar_time: the 5-min bar timestamp (datetime / pd.Timestamp / str).
        passed: True/False if this is a pass/fail gate; None for info-only.
        reason: short text explaining why pass/fail.
        details: dict of numeric / categorical values for later analysis
                 (e.g. {"body_atr_ratio": 1.23, "wick_ratio": 0.31}).

    Never raises.
    """
    try:
        base = base or _default_base()
        base.mkdir(parents=True, exist_ok=True)
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = base / f"{day}.jsonl"
        line = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "symbol": symbol,
            "bar_time": _coerce(bar_time),
            "passed": passed,
            "reason": reason,
            "details": _coerce(details) if details else None,
        }
        # Drop None top-level fields for compactness
        line = {k: v for k, v in line.items() if v is not None}
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception as e:  # never propagate
        logger.debug(f"ict_log.record failed silently: {e}")


def read_day(day: str, base: Optional[Path] = None) -> list[dict]:
    """Read one day's decision log into a list of dicts.

    Args:
        day: "YYYY-MM-DD" string.
    """
    base = base or _default_base()
    path = base / f"{day}.jsonl"
    if not path.exists():
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    return out


def stats(day: str, base: Optional[Path] = None) -> dict:
    """Aggregate counts of events for a day.

    Returns dict like {event: {"pass": n, "fail": n, "info": n}, ...}.
    """
    rows = read_day(day, base)
    agg: dict = {}
    for r in rows:
        ev = r.get("event", "?")
        bucket = agg.setdefault(ev, {"pass": 0, "fail": 0, "info": 0, "total": 0})
        bucket["total"] += 1
        if r.get("passed") is True:
            bucket["pass"] += 1
        elif r.get("passed") is False:
            bucket["fail"] += 1
        else:
            bucket["info"] += 1
    return agg
