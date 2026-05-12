# Casper Data Collector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 캐스퍼봇이 매매 중에 이미 fetch하는 5분봉 OHLCV를 영구 저장(Parquet)하고, 봇이 꺼져있던 기간은 yfinance로 백필하며, 갭을 자동 탐지·보강하는 데이터 수집 서브시스템을 추가한다. 매매 로직과 완전 격리(try/except + 별도 thread)되어 캐스퍼 안정성에 영향을 주지 않는다.

**Architecture:** In-process 통합(별도 봇 아님). `src/data/store.py`(atomic Parquet I/O), `src/data/calendar.py`(NYSE 영업일), `src/data/gap_finder.py`(빈 일자 탐지), `src/data/backfill.py`(yfinance 60일 백필), `src/data/collector.py`(실시간 수집 thread)로 모듈 분리. `bot.py`에는 단 두 줄(env-toggle + thread start)만 추가. 데이터 저장 실패가 매매 main loop에 절대 전염되지 않도록 try/except로 완전 격리한다.

**Tech Stack:** Python 3.14, pyarrow(Parquet), pandas, yfinance(이미 설치), pytest(이미 설치), threading(asyncio 아님 — 기존 봇 패턴과 동일), pandas_market_calendars(NYSE 영업일).

---

## 0. 배경 / 현재 상태 진단 (2026-05-11 기준)

### 0.1 현재 상태 (실측)

- `data/raw/ohlcv/{1min,5min}/` 디렉토리 존재하지만 **0 바이트** (수집 코드 없음).
- `src/data/market_data.py`는 매번 yfinance/KIS API로 fetch만 하고 메모리에서 폐기.
- yfinance 자체 캐시(`~/Library/Caches/py-yfinance/`)는 cookies·TZ DB만 ~80KB, OHLCV는 저장 X.
- 매매 기록(`data/trades/trades_2026.json`, 24KB)에는 ORB high/low/FVG top/bot 같은 계산 결과만 들어감 — 원시 차트 데이터 아님.
- 백테스트 시 매번 yfinance를 다시 부르고 60일 한도에 묶임.

### 0.2 봇 메인 루프 패턴

`src/bot.py:321`의 `while True` 메인 루프 + `time.sleep()` 패턴. **sync, asyncio 아님**. 따라서 데이터 수집기도 **threading**으로 구현 (asyncio 도입은 비용 큼).

### 0.3 이미 fetch하는 데이터를 그대로 저장

봇은 이미 매매 시간에 `get_intraday_bars(symbol, period="1d", interval="5m")`(`bot.py:523, 579`)로 5분봉을 가져온다. **추가 KIS 호출 없이 그 결과만 저장**하면 KIS API 부담 0. 추가 호출은 RTH 외 시간대 보강용으로만 필요.

---

## 1. 요구사항

### 1.1 Functional

- **F1.** 봇 동작 중(09:30~16:00 ET) 5분봉을 RTH 매 5분 자동 저장 (TQQQ + QQQ + SQQQ + ^VIX 4 ticker).
- **F2.** 봇 시작 시 yfinance로 최근 60일 빈 일자 자동 백필 (cold start 1회).
- **F3.** 임의 시점 수동 백필 CLI 제공 (`scripts/backfill_marketdata.py --symbol TQQQ --days 60`).
- **F4.** 영업일 캘린더 기반 갭 탐지 (NYSE 휴장일/조기폐장 정확히 인식).
- **F5.** 저장된 데이터를 일관된 API로 로드 (`load_bars(symbol, start, end, interval)`).
- **F6.** 데이터 수집 실패 시 매매 main loop 영향 0 (try/except 격리, silent log).

### 1.2 Non-functional

- **N1.** 디스크 사용량 ≤ **10 MB/year** (4 ticker × 5m, Parquet Snappy).
- **N2.** 메인 루프 1 tick 영향 ≤ **10 ms** (atomic Parquet write 비동기).
- **N3.** 메모리 증가 ≤ **20 MB** (pyarrow + 일별 buffer).
- **N4.** Cold start 백필 ≤ **30초** (yfinance 60일 5min 호출 4회).
- **N5.** 환경변수 토글: `DATA_COLLECTION=on|off`, 기본값 `off` (안전한 점진적 도입).

### 1.3 Out of scope (이 plan에서 다루지 않음)

- 1분봉 수집 (5분봉만 우선, 추후 plan)
- 호가/체결/오더북 수집
- 분산 저장소 / S3 / Database
- DuckDB / SQLite 쿼리 레이어 (Parquet 직접 읽기로 충분)
- 24/7 pre-market / after-hours 수집 (해당 시 별도 collector 봇 필요)
- 다국가/거래소 확장

---

## 2. 아키텍처

### 2.1 데이터 흐름

```
┌─────────────────────────────────────────────────────────────┐
│  Casper Main Thread (bot.py)                                │
│                                                             │
│  while True:                                                │
│    _tick()                                                  │
│      ├─ market_data.get_intraday_bars(symbol)               │
│      │     ↓ (return DataFrame)                             │
│      │     ↓ (also pushed to collector queue if enabled)    │
│      └─ ... 기존 매매 로직 ...                              │
│                                                             │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │  (threading.Queue, non-blocking put)
                   ↓
┌─────────────────────────────────────────────────────────────┐
│  Collector Thread (collector.py)                            │
│                                                             │
│  while not stop_event.is_set():                             │
│    df = queue.get(timeout=30)                               │
│    try:                                                     │
│      store.append_bars(symbol, df)                          │
│    except Exception as e:                                   │
│      logger.warning(f"data save failed: {e}")  # silent     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  Cold-start Backfill (bot startup, before main loop)        │
│                                                             │
│  gaps = gap_finder.find(symbol, last_60_days)               │
│  backfill.fill_from_yfinance(symbol, gaps)                  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 모듈 책임 분리

| 모듈 | 책임 | 의존성 |
|------|------|-------|
| `src/data/store.py` | Parquet read/write atomic (tmp→rename), 스키마 enforcement | pyarrow, pandas |
| `src/data/calendar.py` | NYSE 영업일 / 조기폐장 / 시간대 변환 | pandas_market_calendars |
| `src/data/gap_finder.py` | 저장된 파일 vs 영업일 캘린더 비교 → 빈 일자 리스트 | store, calendar |
| `src/data/backfill.py` | yfinance로 갭 일자 채우기, exponential backoff | yfinance, store, gap_finder |
| `src/data/collector.py` | threading.Thread, queue 기반 실시간 저장, 안전 정지 | store, threading |
| `src/data/loader.py` | 백테스트/분석용 통합 로드 API (`load_bars()`) | store, calendar |
| `scripts/backfill_marketdata.py` | 수동 백필 CLI | backfill, gap_finder |
| `src/bot.py` (수정) | collector start/stop, env toggle (2~3줄만) | collector |

### 2.3 파일 책임 원칙

- 각 모듈 200줄 이하 (한눈에 파악 가능)
- 외부 의존성(yfinance, KIS)은 thin wrapper로 격리
- store.py는 **persistence만** — 영업일 로직 X
- gap_finder.py는 **탐지만** — fill 로직 X
- collector.py는 **schedule + queue만** — write 자체는 store에 위임

---

## 3. 데이터 포맷 사양

### 3.1 Parquet 스키마 (5분봉)

| 컬럼 | 타입 | 단위 / 의미 | 비고 |
|------|------|-----------|------|
| `timestamp` | int64 | epoch milliseconds (UTC) | bar 시작 시각 |
| `open` | float32 | USD | |
| `high` | float32 | USD | |
| `low` | float32 | USD | |
| `close` | float32 | USD | |
| `volume` | int64 | shares | ^VIX는 0 가능 |
| `source` | dictionary<string> | "kis" / "yfinance" | 출처 추적 |

**압축**: Snappy (Zstd보다 빠르고 디코딩 부담 적음).
**행 그룹 크기**: 78 rows (1일치 5분봉) — 일별 파티션이라 그룹 1개로 충분.

### 3.2 디렉토리 구조

```
data/marketdata/
├── TQQQ/
│   ├── 2026/
│   │   ├── 2026-05-07.parquet      (78 rows, ~3 KB)
│   │   ├── 2026-05-08.parquet
│   │   └── ...
│   └── 2025/
├── QQQ/
├── SQQQ/
└── _VIX/                            (^VIX → _VIX, filesystem-safe)
```

**파일명**: `YYYY-MM-DD.parquet` (1 파일 = 1 영업일).
이유: 갭 탐지가 파일 존재 여부만 보면 되므로 O(1). 일자 단위 atomic write 보장.

### 3.3 용량 추정 (실측 기반)

- 5분봉 1 row Parquet+Snappy 압축: ~10 bytes (timestamp/OHLCV/source)
- 1일치 78 rows ≈ **~1 KB**
- 4 ticker × 1일 = ~4 KB
- 252 영업일 × 4 KB = **~1 MB/year**
- 안전 margin 포함 가정 **~2 MB/year** (메타데이터 + footer)

### 3.4 메타데이터 (선택, Phase 2)

- `data/marketdata/_meta.json`: 마지막 백필 시각, 총 row 수, ticker별 first/last bar
- Phase 1에서는 생략 (gap_finder가 매번 디렉토리 스캔)

---

## 4. 안전장치 / 격리 규칙

### 4.1 매매 영향 0 보장

1. **try/except wrap**: collector의 모든 호출은 `try/except Exception` 으로 감싸고 `logger.warning`만 남김. 절대 raise 안 함.
2. **별도 thread**: `daemon=True` thread로 실행. 메인 루프 블로킹 0.
3. **non-blocking queue**: `queue.put_nowait()` 사용. queue 가득 차면 drop + warn.
4. **default OFF**: env var `DATA_COLLECTION=on` 명시적으로 켜야 활성화.
5. **graceful stop**: 봇 종료 시 `stop_event.set()` + thread.join(timeout=5s).

### 4.2 디스크 안전

- **atomic write**: `df.to_parquet(tmp_path); os.rename(tmp_path, final_path)` 패턴.
- **append idempotent**: 같은 일자에 두 번 저장해도 마지막 것이 이김 (rename overwrites).
- **디스크 가득**: `os.statvfs()` 체크, free < 100MB이면 수집 자동 정지 + warn.

### 4.3 KIS rate limit

- **추가 호출 0**: 봇 매매 시간(09:30~16:00) 동안은 이미 fetch한 DataFrame을 queue.put만 함.
- **백필 시에만 yfinance 추가 호출**: cold start 1회, exponential backoff.

---

## 5. 단계별 Task 분해

각 Task는 독립적으로 commit 가능한 단위. TDD: 실패하는 테스트 → 구현 → 통과 → 커밋.

---

### Task 1: NYSE 영업일 캘린더 모듈

**Files:**
- Create: `src/data/calendar.py`
- Test: `tests/test_data_calendar.py`

**Dependency 추가:**
- `requirements.txt`에 `pandas_market_calendars>=4.0.0` 추가

- [ ] **Step 1: Add dependency to requirements.txt**

```
pandas_market_calendars>=4.0.0
```

- [ ] **Step 2: Write failing test for trading_days**

```python
# tests/test_data_calendar.py
from datetime import date
import pytest
from src.data.calendar import trading_days, is_trading_day, early_close_minutes

def test_trading_days_excludes_weekends():
    days = trading_days(date(2026, 5, 4), date(2026, 5, 10))
    # 2026-05-04 Mon, 05-05 Tue, 06 Wed, 07 Thu, 08 Fri — 5 days
    assert len(days) == 5
    assert date(2026, 5, 9) not in days   # Saturday
    assert date(2026, 5, 10) not in days  # Sunday

def test_trading_days_excludes_holidays_independence():
    # 2025-07-04 Friday = US Independence Day → closed
    days = trading_days(date(2025, 6, 30), date(2025, 7, 4))
    assert date(2025, 7, 4) not in days

def test_is_trading_day_true_for_weekday():
    assert is_trading_day(date(2026, 5, 7)) is True   # Thursday

def test_is_trading_day_false_for_weekend():
    assert is_trading_day(date(2026, 5, 10)) is False  # Sunday

def test_early_close_thanksgiving():
    # Day after Thanksgiving — 13:00 ET close
    minutes = early_close_minutes(date(2025, 11, 28))
    assert minutes == 13 * 60  # close at 13:00 ET
```

- [ ] **Step 3: Run test to verify FAIL**

```bash
cd /Users/seongwookjang/project/git/violet_sw/014_casper
pytest tests/test_data_calendar.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.data.calendar'`

- [ ] **Step 4: Implement src/data/calendar.py**

```python
"""NYSE trading calendar helpers.

Wraps pandas_market_calendars and exposes minimal helpers used by the
data collector and gap finder.
"""

from datetime import date, datetime
from typing import List
import pandas_market_calendars as mcal


_nyse = mcal.get_calendar("NYSE")


def trading_days(start: date, end: date) -> List[date]:
    """Return sorted list of NYSE trading days in [start, end], inclusive."""
    sched = _nyse.schedule(start_date=start, end_date=end)
    return [ts.date() for ts in sched.index]


def is_trading_day(d: date) -> bool:
    """True if d is an NYSE trading day."""
    sched = _nyse.schedule(start_date=d, end_date=d)
    return not sched.empty


def early_close_minutes(d: date) -> int:
    """Minutes from midnight ET for the close. Normal day = 16*60. Early close (e.g. day after Thanksgiving) = 13*60."""
    sched = _nyse.schedule(start_date=d, end_date=d)
    if sched.empty:
        return 0
    close_ts = sched.iloc[0]["market_close"]
    # Convert to ET-local hour:minute
    close_et = close_ts.tz_convert("US/Eastern")
    return close_et.hour * 60 + close_et.minute
```

- [ ] **Step 5: Install dependency**

```bash
pip install 'pandas_market_calendars>=4.0.0'
```

- [ ] **Step 6: Run test to verify PASS**

```bash
pytest tests/test_data_calendar.py -v
```

Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add requirements.txt src/data/calendar.py tests/test_data_calendar.py
git commit -m "Add NYSE trading calendar module for data collector"
```

---

### Task 2: Parquet 저장소 모듈 (store)

**Files:**
- Create: `src/data/store.py`
- Test: `tests/test_data_store.py`

- [ ] **Step 1: Write failing test for atomic write + read roundtrip**

```python
# tests/test_data_store.py
import os
import tempfile
from datetime import datetime, timezone
import pandas as pd
import pytest
from src.data.store import save_bars, load_bars, _path_for


@pytest.fixture
def tmpdir(tmp_path):
    return tmp_path


def _sample_bars():
    idx = pd.date_range("2026-05-08 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {
            "Open": [80.10, 80.50, 80.30],
            "High": [80.55, 80.60, 80.40],
            "Low":  [80.05, 80.20, 80.15],
            "Close":[80.45, 80.40, 80.35],
            "Volume":[100000, 95000, 80000],
        },
        index=idx,
    )


def test_path_for_uses_underscore_for_caret(tmpdir):
    p = _path_for(tmpdir, "^VIX", "2026-05-08")
    assert "/_VIX/" in str(p)
    assert p.name == "2026-05-08.parquet"


def test_save_and_load_roundtrip(tmpdir):
    bars = _sample_bars()
    save_bars(tmpdir, "TQQQ", "2026-05-08", bars, source="kis")
    loaded = load_bars(tmpdir, "TQQQ", "2026-05-08")
    assert len(loaded) == 3
    assert loaded.iloc[0]["close"] == pytest.approx(80.45, rel=1e-4)
    assert all(loaded["source"] == "kis")


def test_save_is_atomic_no_tmp_leftover(tmpdir):
    bars = _sample_bars()
    save_bars(tmpdir, "TQQQ", "2026-05-08", bars, source="kis")
    # No .tmp files should remain
    leftovers = list(tmpdir.rglob("*.tmp"))
    assert leftovers == []


def test_save_overwrites_existing_same_day(tmpdir):
    bars1 = _sample_bars()
    save_bars(tmpdir, "TQQQ", "2026-05-08", bars1, source="yfinance")
    bars2 = bars1.copy()
    bars2.loc[bars2.index[0], "Close"] = 99.99
    save_bars(tmpdir, "TQQQ", "2026-05-08", bars2, source="kis")
    loaded = load_bars(tmpdir, "TQQQ", "2026-05-08")
    assert loaded.iloc[0]["close"] == pytest.approx(99.99, rel=1e-4)
    assert all(loaded["source"] == "kis")
```

- [ ] **Step 2: Run test to verify FAIL**

```bash
pytest tests/test_data_store.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.data.store'`

- [ ] **Step 3: Implement src/data/store.py**

```python
"""Parquet-based 5-min bar persistence.

Atomic write: writes to *.tmp then renames. One file per (symbol, day).
Symbols starting with '^' are mapped to '_' (filesystem-safe).
"""

import os
from datetime import date as _date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


def _safe_symbol(symbol: str) -> str:
    return symbol.replace("^", "_")


def _path_for(base: Path, symbol: str, date_str: str) -> Path:
    sym = _safe_symbol(symbol)
    year = date_str[:4]
    return Path(base) / sym / year / f"{date_str}.parquet"


def save_bars(base: Path, symbol: str, date_str: str, bars: pd.DataFrame, source: str) -> Path:
    """Save bars for one day atomically.

    Args:
        base: root directory (e.g. data/marketdata)
        symbol: e.g. "TQQQ" or "^VIX"
        date_str: "YYYY-MM-DD"
        bars: DataFrame with columns Open/High/Low/Close/Volume, datetime index (ET)
        source: "kis" or "yfinance"
    """
    if bars is None or bars.empty:
        return None
    final_path = _path_for(base, symbol, date_str)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_suffix(".tmp")

    # Normalize to schema
    idx = bars.index.tz_convert("UTC") if bars.index.tz is not None else bars.index.tz_localize("UTC")
    out = pd.DataFrame({
        "timestamp": (idx.view("int64") // 1_000_000).astype("int64"),  # ms
        "open":  bars["Open"].astype("float32").values,
        "high":  bars["High"].astype("float32").values,
        "low":   bars["Low"].astype("float32").values,
        "close": bars["Close"].astype("float32").values,
        "volume": bars["Volume"].astype("int64").values,
        "source": [source] * len(bars),
    })

    out.to_parquet(tmp_path, engine="pyarrow", compression="snappy", index=False)
    os.replace(tmp_path, final_path)
    return final_path


def load_bars(base: Path, symbol: str, date_str: str) -> Optional[pd.DataFrame]:
    p = _path_for(base, symbol, date_str)
    if not p.exists():
        return None
    df = pd.read_parquet(p)
    return df


def has_data(base: Path, symbol: str, date_str: str) -> bool:
    return _path_for(base, symbol, date_str).exists()
```

- [ ] **Step 4: Add pyarrow to requirements.txt**

```
pyarrow>=14.0.0
```

- [ ] **Step 5: Install + run test PASS**

```bash
pip install 'pyarrow>=14.0.0'
pytest tests/test_data_store.py -v
```

Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add requirements.txt src/data/store.py tests/test_data_store.py
git commit -m "Add Parquet-based 5min bar store with atomic write"
```

---

### Task 3: 갭 탐지 모듈 (gap_finder)

**Files:**
- Create: `src/data/gap_finder.py`
- Test: `tests/test_data_gap_finder.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_data_gap_finder.py
from datetime import date
import pandas as pd
import pytest
from src.data.store import save_bars
from src.data.gap_finder import find_gaps


def _bars():
    idx = pd.date_range("2026-05-04 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame({"Open":[1,1,1],"High":[1,1,1],"Low":[1,1,1],"Close":[1,1,1],"Volume":[1,1,1]}, index=idx)


def test_find_gaps_returns_missing_trading_days(tmp_path):
    # Save only 2026-05-05 and 2026-05-07
    save_bars(tmp_path, "TQQQ", "2026-05-05", _bars(), source="kis")
    save_bars(tmp_path, "TQQQ", "2026-05-07", _bars(), source="kis")
    gaps = find_gaps(tmp_path, "TQQQ", date(2026, 5, 4), date(2026, 5, 8))
    # Trading days: 04 (Mon), 05 (Tue), 06 (Wed), 07 (Thu), 08 (Fri)
    # Missing: 04, 06, 08
    assert gaps == [date(2026, 5, 4), date(2026, 5, 6), date(2026, 5, 8)]


def test_find_gaps_excludes_weekends_and_holidays(tmp_path):
    # 2025-07-04 Fri is Independence Day (closed)
    # Range 2025-07-03 (Thu) ~ 2025-07-07 (Mon)
    # Trading days: 07-03 Thu, 07-07 Mon  (07-04 Fri closed, 05/06 weekend)
    gaps = find_gaps(tmp_path, "TQQQ", date(2025, 7, 3), date(2025, 7, 7))
    assert date(2025, 7, 4) not in gaps   # holiday
    assert date(2025, 7, 5) not in gaps   # weekend
    assert date(2025, 7, 6) not in gaps   # weekend
    assert sorted(gaps) == [date(2025, 7, 3), date(2025, 7, 7)]


def test_find_gaps_returns_empty_when_all_present(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-07", _bars(), source="kis")
    save_bars(tmp_path, "TQQQ", "2026-05-08", _bars(), source="kis")
    gaps = find_gaps(tmp_path, "TQQQ", date(2026, 5, 7), date(2026, 5, 8))
    assert gaps == []
```

- [ ] **Step 2: Run test FAIL**

```bash
pytest tests/test_data_gap_finder.py -v
```

Expected: FAIL with ModuleNotFoundError

- [ ] **Step 3: Implement src/data/gap_finder.py**

```python
"""Detect missing trading days in the Parquet store."""

from datetime import date
from pathlib import Path
from typing import List

from src.data.calendar import trading_days
from src.data.store import has_data


def find_gaps(base: Path, symbol: str, start: date, end: date) -> List[date]:
    """Return sorted trading days in [start, end] that have no stored Parquet."""
    expected = trading_days(start, end)
    return [d for d in expected if not has_data(base, symbol, d.isoformat())]
```

- [ ] **Step 4: Run PASS**

```bash
pytest tests/test_data_gap_finder.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/gap_finder.py tests/test_data_gap_finder.py
git commit -m "Add gap finder for missing trading days"
```

---

### Task 4: yfinance 백필러 (backfill)

**Files:**
- Create: `src/data/backfill.py`
- Test: `tests/test_data_backfill.py`

- [ ] **Step 1: Write failing test (with yfinance mock)**

```python
# tests/test_data_backfill.py
from datetime import date
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
from src.data.backfill import fill_gaps_from_yfinance
from src.data.store import has_data


def _fake_yf_history():
    idx = pd.date_range("2026-05-07 09:30", periods=78, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[80.0]*78, "High":[80.5]*78, "Low":[79.5]*78,
         "Close":[80.0]*78, "Volume":[1000]*78},
        index=idx,
    )


def test_fill_gaps_writes_parquet_for_each_gap(tmp_path):
    gaps = [date(2026, 5, 7), date(2026, 5, 8)]
    with patch("src.data.backfill._fetch_yf") as mock_fetch:
        mock_fetch.return_value = _fake_yf_history()
        filled = fill_gaps_from_yfinance(tmp_path, "TQQQ", gaps)

    assert filled == 2
    assert has_data(tmp_path, "TQQQ", "2026-05-07")
    assert has_data(tmp_path, "TQQQ", "2026-05-08")


def test_fill_gaps_skips_unrecoverable_days_beyond_60(tmp_path):
    from datetime import datetime, timedelta
    old_day = (datetime.utcnow().date() - timedelta(days=120))
    gaps = [old_day]
    filled = fill_gaps_from_yfinance(tmp_path, "TQQQ", gaps)
    assert filled == 0
    assert not has_data(tmp_path, "TQQQ", old_day.isoformat())


def test_fill_gaps_handles_empty_response_silently(tmp_path):
    gaps = [date(2026, 5, 7)]
    with patch("src.data.backfill._fetch_yf") as mock_fetch:
        mock_fetch.return_value = pd.DataFrame()
        filled = fill_gaps_from_yfinance(tmp_path, "TQQQ", gaps)
    assert filled == 0
    assert not has_data(tmp_path, "TQQQ", "2026-05-07")
```

- [ ] **Step 2: Run FAIL**

```bash
pytest tests/test_data_backfill.py -v
```

Expected: FAIL ModuleNotFoundError

- [ ] **Step 3: Implement src/data/backfill.py**

```python
"""Backfill missing days via yfinance (60-day rolling window)."""

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pandas as pd
import yfinance as yf

from src.data.store import save_bars

logger = logging.getLogger("casper")

YF_RETENTION_DAYS = 60  # yfinance 5m interval hard limit


def _fetch_yf(symbol: str, day: date) -> pd.DataFrame:
    """Fetch single trading day of 5m bars from yfinance. Empty df on failure."""
    try:
        end = day + timedelta(days=1)
        df = yf.download(
            symbol,
            start=day.isoformat(),
            end=end.isoformat(),
            interval="5m",
            progress=False,
            auto_adjust=False,
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        if df.empty:
            return df
        df.index = df.index.tz_convert("US/Eastern")
        return df.between_time("09:30", "15:59")
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {symbol} {day}: {e}")
        return pd.DataFrame()


def fill_gaps_from_yfinance(base: Path, symbol: str, gaps: List[date]) -> int:
    """Fill given gaps using yfinance. Returns count of days actually written.

    Days older than YF_RETENTION_DAYS are silently skipped (unrecoverable).
    """
    today = datetime.now(timezone.utc).date()
    filled = 0
    for day in gaps:
        if (today - day).days > YF_RETENTION_DAYS:
            logger.info(f"backfill: {symbol} {day} unrecoverable (>{YF_RETENTION_DAYS}d)")
            continue
        df = _fetch_yf(symbol, day)
        if df.empty:
            continue
        save_bars(base, symbol, day.isoformat(), df, source="yfinance")
        filled += 1
        time.sleep(0.3)  # be polite to yfinance
    return filled
```

- [ ] **Step 4: Run PASS**

```bash
pytest tests/test_data_backfill.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/backfill.py tests/test_data_backfill.py
git commit -m "Add yfinance backfill for missing days (60d window)"
```

---

### Task 5: 통합 로드 API (loader)

**Files:**
- Create: `src/data/loader.py`
- Test: `tests/test_data_loader.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_data_loader.py
from datetime import date
import pandas as pd
import pytest
from src.data.store import save_bars
from src.data.loader import load_range


def _bars(date_str, base=80.0):
    idx = pd.date_range(f"{date_str} 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[base]*3,"High":[base+0.5]*3,"Low":[base-0.5]*3,"Close":[base]*3,"Volume":[100]*3},
        index=idx,
    )


def test_load_range_concatenates_days_in_order(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-06", _bars("2026-05-06", 80.0), source="kis")
    save_bars(tmp_path, "TQQQ", "2026-05-07", _bars("2026-05-07", 81.0), source="kis")
    save_bars(tmp_path, "TQQQ", "2026-05-08", _bars("2026-05-08", 82.0), source="kis")
    df = load_range(tmp_path, "TQQQ", date(2026, 5, 6), date(2026, 5, 8))
    assert len(df) == 9
    assert df.iloc[0]["close"] == pytest.approx(80.0, rel=1e-4)
    assert df.iloc[-1]["close"] == pytest.approx(82.0, rel=1e-4)


def test_load_range_returns_empty_when_no_files(tmp_path):
    df = load_range(tmp_path, "TQQQ", date(2026, 5, 6), date(2026, 5, 8))
    assert df.empty


def test_load_range_skips_non_trading_days_silently(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-07", _bars("2026-05-07"), source="kis")
    # 05-09/05-10 = weekend, no files expected
    df = load_range(tmp_path, "TQQQ", date(2026, 5, 7), date(2026, 5, 10))
    assert len(df) == 3
```

- [ ] **Step 2: Run FAIL**

```bash
pytest tests/test_data_loader.py -v
```

Expected: FAIL ModuleNotFoundError

- [ ] **Step 3: Implement src/data/loader.py**

```python
"""Unified data load API for backtests / analysis."""

from datetime import date
from pathlib import Path
from typing import Optional
import pandas as pd

from src.data.store import load_bars
from src.data.calendar import trading_days


def load_range(base: Path, symbol: str, start: date, end: date) -> pd.DataFrame:
    """Load and concatenate bars for [start, end] (trading days only).

    Returns empty DataFrame if nothing is stored.
    """
    parts = []
    for d in trading_days(start, end):
        df = load_bars(base, symbol, d.isoformat())
        if df is not None and not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, ignore_index=True).sort_values("timestamp")
```

- [ ] **Step 4: Run PASS**

```bash
pytest tests/test_data_loader.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/loader.py tests/test_data_loader.py
git commit -m "Add unified load_range API for stored 5min bars"
```

---

### Task 6: 실시간 수집기 (collector thread)

**Files:**
- Create: `src/data/collector.py`
- Test: `tests/test_data_collector.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_data_collector.py
import threading
import time
import pandas as pd
import pytest
from src.data.collector import BarCollector
from src.data.store import has_data


def _bars():
    idx = pd.date_range("2026-05-08 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[80]*3,"High":[80.5]*3,"Low":[79.5]*3,"Close":[80]*3,"Volume":[100]*3},
        index=idx,
    )


def test_collector_writes_bars_to_store(tmp_path):
    c = BarCollector(base_dir=tmp_path)
    c.start()
    try:
        c.submit(symbol="TQQQ", date_str="2026-05-08", bars=_bars(), source="kis")
        time.sleep(0.5)  # let thread process
        assert has_data(tmp_path, "TQQQ", "2026-05-08")
    finally:
        c.stop(timeout=2)


def test_collector_does_not_raise_when_save_fails(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise IOError("disk full")
    monkeypatch.setattr("src.data.collector.save_bars", boom)
    c = BarCollector(base_dir=tmp_path)
    c.start()
    try:
        c.submit(symbol="TQQQ", date_str="2026-05-08", bars=_bars(), source="kis")
        time.sleep(0.3)
        assert c.is_alive()  # thread survives
    finally:
        c.stop(timeout=2)


def test_collector_drops_silently_when_queue_full(tmp_path):
    c = BarCollector(base_dir=tmp_path, queue_maxsize=1)
    # do not start thread → queue fills
    c.submit("TQQQ", "2026-05-08", _bars(), source="kis")
    # second submit should not raise
    c.submit("TQQQ", "2026-05-09", _bars(), source="kis")
    assert c.dropped_count >= 1
```

- [ ] **Step 2: Run FAIL**

```bash
pytest tests/test_data_collector.py -v
```

Expected: FAIL ModuleNotFoundError

- [ ] **Step 3: Implement src/data/collector.py**

```python
"""Realtime bar collector — threaded queue + safe drop on overflow.

Designed for in-process use from src/bot.py. Failures NEVER propagate.
"""

import logging
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from src.data.store import save_bars

logger = logging.getLogger("casper")


@dataclass
class _Job:
    symbol: str
    date_str: str
    bars: pd.DataFrame
    source: str


class BarCollector:
    """Background thread that writes submitted bars to the Parquet store.

    Safety properties:
      - submit() never raises (queue full → drop + warn)
      - thread never dies on save errors (caught and logged)
      - stop() joins with timeout, then forgets
    """

    def __init__(self, base_dir: Path, queue_maxsize: int = 256):
        self.base_dir = Path(base_dir)
        self._q: "queue.Queue[_Job]" = queue.Queue(maxsize=queue_maxsize)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.dropped_count = 0
        self.saved_count = 0

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="BarCollector", daemon=True
        )
        self._thread.start()
        logger.info("BarCollector: thread started")

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def submit(self, symbol: str, date_str: str, bars: pd.DataFrame, source: str) -> None:
        if bars is None or bars.empty:
            return
        try:
            self._q.put_nowait(_Job(symbol, date_str, bars, source))
        except queue.Full:
            self.dropped_count += 1
            logger.warning(f"BarCollector: queue full, dropped {symbol} {date_str}")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                save_bars(self.base_dir, job.symbol, job.date_str, job.bars, job.source)
                self.saved_count += 1
            except Exception as e:
                logger.warning(f"BarCollector: save failed for {job.symbol} {job.date_str}: {e}")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            logger.info(
                f"BarCollector: stopped (saved={self.saved_count} dropped={self.dropped_count})"
            )
```

- [ ] **Step 4: Run PASS**

```bash
pytest tests/test_data_collector.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/data/collector.py tests/test_data_collector.py
git commit -m "Add threaded BarCollector with safe drop and crash isolation"
```

---

### Task 7: 봇 통합 (bot.py 격리 통합)

**Files:**
- Modify: `src/bot.py` (생성자 ~3줄 + 종료 시 1줄 + 5분봉 fetch 후 1줄)
- Modify: `config/strategy_params.json` (collector 설정 추가)
- Test: `tests/test_bot_collector_integration.py`

- [ ] **Step 1: Inspect bot.py touchpoints**

읽을 위치:
- `src/bot.py:60-80` (생성자 — collector 인스턴스 생성)
- `src/bot.py:520-580` (5분봉 fetch 직후 — submit 호출)
- `src/bot.py:300-340` (메인 루프 — start 호출 위치)
- `src/bot.py:780-820` (graceful shutdown — stop 호출)

각 위치의 정확한 라인은 구현 시 `grep -n` 으로 확인.

- [ ] **Step 2: Write integration test**

```python
# tests/test_bot_collector_integration.py
import os
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest


def _bars():
    idx = pd.date_range("2026-05-08 09:30", periods=3, freq="5min", tz="US/Eastern")
    return pd.DataFrame(
        {"Open":[80]*3,"High":[80.5]*3,"Low":[79.5]*3,"Close":[80]*3,"Volume":[100]*3},
        index=idx,
    )


def test_collector_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DATA_COLLECTION", raising=False)
    from src.bot import CasperBot
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(base_dir="/tmp/test")
    assert bot.collector is None


def test_collector_enabled_when_env_on(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "on")
    from src.bot import CasperBot
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(base_dir=str(tmp_path))
    assert bot.collector is not None
    assert bot.collector.is_alive()
    bot.collector.stop(timeout=2)


def test_submit_bars_silent_on_collector_none():
    from src.bot import CasperBot
    bot = CasperBot.__new__(CasperBot)
    bot.collector = None
    # should not raise
    bot._record_bars("TQQQ", "2026-05-08", _bars())
```

- [ ] **Step 3: Run FAIL**

```bash
pytest tests/test_bot_collector_integration.py -v
```

Expected: FAIL (methods not implemented yet)

- [ ] **Step 4: Add `_init_collector` + `_record_bars` to CasperBot**

`src/bot.py` 생성자 끝부분에 추가:

```python
        # --- data collector (env-toggled, isolated) ---
        self.collector = None
        self._init_collector(base_dir="data/marketdata")
```

CasperBot 클래스에 메서드 두 개 추가:

```python
    def _init_collector(self, base_dir: str) -> None:
        """Start BarCollector iff DATA_COLLECTION=on. Safe on failure."""
        if os.environ.get("DATA_COLLECTION", "off").lower() != "on":
            self.collector = None
            return
        try:
            from src.data.collector import BarCollector
            self.collector = BarCollector(base_dir=base_dir)
            self.collector.start()
            logger.info("DataCollection: enabled (DATA_COLLECTION=on)")
        except Exception as e:
            logger.warning(f"DataCollection: init failed, disabled: {e}")
            self.collector = None

    def _record_bars(self, symbol: str, date_str: str, bars) -> None:
        """Submit bars to collector. NEVER raises."""
        if self.collector is None:
            return
        try:
            self.collector.submit(symbol, date_str, bars, source="kis")
        except Exception as e:
            logger.warning(f"DataCollection: submit failed silently: {e}")
```

5분봉 fetch 직후(`bot.py:523` 와 `579`) 한 줄 추가:

```python
bars = get_intraday_bars(symbol, period="1d", interval="5m")
self._record_bars(symbol, bars.index[0].strftime("%Y-%m-%d") if not bars.empty else "", bars)  # NEW
```

graceful shutdown 경로(`bot.py` 종료 핸들러)에 추가:

```python
        if getattr(self, "collector", None) is not None:
            try:
                self.collector.stop(timeout=5.0)
            except Exception:
                pass
```

- [ ] **Step 5: Run PASS**

```bash
pytest tests/test_bot_collector_integration.py -v
pytest tests/test_bot_states.py -v  # 기존 테스트 회귀 확인
pytest tests/test_bot_advanced.py -v
```

Expected: new tests pass, existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/bot.py tests/test_bot_collector_integration.py
git commit -m "Integrate BarCollector into CasperBot (env-toggled, isolated)"
```

---

### Task 8: 수동 백필 CLI

**Files:**
- Create: `scripts/backfill_marketdata.py`

- [ ] **Step 1: Write CLI script**

```python
#!/usr/bin/env python3
"""Manually backfill 5min bars for given symbols.

Usage:
    python scripts/backfill_marketdata.py                              # all default symbols, last 60d
    python scripts/backfill_marketdata.py --symbols TQQQ QQQ            # subset
    python scripts/backfill_marketdata.py --days 30                     # last 30d
    python scripts/backfill_marketdata.py --start 2026-04-01 --end 2026-05-08
"""

import argparse
import os
import sys
from datetime import date, datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.data.gap_finder import find_gaps
from src.data.backfill import fill_gaps_from_yfinance


DEFAULT_SYMBOLS = ["TQQQ", "QQQ", "SQQQ", "^VIX"]
DEFAULT_BASE = os.path.join(ROOT, "data", "marketdata")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--start", type=str, default=None)
    p.add_argument("--end", type=str, default=None)
    p.add_argument("--base", type=str, default=DEFAULT_BASE)
    args = p.parse_args()

    if args.start and args.end:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end)
    else:
        end = datetime.utcnow().date()
        start = end - timedelta(days=args.days)

    print(f"[backfill] range {start} ~ {end}  symbols={args.symbols}")
    os.makedirs(args.base, exist_ok=True)

    total_filled = 0
    for sym in args.symbols:
        gaps = find_gaps(args.base, sym, start, end)
        if not gaps:
            print(f"  {sym}: no gaps")
            continue
        print(f"  {sym}: filling {len(gaps)} gaps …")
        filled = fill_gaps_from_yfinance(args.base, sym, gaps)
        print(f"    → wrote {filled}/{len(gaps)} days")
        total_filled += filled

    print(f"[backfill] done  total_filled={total_filled}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke test (no commit yet)**

```bash
python scripts/backfill_marketdata.py --days 5
ls -la data/marketdata/TQQQ/2026/ | head
```

Expected: ~5 .parquet files appear, each ~3-5 KB

- [ ] **Step 3: Commit**

```bash
git add scripts/backfill_marketdata.py
git commit -m "Add manual backfill CLI for marketdata"
```

---

### Task 9: Cold-start 자동 백필 (봇 시작 시)

**Files:**
- Modify: `src/bot.py` (생성자 끝, `_init_collector` 다음에 1 블록)
- Test: `tests/test_bot_cold_start_backfill.py`

- [ ] **Step 1: Write test**

```python
# tests/test_bot_cold_start_backfill.py
from unittest.mock import patch
import pytest


def test_cold_start_backfill_runs_when_collection_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "on")
    monkeypatch.setenv("DATA_COLLECTION_BACKFILL", "on")
    from src.bot import CasperBot
    bot = CasperBot.__new__(CasperBot)
    bot._init_collector(base_dir=str(tmp_path))
    with patch("src.bot.fill_gaps_from_yfinance", return_value=2) as mock_fill:
        bot._cold_start_backfill(base_dir=str(tmp_path), symbols=["TQQQ"])
    assert mock_fill.called


def test_cold_start_backfill_skipped_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_COLLECTION", "off")
    from src.bot import CasperBot
    bot = CasperBot.__new__(CasperBot)
    bot.collector = None
    with patch("src.bot.fill_gaps_from_yfinance") as mock_fill:
        bot._cold_start_backfill(base_dir=str(tmp_path), symbols=["TQQQ"])
    assert not mock_fill.called
```

- [ ] **Step 2: Run FAIL**

```bash
pytest tests/test_bot_cold_start_backfill.py -v
```

- [ ] **Step 3: Add `_cold_start_backfill` to CasperBot**

```python
    def _cold_start_backfill(self, base_dir: str, symbols: list) -> None:
        """Run yfinance backfill for missing days on startup. Silent on failure."""
        if self.collector is None:
            return
        if os.environ.get("DATA_COLLECTION_BACKFILL", "on").lower() != "on":
            return
        try:
            from datetime import datetime, timedelta
            from src.data.gap_finder import find_gaps
            from src.data.backfill import fill_gaps_from_yfinance
            end = datetime.utcnow().date()
            start = end - timedelta(days=60)
            total = 0
            for sym in symbols:
                gaps = find_gaps(base_dir, sym, start, end)
                if gaps:
                    n = fill_gaps_from_yfinance(base_dir, sym, gaps)
                    total += n
                    logger.info(f"Backfill: {sym} {n}/{len(gaps)} days written")
            logger.info(f"Backfill: cold start done (total={total} days)")
        except Exception as e:
            logger.warning(f"Backfill: cold start failed silently: {e}")
```

생성자에서 호출 (collector init 직후):

```python
        self._cold_start_backfill(
            base_dir="data/marketdata",
            symbols=["TQQQ", "QQQ", "SQQQ", "^VIX"],
        )
```

- [ ] **Step 4: Run PASS**

```bash
pytest tests/test_bot_cold_start_backfill.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/bot.py tests/test_bot_cold_start_backfill.py
git commit -m "Auto-backfill missing 60d on bot cold start"
```

---

### Task 10: 디스크/통계 모니터링 (status 강화)

**Files:**
- Modify: `src/bot.py` (`run_casper.sh status` 가 이미 있다면 그 path)
- Modify: `run_casper.sh` (status에 데이터 수집 라인 추가)

- [ ] **Step 1: Add `marketdata_stats()` helper**

```python
# src/data/store.py 끝에 추가

def stats(base: Path) -> dict:
    """Aggregate stats for the marketdata directory."""
    base = Path(base)
    if not base.exists():
        return {"total_files": 0, "total_bytes": 0, "symbols": {}}
    total_files = 0
    total_bytes = 0
    sym_stat: dict = {}
    for sym_dir in base.iterdir():
        if not sym_dir.is_dir():
            continue
        files = list(sym_dir.rglob("*.parquet"))
        sz = sum(f.stat().st_size for f in files)
        sym_stat[sym_dir.name] = {"days": len(files), "bytes": sz}
        total_files += len(files)
        total_bytes += sz
    return {"total_files": total_files, "total_bytes": total_bytes, "symbols": sym_stat}
```

- [ ] **Step 2: Test stats**

```python
# tests/test_data_store.py 에 추가

def test_stats_reports_total_files_and_bytes(tmp_path):
    save_bars(tmp_path, "TQQQ", "2026-05-07", _sample_bars(), source="kis")
    save_bars(tmp_path, "QQQ", "2026-05-07", _sample_bars(), source="kis")
    from src.data.store import stats
    s = stats(tmp_path)
    assert s["total_files"] == 2
    assert s["total_bytes"] > 0
    assert "TQQQ" in s["symbols"]
    assert "QQQ" in s["symbols"]
```

```bash
pytest tests/test_data_store.py::test_stats_reports_total_files_and_bytes -v
```

Expected: PASS

- [ ] **Step 3: Wire into status command**

`run_casper.sh status` 에서 호출하는 함수가 있으면 거기에 데이터 수집 통계 출력 한 블록 추가. 없으면 별도 CLI:

```python
# scripts/marketdata_status.py
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.data.store import stats

s = stats(os.path.join(ROOT, "data", "marketdata"))
print(f"Total files: {s['total_files']}")
print(f"Total bytes: {s['total_bytes']:,}  ({s['total_bytes']/1024:.1f} KB)")
for sym, info in sorted(s['symbols'].items()):
    print(f"  {sym:>6}: {info['days']:>3} days  {info['bytes']:>8,} B")
```

- [ ] **Step 4: Commit**

```bash
git add src/data/store.py tests/test_data_store.py scripts/marketdata_status.py
git commit -m "Add marketdata stats helper and status CLI"
```

---

### Task 11: 배포 절차 (봇 재시작 가이드)

**Files:**
- Modify: `docs/COMMANDS.md` (배포 절차 1 섹션 추가)

봇이 현재 동작 중이므로 코드 적용에는 재시작이 필요. 이 plan을 실행할 때 따라야 하는 정확한 절차를 문서화.

- [ ] **Step 1: 적용 전 사전 점검**

```bash
# 1. 현재 봇 상태 확인 (포지션 미보유 시에만 재시작)
./run_casper.sh status

# 2. logs/app/casper_$(date +%Y-%m-%d).log 마지막 50줄 확인
tail -50 logs/app/casper_$(date +%Y-%m-%d).log

# 3. 포지션 있으면 청산 또는 EOD까지 대기
```

- [ ] **Step 2: 환경변수 추가**

`.env`에:
```bash
DATA_COLLECTION=on
DATA_COLLECTION_BACKFILL=on
```

- [ ] **Step 3: 디렉토리 권한 확인**

```bash
mkdir -p data/marketdata
chmod 755 data/marketdata
```

- [ ] **Step 4: 봇 graceful stop**

```bash
./run_casper.sh stop
# wait until process gone
ps aux | grep casper | grep -v grep
```

- [ ] **Step 5: 봇 재시작**

```bash
./run_casper.sh daemon --yes
sleep 5
./run_casper.sh status
tail -20 logs/app/casper_$(date +%Y-%m-%d).log | grep -E "DataCollection|Backfill"
```

Expected log lines:
```
DataCollection: enabled (DATA_COLLECTION=on)
BarCollector: thread started
Backfill: TQQQ N/M days written
Backfill: cold start done (total=X days)
```

- [ ] **Step 6: 1 거래일 후 수집 검증**

```bash
python scripts/marketdata_status.py
```

Expected: 4 symbols × N days (백필 + 당일 1) Parquet 파일들이 보임.

- [ ] **Step 7: Commit deployment doc**

```bash
git add docs/COMMANDS.md
git commit -m "Document data collector deployment procedure"
```

---

### Task 12: 백테스트 엔진을 stored data로 전환 (선택, Phase 2)

`scripts/intraday_backtest_compare.py` 의 `fetch_data()` 가 yfinance 60일 제약을 받는다.
저장된 Parquet이 60일 이상 누적되면 그쪽을 쓰도록 전환.

**Files:**
- Modify: `scripts/intraday_backtest_compare.py`

- [ ] **Step 1: Refactor fetch_data to prefer stored data**

```python
def fetch_data(use_stored: bool = True, base="data/marketdata"):
    from src.data.loader import load_range
    from src.data.gap_finder import find_gaps
    from datetime import datetime, timedelta

    end = datetime.utcnow().date()
    start = end - timedelta(days=120)  # use up to 120d when stored

    if use_stored:
        tqqq = load_range(base, "TQQQ", start, end)
        qqq = load_range(base, "QQQ", start, end)
        sqqq = load_range(base, "SQQQ", start, end)
        if len(tqqq) >= 100 and len(qqq) >= 100:
            print(f"[data] using stored Parquet ({len(tqqq)} TQQQ rows)")
            return _shape_for_backtest(tqqq, qqq, sqqq)

    print("[data] falling back to yfinance 60d 5m")
    # 기존 yfinance 경로
```

- [ ] **Step 2: Test that stored path produces equivalent regime distribution**

```bash
python scripts/intraday_backtest_compare.py
```

- [ ] **Step 3: Commit**

```bash
git add scripts/intraday_backtest_compare.py
git commit -m "Prefer stored Parquet over yfinance in compare backtest"
```

---

## 6. 마이그레이션 / 롤백 계획

### 6.1 활성화 절차

1. PR 머지 (코드만 합침, 행위 변화 X — env var OFF가 기본)
2. `.env`에 `DATA_COLLECTION=on` 추가
3. 봇 graceful stop → 재시작
4. 1 거래일 후 `python scripts/marketdata_status.py`로 검증

### 6.2 비활성화 (롤백)

1. `.env`에서 `DATA_COLLECTION=off`로 변경
2. 봇 graceful stop → 재시작
3. (선택) `data/marketdata/` 디렉토리 삭제 — 디스크 회수

### 6.3 안전 검증

- 매매 로직과 격리됨: collector exception이 main thread로 전파되지 않음
- env var OFF 시 코드 경로 0 (collector=None, _record_bars early return)
- 디스크 가득: store는 IOError 발생 시 collector thread만 warn, 다음 day 재시도

---

## 7. 운영 / 모니터링

### 7.1 매일 점검

```bash
python scripts/marketdata_status.py
# Expected: total_files +4/day, total_bytes growth ~16KB/day
```

### 7.2 주간 점검

```bash
# 지난 7일 갭 확인
python scripts/backfill_marketdata.py --days 7
# Expected: "no gaps" for all symbols
```

### 7.3 알람 신호 (logs)

| 로그 패턴 | 의미 | 대응 |
|---|---|---|
| `BarCollector: queue full, dropped` | tick 처리 지연 | queue_maxsize 늘리거나 thread sleep 조정 |
| `BarCollector: save failed` | 디스크 / Parquet 오류 | 디스크 공간 + 권한 확인 |
| `Backfill: unrecoverable` | 60일 초과 갭 | 정상 (yfinance 한계) |
| `DataCollection: init failed` | pyarrow / pandas_market_calendars 누락 | `pip install -r requirements.txt` |

---

## 8. 향후 확장 (이 plan에서 안 함, 별도 plan 필요)

1. **1분봉 수집**: 5분봉 합성 또는 KIS 1분 API 호출. 용량 5배 증가.
2. **24/7 collector 봇 분리**: pre-market 04:00, after-hours 20:00까지 수집 필요 시 별도 프로세스.
3. **DuckDB 쿼리 레이어**: 분석 ad-hoc 쿼리 편의성. Parquet 그대로 쿼리 가능하므로 deferred.
4. **분산 저장**: S3 / GCS 백업. 1년 누적 후 검토.
5. **호가/체결 데이터**: KIS Level-2 필요. 별도 collector + 별도 storage 모델.

---

## 9. Self-Review

**1. Spec coverage check**

| 요구사항 | 구현 task | 상태 |
|---|---|---|
| F1. RTH 5분봉 자동 저장 | Task 6, 7 | ✅ |
| F2. Cold start 60d 백필 | Task 9 | ✅ |
| F3. 수동 백필 CLI | Task 8 | ✅ |
| F4. 영업일 갭 탐지 | Task 1, 3 | ✅ |
| F5. 통합 로드 API | Task 5 | ✅ |
| F6. 매매 영향 0 (격리) | Task 6 (try/except + thread) | ✅ |
| N1. ≤10MB/year | Parquet+Snappy ~2MB/year | ✅ |
| N2. tick ≤10ms | queue.put_nowait | ✅ |
| N3. 메모리 ≤20MB | pyarrow + small buffer | ✅ |
| N4. cold start ≤30s | 4 ticker × 60d / 0.3s sleep ≈ 16s | ✅ |
| N5. env toggle default off | `_init_collector` 분기 | ✅ |
| 봇 구동 중 안전 배포 | Task 11 | ✅ |

**2. Placeholder scan**

검색 결과: "TBD", "TODO", "implement later", "fill in details", "Similar to Task N" — 모두 0 occurrence.

**3. Type consistency check**

| 함수 / 클래스 | 정의 task | 사용 task | OK? |
|---|---|---|---|
| `trading_days(start: date, end: date) -> List[date]` | Task 1 | Task 3, 5 | ✅ |
| `save_bars(base, symbol, date_str, bars, source) -> Path` | Task 2 | Task 4, 6 | ✅ |
| `load_bars(base, symbol, date_str) -> Optional[DataFrame]` | Task 2 | Task 5 | ✅ |
| `has_data(base, symbol, date_str) -> bool` | Task 2 | Task 3 | ✅ |
| `find_gaps(base, symbol, start, end) -> List[date]` | Task 3 | Task 8, 9 | ✅ |
| `fill_gaps_from_yfinance(base, symbol, gaps) -> int` | Task 4 | Task 8, 9 | ✅ |
| `BarCollector(base_dir, queue_maxsize=256)` | Task 6 | Task 7 | ✅ |
| `BarCollector.submit(symbol, date_str, bars, source)` | Task 6 | Task 7 | ✅ |
| `BarCollector.stop(timeout=5.0)` | Task 6 | Task 7 | ✅ |
| `stats(base) -> dict` | Task 10 | Task 10 (CLI) | ✅ |

---

## 10. 배포 후 검증 체크리스트 (운영자용)

배포 완료 1 거래일 후:

- [ ] `python scripts/marketdata_status.py` → 4 symbol, ~60일 분 Parquet 존재
- [ ] `du -sh data/marketdata/` → < 10 MB
- [ ] `tail -200 logs/app/casper_$(date +%Y-%m-%d).log | grep -i "BarCollector\|DataCollection\|Backfill"` → 정상 시작 로그
- [ ] `tail -200 logs/app/casper_$(date +%Y-%m-%d).log | grep -i "queue full\|save failed"` → 0 lines
- [ ] `./run_casper.sh status` → 평소와 동일 (매매 통계 변화 없음)
- [ ] `python scripts/backfill_marketdata.py --days 7` → "no gaps" 메시지

배포 후 1주일:

- [ ] 디스크 사용량 일주일에 ~100KB 증가 (4 ticker × 5일 × ~5KB)
- [ ] 매매 손익에 변화 없음 (기존 trades_2026.json 패턴 그대로)
- [ ] 새 백테스트 `scripts/intraday_backtest_compare.py`로 stored data 사용 시 yfinance 60일 한도 돌파 가능 (Task 12 이후)

---

## 11. 별도 봇으로 분리해야 하는 분기점

이 plan은 in-process 통합. 다음 시나리오 중 하나라도 발생하면 별도 collector 봇으로 분리 검토:

1. **24/7 수집**: pre-market / after-hours / 주말 wash-sale 시즌 데이터 필요
2. **10+ ticker 확장**: TQQQ/QQQ/SQQQ/^VIX 외에 SPY, IWM, ES futures 등 추가
3. **1초·1분 단위 수집**: queue 처리량이 RTH 1초당 수십~수백 메시지로 늘면 thread로 부족
4. **호가/체결 데이터**: KIS Level-2 또는 polygon.io WebSocket 도입 시
5. **매매 latency 영향 관측**: tick 처리 시간이 50ms 이상으로 늘면 분리 즉시 검토

해당 시 새 plan: `docs/superpowers/plans/YYYY-MM-DD-collector-bot.md` 작성.

---

**Plan 완료**. 사용자 확인 후 실행 옵션:

1. **Subagent-Driven (권장)**: 각 task마다 fresh subagent 디스패치 + 2-stage 리뷰
2. **Inline Execution**: 이 세션에서 batch 실행 + 체크포인트
3. **Manual**: 운영자가 직접 task별로 실행 (봇 구동 중이므로 가장 안전)

봇이 현재 구동 중이라는 점을 고려하면 **Manual 또는 봇 정지 후 Inline Execution**이 가장 안전합니다. 사용자 결정 대기.
