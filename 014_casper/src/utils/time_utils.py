"""Time and timezone utilities for Casper Trading Bot."""

from datetime import datetime, time as dtime, date, timedelta
import pytz

ET = pytz.timezone("US/Eastern")
KST = pytz.timezone("Asia/Seoul")


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


def is_weekday() -> bool:
    """True if today is Mon-Fri in ET."""
    return now_et().weekday() < 5


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


def is_past_be_time() -> bool:
    """True if past 11:00 AM ET (breakeven stop move time)."""
    return current_time_et() >= dtime(11, 0)


def is_force_close_time() -> bool:
    """True if at or past 15:50 ET (force close)."""
    return current_time_et() >= dtime(15, 50)


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
