from unittest import mock
import importlib

bot = importlib.import_module("weekly_realestate_bot")  # top-level entry file


def _items(region, base_price):
    # 동일 단지/평형 2건: 1건은 baseline, 다음 호출분이 신고가
    return [{"apt_name": "테스트팰리스", "dong": "동", "area_sqm": 84.9, "floor": 5,
             "price_10k": base_price, "trade_date": "2026-05-10",
             "build_year": 2015, "deal_type": "중개거래"}]


def test_build_report_flags_new_high(tmp_path):
    from realestate_bot.store import RealEstateStore
    store = RealEstateStore(str(tmp_path / "t.db"))
    # 사전 이력 적재(baseline)
    store.insert_new([{"region_code": "11680", "apt_name": "테스트팰리스", "dong": "동",
                       "area_sqm": 84.9, "floor": 4, "price_10k": 200000,
                       "trade_date": "2026-02-01", "build_year": 2015, "deal_type": "중개거래"}])

    def fake_fetch(code, ym, **kw):
        if code == "11680":
            return [{"apt_name": "테스트팰리스", "dong": "dong", "area_sqm": 84.9, "floor": 9,
                     "price_10k": 250000, "trade_date": "2026-05-20",
                     "build_year": 2015, "deal_type": "중개거래", "region_code": "11680"}]
        return []

    with mock.patch("realestate_bot.fetcher.fetch_region", side_effect=fake_fetch):
        report = bot.build_report(store, regions={"강남구": "11680"},
                                  months=["202605"], as_of="2026-05-23")
    assert report["seoul"]["high_total"] == 1
    assert any(h["apt_name"] == "테스트팰리스" and h["kind"] == "HIGH"
               for h in report["highlights"])


def test_backfill_skips_already_loaded(tmp_path, monkeypatch):
    # 백필 재개 시 이미 적재된 (구,월)은 fetch를 건너뛴다 (사용량 절약)
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "bf.db"))
    monkeypatch.setattr(rconfig, "SEOUL_GU", {"강남구": "11680", "마포구": "11440"})
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    b = bot.RealEstateBot(test_mode=True)
    months = bot._recent_months(2)
    # 강남 최근달 1건 사전 적재
    b.store.insert_new([{"region_code": "11680", "apt_name": "X", "dong": "d",
                         "area_sqm": 84.0, "floor": 1, "price_10k": 100000,
                         "trade_date": f"{months[0][:4]}-{months[0][4:6]}-05",
                         "build_year": 2015, "deal_type": "중개거래"}])
    calls = []
    monkeypatch.setattr(bot.fetcher, "fetch_region",
                        lambda code, ym, **kw: (calls.append((code, ym)), [])[1])
    b.backfill(2)
    assert ("11680", months[0]) not in calls   # 이미 적재 → skip
    assert ("11680", months[1]) in calls         # 미적재 → fetch
    assert ("11440", months[0]) in calls and ("11440", months[1]) in calls


def test_backfill_aborts_on_consecutive_failures(tmp_path, monkeypatch):
    # 한도 막힘처럼 연속 실패가 임계치에 도달하면 백필 전체를 즉시 중단(헛돌지 않음)
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "ab.db"))
    monkeypatch.setattr(rconfig, "SEOUL_GU",
                        {f"구{i}": f"110{i:02d}" for i in range(10)})  # 10구
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    b = bot.RealEstateBot(test_mode=True)
    calls = []

    def boom(code, ym, **kw):
        calls.append((code, ym))
        raise RuntimeError("claude -p failed: ")

    monkeypatch.setattr(bot.fetcher, "fetch_region", boom)
    b.backfill(1, max_consecutive_fails=3)
    # 3회 연속 실패 후 중단 → 정확히 3회에서 멈춤 (10구 전부 시도하지 않음)
    assert len(calls) == 3


def test_backfill_success_resets_failure_counter(tmp_path, monkeypatch):
    # 중간에 성공하면 연속 실패 카운터가 리셋 → 흩어진 실패로는 중단하지 않는다
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "rs.db"))
    monkeypatch.setattr(rconfig, "SEOUL_GU",
                        {"A": "11001", "B": "11002", "C": "11003", "D": "11004", "E": "11005"})
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    b = bot.RealEstateBot(test_mode=True)
    outcomes = {"11001": "fail", "11002": "fail", "11003": "ok",
                "11004": "fail", "11005": "fail"}  # 실패2 → 성공(리셋) → 실패2
    calls = []

    def fetch(code, ym, **kw):
        calls.append(code)
        if outcomes[code] == "fail":
            raise RuntimeError("boom")
        return [{"apt_name": "X", "dong": "d", "area_sqm": 84.0, "floor": 1,
                 "price_10k": 100000, "trade_date": f"{ym[:4]}-{ym[4:6]}-05",
                 "build_year": 2015, "deal_type": "중개거래", "region_code": code}]

    monkeypatch.setattr(bot.fetcher, "fetch_region", fetch)
    b.backfill(1, max_consecutive_fails=3)
    # 연속 실패가 2회를 넘지 않으므로 5개 구 모두 시도(중단 안 됨)
    assert calls == ["11001", "11002", "11003", "11004", "11005"]
