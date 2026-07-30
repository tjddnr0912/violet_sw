"""전국 권역 주간 디제스트 markdown 빌드 — 전국 헤더 → 서울 상세 → 권역 요약.

헤더 표현과 섹션 순서는 `variation`이 주차 시드로 결정적으로 변주한다
(같은 주 재실행 시 동일 결과, 주마다 구성 이동).
"""
from realestate_bot import config, indicators, location_enrich, variation

_METRO_ORDER = ["부산", "대구", "인천", "광주", "대전", "울산"]


def _baseline_label() -> str:
    m = config.BASELINE_MONTHS
    return f"최근 {m // 12}년" if m % 12 == 0 else f"최근 {m}개월"


def _fmt_won(man: int) -> str:
    eok, rem = divmod(int(man), 10000)
    if eok and rem:
        return f"{eok}억 {rem:,}만"
    if eok:
        return f"{eok}억"
    return f"{rem:,}만"


def _fmt_pct(p):
    return "—" if p is None else f"{p:+.1f}%"


def _gu_short(name: str) -> str:
    """'경기도 수원시 영통구' → '수원시 영통구' (권역 표기 중복 제거)."""
    parts = name.split()
    return " ".join(parts[1:]) if len(parts) > 1 else name


def _render_highlights(lines: list, highlights: list, limit: int):
    for h in highlights[:limit]:
        badge = "🔼 신고가" if h["kind"] == "HIGH" else "🔽 신저점"
        lines.append(
            f"- {badge} **{_gu_short(h['gu'])} {h['apt_name']} {h['area_band']}㎡대** — "
            f"{_fmt_won(h['price_10k'])} ({_fmt_pct(h['pct'])}, "
            f"직전 {_fmt_won(h['ref_price'])} {h['ref_date']}) · {_baseline_label()} 기준")
        loc_badge = location_enrich.format_badge(h.get("loc"))
        if loc_badge:
            lines.append(f"  - {loc_badge}")


def _seoul_table(lines: list, s: dict, v: dict):
    lines.append(f"### {v['seoul_table']}")
    lines.append("")
    lines.append("| 구 | 신규 | 신고가 비중 | 중앙가 변화(믹스보정) | 비고 |")
    lines.append("|----|----|----|----|----|")
    for gu, g in indicators.rank_regions(s["per_gu"]):
        flag = "⚠️직거래↑" if g["segment"].get("direct_deal_spike") else ""
        lines.append(f"| {gu} | {g['new_count']} | {g['breadth']['high_pct']:.0f}% "
                     f"| {_fmt_pct(g.get('mix_change'))} | {flag} |")
    lines.append("")


def _seoul_highlights(lines: list, s: dict, v: dict):
    lines.append(f"### {v['seoul_highlights']}")
    lines.append("")
    _render_highlights(lines, s["highlights"], 15)
    lines.append("")


def _seoul_jeonse(lines: list, s: dict, v: dict):
    rated = {gu: r for gu, r in (s.get("jeonse") or {}).items() if r is not None}
    lines.append(f"### {v['seoul_jeonse']}")
    lines.append("")
    js = s.get("jeonse_seoul")
    if js is not None:
        lines.append(f"서울 평균 전세가율 **{js:.1f}%** (70%↑면 갭투자 위험 신호). 높은 구 순:")
    lines.append("")
    lines.append("| 구 | 전세가율 |")
    lines.append("|----|----|")
    for gu, r in sorted(rated.items(), key=lambda kv: kv[1], reverse=True)[:10]:
        lines.append(f"| {gu} | {r:.1f}%{' ⚠️' if r >= 70 else ''} |")
    lines.append("")


def _seoul_officetel(lines: list, s: dict, v: dict):
    lines.append(f"### {v['seoul_officetel']}")
    lines.append("")
    if s.get("officetel_total"):
        oftl = s.get("officetel") or {}
        active = sorted(((g, c) for g, c in oftl.items() if c), key=lambda x: -x[1])[:5]
        top = ", ".join(f"{g} {c}건" for g, c in active)
        lines.append(f"매매 **{s['officetel_total']}건**"
                     + (f" — 활발: {top}" if top else "") + ".")
        lines.append("")
    if s.get("officetel_rent_total"):
        lines.append(f"전월세 **{s['officetel_rent_total']}건** "
                     f"(전세 {s.get('officetel_rent_jeonse', 0)}건 · "
                     f"월세 {s.get('officetel_rent_wolse', 0)}건).")
        lines.append("")


def _render_seoul(lines: list, s: dict, v: dict):
    lines.append(f"## {v['seoul']}")
    lines.append("")
    lines.append(f"신규 **{s['new_total']}건**, 신고가 **{s['high_total']}건"
                 f"({s['high_pct']:.1f}%)**, 신저점 **{s['low_total']}건**.")
    lines.append("")
    # 읽는 흐름이 깨지지 않게 두 묶음 안에서만 회전한다.
    # 앞: 아파트 본편(구별 표 · 신고가 단지) / 뒤: 부가 지표(전세가율 · 오피스텔).
    head = [_seoul_table] + ([_seoul_highlights] if s["highlights"] else [])
    tail = []
    if any(r is not None for r in (s.get("jeonse") or {}).values()):
        tail.append(_seoul_jeonse)
    if s.get("officetel_total") or s.get("officetel_rent_total"):
        tail.append(_seoul_officetel)
    for render in (variation.rotate(v["seed"], "seoul_head", head)
                   + variation.rotate(v["seed"], "seoul_tail", tail)):
        render(lines, s, v)


def _render_group(lines: list, title: str, stats: dict, highlights: list,
                  show_officetel: bool, suffix: str = ""):
    lines.append(f"## {title}{suffix}")
    lines.append("")
    parts = [f"신규 **{stats['new_total']}건**",
             f"신고가 {stats['high_total']}건({stats['high_pct']:.1f}%)"]
    if stats.get("avg_jeonse") is not None:
        parts.append(f"평균 전세가율 {stats['avg_jeonse']:.1f}%")
    if show_officetel and (stats.get("officetel_total") or stats.get("officetel_rent_total")):
        parts.append(f"오피스텔 매매 {stats.get('officetel_total', 0)}건·"
                     f"전월세 {stats.get('officetel_rent_total', 0)}건")
    lines.append(" · ".join(parts) + ".")
    lines.append("")
    movers = stats.get("top_movers") or []
    if movers:
        top = ", ".join(f"{_gu_short(gu)} {m['new_count']}건({m['high_pct']:.0f}%)"
                        for gu, m in movers)
        lines.append(f"뜨거운 시군구: {top}.")
        lines.append("")
    if highlights:
        _render_highlights(lines, highlights, 3)
        lines.append("")


def build_digest(d: dict) -> str:
    nat = d["national"]
    groups = d.get("groups") or {}
    hbg = d.get("highlights_by_group") or {}
    v = variation.headers(d["week_label"])
    lines = [f"## {v['national']}", ""]

    if nat["new_total"] == 0:
        lines.append("이번 주 신규 신고된 거래가 없습니다.")
        lines.append("")
        lines.append("> 데이터: 국토교통부 실거래가. 최근 월은 신고 지연으로 미확정.")
        return "\n".join(lines)

    # 전국 헤더
    lines.append(v["national_lead"].format(
        new=nat["new_total"], high=nat["high_total"],
        pct=f"{nat['high_pct']:.1f}", low=nat["low_total"]))
    lines.append("")
    order = [g for g in ["서울", "경기"] if g in groups] \
        + [g for g in _METRO_ORDER if g in groups] \
        + [g for g in ["세종"] if g in groups]
    summary = " · ".join(f"{g} 신규 {groups[g]['new_total']}건" for g in order)
    if summary:
        lines.append(f"권역별: {summary}.")
        lines.append("")

    # 서울 상세 (항상 선두 — 상세 스코프이므로 순서 변주 대상 아님)
    if d.get("seoul") and d["seoul"].get("new_total"):
        _render_seoul(lines, d["seoul"], v)

    def _gyeonggi(out):
        _render_group(out, "경기", groups["경기"], hbg.get("경기", []),
                      show_officetel=True, suffix=v["group_suffix"])

    def _metros(out):
        out.append(f"## {v['metro']}")
        out.append("")
        for city in metro_present:
            _render_group(out, city, groups[city], hbg.get(city, []), show_officetel=True)

    def _sejong(out):
        _render_group(out, "세종", groups["세종"], hbg.get("세종", []),
                      show_officetel=False, suffix=v["group_suffix"])

    # 경기·광역시는 주마다 순서 회전, 세종(최소 물량)은 항상 마지막
    metro_present = [g for g in _METRO_ORDER if g in groups]
    blocks = []
    if "경기" in groups:
        blocks.append(_gyeonggi)
    if metro_present:
        blocks.append(_metros)
    blocks = variation.rotate(v["seed"], "region_blocks", blocks)
    if "세종" in groups:
        blocks.append(_sejong)
    for render in blocks:
        render(lines)

    lines.append("> 데이터: 국토교통부 실거래가. 최근 월은 신고 지연으로 미확정이며, "
                 "중앙가 변화는 동일 평형밴드 매칭(믹스보정) 기준.")
    return "\n".join(lines)
