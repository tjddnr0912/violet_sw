# 05. 개발 가이드

## 실행 방법

### CLI 모드

```bash
# 권장 방법 (환경변수 자동 로드)
./scripts/run_v3_cli.sh

# 직접 실행
source .venv/bin/activate
cd 001_python_code
python ver3/run_cli.py
```

### GUI 모드

```bash
./scripts/run_v3_gui.sh
```

### 단일 분석 테스트

```python
from dotenv import load_dotenv
load_dotenv('.env')

from ver3.config_v3 import get_version_config
from ver3.trading_bot_v3 import TradingBotV3

config = get_version_config()
bot = TradingBotV3(config)

# 단일 코인 분석
result = bot.analyze_market('BTC')
print(result)

# 전체 포트폴리오 요약
summary = bot.get_portfolio_summary()
print(summary)
```

## 설정 변경

### config_v3.py 주요 설정

```python
PORTFOLIO_CONFIG = {
    'coins': ['BTC', 'ETH', 'XRP'],      # 모니터링 코인
    'max_positions': 2,                    # 최대 동시 포지션
    'check_interval': 900,                 # 분석 주기 (초)
    'dry_run': True,                       # 시뮬레이션 모드
}

INDICATOR_CONFIG = {
    'ema_short': 50,
    'ema_long': 200,
    'bb_period': 20,
    'bb_std': 2.0,
    'rsi_period': 14,
    'atr_period': 14,
    'stoch_k_period': 14,
    'stoch_d_period': 3,
}

RISK_CONFIG = {
    'chandelier_multiplier': 3.0,
    'max_daily_loss_pct': 3.0,
    'max_consecutive_losses': 3,
}
```

### 런타임 설정 변경

```python
# 코인 변경
bot.update_coins(['BTC', 'ETH', 'SOL', 'XRP'])

# 동적 팩터 강제 업데이트
bot.force_factor_update()
```

## 코드 수정 가이드

### 진입 조건 수정

`strategy_v3.py`의 `_calculate_entry_score()` 수정:

```python
def _calculate_entry_score(self, df: pd.DataFrame, regime: str) -> float:
    score = 0.0
    weights = self.factors.get('entry_weights', {})

    # BB Touch
    if current_price <= bb_lower:
        score += 1.0 * weights.get('bb_touch', 1.0)

    # RSI Oversold (수정 예시)
    rsi_threshold = self.factors.get('rsi_oversold_threshold', 30)
    if rsi < rsi_threshold:
        score += 1.0 * weights.get('rsi_oversold', 1.0)

    # 새 조건 추가 예시
    if macd_histogram > 0 and macd_prev_histogram < 0:
        score += 0.5 * weights.get('macd_cross', 0.5)

    return score
```

### 청산 조건 수정

`strategy_v3.py`의 `_check_exit_conditions()` 수정:

```python
def _check_exit_conditions(self, position, current_price, indicators):
    # Chandelier Exit
    if current_price <= position.stop_loss_price:
        return {'exit': True, 'reason': 'stop_loss'}

    # Profit Target
    if position.profit_target_mode == 'bb_middle':
        if current_price >= indicators['bb_middle']:
            return {'exit': True, 'reason': 'profit_target'}

    # 새 청산 조건 추가
    if indicators['rsi'] > 80:
        return {'exit': True, 'reason': 'rsi_overbought'}

    return {'exit': False}
```

### 동적 팩터 추가

`dynamic_factor_manager.py`의 `_update_volatility_factors()` 수정:

```python
def _update_volatility_factors(self, atr_pct: float):
    if atr_pct < 1.5:
        volatility = 'LOW'
        self.factors['position_size_multiplier'] = 1.2
        self.factors['chandelier_multiplier'] = 3.5
        # 새 팩터 추가
        self.factors['new_factor'] = 'value_for_low'
```

## 테스트

### 전략 테스트

```python
# 특정 시점 분석
df = bot.api.get_candlestick('BTC', '4h')
regime = bot.strategy.regime_detector.detect(df)
score = bot.strategy._calculate_entry_score(df, regime)
print(f"Regime: {regime}, Score: {score}")
```

### 텔레그램 테스트

```python
from lib.core.telegram_notifier import TelegramNotifier
notifier = TelegramNotifier()

# 메시지 테스트
notifier.send_message("Test message")

# 팩터 요약 테스트
factors = bot.get_current_factors()
notifier.send_dynamic_factors_summary(factors)
```

## 로그 확인

### 로그 파일 위치

```
logs/
├── ver3_cli_YYYYMMDD.log          # 메인 로그
├── transaction_history.json        # 거래 기록
├── positions_v3.json               # 현재 포지션
├── dynamic_factors_v3.json         # 동적 팩터 상태
└── performance_history_v3.json     # 성과 기록
```

### 로그 명령어

```bash
# 실시간 로그
tail -f logs/ver3_cli_$(date +%Y%m%d).log

# 에러만
grep -i "error\|exception" logs/ver3_cli_*.log

# 거래만
grep -i "BUY\|SELL" logs/ver3_cli_*.log

# 레짐 변경
grep -i "regime" logs/ver3_cli_*.log
```

## 디버깅

### 일반적인 문제

**1. ModuleNotFoundError**
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**2. 텔레그램 연결 실패**
```bash
# .env 확인
cat .env | grep TELEGRAM

# 환경변수 로드 확인
python -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); print(os.getenv('TELEGRAM_BOT_TOKEN'))"
```

**3. API 인증 실패**
```bash
# API 키 확인
python -c "
from lib.api.bithumb_api import get_ticker
print(get_ticker('BTC'))
"
```

**4. 포지션 불일치**
```bash
# 포지션 파일 확인
cat logs/positions_v3.json | python -m json.tool

# 강제 동기화
python -c "
from ver3.live_executor_v3 import LiveExecutorV3
# executor.sync_with_exchange()
"
```

## Git 커밋 규칙

```bash
# 기능 추가
git commit -m "Add <feature description>"

# 버그 수정
git commit -m "Fix <bug description>"

# 리팩토링
git commit -m "Refactor <component>"

# 문서
git commit -m "Update documentation for <topic>"
```

## 파일 수정 체크리스트

### 전략 수정 시

- [ ] `strategy_v3.py` 수정
- [ ] `config_v3.py` 관련 설정 추가/수정
- [ ] `dynamic_factor_manager.py` 팩터 반영 (필요시)
- [ ] 테스트 실행
- [ ] 문서 업데이트

### 텔레그램 명령어 추가 시

- [ ] `telegram_bot_handler.py`에 핸들러 추가
- [ ] `_start_bot()`에 핸들러 등록
- [ ] `/help` 메뉴 업데이트
- [ ] `04-telegram-commands.md` 업데이트
- [ ] 테스트

### GUI 수정 시

- [ ] `gui_app_v3.py` 또는 `widgets/` 수정
- [ ] 위젯 연결 확인
- [ ] GUI 테스트
