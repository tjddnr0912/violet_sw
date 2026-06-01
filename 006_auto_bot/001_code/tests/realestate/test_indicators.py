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
