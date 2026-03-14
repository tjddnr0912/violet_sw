"""Market hours logic for US/EU/JP/CN/KR with holiday support."""

from calendar import monthcalendar
from datetime import datetime, date, timedelta

import pytz

from config import MARKET_HOURS

# --- Holiday Cache ---
_holiday_cache: dict[int, set[date]] = {}


def is_market_open(market: str) -> bool:
    """Check if a market is currently open (weekday + within trading hours + not holiday)."""
    cfg = MARKET_HOURS.get(market)
    if not cfg:
        return False

    tz = pytz.timezone(cfg["tz"])
    now = datetime.now(tz)

    # Weekend check
    if now.weekday() >= 5:
        return False

    # US market holiday check
    if market == "US":
        today = now.date()
        holidays = _us_holidays(today.year)
        if today.month == 12:
            holidays = holidays | _us_holidays(today.year + 1)
        if today in holidays:
            return False

    open_h, open_m = cfg["open"]
    close_h, close_m = cfg["close"]

    open_time = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    close_time = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)

    return open_time <= now <= close_time


def get_market_status() -> dict:
    """Return status for all markets."""
    result = {}
    for market, cfg in MARKET_HOURS.items():
        tz = pytz.timezone(cfg["tz"])
        now = datetime.now(tz)
        result[market] = {
            "open": is_market_open(market),
            "time": now.strftime("%H:%M"),
        }
    return result


def is_us_market_hours() -> bool:
    return is_market_open("US")


# --- US Market Holiday Calculation (NYSE/NASDAQ) ---

def _us_holidays(year: int) -> set[date]:
    """Generate US stock market holidays for the given year."""
    if year in _holiday_cache:
        return _holiday_cache[year]

    holidays = set()

    # Fixed holidays (with Saturday->Friday, Sunday->Monday observation)
    fixed = [(1, 1), (6, 19), (7, 4), (12, 25)]
    for month, day in fixed:
        d = date(year, month, day)
        if d.weekday() == 5:       # Saturday -> observe Friday
            holidays.add(d - timedelta(days=1))
        elif d.weekday() == 6:     # Sunday -> observe Monday
            holidays.add(d + timedelta(days=1))
        else:
            holidays.add(d)

    # MLK Day: 3rd Monday of January
    holidays.add(_nth_weekday(year, 1, 0, 3))

    # Presidents' Day: 3rd Monday of February
    holidays.add(_nth_weekday(year, 2, 0, 3))

    # Good Friday: 2 days before Easter
    holidays.add(_easter(year) - timedelta(days=2))

    # Memorial Day: last Monday of May
    holidays.add(_last_weekday(year, 5, 0))

    # Labor Day: 1st Monday of September
    holidays.add(_nth_weekday(year, 9, 0, 1))

    # Thanksgiving: 4th Thursday of November
    holidays.add(_nth_weekday(year, 11, 3, 4))

    _holiday_cache[year] = holidays
    return holidays


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Find the nth occurrence of a weekday in a month (0=Mon..6=Sun)."""
    cal = monthcalendar(year, month)
    count = 0
    for week in cal:
        if week[weekday] != 0:
            count += 1
            if count == n:
                return date(year, month, week[weekday])
    raise ValueError(f"Cannot find {n}th weekday {weekday} in {year}-{month}")


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Find the last occurrence of a weekday in a month."""
    cal = monthcalendar(year, month)
    for week in reversed(cal):
        if week[weekday] != 0:
            return date(year, month, week[weekday])
    raise ValueError(f"Cannot find last weekday {weekday} in {year}-{month}")


def _easter(year: int) -> date:
    """Compute Easter Sunday (Anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l_val = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_val) // 451
    month, day = divmod(h + l_val - 7 * m + 114, 31)
    return date(year, month, day + 1)
