"""NYSE trading calendar helpers.

Thin wrapper around pandas_market_calendars. Used by the data collector
gap-finder and backfill. Keep this module side-effect free.
"""

from datetime import date
from typing import List

import pandas_market_calendars as mcal


_nyse = mcal.get_calendar("NYSE")


def trading_days(start: date, end: date) -> List[date]:
    """Return sorted list of NYSE trading days in [start, end], inclusive."""
    sched = _nyse.schedule(start_date=start, end_date=end)
    return [ts.date() for ts in sched.index]


def is_trading_day(d: date) -> bool:
    """True if d is an NYSE trading day."""
    sched = _nyse.schedule(start_date=d, end_date=d)
    return not sched.empty


def early_close_minutes(d: date) -> int:
    """Minutes from midnight ET for the close.

    Normal day = 16*60 = 960. Early close (e.g. day after Thanksgiving) = 13*60 = 780.
    Returns 0 if the date is not a trading day.
    """
    sched = _nyse.schedule(start_date=d, end_date=d)
    if sched.empty:
        return 0
    close_ts = sched.iloc[0]["market_close"]
    close_et = close_ts.tz_convert("US/Eastern")
    return close_et.hour * 60 + close_et.minute
