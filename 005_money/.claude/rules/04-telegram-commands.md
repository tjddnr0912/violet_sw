# 04. 텔레그램 명령어

## 명령어 목록

| 명령어 | 파일 | 메서드 | 설명 |
|--------|------|--------|------|
| `/start` | telegram_bot_handler.py | cmd_start | 환영 메시지 |
| `/help` | telegram_bot_handler.py | cmd_help | 도움말 |
| `/status` | telegram_bot_handler.py | cmd_status | 봇 상태 개요 |
| `/positions` | telegram_bot_handler.py | cmd_positions | 포지션 상세 |
| `/summary` | telegram_bot_handler.py | cmd_summary | 일일 요약 |
| `/factors` | telegram_bot_handler.py | cmd_factors | 동적 팩터 |
| `/performance` | telegram_bot_handler.py | cmd_performance | 7일 성과 |
| `/close <COIN>` | telegram_bot_handler.py | cmd_close | 포지션 청산 |
| `/stop` | telegram_bot_handler.py | cmd_stop | 봇 중지 |

## 명령어 상세

### /status

봇의 전체 상태를 보여줍니다.

**응답 내용:**
- 실행 상태 (Running/Stopped)
- Uptime
- 분석 사이클 수
- 마지막 분석 시간
- 포지션 현황
- 모니터링 코인

### /positions

각 코인별 포지션 정보를 상세히 표시합니다.

**포지션 있는 경우:**
- 진입가
- 현재가
- 수량
- P&L (금액, %)
- 레짐
- 진입 스코어
- 진입 시간

**포지션 없는 경우:**
- 현재 레짐
- 현재 스코어
- 마지막 신호
- Extreme Oversold 상태 (Bearish 레짐만): `2/3 ✅` 또는 `1/3 ❌`
  - RSI, Stoch, BB 각 조건 충족 여부 표시

### /factors

현재 적용 중인 동적 파라미터를 보여줍니다.

**응답 내용:**
- 시장 레짐
- 변동성 레벨 (LOW/NORMAL/HIGH/EXTREME)
- ATR%
- Chandelier 배수
- 포지션 크기 배수
- RSI/Stoch 임계값
- 진입 가중치
- 최소 스코어

### /close <COIN>

특정 코인의 포지션을 수동 청산합니다.

**사용법:**
```
/close BTC    # BTC 포지션 청산
/close ETH    # ETH 포지션 청산
/close        # 보유 포지션 목록 표시
```

**동작 과정:**
1. 포지션 유무 확인
2. 현재 P&L 표시
3. [Close Position] [Cancel] 버튼
4. 60초 내 확인 필요
5. 청산 실행 후 결과 알림

### /stop

봇을 중지합니다.

**동작 과정:**
1. 현재 포지션 경고 표시
2. [Stop Bot] [Cancel] 버튼
3. 60초 내 확인 필요
4. 포지션은 자동 청산되지 않음

## 자동 알림

### 거래 알림 (send_trade_alert)

매수/매도 실행 시 자동 전송.

```
🟢 BUY Signal Executed

Coin: BTC
Amount: 0.00500000
Price: 128,000,000 KRW
Order ID: 12345678

Reason: Entry score 3.0 in bearish regime
```

### 레짐 변경 알림 (send_regime_change_alert)

시장 레짐이 변경될 때 자동 전송.

```
🚨 중요 레짐 전환!

⏰ 시각: 2025-12-28 15:00:00
🪙 대상: BTC

변경 내역
이전: 📈 상승장
현재: 📉 하락장

EMA 격차: -3.50%
```

### 동적 팩터 요약 (send_dynamic_factors_summary)

일일 팩터 업데이트 시 전송.

```
📊 Dynamic Factors Status

🎯 Market Regime: bearish
📈 Entry Mode: reversion

📉 Volatility
  Level: NORMAL
  ATR%: 2.15%

⚙️ Current Multipliers
  Chandelier: 3.0x
  Position Size: 1.00x
```

## 환경변수 설정

```bash
# .env 파일
TELEGRAM_BOT_TOKEN=1234567890:AABBccDDeeFFggHHiiJJkkLLmmNNoo
TELEGRAM_CHAT_ID=123456789
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

## 코드 위치

```
lib/core/
├── telegram_notifier.py       # 알림 전송 (단방향)
└── telegram_bot_handler.py    # 명령어 처리 (양방향)
```

## 명령어 추가 방법

1. `telegram_bot_handler.py`에 핸들러 메서드 추가:

```python
async def cmd_new_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_id = str(update.effective_chat.id)
    if user_chat_id != self.chat_id:
        await update.message.reply_text("Unauthorized.")
        return

    # 로직 구현
    message = "New command response"
    await update.message.reply_text(message, parse_mode='Markdown')
```

2. `_start_bot()`에서 핸들러 등록:

```python
self._application.add_handler(CommandHandler("new_command", self.cmd_new_command))
```

3. `/help` 메뉴에 추가

4. 문서 업데이트
