# Stock Auto Trading System

한국투자증권 REST API 기반 주식 자동매매 시스템

## Features

- **macOS 지원**: REST API 기반으로 Windows 의존성 없음
- **다양한 매매 전략**: MA Crossover, RSI, MACD, 복합 전략
- **기술적 지표**: SMA, EMA, RSI, MACD, Bollinger Bands, Stochastic, ATR, ADX
- **텔레그램 연동**: 실시간 알림 및 명령어 제어
- **안전한 거래**: Dry-run 모드, 모의투자 환경 지원

## Project Structure

```
007_stock_trade/
├── main.py                 # 메인 실행 파일
├── src/
│   ├── engine.py          # 자동매매 엔진
│   ├── api/               # 한국투자증권 API
│   │   ├── kis_auth.py    # 인증 (토큰 관리)
│   │   └── kis_client.py  # API 클라이언트
│   ├── strategy/          # 매매 전략
│   │   ├── indicators.py  # 기술적 지표
│   │   ├── base.py        # 전략 기본 클래스
│   │   └── strategies.py  # 구체적 전략 구현
│   ├── telegram/          # 텔레그램 봇
│   │   └── bot.py
│   └── utils/
├── tests/                  # 테스트 코드
├── config/                 # 설정 파일
├── logs/                   # 로그 파일
├── .env.example           # 환경변수 템플릿
└── requirements.txt
```

## Installation

### 1. 의존성 설치

```bash
cd 007_stock_trade
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일 편집:

```ini
# 한국투자증권 API (https://apiportal.koreainvestment.com)
KIS_APP_KEY=발급받은_앱키
KIS_APP_SECRET=발급받은_앱시크릿
KIS_ACCOUNT_NO=계좌번호-01

# 텔레그램 봇 (선택)
TELEGRAM_BOT_TOKEN=봇_토큰
TELEGRAM_CHAT_ID=채팅_ID
```

### 3. API 키 발급

1. [KIS Developers](https://apiportal.koreainvestment.com) 접속
2. 회원가입 및 로그인
3. Open API 신청
4. App Key / App Secret 발급

## Usage

### 기본 명령어

```bash
# API 연결 테스트
python main.py --test

# 계좌 상태 확인
python main.py --status

# 종목 시세 조회
python main.py --price 005930

# 종목 분석 (전략 시그널)
python main.py --analyze 005930

# 텔레그램 봇 실행
python main.py --bot
```

### 자동매매 실행

```bash
# 기본 실행 (모의투자, dry-run)
python main.py

# 실제 주문 실행 (모의투자)
python main.py --live

# 실전투자 + 실제 주문
python main.py --real --live

# 옵션 지정
python main.py --strategy rsi --stocks 005930,000660 --interval 15
```

### 명령줄 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--test` | API 연결 테스트 | - |
| `--status` | 계좌 상태 확인 | - |
| `--price CODE` | 종목 시세 조회 | - |
| `--analyze CODE` | 종목 분석 | - |
| `--bot` | 텔레그램 봇 실행 | - |
| `--stocks` | 거래 종목 (쉼표 구분) | 005930 |
| `--strategy` | 전략 선택 | composite |
| `--interval` | 분석 주기 (분) | 30 |
| `--capital` | 투자 자본금 | 1,000,000 |
| `--live` | 실제 주문 실행 | False (dry-run) |
| `--real` | 실전투자 모드 | False (모의투자) |

## Strategies

### 1. MA Crossover (`ma_crossover`)
- 단기/장기 이동평균 교차 전략
- 골든크로스: 매수 / 데드크로스: 매도

### 2. RSI (`rsi`)
- RSI 과매수/과매도 전략
- RSI < 30: 매수 / RSI > 70: 매도

### 3. MACD (`macd`)
- MACD 시그널 교차 전략
- MACD > Signal: 매수 / MACD < Signal: 매도

### 4. Composite (`composite`)
- MA + RSI + MACD 복합 전략
- 가중 평균 점수 기반 판단

## Telegram Commands

| 명령어 | 설명 |
|--------|------|
| `/start` | 봇 시작 |
| `/잔고` | 계좌 잔고 조회 |
| `/시세 005930` | 종목 시세 조회 |
| `/주문내역` | 당일 주문내역 |
| `/상태` | 시스템 상태 |
| `/도움말` | 명령어 도움말 |

## Testing

```bash
# 전체 테스트 실행
python -m pytest tests/ -v

# 개별 테스트
python -m pytest tests/test_kis_api.py -v
python -m pytest tests/test_strategy.py -v
python -m pytest tests/test_telegram.py -v
```

## API Reference

### KISClient

```python
from src.api import KISClient

client = KISClient(is_virtual=True)  # 모의투자

# 시세 조회
price = client.get_stock_price("005930")
print(f"{price.name}: {price.price:,}원")

# 잔고 조회
balance = client.get_balance()

# 매수/매도
client.buy_stock("005930", qty=10, price=70000)
client.sell_stock("005930", qty=10, price=72000)
```

### Strategy

```python
from src.strategy import create_strategy, Signal
import pandas as pd

strategy = create_strategy("composite")
signal = strategy.analyze(df)  # OHLCV DataFrame

if signal.signal == Signal.BUY:
    print(f"매수 신호: {signal.reason}")
```

### TelegramNotifier

```python
from src.telegram import TelegramNotifier

notifier = TelegramNotifier()
notifier.notify_buy("삼성전자", "005930", qty=10, price=70000)
notifier.notify_error("API 오류", "연결 실패")
```

## License

This project is for personal use only. Use at your own risk.

## Disclaimer

- 이 프로그램은 투자 조언을 제공하지 않습니다.
- 모든 투자 결정과 그에 따른 손실은 사용자 본인의 책임입니다.
- 실전 투자 전 반드시 모의투자로 충분히 테스트하세요.
