# 개발 가이드

## 새 기능 추가

### 텔레그램 명령어 추가

1. **핸들러 메서드 작성** (`src/telegram/bot.py`)
```python
async def cmd_new_feature(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """새 기능 설명"""
    from src.core import get_controller

    controller = get_controller()

    # 인자 처리
    if context.args:
        value = context.args[0]

    # 로직 실행
    result = controller.some_method()

    # 응답
    if result['success']:
        message = f"✅ 성공: {result['message']}"
    else:
        message = f"❌ 실패: {result['message']}"

    await update.message.reply_text(message, parse_mode='HTML')
```

2. **핸들러 등록** (`build_application()`)
```python
self.application.add_handler(CommandHandler("new_feature", self.cmd_new_feature))
```

3. **도움말 업데이트** (`cmd_help()`)

---

### SystemController 기능 추가

1. **메서드 추가** (`src/core/system_controller.py`)
```python
def new_action(self, param: str) -> Dict[str, Any]:
    """새 액션 설명"""
    if self.state == SystemState.EMERGENCY_STOP:
        return {"success": False, "message": "긴급 정지 상태"}

    # 콜백 실행
    result = self._trigger_callback('on_new_action', param)

    self.last_action = "new_action"
    self._save_state()

    return {"success": True, "message": "완료", "result": result}
```

2. **콜백 등록** (데몬에서)
```python
controller.register_callback('on_new_action', my_function)
```

---

## 테스트

### 텔레그램 연동 테스트
```bash
./run_quant.sh telegram
```

### API 연결 테스트
```bash
./run_quant.sh test
```

### 데몬 테스트
```bash
python3 scripts/run_daemon.py --dry-run
```

---

## 코드 컨벤션

### 명명 규칙

| 타입 | 규칙 | 예시 |
|------|------|------|
| 클래스 | PascalCase | `SystemController` |
| 함수/메서드 | snake_case | `start_trading()` |
| 상수 | UPPER_CASE | `MAX_RETRIES` |
| 비공개 | _prefix | `_save_state()` |

### 타입 힌트
```python
def set_target_count(self, count: int) -> Dict[str, Any]:
    ...
```

### 로깅
```python
import logging
logger = logging.getLogger(__name__)

logger.info("정상 메시지")
logger.warning("경고 메시지")
logger.error("오류 메시지")
```

---

## 디버깅

### 로그 확인
```bash
tail -f logs/daemon_$(date +%Y%m%d).log
```

### 텔레그램에서 로그 확인
```
/logs 20
```

### 시스템 상태 확인
```
/status
```

---

## 배포

### 데몬 실행
```bash
# 백그라운드 실행
nohup ./run_quant.sh daemon > /dev/null 2>&1 &

# 또는 screen/tmux 사용
screen -S quant
./run_quant.sh daemon
# Ctrl+A, D로 분리
```

### 프로세스 확인
```bash
ps aux | grep run_daemon
```

### 프로세스 종료
```bash
pkill -f "run_daemon.py"
```

---

## 주의사항

### 실전 투자 활성화
```bash
# 매우 주의해서 사용
./run_quant.sh daemon --real --no-dry-run
```

### 환경변수 필수
```
KIS_APP_KEY
KIS_APP_SECRET
KIS_ACCOUNT_NO
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

### 싱글톤 주의
- `SystemController`는 프로세스당 하나만 존재
- 상태 변경은 전역 영향
