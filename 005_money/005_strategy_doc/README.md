# 📱 텔레그램 알림 통합 문서

Ver3 Cryptocurrency Trading Bot에 텔레그램 알림 기능을 추가하는 완벽 가이드입니다.

---

## 📚 문서 목록

### 1. 🚀 [빠른 시작 가이드](telegram_quick_start.md)
**5분 안에 설정 완료!**

- 텔레그램 봇 생성
- Chat ID 획득
- `.env` 설정
- 즉시 테스트

**누구를 위한 문서**: 빠르게 시작하고 싶은 모든 사용자

**읽는 시간**: 5분

---

### 2. 📖 [완전한 기능 가이드](telegram_notification_guide.md)
**모든 기능과 옵션 설명**

- 준비사항 상세 설명
- BotFather 사용법
- 필요한 라이브러리
- 코드 구현 예제
- Trading bot 통합 방법
- 문제 해결 가이드

**누구를 위한 문서**: 기능을 완전히 이해하고 싶은 사용자

**읽는 시간**: 20분

---

### 3. 🔧 [실제 구현 가이드](telegram_implementation.md)
**단계별 코드 구현**

- 파일 구조
- Step-by-step 구현
- 실제 코드 예제
- 테스트 방법
- 알림 예시
- 고급 설정

**누구를 위한 문서**: 직접 코드를 수정하거나 추가 기능을 구현하려는 개발자

**읽는 시간**: 30분

---

## 🎯 어떤 문서를 읽어야 할까요?

### 처음 사용하는 경우
1. ✅ [빠른 시작 가이드](telegram_quick_start.md) - 설정 및 테스트
2. ✅ [완전한 기능 가이드](telegram_notification_guide.md) - 전체 이해

### 코드를 수정하려는 경우
1. ✅ [완전한 기능 가이드](telegram_notification_guide.md) - 아키텍처 이해
2. ✅ [실제 구현 가이드](telegram_implementation.md) - 코드 구현

### 문제가 발생한 경우
1. ✅ [빠른 시작 가이드](telegram_quick_start.md) - 문제 해결 섹션
2. ✅ [완전한 기능 가이드](telegram_notification_guide.md) - 문제 해결 섹션

---

## 🔔 받을 수 있는 알림

### 거래 알림
- 🟢 **매수 성공**: 코인, 수량, 가격, 사유
- 🔴 **매도 성공**: 코인, 수량, 가격, 수익률
- ❌ **거래 실패**: 에러 메시지 및 상세 정보

### 시스템 알림
- 🚀 **봇 시작**: 모니터링 코인, 최대 포지션
- 🛑 **봇 종료**: 현재 포지션, 총 손익
- ⚠️ **에러 발생**: 에러 타입, 메시지, 상세 정보

### 요약 알림 (선택사항)
- 📊 **일일 거래 요약**: 매수/매도 횟수, 총 거래액, 순손익

---

## ⚙️ 필요한 사항

### 텔레그램
- ✅ 텔레그램 계정
- ✅ Bot Token (BotFather에서 발급)
- ✅ Chat ID (개인 또는 그룹)

### Python 환경
- ✅ Python 3.8 이상
- ✅ `requests` 라이브러리
- ✅ (선택) `python-telegram-bot` 라이브러리

### 환경 변수
```bash
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_NOTIFICATIONS_ENABLED=True
```

---

## 📋 구현 체크리스트

### 준비 단계
- [ ] 텔레그램 봇 생성 (BotFather)
- [ ] Bot Token 발급
- [ ] Chat ID 획득
- [ ] `.env` 파일에 설정 추가

### 코드 구현
- [ ] `telegram_notifier.py` 생성
- [ ] `live_executor_v3.py` 수정
- [ ] `trading_bot_v3.py` 수정
- [ ] `requirements.txt` 업데이트

### 테스트
- [ ] `test_telegram.py` 실행
- [ ] 테스트 메시지 수신 확인
- [ ] 봇 시작/종료 알림 테스트
- [ ] Dry run 모드에서 거래 알림 테스트

### 프로덕션
- [ ] 실제 환경 `.env` 설정
- [ ] 알림 필터 설정 (선택)
- [ ] Rate limiting 설정 (선택)
- [ ] 모니터링 시작

---

## 💡 빠른 링크

### 설정
- [BotFather](https://t.me/botfather) - 봇 생성
- [Telegram API](https://core.telegram.org/bots/api) - 공식 문서
- [getUpdates 테스트](https://api.telegram.org/bot<TOKEN>/getUpdates) - Chat ID 확인

### 코드 위치
```
005_money/
├── 001_python_code/
│   ├── lib/core/telegram_notifier.py          # 생성 필요
│   ├── ver3/live_executor_v3.py               # 수정 필요
│   └── ver3/trading_bot_v3.py                 # 수정 필요
├── .env                                       # 설정 추가
├── requirements.txt                           # 업데이트
└── test_telegram.py                           # 생성 필요
```

---

## 🆘 문제 해결

### 일반적인 문제

1. **"Unauthorized" 에러**
   - Bot token 확인
   - `.env` 파일 위치 확인

2. **"Chat not found" 에러**
   - 봇에게 `/start` 전송
   - Chat ID 재확인

3. **메시지가 오지 않음**
   - `test_telegram.py` 실행
   - `.env` 설정 확인
   - 봇이 차단되지 않았는지 확인

4. **Rate limit 에러**
   - 알림 빈도 줄이기
   - 중요한 알림만 활성화

### 상세 트러블슈팅
각 가이드 문서의 "문제 해결" 섹션 참조

---

## 🌟 주요 기능

### ✅ 구현 완료
- 실시간 거래 알림
- 에러 알림
- 봇 상태 알림
- 마크다운 포맷 지원
- 환경변수 기반 설정
- Dry run 모드 지원

### 🔜 추가 가능 기능
- 일일/주간 거래 요약
- 포지션 모니터링 명령어
- 인터랙티브 봇 명령어 (/status, /stop)
- 다중 채널 알림
- 알림 레벨 설정 (ERROR, WARNING, INFO)
- 커스텀 알림 템플릿

---

## 📈 사용 통계

### 알림 빈도 (예상)
- **Dry run**: 0-5회/일 (테스트)
- **Live trading**: 5-20회/일 (거래량에 따라)
- **에러**: 0-2회/일 (정상 작동 시)

### 데이터 사용량
- 텍스트 메시지: ~1KB/메시지
- 하루 20개 알림: ~20KB/일
- 한 달: ~600KB/월

**거의 무시할 수 있는 수준** ✅

---

## 🔒 보안 고려사항

### ✅ 안전한 방법
- Bot token을 `.env` 파일에 저장
- `.gitignore`에 `.env` 추가
- 환경변수로 관리

### ❌ 피해야 할 것
- 코드에 토큰 하드코딩
- 공개 저장소에 토큰 업로드
- 토큰을 채팅방에 공유

### 토큰이 노출된 경우
1. BotFather에서 `/revoke` 명령
2. 새 토큰 발급
3. `.env` 파일 업데이트

---

## 📞 지원

### 공식 리소스
- [Telegram Bot API 문서](https://core.telegram.org/bots/api)
- [python-telegram-bot 문서](https://docs.python-telegram-bot.org/)
- [BotFather 명령어](https://core.telegram.org/bots#6-botfather)

### 프로젝트 문서
- `telegram_quick_start.md` - 빠른 시작
- `telegram_notification_guide.md` - 완전한 가이드
- `telegram_implementation.md` - 구현 상세

---

## 🎉 시작하기

**지금 바로 시작하세요!**

```bash
# 1. 문서 읽기
cat 005_strategy_doc/telegram_quick_start.md

# 2. 봇 생성 (텔레그램 앱에서)
@BotFather에게 /newbot 전송

# 3. .env 설정
nano .env

# 4. 테스트
python test_telegram.py

# 5. 봇 실행
./run_v3.sh
```

**5분 만에 완료! 🚀**

---

## 📄 라이선스

이 문서는 Ver3 Cryptocurrency Trading Bot 프로젝트의 일부입니다.

**Last Updated**: 2025-12-09  
**Version**: 1.0.0

---

**Happy Trading with Real-time Notifications! 📱📈**
