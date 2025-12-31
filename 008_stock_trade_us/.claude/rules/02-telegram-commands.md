# 텔레그램 명령어 가이드

## 명령어 카테고리

### 시스템 제어 (🔧)

```
/start_trading  - 자동매매 시작
/stop_trading   - 자동매매 중지
/pause          - 일시 정지 (신규 주문만 중단)
/resume         - 일시정지에서 재개
/emergency_stop - 긴급 정지 (모든 거래 즉시 중단)
/clear_emergency- 긴급 정지 해제
```

**상태 전이:**
```
STOPPED ──/start_trading──▶ RUNNING
    ▲                           │
    │                           ▼
/stop_trading              /pause
    │                           │
    ▲                           ▼
RUNNING ◀──/resume──── PAUSED
    │
    ▼
/emergency_stop
    │
    ▼
EMERGENCY_STOP ──/clear_emergency──▶ STOPPED
```

### 수동 실행 (🔄)

```
/run_screening  - 스크리닝 즉시 실행
/run_rebalance  - 리밸런싱 즉시 실행
/run_optimize   - 가중치 최적화 실행 (5~10분 소요)
```

### 설정 변경 (⚙️)

```
/set_dryrun on|off    - Dry-run 모드 변경
/set_target [숫자]    - 목표 종목 수 (1~50)
/set_stoploss [숫자]  - 손절 비율 % (1~30)
```

**예시:**
```
/set_dryrun off     → 실제 주문 활성화
/set_target 20      → 목표 20종목
/set_stoploss 5     → 5% 손절
```

### 조회 (📊)

```
/status     - 시스템 상태 (상태, 설정, 가중치 표시)
/positions  - 보유 포지션 목록
/balance    - 계좌 잔고
/logs       - 최근 로그 (기본 10줄)
/logs 20    - 최근 20줄 로그
/report     - 일일 리포트
```

### 포지션 관리 (📈)

```
/close [종목코드]  - 특정 종목 청산
/close_all         - 전체 포지션 청산
```

**예시:**
```
/close 005930    → 삼성전자 청산
/close_all       → 전체 청산
```

### 분석 (🔍)

```
/screening          - 스크리닝 결과 조회
/signal [종목코드]  - 기술적 분석 (RSI, MACD 등)
/price [종목코드]   - 현재가 조회
```

**예시:**
```
/signal 005930   → 삼성전자 기술적 분석
/price 035720    → 카카오 현재가
```

## 명령어 추가 방법

### 1. 핸들러 메서드 추가

`src/telegram/bot.py`의 `TelegramBot` 클래스에:

```python
async def cmd_my_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """내 커맨드 설명"""
    from src.core import get_controller

    controller = get_controller()
    # 로직 구현

    await update.message.reply_text("응답 메시지", parse_mode='HTML')
```

### 2. 핸들러 등록

`build_application()` 메서드에:

```python
self.application.add_handler(CommandHandler("my_command", self.cmd_my_command))
```

### 3. 도움말 업데이트

`cmd_help()` 메서드의 메시지에 추가.

## 주의사항

- 명령어는 **영문 소문자**만 가능 (Telegram API 제한)
- 명령어 이름에 하이픈(-) 사용 가능, 언더스코어(_) 사용 가능
- 한글 명령어 불가
