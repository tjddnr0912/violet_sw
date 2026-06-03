from realestate_bot import digest


def _seoul_block():
    return {
        "per_gu": {
            "강남구": {"new_count": 10, "breadth": {"high_pct": 50.0, "high": 5, "low": 0},
                       "mix_change": 3.2, "segment": {"direct_deal_spike": False}},
            "도봉구": {"new_count": 8, "breadth": {"high_pct": 0.0, "high": 0, "low": 1},
                       "mix_change": -1.1, "segment": {"direct_deal_spike": True}},
        },
        "highlights": [
            {"gu": "강남구", "apt_name": "은마", "area_band": 84, "price_10k": 280000,
             "pct": 4.5, "kind": "HIGH", "ref_price": 268000, "ref_date": "2026-03-01"},
        ],
        "jeonse": {"강남구": 55.0, "도봉구": 71.8}, "jeonse_seoul": 63.4,
        "officetel": {"강남구": 10}, "officetel_total": 10,
        "officetel_rent": {"강남구": 25}, "officetel_rent_total": 25,
        "officetel_rent_jeonse": 8, "officetel_rent_wolse": 17,
        "new_total": 18, "high_total": 5, "low_total": 1, "high_pct": 27.8,
    }


def _input():
    return {
        "week_label": "2026-06-06 기준 주간",
        "national": {"new_total": 60, "high_total": 11, "high_pct": 18.3, "low_total": 3},
        "groups": {
            "서울": {"new_total": 18, "high_total": 5, "high_pct": 27.8, "low_total": 1,
                     "avg_jeonse": 63.4, "officetel_total": 10, "officetel_rent_total": 25,
                     "top_movers": [("강남구", {"new_count": 10, "high_pct": 50.0})], "count": 25},
            "경기": {"new_total": 30, "high_total": 4, "high_pct": 13.3, "low_total": 1,
                     "avg_jeonse": 68.0, "officetel_total": 5, "officetel_rent_total": 40,
                     "top_movers": [("경기도 수원시 영통구", {"new_count": 12, "high_pct": 25.0})],
                     "count": 44},
            "부산": {"new_total": 9, "high_total": 2, "high_pct": 22.2, "low_total": 1,
                     "avg_jeonse": 62.0, "officetel_total": 3, "officetel_rent_total": 18,
                     "top_movers": [("부산진구", {"new_count": 5, "high_pct": 40.0})], "count": 16},
            "세종": {"new_total": 3, "high_total": 0, "high_pct": 0.0, "low_total": 0,
                     "avg_jeonse": 58.0, "officetel_total": 0, "officetel_rent_total": 0,
                     "top_movers": [], "count": 1},
        },
        "highlights_by_group": {
            "경기": [{"gu": "경기도 수원시 영통구", "apt_name": "광교A", "area_band": 84,
                      "price_10k": 130000, "pct": 3.1, "kind": "HIGH",
                      "ref_price": 126000, "ref_date": "2026-02-01"}],
            "부산": [], "서울": [], "세종": [],
        },
        "seoul": _seoul_block(),
    }


def test_national_header_and_sections_present():
    md = digest.build_digest(_input())
    assert "전국" in md and "60건" in md            # 전국 헤더 총 신규
    assert "## 서울" in md                          # 서울 상세 섹션
    assert "강남구" in md and "은마" in md           # 서울 디테일·하이라이트
    assert "## 경기" in md                          # 경기 권역
    assert "광역시" in md                            # 광역시 섹션 헤더
    assert "부산" in md
    assert "세종" in md


def test_seoul_detail_unchanged_sections():
    md = digest.build_digest(_input())
    assert "구별 온도차" in md
    assert digest._baseline_label() in md           # 신고가 기준 라벨
    assert "전세가율" in md and "오피스텔" in md
    assert "전월세" in md and "월세 17건" in md       # 서울 오피스텔 전월세 (기존 기능)


def test_region_summary_has_top_movers_and_jeonse():
    md = digest.build_digest(_input())
    # 경기 요약: 신규 합계·전세가율·top 이동
    assert "30건" in md
    assert "68.0%" in md                            # 경기 평균 전세가율
    assert "수원시 영통구" in md                      # top mover


def test_empty_national_message():
    d = _input()
    d["national"] = {"new_total": 0, "high_total": 0, "high_pct": 0.0, "low_total": 0}
    d["groups"] = {}
    d["highlights_by_group"] = {}
    d["seoul"]["new_total"] = 0
    md = digest.build_digest(d)
    assert "신규 신고" in md      # 0건 안내


def test_region_degrades_when_group_missing():
    d = _input()
    del d["groups"]["부산"]       # 광역시 데이터 일부 없음 → degrade(해당 시 생략, 크래시 없음)
    md = digest.build_digest(d)
    assert "부산" not in md.split("## 서울")[0]   # 헤더 외엔 부산 미등장
    assert "## 경기" in md                        # 나머지 권역은 정상
