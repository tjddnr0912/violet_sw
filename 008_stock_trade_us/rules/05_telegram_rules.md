# 텔레그램 봇 규칙

## 봇 명령어 목록

| 명령어 | 설명 | 권한 |
|--------|------|------|
| `/start` | 봇 시작/환영 메시지 | 모든 사용자 |
| `/help` | 도움말 표시 | 모든 사용자 |
| `/status` | 포트폴리오 상태 | 등록된 사용자 |
| `/holdings` | 보유 종목 목록 | 등록된 사용자 |
| `/today` | 오늘 수익률 | 등록된 사용자 |
| `/signals` | 현재 매매 신호 | 등록된 사용자 |
| `/screen` | 스크리닝 실행 | 관리자 |
| `/balance` | 계좌 잔고 조회 | 관리자 |
| `/stop` | 엔진 중지 | 관리자 |

## 명령어 상세

### /status
```
📊 포트폴리오 현황

총 자산: ₩102,345,678
평가손익: +₩2,345,678 (+2.34%)
오늘 수익: +₩123,456 (+0.12%)

보유 종목: 18개
현금 비중: 8.5%

마지막 업데이트: 14:30:00
```

### /holdings
```
📋 보유 종목 (18개)

1. 삼성전자 (005930)
   10주 | ₩700,000 | +1.23%

2. SK하이닉스 (000660)
   5주 | ₩650,000 | -0.45%

3. 현대차 (005380)
   3주 | ₩600,000 | +2.10%

... (이하 생략)
```

### /today
```
📈 오늘의 성과

수익률: +0.85%
손익금: +₩850,000

거래 현황:
- 매수: 2건 (₩1,200,000)
- 매도: 1건 (₩500,000)

상승 종목: 12개
하락 종목: 6개
```

### /signals
```
🔔 현재 매매 신호

📈 매수 신호 (3개):
1. NAVER (035420) - 강력매수
   신호강도: 0.85 | RSI: 32

2. 카카오 (035720) - 매수
   신호강도: 0.72 | RSI: 38

📉 매도 신호 (1개):
1. LG화학 (051910) - 매도
   신호강도: -0.65 | RSI: 75
```

### /screen
```
🔍 스크리닝 시작...

진행: 50/200 (25%)
진행: 100/200 (50%)
진행: 150/200 (75%)
진행: 200/200 (100%)

✅ 스크리닝 완료! (45.3초)

상위 10개 종목:
1. 삼성전자 - 점수: 87.5
2. SK하이닉스 - 점수: 82.3
3. 현대차 - 점수: 78.9
...
```

### /balance
```
💰 계좌 잔고

예수금: ₩8,500,000
주식평가: ₩91,845,678
총자산: ₩100,345,678

매수가능: ₩8,500,000
출금가능: ₩5,000,000
```

## 알림 유형

### 매매 알림
```python
def send_trade_notification(action, stock_name, quantity, price):
    emoji = "🔵" if action == "BUY" else "🔴"
    message = f"""
{emoji} {action} 체결

종목: {stock_name}
수량: {quantity:,}주
가격: ₩{price:,}
금액: ₩{quantity * price:,}
시간: {datetime.now().strftime('%H:%M:%S')}
"""
    send_message(message)
```

### 리밸런싱 알림
```python
def send_rebalance_notification(actions):
    message = "🔄 리밸런싱 실행\n\n"

    for action in actions:
        if action['type'] == 'BUY':
            message += f"📈 매수: {action['name']} {action['qty']}주\n"
        else:
            message += f"📉 매도: {action['name']} {action['qty']}주\n"

    message += f"\n총 {len(actions)}건 실행"
    send_message(message)
```

### 경고 알림
```python
ALERT_TEMPLATES = {
    "daily_loss": "⚠️ 일일 손실 -{loss:.1%} 경고",
    "stop_loss": "🛑 {stock} 손절 실행 (-{loss:.1%})",
    "take_profit": "✅ {stock} 익절 달성 (+{profit:.1%})",
    "api_error": "❌ API 오류 발생: {error}",
    "engine_stop": "🚨 엔진 비상 정지",
}
```

### 일간 리포트
```
📊 일간 리포트 (2024-12-26)

═══════════════════════
📈 수익률: +1.23%
💰 손익금: +₩1,230,000
═══════════════════════

거래 내역:
- 매수 3건 / 매도 2건
- 총 거래대금: ₩3,500,000

포트폴리오:
- 보유 종목: 18개
- 승률: 66.7% (4/6)
- 샤프비율: 1.85

상위 종목:
1. 삼성전자 +3.2%
2. NAVER +2.1%
3. 현대차 +1.8%

하위 종목:
1. LG화학 -2.1%
2. 카카오 -1.5%

다음 리밸런싱: 2025-01-02
═══════════════════════
```

## 메시지 형식 규칙

### HTML 파싱
```python
# 텔레그램은 HTML 지원
parse_mode = "HTML"

# 허용 태그
# <b>bold</b>
# <i>italic</i>
# <code>monospace</code>
# <pre>preformatted</pre>
# <a href="url">link</a>

# 특수문자 이스케이프
def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
```

### 메시지 길이
```python
MAX_MESSAGE_LENGTH = 4096  # 텔레그램 한도

def split_message(message):
    if len(message) <= MAX_MESSAGE_LENGTH:
        return [message]

    # 줄 단위로 분할
    lines = message.split("\n")
    chunks = []
    current = ""

    for line in lines:
        if len(current) + len(line) + 1 > MAX_MESSAGE_LENGTH:
            chunks.append(current)
            current = line
        else:
            current += "\n" + line if current else line

    if current:
        chunks.append(current)

    return chunks
```

## 접근 제어

### 사용자 인증
```python
AUTHORIZED_USERS = [
    int(os.getenv("TELEGRAM_CHAT_ID")),
]

ADMIN_USERS = [
    int(os.getenv("TELEGRAM_ADMIN_ID")),
]

def check_authorization(chat_id, required_level="user"):
    if required_level == "admin":
        return chat_id in ADMIN_USERS
    return chat_id in AUTHORIZED_USERS
```

### 명령어 권한
```python
def handle_command(update, context):
    chat_id = update.effective_chat.id
    command = update.message.text.split()[0][1:]  # Remove /

    # 권한 확인
    if command in ADMIN_COMMANDS:
        if not check_authorization(chat_id, "admin"):
            send_message(chat_id, "관리자 권한이 필요합니다.")
            return

    # 명령어 실행
    handlers[command](update, context)
```

## 에러 처리

```python
def safe_send_message(chat_id, message):
    try:
        bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML"
        )
        return True
    except TelegramError as e:
        logger.error(f"텔레그램 전송 실패: {e}")
        return False
    except Exception as e:
        logger.error(f"예상치 못한 오류: {e}")
        return False
```

## 속도 제한

```python
# 텔레그램 API 한도
MAX_MESSAGES_PER_SECOND = 30
MAX_MESSAGES_PER_MINUTE = 20  # 동일 채팅

# 큐 기반 전송
message_queue = Queue()

def queue_message(message):
    message_queue.put(message)

def message_sender():
    while True:
        message = message_queue.get()
        send_message(message)
        time.sleep(0.1)  # 100ms 간격
```
