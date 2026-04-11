#!/usr/bin/env python3
"""Update US market holidays in config/us_holidays.json.

Fetches NYSE holiday calendar using exchange_calendars library.
Run once per year (e.g., at the start of each new year).

Usage:
    python scripts/update_holidays.py          # Add next year
    python scripts/update_holidays.py 2028     # Add specific year
    python scripts/update_holidays.py 2028 2029  # Add multiple years

Requirements (script only, not needed for bot runtime):
    pip install exchange_calendars pandas
"""

import json
import os
import sys

import exchange_calendars as xcals
import pandas as pd


def get_holidays(year: int) -> list:
    """Get NYSE holiday dates for a given year."""
    cal = xcals.get_calendar("XNYS")
    all_weekdays = pd.bdate_range(f"{year}-01-01", f"{year}-12-31")
    sessions = cal.sessions_in_range(f"{year}-01-01", f"{year}-12-31")
    holidays = sorted(
        set(all_weekdays.strftime("%Y-%m-%d")) - set(sessions.strftime("%Y-%m-%d"))
    )
    return holidays


def main():
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "us_holidays.json"
    )

    # Parse years from args, default to next year
    if len(sys.argv) > 1:
        years = [int(y) for y in sys.argv[1:]]
    else:
        years = [pd.Timestamp.now().year + 1]

    # Load existing
    with open(config_path) as f:
        data = json.load(f)

    for year in years:
        holidays = get_holidays(year)
        data[str(year)] = holidays
        print(f"{year}: {len(holidays)} holidays added")

    # Write back
    with open(config_path, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Updated: {config_path}")


if __name__ == "__main__":
    main()
