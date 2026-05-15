"""Time and timezone utilities for Casper Trading Bot."""

import json
import logging
import os
from datetime import datetime, time as dtime, date, timedelta
from typing import Optional
import pytz

logger = logging.getLogger("casper")

ET = pytz.timezone("US/Eastern")
KST = pytz.timezone("Asia/Seoul")

# Load US market holidays
_HOLIDAYS_FILE = os.path.join(os.path.dirname(__file__), "..", "..", "config", "us_holidays.json")
_us_holidays: set = set()


def _load_holidays() -> set:
    """Load US holiday dates from config file."""
    global _us_holidays
    if _us_holidays:
        return _us_holidays
    try:
        with open(_HOLIDAYS_FILE, "r") as f:
            data = json.load(f)
        for year_key, dates in data.items():
            if year_key.startswith("_"):
                continue
            for d in dates:
                _us_holidays.add(d)
    except FileNotFoundError:
        logger.warning(f"Holiday file not found: {_HOLIDAYS_FILE} — weekday-only fallback")
    except json.JSONDecodeError as e:
        logger.warning(f"Holiday file parse error: {e} — weekday-only fallback")
    return _us_holidays


def now_et() -> datetime:
    """Current time in US/Eastern."""
    return datetime.now(ET)


def now_kst() -> datetime:
    """Current time in KST."""
    return datetime.now(KST)


def today_et() -> date:
    """Today's date in ET."""
    return now_et().date()


def current_time_et() -> dtime:
    """Current time-of-day in ET."""
    return now_et().time()


def is_trading_day() -> bool:
    """True if today is a trading day (weekday and not a US market holiday)."""
    now = now_et()
    if now.weekday() >= 5:
        return False
    holidays = _load_holidays()
    return now.strftime("%Y-%m-%d") not in holidays


def is_weekday() -> bool:
    """True if today is a trading day (Mon-Fri, not a US holiday)."""
    return is_trading_day()


def is_market_open() -> bool:
    """True if within regular market hours (09:30-16:00 ET)."""
    t = current_time_et()
    return dtime(9, 30) <= t <= dtime(16, 0) and is_weekday()


def is_pre_market() -> bool:
    """True if in pre-market check window (08:00-09:29 ET)."""
    t = current_time_et()
    return dtime(8, 0) <= t < dtime(9, 30) and is_weekday()


def is_orb_forming() -> bool:
    """True if in ORB formation period (09:30-09:44 ET)."""
    t = current_time_et()
    return dtime(9, 30) <= t < dtime(9, 45) and is_weekday()


def is_scan_window() -> bool:
    """True if in scanning window (09:45-10:55 ET)."""
    t = current_time_et()
    return dtime(9, 45) <= t <= dtime(10, 55) and is_weekday()


def is_after_hours() -> bool:
    """True if past regular market close (16:00 ET) on weekdays."""
    return current_time_et() >= dtime(16, 0) and is_weekday()


def is_next_day_open() -> bool:
    """True if market just opened (09:30-09:35 ET) — for overnight position cleanup."""
    t = current_time_et()
    return dtime(9, 30) <= t < dtime(9, 35) and is_weekday()


def is_past_be_time() -> bool:
    """True if past 11:00 AM ET (breakeven stop move time) on weekdays."""
    return current_time_et() >= dtime(11, 0) and is_weekday()


def is_force_close_time() -> bool:
    """True if at or past 15:50 ET (force close) on weekdays."""
    return current_time_et() >= dtime(15, 50) and is_weekday()


def get_week_number() -> int:
    """ISO week number in ET."""
    return now_et().isocalendar()[1]


def seconds_until(target: dtime) -> float:
    """Seconds from now until target time today (ET). Negative if past."""
    now = now_et()
    target_dt = ET.localize(datetime.combine(now.date(), target))
    return (target_dt - now).total_seconds()


def format_et(dt: datetime) -> str:
    """Format datetime for display."""
    return dt.strftime("%Y-%m-%d %H:%M:%S ET")


# ─────────────────────────────────────────────────────────────────────
# Trading-day helpers for monthly / quarterly schedulers (GEM, SPMO drift)
# ─────────────────────────────────────────────────────────────────────
# Why these live here:
#   GEM (Antonacci dual momentum) needs to rebalance on the LAST trading
#   day of every month — but "last day" is rarely the calendar last day
#   because of weekends and NYSE holidays (e.g. Memorial Day, Good Friday,
#   Thanksgiving, Christmas, …). A 1-day miss can change SPY vs VEU
#   ranking. So we resolve trading days from the same holiday file the
#   Casper bot already trusts.
#
# Late-execution grace:
#   If the bot crashes on the last trading day, it must still rebalance
#   the *next* trading day (which is the first trading day of the next
#   month). We expose `was_last_trading_day_within(N)` helper for that.

def _is_trading_date(d: date) -> bool:
    """Pure helper — True if d is a weekday and not a US holiday."""
    if d.weekday() >= 5:
        return False
    holidays = _load_holidays()
    return d.strftime("%Y-%m-%d") not in holidays


def previous_trading_day(d: date) -> date:
    """Closest trading day strictly before d."""
    cur = d - timedelta(days=1)
    while not _is_trading_date(cur):
        cur -= timedelta(days=1)
    return cur


def next_trading_day(d: date) -> date:
    """Closest trading day strictly after d."""
    cur = d + timedelta(days=1)
    while not _is_trading_date(cur):
        cur += timedelta(days=1)
    return cur


def get_last_trading_day_of_month(year: int, month: int) -> date:
    """Last NYSE trading day in the given (year, month).

    Walks backwards from the calendar last day until a trading day is
    found. Always returns *some* date — if no holiday data is loaded,
    falls back to last weekday.
    """
    # Calendar last day of month
    if month == 12:
        first_next = date(year + 1, 1, 1)
    else:
        first_next = date(year, month + 1, 1)
    d = first_next - timedelta(days=1)
    while not _is_trading_date(d):
        d -= timedelta(days=1)
    return d


def get_first_trading_day_of_month(year: int, month: int) -> date:
    """First NYSE trading day in the given (year, month)."""
    d = date(year, month, 1)
    while not _is_trading_date(d):
        d += timedelta(days=1)
    return d


def is_last_trading_day_of_month(d: Optional[date] = None) -> bool:
    """True if d (default = today ET) is the last trading day of its month."""
    if d is None:
        d = today_et()
    if not _is_trading_date(d):
        return False
    return d == get_last_trading_day_of_month(d.year, d.month)


def is_first_trading_day_of_month(d: Optional[date] = None) -> bool:
    """True if d (default = today ET) is the first trading day of its month."""
    if d is None:
        d = today_et()
    if not _is_trading_date(d):
        return False
    return d == get_first_trading_day_of_month(d.year, d.month)


def was_last_trading_day_of_month_within(days_back: int = 3,
                                         today: Optional[date] = None) -> Optional[date]:
    """Late-execution helper.

    Look back up to `days_back` trading days from `today` (ET). If any of
    those was the last trading day of its month, return that date. Used by
    the GEM scheduler so a missed rebalance (bot crash, network outage)
    is still executed within a short grace window instead of waiting a
    full month.

    Returns None if no recent date qualifies.
    """
    if today is None:
        today = today_et()
    cur = today
    for _ in range(days_back + 1):  # include today
        if _is_trading_date(cur) and is_last_trading_day_of_month(cur):
            return cur
        cur = previous_trading_day(cur)
    return None


def is_last_trading_day_of_quarter(d: Optional[date] = None) -> bool:
    """True if d (default = today ET) is the last trading day of a quarter
    (Mar/Jun/Sep/Dec)."""
    if d is None:
        d = today_et()
    if d.month not in (3, 6, 9, 12):
        return False
    return is_last_trading_day_of_month(d)


def trading_days_between(start: date, end: date) -> int:
    """Count NYSE trading days in (start, end] — exclusive of start.

    Used for GEM 12-month-return lookback validation and for measuring
    how stale a cached signal is.
    """
    if end <= start:
        return 0
    cur = start
    count = 0
    while cur < end:
        cur = cur + timedelta(days=1)
        if _is_trading_date(cur):
            count += 1
    return count


# Import-time sanity: surface a clear warning if no holidays loaded so
# downstream schedulers don't silently miss key cutoff dates (e.g. trying
# to rebalance on Good Friday).
def _check_holiday_data_loaded() -> bool:
    hs = _load_holidays()
    if not hs:
        logger.warning(
            "time_utils: NO holiday data loaded — monthly/quarterly schedulers "
            "will only respect weekends. Update config/us_holidays.json."
        )
        return False
    return True


_check_holiday_data_loaded()
