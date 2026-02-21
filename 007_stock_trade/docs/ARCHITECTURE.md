# Architecture

## 프로젝트 구조

```
src/
├── quant_engine.py              # 자동매매 엔진 오케스트레이션 (~980줄)
├── quant_modules/               # 퀀트 엔진 모듈
│   ├── state_manager.py         # 상태 저장/로드, Lock 관리
│   ├── order_executor.py        # 주문 생성/실행/재시도
│   ├── position_monitor.py      # 포지션 모니터링 (손절/익절)
│   ├── schedule_handler.py      # 스케줄 이벤트 핸들러
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

scripts/run_daemon.py            # 통합 데몬
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
팩터 가중치. 반기 최적화 시 자동 업데이트.

## 의존성

| 패키지 | 최소 버전 | 비고 |
|--------|----------|------|
| pykrx | **1.2.3** | 1.0.x는 KRX API 변경으로 실패 |
| python-telegram-bot | 20.0+ | async 필수 |
| schedule | 1.0+ | - |
| pandas | 1.5+ | - |
