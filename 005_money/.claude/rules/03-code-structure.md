# 03. 코드 구조

## Ver3 핵심 파일 맵

```
001_python_code/ver3/
├── __init__.py                    # 버전 메타데이터, get_version_instance()
├── config_v3.py                   # 설정값 (400줄)
├── trading_bot_v3.py              # 메인 오케스트레이터 (815줄)
├── strategy_v3.py                 # 매매 전략 (908줄)
├── portfolio_manager_v3.py        # 포트폴리오 관리 (840줄)
├── live_executor_v3.py            # 주문 실행 (1069줄)
├── regime_detector.py             # 레짐 분류 (490줄)
├── dynamic_factor_manager.py      # 동적 파라미터 (764줄)
├── monthly_optimizer.py           # 월간 파라미터 최적화 (715줄)
├── performance_tracker.py         # 성과 추적 (458줄)
├── preference_manager_v3.py       # 사용자 설정 관리 (362줄)
├── gui_app_v3.py                  # GUI 메인 (1373줄)
├── run_cli.py                     # CLI 엔트리포인트 (102줄)
└── widgets/                       # GUI 위젯 컴포넌트
    ├── __init__.py
    ├── account_info_widget.py     # 계정 정보 위젯 (419줄)
    ├── coin_selector_widget.py    # 코인 선택 위젯 (270줄)
    ├── portfolio_overview_widget.py # 포트폴리오 개요 (247줄)
    └── settings_panel_widget.py   # 설정 패널 (769줄)
```

## 클래스 관계도

```
TradingBotV3 (trading_bot_v3.py)
├── StrategyV3 (strategy_v3.py)
│   ├── RegimeDetector (regime_detector.py)
│   └── DynamicFactorManager (dynamic_factor_manager.py)
│       └── MonthlyOptimizer (monthly_optimizer.py)
├── PortfolioManagerV3 (portfolio_manager_v3.py)
│   └── LiveExecutorV3 (live_executor_v3.py)
│       └── BithumbAPI (lib/api/bithumb_api.py)
├── TelegramNotifier (lib/core/telegram_notifier.py)
├── TelegramBotHandler (lib/core/telegram_bot_handler.py)
├── PerformanceTracker (performance_tracker.py)
└── PreferenceManager (preference_manager_v3.py)

GUIAppV3 (gui_app_v3.py)
├── AccountInfoWidget (widgets/account_info_widget.py)
├── CoinSelectorWidget (widgets/coin_selector_widget.py)
├── PortfolioOverviewWidget (widgets/portfolio_overview_widget.py)
└── SettingsPanelWidget (widgets/settings_panel_widget.py)
```

## 핵심 클래스 상세

### TradingBotV3 (trading_bot_v3.py)

메인 봇 클래스. 모든 컴포넌트를 초기화하고 분석 루프를 실행합니다.

```python
class TradingBotV3:
    def __init__(self, config: Dict[str, Any]):
        self.strategy = StrategyV3(config)
        self.portfolio_manager = PortfolioManagerV3(...)
        self.factor_manager = DynamicFactorManager()
        self.telegram = TelegramNotifier()
        self.telegram_handler = TelegramBotHandler(self)

    def run(self):
        # 15분 주기 분석 루프
        while self.running:
            for coin in self.coins:
                result = self.analyze_market(coin)
                self.portfolio_manager.process_signal(coin, result)
            time.sleep(self.check_interval)

    def analyze_market(self, coin: str) -> Dict[str, Any]:
        # 전략 분석 실행
        return self.strategy.analyze(coin)
```

### StrategyV3 (strategy_v3.py)

매매 전략의 핵심. 진입/청산 신호 생성.

```python
class StrategyV3:
    def __init__(self, config: Dict[str, Any]):
        self.regime_detector = RegimeDetector()
        self.factor_manager = DynamicFactorManager()

    def analyze(self, coin: str) -> Dict[str, Any]:
        # 1. 가격 데이터 조회
        df = self._get_price_data(coin)

        # 2. 레짐 판단
        regime = self.regime_detector.detect(df)

        # 3. 진입 스코어 계산
        entry_score = self._calculate_entry_score(df, regime)

        # 4. 신호 생성
        action = self._determine_action(entry_score, regime)

        return {
            'action': action,
            'regime': regime,
            'entry_score': entry_score,
            'indicators': {...}
        }
```

### LiveExecutorV3 (live_executor_v3.py)

실제 주문 실행 및 포지션 관리.

```python
class LiveExecutorV3:
    def __init__(self, api, logger, telegram):
        self.api = api
        self.positions: Dict[str, Position] = {}

    def execute_order(self, ticker, action, units, price, dry_run=True):
        if dry_run:
            # 시뮬레이션
            return self._simulate_order(...)
        else:
            # 실제 주문
            return self.api.place_order(...)

    def close_position(self, ticker, price, dry_run=True, reason=""):
        # 전량 청산
        pos = self.positions[ticker]
        return self.execute_order(ticker, 'SELL', pos.size, price, dry_run)

    def check_stop_loss(self, ticker, current_price):
        # Chandelier Exit 확인
        pos = self.positions[ticker]
        if current_price <= pos.stop_loss_price:
            return True
        return False
```

### RegimeDetector (regime_detector.py)

시장 레짐 분류기.

```python
class RegimeDetector:
    def detect(self, df: pd.DataFrame) -> str:
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['close'].ewm(span=200).mean().iloc[-1]
        adx = self._calculate_adx(df)

        ema_diff_pct = (ema50 - ema200) / ema200 * 100

        if adx < 20:
            return 'ranging'
        elif ema_diff_pct > 5:
            return 'strong_bullish'
        # ... etc
```

### DynamicFactorManager (dynamic_factor_manager.py)

변동성 기반 파라미터 동적 조정.

```python
class DynamicFactorManager:
    def update_factors(self, volatility: str, regime: str):
        self.factors = {
            'volatility_regime': volatility,
            'position_size_multiplier': self._get_position_mult(volatility),
            'chandelier_multiplier': self._get_chandelier_mult(volatility),
            'min_entry_score': self._get_min_score(volatility, regime),
            ...
        }
```

## 공유 라이브러리 (lib/)

```
001_python_code/lib/
├── __init__.py
├── api/                           # 거래소 API
│   ├── __init__.py
│   └── bithumb_api.py             # 빗썸 API 래퍼 (약 400줄)
├── core/                          # 핵심 유틸리티
│   ├── __init__.py
│   ├── arg_parser.py              # CLI 인자 파서 (208줄)
│   ├── config_common.py           # 공통 설정 (171줄)
│   ├── config_manager.py          # 설정 관리자 (491줄)
│   ├── logger.py                  # 로깅 유틸리티 (412줄)
│   ├── portfolio_manager.py       # 공통 포트폴리오 (334줄)
│   ├── telegram_bot_handler.py    # 텔레그램 명령어 (934줄)
│   ├── telegram_notifier.py       # 텔레그램 알림 (673줄)
│   └── version_loader.py          # 버전 로더 (92줄)
├── gui/                           # GUI 공통 컴포넌트
│   ├── __init__.py
│   ├── components/                # GUI 서브 컴포넌트
│   ├── data_manager.py            # 데이터 관리 (278줄)
│   └── indicator_calculator.py    # 지표 계산기 (318줄)
└── interfaces/                    # 인터페이스 정의
    ├── __init__.py
    ├── strategy_interface.py      # 전략 인터페이스 (47줄)
    └── version_interface.py       # 버전 인터페이스 (46줄)
```

### lib/api/bithumb_api.py

```python
def get_candlestick(ticker: str, interval: str = "24h") -> pd.DataFrame:
    # OHLCV 데이터 조회

def get_ticker(ticker: str) -> Dict:
    # 현재가 조회

def get_balance(ticker: str) -> Dict:
    # 잔고 조회 (인증 필요)
```

### lib/core/telegram_notifier.py (673줄)

```python
class TelegramNotifier:
    def send_message(self, message: str) -> bool
    def send_trade_alert(self, action, ticker, amount, price, ...) -> bool
    def send_dynamic_factors_summary(self, factors: Dict) -> bool
    def send_regime_change_alert(self, old, new, coin, ema_diff) -> bool
```

### lib/core/telegram_bot_handler.py (934줄)

```python
class TelegramBotHandler:
    # 명령어 핸들러
    async def cmd_status(self, update, context)
    async def cmd_positions(self, update, context)
    async def cmd_factors(self, update, context)
    async def cmd_close(self, update, context)  # /close <COIN>
    async def cmd_stop(self, update, context)
```

### lib/core/config_manager.py (491줄)

```python
class ConfigManager:
    # 설정 파일 로드/저장
    def load_config(self, config_path: str) -> Dict
    def save_config(self, config: Dict, config_path: str) -> bool
    def get_default_config(self) -> Dict
```

### lib/core/logger.py (412줄)

```python
def setup_logger(name: str, log_file: str, level: int) -> logging.Logger
    # 로거 설정 및 반환

class ColoredFormatter:
    # 컬러 로그 포매터
```

### lib/gui/indicator_calculator.py (318줄)

```python
class IndicatorCalculator:
    # 기술적 지표 계산
    def calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series
    def calculate_bb(self, df: pd.DataFrame, period: int, std: float) -> Dict
    def calculate_rsi(self, df: pd.DataFrame, period: int) -> pd.Series
```

### lib/interfaces/strategy_interface.py

```python
class StrategyInterface(ABC):
    @abstractmethod
    def analyze(self, coin: str) -> Dict[str, Any]

    @abstractmethod
    def get_signal(self, coin: str) -> str
```

## 데이터 흐름

```
1. 분석 시작
   TradingBotV3.run()
   ↓
2. 가격 데이터 조회
   bithumb_api.get_candlestick(coin, '4h')
   ↓
3. 레짐 판단
   RegimeDetector.detect(df) → 'bearish'
   ↓
4. 동적 파라미터 적용
   DynamicFactorManager.update_factors(volatility, regime)
   ↓
5. 진입 스코어 계산
   StrategyV3._calculate_entry_score(df) → 2.5
   ↓
6. 신호 생성
   StrategyV3._determine_action() → 'BUY'
   ↓
7. 주문 실행
   PortfolioManagerV3.process_signal()
   LiveExecutorV3.execute_order()
   ↓
8. 알림 전송
   TelegramNotifier.send_trade_alert()
```
