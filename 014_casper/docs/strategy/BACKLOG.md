# 전략 업그레이드 Backlog

> 정량/정성 평가까지 마쳤지만 *이번 사이클에서는 도입 보류*한 후보들. 트리거 조건이 충족되면 재검토. 채택·기각 모두 사후에 이 파일에 결과 기록.

---

## 5m ORB 옵션 (보류 — 2026-05-15)

### 후보 설명
ORB 길이를 현재 15분(09:30~09:44)에서 5분(09:30~09:34)으로 단축하는 A/B 옵션. config 토글로 즉시 ON/OFF 가능.

상세: [UPGRADE_REVIEW.md §2](UPGRADE_REVIEW.md#2-5m-orb-옵션)

### 60일 백테스트 결과 (이번 사이클)

| | 15m (현재) | 5m | 30m |
|---|---|---|---|
| 매매 빈도 | 3건 | **6건 (2배)** | 2건 |
| WR | 0% | 16.7% | 0% |
| PF | 0.00 | 0.83 | 0.00 |
| Net Ret | -0.01% | **-0.35%** | -0.01% |

### 보류 이유
- 60일에서 매매 빈도는 2배지만 **Net Return은 악화** (-0.35%, commission 누적)
- WR 16.7%는 표본 6건 기준 통계 의미 약함
- Partial TP 도입 직후라 변화 영향 분리 어려움 — 한 번에 한 가지 변경 원칙
- ICT decision log의 borderline displacement 데이터가 1~3개월 누적되면 재검토 가능

### 재검토 트리거 조건 (이 중 하나 충족 시)
1. Partial TP 라이브 운용 1~2개월 후 안정화 확인됨
2. 현재 15m ORB 설정으로 라이브 매매 표본 ≥ 10건 누적 (PRECHECK 가설 재검증 가능 시점)
3. yfinance·KIS 데이터 ≥ 6개월 누적되어 더 긴 백테스트 가능
4. AM_MACRO 진입 빈도가 너무 낮아 표본 누적이 정체 (월 2건 이하)

### 채택 시 작업 (참조용)
- `config/strategy_params.json::orb.minutes` (default 15) — 5/15/30 중 선택
- `src/utils/time_utils.py::is_orb_forming`, `is_scan_window` — minutes 파라미터화
- `src/core/orb.py::calculate_orb` — end_time을 minutes에서 derive
- `src/bot.py` — `_handle_orb_forming` 시간 분기 minutes 사용
- `run_casper.sh` 시작 배너 — orb_minutes 표시
- Telegram bot_started 메시지에 ORB length 명시
- tests/test_orb.py — 5min·30min 케이스 추가
- 예상 변경 라인: ~30~50 lines

### 보류 결정 일자
**2026-05-15** — Partial TP 도입과 분리하기 위해. 위 트리거 충족 후 재평가.

---

## 추후 추가될 후보들

이 섹션은 새 보류 항목이 생길 때 위쪽에 timestamped로 prepend.

### 결정 일자: TBD
(없음 — 첫 번째 backlog entry는 5m ORB)

---

## 채택·기각 이력

이 파일에서 보류 항목이 채택되면 → 본 섹션으로 이동하고 commit 메시지 + 백테스트 결과 첨부.
기각 시도 → 영구 archive 결정 사유.

(아직 없음)
