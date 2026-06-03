"""주간 다이제스트 markdown 빌드 — 요약→하이라이트→상세 깔때기."""
from realestate_bot import config, indicators


def _baseline_label() -> str:
    """신고가 기준 윈도우 라벨을 config.BASELINE_MONTHS에서 동적 도출 (과장 방지)."""
    m = config.BASELINE_MONTHS
    return f"최근 {m // 12}년" if m % 12 == 0 else f"최근 {m}개월"


def _fmt_won(man: int) -> str:
    """만원 단위 정수 -> '12억 3,400만'."""
    eok, rem = divmod(int(man), 10000)
    if eok and rem:
        return f"{eok}억 {rem:,}만"
    if eok:
        return f"{eok}억"
    return f"{rem:,}만"


def _fmt_pct(p):
    if p is None:
        return "—"
    return f"{p:+.1f}%"


def build_digest(d: dict) -> str:
    seoul = d["seoul"]
    lines = []
    lines.append(f"## 서울 아파트 시장 흐름 — {d['week_label']}")
    lines.append("")
    if seoul["new_total"] == 0:
        lines.append("이번 주 신규 신고된 거래가 없습니다.")
        lines.append("")
        lines.append("> 데이터: 국토교통부 실거래가. 최근 월은 신고 지연으로 미확정.")
        return "\n".join(lines)

    lines.append(
        f"이번 주 신규 신고 **{seoul['new_total']}건**, "
        f"신고가 **{seoul['high_total']}건({seoul['high_pct']:.1f}%)**, "
        f"신저점 **{seoul['low_total']}건**."
    )
    lines.append("")

    # 순위표
    lines.append("## 구별 온도차 (뜨거운 순)")
    lines.append("")
    lines.append("| 구 | 신규 | 신고가 비중 | 중앙가 변화(믹스보정) | 비고 |")
    lines.append("|----|----|----|----|----|")
    for gu, g in indicators.rank_regions(d["per_gu"]):
        flag = "⚠️직거래↑" if g["segment"].get("direct_deal_spike") else ""
        lines.append(
            f"| {gu} | {g['new_count']} | {g['breadth']['high_pct']:.0f}% "
            f"| {_fmt_pct(g.get('mix_change'))} | {flag} |"
        )
    lines.append("")

    # 신고가/신저점 하이라이트
    if d["highlights"]:
        lines.append("## 신고가·신저점 단지")
        lines.append("")
        for h in d["highlights"]:
            badge = "🔼 신고가" if h["kind"] == "HIGH" else "🔽 신저점"
            lines.append(
                f"- {badge} **{h['gu']} {h['apt_name']} {h['area_band']}㎡대** — "
                f"{_fmt_won(h['price_10k'])} ({_fmt_pct(h['pct'])}, "
                f"직전 {_fmt_won(h['ref_price'])} {h['ref_date']}) · {_baseline_label()} 기준"
            )
        lines.append("")

    # 전세가율 (매매+전세 종합) — 데이터 있을 때만
    jeonse = d.get("jeonse") or {}
    rated = {gu: r for gu, r in jeonse.items() if r is not None}
    if rated:
        js = d.get("jeonse_seoul")
        lines.append("## 전세가율 (갭투자 위험 지표)")
        lines.append("")
        if js is not None:
            lines.append(f"서울 평균 전세가율 **{js:.1f}%** "
                         f"(70%↑면 갭투자 위험 신호). 높은 구 순:")
        lines.append("")
        top = sorted(rated.items(), key=lambda kv: kv[1], reverse=True)[:10]
        lines.append("| 구 | 전세가율 |")
        lines.append("|----|----|")
        for gu, r in top:
            warn = " ⚠️" if r >= 70 else ""
            lines.append(f"| {gu} | {r:.1f}%{warn} |")
        lines.append("")

    # 오피스텔 시장 — 데이터 있을 때만
    if d.get("officetel_total"):
        oftl = d.get("officetel") or {}
        active = sorted(((g, c) for g, c in oftl.items() if c), key=lambda x: -x[1])[:5]
        top_str = ", ".join(f"{g} {c}건" for g, c in active)
        lines.append("## 오피스텔 시장")
        lines.append("")
        lines.append(f"이번 집계 서울 오피스텔 매매 **{d['officetel_total']}건**"
                     + (f" — 활발: {top_str}" if top_str else "") + ".")
        lines.append("")

    lines.append("> 데이터: 국토교통부 실거래가. 최근 월은 신고 지연으로 미확정이며, "
                 "중앙가 변화는 동일 평형밴드 매칭(믹스보정) 기준.")
    return "\n".join(lines)
