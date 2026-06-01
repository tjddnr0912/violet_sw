# 주간 서울 아파트 시장 흐름 다이제스트 봇 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매주 토요일 08:00 서울 25개 구 아파트 실거래를 조회해 시장 흐름 지표(거래량·믹스보정 중앙가·신고가/신저점 breadth·세그먼트·구간 온도차)를 코드로 계산하고 AI 해석 시황을 붙여 Telegram·Blogger에 발행하는 봇.

**Architecture:** `claude -p --mcp-config`로 kr-realestate MCP를 *운반책*으로만 써서 raw JSON을 받고(검증 완료), 모든 숫자 계산은 결정적 파이썬(store/detector/indicators)이 수행, AI는 해석 시황만 작성. SQLite 단일 `transactions` 테이블이 diff(신규 신고)·baseline(신고가 판정)·집계를 모두 도출. 기존 `006_auto_bot` 봇 컨벤션(`BuffettBot` 클래스, `shared/` 재사용)을 따른다.

**Tech Stack:** Python 3, SQLite(stdlib `sqlite3`), pytest, `schedule`, 기존 `shared/`(blogger_uploader/telegram_notifier/claude_html_converter/gemini_cli), `claude` CLI + kr-realestate MCP.

**설계 문서(spec):** `006_auto_bot/docs/superpowers/specs/2026-06-02-realestate-weekly-digest-bot-design.md`

---

## 사전 지식 (도메인/코드베이스 무지 가정)

- **작업 디렉토리:** 모든 경로는 `006_auto_bot/001_code/` 기준. 명령은 이 디렉토리에서 실행.
- **가상환경:** `.venv`가 이미 있다. 테스트는 `.venv/bin/pytest`, 실행은 `.venv/bin/python` 또는 `source .venv/bin/activate` 후 `python`.
- **MCP 운반책 검증 결과(중요):** `claude -p --mcp-config <루트 .mcp.json> --dangerously-skip-permissions -` 형태로 호출하면 kr-realestate MCP가 로드되고 raw JSON을 충실히 반환한다. **함정:** `--mcp-config <file>` 는 뒤따르는 토큰을 설정파일로 greedy하게 먹으므로 `--mcp-config`의 값 바로 뒤에는 반드시 다른 플래그(`--dangerously-skip-permissions`)를 두고 stdin 마커 `-`는 맨 끝에 둔다.
- **데이터 단위:** MOLIT 실거래가는 (구 5자리코드 + 월 YYYYMM) 단위. 신고일 필드 없음 → "새 신고"는 이전 조회와의 차집합으로만 잡는다. 가격 단위는 만원(`price_10k`).
- **`get_apartment_trades` 반환 필드:** `total_count`, `items[]`(apt_name, dong, area_sqm, floor, price_10k, trade_date('YYYY-MM-DD'), build_year, deal_type), `summary`.
- **커밋 컨벤션(repo 규칙):** `Add/Fix/Update/Refactor <대상>` 접두사 사용(이 repo는 `feat:` 안 씀).

## 공유 타입/인터페이스 (태스크 간 일관성 — 변경 금지)

```python
# detector.Verdict (dataclass)
#   kind: str        # 'HIGH' | 'LOW' | 'NEW' | 'NORMAL'
#   pct: float|None  # 경신율 % (HIGH/LOW일 때만)
#   ref_price: int|None   # 비교된 직전 max/min (만원)
#   ref_date: str|None    # 그 가격의 계약일

# record(dict) 표준 키: region_code, apt_name, dong, area_sqm, floor,
#   price_10k, trade_date, build_year, deal_type   (area_band/record_key는 store가 부여)

# store.RealEstateStore 메서드:
#   insert_new(records: list[dict]) -> list[dict]      # 실제 삽입된(=신규) 레코드
#   baseline_snapshot(region_code, as_of='now') -> dict[(apt_name:str, area_band:int), dict]
#       value = {'max':int,'max_date':str,'min':int,'min_date':str,'count':int}  # 최근 36개월
#   monthly_volume(region_code, months:int) -> list[(ym:str, count:int)]
#   band_medians(region_code, year_month) -> dict[area_band:int, dict]  # {'median':int,'count':int}

# indicators 순수함수:
#   breadth(verdicts) -> {'high','low','new','normal','total','high_pct','low_pct'}
#   mix_adjusted_change(cur:dict[int,int], prev:dict[int,int], cur_counts:dict[int,int]) -> float|None
#   segment_flags(records) -> {'direct_deal_pct','new_build_pct','direct_deal_spike'}
#   rank_regions(per_gu: dict[str,dict]) -> list[(gu, dict)]  # 뜨거운 순
```

## 파일 구조

| 파일 | 책임 |
|------|------|
| `realestate_bot/__init__.py` | 패키지 마커 |
| `realestate_bot/config.py` | 서울 25구 코드, baseline 윈도우, num_of_rows, 평형/신축 기준, 경로, 블로그 ID |
| `realestate_bot/store.py` | SQLite `transactions` — diff·baseline·거래량·중앙가 |
| `realestate_bot/detector.py` | `classify(record, group_baseline) -> Verdict` (순수) |
| `realestate_bot/indicators.py` | breadth·믹스보정·세그먼트·순위 (순수) |
| `realestate_bot/fetcher.py` | `fetch_region(code, ym)` — claude -p + MCP 운반·검증·재시도 |
| `realestate_bot/digest.py` | `build_digest(...)` — 깔때기 markdown |
| `realestate_bot/commentary.py` | `make_commentary(summary)` — gemini 시황(실패 시 "") |
| `weekly_realestate_bot.py` | `RealEstateBot` 오케스트레이션 + `--once/--test/--backfill` |
| `conftest.py` (001_code) | 테스트 sys.path 보장 |
| `tests/realestate/test_*.py` | 단위/통합 테스트 |
| `investment_bot.py` (수정) | 토요일 08:00 잡 등록 |

---

## Task 1: 패키지 스켈레톤 + config + conftest

**Files:**
- Create: `realestate_bot/__init__.py`
- Create: `realestate_bot/config.py`
- Create: `conftest.py`
- Create: `tests/realestate/__init__.py`
- Test: `tests/realestate/test_config.py`

- [ ] **Step 1: conftest로 sys.path 보장**

Create `conftest.py` (001_code 루트):
```python
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

- [ ] **Step 2: 패키지 마커 + 테스트 디렉토리**

Create `realestate_bot/__init__.py` (빈 파일):
```python
```
Create `tests/realestate/__init__.py` (빈 파일):
```python
```

- [ ] **Step 3: config.py 작성**

Create `realestate_bot/config.py`:
```python
"""주간 서울 아파트 시장 흐름 다이제스트 봇 설정."""
import os

# 서울 25개 자치구 — 법정동 시군구 5자리 코드 (MOLIT region_code)
# 마포(11440)는 get_region_code로 검증됨. 나머지는 표준 자치구 코드.
SEOUL_GU = {
    "종로구": "11110", "중구": "11140", "용산구": "11170", "성동구": "11200",
    "광진구": "11215", "동대문구": "11230", "중랑구": "11260", "성북구": "11290",
    "강북구": "11305", "도봉구": "11320", "노원구": "11350", "은평구": "11380",
    "서대문구": "11410", "마포구": "11440", "양천구": "11470", "강서구": "11500",
    "구로구": "11530", "금천구": "11545", "영등포구": "11560", "동작구": "11590",
    "관악구": "11620", "서초구": "11650", "강남구": "11680", "송파구": "11710",
    "강동구": "11740",
}

BASELINE_MONTHS = 36          # 신고가 baseline 윈도우 → "최근 3년"
NUM_OF_ROWS = 1000            # 월 거래 누락 방지
NEW_BUILD_MAX_AGE = 5         # build_year 기준 신축 (현재연도 - build_year <= 5)
DIRECT_DEAL_SPIKE_PCT = 30.0  # 직거래 비중 이 이상이면 왜곡 주의 플래그
VOLUME_TREND_MONTHS = 12      # 월별 거래량 시계열 길이

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "realestate", "molit.db")

# 루트 .mcp.json (001_code 기준 ../../../.mcp.json). env로 override 가능.
MCP_CONFIG_PATH = os.getenv(
    "REALESTATE_MCP_CONFIG",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".mcp.json")),
)

# 출력
REALESTATE_BLOGGER_BLOG_ID = os.getenv("REALESTATE_BLOGGER_BLOG_ID", "9115231004981625966")  # OgusInvest
SCHEDULE_DAY = "saturday"
SCHEDULE_TIME = "08:00"
```

- [ ] **Step 4: 실패하는 테스트 작성**

Create `tests/realestate/test_config.py`:
```python
from realestate_bot import config


def test_seoul_has_25_gu():
    assert len(config.SEOUL_GU) == 25


def test_all_codes_are_5_digit():
    for gu, code in config.SEOUL_GU.items():
        assert len(code) == 5 and code.isdigit(), f"{gu}={code}"


def test_mapo_code_matches_verified_value():
    # get_region_code('마포구') == '11440' (spike에서 검증)
    assert config.SEOUL_GU["마포구"] == "11440"


def test_mcp_config_path_exists():
    import os
    assert os.path.exists(config.MCP_CONFIG_PATH), config.MCP_CONFIG_PATH
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `.venv/bin/pytest tests/realestate/test_config.py -v`
Expected: 4 passed. `test_mcp_config_path_exists`가 실패하면 `MCP_CONFIG_PATH` 기본값의 `..` 개수를 조정(루트 `.mcp.json` 절대경로가 나오도록).

- [ ] **Step 6: region_code 실측 검증 (선택적 1회, MCP 필요)**

이 세션/환경에 kr-realestate MCP가 있으면 강남(11680)·송파(11710) 등 2~3개를 `get_region_code`로 교차 확인. 불일치 시 `SEOUL_GU` 수정. (CI 불가 환경이면 skip — 코드는 표준값)

- [ ] **Step 7: 커밋**

```bash
git add conftest.py realestate_bot/__init__.py realestate_bot/config.py tests/realestate/
git commit -m "Add realestate_bot 패키지 스켈레톤 + 서울 25구 config"
```

---

## Task 2: store.py — SQLite 적재·diff·baseline·집계

**Files:**
- Create: `realestate_bot/store.py`
- Test: `tests/realestate/test_store.py`

- [ ] **Step 1: 실패하는 테스트 작성 (diff 멱등성 + baseline)**

Create `tests/realestate/test_store.py`:
```python
import pytest
from realestate_bot.store import RealEstateStore


def _rec(apt="A아파트", area=84.9, floor=10, price=100000, date="2026-05-10",
         region="11440", dong="합정동", build=2015, deal="중개거래"):
    return {"region_code": region, "apt_name": apt, "dong": dong, "area_sqm": area,
            "floor": floor, "price_10k": price, "trade_date": date,
            "build_year": build, "deal_type": deal}


@pytest.fixture
def store(tmp_path):
    return RealEstateStore(str(tmp_path / "t.db"))


def test_insert_new_returns_only_new(store):
    first = store.insert_new([_rec(price=100000), _rec(price=110000, floor=11)])
    assert len(first) == 2
    # 같은 레코드 재삽입 → 신규 0
    again = store.insert_new([_rec(price=100000), _rec(price=110000, floor=11)])
    assert again == []
    # 하나만 새 레코드
    third = store.insert_new([_rec(price=100000), _rec(price=120000, floor=12)])
    assert len(third) == 1 and third[0]["price_10k"] == 120000


def test_area_band_is_rounded(store):
    store.insert_new([_rec(area=84.96), _rec(area=84.12, floor=11)])
    snap = store.baseline_snapshot("11440")
    assert (("A아파트", 85) in snap) and (("A아파트", 84) in snap)


def test_baseline_snapshot_max_min(store):
    store.insert_new([
        _rec(price=100000, floor=1, date="2026-01-05"),
        _rec(price=130000, floor=2, date="2026-02-05"),
        _rec(price=90000, floor=3, date="2026-03-05"),
    ])
    snap = store.baseline_snapshot("11440")
    g = snap[("A아파트", 85)]
    assert g["max"] == 130000 and g["max_date"] == "2026-02-05"
    assert g["min"] == 90000 and g["min_date"] == "2026-03-05"
    assert g["count"] == 3


def test_baseline_excludes_older_than_36_months(store):
    store.insert_new([
        _rec(price=200000, floor=1, date="2000-01-05"),  # 아주 오래된 거래
        _rec(price=100000, floor=2, date="2026-05-05"),
    ])
    snap = store.baseline_snapshot("11440", as_of="2026-06-01")
    g = snap[("A아파트", 85)]
    # 2000년 거래는 36개월 윈도우 밖 → max는 100000
    assert g["max"] == 100000 and g["count"] == 1


def test_monthly_volume(store):
    store.insert_new([
        _rec(date="2026-04-10", floor=1), _rec(date="2026-04-20", floor=2),
        _rec(date="2026-05-10", floor=3),
    ])
    vol = dict(store.monthly_volume("11440", months=12))
    assert vol.get("202604") == 2 and vol.get("202605") == 1


def test_band_medians(store):
    store.insert_new([
        _rec(area=84.9, price=100000, floor=1, date="2026-05-01"),
        _rec(area=84.9, price=120000, floor=2, date="2026-05-02"),
        _rec(area=59.9, price=80000, floor=3, date="2026-05-03"),
    ])
    bm = store.band_medians("11440", "202605")
    assert bm[85]["median"] == 110000 and bm[85]["count"] == 2
    assert bm[60]["median"] == 80000
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `.venv/bin/pytest tests/realestate/test_store.py -v`
Expected: FAIL (`ModuleNotFoundError: realestate_bot.store`).

- [ ] **Step 3: store.py 구현**

Create `realestate_bot/store.py`:
```python
"""SQLite 상태 저장소 — 적재·diff·baseline·집계."""
import os
import sqlite3
import statistics
from datetime import date as _date

from realestate_bot import config


def _record_key(r: dict) -> str:
    return "|".join([
        str(r["region_code"]), str(r["apt_name"]), str(r.get("dong", "")),
        f'{float(r["area_sqm"]):.4f}', str(r["floor"]),
        str(r["trade_date"]), str(r["price_10k"]),
    ])


def _area_band(area_sqm) -> int:
    return int(round(float(area_sqm)))


def _ym(trade_date: str) -> str:
    # 'YYYY-MM-DD' -> 'YYYYMM'
    return trade_date[:7].replace("-", "")


class RealEstateStore:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transactions (
              record_key TEXT PRIMARY KEY,
              region_code TEXT, apt_name TEXT, dong TEXT,
              area_sqm REAL, area_band INTEGER,
              floor INTEGER, price_10k INTEGER,
              trade_date TEXT, build_year INTEGER, deal_type TEXT,
              first_seen_date TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_group
              ON transactions(region_code, apt_name, area_band, trade_date);
            CREATE INDEX IF NOT EXISTS idx_vol
              ON transactions(region_code, trade_date);
            """
        )
        self.conn.commit()

    def insert_new(self, records: list) -> list:
        """INSERT OR IGNORE 후 실제 삽입된(신규) 레코드만 반환."""
        today = _date.today().isoformat()
        new_records = []
        cur = self.conn.cursor()
        for r in records:
            key = _record_key(r)
            band = _area_band(r["area_sqm"])
            cur.execute(
                """INSERT OR IGNORE INTO transactions
                   (record_key, region_code, apt_name, dong, area_sqm, area_band,
                    floor, price_10k, trade_date, build_year, deal_type, first_seen_date)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (key, r["region_code"], r["apt_name"], r.get("dong", ""),
                 float(r["area_sqm"]), band, int(r["floor"]), int(r["price_10k"]),
                 r["trade_date"], r.get("build_year"), r.get("deal_type"), today),
            )
            if cur.rowcount == 1:
                out = dict(r)
                out["area_band"] = band
                new_records.append(out)
        self.conn.commit()
        return new_records

    def _cutoff(self, as_of: str) -> str:
        if as_of == "now":
            ref = _date.today()
        else:
            ref = _date.fromisoformat(as_of)
        # 36개월 전 (대략: 연/월 빼기)
        y, m = ref.year, ref.month - config.BASELINE_MONTHS
        while m <= 0:
            m += 12
            y -= 1
        return f"{y:04d}-{m:02d}-01"

    def baseline_snapshot(self, region_code: str, as_of: str = "now") -> dict:
        cutoff = self._cutoff(as_of)
        rows = self.conn.execute(
            """SELECT apt_name, area_band,
                      MAX(price_10k) AS mx, MIN(price_10k) AS mn, COUNT(*) AS cnt
               FROM transactions
               WHERE region_code=? AND trade_date>=?
               GROUP BY apt_name, area_band""",
            (region_code, cutoff),
        ).fetchall()
        snap = {}
        for row in rows:
            key = (row["apt_name"], row["area_band"])
            mx_date = self.conn.execute(
                """SELECT trade_date FROM transactions
                   WHERE region_code=? AND apt_name=? AND area_band=? AND price_10k=?
                   ORDER BY trade_date DESC LIMIT 1""",
                (region_code, row["apt_name"], row["area_band"], row["mx"]),
            ).fetchone()["trade_date"]
            mn_date = self.conn.execute(
                """SELECT trade_date FROM transactions
                   WHERE region_code=? AND apt_name=? AND area_band=? AND price_10k=?
                   ORDER BY trade_date DESC LIMIT 1""",
                (region_code, row["apt_name"], row["area_band"], row["mn"]),
            ).fetchone()["trade_date"]
            snap[key] = {"max": row["mx"], "max_date": mx_date,
                         "min": row["mn"], "min_date": mn_date, "count": row["cnt"]}
        return snap

    def monthly_volume(self, region_code: str, months: int = 12) -> list:
        rows = self.conn.execute(
            """SELECT substr(replace(trade_date,'-',''),1,6) AS ym, COUNT(*) AS cnt
               FROM transactions WHERE region_code=?
               GROUP BY ym ORDER BY ym DESC LIMIT ?""",
            (region_code, months),
        ).fetchall()
        return [(row["ym"], row["cnt"]) for row in reversed(rows)]

    def band_medians(self, region_code: str, year_month: str) -> dict:
        like = f"{year_month[:4]}-{year_month[4:6]}-%"
        rows = self.conn.execute(
            """SELECT area_band, price_10k FROM transactions
               WHERE region_code=? AND trade_date LIKE ?""",
            (region_code, like),
        ).fetchall()
        by_band = {}
        for row in rows:
            by_band.setdefault(row["area_band"], []).append(row["price_10k"])
        return {b: {"median": int(statistics.median(p)), "count": len(p)}
                for b, p in by_band.items()}
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `.venv/bin/pytest tests/realestate/test_store.py -v`
Expected: 6 passed.

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/store.py tests/realestate/test_store.py
git commit -m "Add realestate_bot SQLite store (diff/baseline/집계) + tests"
```

---

## Task 3: detector.py — 신고가/신저점 판정

**Files:**
- Create: `realestate_bot/detector.py`
- Test: `tests/realestate/test_detector.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/realestate/test_detector.py`:
```python
from realestate_bot.detector import classify, Verdict


def test_new_high():
    base = {"max": 100000, "max_date": "2025-01-01", "min": 80000,
            "min_date": "2024-01-01", "count": 5}
    v = classify({"price_10k": 110000}, base)
    assert v.kind == "HIGH"
    assert round(v.pct, 1) == 10.0
    assert v.ref_price == 100000 and v.ref_date == "2025-01-01"


def test_new_low():
    base = {"max": 100000, "max_date": "2025-01-01", "min": 80000,
            "min_date": "2024-01-01", "count": 5}
    v = classify({"price_10k": 70000}, base)
    assert v.kind == "LOW"
    assert round(v.pct, 1) == -12.5
    assert v.ref_price == 80000 and v.ref_date == "2024-01-01"


def test_no_history_is_new():
    v = classify({"price_10k": 90000}, None)
    assert v.kind == "NEW" and v.pct is None


def test_within_range_is_normal():
    base = {"max": 100000, "max_date": "x", "min": 80000, "min_date": "y", "count": 5}
    v = classify({"price_10k": 90000}, base)
    assert v.kind == "NORMAL"


def test_tie_with_max_is_normal_not_high():
    # 동일가는 경신이 아님
    base = {"max": 100000, "max_date": "x", "min": 80000, "min_date": "y", "count": 5}
    v = classify({"price_10k": 100000}, base)
    assert v.kind == "NORMAL"
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `.venv/bin/pytest tests/realestate/test_detector.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: detector.py 구현**

Create `realestate_bot/detector.py`:
```python
"""신고가/신저점 판정 — 순수함수."""
from dataclasses import dataclass


@dataclass
class Verdict:
    kind: str            # 'HIGH' | 'LOW' | 'NEW' | 'NORMAL'
    pct: float | None = None
    ref_price: int | None = None
    ref_date: str | None = None


def classify(record: dict, group_baseline: dict | None) -> Verdict:
    """record를 (단지,평형밴드) 36개월 baseline과 비교.

    group_baseline: {'max','max_date','min','min_date','count'} 또는 None(이력 없음).
    """
    price = int(record["price_10k"])
    if not group_baseline or group_baseline.get("count", 0) == 0:
        return Verdict(kind="NEW")

    mx = group_baseline["max"]
    mn = group_baseline["min"]
    if price > mx:
        return Verdict(kind="HIGH", pct=(price / mx - 1) * 100,
                       ref_price=mx, ref_date=group_baseline["max_date"])
    if price < mn:
        return Verdict(kind="LOW", pct=(price / mn - 1) * 100,
                       ref_price=mn, ref_date=group_baseline["min_date"])
    return Verdict(kind="NORMAL")
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `.venv/bin/pytest tests/realestate/test_detector.py -v`
Expected: 5 passed.

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/detector.py tests/realestate/test_detector.py
git commit -m "Add realestate_bot 신고가/신저점 detector + tests"
```

---

## Task 4: indicators.py — 시장 흐름 지표 집계

**Files:**
- Create: `realestate_bot/indicators.py`
- Test: `tests/realestate/test_indicators.py`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/realestate/test_indicators.py`:
```python
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
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `.venv/bin/pytest tests/realestate/test_indicators.py -v`
Expected: FAIL.

- [ ] **Step 3: indicators.py 구현**

Create `realestate_bot/indicators.py`:
```python
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


def rank_regions(per_gu: dict) -> list:
    """뜨거운 순: (신고가 비중, 신규건수) 내림차순."""
    return sorted(
        per_gu.items(),
        key=lambda kv: (kv[1]["breadth"]["high_pct"], kv[1]["new_count"]),
        reverse=True,
    )
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `.venv/bin/pytest tests/realestate/test_indicators.py -v`
Expected: 6 passed.

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/indicators.py tests/realestate/test_indicators.py
git commit -m "Add realestate_bot 시장흐름 indicators (breadth/믹스보정/세그먼트/순위) + tests"
```

---

## Task 5: fetcher.py — claude -p + MCP 운반책

**Files:**
- Create: `realestate_bot/fetcher.py`
- Test: `tests/realestate/test_fetcher.py`

- [ ] **Step 1: 실패하는 테스트 작성 (subprocess mock)**

Create `tests/realestate/test_fetcher.py`:
```python
import json
import pytest
from unittest import mock
from realestate_bot import fetcher


def _claude_output(items):
    payload = {"total_count": len(items), "items": items, "summary": {}}
    return "<<<JSON>>>\n" + json.dumps(payload, ensure_ascii=False) + "\n<<<END>>>\n"


def _fake_run(output, returncode=0):
    m = mock.Mock()
    m.stdout = output
    m.stderr = ""
    m.returncode = returncode
    return m


def test_parse_valid_output_returns_items():
    items = [{"apt_name": "A", "area_sqm": 84.9, "floor": 5,
              "price_10k": 100000, "trade_date": "2026-05-10",
              "build_year": 2015, "deal_type": "중개거래", "dong": "합정동"}]
    with mock.patch("subprocess.run", return_value=_fake_run(_claude_output(items))):
        out = fetcher.fetch_region("11440", "202605")
    assert len(out) == 1
    assert out[0]["region_code"] == "11440" and out[0]["price_10k"] == 100000


def test_retry_then_succeed_on_garbage_first():
    items = [{"apt_name": "A", "area_sqm": 84.9, "floor": 5, "price_10k": 100000,
              "trade_date": "2026-05-10", "build_year": 2015, "deal_type": "중개거래"}]
    seq = [_fake_run("no json here"), _fake_run(_claude_output(items))]
    with mock.patch("subprocess.run", side_effect=seq), \
         mock.patch("time.sleep"):
        out = fetcher.fetch_region("11440", "202605", max_retries=2)
    assert len(out) == 1


def test_all_retries_fail_raises():
    with mock.patch("subprocess.run", return_value=_fake_run("garbage")), \
         mock.patch("time.sleep"):
        with pytest.raises(RuntimeError):
            fetcher.fetch_region("11440", "202605", max_retries=2)


def test_missing_required_field_is_rejected():
    bad = [{"apt_name": "A", "floor": 5}]  # area_sqm/price_10k/trade_date 없음
    with mock.patch("subprocess.run", return_value=_fake_run(_claude_output(bad))), \
         mock.patch("time.sleep"):
        with pytest.raises(RuntimeError):
            fetcher.fetch_region("11440", "202605", max_retries=1)
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `.venv/bin/pytest tests/realestate/test_fetcher.py -v`
Expected: FAIL.

- [ ] **Step 3: fetcher.py 구현**

Create `realestate_bot/fetcher.py`:
```python
"""claude -p + kr-realestate MCP 운반책: (region, ym) -> raw items[]."""
import json
import re
import subprocess
import time
import logging

from realestate_bot import config

logger = logging.getLogger(__name__)

CLAUDE_TIMEOUT = 300
RETRY_DELAY = 15
REQUIRED_FIELDS = ("apt_name", "area_sqm", "floor", "price_10k", "trade_date")
_SENTINEL = re.compile(r"<<<JSON>>>\s*(.*?)\s*<<<END>>>", re.DOTALL)


def _build_prompt(region_code: str, year_month: str) -> str:
    return (
        "You have access to the kr-realestate MCP server tools. "
        f"Call the get_apartment_trades tool exactly once with arguments: "
        f"region_code={region_code}, year_month={year_month}, num_of_rows={config.NUM_OF_ROWS}. "
        "Then output ONLY the raw JSON object the tool returned, verbatim, "
        "between a line containing <<<JSON>>> and a line containing <<<END>>>. "
        "Do not summarize, reformat, compute, or add commentary."
    )


def _invoke_claude(prompt: str) -> str:
    # 함정: --mcp-config 값 뒤에 반드시 플래그를 두고 stdin 마커 '-'는 맨 끝.
    cmd = ["claude", "-p", "--mcp-config", config.MCP_CONFIG_PATH,
           "--dangerously-skip-permissions", "-"]
    result = subprocess.run(cmd, input=prompt, capture_output=True,
                            text=True, timeout=CLAUDE_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(f"claude -p failed: {(result.stderr or '')[:300]}")
    return result.stdout or ""


def _parse(output: str, region_code: str) -> list:
    m = _SENTINEL.search(output)
    if not m:
        raise ValueError("sentinel not found")
    payload = json.loads(m.group(1))
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("items missing")
    total = payload.get("total_count")
    if isinstance(total, int) and total > len(items):
        logger.warning("incomplete: %s items < total_count %s (region %s)",
                       len(items), total, region_code)
    out = []
    for it in items:
        for f in REQUIRED_FIELDS:
            if f not in it:
                raise ValueError(f"missing field {f}")
        rec = dict(it)
        rec["region_code"] = region_code
        out.append(rec)
    return out


def fetch_region(region_code: str, year_month: str, max_retries: int = 3) -> list:
    prompt = _build_prompt(region_code, year_month)
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            output = _invoke_claude(prompt)
            return _parse(output, region_code)
        except Exception as e:  # noqa: BLE001
            last_err = e
            logger.warning("fetch %s %s attempt %s/%s failed: %s",
                           region_code, year_month, attempt, max_retries, e)
            if attempt < max_retries:
                time.sleep(RETRY_DELAY)
    raise RuntimeError(f"fetch_region failed {region_code} {year_month}: {last_err}")
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `.venv/bin/pytest tests/realestate/test_fetcher.py -v`
Expected: 4 passed.

- [ ] **Step 5: 실거래 1회 라이브 검증 (MCP 필요, 선택적)**

MCP가 있는 환경이면 1회 라이브 호출로 회귀 방지:
```bash
.venv/bin/python -c "from realestate_bot import fetcher; r=fetcher.fetch_region('11440','202605'); print(len(r), r[0]['apt_name'])"
```
Expected: 양수 건수 + 단지명 출력. (CI 불가 환경이면 skip)

- [ ] **Step 6: 커밋**

```bash
git add realestate_bot/fetcher.py tests/realestate/test_fetcher.py
git commit -m "Add realestate_bot fetcher (claude -p + MCP 운반책) + tests"
```

---

## Task 6: digest.py — 깔때기 리포트(markdown)

**Files:**
- Create: `realestate_bot/digest.py`
- Test: `tests/realestate/test_digest.py`

리포트 입력 구조(오케스트레이터가 구성, 일관성 유지):
```python
# digest_input = {
#   "week_label": "2026-06-01 기준 주간",
#   "seoul": {"new_total": int, "high_total": int, "low_total": int, "high_pct": float},
#   "per_gu": { "강남구": {"new_count","breadth":{...},"mix_change":float|None,
#                          "segment":{...}}, ... },   # rank_regions 입력과 동일 구조
#   "highlights": [ {"gu","apt_name","area_band","price_10k","pct","kind","ref_price","ref_date"} ],
# }
```

- [ ] **Step 1: 실패하는 테스트 작성**

Create `tests/realestate/test_digest.py`:
```python
from realestate_bot import digest


def _input():
    return {
        "week_label": "2026-06-01 기준 주간",
        "seoul": {"new_total": 18, "high_total": 5, "low_total": 1, "high_pct": 27.8},
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
    }


def test_markdown_has_sections_and_ranking_order():
    md = digest.build_digest(_input())
    assert "## " in md  # 섹션 헤더 존재
    # 강남구가 도봉구보다 순위표에서 먼저
    assert md.index("강남구") < md.index("도봉구")
    # 신고가 하이라이트 단지명·라벨
    assert "은마" in md and "최근 3년" in md
    # 미확정 caveat
    assert "확정" in md


def test_empty_week_message():
    md = digest.build_digest({
        "week_label": "x", "seoul": {"new_total": 0, "high_total": 0,
                                     "low_total": 0, "high_pct": 0.0},
        "per_gu": {}, "highlights": []})
    assert "신규 신고" in md
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `.venv/bin/pytest tests/realestate/test_digest.py -v`
Expected: FAIL.

- [ ] **Step 3: digest.py 구현**

Create `realestate_bot/digest.py`:
```python
"""주간 다이제스트 markdown 빌드 — 요약→하이라이트→상세 깔때기."""
from realestate_bot import indicators


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
        lines.append("이번 주 새로 신고된 거래가 없습니다.")
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
                f"직전 {_fmt_won(h['ref_price'])} {h['ref_date']}) · 최근 3년 기준"
            )
        lines.append("")

    lines.append("> 데이터: 국토교통부 실거래가. 최근 월은 신고 지연으로 미확정이며, "
                 "중앙가 변화는 동일 평형밴드 매칭(믹스보정) 기준.")
    return "\n".join(lines)
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `.venv/bin/pytest tests/realestate/test_digest.py -v`
Expected: 2 passed.

- [ ] **Step 5: 커밋**

```bash
git add realestate_bot/digest.py tests/realestate/test_digest.py
git commit -m "Add realestate_bot digest (깔때기 markdown 리포트) + tests"
```

---

## Task 7: commentary.py — AI 해석 시황

**Files:**
- Create: `realestate_bot/commentary.py`
- Test: `tests/realestate/test_commentary.py`

- [ ] **Step 1: gemini 진입점 시그니처 확인**

Run: `grep -nA8 "def call_gemini_with_fallback" shared/gemini_cli.py`
호출 방식(인자/반환)을 확인해 아래 `make_commentary`의 호출부를 실제 시그니처에 맞춘다. 반환이 `GeminiResponse`(텍스트 속성 보유)인지 문자열인지 확인하고, 텍스트 추출 코드를 거기에 맞춰 작성.

- [ ] **Step 2: 실패하는 테스트 작성 (gemini mock — 실패 시 빈 문자열)**

Create `tests/realestate/test_commentary.py`:
```python
from unittest import mock
from realestate_bot import commentary


def test_returns_text_on_success():
    with mock.patch("realestate_bot.commentary._ask_gemini", return_value="시황 텍스트"):
        out = commentary.make_commentary({"seoul": {"new_total": 10}})
    assert out == "시황 텍스트"


def test_degrades_to_empty_on_failure():
    with mock.patch("realestate_bot.commentary._ask_gemini",
                    side_effect=RuntimeError("429")):
        out = commentary.make_commentary({"seoul": {"new_total": 10}})
    assert out == ""
```

- [ ] **Step 3: 테스트 실행 → 실패 확인**

Run: `.venv/bin/pytest tests/realestate/test_commentary.py -v`
Expected: FAIL.

- [ ] **Step 4: commentary.py 구현**

Create `realestate_bot/commentary.py` — `_ask_gemini`는 Step 1에서 확인한 실제 시그니처로 작성. 아래는 `call_gemini_with_fallback(prompt) -> 객체(.text 또는 .content)` 가정 템플릿이며, Step 1 결과에 맞춰 `_ask_gemini` 내부만 조정:
```python
"""계산된 지표를 받아 AI 해석 시황을 생성 (실패 시 빈 문자열로 degrade)."""
import json
import logging

logger = logging.getLogger(__name__)

_FRAME = (
    "다음은 서울 아파트 주간 실거래 지표(코드가 계산한 확정 숫자)다. "
    "숫자를 재계산하지 말고, 아래 순서로 2~3문단의 시황만 한국어로 써라: "
    "① 거래량(활동·선행) → ② 중앙가 방향 → ③ 신고가/신저점 비중(모멘텀) → "
    "④ 세그먼트·구간 확산. 단정 대신 정합성으로 해석하고, 최근 월은 미확정임을 감안하라. "
    "한자 학술 용어 헤더(기승전결 등) 금지, 표/숫자 나열 금지, 해석 문장만.\n\n지표:\n"
)


def _ask_gemini(prompt: str) -> str:
    # Step 1에서 확인한 shared.gemini_cli 실제 시그니처에 맞춰 작성.
    from shared.gemini_cli import call_gemini_with_fallback
    resp = call_gemini_with_fallback(prompt)
    text = getattr(resp, "text", None) or getattr(resp, "content", None) or str(resp)
    if not text or not text.strip():
        raise RuntimeError("empty gemini response")
    return text.strip()


def make_commentary(indicators_summary: dict) -> str:
    prompt = _FRAME + json.dumps(indicators_summary, ensure_ascii=False, indent=2)
    try:
        return _ask_gemini(prompt)
    except Exception as e:  # noqa: BLE001
        logger.warning("commentary degraded (no AI): %s", e)
        return ""
```

- [ ] **Step 5: 테스트 실행 → 통과 확인**

Run: `.venv/bin/pytest tests/realestate/test_commentary.py -v`
Expected: 2 passed.

- [ ] **Step 6: 커밋**

```bash
git add realestate_bot/commentary.py tests/realestate/test_commentary.py
git commit -m "Add realestate_bot AI 시황 commentary (gemini, 실패시 degrade) + tests"
```

---

## Task 8: weekly_realestate_bot.py — 오케스트레이션 + CLI

**Files:**
- Create: `weekly_realestate_bot.py`
- Test: `tests/realestate/test_orchestration.py`

오케스트레이션 핵심 로직(`build_report`)을 fetch/blogger와 분리해 테스트 가능하게 만든다.

- [ ] **Step 1: 실패하는 테스트 작성 (fetch_region mock → build_report)**

Create `tests/realestate/test_orchestration.py`:
```python
from unittest import mock
import importlib

bot = importlib.import_module("weekly_realestate_bot")  # top-level entry file


def _items(region, base_price):
    # 동일 단지/평형 2건: 1건은 baseline, 다음 호출분이 신고가
    return [{"apt_name": "테스트팰리스", "dong": "동", "area_sqm": 84.9, "floor": 5,
             "price_10k": base_price, "trade_date": "2026-05-10",
             "build_year": 2015, "deal_type": "중개거래"}]


def test_build_report_flags_new_high(tmp_path):
    from realestate_bot.store import RealEstateStore
    store = RealEstateStore(str(tmp_path / "t.db"))
    # 사전 이력 적재(baseline)
    store.insert_new([{"region_code": "11680", "apt_name": "테스트팰리스", "dong": "동",
                       "area_sqm": 84.9, "floor": 4, "price_10k": 200000,
                       "trade_date": "2026-02-01", "build_year": 2015, "deal_type": "중개거래"}])

    def fake_fetch(code, ym, **kw):
        if code == "11680":
            return [{"apt_name": "테스트팰리스", "dong": "동", "area_sqm": 84.9, "floor": 9,
                     "price_10k": 250000, "trade_date": "2026-05-20",
                     "build_year": 2015, "deal_type": "중개거래", "region_code": "11680"}]
        return []

    with mock.patch("realestate_bot.fetcher.fetch_region", side_effect=fake_fetch):
        report = bot.build_report(store, regions={"강남구": "11680"},
                                  months=["202605"], as_of="2026-05-23")
    assert report["seoul"]["high_total"] == 1
    assert any(h["apt_name"] == "테스트팰리스" and h["kind"] == "HIGH"
               for h in report["highlights"])
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `.venv/bin/pytest tests/realestate/test_orchestration.py -v`
Expected: FAIL (`AttributeError: build_report` 또는 import 에러).

- [ ] **Step 3: weekly_realestate_bot.py 구현**

Create `weekly_realestate_bot.py` (001_code 루트, top-level):
```python
#!/usr/bin/env python3
"""주간 서울 아파트 시장 흐름 다이제스트 봇.

  python weekly_realestate_bot.py --once [--test]   # 즉시 1회 (test=업로드 스킵)
  python weekly_realestate_bot.py --backfill 36     # 25구 × N개월 초기 적재
  python weekly_realestate_bot.py                   # 스케줄 (토 08:00)
"""
import os
import re
import sys
import time
import logging
import argparse
import subprocess
import schedule
from datetime import datetime, date

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from realestate_bot import config, fetcher, indicators, commentary, digest
from realestate_bot.store import RealEstateStore
from realestate_bot.detector import classify
from shared.blogger_uploader import BloggerUploader
from shared.telegram_notifier import TelegramNotifier
from shared.claude_html_converter import convert_md_to_html_via_claude

load_dotenv(override=True)
os.makedirs("./logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(f"./logs/realestate_bot_{datetime.now():%Y%m%d}.log",
                                  encoding="utf-8")],
)
logger = logging.getLogger(__name__)

TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"


def _recent_months(n: int, ref: date = None) -> list:
    ref = ref or date.today()
    out = []
    y, m = ref.year, ref.month
    for _ in range(n):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def build_report(store: RealEstateStore, regions: dict, months: list, as_of: str) -> dict:
    """fetch → diff → 지표 → report dict. (fetch_region은 외부에서 mock 가능)"""
    cur_year = int(as_of[:4])
    per_gu = {}
    highlights = []
    seoul = {"new_total": 0, "high_total": 0, "low_total": 0}

    for gu, code in regions.items():
        # 1) baseline 스냅샷(삽입 전)
        baseline = store.baseline_snapshot(code, as_of=as_of)
        # 2) fetch + 적재(diff)
        fetched = []
        for ym in months:
            try:
                fetched.extend(fetcher.fetch_region(code, ym))
            except Exception as e:  # noqa: BLE001
                logger.warning("skip %s %s: %s", gu, ym, e)
        new_records = store.insert_new(fetched)
        # 3) 판정
        verdicts = []
        for r in new_records:
            v = classify(r, baseline.get((r["apt_name"], r["area_band"])))
            verdicts.append(v)
            if v.kind in ("HIGH", "LOW"):
                highlights.append({"gu": gu, "apt_name": r["apt_name"],
                                   "area_band": r["area_band"], "price_10k": r["price_10k"],
                                   "pct": v.pct, "kind": v.kind,
                                   "ref_price": v.ref_price, "ref_date": v.ref_date})
        # 4) 지표
        b = indicators.breadth(verdicts)
        latest_ym = months[0]
        prev_ym = months[1] if len(months) > 1 else None
        cur_bm = store.band_medians(code, latest_ym)
        prev_bm = store.band_medians(code, prev_ym) if prev_ym else {}
        mix = indicators.mix_adjusted_change(
            {k: v["median"] for k, v in cur_bm.items()},
            {k: v["median"] for k, v in prev_bm.items()},
            {k: v["count"] for k, v in cur_bm.items()})
        seg = indicators.segment_flags(new_records, current_year=cur_year)
        per_gu[gu] = {"new_count": len(new_records), "breadth": b,
                      "mix_change": mix, "segment": seg}
        seoul["new_total"] += len(new_records)
        seoul["high_total"] += b["high"]
        seoul["low_total"] += b["low"]

    seoul["high_pct"] = (seoul["high_total"] / seoul["new_total"] * 100
                         if seoul["new_total"] else 0.0)
    highlights.sort(key=lambda h: abs(h["pct"] or 0), reverse=True)
    return {"week_label": f"{as_of} 기준 주간", "seoul": seoul,
            "per_gu": per_gu, "highlights": highlights[:15]}


def _convert_html(md: str) -> str:
    """h2 청크 분할 후 Claude HTML 변환 (buffett 패턴)."""
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
    parts = []
    for i, c in enumerate(chunks, 1):
        try:
            html, _ = convert_md_to_html_via_claude(c)
            parts.append(html if len(html) >= len(c) * 0.3 else c)
        except Exception as e:  # noqa: BLE001
            logger.warning("html chunk %s failed: %s", i, e)
            parts.append(c)
    return "\n\n".join(parts).strip()


class RealEstateBot:
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self.store = RealEstateStore()
        self.blogger = None if test_mode else BloggerUploader(
            blog_id=config.REALESTATE_BLOGGER_BLOG_ID,
            credentials_path=os.getenv("BLOGGER_CREDENTIALS_PATH", "./credentials/blogger_credentials.json"),
            token_path=os.getenv("BLOGGER_TOKEN_PATH", "./credentials/blogger_token.pkl"))
        self.telegram = (TelegramNotifier(os.getenv("TELEGRAM_BOT_TOKEN", ""),
                                          os.getenv("TELEGRAM_CHAT_ID", ""))
                         if TELEGRAM_ENABLED else None)
        logger.info("RealEstateBot init (test_mode=%s)", test_mode)

    def run(self) -> dict:
        result = {"success": False, "blog_url": None, "error": None}
        try:
            months = _recent_months(2)
            report = build_report(self.store, config.SEOUL_GU, months,
                                  as_of=date.today().isoformat())
            comment = commentary.make_commentary(
                {"seoul": report["seoul"],
                 "top": dict(list(indicators.rank_regions(report["per_gu"]))[:5])})
            md = digest.build_digest(report)
            if comment:
                md += "\n\n## 시황 해석\n\n" + comment

            if report["seoul"]["new_total"] == 0:
                if self.telegram:
                    self.telegram.send_message("🏠 이번 주 서울 신규 신고 없음", parse_mode="HTML")
                result["success"] = True
                return result

            title = f"{date.today():%Y-%m-%d} 서울 아파트 시장 흐름"
            if not self.test_mode:
                html = _convert_html(md)
                up = self.blogger.upload_post(title=title, content=html,
                                              labels=["부동산", "서울", "주간"],
                                              is_draft=False, is_markdown=False)
                if not up["success"]:
                    raise RuntimeError(f"upload failed: {up.get('message')}")
                result["blog_url"] = up.get("url")
            result["success"] = True

            if self.telegram:
                s = report["seoul"]
                link = f"<a href='{result['blog_url']}'>블로그</a>" if result["blog_url"] else "테스트"
                self.telegram.send_message(
                    f"🏠 <b>{title}</b>\n신규 {s['new_total']} · 신고가 {s['high_total']}"
                    f"({s['high_pct']:.0f}%)\n{link}", parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            logger.error("realestate bot error: %s", e)
            result["error"] = str(e)
            if self.telegram:
                try:
                    self.telegram.send_message(f"❌ 부동산 봇 실패: {e}", parse_mode="HTML")
                except Exception:
                    pass
        return result

    def backfill(self, months: int):
        all_months = _recent_months(months)
        for gu, code in config.SEOUL_GU.items():
            for ym in all_months:
                try:
                    recs = fetcher.fetch_region(code, ym)
                    n = len(self.store.insert_new(recs))
                    logger.info("backfill %s %s: +%s", gu, ym, n)
                except Exception as e:  # noqa: BLE001
                    logger.warning("backfill skip %s %s: %s", gu, ym, e)

    def run_scheduled(self):
        getattr(schedule.every(), config.SCHEDULE_DAY).at(config.SCHEDULE_TIME).do(self.run)
        logger.info("scheduled %s %s", config.SCHEDULE_DAY, config.SCHEDULE_TIME)
        while True:
            schedule.run_pending()
            time.sleep(60)


def main():
    p = argparse.ArgumentParser(description="Seoul weekly apartment market digest bot")
    p.add_argument("--once", action="store_true")
    p.add_argument("--test", action="store_true")
    p.add_argument("--backfill", type=int, metavar="MONTHS")
    args = p.parse_args()

    boot = RealEstateBot(test_mode=args.test)
    if args.backfill:
        boot.backfill(args.backfill)
    elif args.once:
        r = boot.run()
        print(f"Result: {'OK' if r['success'] else 'FAIL'} {r.get('blog_url') or r.get('error') or ''}")
    else:
        try:
            boot.run_scheduled()
        except KeyboardInterrupt:
            logger.info("stopped")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 실행 → 통과 확인**

Run: `.venv/bin/pytest tests/realestate/test_orchestration.py -v`
Expected: 1 passed.

- [ ] **Step 5: 전체 단위 테스트 회귀 확인**

Run: `.venv/bin/pytest tests/realestate/ -v`
Expected: all passed (config 4 + store 6 + detector 5 + indicators 6 + fetcher 4 + digest 2 + commentary 2 + orchestration 1 = 30).

- [ ] **Step 6: 커밋**

```bash
git add weekly_realestate_bot.py tests/realestate/test_orchestration.py
git commit -m "Add realestate_bot 오케스트레이션 + --once/--test/--backfill CLI + tests"
```

---

## Task 9: investment_bot.py 스케줄 등록

**Files:**
- Modify: `investment_bot.py` (스케줄 등록부, 약 line 92~133 영역)

- [ ] **Step 1: 등록 코드 추가**

`investment_bot.py`에서 다른 봇 등록부(예: `schedule.every().sunday.at("07:00")...` 부근)에 추가. 먼저 인스턴스 생성을 봇 초기화 블록(다른 `*_bot = ...Bot(...)` 부근)에 추가:
```python
    from weekly_realestate_bot import RealEstateBot
    realestate_digest_bot = RealEstateBot(test_mode=args.test)
```
그리고 스케줄 등록:
```python
    schedule.every().saturday.at("08:00").do(
        _safe_run, "RealEstate", realestate_digest_bot.run
    )
    logger.info("Scheduled: RealEstate digest at Saturday 08:00")
```
(엔트리 파일 `weekly_realestate_bot.py`는 패키지 `realestate_bot/`와 이름이 달라 import 충돌 없음 — 기존 `weekly_sector_bot.py` + `sector_bot/`와 동일 패턴.)

- [ ] **Step 2: import/등록 무오류 확인**

Run: `.venv/bin/python -c "import investment_bot"`
Expected: import 에러 없음 (실행은 하지 않음).

- [ ] **Step 3: 커밋**

```bash
git add investment_bot.py
git commit -m "Update investment_bot: 부동산 주간 다이제스트 토 08:00 스케줄 등록"
```

> **이름 규칙(중요):** 엔트리 파일은 패키지명과 반드시 달라야 한다. 이 계획은 패키지 `realestate_bot/`(내부 모듈) + 엔트리 `weekly_realestate_bot.py`(클래스·CLI)로 분리했다 — 기존 `sector_bot/` + `weekly_sector_bot.py`와 동일. 두 이름을 같게 두면 `import realestate_bot`이 모호해지므로 절대 금지.

---

## Task 10: 백필 + 첫 라이브 스모크 (운영, MCP 필요)

**Files:** 없음 (실행 단계)

- [ ] **Step 1: 소규모 백필로 파이프라인 확인**

먼저 3~5개 구만 빠르게 확인하려면 임시로 `config.SEOUL_GU`를 줄이지 말고, 직접 호출로 점검:
```bash
.venv/bin/python -c "
from realestate_bot.store import RealEstateStore
from realestate_bot import fetcher
s=RealEstateStore()
for ym in ['202604','202605']:
    n=len(s.insert_new(fetcher.fetch_region('11680',ym)))
    print('강남',ym,'+',n)
"
```
Expected: 각 월 양수 적재.

- [ ] **Step 2: 전체 백필 (36개월, 시간 소요 — 백그라운드 권장)**

```bash
.venv/bin/python weekly_realestate_bot.py --backfill 36
```
Expected: 로그에 구·월별 `+N` 적재. 중간 실패 구는 경고 후 진행(멱등이라 재실행 안전).

- [ ] **Step 3: --once --test 스모크 (업로드 스킵)**

```bash
.venv/bin/python weekly_realestate_bot.py --once --test
```
Expected: `Result: OK`. 에러 없이 report 생성·digest 빌드까지 완료.

- [ ] **Step 4: 산출물 markdown 육안 점검**

`--test`에서 markdown을 파일로 떨궈 확인하려면 `run()`에 임시 저장을 넣지 말고, 위 Step 3 직후 다음으로 확인:
```bash
.venv/bin/python -c "
from datetime import date
from realestate_bot import digest, config
from realestate_bot.store import RealEstateStore
import weekly_realestate_bot as bot
r=bot.build_report(RealEstateStore(), config.SEOUL_GU, bot._recent_months(2), date.today().isoformat())
print(digest.build_digest(r)[:2000])
"
```
순위표·신고가 하이라이트·caveat이 자연스러운지, 숫자가 합리적인지 점검. "역대/최고가" 과장 표현이 없고 "최근 3년" 라벨이 붙는지 확인.

- [ ] **Step 5: 실제 발행 1회 (선택, 승인 후)**

사용자 승인 시 `--once`(업로드 포함)로 1회 발행해 Blogger/Telegram 결선 확인. 라벨·제목·HTML 렌더 점검.

---

## Self-Review 결과 (작성자 점검)

- **Spec 커버리지:** §3-B 지표 ①~⑤ → Task 2(거래량/중앙가 집계)·3(신고가/신저점)·4(breadth/믹스보정/세그먼트/순위). §4 파이프라인 → Task 8 `build_report`+`run`. §8 fetcher(함정 포함) → Task 5. §9 digest 깔때기 → Task 6. §9 빈주 정책 → Task 8 `run`/Task 6. §10 backfill → Task 8 `backfill`/Task 10. §11 에러처리 → 구별 try/except·gemini degrade·`_safe_run`. §12 테스트 → 각 Task. §13 단계순서 → Task 1~10 대응. 누락 없음.
- **Placeholder 스캔:** 코드 단계는 전부 실제 코드 포함. 단 commentary `_ask_gemini`는 Task 7 Step 1에서 실제 gemini 시그니처 확인 후 확정(명시적 검증 단계로 처리, 빈칸 아님).
- **타입 일관성:** `Verdict(kind/pct/ref_price/ref_date)`·store 메서드명(`insert_new/baseline_snapshot/monthly_volume/band_medians`)·indicators 시그니처·digest 입력 dict 구조가 Task 2~8 전반에서 동일하게 사용됨. `build_report` 출력(seoul/per_gu/highlights/week_label)이 digest 입력과 일치.
- **해소된 리스크:** top-level 파일/패키지 동명 충돌 → 엔트리를 `weekly_realestate_bot.py`로 분리(패키지 `realestate_bot/`와 다름)해 제거. Task 9 Step 2(`import investment_bot`)로 재확인.
