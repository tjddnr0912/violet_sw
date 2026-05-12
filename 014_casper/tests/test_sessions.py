"""Tests for src.core.sessions."""

from datetime import time as dtime

import pandas as pd
import pytest

from src.core.sessions import killzone_for, in_allowed_killzones, KILLZONES


def _ts(hour, minute, tz="US/Eastern"):
    return pd.Timestamp(f"2026-05-12 {hour:02d}:{minute:02d}").tz_localize(tz)


def test_killzone_for_am_macro_boundaries():
    assert killzone_for(_ts(9, 30)) == "AM_MACRO"
    assert killzone_for(_ts(9, 45)) == "AM_MACRO"
    assert killzone_for(_ts(10, 9)) == "AM_MACRO"
    # 10:10 is the start of AM_LATE (half-open interval)
    assert killzone_for(_ts(10, 10)) == "AM_LATE"


def test_killzone_for_am_late_boundaries():
    assert killzone_for(_ts(10, 10)) == "AM_LATE"
    assert killzone_for(_ts(10, 30)) == "AM_LATE"
    assert killzone_for(_ts(10, 54)) == "AM_LATE"
    assert killzone_for(_ts(10, 55)) is None  # exclusive end → outside


def test_killzone_for_outside_hours():
    assert killzone_for(_ts(8, 0)) is None
    assert killzone_for(_ts(11, 0)) is None
    assert killzone_for(_ts(12, 30)) is None
    assert killzone_for(_ts(14, 30)) is None
    assert killzone_for(_ts(16, 0)) is None


def test_killzone_for_other_zones():
    assert killzone_for(_ts(11, 30)) == "PRE_LUNCH"
    assert killzone_for(_ts(13, 45)) == "PM_MACRO"
    assert killzone_for(_ts(15, 30)) == "PM_LATE"


def test_killzone_for_with_utc_timestamp():
    # 13:30 UTC = 09:30 ET (DST) — but we treat naive comparisons via .time()
    # so use tz-aware US/Eastern then verify
    et = pd.Timestamp("2026-05-12 09:30:00", tz="US/Eastern")
    utc = et.tz_convert("UTC")
    assert killzone_for(utc) == "AM_MACRO"


def test_killzone_for_dtime_input():
    assert killzone_for(dtime(9, 45)) == "AM_MACRO"
    assert killzone_for(dtime(10, 30)) == "AM_LATE"


def test_killzone_for_returns_none_for_unknown_input():
    assert killzone_for("not a timestamp") is None
    assert killzone_for(None) is None


def test_in_allowed_killzones_filter_disabled_when_empty():
    # None / empty list ⇒ filter disabled (everything passes)
    assert in_allowed_killzones(_ts(11, 0), None) is True
    assert in_allowed_killzones(_ts(11, 0), []) is True


def test_in_allowed_killzones_passes_only_listed():
    allowed = ["AM_MACRO"]
    assert in_allowed_killzones(_ts(9, 45), allowed) is True
    assert in_allowed_killzones(_ts(10, 30), allowed) is False  # AM_LATE
    assert in_allowed_killzones(_ts(11, 30), allowed) is False  # PRE_LUNCH


def test_in_allowed_killzones_multiple_allowed():
    allowed = ["AM_MACRO", "AM_LATE"]
    assert in_allowed_killzones(_ts(9, 45), allowed) is True
    assert in_allowed_killzones(_ts(10, 30), allowed) is True
    assert in_allowed_killzones(_ts(11, 30), allowed) is False


def test_killzones_dict_immutable_interface():
    # Sanity: all expected keys present
    expected = {"AM_MACRO", "AM_LATE", "PRE_LUNCH", "PM_MACRO", "PM_LATE"}
    assert set(KILLZONES.keys()) == expected
    # AM_MACRO is exactly 09:30-10:10
    s, e = KILLZONES["AM_MACRO"]
    assert s == dtime(9, 30) and e == dtime(10, 10)
