"""전국 권역 주간 디제스트 markdown 빌드 — 전국 헤더 → 서울 상세 → 권역 요약."""
from realestate_bot import config, indicators

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


def _render_seoul(lines: list, s: dict):
    lines.append("## 서울 (상세)")
    lines.append("")
    lines.append(f"신규 **{s['new_total']}건**, 신고가 **{s['high_total']}건"
                 f"({s['high_pct']:.1f}%)**, 신저점 **{s['low_total']}건**.")
    lines.append("")
    lines.append("### 구별 온도차 (뜨거운 순)")
    lines.append("")
    lines.append("| 구 | 신규 | 신고가 비중 | 중앙가 변화(믹스보정) | 비고 |")
    lines.append("|----|----|----|----|----|")
    for gu, g in indicators.rank_regions(s["per_gu"]):
        flag = "⚠️직거래↑" if g["segment"].get("direct_deal_spike") else ""
        lines.append(f"| {gu} | {g['new_count']} | {g['breadth']['high_pct']:.0f}% "
                     f"| {_fmt_pct(g.get('mix_change'))} | {flag} |")
    lines.append("")
    if s["highlights"]:
        lines.append("### 신고가·신저점 단지")
        lines.append("")
        _render_highlights(lines, s["highlights"], 15)
        lines.append("")
    rated = {gu: r for gu, r in (s.get("jeonse") or {}).items() if r is not None}
    if rated:
        lines.append("### 전세가율 (갭투자 위험 지표)")
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
    if s.get("officetel_total") or s.get("officetel_rent_total"):
        lines.append("### 오피스텔 시장")
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


def _render_group(lines: list, title: str, stats: dict, highlights: list,
                  show_officetel: bool):
    lines.append(f"## {title}")
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
    lines = [f"## 전국 아파트 시장 흐름 — {d['week_label']}", ""]

    if nat["new_total"] == 0:
        lines.append("이번 주 신규 신고된 거래가 없습니다.")
        lines.append("")
        lines.append("> 데이터: 국토교통부 실거래가. 최근 월은 신고 지연으로 미확정.")
        return "\n".join(lines)

    # 전국 헤더
    lines.append(f"이번 주 전국 신규 신고 **{nat['new_total']}건**, "
                 f"신고가 **{nat['high_total']}건({nat['high_pct']:.1f}%)**, "
                 f"신저점 **{nat['low_total']}건**.")
    lines.append("")
    order = [g for g in ["서울", "경기"] if g in groups] \
        + [g for g in _METRO_ORDER if g in groups] \
        + [g for g in ["세종"] if g in groups]
    summary = " · ".join(f"{g} 신규 {groups[g]['new_total']}건" for g in order)
    if summary:
        lines.append(f"권역별: {summary}.")
        lines.append("")

    # 서울 상세
    if d.get("seoul") and d["seoul"].get("new_total"):
        _render_seoul(lines, d["seoul"])

    # 경기 요약
    if "경기" in groups:
        _render_group(lines, "경기", groups["경기"], hbg.get("경기", []), show_officetel=True)

    # 6대 광역시 요약 (시별)
    metro_present = [g for g in _METRO_ORDER if g in groups]
    if metro_present:
        lines.append("## 6대 광역시")
        lines.append("")
        for city in metro_present:
            _render_group(lines, city, groups[city], hbg.get(city, []), show_officetel=True)

    # 세종 요약
    if "세종" in groups:
        _render_group(lines, "세종", groups["세종"], hbg.get("세종", []), show_officetel=False)

    lines.append("> 데이터: 국토교통부 실거래가. 최근 월은 신고 지연으로 미확정이며, "
                 "중앙가 변화는 동일 평형밴드 매칭(믹스보정) 기준.")
    return "\n".join(lines)
