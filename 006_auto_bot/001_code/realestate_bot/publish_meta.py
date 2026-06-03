"""블로그 제목·주차·라벨 — 순수함수. 주차별 일관 제목 + 내용 반영 동적 라벨."""
from datetime import date

_HEADLINE_FALLBACK = "전국 아파트 시장 흐름"
_BASE_LABELS = ["부동산", "아파트", "실거래가", "주간시황", "전국", "전세가율"]
_HIGH_PCT_LABEL_THRESHOLD = 15.0   # 전국 신고가 비중 이 이상이면 '신고가' 라벨


def week_of_month(d: date) -> str:
    """발행일 → 'N월 M주차'. M = ((일-1)//7)+1 (결정적, 라이브러리 불필요)."""
    return f"{d.month}월 {((d.day - 1) // 7) + 1}주차"


def build_title(d: date, headline: str) -> str:
    """'YYYY-MM-DD, N월 M주차 {헤드라인}'. 헤드라인 비면 fallback."""
    head = (headline or "").strip() or _HEADLINE_FALLBACK
    return f"{d.isoformat()}, {week_of_month(d)} {head}"


def build_labels(groups: dict, hottest_gu: str = None) -> list:
    """7~9개 라벨. 고정6 + 신규 최다 권역 + (조건부 신고가/오피스텔) + 핫스팟 구.

    groups: rollup_groups 결과 {권역명: {new_total, high_total, officetel_total, officetel_rent_total}}.
    """
    labels = list(_BASE_LABELS)
    if groups:
        hot_group = max(groups.items(), key=lambda kv: kv[1]["new_total"])[0]
        labels.append(hot_group)
    if hottest_gu:                      # 핫스팟 구는 토픽 라벨보다 우선(9 cap에서 안 잘리게)
        labels.append(hottest_gu)
    if groups:
        nat_new = sum(g["new_total"] for g in groups.values())
        nat_high = sum(g["high_total"] for g in groups.values())
        if nat_new and nat_high / nat_new * 100 >= _HIGH_PCT_LABEL_THRESHOLD:
            labels.append("신고가")
        oftl = sum(g.get("officetel_total", 0) + g.get("officetel_rent_total", 0)
                   for g in groups.values())
        if oftl > 0:
            labels.append("오피스텔")
    out = []
    for label in labels:
        if label not in out:
            out.append(label)
    return out[:9]
