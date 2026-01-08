# Quick Reference

CLAUDE.md에 없는 상세 코드 패턴 참조.

## 모듈 구조 (2026-01 리팩토링)

```
src/
├── quant_engine.py              # 엔진 오케스트레이션 (~1,160줄)
├── quant_modules/               # 분리된 엔진 모듈
│   ├── state_manager.py         # EngineState, PendingOrder, 상태 저장/로드
│   └── order_executor.py        # 주문 생성/실행/재시도
├── telegram/
│   ├── bot.py                   # 텔레그램 봇 (~1,134줄)
│   ├── notifier.py              # TelegramNotifier (알림 전송)
│   └── validators.py            # InputValidator (입력 검증)
└── utils/
    ├── converters.py            # safe_float, format_currency 등
    └── retry.py                 # RetryConfig, @with_retry
```

## SystemController 패턴

```python
from src.core import get_controller
controller = get_controller()  # 싱글톤

# 상태: STOPPED, RUNNING, PAUSED, EMERGENCY_STOP
controller.start_trading()
controller.emergency_stop()

# 설정 변경 (자동 저장)
controller.set_dry_run(False)
controller.set_target_count(20)

# 콜백 등록
controller.register_callback('on_start', engine.start)
controller.register_callback('on_screening', engine.run_screening)
controller.register_callback('on_rebalance', engine.rebalance)
```

## 텔레그램 명령어 추가

```python
# src/telegram/bot.py

async def cmd_new_feature(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """새 기능"""
    from src.core import get_controller
    controller = get_controller()

    # 인자 처리
    if context.args:
        value = context.args[0]

    result = controller.some_method()

    if result['success']:
        await update.message.reply_text(f"✅ {result['message']}", parse_mode='HTML')
    else:
        await update.message.reply_text(f"❌ {result['message']}")

# build_application()에 추가
self.application.add_handler(CommandHandler("new_feature", self.cmd_new_feature))
```

## 데이터 파일

| 파일 | 용도 |
|------|------|
| `config/system_config.json` | 시스템 설정 (텔레그램 명령 저장) |
| `config/optimal_weights.json` | 팩터 가중치 |
| `data/quant/engine_state.json` | 포지션, 주문 상태 |
| `logs/daemon_YYYYMMDD.log` | 일별 로그 |

## 상태 전이

```
STOPPED ──/start_trading──▶ RUNNING ──/pause──▶ PAUSED
    ▲                           │                   │
    └────/stop_trading──────────┴───/resume─────────┘
                                │
                        /emergency_stop
                                │
                                ▼
                        EMERGENCY_STOP ──/clear_emergency──▶ STOPPED
```

## API Rate Limit 대응

```python
# 여러 종목 처리 시 150ms 딜레이 필수
for i, code in enumerate(codes):
    if i > 0:
        time.sleep(0.15)  # API Rate Limit 방지
    result = api.call(code)
```

## 로깅

```python
import logging
logger = logging.getLogger(__name__)

logger.info("정상")
logger.warning("경고")
logger.error("오류")
```

## 퀀트 모듈 사용

### 상태 관리 (state_manager.py)
```python
from src.quant_modules import EngineState, SchedulePhase, PendingOrder, EngineStateManager

# Enum 사용
state = EngineState.RUNNING
phase = SchedulePhase.MARKET_HOURS

# 대기 주문 생성
order = PendingOrder(
    code="005930",
    name="삼성전자",
    order_type="BUY",
    quantity=10,
    price=0,  # 시장가
    reason="리밸런싱 매수"
)
```

### 주문 실행 (order_executor.py)
```python
from src.quant_modules import OrderExecutor

# OrderExecutor는 QuantTradingEngine 내부에서 사용
# engine.order_executor.generate_rebalance_orders(...)
# engine.order_executor.execute_pending_orders(...)
```

## 텔레그램 모듈 사용

### 알림 전송 (notifier.py)
```python
from src.telegram import get_notifier

notifier = get_notifier()
notifier.notify_buy(code, name, qty, price, reason)
notifier.notify_sell(code, name, qty, price, reason)
notifier.notify_error("제목", "상세 내용")
notifier.notify_system("시스템 알림", {"키": "값"})
notifier.notify_screening_result(result)
notifier.notify_daily_report(report_data)
```

### 입력 검증 (validators.py)
```python
from src.telegram.validators import InputValidator

# 종목코드 검증
valid, error = InputValidator.validate_stock_code("005930")

# 숫자 검증
valid, value, error = InputValidator.validate_positive_int("10", 1, 100)

# on/off 검증
valid, bool_val, error = InputValidator.validate_on_off("on")
```

## 유틸리티 모듈

### 타입 변환 (converters.py)
```python
from src.utils import safe_float, safe_int, format_currency, format_pct

price = safe_float(data.get('price'), 0)  # None/빈문자열 → 0
qty = safe_int("123.45")  # → 123
formatted = format_currency(1234567)  # → "1,234,567원"
pct = format_pct(1.23)  # → "+1.23%"
```

### 재시도 (retry.py)
```python
from src.utils.retry import with_retry, RetryConfig, API_RETRY_CONFIG

# 데코레이터 사용
@with_retry(API_RETRY_CONFIG)
def api_call():
    return client.get_price(code)

# 커스텀 설정
config = RetryConfig(
    max_retries=5,
    base_delay=2.0,
    backoff_factor=2.0,
    retriable_errors=("500", "Timeout")
)
```
