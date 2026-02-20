# CLAUDE.md - 퀀트 자동매매 시스템

KIS Open API 기반 멀티팩터 퀀트 자동매매 시스템.

## 핵심 정보

| 항목 | 값 |
|------|-----|
| 전략 | 모멘텀(20%) + 단기모멘텀(10%) + 저변동성(50%) |
| 유니버스 | KOSPI200 |
| 목표 종목 | 15개 |
| 손절/익절 | -7% / +10% |

## 실행

```bash
./run_quant.sh daemon          # 통합 데몬 (권장)
./run_quant.sh screen          # 스크리닝만
./run_quant.sh backtest        # 백테스트
```

## 프로젝트 구조

```
src/
├── quant_engine.py              # 자동매매 엔진 오케스트레이션 (~980줄)
├── quant_modules/               # 퀀트 엔진 모듈
│   ├── state_manager.py         # 상태 저장/로드, Lock 관리
│   ├── order_executor.py        # 주문 생성/실행/재시도
│   ├── position_monitor.py      # 포지션 모니터링 (손절/익절) (2026-02)
│   ├── schedule_handler.py      # 스케줄 이벤트 핸들러 (2026-02)
│   ├── report_generator.py      # 일일/월간 리포트 생성 (2026-02)
│   ├── tracker_base.py          # 트래커 공통 JSON 로드/세이브 (2026-02)
│   ├── monthly_tracker.py       # 월간 포트폴리오 트래킹
│   └── daily_tracker.py         # 일별 자산 추적 및 거래 일지 (2026-02)
├── api/
│   ├── kis_client.py            # KIS API 클라이언트
│   └── kis_quant.py             # 퀀트용 API 확장
├── core/system_controller.py    # 원격 제어 (싱글톤)
├── scheduler/auto_manager.py    # 월간 모니터링, 반기 최적화
├── telegram/
│   ├── bot.py                   # 텔레그램 봇 엔트리 (~330줄)
│   ├── commands/                # 명령어 Mixin 모듈 (2026-02)
│   │   ├── _base.py             # 공통 유틸 (에러 핸들링 데코레이터 등)
│   │   ├── query_commands.py    # 조회 명령어 (balance, positions 등)
│   │   ├── control_commands.py  # 제어 명령어 (start/stop/pause 등)
│   │   ├── action_commands.py   # 실행 명령어 (rebalance, reconcile 등)
│   │   ├── setting_commands.py  # 설정 명령어 (set_dryrun 등)
│   │   └── analysis_commands.py # 분석 명령어 (screening, signal 등)
│   ├── notifier.py              # 알림 전송 전담
│   └── validators.py            # 입력 검증 유틸리티
├── strategy/quant/              # 팩터, 스크리너, 리스크
└── utils/
    ├── balance_helpers.py       # 잔고 계산 헬퍼 (parse_balance) (2026-02)
    ├── converters.py            # 타입 변환, 포맷팅
    ├── error_formatter.py       # 사용자 친화적 에러 메시지 (2026-02)
    ├── retry.py                 # 재시도 데코레이터/설정
    └── market_calendar.py       # 휴장일 판단
scripts/run_daemon.py            # 통합 데몬
config/
├── optimal_weights.json         # 팩터 가중치
└── system_config.json           # 시스템 설정
data/quant/
├── daily_history.json           # 일별 자산 스냅샷 (2026-02)
└── transaction_journal.json     # 전체 거래 일지 (2026-02)
```

## 텔레그램 명령어

### 제어
| 명령어 | 설명 |
|--------|------|
| `/start_trading` | 시작 |
| `/stop_trading` | 중지 |
| `/emergency_stop` | 긴급정지 |
| `/run_screening` | 스크리닝 실행 |
| `/run_rebalance` | 리밸런싱 실행 |
| `/reconcile` | 장부 점검 (KIS 실잔고 대조) |

### 조회/설정
| 명령어 | 설명 |
|--------|------|
| `/status` | 상태 확인 |
| `/positions` | 보유 종목 |
| `/orders [N]` | 체결 내역 (기본 당일, 최대 90일) |
| `/history [N]` | 일별 자산 변동 (기본 7일) |
| `/trades [N]` | 거래 내역 (기본 7일) |
| `/capital` | 초기 투자금 대비 현황 |
| `/set_target N` | 목표 종목 수 |
| `/set_dryrun on\|off` | Dry-run 모드 |

## 일일 스케줄

| 시간 | 동작 |
|------|------|
| 08:30 | 장 전 스크리닝 (리밸런싱 일) |
| 09:00 | 주문 실행 → 거래 즉시 기록 (transaction_journal.json) |
| 5분마다 | 포지션 모니터링 |
| 15:20 | 일일 리포트 + 일별 스냅샷 저장 (daily_history.json) |
| 토요일 10:00 | 주간 장부 점검 (KIS 실잔고 대조, 편차 시 보정) |

## 환경 변수 (.env)

```
KIS_APP_KEY=xxx
KIS_APP_SECRET=xxx
KIS_ACCOUNT_NO=12345678-01
TRADING_MODE=VIRTUAL
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
```

## 설정 파일

### config/system_config.json
텔레그램 명령으로 변경한 설정 저장. 데몬 재시작 후에도 유지.

### config/optimal_weights.json
팩터 가중치. 반기 최적화 시 자동 업데이트.

## 트러블슈팅

### API Rate Limit (EGW00201)
- 증상: `초당 거래건수를 초과하였습니다`
- 원인: API 호출이 너무 빠름

**한국투자증권 API 호출 제한:**
| 모드 | API 제한 | 적용 딜레이 | 초당 호출 |
|------|----------|-------------|----------|
| 모의투자 | 5건/초 | 500ms | ~2건 |
| 실전투자 | 20건/초 | 100ms | ~10건 |

**관련 코드:**
- `src/quant_modules/order_executor.py`: `API_DELAY_VIRTUAL`, `API_DELAY_REAL`
- `src/api/kis_quant.py`: `_min_interval` (생성자에서 설정)

**주의:** 슬라이딩 윈도우 방식으로 계산되므로 한계치에 딱 맞추면 초과될 수 있음. 충분한 여유 필요.

### 텔레그램 네트워크 에러 (httpx.ConnectError)
- 원인: 네트워크 연결 문제 (토큰 충돌 아님)
- 해결: 자동 복구됨 - 최대 10회 재시도 + 스레드 자동 재시작 (2026-01)

### 텔레그램 Conflict 에러 (409 Error)
- 증상: `telegram.error.Conflict: terminated by other getUpdates request`
- 원인: 이전 봇 세션이 완전히 종료되지 않은 상태에서 새 세션 시작
- 해결: 자동 복구됨 - Conflict 감지 시 10+5n초 딜레이 후 재시도 (2026-01)

**예방 조치:**
- `run_quant.sh daemon`은 SIGTERM으로 graceful shutdown 후 3초 대기
- `drop_pending_updates=True`로 이전 세션의 pending updates 무시

**관련 코드:** `src/telegram/bot.py`, `run_quant.sh`

### 총자산 과대 표시 (T+2 결제 이중 계산)
- 증상: 매수 발생일 총자산/수익률이 비정상적으로 높게 표시
- 원인: `cash(dnca_tot_amt)` + `scts_evlu` 계산 시 T+2 결제 미반영으로 매수 금액 이중 계산
- 해결: `nass_amt`(순자산) 사용 → 미결제 약정 반영
- 참고: `.claude/rules/00-quick-reference.md`의 "총자산 계산 패턴" 참조

### 목표 종목 미달
- 스크리닝 결과 < 목표: 필터 조건 미충족
- 매수 실패: 다음 장 09:00 재시도 (최대 3회)
- 텔레그램으로 미달 알림 발송 (2026-01)

### pykrx 스크리닝 실패 (2026-01-27 발생/해결)

**증상:**
- `유니버스: 0개` 스크리닝 실패
- `KeyError: "None of [Index(['종가', '시가총액', '거래량', '거래대금']..."`
- `IndexError: index -1 is out of bounds for axis 0 with size 0`

**원인:** KRX 웹사이트 API 응답 형식 변경으로 pykrx 1.0.x 호환성 문제

**해결:** pykrx 1.2.3 이상으로 업그레이드
```bash
pip install pykrx>=1.2.3 --break-system-packages  # Homebrew Python
```

**폴백 동작 (pykrx 실패 시):**
1. KIS API로 시가총액 상위 30개 조회
2. pykrx로 KOSPI200 확장 시도
3. pykrx 실패 시 → KIS 30개로 진행

**관련 코드:** `src/strategy/quant/screener.py` - `_build_universe()`

**참고:** pykrx는 KRX 웹 크롤링 기반이라 KRX 사이트 변경 시 영향받음. 유사 문제 발생 시 pykrx 업데이트 먼저 확인.

### 긴급 리밸런싱 무한 반복 (2026-01 수정)
- 증상: 매일 08:30에 "긴급 리밸런싱 트리거" 메시지 반복
- 원인: 긴급 리밸런싱이 월초 중복 방지 로직을 우회
- 해결: `last_urgent_rebalance_month`로 별도 추적, 월 1회 제한

**리밸런싱 동작:**
| 유형 | 추적 변수 | 조건 | 제한 |
|------|----------|------|------|
| 월초 리밸런싱 | `last_rebalance_month` | 매월 첫 거래일 | 월 1회 |
| 긴급 리밸런싱 | `last_urgent_rebalance_month` | 보유 < 목표의 70% | 월 1회 |

**관련 코드:** `src/quant_engine.py` - `_is_rebalance_day()`

### 휴장일 오판단 (2026-01 수정)
- 증상: 평일(거래일)인데 휴장일로 판단하여 봇 미동작
- 원인: pykrx가 자정에 당일 거래 데이터 조회 시 데이터 없음 → 휴장일로 잘못 판단
- 해결: 오늘/미래 날짜는 pykrx 조회 생략, KNOWN_HOLIDAYS 기반 판단

**휴장일 판단 우선순위:**
1. 주말(토/일) → 휴장
2. KNOWN_HOLIDAYS (하드코딩) → 휴장
3. 오늘/미래 날짜 → 평일이면 거래일로 가정
4. 과거 날짜 → pykrx로 실제 거래 데이터 확인

**관련 코드:** `src/utils/market_calendar.py`

**참고:** KIS API 휴장일조회(CTCA0903R)는 실전투자에서만 지원. 모의투자에서는 KNOWN_HOLIDAYS 사용.

### 긴급 정지 해제
```
/clear_emergency
/start_trading
```

## 개발 가이드

### 텔레그램 명령어 추가
1. 해당 카테고리의 Mixin 파일에 `async def cmd_XXX()` 추가:
   - 조회: `src/telegram/commands/query_commands.py`
   - 제어: `src/telegram/commands/control_commands.py`
   - 실행: `src/telegram/commands/action_commands.py`
   - 설정: `src/telegram/commands/setting_commands.py`
   - 분석: `src/telegram/commands/analysis_commands.py`
2. `src/telegram/bot.py`의 `build_application()`에 핸들러 등록
3. `cmd_help()` 업데이트

### 알림 전송
```python
from src.telegram import get_notifier
notifier = get_notifier()
notifier.notify_buy(code, name, qty, price, reason)
notifier.notify_error("제목", "상세 내용")
```

### 에러 메시지 (사용자 친화적)
```python
from src.utils.error_formatter import format_user_error

# except 블록에서 사용
except Exception as e:
    logger.error(f"작업 실패: {e}", exc_info=True)  # 로그에 raw traceback 유지
    await reply_text(format_user_error(e, "잔고 조회"), parse_mode='HTML')
```

에러 카테고리: timeout, connection, rate_limit, server_error, auth, data, file, unknown

### 콜백 등록
```python
controller = get_controller()
controller.register_callback('on_screening', engine.run_screening)
```

### 유틸리티 사용
```python
from src.utils import safe_float, safe_int, format_currency
from src.utils.retry import with_retry, API_RETRY_CONFIG

# 안전한 타입 변환
price = safe_float(data.get('price'), 0)

# 재시도 데코레이터
@with_retry(API_RETRY_CONFIG)
def api_call():
    ...
```

## 봇 운영 구조

| 봇 | 실행 방식 | 토큰 |
|----|----------|------|
| 주식봇 (007_stock_trade) | 수동 터미널 | 별도 .env |
| 암호화폐봇 (005_money) | start_all_bots.sh | 별도 .env |

각 봇은 독립 터미널/토큰 사용 → 토큰 충돌 없음.

## 의존성 요구사항

| 패키지 | 최소 버전 | 용도 | 비고 |
|--------|----------|------|------|
| pykrx | **1.2.3** | KOSPI200 유니버스 조회 | 1.0.x는 KRX API 변경으로 실패 |
| python-telegram-bot | 20.0+ | 텔레그램 봇 | async 지원 필수 |
| schedule | 1.0+ | 스케줄러 | - |
| pandas | 1.5+ | 데이터 처리 | - |

**pykrx 버전 주의:** KRX 웹사이트 구조 변경 시 pykrx가 영향받음. 스크리닝 실패 시 pykrx 업데이트 먼저 확인.

---

## 변경 히스토리

### 2026-01-27: pykrx 호환성 문제 및 긴급 리밸런싱 버그 수정

**문제 1: pykrx 스크리닝 실패**
- 현상: 08:30 스크리닝 시 유니버스 0개, `KeyError` 발생
- 원인: KRX 웹사이트 API 응답 형식 변경 → pykrx 1.0.51 호환성 깨짐
- 영향: KOSPI200 조회 실패 → KIS API 폴백(30개)으로 진행
- 해결: pykrx 1.0.51 → 1.2.3 업그레이드
- 결과: 유니버스 30개 → 200개 정상화

**문제 2: 긴급 리밸런싱 무한 반복**
- 현상: 매일 08:30에 "긴급 리밸런싱 트리거" 반복 실행
- 원인: 긴급 리밸런싱이 `last_rebalance_month` 체크를 우회
- 영향: 월초 외에도 매일 리밸런싱 시도 → 스크리닝 실패와 맞물려 매도만 발생
- 해결: `last_urgent_rebalance_month` 별도 추적, 월 1회 제한
- 관련 커밋: `0b10b36`, `627c4fd`, `aeeae65`

**교훈:**
1. pykrx는 KRX 웹 크롤링 기반이라 외부 변경에 취약 → 폴백 로직 필수
2. 긴급 리밸런싱 같은 예외 로직은 별도 추적 변수로 제한 필요

### 2026-02-09: 일별 자산 추적 및 거래 일지 기능 추가

**배경:** 모의투자 계좌는 앱에서 직접 확인 불가. 기존엔 월간 스냅샷만 저장하여 일별 자산 변화 및 매매 기록 검증이 어려웠음.

**추가된 기능:**
- `src/quant_modules/daily_tracker.py` - 일별 자산 스냅샷 + 영구 거래 일지 모듈
- 거래 발생 시 `transaction_journal.json`에 즉시 기록 (order_executor 3곳)
- 15:20 일일 리포트 시 `daily_history.json`에 자산 스냅샷 저장
- 텔레그램 명령어: `/history [N]`, `/trades [N]`, `/capital`
- 초기 투자금 기록 (최초 1회), 365일 자동 정리

**데이터 파일:**
| 파일 | 용도 | 생성 시점 |
|------|------|----------|
| `data/quant/daily_history.json` | 일별 자산 스냅샷 | 15:20 일일 리포트 |
| `data/quant/transaction_journal.json` | 전체 거래 일지 | 매매 즉시 |

**관련 코드:**
- `src/quant_modules/daily_tracker.py` - DailySnapshot, TransactionRecord, DailyTracker
- `src/quant_modules/order_executor.py` - `daily_tracker` 파라미터 + `log_transaction()` 호출
- `src/quant_engine.py` - DailyTracker 초기화, `generate_daily_report()`에서 스냅샷 저장
- `src/telegram/bot.py` - `/history`, `/trades`, `/capital` 명령어

### 2026-02-14: 사용자 친화적 에러 메시지 시스템

**배경:** 텔레그램 에러 알림이 Python raw exception 형태로 노출되어 사용자가 심각도를 판단하기 어려웠음.

**변경 내용:**
- `src/utils/error_formatter.py` - 에러 분류 + 사용자 친화적 HTML 메시지 변환 모듈
- 텔레그램 봇 9곳, 퀀트 엔진 2곳, 자동관리자 2곳의 에러 메시지를 상황/조치/안심 포맷으로 전환
- 데몬 터미널 출력: WARNING 이상만 표시, traceback 숨김 (로그 파일에는 유지)

**에러 메시지 포맷 (Before → After):**
```
Before: ❌ 잔고 조회 실패: HTTPSConnectionPool(...): Read timed out
After:  ⏱️ 잔고 조회 지연 / 상황: 서버 응답 지연 / 조치: 자동 재시도 / 시스템 정상 운영 중
```

**설계 원칙:**
- 로그 파일: raw exception + traceback 그대로 유지 (디버깅용)
- 텔레그램/터미널: 사용자 친화적 메시지만 표시
- KIS 커스텀 예외 → 표준 예외 → 문자열 패턴 순으로 분류

**관련 코드:**
- `src/utils/error_formatter.py` - classify_error(), format_user_error()
- `src/telegram/bot.py` - 9곳 except 블록 수정
- `src/quant_engine.py` - 스크리닝/초기 스크리닝 에러 2곳
- `src/scheduler/auto_manager.py` - 모니터링/최적화 에러 2곳
- `scripts/run_daemon.py` - CleanFormatter + stream_handler WARNING 레벨
- `scripts/run_daemon.py` - 데몬 시작 시 잔고 조회 재시도 (최대 3회, 2초 간격)

**데몬 시작 시 잔고 조회:**
- KIS 모의투자 서버가 간헐적으로 `INVALID_CHECK_ACNO` 응답 → 재시도로 해결
- 재시도 없을 때: 기본값 1천만원으로 시작 → 실제 예수금과 불일치
- 재시도 추가 후: 2~3번째 시도에서 정상 조회되어 실제 예수금으로 시작

### 2026-02-19: 주간 장부 점검 (Weekly Reconciliation) 기능 추가

**배경:** `daily_history.json`의 일일 스냅샷이 내부 계산 오류(이중 카운팅 등)로 실제 KIS 잔고와 불일치할 수 있음이 확인됨.

**추가된 기능:**
- `src/quant_modules/daily_tracker.py` - `reconcile_latest_snapshot()` 메서드 추가
- `src/quant_engine.py` - `_on_weekly_reconciliation()` 메서드 + 토요일 10:00 스케줄 등록
- `src/telegram/bot.py` - `/reconcile` 수동 점검 명령어 추가
- `scripts/run_daemon.py` - `on_reconcile` 콜백 등록
- `src/api/kis_client.py` - `get_balance()`에 `scts_evlu`, `nass` 필드 추가

**동작 방식:**
- 토요일 10:00 자동 실행 (또는 `/reconcile` 수동 실행)
- KIS API 실잔고 조회 → 최근 스냅샷과 비교
- 편차 >1% 시 스냅샷 보정 (total_assets, cash, invested, PnL 재계산)
- 포지션 수 불일치 시 자동 동기화
- 텔레그램으로 점검 결과 알림

**관련 코드:**
- `src/quant_modules/daily_tracker.py` - `reconcile_latest_snapshot()`
- `src/quant_engine.py` - `_on_weekly_reconciliation(force=False)`
- `src/telegram/bot.py` - `cmd_reconcile()`
- `scripts/run_daemon.py` - `on_reconcile` 콜백

### 2026-02-20: 월간 리포트 총자산 이중계산 수정 + 리밸런싱 실시간 진행상황 알림

**버그 1: 월간 리포트/`/capital` 총자산 이중 카운팅**
- 현상: 총자산이 실제보다 ~60% 높게 표시됨
- 원인: `total_eval`(현금+주식 포함) + `cash`(현금) = 현금 2번 합산
- 영향: `generate_monthly_report()`, `/capital` 명령어
- 해결: `total_eval` → `scts_evlu`(주식평가만)로 변경하여 `scts_evlu + cash` 패턴 통일
- 참고: `generate_daily_report()`, `reconcile_latest_snapshot()`, `/status`는 이미 정상이었음

**개선 2: 리밸런싱 실시간 진행상황 알림**
- 현상: `/run_rebalance` 실행 시 20~40초간 피드백 없이 블로킹 → 중복 실행 유발
- 해결 (bot.py):
  - `threading.Lock`으로 `/run_rebalance`와 `/rebalance` 중복 실행 방지
  - 즉시 "접수" 메시지 전송 + `asyncio.to_thread()`로 비차단 실행
  - 완료/에러 시 결과 메시지 전송
- 해결 (quant_engine.py):
  - `manual_rebalance()`: 스크리닝 시작/주문 생성 중/주문 완료 단계별 알림
  - `run_urgent_rebalance()`: 스크리닝 시작/매수 주문 완료 알림

**관련 코드:**
- `src/quant_engine.py` - `generate_monthly_report()`, `manual_rebalance()`, `run_urgent_rebalance()`
- `src/telegram/bot.py` - `cmd_capital()`, `cmd_run_rebalance()`, `cmd_rebalance()`

### 2026-02-20: 기간별 체결 내역 조회 기능 추가

**배경:** `/orders`가 당일 주문만 조회 가능하고, `/trades`는 봇 자체 기록만 조회 → KIS에서 실제 체결 내역을 기간별로 확인할 수 없었음.

**추가된 기능:**
- `src/api/kis_client.py` - `get_execution_history()` 메서드 추가 (기간별 체결 조회 + 페이지네이션)
- `src/telegram/bot.py` - `/orders [N]` 명령어 확장 (최근 N일 체결 내역)

**사용법:**
```
/orders       → 당일 주문내역 (기존 동작 유지)
/orders 7     → 최근 7일 체결 내역
/orders 30    → 최근 30일 체결 내역 (최대 90일)
```

**API 세부사항:**
- 3개월 이내: `VTTC0081R`(모의) / `TTTC0081R`(실전)
- 3개월 이전: `VTSC9215R`(모의) / `CTSC9215R`(실전)
- 페이지네이션: `tr_cont` 헤더 + `CTX_AREA_FK100/NK100`으로 연속 조회
- 모의투자 1회 최대 15건 제한 → 자동 페이지네이션 처리

**관련 코드:**
- `src/api/kis_client.py` - `get_execution_history()`, `_last_response_headers` 추가
- `src/telegram/bot.py` - `cmd_orders()` 확장, `cmd_help()` 업데이트

### 2026-02-20: 총자산 T+2 결제 이중 계산 수정

**버그: 매매일 총자산/일일수익률 과대 계산**
- 현상: 대량 매수 발생일 일일 수익률 42% 표시 (실제 ~4%)
- 원인: `total_assets = cash(dnca_tot_amt) + scts_evlu(scts_evlu_amt)` 계산 시 T+2 결제 미반영
  - `scts_evlu`: 매수 종목 이미 포함 (9,514,900)
  - `dnca_tot_amt`: 매수 대금 미차감 (6,119,098 그대로)
  - → 매수 금액만큼 이중 계산
- 해결: `nass_amt`(순자산) 사용으로 미결제 약정 반영

**수정 패턴 (5곳 통일):**
```
Before: total_assets = cash + scts_evlu  ← 결제 전 예수금 이중 계산
After:  total_assets = nass              ← 순자산 (미결제 반영)
        cash = nass - scts_evlu          ← 실질 현금 (역산)
```

**관련 코드:**
- `src/quant_engine.py` - `generate_daily_report()`, `generate_monthly_report()`, `_on_weekly_reconciliation()`
- `src/telegram/bot.py` - `cmd_capital()`
- `src/quant_modules/daily_tracker.py` - `reconcile_latest_snapshot()`

### 2026-02-21: 코드베이스 모듈화 리팩토링 (8단계)

**배경:** `quant_engine.py`(1,664줄)와 `bot.py`(1,653줄) 두 파일이 과도하게 비대하여 유지보수 어려움. Balance 계산 패턴 5곳 중복, 손절/익절 로직 ~60줄 거의 동일 등 코드 중복 다수.

**리팩토링 결과:**

| 파일 | Before | After | 변화 |
|------|--------|-------|------|
| `src/quant_engine.py` | 1,664줄 | ~980줄 | -41% |
| `src/telegram/bot.py` | 1,653줄 | ~330줄 | -80% |

**Phase 1: Balance 계산 헬퍼 추출 + cmd_balance 버그 수정**
- `src/utils/balance_helpers.py` 신규 생성 (BalanceSummary, parse_balance)
- nass 기반 T+2 결제 대응 로직을 단일 함수로 통합 (5곳 중복 제거)
- `cmd_balance`의 `total_eval` 사용 버그 수정
- `tests/test_balance_helpers.py` 테스트 추가

**Phase 2: API 딜레이 상수 통합**
- `quant_engine.py`의 중복 상수 삭제 → `order_executor.py`에서 import

**Phase 3: 손절/익절 트리거 통합**
- `_trigger_sell_with_retry()` 공통 메서드 추출 (손절/익절 ~60줄 중복 제거)

**Phase 4: 리포트 모듈 추출**
- `src/quant_modules/report_generator.py` 신규 생성 (ReportGenerator 클래스)
- `generate_daily_report()`, `generate_monthly_report()` 이관

**Phase 5: bot.py 커맨드 모듈 분리**
- `src/telegram/commands/` 디렉토리 신규 생성 (5개 Mixin + 공통 베이스)
- Mixin 패턴: QueryCommandsMixin, ControlCommandsMixin, ActionCommandsMixin, SettingCommandsMixin, AnalysisCommandsMixin
- `with_error_handling` 데코레이터로 11곳 에러 핸들링 통합
- `parse_days_arg()` 유틸로 일수 검증 3곳 통합

**Phase 6: 포지션 모니터 추출**
- `src/quant_modules/position_monitor.py` 신규 생성 (PositionMonitor 클래스)
- `monitor_positions()`, `_trigger_stop_loss()`, `_trigger_take_profit()` 이관

**Phase 7: 스케줄 핸들러 추출**
- `src/quant_modules/schedule_handler.py` 신규 생성 (ScheduleHandler 클래스)
- `_setup_schedule()`, `_on_pre_market()`, `_on_market_open()`, `_on_monitoring()`, `_on_market_close()` 이관

**Phase 8: 트래커 베이스 클래스 추출**
- `src/quant_modules/tracker_base.py` 신규 생성 (TrackerBase 클래스)
- JSON 로드/세이브 공통 패턴 추출 (원자적 쓰기, 손상 파일 백업)
- DailyTracker, MonthlyTracker가 TrackerBase 상속

**설계 원칙:**
- 500줄 초과 파일 없음, 각 파일이 단일 책임
- 기능 변경 없이 순수 리팩토링 (cmd_balance 버그 수정 제외)
- 기존 테스트 전체 통과
