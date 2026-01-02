# Quick Reference

CLAUDE.md에 없는 상세 코드 패턴 참조.

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
