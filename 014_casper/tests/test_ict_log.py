"""Tests for src.data.ict_log."""

import json
from datetime import datetime, timezone

import pytest

from src.data.ict_log import record, read_day, stats


def test_record_creates_file_and_appends(tmp_path):
    record(event="killzone_check", symbol="TQQQ", bar_time="2026-05-12 09:45",
           passed=True, details={"kz": "AM_MACRO"}, base=tmp_path)
    record(event="displacement_check", symbol="TQQQ", passed=False,
           reason="body 0.4 < 1.0 ATR", base=tmp_path)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = tmp_path / f"{day}.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    p1 = json.loads(lines[0])
    assert p1["event"] == "killzone_check"
    assert p1["symbol"] == "TQQQ"
    assert p1["passed"] is True
    assert p1["details"] == {"kz": "AM_MACRO"}


def test_record_silent_on_unwritable_path(tmp_path, monkeypatch):
    # Pass an explicit invalid base — function must not raise
    bad = tmp_path / "subdir" / "more"
    record(event="test", base=bad)  # should auto-create
    assert (bad).exists()


def test_record_skips_none_fields(tmp_path):
    record(event="signal_emit", symbol="QQQ", base=tmp_path)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    line = json.loads((tmp_path / f"{day}.jsonl").read_text().strip())
    assert "passed" not in line
    assert "reason" not in line
    assert "details" not in line
    assert line["symbol"] == "QQQ"


def test_read_day_returns_list(tmp_path):
    record(event="e1", symbol="TQQQ", passed=True, base=tmp_path)
    record(event="e2", symbol="SQQQ", passed=False, base=tmp_path)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = read_day(day, base=tmp_path)
    assert len(rows) == 2
    assert rows[0]["event"] == "e1"
    assert rows[1]["event"] == "e2"


def test_read_day_returns_empty_when_missing(tmp_path):
    assert read_day("2050-01-01", base=tmp_path) == []


def test_stats_aggregates_pass_fail(tmp_path):
    record(event="killzone_check", passed=True, base=tmp_path)
    record(event="killzone_check", passed=True, base=tmp_path)
    record(event="killzone_check", passed=False, base=tmp_path)
    record(event="displacement_check", passed=False, base=tmp_path)
    record(event="signal_emit", base=tmp_path)  # info-only
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    s = stats(day, base=tmp_path)
    assert s["killzone_check"] == {"pass": 2, "fail": 1, "info": 0, "total": 3}
    assert s["displacement_check"] == {"pass": 0, "fail": 1, "info": 0, "total": 1}
    assert s["signal_emit"]["info"] == 1


def test_record_handles_timestamp_object(tmp_path):
    import pandas as pd
    ts = pd.Timestamp("2026-05-12 09:45", tz="US/Eastern")
    record(event="bar", bar_time=ts, base=tmp_path)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    line = json.loads((tmp_path / f"{day}.jsonl").read_text().strip())
    assert "2026-05-12" in line["bar_time"]
