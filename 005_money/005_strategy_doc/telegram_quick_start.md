# 🚀 텔레그램 알림 빠른 시작 가이드

5분 안에 텔레그램 알림을 설정하고 테스트하는 방법입니다.

---

## ⚡ 빠른 설정 (5분)

### 1단계: 텔레그램 봇 생성 (2분)

1. **텔레그램 앱 열기**

2. **@BotFather 검색 및 대화 시작**

3. **명령어 입력**:
```
/newbot
```

4. **봇 이름 입력** (예: `My Trading Alert Bot`)

5. **봇 사용자명 입력** (반드시 `bot`으로 끝나야 함):
```
mytradingalert_bot
```

6. **토큰 복사** (다음과 같은 형식):
```
1234567890:ABCdefGHIjklMNOpqrsTUVwxyz1234567890
```

### 2단계: Chat ID 획득 (1분)

1. **생성한 봇 검색 및 대화 시작**

2. **아무 메시지 전송** (예: `Hello`)

3. **브라우저에서 다음 URL 열기** (토큰 부분 교체):
```
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

4. **응답에서 `chat.id` 찾기**:
```json
{
  "result": [{
    "message": {
      "chat": {
        "id": 987654321  // <-- 이것을 복사
      }
    }
  }]
}
```

### 3단계: .env 설정 (1분)

`.env` 파일 열기:
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
nano .env  # 또는 vscode로 열기
```

다음 추가:
```bash
# Telegram Settings
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz1234567890
TELEGRAM_CHAT_ID=987654321
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

저장 후 종료 (nano: `Ctrl+X`, `Y`, `Enter`)

### 4단계: 테스트 (1분)

```bash
python test_telegram.py
```

성공 메시지 확인:
```
📱 Testing Telegram notifications...

✅ Telegram configured
   Bot Token: 1234567890...
   Chat ID: 987654321

Sending test message...
✅ Message sent successfully!
   Check your Telegram app
```

**완료! 🎉**

텔레그램 앱에서 메시지를 확인하세요.

---

## 📱 실제 사용

### CLI 모드로 봇 시작

```bash
./run_v3.sh
```

다음과 같은 알림을 받게 됩니다:
- 🚀 봇 시작 알림
- 🟢 매수 시도 및 결과
- 🔴 매도 시도 및 결과
- ⚠️ 에러 발생 시
- 🛑 봇 종료 알림

### GUI 모드로 봇 시작

```bash
python run_gui.py
```

GUI와 함께 텔레그램 알림도 받습니다.

---

## 🎛️ 알림 끄기/켜기

### 일시적으로 끄기

`.env` 파일 수정:
```bash
TELEGRAM_NOTIFICATIONS_ENABLED=False
```

봇 재시작 필요.

### 특정 알림만 선택적으로 받기

`.env`에 추가:
```bash
# 선택적 알림 설정
TELEGRAM_NOTIFY_BUY=True      # 매수 알림
TELEGRAM_NOTIFY_SELL=True     # 매도 알림
TELEGRAM_NOTIFY_ERROR=True    # 에러 알림
TELEGRAM_MIN_AMOUNT=50000     # 5만원 이상만 알림
```

---

## 🔍 문제 해결

### "Unauthorized" 에러

**원인**: Bot token이 잘못됨

**해결**:
```bash
# 1. .env 파일 확인
cat .env | grep TELEGRAM_BOT_TOKEN

# 2. 토큰 재확인 (BotFather에서 /mybots 명령)

# 3. .env 다시 설정
```

### "Chat not found" 에러

**원인**: Chat ID가 잘못되었거나 봇을 시작하지 않음

**해결**:
```bash
# 1. 봇에게 /start 메시지 전송

# 2. getUpdates로 Chat ID 재확인
curl "https://api.telegram.org/bot<TOKEN>/getUpdates"

# 3. .env 파일 업데이트
```

### 메시지가 오지 않음

**체크리스트**:
```bash
# 1. .env 파일 위치 확인
ls -la .env

# 2. 텔레그램 설정 확인
grep TELEGRAM .env

# 3. 테스트 스크립트 실행
python test_telegram.py

# 4. 봇이 차단되지 않았는지 확인 (텔레그램 앱에서)
```

---

## 📚 더 알아보기

### 상세 가이드
- `telegram_notification_guide.md` - 전체 기능 설명
- `telegram_implementation.md` - 코드 구현 상세

### 고급 기능
- 일일 거래 요약
- 포지션 모니터링
- 커스텀 알림 필터
- Rate limiting

---

## 💡 팁

### 그룹으로 알림 받기

1. 그룹 생성
2. 봇을 그룹에 추가
3. 그룹에서 봇에게 메시지 전송
4. getUpdates로 그룹 Chat ID 확인 (음수값)
5. `.env`에 그룹 Chat ID 설정

### 여러 채널에 알림

현재는 하나의 Chat ID만 지원합니다.
여러 채널에 보내려면:

```python
# telegram_notifier.py 수정
self.chat_ids = os.getenv("TELEGRAM_CHAT_ID", "").split(",")

def send_message(self, message):
    for chat_id in self.chat_ids:
        # 각 채널에 전송
```

`.env`:
```bash
TELEGRAM_CHAT_ID=123456789,987654321,-1001234567890
```

### 모바일과 데스크톱에서 모두 받기

- 개인 Chat ID를 사용하면 모든 기기에서 알림 수신
- 별도 설정 불필요 (텔레그램 클라우드 동기화)

---

## ✅ 체크리스트

설정 완료:
- [ ] BotFather에서 봇 생성
- [ ] Bot token 복사
- [ ] Chat ID 획득
- [ ] `.env` 파일 설정
- [ ] `test_telegram.py` 테스트 성공

실사용:
- [ ] 봇 시작 알림 수신
- [ ] 거래 알림 테스트 (Dry run)
- [ ] 에러 알림 테스트
- [ ] 프로덕션 배포

**모든 준비 완료! 🚀**

이제 거래가 발생할 때마다 텔레그램으로 알림을 받습니다.

---

## 🆘 도움이 필요하신가요?

1. **공식 문서**: https://core.telegram.org/bots
2. **상세 가이드**: `telegram_notification_guide.md`
3. **구현 가이드**: `telegram_implementation.md`

**Happy Trading! 📈**
