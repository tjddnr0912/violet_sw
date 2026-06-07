"""편집 레이어 C3 — 고유 데이터 블록(표).

봇이 마크다운을 만들 때(데이터가 dict로 살아있는 단계)에서 호출해, 봇만 가진
수치를 **결정적(deterministic) 마크다운 표**로 본문에 박아 넣는다. 표는
claude_html_converter가 styled HTML 표로 변환하며, Tistory로 복사돼도 안전하다.

설계 배경: docs/ADSENSE_EDITORIAL_LAYER.md (C3)
"고유 데이터"는 경쟁 AI 블로그가 흉내 못 내는 가장 강한 originality/experience 신호다.
"""

from __future__ import annotations

from typing import Iterable, Sequence


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence]) -> str:
    """헤더 + 행 리스트를 깃허브-flavored 마크다운 표 문자열로 만든다."""
    headers = list(headers)
    head = "| " + " | ".join(str(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body_lines = []
    for row in rows:
        cells = list(row)
        # 열 수가 모자라면 빈 칸으로 채움
        if len(cells) < len(headers):
            cells = cells + [""] * (len(headers) - len(cells))
        body_lines.append("| " + " | ".join(str(c) for c in cells[: len(headers)]) + " |")
    return "\n".join([head, sep, *body_lines])


def news_quality_block(stats: dict) -> str:
    """일간 뉴스봇의 수집 통계(stats)를 독자용 데이터 섹션 마크다운으로 만든다.

    stats: news_bot.orchestrator._compute_stats 결과
        {total, by_category: {cat:count}, tier1_ratio, korean_ratio}
    데이터가 없으면 빈 문자열을 반환(본문 변화 없음).
    """
    if not stats:
        return ""
    total = stats.get("total", 0)
    if not total:
        return ""

    by_cat = stats.get("by_category") or {}
    lines = [
        "## 이번 호 수집 데이터",
        "",
        f"이번 요약은 여러 매체에서 모은 **총 {total}건**의 기사를 카테고리별로 선별했습니다.",
        "",
    ]

    if by_cat:
        rows = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)
        lines.append(markdown_table(["카테고리", "기사 수"], rows))
        lines.append("")

    tier1 = stats.get("tier1_ratio")
    korean = stats.get("korean_ratio")
    bullets = []
    if tier1 is not None:
        bullets.append(f"- 주요 매체(Tier-1) 비중: **{round(tier1 * 100)}%**")
    if korean is not None:
        kr = round(korean * 100)
        bullets.append(f"- 국내·해외 비율: 국내 **{kr}%** / 해외 **{100 - kr}%**")
    if bullets:
        lines.extend(bullets)

    return "\n".join(lines).rstrip() + "\n"
