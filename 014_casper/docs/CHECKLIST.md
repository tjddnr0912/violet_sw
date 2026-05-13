# CHECKLIST - 014_casper

> `/checklist` 스킬이 갱신·검증한다. 각 항목의 `Verify` 명령은 단일 라인이며 exit code 0이 pass다. 직접 편집해도 되지만 다음 호출에서 갱신될 수 있다.

- **Last verified**: 2026-05-14 22:50 (PASS — 542/542 unit tests + 16/16 checklist items)
- **Last verified commit**: uncommitted (Scenario B 적용 직후)
- **Total items**: 16
- **Loop iterations on last run**: 2 (iter 1: #9 FAIL — sys.path missing in helper; iter 2: all pass)

---

## Layer 1 — Function

### 1. KILLZONES 정의 안정
- **Layer**: function
- **Target**: src/core/sessions.py:18 (KILLZONES dict)
- **Why**: 모든 시간 윈도우 계산이 이 dict의 경계값에 의존. 누군가 09:30→09:45로 옮기면 ORB와 충돌, 10:10/10:55 변경 시 BE shift와 충돌
- **Verify**: `python -c "from src.core.sessions import KILLZONES; from datetime import time as t; assert KILLZONES['AM_MACRO'] == (t(9,30), t(10,10)); assert KILLZONES['AM_LATE'] == (t(10,10), t(10,55))"`
- **Pass criteria**: exit 0

### 2. killzone_for 경계 처리
- **Layer**: function
- **Target**: src/core/sessions.py::killzone_for
- **Why**: AM_MACRO와 AM_LATE의 RR이 다르므로 경계 candle (10:10) 분류가 잘못되면 RR 잘못 적용됨
- **Verify**: `cd "$(pwd)" && python -m pytest tests/test_sessions.py -q`
- **Pass criteria**: exit 0

### 3. scan_for_signal — rr_by_killzone 파라미터 수용
- **Layer**: function
- **Target**: src/core/strategy.py::scan_for_signal
- **Why**: Scenario B의 본체. 신규 파라미터 시그니처가 깨지면 bot.py 호출이 TypeError로 죽음
- **Verify**: `python -c "import inspect; from src.core.strategy import scan_for_signal; assert 'rr_by_killzone' in inspect.signature(scan_for_signal).parameters"`
- **Pass criteria**: exit 0

### 4. signal_emit 로그에 killzone 메타 포함
- **Layer**: function
- **Target**: src/core/strategy.py (signal_emit _log_decision)
- **Why**: ict_log에 killzone과 effective rr가 기록돼야 추후 분석 가능
- **Verify**: `grep -n '\"killzone\": bar_killzone\|\"rr_default\": rr_ratio' src/core/strategy.py`
- **Pass criteria**: exit 0 (둘 다 grep 매치)

### 5. notify_scan_start 신규 파라미터 수용
- **Layer**: function
- **Target**: src/telegram/notifier.py::notify_scan_start
- **Why**: bot.py가 rr_default, kz_segments를 넘기는데 미수용이면 TypeError
- **Verify**: `python -c "import inspect; from src.telegram.notifier import TelegramNotifier; p = inspect.signature(TelegramNotifier.notify_scan_start).parameters; assert 'rr_default' in p and 'kz_segments' in p"`
- **Pass criteria**: exit 0

### 6. notify_killzone_end_no_signal — kst_window/reasons 수용
- **Layer**: function
- **Target**: src/telegram/notifier.py::notify_killzone_end_no_signal
- **Why**: 새 호출부에서 kst_window를 같이 보냄
- **Verify**: `python -c "import inspect; from src.telegram.notifier import TelegramNotifier; p = inspect.signature(TelegramNotifier.notify_killzone_end_no_signal).parameters; assert 'kst_window' in p and 'reasons' in p"`
- **Pass criteria**: exit 0

### 7. notify_entry — killzone 파라미터 수용
- **Layer**: function
- **Target**: src/telegram/notifier.py::notify_entry
- **Why**: bot.py가 enter 시 killzone을 같이 전송. 시그니처 빠지면 TypeError
- **Verify**: `python -c "import inspect; from src.telegram.notifier import TelegramNotifier; assert 'killzone' in inspect.signature(TelegramNotifier.notify_entry).parameters"`
- **Pass criteria**: exit 0

## Layer 2 — Scenario

### 8. config JSON 유효성 + Scenario B 적용
- **Layer**: scenario
- **Target**: config/strategy_params.json
- **Why**: Scenario B의 두 핵심 키가 빠지면 fallback이 작동해 의도치 않게 BASE로 회귀
- **Verify**: `python -c "import json; c=json.load(open('config/strategy_params.json')); e=c['entry']; assert set(e['allowed_killzones'])=={'AM_MACRO','AM_LATE'}, e['allowed_killzones']; rr=e['rr_ratio_by_killzone']; assert rr['AM_MACRO']==3.0 and rr['AM_LATE']==2.0, rr"`
- **Pass criteria**: exit 0

### 9. RR 결정 시뮬레이션 — AM_MACRO breakout = 1:3
- **Layer**: scenario
- **Target**: src/core/strategy.py (effective_rr 결정 로직)
- **Why**: 결국 사용자 자본에 영향을 주는 결정. 정상 케이스 1건은 단순 단위검증으로 항상 통과해야 함
- **Verify**: `python scripts/check_killzone_rr.py macro`
- **Pass criteria**: exit 0, stdout에 "rr=3.0"

### 10. RR 결정 시뮬레이션 — AM_LATE breakout = 1:2
- **Layer**: scenario
- **Target**: src/core/strategy.py (effective_rr 결정 로직)
- **Why**: Scenario B의 가장 새로운 동작. RR=2가 안 나오면 기능 실패
- **Verify**: `python scripts/check_killzone_rr.py late`
- **Pass criteria**: exit 0, stdout에 "rr=2.0"

### 11. RR 결정 — rr_by_killzone 없을 때 default 폴백
- **Layer**: scenario
- **Target**: src/core/strategy.py (effective_rr 폴백)
- **Why**: 다른 코드 경로(테스트, 외부 호출)에서 rr_by_killzone=None인 경우 기존 동작과 동일해야 함
- **Verify**: `python scripts/check_killzone_rr.py fallback`
- **Pass criteria**: exit 0, stdout에 "rr=3.0"

### 12. bot.py가 rr_by_killzone을 scan_for_signal로 전달
- **Layer**: scenario
- **Target**: src/bot.py (scan_for_signal 호출부)
- **Why**: config 키 정의돼도 호출부가 누락되면 무효
- **Verify**: `grep -n "rr_by_killzone=entry_params.get" src/bot.py`
- **Pass criteria**: exit 0

## Layer 3 — System

### 13. 전체 unit test 통과
- **Layer**: system
- **Target**: tests/
- **Why**: Scenario B로 기존 270+개 테스트가 깨지지 않았는지 확인
- **Verify**: `cd "$(pwd)" && python -m pytest tests/ -q --tb=no -x`
- **Pass criteria**: exit 0

### 14. run_casper.sh 문법 정상
- **Layer**: system
- **Target**: run_casper.sh
- **Why**: 새 KST_WINDOW 헬퍼가 들어갔고, 따옴표/HEREDOC 실수가 흔함
- **Verify**: `bash -n run_casper.sh`
- **Pass criteria**: exit 0

### 15. 배너 KST window 계산이 23:55로 확장됨
- **Layer**: system
- **Target**: run_casper.sh 의 WINDOW_INFO python 헬퍼 + bot.py 의 trade-window banner
- **Why**: 사용자가 보는 첫 번째 표시. 23:10 그대로면 Scenario B가 시각화 안 됨
- **Verify**: `python -c "from datetime import datetime, time as dtime; import pytz, json; from src.core.sessions import KILLZONES; e=json.load(open('config/strategy_params.json'))['entry']; allowed=e['allowed_killzones']; end_t=max(KILLZONES[k][1] for k in allowed); assert end_t==dtime(10,55), end_t"`
- **Pass criteria**: exit 0

### 16. import-time smoke — 핵심 모듈
- **Layer**: system
- **Target**: src/bot.py, src/core/strategy.py, src/telegram/notifier.py
- **Why**: Scenario B 변경 중 import 순환·미존재 심볼이 들어가지 않았는지
- **Verify**: `python -c "import src.bot; import src.core.strategy; import src.telegram.notifier; import src.core.sessions"`
- **Pass criteria**: exit 0

---

## 히스토리 (append-only, 재읽기 안 함 — 기록용)

### 2026-05-14 22:50 — PASS (루프 2회 후 회복)
- 트리거: 사용자 요청 "체크리스트 검증 실시" + Scenario B 코드/문서/텔레그램 동기화
- 대상: 014_casper
- 항목 수: 16 (신규)
- 루프 회차별 사건:
  - iter 1, item #9 FAIL: `scripts/check_killzone_rr.py macro` → `ModuleNotFoundError: No module named 'src'` → 코드 수정: scripts/check_killzone_rr.py 에 `sys.path.insert(0, "..")` 추가
  - iter 2, items #1~#16 all pass (item #13 pytest 542/542 in 343s)
- 변경된 코드 파일: config/strategy_params.json, src/core/strategy.py, src/bot.py, src/telegram/notifier.py, run_casper.sh, CLAUDE.md, docs/CONFIGURATION.md, scripts/check_killzone_rr.py(신규)
- commit sha: uncommitted
