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


def test_build_report_uses_injected_fetch_region(tmp_path, monkeypatch):
    # 주간 런은 직접 MCP 경로를 주입한다 — claude-p(fetcher.fetch_region)는 호출되면 안 됨
    from realestate_bot.store import RealEstateStore
    store = RealEstateStore(str(tmp_path / "t.db"))
    calls = []

    def fake(code, ym, **kw):
        calls.append((code, ym))
        return []

    monkeypatch.setattr(bot.fetcher, "fetch_region",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("claude-p 호출됨")))
    report = bot.build_report(store, {"강남구": "11680"}, ["202605"],
                              as_of="2026-06-01", fetch_region=fake)
    assert ("11680", "202605") in calls
    assert report["seoul"]["new_total"] == 0


def test_backfill_skips_already_loaded(tmp_path, monkeypatch):
    # 백필 재개 시 이미 적재된 (구,월)은 fetch를 건너뛴다 (사용량 절약)
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "bf.db"))
    monkeypatch.setattr(rconfig, "ALL_REGIONS", {"강남구": "11680", "마포구": "11440"})
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    b = bot.RealEstateBot(test_mode=True)
    months = bot._recent_months(3)        # [현재월, 직전월, 전전월]
    loaded, other = months[1], months[2]  # backfill(2)가 적재하는 '완료월' 2개
    # 강남 'loaded'월 1건 사전 적재
    b.store.insert_new([{"region_code": "11680", "apt_name": "X", "dong": "d",
                         "area_sqm": 84.0, "floor": 1, "price_10k": 100000,
                         "trade_date": f"{loaded[:4]}-{loaded[4:6]}-05",
                         "build_year": 2015, "deal_type": "중개거래"}])
    calls = []
    b.backfill(2, fetch_region=lambda code, ym, **kw: (calls.append((code, ym)), [])[1])
    assert ("11680", loaded) not in calls          # 이미 적재 → skip
    assert ("11680", other) in calls                # 미적재 → fetch
    assert ("11440", loaded) in calls and ("11440", other) in calls
    assert ("11680", months[0]) not in calls        # 현재월(미확정)은 백필 제외
    assert ("11440", months[0]) not in calls


def test_backfill_skips_current_incomplete_month(tmp_path, monkeypatch):
    # 현재월(신고지연·미확정)은 백필하지 않는다 — 완료된 월만 적재(헛호출 방지)
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "cm.db"))
    monkeypatch.setattr(rconfig, "ALL_REGIONS", {"마포구": "11440"})
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    b = bot.RealEstateBot(test_mode=True)
    months = bot._recent_months(3)        # [현재월, 직전월, 전전월]
    calls = []
    b.backfill(2, fetch_region=lambda code, ym, **kw: (calls.append(ym), [])[1])
    assert months[0] not in calls                       # 현재월 제외
    assert months[1] in calls and months[2] in calls    # 완료월 2개는 적재


def test_backfill_rents_writes_rent_table_only(tmp_path, monkeypatch):
    # 전월세 백필은 rents 테이블에만 적재(transactions와 분리)
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "r.db"))
    monkeypatch.setattr(rconfig, "ALL_REGIONS", {"강남구": "11680"})
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    b = bot.RealEstateBot(test_mode=True)
    months = bot._recent_months(3)

    def fake_rent(code, ym, **kw):
        return [{"region_code": code, "apt_name": "X", "dong": "d", "area_sqm": 84.0,
                 "floor": 1, "deposit_10k": 50000, "monthly_rent_10k": 0,
                 "contract_type": "전세", "trade_date": f"{ym[:4]}-{ym[4:6]}-05",
                 "build_year": 2015}]

    b.backfill_rents(2, fetch_rent=fake_rent)
    assert b.store.has_rent_records_for_month("11680", months[1])      # rents에 적재
    assert not b.store.has_records_for_month("11680", months[1])       # transactions엔 없음


def test_synthesize_jeonse_and_officetel(tmp_path):
    from realestate_bot.store import RealEstateStore
    store = RealEstateStore(str(tmp_path / "syn.db"))
    store.insert_new([
        {"region_code": "11680", "apt_name": "A", "dong": "d", "area_sqm": 84.9,
         "floor": 1, "price_10k": 100000, "trade_date": "2026-05-10",
         "build_year": 2015, "deal_type": "중개거래"},
        {"region_code": "11680", "apt_name": "A", "dong": "d", "area_sqm": 84.9,
         "floor": 2, "price_10k": 100000, "trade_date": "2026-05-11",
         "build_year": 2015, "deal_type": "중개거래"},
    ], "apartment")
    store.insert_new_rents([
        {"region_code": "11680", "apt_name": "A", "dong": "d", "area_sqm": 84.9,
         "floor": 1, "deposit_10k": 70000, "monthly_rent_10k": 0,
         "contract_type": "전세", "trade_date": "2026-05-12", "build_year": 2015},
    ], "apartment")
    store.insert_new([
        {"region_code": "11680", "apt_name": "OFTL", "dong": "d", "area_sqm": 30.0,
         "floor": 3, "price_10k": 20000, "trade_date": "2026-05-13",
         "build_year": 2018, "deal_type": "중개거래"},
    ], "officetel")
    syn = bot.synthesize(store, {"강남구": "11680"}, "202605")
    assert syn["jeonse"]["강남구"] == 70.0          # 전세 70000 / 매매 100000
    assert syn["jeonse_seoul"] == 70.0
    assert syn["officetel"]["강남구"] == 1 and syn["officetel_total"] == 1


def test_synthesize_includes_officetel_rent(tmp_path):
    from realestate_bot.store import RealEstateStore
    store = RealEstateStore(str(tmp_path / "syn_oftl_rent.db"))
    store.insert_new_rents([
        {"region_code": "11680", "apt_name": "O", "dong": "d", "area_sqm": 30.0,
         "floor": 1, "deposit_10k": 8000, "monthly_rent_10k": 0,
         "contract_type": "전세", "trade_date": "2026-05-10", "build_year": 2018},
        {"region_code": "11680", "apt_name": "O", "dong": "d", "area_sqm": 30.0,
         "floor": 2, "deposit_10k": 1000, "monthly_rent_10k": 60,
         "contract_type": "월세", "trade_date": "2026-05-11", "build_year": 2018},
    ], "officetel")
    syn = bot.synthesize(store, {"강남구": "11680"}, "202605")
    assert syn["officetel_rent_total"] == 2
    assert syn["officetel_rent_jeonse"] == 1
    assert syn["officetel_rent_wolse"] == 1
    assert syn["officetel_rent"]["강남구"] == 2


class _FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def fetch_region(self, code, ym, **kw):
        return [{"region_code": code, "apt_name": "APT", "dong": "d", "area_sqm": 84.0,
                 "floor": 1, "price_10k": 100000, "trade_date": f"{ym[:4]}-{ym[4:6]}-05",
                 "build_year": 2015, "deal_type": "중개거래"}]

    def fetch_rent(self, code, ym, **kw):
        return [{"region_code": code, "apt_name": "APT", "dong": "d", "area_sqm": 84.0,
                 "floor": 1, "deposit_10k": 50000, "monthly_rent_10k": 0,
                 "contract_type": "전세", "trade_date": f"{ym[:4]}-{ym[4:6]}-05",
                 "build_year": 2015}]

    def fetch_officetel_trades(self, code, ym, **kw):
        return [{"region_code": code, "apt_name": "OFTL", "dong": "d", "area_sqm": 30.0,
                 "floor": 2, "price_10k": 20000, "trade_date": f"{ym[:4]}-{ym[4:6]}-06",
                 "build_year": 2018, "deal_type": "중개거래"}]

    def fetch_officetel_rent(self, code, ym, **kw):
        return [{"region_code": code, "apt_name": "OFTL", "dong": "d", "area_sqm": 30.0,
                 "floor": 2, "deposit_10k": 8000, "monthly_rent_10k": 0,
                 "contract_type": "전세", "trade_date": f"{ym[:4]}-{ym[4:6]}-06",
                 "build_year": 2018}]


def test_backfill_all_separates_4_types(tmp_path, monkeypatch):
    # 아파트·오피스텔 매매+전월세 4종이 각자 property_type/테이블로 분리 적재된다
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "all.db"))
    monkeypatch.setattr(rconfig, "ALL_REGIONS", {"강남구": "11680"})
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    monkeypatch.setattr(bot.mcp_client, "MCPClient", lambda *a, **k: _FakeClient())
    b = bot.RealEstateBot(test_mode=True)
    b.backfill_all(2)
    m = bot._recent_months(3)[1]   # 완료월 하나
    assert b.store.has_records_for_month("11680", m, "apartment")
    assert b.store.has_records_for_month("11680", m, "officetel")
    assert b.store.has_rent_records_for_month("11680", m, "apartment")
    assert b.store.has_rent_records_for_month("11680", m, "officetel")


def test_backfill_aborts_on_consecutive_failures(tmp_path, monkeypatch):
    # 한도 막힘처럼 연속 실패가 임계치에 도달하면 백필 전체를 즉시 중단(헛돌지 않음)
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "ab.db"))
    monkeypatch.setattr(rconfig, "ALL_REGIONS",
                        {f"구{i}": f"110{i:02d}" for i in range(10)})  # 10구
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    b = bot.RealEstateBot(test_mode=True)
    calls = []

    def boom(code, ym, **kw):
        calls.append((code, ym))
        raise RuntimeError("claude -p failed: ")

    b.backfill(1, max_consecutive_fails=3, fetch_region=boom)
    # 3회 연속 실패 후 중단 → 정확히 3회에서 멈춤 (10구 전부 시도하지 않음)
    assert len(calls) == 3


def test_backfill_success_resets_failure_counter(tmp_path, monkeypatch):
    # 중간에 성공하면 연속 실패 카운터가 리셋 → 흩어진 실패로는 중단하지 않는다
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "rs.db"))
    monkeypatch.setattr(rconfig, "ALL_REGIONS",
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

    b.backfill(1, max_consecutive_fails=3, fetch_region=fetch)
    # 연속 실패가 2회를 넘지 않으므로 5개 구 모두 시도(중단 안 됨)
    assert calls == ["11001", "11002", "11003", "11004", "11005"]


def test_run_national_scope_publishes(tmp_path, monkeypatch):
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "nat.db"))
    # 전국 범위를 작게 축소: 서울 1 + 경기 1 + 부산 1
    monkeypatch.setattr(rconfig, "SEOUL_GU", {"강남구": "11680"})
    monkeypatch.setattr(rconfig, "ALL_REGIONS",
                        {"강남구": "11680", "경기도 수원시 영통구": "41117", "부산진구": "26230"})
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    monkeypatch.setattr(bot.mcp_client, "MCPClient", lambda *a, **k: _FakeClient())
    captured = {}

    def fake_upload(title, content, labels, **kw):
        captured["title"] = title
        captured["labels"] = labels
        return {"success": True, "url": "http://blog/x"}

    monkeypatch.setattr(bot, "convert_md_to_html_via_claude",
                        lambda c: ("<p>html</p>", "전국 신고가 테스트 헤드라인"))
    monkeypatch.setattr(bot.commentary, "make_commentary", lambda s: "")

    b = bot.RealEstateBot(test_mode=False)
    b.blogger = type("B", (), {"upload_post": staticmethod(fake_upload)})()
    r = b.run()

    assert r["success"] is True
    assert r["blog_url"] == "http://blog/x"
    # 제목: 날짜, 주차 + AI 헤드라인
    assert "주차" in captured["title"] and "전국 신고가 테스트 헤드라인" in captured["title"]
    # 라벨 7~9개
    assert 7 <= len(captured["labels"]) <= 9
    assert "전국" in captured["labels"]
