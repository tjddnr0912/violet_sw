"""Market hours logic for US/EU/JP/CN/KR."""

from datetime import datetime
import pytz
from config import MARKET_HOURS


def is_market_open(market: str) -> bool:
    """Check if a market is currently open (weekday + within trading hours)."""
    cfg = MARKET_HOURS.get(market)
    if not cfg:
        return False

    tz = pytz.timezone(cfg["tz"])
    now = datetime.now(tz)

    # Weekend check
    if now.weekday() >= 5:
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
