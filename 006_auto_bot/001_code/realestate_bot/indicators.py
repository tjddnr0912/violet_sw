"""시장 흐름 지표 집계 — 순수함수."""
from realestate_bot import config


def breadth(verdicts: list) -> dict:
    total = len(verdicts)
    high = sum(1 for v in verdicts if v.kind == "HIGH")
    low = sum(1 for v in verdicts if v.kind == "LOW")
    new = sum(1 for v in verdicts if v.kind == "NEW")
    normal = sum(1 for v in verdicts if v.kind == "NORMAL")
    return {
        "high": high, "low": low, "new": new, "normal": normal, "total": total,
        "high_pct": (high / total * 100) if total else 0.0,
        "low_pct": (low / total * 100) if total else 0.0,
    }


def mix_adjusted_change(cur: dict, prev: dict, cur_counts: dict) -> float | None:
    """공통 평형밴드만 매칭, 현재 거래수 가중평균 변화율(%). 공통밴드 없으면 None."""
    common = [b for b in cur if b in prev and prev[b]]
    if not common:
        return None
    num = 0.0
    den = 0.0
    for b in common:
        w = cur_counts.get(b, 1)
        num += (cur[b] / prev[b] - 1) * 100 * w
        den += w
    return num / den if den else None


def segment_flags(records: list, current_year: int) -> dict:
    total = len(records)
    if total == 0:
        return {"direct_deal_pct": 0.0, "new_build_pct": 0.0, "direct_deal_spike": False}
    direct = sum(1 for r in records if (r.get("deal_type") or "").startswith("직거래"))
    new_build = sum(1 for r in records
                    if r.get("build_year") and current_year - int(r["build_year"]) <= config.NEW_BUILD_MAX_AGE)
    direct_pct = direct / total * 100
    return {
        "direct_deal_pct": direct_pct,
        "new_build_pct": new_build / total * 100,
        "direct_deal_spike": direct_pct >= config.DIRECT_DEAL_SPIKE_PCT,
    }


def jeonse_ratio(trade_medians: dict, rent_deposit_medians: dict,
                 rent_counts: dict = None) -> float | None:
    """전세가율(%) = 공통 평형밴드의 (전세 보증금중앙값 / 매매 중앙값), 전세 거래수 가중.

    trade_medians: {band: 매매 중앙가}  (store.band_medians의 median)
    rent_deposit_medians: {band: 전세 보증금중앙값}  (store.rent_band_medians)
    공통 밴드 없으면 None. 70%↑면 갭투자 위험 신호.
    """
    common = [b for b in rent_deposit_medians if trade_medians.get(b)]
    if not common:
        return None
    num = den = 0.0
    for b in common:
        w = (rent_counts or {}).get(b, 1)
        num += (rent_deposit_medians[b] / trade_medians[b] * 100) * w
        den += w
    return round(num / den, 1) if den else None


def rank_regions(per_gu: dict) -> list:
    """뜨거운 순: (신고가 비중, 신규건수) 내림차순."""
    return sorted(
        per_gu.items(),
        key=lambda kv: (kv[1]["breadth"]["high_pct"], kv[1]["new_count"]),
        reverse=True,
    )


def rollup_groups(per_gu: dict, jeonse: dict, officetel: dict,
                  officetel_rent: dict, gu_to_group: dict) -> dict:
    """구별 지표를 권역별로 집계.

    gu_to_group: {gu_name: 권역명} (regions_extra.group_of로 사전 산출)
    반환 {권역명: {new_total, high_total, low_total, high_pct, avg_jeonse,
                  officetel_total, officetel_rent_total, top_movers, count}}.
    top_movers = (신고가 비중, 신규) 내림차순 상위 5 (신규>0만), [(gu, {new_count, high_pct})].
    """
    acc = {}
    for gu, g in per_gu.items():
        grp = gu_to_group.get(gu, "기타")
        d = acc.setdefault(grp, {"new_total": 0, "high_total": 0, "low_total": 0,
                                 "officetel_total": 0, "officetel_rent_total": 0,
                                 "jeonse_vals": [], "members": []})
        d["new_total"] += g["new_count"]
        d["high_total"] += g["breadth"]["high"]
        d["low_total"] += g["breadth"]["low"]
        d["officetel_total"] += officetel.get(gu, 0)
        d["officetel_rent_total"] += officetel_rent.get(gu, 0)
        j = jeonse.get(gu)
        if j is not None:
            d["jeonse_vals"].append(j)
        d["members"].append((gu, g))

    out = {}
    for grp, d in acc.items():
        nt = d["new_total"]
        jv = d["jeonse_vals"]
        movers = sorted((m for m in d["members"] if m[1]["new_count"] > 0),
                        key=lambda kv: (kv[1]["breadth"]["high_pct"], kv[1]["new_count"]),
                        reverse=True)[:5]
        out[grp] = {
            "new_total": nt,
            "high_total": d["high_total"],
            "low_total": d["low_total"],
            "high_pct": (d["high_total"] / nt * 100) if nt else 0.0,
            "avg_jeonse": round(sum(jv) / len(jv), 1) if jv else None,
            "officetel_total": d["officetel_total"],
            "officetel_rent_total": d["officetel_rent_total"],
            "top_movers": [(gu, {"new_count": g["new_count"],
                                 "high_pct": g["breadth"]["high_pct"]}) for gu, g in movers],
            "count": len(d["members"]),
        }
    return out
