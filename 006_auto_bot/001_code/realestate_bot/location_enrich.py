"""신고가/신저점 단지의 반경 500m 입지 enrichment (카카오 로컬 API).

단지명 → 좌표(키워드검색) → 반경 내 초등학교/학원/지하철(GTX) 카운트.
- 초등학교: SC4 결과를 category_name='초등학교'로 필터(초/중/고 혼입 방지)
- 학원   : AC5 는 meta.total_count 만 사용(수백 개여도 1콜). 계열 필터는 카카오 불가 → 향후 공공데이터 학원표준데이터로 보강 여지
- 지하철 : SW8 반경 결과 역명 나열 + 'GTX' 문자열로 GTX 판별

게이트: KAKAO_REST_API_KEY 있고 LOCATION_ENRICH_ENABLED != 'false' 일 때만 동작.
키가 없으면 조용히 비활성(디제스트는 배지 없이 그대로 발행).
"""
import logging
import os
import re
import time

import requests

logger = logging.getLogger(__name__)

_BASE = "https://dapi.kakao.com/v2/local"
_TIMEOUT = 8
_PACING = 0.03  # 호출 간 간격(초) — 429 예방


def is_enabled() -> bool:
    """카카오 키가 있고 명시적으로 끄지 않았으면 활성."""
    if os.getenv("LOCATION_ENRICH_ENABLED", "true").strip().lower() == "false":
        return False
    return bool(os.getenv("KAKAO_REST_API_KEY", "").strip())


def _radius() -> int:
    try:
        return int(os.getenv("LOCATION_ENRICH_RADIUS", "500"))
    except ValueError:
        return 500


def _headers() -> dict:
    return {"Authorization": f"KakaoAK {os.getenv('KAKAO_REST_API_KEY', '').strip()}"}


def _get(path: str, params: dict, tries: int = 3) -> dict:
    """카카오 로컬 GET — 429 백오프. 실패 시 예외 전파(호출부에서 흡수)."""
    for i in range(tries):
        r = requests.get(f"{_BASE}/{path}", headers=_headers(),
                         params=params, timeout=_TIMEOUT)
        if r.status_code == 429:
            time.sleep(0.4 * (i + 1))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


# ---- 순수 헬퍼(네트워크 無, 테스트 대상) --------------------------------

def _is_elementary(doc: dict) -> bool:
    """카카오 SC4 문서가 초등학교인지."""
    cat = doc.get("category_name") or ""
    name = doc.get("place_name") or ""
    return "초등학교" in cat or name.endswith("초등학교")


def _detect_gtx(station_names: list) -> list:
    """역명 리스트에서 GTX 노선 역만 추출."""
    return [n for n in station_names if "GTX" in n.upper() or "광역급행" in n]


# 예체능·취미·실기·기타 비교과 학원(카카오 category_name leaf 부분일치로 제외).
# 나머지(입시/보습/논술/어학/영어/수학/과학/국어/컴퓨터/일반 '학원')는 교과로 집계.
_NON_ACADEMIC = (
    "음악", "미술", "무용", "댄스", "발레", "피아노", "성악", "국악", "실용음악",
    "태권도", "검도", "유도", "합기도", "복싱", "주짓수", "무술", "체육", "스포츠",
    "골프", "수영", "요가", "필라테스", "클라이밍", "요리", "제과", "바리스타",
    "웅변", "연기", "방송", "모델", "미용", "네일", "뷰티", "운전", "공예",
    "서예", "애견", "바둑", "꽃꽂이", "댄스스포츠",
)


def _is_academic_academy(doc: dict) -> bool:
    """카카오 AC5 문서가 교과(입시·보습·어학 등) 학원인지 — 예체능/취미면 False."""
    leaf = (doc.get("category_name") or "").split(">")[-1].strip()
    return not any(bad in leaf for bad in _NON_ACADEMIC)


def _pick_apt(docs: list, dong: str = "") -> dict | None:
    """키워드 검색 결과에서 아파트 카테고리만 채택. dong 있으면 주소 매칭 우선."""
    apt_docs = [d for d in docs if "아파트" in (d.get("category_name") or "")]
    if not apt_docs:
        return None
    if dong:
        for d in apt_docs:
            if dong in (d.get("address_name") or ""):
                return d
    return apt_docs[0]


def format_badge(loc: dict | None) -> str:
    """enrichment dict → 디제스트용 한 줄 배지. loc 없으면 빈 문자열."""
    if not loc:
        return ""
    academy = f"{loc['academy']}{'+' if loc.get('academy_capped') else ''}"
    parts = [f"🏫 초 {loc['elementary']}", f"📚 교과학원 {academy}"]
    if loc.get("subway_names"):
        subway = " · ".join(loc["subway_names"])
        if loc.get("gtx"):
            subway += " ✨GTX"
        parts.append(f"🚇 {subway}")
    else:
        parts.append("🚇 500m 내 없음")
    return " · ".join(parts)


# ---- 네트워크 경로 --------------------------------------------------------

def _geocode(gu: str, apt: str, dong: str = "") -> dict | None:
    """단지명 → 좌표. 아파트 카테고리 필터 + 캐스케이드로 오매칭/실패 최소화."""
    clean = re.sub(r"\(.*?\)", "", apt).strip()
    loc = f"{gu} {dong}".strip()
    queries = [f"{loc} {apt} 아파트", f"{loc} {clean} 아파트",
               f"{loc} {clean}", f"{gu} {clean} 아파트", f"{gu} {clean}"]
    seen = set()
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        docs = _get("search/keyword.json", {"query": q, "size": 10}).get("documents") or []
        best = _pick_apt(docs, dong)
        if best:
            return {"x": best["x"], "y": best["y"], "matched": best.get("place_name"),
                    "addr": best.get("road_address_name") or best.get("address_name")}
    return None


def _fetch_category(x, y, code: str) -> tuple:
    """반경 내 카테고리 문서 회수. (docs, total_count, capped) 반환.

    카카오는 pageable_count(<=45)까지만 회수 → total_count > 회수수면 capped=True
    (밀집지 학원 등에서 발생). is_end 시점까지 페이지 순회."""
    out, page, radius, total = [], 1, _radius(), 0
    while page <= 45:
        d = _get("search/category.json", {"category_group_code": code, "x": x, "y": y,
                                          "radius": radius, "size": 15, "page": page})
        out.extend(d.get("documents") or [])
        meta = d.get("meta") or {}
        total = meta.get("total_count", len(out))
        if meta.get("is_end", True):
            break
        page += 1
        time.sleep(_PACING)
    return out, total, total > len(out)


def enrich_one(gu: str, apt_name: str, dong: str = "") -> dict | None:
    """단지 1건 → {matched, addr, elementary, academy, subway, subway_names, gtx} 또는 None.

    지오코딩 실패/네트워크 오류는 None 반환(발행은 계속 — 입지 배지만 생략)."""
    try:
        geo = _geocode(gu, apt_name, dong)
        if not geo:
            logger.info("입지 지오코딩 실패: %s %s %s", gu, dong, apt_name)
            return None
        x, y = geo["x"], geo["y"]
        schools, _, _ = _fetch_category(x, y, "SC4")
        elem = [s for s in schools if _is_elementary(s)]
        ac_docs, ac_total, ac_capped = _fetch_category(x, y, "AC5")
        academic = [a for a in ac_docs if _is_academic_academy(a)]
        sub_docs, _, _ = _fetch_category(x, y, "SW8")
        subways = [s.get("place_name", "") for s in sub_docs]
        return {"matched": geo["matched"], "addr": geo["addr"],
                "elementary": len(elem), "elem_names": [e["place_name"] for e in elem],
                "academy": len(academic),       # 교과학원(예체능 제외)
                "academy_total": ac_total,      # 전체 학원(예체능 포함) raw total_count
                "academy_capped": ac_capped,    # 회수 상한(45) 도달 → 교과학원은 floor
                "subway": len(subways),
                "subway_names": subways, "gtx": _detect_gtx(subways)}
    except Exception as e:  # noqa: BLE001
        logger.warning("입지 enrichment 오류(%s %s): %s", gu, apt_name, e)
        return None


def enrich_highlights(highlights: list, limit: int = 15) -> list:
    """highlights 앞 limit개에 'loc' 필드를 부착(in-place). 비활성/실패 시 무변.

    같은 (gu, apt, dong)은 run 내 1회만 조회(캐시)."""
    if not is_enabled():
        return highlights
    cache: dict = {}
    enriched = 0
    for h in highlights[:limit]:
        key = (h.get("gu", ""), h.get("apt_name", ""), h.get("dong", ""))
        if key not in cache:
            cache[key] = enrich_one(*key)
            time.sleep(_PACING)
        h["loc"] = cache[key]
        if cache[key]:
            enriched += 1
    logger.info("입지 enrichment: %d/%d 단지 성공", enriched, min(len(highlights), limit))
    return highlights
