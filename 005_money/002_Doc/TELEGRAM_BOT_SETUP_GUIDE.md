# Telegram 봇 설정 가이드

## 1. 개요

이 가이드는 Telegram 봇을 생성하고, 자동매매 봇과 연동하여 실시간 거래 알림을 받는 방법을 설명합니다.

---

## 2. Telegram 봇 알림 기능

### 2.1 제공되는 알림 유형

| 알림 유형 | 이모지 | 설명 |
|----------|--------|------|
| **거래 알림** | 🟢 / 🔴 | 매수/매도 실행 결과 |
| **에러 알림** | ⚠️ | API 오류, 주문 실패 |
| **봇 상태** | 🚀 / 🛑 | 봇 시작/종료 알림 |
| **일일 요약** | 📈 | 일별 거래 통계 |

### 2.2 알림 예시

```
🟢 BUY 성공

📊 코인: BTC
💰 수량: 0.00100000
💵 가격: 50,000,000 KRW
💸 총액: 50,000 KRW

⏰ 시각: 2025-12-10 14:30:45
📝 사유: Entry score: 4/4, regime: bullish
🔖 주문ID: 20251210143045_BTC_BUY
```

---

## 3. Telegram 봇 생성

### 3.1 BotFather 접속

1. Telegram 앱 실행
2. 검색창에 `@BotFather` 입력
3. 공식 BotFather 선택 (파란색 체크 마크 확인)

### 3.2 새 봇 생성

1. BotFather 채팅창에서 `/newbot` 명령어 입력

2. **봇 이름** 입력 (표시 이름)
   ```
   My Trading Bot
   ```

3. **봇 username** 입력 (고유 ID, `_bot`으로 끝나야 함)
   ```
   my_crypto_trading_bot
   ```

4. **Bot Token** 수신 및 저장
   ```
   Done! Congratulations on your new bot. You will find it at t.me/my_crypto_trading_bot.

   Use this token to access the HTTP API:
   1234567890:ABCDefGhIJKlmnOPQrstUVWxyZ

   Keep your token secure and store it safely.
   ```

> **중요**: Bot Token은 절대 외부에 공개하지 마세요!

---

## 4. Chat ID 확인

### 4.1 봇에 메시지 전송

1. Telegram에서 생성한 봇 검색 (`@my_crypto_trading_bot`)
2. `/start` 버튼 클릭 또는 아무 메시지 전송
3. 이 단계가 필수입니다 (봇이 메시지를 받아야 Chat ID 확인 가능)

### 4.2 Chat ID 조회

#### 방법 1: 브라우저에서 확인

```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

예시:
```
https://api.telegram.org/bot1234567890:ABCDefGhIJKlmnOPQrstUVWxyZ/getUpdates
```

응답 예시:
```json
{
  "ok": true,
  "result": [
    {
      "update_id": 123456789,
      "message": {
        "message_id": 1,
        "from": {
          "id": 987654321,
          "first_name": "Your Name"
        },
        "chat": {
          "id": 987654321,
          "first_name": "Your Name",
          "type": "private"
        },
        "text": "/start"
      }
    }
  ]
}
```

→ `"chat": {"id": 987654321}` 부분이 **Chat ID**입니다.

#### 방법 2: 터미널에서 확인

```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates" | jq '.result[0].message.chat.id'
```

#### 방법 3: Python 스크립트로 확인

```python
import requests

BOT_TOKEN = "your_bot_token_here"
response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates")
data = response.json()

if data["result"]:
    chat_id = data["result"][0]["message"]["chat"]["id"]
    print(f"Your Chat ID: {chat_id}")
else:
    print("No messages found. Please send a message to your bot first.")
```

---

## 5. 환경 설정

### 5.1 .env 파일 수정

```bash
# .env 파일 편집
nano .env
```

### 5.2 Telegram 설정 추가

```bash
# ===================================
# Telegram Notification Settings
# ===================================

# Telegram Bot Token (@BotFather에서 발급)
TELEGRAM_BOT_TOKEN=1234567890:ABCDefGhIJKlmnOPQrstUVWxyZ

# Telegram Chat ID (본인의 Chat ID)
TELEGRAM_CHAT_ID=987654321

# Telegram 알림 활성화 여부
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

---

## 6. 연결 테스트

### 6.1 테스트 스크립트 실행

```bash
# 가상환경 활성화
source .venv/bin/activate

# 테스트 실행
python tests/test_telegram.py
```

### 6.2 예상 결과 (성공 시)

```
============================================================
Telegram Bot Connection Test
============================================================

[1] Testing Bot Token...
    Bot Name: my_crypto_trading_bot
    Status: OK

[2] Sending Test Message...
    Message sent successfully!
    Check your Telegram app.

============================================================
```

### 6.3 Telegram에서 확인

테스트 성공 시 다음과 같은 메시지가 Telegram에 도착합니다:

```
🧪 테스트 메시지

Trading Bot이 정상적으로 연결되었습니다!

⏰ 시각: 2025-12-10 14:30:00
```

---

## 7. 알림 설정 커스터마이징

### 7.1 config_v3.py에서 알림 설정

```python
# 001_python_code/ver3/config_v3.py

TELEGRAM_CONFIG = {
    # 알림 활성화
    'enabled': True,

    # 알림 유형별 설정
    'notify_on_buy': True,           # 매수 알림
    'notify_on_sell': True,          # 매도 알림
    'notify_on_stop_loss': True,     # 손절 알림
    'notify_on_take_profit': True,   # 이익실현 알림
    'notify_on_error': True,         # 에러 알림
    'notify_on_bot_status': True,    # 봇 상태 알림

    # 일일 요약 알림
    'daily_summary_enabled': True,
    'daily_summary_time': '21:00',   # 매일 21:00에 전송

    # 재시도 설정
    'max_retries': 3,
    'retry_delay_seconds': 2,
}
```

### 7.2 알림 비활성화

특정 알림만 비활성화하고 싶은 경우:

```python
# 에러 알림만 비활성화
'notify_on_error': False,

# 봇 상태 알림만 비활성화
'notify_on_bot_status': False,
```

### 7.3 전체 비활성화

```bash
# .env 파일
TELEGRAM_NOTIFICATIONS_ENABLED=False
```

---

## 8. 그룹 채팅에서 사용

### 8.1 그룹에 봇 추가

1. Telegram 그룹 생성 또는 기존 그룹 열기
2. 그룹 설정 → 구성원 추가
3. 봇 username 검색하여 추가 (`@my_crypto_trading_bot`)

### 8.2 그룹 Chat ID 확인

그룹의 Chat ID는 음수(-)로 시작합니다:

```
-1001234567890
```

### 8.3 봇 관리자 권한 설정

그룹에서 봇이 메시지를 보내려면 관리자 권한이 필요할 수 있습니다:

1. 그룹 설정 → 관리자
2. 봇을 관리자로 추가
3. "메시지 보내기" 권한 활성화

---

## 9. 트러블슈팅

### 9.1 일반적인 오류

#### 오류 1: Bot Token 오류

```
Error: Unauthorized
```

**해결 방법**:

- Bot Token이 정확한지 확인
- Token에 공백이나 줄바꿈이 없는지 확인
- BotFather에서 Token 재생성 (`/token` 명령어)

#### 오류 2: Chat ID 오류

```
Error: Chat not found
```

**해결 방법**:

- Chat ID가 정확한지 확인
- 봇에게 최소 1개 이상의 메시지를 보냈는지 확인
- 그룹 사용 시 `-` 기호 포함 확인

#### 오류 3: 메시지 전송 실패

```
Error: Bad Request: can't parse entities
```

**해결 방법**:

- 메시지 형식 오류 (Markdown 문법 확인)
- 특수 문자 이스케이프 처리

#### 오류 4: 네트워크 오류

```
Error: Connection timed out
```

**해결 방법**:

- 인터넷 연결 확인
- 방화벽에서 Telegram API 차단 여부 확인
- VPN 사용 시 비활성화 후 재시도

### 9.2 로그 확인

```bash
# Telegram 관련 로그만 필터링
grep -i "telegram" logs/ver3_cli_$(date +%Y%m%d).log

# 에러 로그 확인
grep -i "telegram.*error\|telegram.*fail" logs/ver3_cli_$(date +%Y%m%d).log
```

---

## 10. 보안 권장사항

### 10.1 Bot Token 보안

| 항목 | 권장 사항 |
|------|----------|
| **저장 위치** | `.env` 파일에만 저장 |
| **Git 커밋** | 절대 금지 (`.gitignore`에 추가) |
| **공유** | 다른 사람과 공유 금지 |
| **갱신** | 노출 의심 시 즉시 재발급 |

### 10.2 Token 재발급 방법

1. BotFather 채팅창 열기
2. `/revoke` 명령어 입력
3. 재발급할 봇 선택
4. 새 Token 발급 및 `.env` 파일 업데이트

### 10.3 봇 삭제 방법

1. BotFather 채팅창 열기
2. `/deletebot` 명령어 입력
3. 삭제할 봇 선택
4. 확인

---

## 11. 고급 기능

### 11.1 봇 프로필 설정

BotFather에서 봇 프로필을 꾸밀 수 있습니다:

```
/setname - 봇 표시 이름 변경
/setdescription - 봇 설명 설정
/setabouttext - 봇 소개 텍스트 설정
/setuserpic - 봇 프로필 사진 설정
```

### 11.2 명령어 등록 (선택사항)

BotFather에서 봇 명령어를 등록할 수 있습니다:

```
/setcommands
```

명령어 목록 예시:
```
status - 봇 상태 확인
positions - 현재 포지션 조회
summary - 오늘 거래 요약
```

> 참고: 현재 시스템은 단방향 알림만 지원합니다. 봇 명령어 기능은 추후 개발 예정입니다.

---

## 12. 참고 자료

### 공식 문서

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [BotFather 공식 가이드](https://core.telegram.org/bots#botfather)

### 관련 가이드

- [BITHUMB_API_SETUP_GUIDE.md](./BITHUMB_API_SETUP_GUIDE.md) - 빗썸 API 설정
- [TESTING_GUIDE.md](./TESTING_GUIDE.md) - 테스트 방법 가이드

---

**작성일**: 2025년 12월 10일
