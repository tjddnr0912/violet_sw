# 코드 구조 분석

## 핵심 모듈

### src/core/system_controller.py

**역할**: 시스템 원격 제어 (싱글톤)

```python
class SystemState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    EMERGENCY_STOP = "emergency_stop"

class SystemConfig:
    dry_run: bool = True
    is_virtual: bool = True
    target_count: int = 15
    stop_loss_pct: float = 7.0
    # 팩터 가중치...

class SystemController:
    # 시스템 제어
    start_trading() -> Dict
    stop_trading() -> Dict
    pause_trading() -> Dict
    resume_trading() -> Dict
    emergency_stop() -> Dict

    # 설정 변경
    set_dry_run(enabled: bool) -> Dict
    set_target_count(count: int) -> Dict
    set_stop_loss(pct: float) -> Dict

    # 수동 실행
    run_screening() -> Dict
    run_rebalance() -> Dict
    run_optimize() -> Dict

    # 콜백 등록
    register_callback(name: str, callback: Callable)
```

**사용법**:
```python
from src.core import get_controller
controller = get_controller()  # 싱글톤
```

---

### src/scheduler/auto_manager.py

**역할**: 자동 전략 관리

```python
class WeightConfig:
    # 가중치 설정 로드/저장
    load() -> dict
    save(weights: dict)
    update_from_optimization(result: dict) -> dict

class TelegramReporter:
    # 텔레그램 리포트 전송
    send_monitoring_report(metrics, alerts)
    send_optimization_report(result, updated)
    send_alert(title, message, level)

class AutoStrategyManager:
    # 자동 관리
    run_monitoring() -> dict       # 월간 모니터링
    run_optimization() -> dict     # 반기 최적화
    start()                        # 스케줄러 시작
```

**스케줄**:
- 매월 1일 09:00: 모니터링 실행
- 1월/7월 첫째주 08:00: 최적화 실행

---

### src/telegram/bot.py

**역할**: 텔레그램 봇

```python
class TelegramNotifier:
    # 단방향 알림 전송
    send_message(message: str) -> bool
    notify_buy(...) -> bool
    notify_sell(...) -> bool
    # 퀀트 알림...

class TelegramBot:
    # 양방향 명령어 처리
    cmd_start()          # /start
    cmd_help()           # /help
    cmd_start_trading()  # /start_trading
    cmd_stop_trading()   # /stop_trading
    # ... 20+ 명령어

    build_application() -> Application  # 핸들러 등록

class TelegramBotHandler:
    # 데몬용 래퍼 (스레드 안전)
    start()  # 폴링 시작
    stop()   # 중지
```

---

### src/quant_engine.py

**역할**: 자동매매 엔진

```python
class QuantEngineConfig:
    universe_size: int = 200
    target_stock_count: int = 15
    dry_run: bool = True

class QuantTradingEngine:
    start()              # 스케줄 시작
    run_screening()      # 스크리닝 실행
    execute_orders()     # 주문 실행
    monitor_positions()  # 포지션 모니터링
```

**스케줄**:
- 08:30: 스크리닝 (리밸런싱 일)
- 09:00: 주문 실행
- 5분 간격: 모니터링
- 15:20: 일간 리포트

---

## 설정 파일

### config/optimal_weights.json
```json
{
  "momentum_weight": 0.20,
  "short_mom_weight": 0.10,
  "volatility_weight": 0.50,
  "volume_weight": 0.00,
  "target_count": 15,
  "baseline_sharpe": 2.39,
  "auto_update": true
}
```

### config/system_config.json
```json
{
  "dry_run": true,
  "is_virtual": true,
  "target_count": 15,
  "stop_loss_pct": 7.0,
  "take_profit_pct": 10.0
}
```

---

## 디자인 패턴

### 싱글톤 패턴
- `SystemController` - 전역 시스템 상태 관리
- `TelegramNotifier` - 알림 인스턴스

### 콜백 패턴
```python
controller.register_callback('on_start', engine.start)
controller.register_callback('on_screening', engine.run_screening)
```

### 팩토리 함수
```python
def get_controller() -> SystemController:
    return SystemController()  # 싱글톤

def get_notifier() -> TelegramNotifier:
    return _notifier_instance
```

---

## 에러 처리

### 텔레그램 명령어
```python
async def cmd_xxx(self, update, context):
    try:
        # 로직
        await update.message.reply_text("성공", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ 오류: {e}")
```

### 콜백 실행
```python
def _trigger_callback(self, name, *args, **kwargs):
    if name in self.callbacks:
        try:
            return self.callbacks[name](*args, **kwargs)
        except Exception as e:
            logger.error(f"콜백 오류 ({name}): {e}")
    return None
```
