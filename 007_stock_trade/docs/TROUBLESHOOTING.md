# 007_stock_trade 트러블슈팅

각 항목은 6필드(증상/원인/해결/복구절차/관련 사고/재발 감지) + Claude 진단 미스 기록 구조를 따른다.

---

## API Rate Limit (EGW00201)

- **증상**: KIS API가 `초당 거래건수를 초과하였습니다` (EGW00201) 반환.
- **원인**: 모드별 KIS API 제한 초과:

  | 모드 | API 제한 | 적용 딜레이 | 초당 호출 |
  |------|----------|-------------|----------|
  | 모의투자 | 5건/초 | 500ms | ~2건 |
  | 실전투자 | 20건/초 | 100ms | ~10건 |

- **해결**: `src/quant_modules/order_executor.py`의 `API_DELAY_VIRTUAL`, `API_DELAY_REAL` 상수로 자동 조절.
- **복구 절차**: rate limit 발생 시 자동 backoff. 지속 시 `time.sleep(5)` 후 재호출.
- **관련 사고**: 2026-01 (초기 모드별 분기 미반영 → 모의투자에서 빈발)
- **재발 감지**: `EGW00201` 로그 빈도. 일일 0건이 정상.

---

## pykrx 유니버스 0개 (Python 3.14 호환성)

- **증상**: `유니버스: 0개`, `KeyError`, `pykrx 유니버스 구성 실패: index -1 is out of bounds`. 30개에 머묾.
- **원인**: pykrx 1.2.x가 Python 3.14와 호환 안 됨. KRX 스크래핑이 빈 데이터 반환.
- **해결**: 2026-03-26에 네이버 금융 기반 유니버스 조회로 교체 (`_build_universe_from_naver`). 네이버 접근 불가 시 KIS API 30개 fallback.
- **복구 절차**: pykrx 업그레이드(`pip install pykrx>=1.2.3`) 또는 Python 3.13으로 다운그레이드.
- **관련 사고**: 2026-03-26 (007-pykrx-python314-incompat)
- **재발 감지**: 시작 시 `유니버스: <30개 미만` 경고.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: KRX 일시 장애 또는 네트워크 문제
- **실제 원인**: Python 3.14 + pykrx 1.2.x 비호환. 같은 코드가 Python 3.13에서는 정상.
- **방향 전환 지점**: 사용자가 Python 버전 차이 확인 요청
- **교훈**:
  - 첫 의심 영역: **Python interpreter 버전 vs 라이브러리 호환성 매트릭스**
  - 빨리 배제할 가설: "KRX 서버 장애" — 다른 도구로 같은 데이터 조회되면 외부 서비스 문제 아님
  - 핵심 진단 명령: `python --version && pip show pykrx | grep Version`

---

## 텔레그램 네트워크 에러 (httpx.ConnectError)

- **증상**: `httpx.ConnectError`, polling 실패.
- **원인**: 네트워크 연결 문제 (토큰 충돌 아님).
- **해결**: 자동 복구 — 최대 10회 재시도 + 스레드 자동 재시작.
- **복구 절차**: 자동. 1시간 이상 지속 시 네트워크/방화벽 점검.
- **관련 사고**: 정기적 (Mac sleep 복귀, 네트워크 전환 시)
- **재발 감지**: 일일 `httpx.ConnectError` 빈도. 5회 미만이 정상.

---

## 텔레그램 Conflict 409

- **증상**: `terminated by other getUpdates request`.
- **원인**: 이전 봇 세션 미종료 상태에서 새 세션 시작.
- **해결**: 자동 복구 — Conflict 감지 시 `10 + 5n`초 지수 딜레이 후 재시도.
- **복구 절차**: `run_quant.sh daemon`은 SIGTERM graceful shutdown + `drop_pending_updates=True` 보장. 직접 kill -9 사용 시 수동으로 `pkill -f telegram` 후 재시작.
- **관련 사고**: 2026-01-17 (telegram-409-conflict)
- **재발 감지**: 시작 후 60s 내 Conflict 발생.

---

## 총자산 과대 표시 (T+2 결제 미반영)

- **증상**: 매수 발생일 총자산/수익률 비정상적으로 부풀림.
- **원인**: `cash(dnca_tot_amt)` + `scts_evlu` 계산 시 T+2 결제 미반영. 매수 시 `scts_evlu`에는 즉시 반영되지만 `dnca_tot_amt`에서는 차감 안 됨 → 이중 계산.
- **해결**: `nass_amt`(순자산) 사용. `parse_balance()` 통합:

  ```python
  from src.utils.balance_helpers import parse_balance
  bs = parse_balance(balance)
  total_assets = bs.total_assets  # nass 우선, fallback: scts_evlu + cash
  cash = bs.cash                  # total_assets - scts_evlu (역산)
  ```

- **복구 절차**: 코드 패치 후 5곳 통일 — daily snapshot, 리포트, 텔레그램 명령, 백테스트 비교, 월간 트래커.
- **관련 사고**: 2026-02-20 (t2-settlement-double-count)
- **재발 감지**: 일일 `total_assets` 변화율이 매수액의 2배에 근접하면 의심.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: 시세 조회 시점 문제 또는 환율 변동
- **실제 원인**: `cash + scts_evlu` 공식 자체가 결제 전 예수금을 이중 계산. KIS는 매수 즉시 cash 차감을 안 하므로 단순 합산은 항상 부풀림.
- **방향 전환 지점**: 사용자가 "KIS는 nass_amt를 쓰는 이유가 있어" 지적
- **교훈**:
  - 첫 의심 영역: **회계 공식 자체** (broker 계약상 정확한 잔고 정의)
  - 빨리 배제할 가설: "시세 caching", "환율 lag" — 자산 부풀림이 매수액에 비례하면 회계 문제
  - 핵심 진단 명령: `nass_amt vs (cash + scts_evlu)` 비교 — 차이가 매수액과 같으면 T+2 미반영

---

## 긴급 리밸런싱 무한 반복

- **증상**: 매일 08:30에 "긴급 리밸런싱 트리거" 반복.
- **원인**: 긴급 리밸런싱이 월초 중복 방지 로직(`last_rebalance_month`)을 우회. 별도 추적 변수 부재.
- **해결**: `last_urgent_rebalance_month`로 별도 추적, 월 1회 제한.

  | 유형 | 추적 변수 | 제한 |
  |------|----------|------|
  | 월초 리밸런싱 | `last_rebalance_month` | 월 1회 |
  | 긴급 리밸런싱 | `last_urgent_rebalance_month` | 월 1회 |

- **복구 절차**: 코드 패치 + `engine_state.json` 수동 reset (이미 트리거된 월 표시).
- **관련 사고**: 2026-01-27 (urgent-rebalance-infinite-loop)
- **재발 감지**: 일일 리밸런싱 트리거 횟수. 월 1회 미만이 정상.

---

## 휴장일 오판단

- **증상**: 평일인데 휴장일로 판단하여 봇 미동작.
- **원인**: pykrx가 자정에 당일 거래 데이터 조회 시 데이터 없음 → 휴장으로 잘못 판단.
- **해결**: 판단 우선순위 변경:
  1. 주말(토/일) → 휴장
  2. `KNOWN_HOLIDAYS` 하드코딩 → 휴장
  3. 오늘/미래 → 평일이면 거래일로 가정 (보수적)
  4. 과거 → pykrx 실제 확인
- **복구 절차**: 휴장일로 잘못 판단된 날은 다음날 자동 복구. 즉시 강제 실행 필요 시 `/run_screening`.
- **관련 사고**: 정기적 (자정 ~ 09:00 사이 시작 시)
- **재발 감지**: 평일 09:00에 `holiday=True` 로그.

참고: KIS 휴장일조회(CTCA0903R)는 실전투자에서만 지원.

---

## engine_state ↔ KIS 포지션 불일치

- **증상**: `engine_state.json`의 포지션 수가 실제 KIS 잔고와 다름. 모니터링 누락, 리밸런싱 시 이미 보유 종목 중복 매수.
- **원인**: 데몬 재시작 시 상태 유실, 또는 이전 리밸런싱에서 기존 포지션 미반영.
- **해결**: `sync_positions_from_kis()` 3-way 동기화 (2026-02-24).

  자동 동기화 시점:
  1. 엔진 시작 시 (`start()`)
  2. 리밸런싱 전 (`generate_rebalance_orders()`)
  3. 주간 점검 (토요일 10:00, 불일치 감지 시)

- **복구 절차**: 텔레그램 `/sync_positions` 또는 `/reconcile`. 자동 복구가 우선.
- **관련 사고**: 2026-02-24 (engine-state-position-desync)
- **재발 감지**: 매 동기화 시 KIS 보유 종목 수 vs `engine_state.positions` 길이 차이 로그.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: KIS API 일시 장애로 잔고 조회 부정확
- **실제 원인**: 데몬 재시작 시 상태 파일은 보존되지만 외부(KIS) 변화 미반영. 단방향 신뢰 → 불일치 누적.
- **방향 전환 지점**: 사용자가 "재시작 후 차이가 점점 커진다" 지적
- **교훈**:
  - 첫 의심 영역: **상태 동기화 트리거 시점** (시작·리밸런싱·주간)
  - 빨리 배제할 가설: "KIS API 부정확" — KIS는 broker 측 truth, 우리 state가 stale
  - 핵심 진단 명령: 3-way diff (engine_state vs KIS holdings vs 주문 history)

---

## 긴급 정지 해제

- **증상**: `EMERGENCY_STOP` 상태에서 거래 차단.
- **원인**: `/emergency_stop` 호출 또는 안전장치 자동 발동.
- **해결**:

  ```
  /clear_emergency
  /start_trading
  ```

- **복구 절차**: 위 두 명령 순차 실행. 발동 원인 점검 후 진행.
- **관련 사고**: 사용자 운영
- **재발 감지**: `EMERGENCY_STOP` 진입 사유 로그.

---

## pykrx 스크리닝 실패 (1.0.x)

- **증상**: `유니버스: 0개`, `KeyError`.
- **원인**: KRX 웹사이트 API 응답 형식 변경 → pykrx 1.0.x 호환성 문제.
- **해결**: `pip install pykrx>=1.2.3`.
- **복구 절차**:
  1. KIS API로 시가총액 상위 30개 조회 (자동)
  2. pykrx로 KOSPI200 확장 시도
  3. 실패 시 → KIS 30개로 진행
- **관련 사고**: 2025년 말 (KRX 응답 변경)
- **재발 감지**: pykrx 버전 < 1.2.3 + universe < 100 동시 발생.
