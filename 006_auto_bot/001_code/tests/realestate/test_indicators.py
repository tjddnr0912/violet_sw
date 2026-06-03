from realestate_bot.detector import Verdict
from realestate_bot import indicators


def test_breadth_counts_and_pct():
    vs = [Verdict("HIGH"), Verdict("HIGH"), Verdict("LOW"),
          Verdict("NEW"), Verdict("NORMAL")]
    b = indicators.breadth(vs)
    assert b["high"] == 2 and b["low"] == 1 and b["total"] == 5
    assert round(b["high_pct"], 0) == 40.0 and round(b["low_pct"], 0) == 20.0


def test_breadth_empty():
    b = indicators.breadth([])
    assert b["total"] == 0 and b["high_pct"] == 0.0


def test_mix_adjusted_change_common_bands_only():
    # 84밴드: 100000->110000(+10%), 59밴드: prev 없음 → 무시
    cur = {84: 110000, 59: 80000}
    prev = {84: 100000}
    counts = {84: 10, 59: 5}
    chg = indicators.mix_adjusted_change(cur, prev, counts)
    assert round(chg, 1) == 10.0


def test_mix_adjusted_change_none_when_no_common():
    assert indicators.mix_adjusted_change({84: 110000}, {59: 80000}, {84: 1}) is None


def test_segment_flags_direct_deal_spike():
    recs = [{"deal_type": "직거래", "build_year": 2024},
            {"deal_type": "직거래", "build_year": 2010},
            {"deal_type": "중개거래", "build_year": 2010}]
    s = indicators.segment_flags(recs, current_year=2026)
    assert round(s["direct_deal_pct"], 0) == 67.0
    assert s["direct_deal_spike"] is True
    assert round(s["new_build_pct"], 0) == 33.0


def test_rank_regions_hottest_first():
    per_gu = {
        "강남구": {"new_count": 10, "breadth": {"high_pct": 50.0}},
        "도봉구": {"new_count": 3, "breadth": {"high_pct": 5.0}},
        "마포구": {"new_count": 8, "breadth": {"high_pct": 20.0}},
    }
    ranked = indicators.rank_regions(per_gu)
    assert [g for g, _ in ranked] == ["강남구", "마포구", "도봉구"]


from realestate_bot.indicators import rollup_groups


def _gu(new_count, high, low=0, high_pct=0.0):
    return {"new_count": new_count,
            "breadth": {"high": high, "low": low, "high_pct": high_pct},
            "mix_change": None, "segment": {"direct_deal_spike": False}}


def test_rollup_groups_aggregates_by_group():
    per_gu = {
        "강남구": _gu(10, 5, 0, 50.0),
        "송파구": _gu(6, 1, 1, 16.7),
        "경기도 수원시 영통구": _gu(8, 2, 0, 25.0),
        "경기도 성남시 분당구": _gu(4, 0, 1, 0.0),
    }
    jeonse = {"강남구": 55.0, "송파구": 60.0,
              "경기도 수원시 영통구": 70.0, "경기도 성남시 분당구": None}
    officetel = {"강남구": 3, "경기도 수원시 영통구": 2}
    officetel_rent = {"강남구": 30, "경기도 수원시 영통구": 12}
    gu_to_group = {"강남구": "서울", "송파구": "서울",
                   "경기도 수원시 영통구": "경기", "경기도 성남시 분당구": "경기"}

    out = rollup_groups(per_gu, jeonse, officetel, officetel_rent, gu_to_group)

    assert out["서울"]["new_total"] == 16
    assert out["서울"]["high_total"] == 6
    assert round(out["서울"]["high_pct"], 1) == 37.5     # 6/16
    assert out["서울"]["avg_jeonse"] == 57.5             # (55+60)/2
    assert out["서울"]["officetel_total"] == 3
    assert out["서울"]["officetel_rent_total"] == 30
    # top_movers: 신고가 비중 내림차순, 신규>0만
    assert out["서울"]["top_movers"][0][0] == "강남구"
    assert out["경기"]["new_total"] == 12
    assert out["경기"]["avg_jeonse"] == 70.0             # None은 제외


def test_rollup_groups_empty_group_absent():
    out = rollup_groups({}, {}, {}, {}, {})
    assert out == {}
