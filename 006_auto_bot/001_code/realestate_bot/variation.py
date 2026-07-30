"""주간 디제스트 헤더·섹션 순서 변주 — 주차 시드 기반 결정적 선택.

목적: 매주 같은 헤더·같은 순서로 찍혀 나오는 신호(scaled content) 완화.
`random` 금지 — 같은 주를 재실행하면 항상 같은 결과가 나와야 백필·재발행이 안전하다.
"""
import hashlib

_HEADERS = {
    # h2 전국 리드 ({week} = week_label)
    "national": [
        "전국 아파트 시장 흐름 — {week}",
        "이번 주 전국 실거래 요약 — {week}",
        "전국 아파트, 이번 주 숫자부터 — {week}",
        "주간 전국 아파트 지표 — {week}",
    ],
    # 전국 리드 문장 ({new}/{high}/{pct}/{low})
    "national_lead": [
        "이번 주 전국 신규 신고 **{new}건**, 신고가 **{high}건({pct}%)**, 신저점 **{low}건**.",
        "전국 신규 **{new}건** — 신고가 **{high}건({pct}%)**, 신저점 **{low}건**.",
        "이번 주 신규 신고는 **{new}건**. 이 가운데 신고가 **{high}건({pct}%)**, "
        "신저점 **{low}건**.",
        "신규 **{new}건** 중 신고가 **{high}건({pct}%)** · 신저점 **{low}건**.",
    ],
    # h2 서울 (반드시 '서울'로 시작 — 권역 식별자 유지)
    "seoul": [
        "서울 (상세)",
        "서울 상세 — 구별 온도차",
        "서울 — 25개 구 상세",
        "서울 상세",
    ],
    "seoul_table": [
        "구별 온도차 (뜨거운 순)",
        "25개 구 온도차 — 뜨거운 순",
        "구별 신고가 비중과 중앙가 변화",
        "구 단위 온도차 — 신규·신고가 비중 순",
    ],
    "seoul_highlights": [
        "신고가·신저점 단지",
        "이번 주 신고가·신저점 단지",
        "값을 새로 쓴 단지들",
        "신고가·신저점이 나온 곳",
    ],
    # '전세가율' 키워드 유지 — 지표명 자체는 바꾸지 않는다
    "seoul_jeonse": [
        "전세가율 (갭투자 위험 지표)",
        "전세가율로 본 갭투자 위험",
        "전세가율 상위 구 — 갭 위험 점검",
        "구별 전세가율",
    ],
    "seoul_officetel": [
        "오피스텔 시장",
        "오피스텔 매매·전월세",
        "오피스텔 거래 동향",
        "오피스텔은 어디에 몰렸나",
    ],
    # h2 광역시 묶음 ('광역시' 키워드 유지)
    "metro": [
        "6대 광역시",
        "6대 광역시 — 시별 요약",
        "지방 광역시 흐름",
        "6대 광역시 시별 정리",
    ],
    # h2 권역 접미 (앞에 권역명이 붙는다: '## 경기{suffix}')
    "group_suffix": [
        "",
        " — 권역 요약",
        " — 시군구 요약",
        " 시장",
    ],
}


def _h(*parts) -> int:
    raw = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:12], 16)


def seed(week_label: str) -> int:
    """주차 라벨 → 결정적 시드."""
    return _h(week_label or "")


def pick(sd: int, slot: str, options: list = None):
    """슬롯별 결정적 선택. options 미지정 시 내장 헤더 풀 사용."""
    pool = options if options is not None else _HEADERS.get(slot) or []
    return pool[_h(slot, sd) % len(pool)] if pool else ""


def rotate(sd: int, slot: str, items: list) -> list:
    """리스트를 결정적으로 회전 — 내용은 그대로, 순서만 주마다 이동."""
    items = list(items)
    if len(items) < 2:
        return items
    k = _h(slot, sd) % len(items)
    return items[k:] + items[:k]


def headers(week_label: str) -> dict:
    """주차별 헤더 세트 + 시드. digest 렌더러가 통째로 받아 쓴다."""
    sd = seed(week_label)
    out = {slot: pick(sd, slot) for slot in _HEADERS}
    out["national"] = out["national"].format(week=week_label)
    out["seed"] = sd
    return out
