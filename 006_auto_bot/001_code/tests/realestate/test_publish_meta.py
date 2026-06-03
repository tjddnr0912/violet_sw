from datetime import date
from realestate_bot.publish_meta import week_of_month, build_title, build_labels


def test_week_of_month():
    assert week_of_month(date(2026, 6, 6)) == "6월 1주차"
    assert week_of_month(date(2026, 6, 13)) == "6월 2주차"
    assert week_of_month(date(2026, 6, 30)) == "6월 5주차"


def test_build_title_prefix_and_headline():
    t = build_title(date(2026, 6, 6), "전국 신고가 21%, 수도권 과열")
    assert t == "2026-06-06, 6월 1주차 전국 신고가 21%, 수도권 과열"


def test_build_title_fallback_when_empty():
    t = build_title(date(2026, 6, 6), "")
    assert t == "2026-06-06, 6월 1주차 전국 아파트 시장 흐름"


def test_build_labels_7_to_9_and_dynamic():
    groups = {
        "서울": {"new_total": 50, "high_total": 12, "officetel_total": 9, "officetel_rent_total": 80},
        "경기": {"new_total": 30, "high_total": 3, "officetel_total": 2, "officetel_rent_total": 10},
    }
    labels = build_labels(groups, hottest_gu="영등포구")
    assert 7 <= len(labels) <= 9
    assert labels[:6] == ["부동산", "아파트", "실거래가", "주간시황", "전국", "전세가율"]
    assert "서울" in labels          # 신규 최다 권역
    assert "영등포구" in labels       # 핫스팟 (토픽 라벨보다 우선)
    assert "신고가" in labels         # 15/80 = 18.75% ≥ 15%
    assert len(labels) == len(set(labels))   # 중복 없음
    # base6 + 서울(권역) + 영등포구(핫스팟) + 신고가 = 9; 오피스텔은 9 cap으로 탈락
    assert len(labels) == 9 and "오피스텔" not in labels


def test_build_labels_floor_7_without_optional():
    groups = {"서울": {"new_total": 50, "high_total": 2,
                       "officetel_total": 0, "officetel_rent_total": 0}}
    labels = build_labels(groups, hottest_gu=None)
    # 신고가(2/50=4%)·오피스텔·핫스팟 없음 → 고정6 + 권역1 = 7
    assert len(labels) == 7
    assert "서울" in labels
