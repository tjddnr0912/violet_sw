# 부동산봇 전국 권역 디제스트 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주간 부동산 디제스트의 발행 범위를 서울 25구 → 전국 119시군구(서울 상세 + 경기·광역시·세종 권역 요약) 단일 블로그 글로 확장하고, 제목을 주차별 일관 형식 + AI 헤드라인으로, 라벨을 7~9개 동적으로 만든다.

**Architecture:** 데이터 수집·diff·집계는 기존 `build_report`/`synthesize`를 `ALL_REGIONS`로 호출. 새 순수함수 `rollup_groups`가 구별 지표를 권역별로 집계하고, `digest.build_digest`가 전국 헤더 + 서울 상세(기존 렌더 재사용) + 권역 요약을 조립. 제목·주차·라벨은 신규 `publish_meta` 모듈. 숫자=코드/해석=Gemini/HTML=Claude 하이브리드 불변.

**Tech Stack:** Python 3.13, SQLite, pytest, 직접 MCP stdio(`mcp_client`), Gemini API(`shared.gemini_cli`), Claude CLI(`shared.claude_html_converter`), Blogger v3(`shared.blogger_uploader`).

**Spec:** `006_auto_bot/docs/superpowers/specs/2026-06-04-realestate-national-digest-expansion-design.md`

**작업 디렉토리:** 모든 명령은 `006_auto_bot/001_code`에서 `.venv/bin/python` 사용.

---

## File Structure

| 파일 | 책임 | 변경 |
|------|------|------|
| `realestate_bot/regions_extra.py` | 권역 코드·매핑 | `REGION_GROUPS`, `group_of()` 추가 |
| `realestate_bot/indicators.py` | 순수 지표 집계 | `rollup_groups()` 추가 |
| `realestate_bot/publish_meta.py` | 제목·주차·라벨 | **신규** |
| `realestate_bot/commentary.py` | AI 시황 | 전국 다문단 프롬프트로 교체 |
| `realestate_bot/digest.py` | markdown 조립 | 전국 헤더 + 서울 상세 + 권역 요약 구조로 재편 |
| `weekly_realestate_bot.py` | 오케스트레이션 | `run()` 배선: `ALL_REGIONS`, rollup, 제목·라벨, blog_title 보존 |
| `tests/realestate/test_regions.py` | | **신규** |
| `tests/realestate/test_indicators.py` | | `rollup_groups` 테스트 추가 |
| `tests/realestate/test_publish_meta.py` | | **신규** |
| `tests/realestate/test_commentary.py` | | 전국 입력 테스트 추가 |
| `tests/realestate/test_digest.py` | | 새 입력 형태로 재작성 |
| `tests/realestate/test_orchestration.py` | | run 통합(전국) 테스트 추가 |

---

## Task 1: 권역 매핑 헬퍼 (regions_extra)

**Files:**
- Modify: `realestate_bot/regions_extra.py` (파일 끝에 추가)
- Test: `tests/realestate/test_regions.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`tests/realestate/test_regions.py` 생성:

```python
from realestate_bot.regions_extra import REGION_GROUPS, group_of, METRO_PREFIXES


def test_group_of_by_prefix():
    assert group_of("11680") == "서울"      # 강남구
    assert group_of("41135") == "경기"      # 성남 분당
    assert group_of("26110") == "부산"
    assert group_of("27110") == "대구"
    assert group_of("28110") == "인천"
    assert group_of("29110") == "광주"
    assert group_of("30110") == "대전"
    assert group_of("31110") == "울산"
    assert group_of("36110") == "세종"


def test_group_of_unknown_prefix_is_etc():
    assert group_of("99999") == "기타"


def test_metro_prefixes_are_six_cities():
    assert set(METRO_PREFIXES) == {"26", "27", "28", "29", "30", "31"}
    # 광역시 prefix는 전부 REGION_GROUPS에 시명으로 등록돼 있다
    for p in METRO_PREFIXES:
        assert p in REGION_GROUPS
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_regions.py -q`
Expected: FAIL — `ImportError: cannot import name 'REGION_GROUPS'`

- [ ] **Step 3: 구현**

`realestate_bot/regions_extra.py` 맨 끝에 추가:

```python

# ── 권역 그룹 (지역코드 2자리 prefix → 권역명) ─────────────────────────
REGION_GROUPS = {
    "11": "서울", "41": "경기",
    "26": "부산", "27": "대구", "28": "인천",
    "29": "광주", "30": "대전", "31": "울산",
    "36": "세종",
}
METRO_PREFIXES = ("26", "27", "28", "29", "30", "31")  # 6대 광역시


def group_of(region_code: str) -> str:
    """지역코드 5자리 → 권역명(서울/경기/부산…울산/세종). 미등록 prefix는 '기타'."""
    return REGION_GROUPS.get(str(region_code)[:2], "기타")
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_regions.py -q`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/regions_extra.py tests/realestate/test_regions.py
git commit -m "Add 권역 그룹 매핑(group_of) for 전국 디제스트"
```

---

## Task 2: 권역 집계 rollup_groups (indicators)

per_gu(구별 지표)와 synthesize 결과(jeonse/officetel)를 권역별로 집계한다.

**Files:**
- Modify: `realestate_bot/indicators.py` (파일 끝에 추가)
- Test: `tests/realestate/test_indicators.py` (추가)

- [ ] **Step 1: 실패 테스트 작성**

`tests/realestate/test_indicators.py` 끝에 추가:

```python
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
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_indicators.py::test_rollup_groups_aggregates_by_group -q`
Expected: FAIL — `ImportError: cannot import name 'rollup_groups'`

- [ ] **Step 3: 구현**

`realestate_bot/indicators.py` 끝에 추가:

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_indicators.py -q`
Expected: PASS (기존 indicators 테스트 + 신규 2개)

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/indicators.py tests/realestate/test_indicators.py
git commit -m "Add rollup_groups 권역 집계 (순수함수)"
```

---

## Task 3: 제목·주차·라벨 모듈 (publish_meta)

**Files:**
- Create: `realestate_bot/publish_meta.py`
- Test: `tests/realestate/test_publish_meta.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

`tests/realestate/test_publish_meta.py` 생성:

```python
from datetime import date
from realestate_bot.publish_meta import week_of_month, build_title, build_labels


def test_week_of_month():
    assert week_of_month(date(2026, 6, 6)) == "6월 1주차"
    assert week_of_month(date(2026, 6, 13)) == "6월 2주차"
    assert week_of_month(date(2026, 6, 30)) == "6월 5주차"


def test_build_title_prefix_and_headline():
    t = build_title(date(2026, 6, 6), "전국 신고가 21%, 수도권 과열")
    assert t == "2026-06-06, 6월 1주차 전국 신고가 21%, 수도권 과열"


def test_build_title_fallback_when_empty():
    t = build_title(date(2026, 6, 6), "")
    assert t == "2026-06-06, 6월 1주차 전국 아파트 시장 흐름"


def test_build_labels_7_to_9_and_dynamic():
    groups = {
        "서울": {"new_total": 50, "high_total": 12, "officetel_total": 9, "officetel_rent_total": 80},
        "경기": {"new_total": 30, "high_total": 3, "officetel_total": 2, "officetel_rent_total": 10},
    }
    labels = build_labels(groups, hottest_gu="영등포구")
    assert 7 <= len(labels) <= 9
    assert labels[:6] == ["부동산", "아파트", "실거래가", "주간시황", "전국", "전세가율"]
    assert "서울" in labels          # 신규 최다 권역
    assert "영등포구" in labels       # 핫스팟 (토픽 라벨보다 우선)
    assert "신고가" in labels         # 15/80 = 18.75% ≥ 15%
    assert len(labels) == len(set(labels))   # 중복 없음
    # base6 + 서울(권역) + 영등포구(핫스팟) + 신고가 = 9; 오피스텔은 9 cap으로 탈락
    assert len(labels) == 9 and "오피스텔" not in labels


def test_build_labels_floor_7_without_optional():
    groups = {"서울": {"new_total": 50, "high_total": 2,
                       "officetel_total": 0, "officetel_rent_total": 0}}
    labels = build_labels(groups, hottest_gu=None)
    # 신고가(2/50=4%)·오피스텔·핫스팟 없음 → 고정6 + 권역1 = 7
    assert len(labels) == 7
    assert "서울" in labels
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_publish_meta.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'realestate_bot.publish_meta'`

- [ ] **Step 3: 구현**

`realestate_bot/publish_meta.py` 생성:

```python
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
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_publish_meta.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/publish_meta.py tests/realestate/test_publish_meta.py
git commit -m "Add publish_meta — 주차별 제목 + 동적 라벨(7~9)"
```

---

## Task 4: 시황 해석 전국 다문단 (commentary)

**Files:**
- Modify: `realestate_bot/commentary.py:7-13` (`_FRAME` 교체)
- Test: `tests/realestate/test_commentary.py` (추가)

- [ ] **Step 1: 실패 테스트 작성**

`tests/realestate/test_commentary.py` 끝에 추가:

```python
from realestate_bot import commentary as _c


def test_frame_is_national_multiparagraph():
    # 전국 다문단 지시가 프레임에 들어있다 (서울 전용 문구 아님)
    assert "전국" in _c._FRAME
    assert "광역시" in _c._FRAME


def test_make_commentary_degrades_without_ai(monkeypatch):
    def boom(_prompt):
        raise RuntimeError("no ai")
    monkeypatch.setattr(_c, "_ask_gemini", boom)
    assert _c.make_commentary({"national": {"new_total": 0}, "groups": {}}) == ""
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_commentary.py::test_frame_is_national_multiparagraph -q`
Expected: FAIL — `_FRAME`에 "전국"/"광역시" 없음(현재 서울 전용)

- [ ] **Step 3: 구현**

`realestate_bot/commentary.py`의 `_FRAME`(7~13행)을 아래로 교체:

```python
_FRAME = (
    "다음은 전국 주간 아파트 실거래 지표(코드가 계산한 확정 숫자)다. "
    "숫자를 재계산하지 말고, 서울·경기·6대 광역시를 고르게 다루는 3~5문단 시황을 "
    "한국어로 써라: ① 전국 거래량·온도 → ② 수도권(서울·경기) 흐름 → "
    "③ 지방 광역시 대비 → ④ 신고가/신저점·전세가율 신호. "
    "권역 간 온도차를 단정 대신 비교로 해석하고, 최근 월은 신고 지연으로 미확정임을 감안하라. "
    "한자 학술 용어 헤더(기승전결 등) 금지, 표/숫자 나열 금지, 해석 문장만.\n\n지표:\n"
)
```

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_commentary.py -q`
Expected: PASS (기존 + 신규 2개)

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/commentary.py tests/realestate/test_commentary.py
git commit -m "Update commentary 프롬프트 서울 전용 → 전국 다문단"
```

---

## Task 5: 전국 디제스트 구조 (digest)

`build_digest`를 **전국 헤더 + 서울 상세 + 권역 요약** 구조로 재편한다. 서울 상세 렌더(온도차 표·신고가/신저점·전세가율·오피스텔)는 기존 로직을 `_render_seoul`로 옮겨 재사용한다.

**새 `build_digest(d)` 입력 형태:**
```
d = {
  "week_label": str,
  "national": {"new_total","high_total","high_pct","low_total"},
  "groups": {권역명: rollup_groups 결과},
  "highlights_by_group": {권역명: [highlight,...]},
  "seoul": {  # 서울 상세용 (구별, 서울만 스코프)
      "per_gu": {...}, "highlights": [...],
      "jeonse": {...}, "jeonse_seoul": float|None,
      "officetel": {...}, "officetel_total": int,
      "officetel_rent": {...}, "officetel_rent_total": int,
      "officetel_rent_jeonse": int, "officetel_rent_wolse": int,
      "new_total": int, "high_total": int, "low_total": int, "high_pct": float,
  },
}
```
highlight 항목 형태(기존과 동일): `{gu, apt_name, area_band, price_10k, pct, kind, ref_price, ref_date}`.

**Files:**
- Modify: `realestate_bot/digest.py` (전면 재편, 헬퍼 보존)
- Test: `tests/realestate/test_digest.py` (새 입력 형태로 재작성)

- [ ] **Step 1: 실패 테스트 작성 (test_digest.py 전체 교체)**

`tests/realestate/test_digest.py` 전체를 아래로 교체:

```python
from realestate_bot import digest


def _seoul_block():
    return {
        "per_gu": {
            "강남구": {"new_count": 10, "breadth": {"high_pct": 50.0, "high": 5, "low": 0},
                       "mix_change": 3.2, "segment": {"direct_deal_spike": False}},
            "도봉구": {"new_count": 8, "breadth": {"high_pct": 0.0, "high": 0, "low": 1},
                       "mix_change": -1.1, "segment": {"direct_deal_spike": True}},
        },
        "highlights": [
            {"gu": "강남구", "apt_name": "은마", "area_band": 84, "price_10k": 280000,
             "pct": 4.5, "kind": "HIGH", "ref_price": 268000, "ref_date": "2026-03-01"},
        ],
        "jeonse": {"강남구": 55.0, "도봉구": 71.8}, "jeonse_seoul": 63.4,
        "officetel": {"강남구": 10}, "officetel_total": 10,
        "officetel_rent": {"강남구": 25}, "officetel_rent_total": 25,
        "officetel_rent_jeonse": 8, "officetel_rent_wolse": 17,
        "new_total": 18, "high_total": 5, "low_total": 1, "high_pct": 27.8,
    }


def _input():
    return {
        "week_label": "2026-06-06 기준 주간",
        "national": {"new_total": 60, "high_total": 11, "high_pct": 18.3, "low_total": 3},
        "groups": {
            "서울": {"new_total": 18, "high_total": 5, "high_pct": 27.8, "low_total": 1,
                     "avg_jeonse": 63.4, "officetel_total": 10, "officetel_rent_total": 25,
                     "top_movers": [("강남구", {"new_count": 10, "high_pct": 50.0})], "count": 25},
            "경기": {"new_total": 30, "high_total": 4, "high_pct": 13.3, "low_total": 1,
                     "avg_jeonse": 68.0, "officetel_total": 5, "officetel_rent_total": 40,
                     "top_movers": [("경기도 수원시 영통구", {"new_count": 12, "high_pct": 25.0})],
                     "count": 44},
            "부산": {"new_total": 9, "high_total": 2, "high_pct": 22.2, "low_total": 1,
                     "avg_jeonse": 62.0, "officetel_total": 3, "officetel_rent_total": 18,
                     "top_movers": [("부산진구", {"new_count": 5, "high_pct": 40.0})], "count": 16},
            "세종": {"new_total": 3, "high_total": 0, "high_pct": 0.0, "low_total": 0,
                     "avg_jeonse": 58.0, "officetel_total": 0, "officetel_rent_total": 0,
                     "top_movers": [], "count": 1},
        },
        "highlights_by_group": {
            "경기": [{"gu": "경기도 수원시 영통구", "apt_name": "광교A", "area_band": 84,
                      "price_10k": 130000, "pct": 3.1, "kind": "HIGH",
                      "ref_price": 126000, "ref_date": "2026-02-01"}],
            "부산": [], "서울": [], "세종": [],
        },
        "seoul": _seoul_block(),
    }


def test_national_header_and_sections_present():
    md = digest.build_digest(_input())
    assert "전국" in md and "60건" in md            # 전국 헤더 총 신규
    assert "## 서울" in md                          # 서울 상세 섹션
    assert "강남구" in md and "은마" in md           # 서울 디테일·하이라이트
    assert "## 경기" in md                          # 경기 권역
    assert "광역시" in md                            # 광역시 섹션 헤더
    assert "부산" in md
    assert "세종" in md


def test_seoul_detail_unchanged_sections():
    md = digest.build_digest(_input())
    assert "구별 온도차" in md
    assert digest._baseline_label() in md           # 신고가 기준 라벨
    assert "전세가율" in md and "오피스텔" in md
    assert "전월세" in md and "월세 17건" in md       # 서울 오피스텔 전월세 (기존 기능)


def test_region_summary_has_top_movers_and_jeonse():
    md = digest.build_digest(_input())
    # 경기 요약: 신규 합계·전세가율·top 이동
    assert "30건" in md
    assert "68.0%" in md                            # 경기 평균 전세가율
    assert "수원시 영통구" in md                      # top mover


def test_empty_national_message():
    d = _input()
    d["national"] = {"new_total": 0, "high_total": 0, "high_pct": 0.0, "low_total": 0}
    d["groups"] = {}
    d["highlights_by_group"] = {}
    d["seoul"]["new_total"] = 0
    md = digest.build_digest(d)
    assert "신규 신고" in md      # 0건 안내


def test_region_degrades_when_group_missing():
    d = _input()
    del d["groups"]["부산"]       # 광역시 데이터 일부 없음 → degrade(해당 시 생략, 크래시 없음)
    md = digest.build_digest(d)
    assert "부산" not in md.split("## 서울")[0]   # 헤더 외엔 부산 미등장
    assert "## 경기" in md                        # 나머지 권역은 정상
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_digest.py -q`
Expected: FAIL — `KeyError`/구조 불일치 (현재 build_digest는 옛 입력 형태)

- [ ] **Step 3: 구현 (digest.py 전체 교체)**

`realestate_bot/digest.py` 전체를 아래로 교체 (헬퍼 `_baseline_label`/`_fmt_won`/`_fmt_pct`는 보존, 본문 구조만 재편):

```python
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
```

> 참고: 세종은 `_render_group(... show_officetel=False)`로 호출돼 오피스텔 줄이 생략된다(스펙 §5 세종 오피스텔 ✗). 광역시 헤더 `## 6대 광역시` 아래 각 시는 `## {city}`로 렌더된다.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_digest.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/digest.py tests/realestate/test_digest.py
git commit -m "Refactor digest 서울 전용 → 전국 헤더+서울 상세+권역 요약"
```

---

## Task 6: run() 전국 배선 (weekly_realestate_bot)

`run()`을 전국으로 배선: `ALL_REGIONS` 수집, 오피스텔은 서울·경기·광역시만, rollup → 서울 스코프 분리 → 새 digest 입력 조립 → 전국 commentary → 제목·라벨(`publish_meta`) → `blog_title` 보존.

**Files:**
- Modify: `weekly_realestate_bot.py` — import 추가, `_collect_extra`, `run()`, `_convert_html`
- Test: `tests/realestate/test_orchestration.py` (추가)

- [ ] **Step 1: 실패 테스트 작성**

`tests/realestate/test_orchestration.py` 끝에 추가 (`_FakeClient`는 같은 파일에 이미 존재 — 4종 fetch 제공):

```python
def test_run_national_scope_publishes(tmp_path, monkeypatch):
    from realestate_bot import config as rconfig
    monkeypatch.setattr(rconfig, "DB_PATH", str(tmp_path / "nat.db"))
    # 전국 범위를 작게 축소: 서울 1 + 경기 1 + 부산 1
    monkeypatch.setattr(rconfig, "SEOUL_GU", {"강남구": "11680"})
    monkeypatch.setattr(rconfig, "ALL_REGIONS",
                        {"강남구": "11680", "경기도 수원시 영통구": "41117", "부산진구": "26230"})
    monkeypatch.setattr(bot, "TELEGRAM_ENABLED", False)
    monkeypatch.setattr(bot.mcp_client, "MCPClient", lambda *a, **k: _FakeClient())
    captured = {}

    def fake_upload(title, content, labels, **kw):
        captured["title"] = title
        captured["labels"] = labels
        return {"success": True, "url": "http://blog/x"}

    monkeypatch.setattr(bot, "convert_md_to_html_via_claude",
                        lambda c: ("<p>html</p>", "전국 신고가 테스트 헤드라인"))
    monkeypatch.setattr(bot.commentary, "make_commentary", lambda s: "")

    b = bot.RealEstateBot(test_mode=False)
    b.blogger = type("B", (), {"upload_post": staticmethod(fake_upload)})()
    r = b.run()

    assert r["success"] is True
    assert r["blog_url"] == "http://blog/x"
    # 제목: 날짜, 주차 + AI 헤드라인
    assert "주차" in captured["title"] and "전국 신고가 테스트 헤드라인" in captured["title"]
    # 라벨 7~9개
    assert 7 <= len(captured["labels"]) <= 9
    assert "전국" in captured["labels"]
```

- [ ] **Step 2: 실패 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_orchestration.py::test_run_national_scope_publishes -q`
Expected: FAIL (현재 run은 SEOUL_GU만·옛 digest 입력·blog_title 미보존·정적 제목)

- [ ] **Step 3: 구현**

3-1. `weekly_realestate_bot.py` import 블록(22~27행 부근)에 추가:

```python
from realestate_bot import config, fetcher, indicators, commentary, digest, mcp_client, publish_meta
from realestate_bot.regions_extra import group_of
```
(기존 `from realestate_bot import config, fetcher, indicators, commentary, digest, mcp_client` 줄을 위 두 줄로 교체.)

3-2. `_collect_extra`(235행 부근) — 오피스텔을 서울·경기·광역시만 적재하도록 교체:

```python
    def _collect_extra(self, client, regions: dict, months: list):
        """전세가율용 아파트 전월세는 전 지역, 오피스텔(매매+전월세)은 서울·경기·광역시만 적재.
        한 종류가 실패해도 나머지·본 디제스트는 진행(degrade)."""
        for gu, code in regions.items():
            grp = group_of(code)
            specs = [(client.fetch_rent, self.store.insert_new_rents, "apartment")]
            if grp != "세종":   # 세종 오피스텔은 표본 적어 제외(스펙 §5)
                specs += [(client.fetch_officetel_trades, self.store.insert_new, "officetel"),
                          (client.fetch_officetel_rent, self.store.insert_new_rents, "officetel")]
            for ym in months:
                for fetch, insert, ptype in specs:
                    try:
                        insert(fetch(code, ym), ptype)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("extra collect skip %s %s %s: %s", ptype, gu, ym, e)
```

3-3. `_convert_html`(142행 부근) — 첫 청크의 `blog_title`을 보존해 반환:

```python
def _convert_html(md: str):
    """h2 청크 분할 후 Claude HTML 변환. 반환 (html, blog_title) — 첫 청크 헤드라인 보존."""
    sections = re.split(r"(?=^## )", md, flags=re.MULTILINE)
    chunks, cur = [], ""
    for s in sections:
        s = s.strip()
        if not s:
            continue
        if len(cur) + len(s) < 5000:
            cur = (cur + "\n\n" + s) if cur else s
        else:
            chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    parts, headline = [], ""
    for i, c in enumerate(chunks, 1):
        try:
            html, title = convert_md_to_html_via_claude(c)
            if i == 1 and title:
                headline = title
            parts.append(html if len(html) >= len(c) * 0.3 else c)
        except Exception as e:  # noqa: BLE001
            logger.warning("html chunk %s failed: %s", i, e)
            parts.append(c)
    return "\n\n".join(parts).strip(), headline
```

3-4. `run()`(181행 부근) 전체를 아래로 교체:

```python
    def run(self) -> dict:
        result = {"success": False, "blog_url": None, "error": None}
        try:
            months = _recent_months(2)
            regions = config.ALL_REGIONS
            gu_to_group = {gu: group_of(code) for gu, code in regions.items()}
            with mcp_client.MCPClient() as client:
                report = build_report(self.store, regions, months,
                                      as_of=date.today().isoformat(),
                                      fetch_region=client.fetch_region)
                self._collect_extra(client, regions, months)
            syn = synthesize(self.store, regions, months[1])
            rollup = indicators.rollup_groups(
                report["per_gu"], syn["jeonse"], syn["officetel"],
                syn["officetel_rent"], gu_to_group)

            # 하이라이트를 권역별로 분류
            hbg = {}
            for h in report["highlights"]:
                hbg.setdefault(gu_to_group.get(h["gu"], "기타"), []).append(h)

            # 서울 상세 스코프 분리
            seoul_gu = {gu: g for gu, g in report["per_gu"].items()
                        if gu_to_group.get(gu) == "서울"}
            seoul_block = self._seoul_block(seoul_gu, hbg.get("서울", []), syn, rollup.get("서울"))

            national = {"new_total": report["seoul"]["new_total"],
                        "high_total": report["seoul"]["high_total"],
                        "high_pct": report["seoul"]["high_pct"],
                        "low_total": report["seoul"]["low_total"]}
            d = {"week_label": report["week_label"], "national": national,
                 "groups": rollup, "highlights_by_group": hbg, "seoul": seoul_block}

            comment = commentary.make_commentary({"national": national, "groups": {
                g: {"new_total": s["new_total"], "high_pct": s["high_pct"],
                    "avg_jeonse": s["avg_jeonse"]} for g, s in rollup.items()}})
            md = digest.build_digest(d)
            if comment:
                md += "\n\n## 시황 해석\n\n" + comment

            if national["new_total"] == 0:
                if self.telegram:
                    self.telegram.send_message("🏠 이번 주 전국 신규 신고 없음", parse_mode="HTML")
                result["success"] = True
                return result

            # 가장 뜨거운 구(전국 top mover) → 핫스팟 라벨
            hottest = None
            ranked = indicators.rank_regions(report["per_gu"])
            if ranked:
                hottest = ranked[0][0]
            if not self.test_mode:
                html, headline = _convert_html(md)
                title = publish_meta.build_title(date.today(), headline)
                labels = publish_meta.build_labels(rollup, hottest_gu=hottest)
                up = self.blogger.upload_post(title=title, content=html, labels=labels,
                                              is_draft=False, is_markdown=False)
                if not up["success"]:
                    raise RuntimeError(f"upload failed: {up.get('message')}")
                result["blog_url"] = up.get("url")
            result["success"] = True

            if self.telegram:
                link = f"<a href='{result['blog_url']}'>블로그</a>" if result["blog_url"] else "테스트"
                self.telegram.send_message(
                    f"🏠 <b>전국 아파트 시장 흐름</b>\n신규 {national['new_total']} · "
                    f"신고가 {national['high_total']}({national['high_pct']:.0f}%)\n{link}",
                    parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            logger.error("realestate bot error: %s", e)
            result["error"] = str(e)
            if self.telegram:
                try:
                    self.telegram.send_message(f"❌ 부동산 봇 실패: {e}", parse_mode="HTML")
                except Exception:
                    pass
        return result

    def _seoul_block(self, seoul_gu: dict, seoul_highlights: list, syn: dict,
                     seoul_rollup: dict) -> dict:
        """서울 상세 렌더용 입력. 전세가율·오피스텔은 서울 구만 필터."""
        from realestate_bot import config as _cfg
        seoul_names = set(_cfg.SEOUL_GU.keys())
        jeonse = {gu: r for gu, r in syn["jeonse"].items() if gu in seoul_names}
        rated = [r for r in jeonse.values() if r is not None]
        officetel = {gu: c for gu, c in syn["officetel"].items() if gu in seoul_names}
        officetel_rent = {gu: c for gu, c in syn["officetel_rent"].items() if gu in seoul_names}
        r = seoul_rollup or {"new_total": 0, "high_total": 0, "low_total": 0, "high_pct": 0.0}
        return {
            "per_gu": seoul_gu, "highlights": seoul_highlights,
            "jeonse": jeonse,
            "jeonse_seoul": round(sum(rated) / len(rated), 1) if rated else None,
            "officetel": officetel, "officetel_total": sum(officetel.values()),
            "officetel_rent": officetel_rent,
            "officetel_rent_total": sum(officetel_rent.values()),
            "officetel_rent_jeonse": syn.get("officetel_rent_jeonse", 0),
            "officetel_rent_wolse": syn.get("officetel_rent_wolse", 0),
            "new_total": r["new_total"], "high_total": r["high_total"],
            "low_total": r["low_total"], "high_pct": r["high_pct"],
        }
```

> 참고: `synthesize`는 `regions`를 받아 구별로 계산하므로 `ALL_REGIONS`로 호출하면 전국 jeonse/officetel을 그대로 산출한다(별도 수정 불필요). `officetel_rent_jeonse/_wolse`는 전국 합계라 서울 블록엔 근사로 들어가지만 표시엔 비치명적(서울 전월세 구성 라인). 정밀 서울 분리는 향후 과제.

- [ ] **Step 4: 통과 확인**

Run: `.venv/bin/python -m pytest tests/realestate/test_orchestration.py -q`
Expected: PASS (기존 + 신규 통합 테스트)

- [ ] **Step 5: 커밋**

```bash
git add weekly_realestate_bot.py tests/realestate/test_orchestration.py
git commit -m "Wire run() 전국 범위: ALL_REGIONS·rollup·주차 제목·동적 라벨"
```

---

## Task 7: 전체 회귀 + 라이브 스모크

**Files:** (없음 — 검증만)

- [ ] **Step 1: 전체 realestate 스위트**

Run: `.venv/bin/python -m pytest tests/realestate/ -q`
Expected: PASS (전부 green, 회귀 0)

- [ ] **Step 2: 라이브 스모크 (test 모드, 발행 스킵)**

Run: `.venv/bin/python weekly_realestate_bot.py --once --test`
Expected: 전국 fetch(~950회) 후 `Result: OK` 출력, 예외/Traceback 없음. (test 모드라 Blogger·Claude HTML 스킵, diff 0건이면 "신규 없음"도 정상)

- [ ] **Step 3: digest 육안 점검**

Run:
```bash
.venv/bin/python -c "
import sys; sys.path.insert(0,'.')
from realestate_bot import digest
# Task5 테스트 _input과 동일 샘플로 렌더 확인
"
```
실제로는 Task 5 테스트 출력으로 충분 — 전국 헤더·서울 상세·경기·광역시·세종 섹션이 순서대로 나오는지 확인.

- [ ] **Step 4: 커밋 (필요 시 정리 커밋)**

```bash
git add -A
git commit -m "Verify 전국 디제스트 회귀·스모크 통과" --allow-empty
```

---

## Self-Review 체크 결과

- **Spec 커버리지:** §3 권역(Task1) / §4·§5 구조·데이터깊이(Task5 digest + Task6 _collect_extra) / §6 모듈(Task1-6) / §11 제목·라벨(Task3) / 시황 전국화(Task4) / 성능(Task7 스모크) — 전부 태스크 매핑됨.
- **Placeholder:** 없음 (모든 step에 실제 코드·명령·기대출력).
- **Type 일관성:** `rollup_groups` 반환 키(new_total/high_total/high_pct/avg_jeonse/officetel_total/officetel_rent_total/top_movers)가 digest `_render_group`·publish_meta `build_labels`·run() commentary 입력에서 동일하게 사용됨. `group_of`/`gu_to_group` 명칭 일관. `_convert_html` 반환이 `(html, headline)` 튜플로 바뀐 점은 run()에서만 호출되므로 영향 국소.

## 리스크 / 비고

- `build_report`의 `"seoul"` 키는 이제 **전국 합계**를 담는다(명칭 미스노머지만 기존 함수 시그니처 보존). run()에서 `national`로 매핑해 사용.
- 최초 전국 발행도 0신규 가능 → 검증은 직전과 동일하게 "최근 완료월 델타 리셋"(서울 아파트 5월 삭제→재실행) 방식 재사용.
- 글 길이 증가로 Claude HTML 변환 청크↑·시간↑ — 스모크 후 실제 발행 시간 모니터링.
