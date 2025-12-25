# CLAUDE.md - 퀀트 자동매매 시스템

이 문서는 Claude Code가 코드 작업 시 참조하는 프로젝트 가이드입니다.

## 프로젝트 개요

한국투자증권(KIS) Open API를 활용한 멀티팩터 퀀트 자동매매 시스템입니다.
- **전략**: 가치(40%) + 모멘텀(30%) + 퀄리티(30%) 팩터 조합
- **유니버스**: KOSPI200 구성종목
- **목표**: 상위 20개 종목 선정 및 자동 리밸런싱

## 프로젝트 구조

```
007_stock_trade/
├── src/
│   ├── __init__.py
│   ├── quant_engine.py          # 퀀트 자동매매 엔진 (스케줄러)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── kis_client.py        # KIS API 기본 클라이언트
│   │   ├── kis_quant.py         # 퀀트용 확장 클라이언트
│   │   └── kis_websocket.py     # WebSocket 실시간 시세
│   ├── strategy/
│   │   └── quant/
│   │       ├── __init__.py      # 모듈 exports
│   │       ├── factors.py       # 팩터 계산기 (Value, Momentum, Quality)
│   │       ├── screener.py      # 멀티팩터 스크리너
│   │       ├── signals.py       # 기술적 신호 생성
│   │       ├── risk.py          # 리스크 관리/포지션 사이징
│   │       ├── backtest.py      # 백테스팅 프레임워크
│   │       ├── analytics.py     # 성과 분석/시각화
│   │       └── sector.py        # 섹터 분산 관리
│   └── telegram/
│       ├── __init__.py
│       ├── notifier.py          # 텔레그램 알림 전송
│       └── bot.py               # 텔레그램 봇 명령어 처리
├── config/
│   ├── sample.env               # 환경변수 샘플
│   └── token.json               # KIS API 토큰 캐시
├── data/
│   └── quant/                   # 스크리닝/상태 데이터
├── tests/
│   ├── test_quant_engine.py
│   └── test_quant_strategy.py
├── docs/
│   └── strategy/                # 전략 문서
├── run_quant.sh                 # 실행 스크립트
├── requirements.txt
└── CLAUDE.md
```

## 핵심 모듈 설명

### 1. API 레이어 (`src/api/`)

**kis_client.py** - 기본 KIS API 클라이언트
- OAuth 토큰 발급/갱신/캐싱
- REST API 요청 래퍼
- 모의/실전 투자 모드 지원

**kis_quant.py** - 퀀트용 확장 클라이언트
```python
client = KISQuantClient(is_virtual=True)
rankings = client.get_market_cap_ranking(count=30)  # 시가총액 순위
price_data = client.get_stock_price_history(code, days=60)  # 가격 이력
financial = client.get_financial_data(code)  # 재무 데이터
```

**kis_websocket.py** - 실시간 시세
```python
ws = KISWebSocket(is_virtual=True)
ws.subscribe("005930")  # 삼성전자 구독
ws.on_price = lambda data: print(data['current_price'])
ws.start()
```

### 2. 전략 레이어 (`src/strategy/quant/`)

**factors.py** - 팩터 계산기
- `ValueFactorCalculator`: PER, PBR, PSR, 배당수익률
- `MomentumFactorCalculator`: 1M/3M/6M 수익률, 52주 고점
- `QualityFactorCalculator`: ROE, 부채비율, 영업이익률, 이익성장률
- `CompositeScoreCalculator`: 가중 합성 점수 계산

**screener.py** - 멀티팩터 스크리너
```python
config = ScreeningConfig(
    universe_size=200,
    target_count=20,
    factor_weights=FactorWeights(value=0.4, momentum=0.3, quality=0.3)
)
screener = MultiFactorScreener(client, config)
result = screener.run_screening()
excel_path = screener.export_to_excel(result)  # 엑셀 저장
```

**signals.py** - 기술적 신호
- `TechnicalAnalyzer`: RSI, MACD, 볼린저밴드, 이동평균
- `MarketAnalyzer`: 시장 상태 분석 (상승/하락/횡보)
- `SignalGenerator`: 매수/매도/홀드 신호 생성
- `StopLossManager`, `TakeProfitManager`: 손절/익절 관리

**risk.py** - 리스크 관리
- `PositionSizer`: 켈리 기준, ATR 기반, 동일 비중 포지션 사이징
- `RiskMonitor`: 일간 손실, 섹터 비중, 집중도 모니터링
- `PortfolioManager`: 리밸런싱 계산

**backtest.py** - 백테스팅
```python
config = BacktestConfig(
    initial_capital=100_000_000,
    commission_rate=0.00015,
    rebalance_frequency="M"  # Monthly
)
backtester = Backtester(config)
result = backtester.run(price_data, signals, start_date, end_date)
```

**analytics.py** - 성과 분석
```python
analyzer = PerformanceAnalyzer()
metrics = analyzer.calculate_metrics(returns)
# 샤프비율, 소르티노비율, 최대낙폭, 승률 등

chart = ChartGenerator()
chart.plot_equity_curve(equity)
chart.plot_drawdown(equity)
```

**sector.py** - 섹터 분산
```python
manager = SectorManager(SectorConstraints(
    max_sector_weight=0.30,
    min_sector_count=3
))
diversified = manager.apply_sector_diversification(candidates, 20)
report = manager.get_sector_report(positions, total_value)
```

### 3. 텔레그램 (`src/telegram/`)

**notifier.py** - 알림 전송
```python
notifier = get_notifier()
notifier.send_message("매매 완료")
notifier.send_trade_notification("BUY", "삼성전자", 10, 70000)
```

**bot.py** - 봇 명령어
- `/status` - 포트폴리오 상태
- `/holdings` - 보유 종목
- `/today` - 오늘 수익률
- `/signals` - 현재 신호
- `/screen` - 스크리닝 실행
- `/balance` - 계좌 잔고

### 4. 메인 엔진 (`src/quant_engine.py`)

```python
config = QuantEngineConfig(
    universe_size=200,
    target_stock_count=20,
    dry_run=True
)
engine = QuantTradingEngine(config, is_virtual=True)
engine.start()  # 스케줄 기반 자동 실행
```

## 실행 방법

```bash
# 실행 스크립트 사용
./run_quant.sh start          # 자동매매 시작
./run_quant.sh screen         # 1회 스크리닝
./run_quant.sh screen-full    # 전체 스크리닝 + 엑셀
./run_quant.sh status         # 상태 확인
./run_quant.sh test           # API 테스트
./run_quant.sh telegram       # 텔레그램 테스트

# 옵션
--dry-run                     # 모의 실행
--virtual / --real            # 모의투자 / 실전투자
--universe 100                # 유니버스 크기
--target 15                   # 목표 종목 수
```

## 환경 변수

```bash
# .env 파일
KIS_APP_KEY=your_app_key
KIS_APP_SECRET=your_app_secret
KIS_ACCOUNT_NO=12345678-01
TRADING_MODE=VIRTUAL          # VIRTUAL or REAL
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

## 의존성

```
requests>=2.28.0
pandas>=1.5.0
numpy>=1.23.0
schedule>=1.1.0
pykrx>=1.0.0      # KOSPI200 유니버스
openpyxl>=3.0.0   # 엑셀 저장
matplotlib>=3.6.0 # 차트 생성
```

## 주요 데이터 흐름

```
1. 유니버스 구성 (pykrx → KOSPI200 종목)
       ↓
2. 재무/가격 데이터 수집 (KIS API)
       ↓
3. 팩터 점수 계산 (Value + Momentum + Quality)
       ↓
4. 종합 점수 기준 순위 매김
       ↓
5. 섹터 분산 적용
       ↓
6. 상위 20개 종목 선정
       ↓
7. 리밸런싱 계산 (매수/매도 액션)
       ↓
8. 주문 실행 (dry_run=False 시)
       ↓
9. 텔레그램 알림 전송
```

## 주의사항

- **API 한도**: KIS API는 시가총액 순위 조회 시 최대 30개만 반환
  - 해결: pykrx로 KOSPI200 전체 종목 조회 후 개별 데이터 수집
- **거래일 확인**: 공휴일에는 pykrx 데이터가 없음
  - 해결: 최대 7일 전까지 거래일 데이터 탐색
- **토큰 만료**: OAuth 토큰은 24시간 유효
  - 자동 갱신 로직 구현됨 (`token.json` 캐싱)

## 개발 가이드

### 새 팩터 추가
1. `factors.py`에 `XxxFactorCalculator` 클래스 추가
2. `CompositeScoreCalculator`에 가중치 추가
3. `__init__.py`에 export 추가

### 새 텔레그램 명령어 추가
1. `bot.py`의 `TelegramBotHandler`에 핸들러 메서드 추가
2. `_register_handlers()`에 명령어 등록

### 백테스트 실행
```python
from src.strategy.quant import Backtester, BacktestConfig
from src.strategy.quant import PerformanceAnalyzer

config = BacktestConfig(initial_capital=1_000_000_000)
backtester = Backtester(config)
result = backtester.run(price_data, signals, "2023-01-01", "2024-12-31")

analyzer = PerformanceAnalyzer()
metrics = analyzer.calculate_metrics(result.equity_curve)
print(f"샤프비율: {metrics.sharpe_ratio:.2f}")
```

## 트러블슈팅

### ModuleNotFoundError
```bash
pip install -r requirements.txt
pip install pykrx setuptools openpyxl
```

### API 인증 오류
1. `.env` 파일 확인
2. `config/token.json` 삭제 후 재시도
3. KIS 개발자센터에서 API 키 상태 확인

### 스크리닝 데이터 없음
- 공휴일/주말에는 실시간 데이터 없음
- pykrx는 과거 데이터만 제공 (당일 X)
