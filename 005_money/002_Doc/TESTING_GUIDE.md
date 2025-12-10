# 테스트 가이드

## 1. 개요

이 가이드는 암호화폐 자동매매 봇의 테스트 방법을 설명합니다. 실거래 전 반드시 충분한 테스트를 수행하세요.

---

## 2. 테스트 환경 설정

### 2.1 가상환경 활성화

```bash
cd /path/to/005_money
source .venv/bin/activate
```

### 2.2 테스트 디렉토리 구조

```
005_money/
├── tests/                         # 테스트 스크립트
│   ├── test_api_connection.py     # API 연결 테스트
│   ├── test_telegram.py           # Telegram 연결 테스트
│   ├── test_strategy.py           # 전략 로직 테스트
│   └── test_executor.py           # 주문 실행 테스트
└── logs/                          # 테스트 로그
```

---

## 3. API 연결 테스트

### 3.1 빗썸 API 테스트

#### 테스트 스크립트 실행

```bash
python tests/test_api_connection.py
```

#### 테스트 내용

| 테스트 항목 | 설명 |
|------------|------|
| Public API | Ticker, Orderbook 조회 |
| Private API | 잔고 조회, 주문 권한 확인 |
| Rate Limit | API 호출 제한 확인 |

#### 예상 출력 (성공)

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

[3] API Connection Status: SUCCESS
============================================================
```

### 3.2 Telegram 연결 테스트

#### 테스트 스크립트 실행

```bash
python tests/test_telegram.py
```

#### 테스트 내용

| 테스트 항목 | 설명 |
|------------|------|
| Bot Token 검증 | Token 유효성 확인 |
| Chat ID 검증 | Chat ID 유효성 확인 |
| 메시지 전송 | 테스트 메시지 전송 |

#### 예상 출력 (성공)

```
============================================================
Telegram Bot Connection Test
============================================================

[1] Testing Bot Token...
    Bot Name: my_crypto_trading_bot
    Status: OK

[2] Sending Test Message...
    Message sent successfully!

============================================================
```

---

## 4. 시뮬레이션 모드 테스트 (Dry-Run)

### 4.1 Dry-Run 모드 설정

```bash
# .env 파일
DRY_RUN=True
```

### 4.2 CLI 모드 테스트

```bash
# Ver3 CLI 실행 (시뮬레이션)
./scripts/run_v3_cli.sh
```

#### 예상 출력

```
============================================================
Trading Bot V3 Started [DRY-RUN MODE]
============================================================
  Version: ver3
  Mode: SIMULATION (No real orders)
  Coins: BTC, ETH, XRP
  Max Positions: 2
============================================================

Analysis Cycle #1 - 2025-12-10 14:30:00

Analyzing BTC...
  Market Regime: bullish
  Entry Score: 4/4
  Action: BUY

[DRY-RUN] Simulating BUY: 0.001000 BTC @ 50,000,000 KRW
  Order ID: DRY_RUN_BUY_1702184200
  Status: SIMULATED SUCCESS
```

### 4.3 테스트 포인트

| 확인 사항 | 설명 |
|----------|------|
| **[DRY-RUN] 표시** | 로그에 DRY-RUN이 명시되어야 함 |
| **SIMULATED** | 주문 결과가 SIMULATED로 표시 |
| **실제 주문 없음** | 빗썸 거래 내역에 주문이 없어야 함 |
| **포지션 추적** | 가상 포지션이 정상적으로 추적됨 |

### 4.4 GUI 모드 테스트

```bash
# Ver3 GUI 실행 (시뮬레이션)
./scripts/run_v3_gui.sh
```

#### GUI 테스트 체크리스트

- [ ] GUI 창이 정상적으로 열림
- [ ] 거래 현황 탭에 로그가 표시됨
- [ ] 실시간 차트가 업데이트됨
- [ ] [DRY-RUN] 모드 표시 확인
- [ ] 시작/중지 버튼이 작동함

---

## 5. 전략 로직 테스트

### 5.1 지표 계산 테스트

```bash
python tests/test_strategy.py
```

#### 테스트 내용

| 테스트 항목 | 설명 |
|------------|------|
| Bollinger Bands | 상단/중간/하단 밴드 계산 |
| RSI | 과매수/과매도 계산 |
| Stochastic RSI | K/D 라인 계산 |
| ATR | 변동성 계산 |

#### 예상 출력

```
============================================================
Strategy Logic Test
============================================================

[1] Testing Bollinger Bands Calculation...
    BB Upper: 51,500,000
    BB Middle: 50,000,000
    BB Lower: 48,500,000
    Status: PASS

[2] Testing RSI Calculation...
    RSI: 28.5 (Oversold)
    Status: PASS

[3] Testing Entry Score Calculation...
    Score: 4/4
    Details: BB touch ✓, RSI<30 ✓, Stoch cross<20 ✓
    Status: PASS

============================================================
All tests passed!
```

### 5.2 시장 체제 테스트

```bash
python tests/test_market_regime.py
```

#### 테스트 시나리오

| 시나리오 | EMA50 vs EMA200 | 예상 결과 |
|----------|-----------------|----------|
| 상승장 | EMA50 > EMA200 | bullish |
| 하락장 | EMA50 < EMA200 | bearish |
| 교차 시점 | EMA50 ≈ EMA200 | neutral |

### 5.3 진입/청산 로직 테스트

```bash
python tests/test_entry_exit.py
```

#### 테스트 케이스

| 케이스 | 조건 | 예상 액션 |
|--------|------|----------|
| 강한 매수 신호 | Score 4/4, Bullish | BUY |
| 중간 매수 신호 | Score 3/4, Bullish | BUY |
| 약한 신호 | Score 2/4 | HOLD |
| 하락장 | Score 4/4, Bearish | HOLD |
| TP1 도달 | Price >= BB Middle | PARTIAL_SELL_50 |
| TP2 도달 | Price >= BB Upper | SELL |
| 손절 | Price <= Stop Loss | SELL |

---

## 6. 주문 실행 테스트

### 6.1 주문 실행 시뮬레이션

```bash
python tests/test_executor.py
```

#### 테스트 내용

| 테스트 항목 | 설명 |
|------------|------|
| 매수 주문 | 시뮬레이션 매수 |
| 매도 주문 | 시뮬레이션 매도 |
| 부분 청산 | 50% 매도 |
| 손절 실행 | 손절가 도달 시 매도 |
| 소수점 처리 | 빗썸 소수점 제한 준수 |

#### 예상 출력

```
============================================================
Order Execution Test [DRY-RUN]
============================================================

[1] Testing Buy Order...
    [DRY-RUN] BUY 0.00100000 BTC @ 50,000,000 KRW
    Order ID: DRY_RUN_BUY_1702184200
    Status: PASS

[2] Testing Sell Order...
    [DRY-RUN] SELL 0.00050000 BTC @ 51,000,000 KRW
    Order ID: DRY_RUN_SELL_1702184201
    Status: PASS

[3] Testing Position Update...
    Position after buy: 0.00100000 BTC
    Position after sell: 0.00050000 BTC
    Status: PASS

============================================================
```

### 6.2 포지션 상태 테스트

```bash
python tests/test_position.py
```

#### 테스트 내용

| 테스트 항목 | 설명 |
|------------|------|
| 포지션 생성 | 매수 후 포지션 생성 확인 |
| 포지션 업데이트 | 부분 청산 후 업데이트 |
| 포지션 삭제 | 전량 청산 후 삭제 |
| 상태 저장/로드 | JSON 파일 영속화 |

---

## 7. 통합 테스트

### 7.1 전체 사이클 테스트

```bash
python tests/test_full_cycle.py
```

#### 테스트 시나리오

1. **분석 사이클**: 3개 코인 동시 분석
2. **진입 결정**: 점수 기반 진입 결정
3. **주문 실행**: 시뮬레이션 주문
4. **포지션 추적**: 포지션 상태 확인
5. **청산 결정**: TP/SL 조건 확인
6. **알림 전송**: Telegram 알림 확인

### 7.2 장시간 테스트

시뮬레이션 모드로 최소 24시간 이상 실행하여 안정성을 확인합니다:

```bash
# 백그라운드에서 실행
nohup ./scripts/run_v3_cli.sh > logs/long_test.log 2>&1 &

# 로그 모니터링
tail -f logs/long_test.log

# 프로세스 확인
ps aux | grep trading_bot

# 종료
pkill -f trading_bot_v3
```

#### 확인 사항

- [ ] 메모리 누수 없음 (메모리 사용량 일정)
- [ ] 에러 없이 분석 사이클 반복
- [ ] 포지션 상태 정확히 추적
- [ ] 로그 파일 정상 기록

---

## 8. 실거래 전 최종 체크리스트

### 8.1 시스템 체크

- [ ] API 연결 테스트 통과
- [ ] Telegram 연결 테스트 통과
- [ ] 시뮬레이션 모드 최소 1주일 운영
- [ ] 에러 로그 검토 완료
- [ ] 메모리/CPU 사용량 정상

### 8.2 설정 체크

- [ ] DRY_RUN=False로 변경
- [ ] 초기 투자 금액 소액 설정 (10,000원 권장)
- [ ] max_positions=1로 시작
- [ ] Telegram 알림 활성화

### 8.3 리스크 체크

- [ ] API 키 출금 권한 비활성화
- [ ] 손절가 로직 정상 작동 확인
- [ ] 비상 정지 방법 숙지

### 8.4 실거래 시작

```bash
# .env 파일 수정
DRY_RUN=False
TRADE_AMOUNT_KRW=10000

# 실행
./scripts/run_v3_cli.sh
```

> **주의**: 실거래 시작 후 첫 1시간은 로그를 주시하며 모니터링하세요!

---

## 9. 디버깅 가이드

### 9.1 로그 확인

```bash
# 오늘 로그 확인
cat logs/ver3_cli_$(date +%Y%m%d).log

# 에러만 필터링
grep -i "error\|fail\|exception" logs/ver3_cli_$(date +%Y%m%d).log

# 실시간 모니터링
tail -f logs/ver3_cli_$(date +%Y%m%d).log
```

### 9.2 포지션 상태 확인

```bash
# 현재 포지션 확인
cat logs/positions_v3.json | jq

# 특정 코인 포지션
cat logs/positions_v3.json | jq '.BTC'
```

### 9.3 거래 내역 확인

```bash
# 전체 거래 내역
cat logs/transaction_history.json | jq

# 오늘 거래만
cat logs/transaction_history.json | jq '.[] | select(.timestamp | startswith("2025-12-10"))'

# 매수 거래만
cat logs/transaction_history.json | jq '.[] | select(.action == "BUY")'
```

### 9.4 일반적인 문제 해결

#### 문제 1: 봇이 시작되지 않음

```bash
# Python 경로 확인
which python

# 가상환경 확인
echo $VIRTUAL_ENV

# 의존성 재설치
pip install -r requirements.txt
```

#### 문제 2: API 오류

```bash
# API 키 확인
echo $BITHUMB_CONNECT_KEY | head -c 10

# .env 파일 로드 확인
python -c "from dotenv import load_dotenv; load_dotenv(); import os; print(os.getenv('BITHUMB_CONNECT_KEY')[:10])"
```

#### 문제 3: 포지션 불일치

```bash
# 포지션 파일 백업
cp logs/positions_v3.json logs/positions_v3_backup.json

# 포지션 초기화 (주의!)
echo "{}" > logs/positions_v3.json
```

---

## 10. 자동화된 테스트 실행

### 10.1 전체 테스트 실행

```bash
# 모든 테스트 실행
python -m pytest tests/ -v

# 특정 테스트 파일만
python -m pytest tests/test_strategy.py -v

# 특정 테스트 함수만
python -m pytest tests/test_strategy.py::test_entry_score -v
```

### 10.2 CI/CD 통합 (선택사항)

```yaml
# .github/workflows/test.yml
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: python -m pytest tests/ -v
```

---

## 11. 참고 자료

### 관련 가이드

- [BITHUMB_API_SETUP_GUIDE.md](./BITHUMB_API_SETUP_GUIDE.md) - 빗썸 API 설정
- [TELEGRAM_BOT_SETUP_GUIDE.md](./TELEGRAM_BOT_SETUP_GUIDE.md) - Telegram 봇 설정
- [PROJECT_FINAL_REPORT.md](./PROJECT_FINAL_REPORT.md) - 프로젝트 결과 보고서

---

**작성일**: 2025년 12월 10일
