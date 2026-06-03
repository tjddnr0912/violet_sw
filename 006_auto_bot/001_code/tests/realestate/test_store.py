import pytest
from realestate_bot.store import RealEstateStore


def _rec(apt="A아파트", area=84.9, floor=10, price=100000, date="2026-05-10",
         region="11440", dong="합정동", build=2015, deal="중개거래"):
    return {"region_code": region, "apt_name": apt, "dong": dong, "area_sqm": area,
            "floor": floor, "price_10k": price, "trade_date": date,
            "build_year": build, "deal_type": deal}


@pytest.fixture
def store(tmp_path):
    return RealEstateStore(str(tmp_path / "t.db"))


def test_insert_new_returns_only_new(store):
    first = store.insert_new([_rec(price=100000), _rec(price=110000, floor=11)])
    assert len(first) == 2
    # 같은 레코드 재삽입 → 신규 0
    again = store.insert_new([_rec(price=100000), _rec(price=110000, floor=11)])
    assert again == []
    # 하나만 새 레코드
    third = store.insert_new([_rec(price=100000), _rec(price=120000, floor=12)])
    assert len(third) == 1 and third[0]["price_10k"] == 120000


def test_area_band_is_rounded(store):
    store.insert_new([_rec(area=84.96), _rec(area=84.12, floor=11)])
    snap = store.baseline_snapshot("11440")
    assert (("A아파트", 85) in snap) and (("A아파트", 84) in snap)


def test_baseline_snapshot_max_min(store):
    store.insert_new([
        _rec(price=100000, floor=1, date="2026-01-05"),
        _rec(price=130000, floor=2, date="2026-02-05"),
        _rec(price=90000, floor=3, date="2026-03-05"),
    ])
    snap = store.baseline_snapshot("11440")
    g = snap[("A아파트", 85)]
    assert g["max"] == 130000 and g["max_date"] == "2026-02-05"
    assert g["min"] == 90000 and g["min_date"] == "2026-03-05"
    assert g["count"] == 3


def test_baseline_excludes_older_than_36_months(store):
    store.insert_new([
        _rec(price=200000, floor=1, date="2000-01-05"),  # 아주 오래된 거래
        _rec(price=100000, floor=2, date="2026-05-05"),
    ])
    snap = store.baseline_snapshot("11440", as_of="2026-06-01")
    g = snap[("A아파트", 85)]
    # 2000년 거래는 36개월 윈도우 밖 → max는 100000
    assert g["max"] == 100000 and g["count"] == 1


def test_monthly_volume(store):
    store.insert_new([
        _rec(date="2026-04-10", floor=1), _rec(date="2026-04-20", floor=2),
        _rec(date="2026-05-10", floor=3),
    ])
    vol = dict(store.monthly_volume("11440", months=12))
    assert vol.get("202604") == 2 and vol.get("202605") == 1


def test_band_medians(store):
    store.insert_new([
        _rec(area=84.9, price=100000, floor=1, date="2026-05-01"),
        _rec(area=84.9, price=120000, floor=2, date="2026-05-02"),
        _rec(area=59.9, price=80000, floor=3, date="2026-05-03"),
    ])
    bm = store.band_medians("11440", "202605")
    assert bm[85]["median"] == 110000 and bm[85]["count"] == 2
    assert bm[60]["median"] == 80000


def test_has_records_for_month(store):
    store.insert_new([_rec(date="2026-05-10")])
    assert store.has_records_for_month("11440", "202605") is True
    assert store.has_records_for_month("11440", "202604") is False   # 다른 월
    assert store.has_records_for_month("11680", "202605") is False   # 다른 구


def _rent(apt="A아파트", area=84.9, floor=10, deposit=50000, monthly=0,
          date="2026-05-10", region="11440", dong="합정동", ctype="전세"):
    return {"region_code": region, "apt_name": apt, "dong": dong, "area_sqm": area,
            "floor": floor, "deposit_10k": deposit, "monthly_rent_10k": monthly,
            "contract_type": ctype, "trade_date": date, "build_year": 2015}


def test_insert_new_rents_dedup(store):
    first = store.insert_new_rents([_rent(deposit=50000), _rent(deposit=60000, floor=11)])
    assert len(first) == 2
    again = store.insert_new_rents([_rent(deposit=50000), _rent(deposit=60000, floor=11)])
    assert again == []


def test_has_rent_records_for_month(store):
    store.insert_new_rents([_rent(date="2026-05-10")])
    assert store.has_rent_records_for_month("11440", "202605") is True
    assert store.has_rent_records_for_month("11440", "202604") is False
    # 매매 테이블과 분리 — 전월세 적재가 매매 has에 안 잡힌다
    assert store.has_records_for_month("11440", "202605") is False


def test_rent_band_medians_jeonse_only(store):
    store.insert_new_rents([
        _rent(area=84.9, deposit=50000, monthly=0, floor=1, date="2026-05-01"),   # 전세
        _rent(area=84.9, deposit=70000, monthly=0, floor=2, date="2026-05-02"),   # 전세
        _rent(area=84.9, deposit=10000, monthly=50, floor=3, date="2026-05-03"),  # 월세 → 제외
    ])
    bm = store.rent_band_medians("11440", "202605")
    assert bm[85]["median_deposit_10k"] == 60000 and bm[85]["count"] == 2
