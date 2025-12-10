# Bithumb API 설정 가이드

## 1. 개요

이 가이드는 빗썸(Bithumb) 거래소의 API 키를 발급받고, 자동매매 봇에 연동하는 방법을 설명합니다.

---

## 2. 사전 준비사항

### 2.1 빗썸 계정 요구사항

- [x] 빗썸 회원 가입 완료
- [x] 본인 인증 완료 (Level 2 이상 권장)
- [x] OTP 인증 설정 (필수)
- [x] 거래 가능 상태 확인

### 2.2 시스템 요구사항

- Python 3.8 이상
- pip (Python 패키지 관리자)
- Git (pybithumb 라이브러리 설치용)

---

## 3. API 키 발급 방법

### 3.1 빗썸 웹사이트 접속

1. [빗썸 공식 웹사이트](https://www.bithumb.com) 접속
2. 계정 로그인

### 3.2 API 관리 페이지 이동

1. 우측 상단 **프로필 아이콘** 클릭
2. **마이페이지** 선택
3. 좌측 메뉴에서 **API 관리** 클릭

### 3.3 API 키 생성

1. **API Key 발급** 버튼 클릭
2. OTP 인증 코드 입력
3. API 권한 설정:

| 권한 | 설명 | 권장 설정 |
|------|------|----------|
| **조회** | 잔고, 거래내역 조회 | 활성화 |
| **거래** | 주문 생성/취소 | 활성화 |
| **출금** | 암호화폐/원화 출금 | **비활성화** (보안) |

4. **발급** 버튼 클릭
5. **Connect Key**와 **Secret Key** 저장

> **중요**: Secret Key는 발급 시 한 번만 표시됩니다. 반드시 안전한 곳에 저장하세요!

### 3.4 IP 화이트리스트 설정 (선택사항)

보안 강화를 위해 특정 IP에서만 API를 사용하도록 제한할 수 있습니다.

1. API 관리 페이지에서 해당 API 키 선택
2. **IP 화이트리스트** 설정 클릭
3. 사용할 IP 주소 입력 (서버 IP 또는 공인 IP)
4. 저장

```bash
# 현재 공인 IP 확인 방법
curl ifconfig.me
```

---

## 4. 환경 설정

### 4.1 프로젝트 디렉토리로 이동

```bash
cd /path/to/005_money
```

### 4.2 가상환경 생성 및 활성화

```bash
# 가상환경 생성
python3 -m venv .venv

# 가상환경 활성화 (macOS/Linux)
source .venv/bin/activate

# 가상환경 활성화 (Windows)
.venv\Scripts\activate
```

### 4.3 의존성 설치

```bash
pip install -r requirements.txt
```

### 4.4 pybithumb 라이브러리 설치

```bash
# 자동으로 클론되지만, 수동 설치도 가능
git clone --depth 1 https://github.com/sharebook-kr/pybithumb.git
```

### 4.5 .env 파일 생성

```bash
# .env.example 파일 복사
cp .env.example .env

# 편집기로 .env 파일 열기
nano .env  # 또는 vim, code 등
```

### 4.6 .env 파일 설정

```bash
# ===================================
# Bithumb API Credentials
# ===================================
# 빗썸에서 발급받은 API 키 입력
BITHUMB_CONNECT_KEY=your_connect_key_here
BITHUMB_SECRET_KEY=your_secret_key_here

# ===================================
# Trading Mode
# ===================================
# True: 시뮬레이션 모드 (실제 주문 미실행)
# False: 실거래 모드 (실제 주문 실행)
DRY_RUN=True

# ===================================
# Trading Parameters
# ===================================
TRADE_AMOUNT_KRW=50000
MAX_POSITIONS=2
CHECK_INTERVAL_MINUTES=15
```

---

## 5. API 연결 테스트

### 5.1 테스트 스크립트 실행

```bash
# 가상환경 활성화 확인
source .venv/bin/activate

# 테스트 실행
python tests/test_api_connection.py
```

### 5.2 예상 출력 (성공 시)

```
============================================================
Bithumb API Connection Test
============================================================

[1] Testing Public API (Ticker)...
    BTC/KRW: 50,000,000 KRW
    ETH/KRW: 3,000,000 KRW
    XRP/KRW: 800 KRW

[2] Testing Private API (Balance)...
    KRW Balance: 1,000,000 KRW
    BTC Balance: 0.00100000 BTC
    ETH Balance: 0.01000000 ETH

[3] API Connection Status: SUCCESS

============================================================
```

### 5.3 일반적인 오류 및 해결 방법

#### 오류 1: API 인증 실패 (401 Unauthorized)

```
Error: Invalid API key
```

**해결 방법**:

- `.env` 파일의 API 키가 올바른지 확인
- API 키에 공백이나 따옴표가 포함되지 않았는지 확인
- API 키가 활성화 상태인지 빗썸에서 확인

#### 오류 2: IP 제한 오류

```
Error: IP address not allowed
```

**해결 방법**:

- 빗썸 API 관리에서 IP 화이트리스트 확인
- 현재 공인 IP가 화이트리스트에 포함되어 있는지 확인

#### 오류 3: 권한 부족

```
Error: Permission denied
```

**해결 방법**:

- API 키에 필요한 권한(조회, 거래)이 활성화되어 있는지 확인

#### 오류 4: 모듈 없음 오류

```
ModuleNotFoundError: No module named 'pybithumb'
```

**해결 방법**:

```bash
# pybithumb 수동 설치
git clone --depth 1 https://github.com/sharebook-kr/pybithumb.git
```

---

## 6. 보안 권장사항

### 6.1 API 키 보안

| 항목 | 권장 사항 |
|------|----------|
| **출금 권한** | 반드시 비활성화 |
| **IP 화이트리스트** | 가능하면 설정 |
| **Secret Key 저장** | `.env` 파일에만 저장, Git에 커밋 금지 |
| **정기 갱신** | 3-6개월마다 API 키 재발급 권장 |

### 6.2 .gitignore 확인

```bash
# .gitignore 파일에 다음 내용이 포함되어 있는지 확인
.env
.env.local
*.key
```

### 6.3 환경변수 확인

```bash
# 환경변수가 노출되지 않도록 확인
echo $BITHUMB_CONNECT_KEY  # 출력되면 안 됨

# .env 파일 권한 설정 (소유자만 읽기/쓰기)
chmod 600 .env
```

---

## 7. API 사용량 제한

### 7.1 빗썸 API Rate Limit

| API 유형 | 제한 | 설명 |
|----------|------|------|
| **Public API** | 135회/초 | Ticker, Orderbook 등 |
| **Private API** | 15회/초 | 잔고 조회, 주문 등 |

### 7.2 본 시스템의 API 호출 빈도

- **분석 주기**: 15분마다 1회
- **코인당 호출**: 약 3-4회 (Ticker, Candle 등)
- **총 호출**: 3개 코인 × 4회 = 12회/15분 = 0.013회/초

> Rate Limit에 여유가 있으므로 걱정하지 않아도 됩니다.

---

## 8. 트러블슈팅

### 8.1 자주 묻는 질문

**Q: API 키 발급 후 바로 사용 가능한가요?**

A: 네, 발급 즉시 사용 가능합니다. 다만 IP 화이트리스트 설정 시 약간의 지연이 있을 수 있습니다.

**Q: OTP 인증이 필수인가요?**

A: 네, 빗썸에서 API 키 발급 시 OTP 인증이 필수입니다.

**Q: API 키를 분실했어요.**

A: Secret Key는 재확인이 불가능합니다. 기존 키를 삭제하고 새로 발급받아야 합니다.

**Q: 거래 수수료는 어떻게 되나요?**

A: 빗썸의 기본 거래 수수료는 0.04%입니다. 쿠폰이나 멤버십에 따라 할인될 수 있습니다.

### 8.2 로그 확인

문제 발생 시 로그 파일을 확인하세요:

```bash
# 최근 로그 확인
tail -100 logs/ver3_cli_$(date +%Y%m%d).log

# API 관련 에러만 필터링
grep -i "api\|error\|fail" logs/ver3_cli_$(date +%Y%m%d).log
```

---

## 9. 참고 자료

### 공식 문서

- [빗썸 API 공식 문서](https://apidocs.bithumb.com/)
- [pybithumb GitHub](https://github.com/sharebook-kr/pybithumb)

### 관련 가이드

- [TELEGRAM_BOT_SETUP_GUIDE.md](./TELEGRAM_BOT_SETUP_GUIDE.md) - Telegram 알림 설정
- [TESTING_GUIDE.md](./TESTING_GUIDE.md) - 테스트 방법 가이드

---

**작성일**: 2025년 12월 10일
