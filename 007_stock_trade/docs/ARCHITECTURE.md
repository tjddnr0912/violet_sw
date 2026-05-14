# Architecture

## 프로젝트 구조

```
src/
├── quant_engine.py              # 자동매매 엔진 오케스트레이션 (~980줄)
├── quant_modules/               # 퀀트 엔진 모듈
│   ├── state_manager.py         # 상태 저장/로드, Lock 관리
│   ├── order_executor.py        # 주문 생성/실행/재시도 + 재진입 쿨다운(P2-6) + 섹터 한도(P2-7)
│   ├── position_monitor.py      # 포지션 모니터링 (손절/익절)
│   ├── schedule_handler.py      # 스케줄 이벤트 핸들러 + 월초 리밸런싱 누락 감지(P1)
│   ├── report_generator.py      # 일일/월간 리포트 생성
│   ├── tracker_base.py          # 트래커 공통 JSON 로드/세이브
│   ├── monthly_tracker.py       # 월간 포트폴리오 트래킹
│   └── daily_tracker.py         # 일별 자산 추적 및 거래 일지
├── api/
│   ├── kis_client.py            # KIS API 클라이언트
│   └── kis_quant.py             # 퀀트용 API 확장
├── core/system_controller.py    # 원격 제어 (싱글톤)
├── scheduler/auto_manager.py    # 월간 모니터링, 반기 최적화
├── telegram/
│   ├── bot.py                   # 텔레그램 봇 엔트리 (~330줄)
│   ├── commands/                # 명령어 Mixin 모듈
│   │   ├── _base.py             # 공통 유틸 (에러 핸들링 데코레이터)
│   │   ├── query_commands.py    # 조회 (balance, positions 등)
│   │   ├── control_commands.py  # 제어 (start/stop/pause 등)
│   │   ├── action_commands.py   # 실행 (rebalance, reconcile 등)
│   │   ├── setting_commands.py  # 설정 (set_dryrun 등)
│   │   └── analysis_commands.py # 분석 (screening, signal 등)
│   ├── notifier.py              # 알림 전송 전담
│   └── validators.py            # 입력 검증
├── strategy/quant/              # 팩터, 스크리너, 리스크
└── utils/
    ├── balance_helpers.py       # 잔고 계산 헬퍼 (parse_balance)
    ├── converters.py            # 타입 변환, 포맷팅
    ├── error_formatter.py       # 사용자 친화적 에러 메시지
    ├── retry.py                 # 재시도 데코레이터/설정
    └── market_calendar.py       # 휴장일 판단

scripts/
├── run_daemon.py                # 통합 데몬
├── run_quant_watchdog.sh        # 데몬 수명 감시 + 다운/hang 자동 재시작 (P1)
├── check_missed_rebalance_alert.py  # P1 회귀 체크 (#41)
├── check_reentry_cooldown.py    # P2-6 회귀 체크 (#42)
├── check_sector_limit.py        # P2-7 회귀 체크 (#43)
├── check_watchdog_syntax.py     # P1 watchdog 문법 검증 (#44)
└── run_checklist.py             # docs/CHECKLIST.md 일괄 실행

config/
├── optimal_weights.json         # 팩터 가중치
└── system_config.json           # 시스템 설정 (Telegram 명령으로 변경)
data/quant/
├── engine_state.json            # 포지션, 리밸런스 상태
├── daily_history.json           # 일별 자산 스냅샷
└── transaction_journal.json     # 전체 거래 일지
```

## 개발 가이드

### 텔레그램 명령어 추가

1. 해당 카테고리 Mixin 파일에 `async def cmd_XXX()` 추가
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

except Exception as e:
    logger.error(f"작업 실패: {e}", exc_info=True)
    await reply_text(format_user_error(e, "잔고 조회"), parse_mode='HTML')
```

에러 카테고리: timeout, connection, rate_limit, server_error, auth, data, file, unknown

### 유틸리티

```python
from src.utils import safe_float, safe_int, format_currency
from src.utils.retry import with_retry, API_RETRY_CONFIG

price = safe_float(data.get('price'), 0)

@with_retry(API_RETRY_CONFIG)
def api_call():
    ...
```

### 콜백 등록

```python
controller = get_controller()
controller.register_callback('on_screening', engine.run_screening)
```

## 설정 파일

### config/system_config.json
Telegram 명령으로 변경한 설정 저장. 데몬 재시작 후에도 유지.

### config/optimal_weights.json
팩터 가중치 Single Source of Truth. 두 가지 가중치 체계:
- `factor_weights`: 엔진 스크리너용 V/M/Q/Vol 4팩터 가중치
- `signal_weights`: 모니터링/최적화 스크립트용 신호 가중치
반기 최적화 시 자동 업데이트.

## 트레이딩 룰 가드 (P2 — 매수 주문 직전 필터)

리밸런싱 매수 후보가 다음 두 가드를 모두 통과해야 주문 생성됨. 위치: `order_executor.py:execute_pending_orders` 내부 후보 평가 루프.

| 가드 | 조건 | 발화 시 |
|------|------|--------|
| 재진입 쿨다운 (P2-6) | `daily_tracker`에서 최근 `COOLDOWN_DAYS=20` 영업일 손절 이력 조회 → 현재가가 손절가 대비 `COOLDOWN_OVERRIDE_DROP_PCT=5%` 추가 하락이 아니면 차단 | `재진입 쿨다운 스킵` 로그, 주문 생성 안 함 |
| 섹터 한도 (P2-7) | 보유 + 신규 주문 후보 합산 sector 카운트가 `DEFAULT_MAX_PER_SECTOR=3`을 초과하지 않을 때만 허용 | `섹터 한도 스킵` 로그, 주문 생성 안 함 |

쿨다운/한도 파라미터는 모듈 상단 상수로 노출 (`order_executor.py:30~35`). 변경 시 회귀 체크: `python scripts/check_reentry_cooldown.py`, `python scripts/check_sector_limit.py`.

## 재발 방지 인프라 (P1)

| 구성요소 | 위치 | 트리거 |
|---------|------|--------|
| `_check_missed_rebalance` | `schedule_handler.py:372` | 일일 리포트(15:20) 후. 오늘이 월 첫 영업일인데 `last_rebalance_month`·`last_urgent_rebalance_month`가 이번 달이 아니면 텔레그램 경고. |
| `run_quant_watchdog.sh` | `scripts/run_quant_watchdog.sh` (래퍼: `./run_quant.sh watchdog`) | 별도 프로세스. 데몬 PID 사망 또는 `HANG_TIMEOUT=1800s` 무로그 시 자동 재시작 + 텔레그램 알림. |

상세 사고 컨텍스트: [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — "월 첫 영업일 리밸런싱 사일런트 실패", "데몬 다운/Hang 미감지".

## 의존성

| 패키지 | 최소 버전 | 비고 |
|--------|----------|------|
| pykrx | **1.2.3** | 1.0.x는 KRX API 변경으로 실패 |
| python-telegram-bot | 20.0+ | async 필수 |
| schedule | 1.0+ | - |
| pandas | 1.5+ | - |
