from realestate_bot import digest


def _input():
    return {
        "week_label": "2026-06-01 기준 주간",
        "seoul": {"new_total": 18, "high_total": 5, "low_total": 1, "high_pct": 27.8},
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
    }


def test_markdown_has_sections_and_ranking_order():
    md = digest.build_digest(_input())
    assert "## " in md  # 섹션 헤더 존재
    # 강남구가 도봉구보다 순위표에서 먼저
    assert md.index("강남구") < md.index("도봉구")
    # 신고가 하이라이트 단지명·라벨
    assert "은마" in md and digest._baseline_label() in md
    # 미확정 caveat
    assert "확정" in md


def test_empty_week_message():
    md = digest.build_digest({
        "week_label": "x", "seoul": {"new_total": 0, "high_total": 0,
                                     "low_total": 0, "high_pct": 0.0},
        "per_gu": {}, "highlights": []})
    assert "신규 신고" in md


def test_digest_renders_jeonse_and_officetel_when_present():
    d = _input()
    d.update({"jeonse": {"강남구": 72.5, "노원구": None}, "jeonse_seoul": 72.5,
              "officetel": {"강남구": 10}, "officetel_total": 10,
              "officetel_rent": {"강남구": 25}, "officetel_rent_total": 25,
              "officetel_rent_jeonse": 8, "officetel_rent_wolse": 17})
    md = digest.build_digest(d)
    assert "전세가율" in md and "72.5%" in md and "⚠️" in md   # 70%↑ 경고
    assert "오피스텔" in md and "10건" in md
    # 오피스텔 전월세: 총건수 + 전세/월세 구성
    assert "전월세" in md and "25건" in md and "전세 8건" in md and "월세 17건" in md


def test_digest_officetel_section_renders_with_rent_only():
    # 매매 0이어도 전월세만 있으면 오피스텔 섹션이 나온다 (오피스텔은 임대 위주)
    d = _input()
    d.update({"officetel_total": 0, "officetel": {},
              "officetel_rent": {"강남구": 12}, "officetel_rent_total": 12,
              "officetel_rent_jeonse": 3, "officetel_rent_wolse": 9})
    md = digest.build_digest(d)
    assert "## 오피스텔 시장" in md and "전월세" in md and "12건" in md
    assert "매매" not in md.split("## 오피스텔 시장")[1]   # 매매 0이면 매매 줄 생략


def test_digest_omits_synthesis_when_absent():
    # 전세/오피스텔 데이터 없으면 해당 섹션 미출력 (degrade)
    md = digest.build_digest(_input())
    assert "전세가율" not in md and "오피스텔 시장" not in md
