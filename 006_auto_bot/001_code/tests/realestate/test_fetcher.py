import json
import pytest
from unittest import mock
from realestate_bot import fetcher


def _claude_output(items):
    payload = {"total_count": len(items), "items": items, "summary": {}}
    return "<<<JSON>>>\n" + json.dumps(payload, ensure_ascii=False) + "\n<<<END>>>\n"


def _fake_run(output, returncode=0):
    m = mock.Mock()
    m.stdout = output
    m.stderr = ""
    m.returncode = returncode
    return m


def test_parse_valid_output_returns_items():
    items = [{"apt_name": "A", "area_sqm": 84.9, "floor": 5,
              "price_10k": 100000, "trade_date": "2026-05-10",
              "build_year": 2015, "deal_type": "중개거래", "dong": "합정동"}]
    with mock.patch("realestate_bot.fetcher.subprocess.run", return_value=_fake_run(_claude_output(items))):
        out = fetcher.fetch_region("11440", "202605")
    assert len(out) == 1
    assert out[0]["region_code"] == "11440" and out[0]["price_10k"] == 100000


def test_retry_then_succeed_on_garbage_first():
    items = [{"apt_name": "A", "area_sqm": 84.9, "floor": 5, "price_10k": 100000,
              "trade_date": "2026-05-10", "build_year": 2015, "deal_type": "중개거래"}]
    seq = [_fake_run("no json here"), _fake_run(_claude_output(items))]
    with mock.patch("realestate_bot.fetcher.subprocess.run", side_effect=seq), \
         mock.patch("realestate_bot.fetcher.time.sleep"):
        out = fetcher.fetch_region("11440", "202605", max_retries=2)
    assert len(out) == 1


def test_all_retries_fail_raises():
    with mock.patch("realestate_bot.fetcher.subprocess.run", return_value=_fake_run("garbage")), \
         mock.patch("realestate_bot.fetcher.time.sleep"):
        with pytest.raises(RuntimeError):
            fetcher.fetch_region("11440", "202605", max_retries=2)


def test_missing_required_field_is_rejected():
    bad = [{"apt_name": "A", "floor": 5}]  # area_sqm/price_10k/trade_date 없음
    with mock.patch("realestate_bot.fetcher.subprocess.run", return_value=_fake_run(_claude_output(bad))), \
         mock.patch("realestate_bot.fetcher.time.sleep"):
        with pytest.raises(RuntimeError):
            fetcher.fetch_region("11440", "202605", max_retries=1)


def test_partial_result_warns_but_returns(caplog):
    # total_count > len(items): 부분 결과를 반환하되 완전성 경고를 남긴다 (raise 아님)
    items = [{"apt_name": "A", "area_sqm": 84.9, "floor": 5,
              "price_10k": 100000, "trade_date": "2026-05-10"}]
    payload = {"total_count": 122, "items": items, "summary": {}}
    text = "<<<JSON>>>\n" + json.dumps(payload, ensure_ascii=False) + "\n<<<END>>>\n"
    with mock.patch("realestate_bot.fetcher.subprocess.run",
                    return_value=_fake_run(text)):
        with caplog.at_level("WARNING"):
            out = fetcher.fetch_region("11440", "202605")
    assert len(out) == 1
    assert any("incomplete" in r.message for r in caplog.records)
