"""location_enrich 순수 로직 + 게이트 테스트 (네트워크 monkeypatch)."""
import pytest

from realestate_bot import location_enrich as le


# ---- 순수 헬퍼 ----

def test_is_elementary_by_category():
    assert le._is_elementary({"category_name": "교육,학문 > 학교 > 초등학교",
                              "place_name": "서울양원초등학교"})


def test_is_elementary_by_name_suffix():
    assert le._is_elementary({"category_name": "", "place_name": "구미초등학교"})


def test_middle_school_is_not_elementary():
    assert not le._is_elementary({"category_name": "교육,학문 > 학교 > 중학교",
                                  "place_name": "구미중학교"})


def test_detect_gtx():
    names = ["동탄역 GTX-A", "동탄역 SRT", "오리역 수인분당선"]
    assert le._detect_gtx(names) == ["동탄역 GTX-A"]


def test_detect_gtx_none():
    assert le._detect_gtx(["강남역 2호선", "강남역 신분당선"]) == []


def test_is_academic_academy_includes_ipsi():
    assert le._is_academic_academy({"category_name": "교육,학문 > 학원 > 입시학원"})


def test_is_academic_academy_includes_generic():
    assert le._is_academic_academy({"category_name": "교육,학문 > 학원 > 학원"})


def test_is_academic_academy_excludes_taekwondo():
    assert not le._is_academic_academy({"category_name": "교육,학문 > 학원 > 태권도장"})


def test_is_academic_academy_excludes_art_music():
    assert not le._is_academic_academy({"category_name": "교육,학문 > 학원 > 미술학원"})
    assert not le._is_academic_academy({"category_name": "교육,학문 > 학원 > 음악학원"})


def test_pick_apt_filters_non_apartment():
    docs = [
        {"place_name": "삼성전자서비스 영등포센터", "category_name": "가전 > 서비스센터",
         "address_name": "서울 영등포구 가마산로 476"},
        {"place_name": "삼성아파트", "category_name": "부동산 > 주거시설 > 아파트",
         "address_name": "서울 영등포구 신길동 4759"},
    ]
    assert le._pick_apt(docs)["place_name"] == "삼성아파트"


def test_pick_apt_prefers_dong_match():
    docs = [
        {"place_name": "삼성아파트", "category_name": "아파트",
         "address_name": "서울 영등포구 신길동 4759"},
        {"place_name": "삼성아파트", "category_name": "아파트",
         "address_name": "서울 영등포구 영등포동7가 94-41"},
    ]
    assert le._pick_apt(docs, dong="영등포동")["address_name"].startswith("서울 영등포구 영등포동")


def test_pick_apt_none_when_no_apartment():
    docs = [{"place_name": "코엑스", "category_name": "전시관", "address_name": "x"}]
    assert le._pick_apt(docs) is None


# ---- 배지 포맷 ----

def test_format_badge_full():
    loc = {"elementary": 1, "academy": 37, "subway_names": ["신풍역 7호선"], "gtx": []}
    assert le.format_badge(loc) == "🏫 초 1 · 📚 교과학원 37 · 🚇 신풍역 7호선"


def test_format_badge_capped_marks_plus():
    loc = {"elementary": 2, "academy": 45, "academy_capped": True,
           "subway_names": [], "gtx": []}
    assert "📚 교과학원 45+" in le.format_badge(loc)


def test_format_badge_gtx_marked():
    loc = {"elementary": 2, "academy": 5, "subway_names": ["동탄역 GTX-A"],
           "gtx": ["동탄역 GTX-A"]}
    assert "✨GTX" in le.format_badge(loc)


def test_format_badge_no_subway():
    loc = {"elementary": 2, "academy": 74, "subway_names": [], "gtx": []}
    assert "🚇 500m 내 없음" in le.format_badge(loc)


def test_format_badge_empty_when_none():
    assert le.format_badge(None) == ""


# ---- 게이트 ----

def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    assert le.is_enabled() is False


def test_disabled_by_flag(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "x")
    monkeypatch.setenv("LOCATION_ENRICH_ENABLED", "false")
    assert le.is_enabled() is False


def test_enabled_with_key(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "x")
    monkeypatch.setenv("LOCATION_ENRICH_ENABLED", "true")
    assert le.is_enabled() is True


def test_enrich_highlights_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("KAKAO_REST_API_KEY", raising=False)
    hs = [{"gu": "양천구", "apt_name": "탑건진선미", "dong": "신월동"}]
    le.enrich_highlights(hs)
    assert "loc" not in hs[0]


# ---- enrich_one (네트워크 monkeypatch) ----

def _fake_get_factory():
    """path별 canned 응답. 키워드=아파트 1건, SC4=초1+중1, AC5 total=37, SW8=신풍역."""
    def fake_get(path, params, tries=3):
        if path == "search/keyword.json":
            return {"documents": [
                {"x": "126.9", "y": "37.5", "place_name": "삼성아파트",
                 "category_name": "부동산 > 주거시설 > 아파트",
                 "address_name": "서울 영등포구 신길동 4759",
                 "road_address_name": "서울 영등포구 여의대방로 45"}]}
        if path == "search/category.json":
            code = params["category_group_code"]
            if code == "SC4":
                return {"documents": [
                    {"place_name": "서울대길초등학교", "category_name": "학교 > 초등학교"},
                    {"place_name": "대영중학교", "category_name": "학교 > 중학교"}],
                    "meta": {"is_end": True, "total_count": 2}}
            if code == "AC5":
                return {"documents": [
                    {"place_name": "우리입시학원", "category_name": "학원 > 입시학원"},
                    {"place_name": "수학의힘", "category_name": "학원 > 수학학원"},
                    {"place_name": "으뜸태권도", "category_name": "학원 > 태권도장"},
                    {"place_name": "손그림미술", "category_name": "학원 > 미술학원"}],
                    "meta": {"is_end": True, "total_count": 4}}
            if code == "SW8":
                return {"documents": [{"place_name": "신풍역 7호선"}],
                        "meta": {"is_end": True, "total_count": 1}}
        return {"documents": [], "meta": {"is_end": True, "total_count": 0}}
    return fake_get


def test_enrich_one_end_to_end(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "x")
    monkeypatch.setattr(le, "_get", _fake_get_factory())
    monkeypatch.setattr(le.time, "sleep", lambda *_: None)
    r = le.enrich_one("영등포구", "삼성", "신길동")
    assert r["elementary"] == 1          # 중학교 제외
    assert r["academy"] == 2             # 입시·수학만(태권도·미술 제외)
    assert r["academy_total"] == 4       # 예체능 포함 raw
    assert r["academy_capped"] is False
    assert r["subway_names"] == ["신풍역 7호선"]
    assert r["gtx"] == []
    assert r["matched"] == "삼성아파트"


def test_enrich_one_returns_none_on_geocode_miss(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "x")
    monkeypatch.setattr(le, "_get", lambda *a, **k: {"documents": []})
    r = le.enrich_one("종로구", "두레엘리시안", "숭인동")
    assert r is None
