"""ICT Killzone (intraday session) helpers.

ICT divides the regular session into "killzones" — narrow windows
where institutional liquidity is most concentrated. Casper's Phase 1
pre-check (PHASE1_PRECHECK.md) showed AM_MACRO (09:30~10:10) had
WR 71.4% vs AM_LATE 25.0% across 11 live trades.

All times are US/Eastern (ET).
"""

from datetime import time as dtime
from typing import Iterable, Optional

import pandas as pd


KILLZONES: dict[str, tuple[dtime, dtime]] = {
    "AM_MACRO":  (dtime(9, 30),  dtime(10, 10)),
    "AM_LATE":   (dtime(10, 10), dtime(10, 55)),
    "PRE_LUNCH": (dtime(11, 10), dtime(12, 0)),
    "PM_MACRO":  (dtime(13, 30), dtime(14, 0)),
    "PM_LATE":   (dtime(15, 15), dtime(15, 45)),
}


def killzone_for(ts) -> Optional[str]:
    """Return the killzone name that contains ts (ET), or None.

    Args:
        ts: pandas Timestamp (any timezone — will use .time()) or datetime.time.
    """
    if isinstance(ts, dtime):
        t = ts
    elif hasattr(ts, "time"):
        # convert to ET first if tz-aware
        if getattr(ts, "tz", None) is not None:
            ts = ts.tz_convert("US/Eastern")
        t = ts.time()
    else:
        return None
    for name, (start, end) in KILLZONES.items():
        if start <= t < end:
            return name
    return None


def in_allowed_killzones(ts, allowed: Optional[Iterable[str]]) -> bool:
    """True if ts is in one of the allowed killzones.

    Returns True unconditionally when allowed is None or empty (filter disabled).
    """
    if not allowed:
        return True
    zone = killzone_for(ts)
    return zone in set(allowed)
