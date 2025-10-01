# API Reference Documentation

**Project**: Bithumb Cryptocurrency Trading Bot
**Version**: 2.0 (Elite Strategy)
**Last Updated**: 2025-10-02
**Audience**: Developers, Integration Engineers

---

## Table of Contents

1. [Bithumb API Integration](#bithumb-api-integration)
2. [Strategy Engine API](#strategy-engine-api)
3. [Trading Bot API](#trading-bot-api)
4. [Configuration Manager API](#configuration-manager-api)
5. [Logging System API](#logging-system-api)
6. [GUI Components API](#gui-components-api)
7. [Utility Functions](#utility-functions)
8. [Error Handling](#error-handling)

---

## Bithumb API Integration

### Module: `bithumb_api.py`

Wrapper for Bithumb REST API public endpoints.

---

#### `get_ticker(ticker: str) -> Dict[str, Any]`

Get current market data for a cryptocurrency.

**Parameters**:
- `ticker` (str): Cryptocurrency symbol (e.g., 'BTC', 'ETH')

**Returns**:
- `dict`: Market data dictionary
  ```python
  {
      'opening_price': str,      # Opening price (24h)
      'closing_price': str,      # Current price
      'min_price': str,          # 24h low
      'max_price': str,          # 24h high
      'units_traded': str,       # 24h volume (coins)
      'acc_trade_value': str,    # 24h volume (KRW)
      'prev_closing_price': str, # Previous day close
      'units_traded_24H': str,
      'acc_trade_value_24H': str,
      'fluctate_24H': str,       # 24h change amount
      'fluctate_rate_24H': str,  # 24h change percentage
      'date': str                # Unix timestamp (milliseconds)
  }
  ```

**Raises**:
- `requests.RequestException`: Network or API error
- `KeyError`: Unexpected API response format

**Example**:
```python
from bithumb_api import get_ticker

try:
    data = get_ticker('BTC')
    current_price = float(data['closing_price'])
    print(f"BTC Price: {current_price:,.0f} KRW")
except Exception as e:
    print(f"Error: {e}")
```

**Rate Limit**: No explicit limit documented, but avoid excessive calls

---

#### `get_candlestick(ticker: str, interval: str = '24h') -> pd.DataFrame`

Get OHLCV candlestick data.

**Parameters**:
- `ticker` (str): Cryptocurrency symbol
- `interval` (str): Candlestick interval
  - Valid: `'1m'`, `'3m'`, `'5m'`, `'10m'`, `'30m'`, `'1h'`, `'6h'`, `'12h'`, `'24h'`
  - Default: `'24h'`

**Returns**:
- `pd.DataFrame`: OHLCV data with columns:
  ```python
  Index: pd.DatetimeIndex (timezone-aware KST)
  Columns:
      - open: float64      # Opening price
      - high: float64      # Highest price
      - low: float64       # Lowest price
      - close: float64     # Closing price
      - volume: float64    # Trading volume (coins)
  ```

**Raises**:
- `requests.RequestException`: Network or API error
- `ValueError`: Invalid interval parameter

**Example**:
```python
from bithumb_api import get_candlestick

# Get 1-hour candlesticks
df = get_candlestick('BTC', interval='1h')

print(df.head())
#                      open      high       low     close     volume
# 2025-10-01 00:00  98000.0  99000.0  97500.0  98500.0  123.456
# 2025-10-01 01:00  98500.0  99500.0  98000.0  99000.0  145.678

# Latest price
latest_close = df['close'].iloc[-1]
```

**Notes**:
- Returns up to 200 most recent candles
- Timestamps are in KST (Korea Standard Time)
- Data may have gaps during low-activity periods

---

#### `get_orderbook(ticker: str) -> Dict[str, Any]`

Get current order book (bid/ask data).

**Parameters**:
- `ticker` (str): Cryptocurrency symbol

**Returns**:
- `dict`: Order book data
  ```python
  {
      'timestamp': str,
      'payment_currency': 'KRW',
      'order_currency': str,  # e.g., 'BTC'
      'bids': [
          {'price': str, 'quantity': str},
          ...  # Up to 30 levels
      ],
      'asks': [
          {'price': str, 'quantity': str},
          ...
      ]
  }
  ```

**Example**:
```python
orderbook = get_orderbook('BTC')
best_bid = float(orderbook['bids'][0]['price'])
best_ask = float(orderbook['asks'][0]['price'])
spread = best_ask - best_bid
print(f"Spread: {spread:,.0f} KRW")
```

**Note**: Not currently used in trading bot logic (market orders only)

---

### Private API Endpoints

**Note**: Balance inquiry and trading endpoints are intentionally disabled in the current bot implementation for security reasons. Test files exist but are not integrated into production code.

**Test Files** (for reference):
- `test_balance.py`: Balance inquiry example
- `test_api_signature.py`: API signature verification
- `bithumb_secure_api.py`: Secure private API wrapper (not used in bot)

---

## Strategy Engine API

### Module: `strategy.py`

Core trading strategy implementation with 8 technical indicators.

---

### Class: `TradingStrategy`

Main strategy engine coordinator.

#### Constructor

```python
TradingStrategy(config: Dict[str, Any] = None)
```

**Parameters**:
- `config` (dict, optional): Strategy configuration override. If None, uses `config.STRATEGY_CONFIG`

**Example**:
```python
from strategy import TradingStrategy

# Use default config
strategy = TradingStrategy()

# Or custom config
custom_config = {
    'rsi_period': 21,
    'macd_fast': 10,
    # ...
}
strategy = TradingStrategy(config=custom_config)
```

---

#### `analyze_market_data(ticker: str, interval: str = '1h') -> Dict[str, Any]`

Comprehensive market analysis with all 8 indicators.

**Parameters**:
- `ticker` (str): Cryptocurrency symbol
- `interval` (str): Candlestick interval (default: '1h')

**Returns**:
- `dict`: Complete analysis results
  ```python
  {
      'ticker': str,
      'interval': str,
      'timestamp': datetime,
      'current_price': float,
      'price_data': pd.DataFrame,  # OHLCV data

      # Indicator values
      'indicators': {
          'ma_short': pd.Series,
          'ma_long': pd.Series,
          'rsi': pd.Series,
          'bb_upper': pd.Series,
          'bb_middle': pd.Series,
          'bb_lower': pd.Series,
          'macd': pd.Series,
          'macd_signal': pd.Series,
          'macd_histogram': pd.Series,
          'atr': pd.Series,
          'atr_percent': pd.Series,
          'stoch_k': pd.Series,
          'stoch_d': pd.Series,
          'adx': pd.Series,
          'volume_ratio': pd.Series
      },

      # Latest values
      'current_values': {
          'ma_short': float,
          'ma_long': float,
          'rsi': float,
          'bb_position': float,  # 0-1 scale
          'macd_histogram': float,
          'atr': float,
          'atr_pct': float,
          'stoch_k': float,
          'stoch_d': float,
          'adx': float,
          'volume_ratio': float
      },

      # Market regime
      'market_regime': {
          'regime': str,  # 'Trending' | 'Ranging' | 'Transitional'
          'volatility': str,  # 'LOW' | 'NORMAL' | 'HIGH'
          'adx_value': float,
          'atr_pct': float,
          'recommendation': str  # Strategy suggestion
      },

      # Risk management
      'risk_levels': {
          'entry_price': float,
          'stop_loss': float,
          'take_profit_1': float,
          'take_profit_2': float,
          'stop_pct': float,
          'tp1_pct': float,
          'tp2_pct': float,
          'rr_ratio_tp1': str,  # e.g., "1:1.5"
          'rr_ratio_tp2': str,
          'position_sizing_advice': str
      }
  }
  ```

**Raises**:
- `ValueError`: Invalid ticker or interval
- `Exception`: API or calculation errors

**Example**:
```python
from strategy import TradingStrategy

strategy = TradingStrategy()
analysis = strategy.analyze_market_data('BTC', '1h')

print(f"Current Price: {analysis['current_price']:,.0f}")
print(f"RSI: {analysis['current_values']['rsi']:.2f}")
print(f"Market Regime: {analysis['market_regime']['regime']}")
print(f"Stop Loss: {analysis['risk_levels']['stop_loss']:,.0f}")
```

---

#### `generate_weighted_signals(analysis: Dict) -> Dict[str, Any]`

Generate trading signals from analysis using weighted combination.

**Parameters**:
- `analysis` (dict): Output from `analyze_market_data()`

**Returns**:
- `dict`: Signal decision
  ```python
  {
      'decision': str,  # 'BUY' | 'SELL' | 'HOLD'
      'overall_signal': float,  # -1.0 to +1.0
      'confidence': float,      # 0.0 to 1.0
      'individual_signals': {
          'ma': float,           # -1.0 to +1.0
          'rsi': float,
          'macd': float,
          'bb': float,
          'volume': float,
          'stochastic': float,
          'adx': float,
          'atr': float
      },
      'signal_explanations': {
          'ma': str,
          'rsi': str,
          # ... human-readable descriptions
      }
  }
  ```

**Example**:
```python
analysis = strategy.analyze_market_data('BTC')
signals = strategy.generate_weighted_signals(analysis)

if signals['decision'] == 'BUY':
    print(f"BUY Signal! Confidence: {signals['confidence']:.1%}")
    print(f"Signal Strength: {signals['overall_signal']:+.2f}")
    for indicator, value in signals['individual_signals'].items():
        print(f"  {indicator}: {value:+.2f}")
```

---

### Indicator Calculation Functions

All indicator functions are standalone and can be used independently.

---

#### `calculate_moving_average(df: pd.DataFrame, window: int) -> pd.Series`

Simple Moving Average (SMA).

**Parameters**:
- `df` (pd.DataFrame): OHLCV data with 'close' column
- `window` (int): Lookback period

**Returns**:
- `pd.Series`: SMA values

**Example**:
```python
from strategy import calculate_moving_average
from bithumb_api import get_candlestick

df = get_candlestick('BTC', '1h')
ma20 = calculate_moving_average(df, 20)
ma50 = calculate_moving_average(df, 50)

# Golden cross detection
if ma20.iloc[-1] > ma50.iloc[-1] and ma20.iloc[-2] <= ma50.iloc[-2]:
    print("Golden Cross! Bullish signal")
```

---

#### `calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series`

Relative Strength Index (RSI).

**Parameters**:
- `df` (pd.DataFrame): OHLCV data with 'close' column
- `period` (int, default=14): Lookback period

**Returns**:
- `pd.Series`: RSI values (0-100)

**Example**:
```python
from strategy import calculate_rsi

rsi = calculate_rsi(df, 14)
current_rsi = rsi.iloc[-1]

if current_rsi < 30:
    print("Oversold condition (RSI < 30)")
elif current_rsi > 70:
    print("Overbought condition (RSI > 70)")
```

---

#### `calculate_macd(df, fast=8, slow=17, signal=9) -> Tuple[pd.Series, pd.Series, pd.Series]`

MACD (Moving Average Convergence Divergence).

**Parameters**:
- `df` (pd.DataFrame): OHLCV data
- `fast` (int): Fast EMA period
- `slow` (int): Slow EMA period
- `signal` (int): Signal line EMA period

**Returns**:
- Tuple of 3 pd.Series:
  - `macd_line`: MACD line (fast_EMA - slow_EMA)
  - `signal_line`: Signal line (MACD smoothed)
  - `histogram`: MACD histogram (macd_line - signal_line)

**Example**:
```python
from strategy import calculate_macd

macd, signal, histogram = calculate_macd(df, fast=8, slow=17, signal=9)

# Bullish crossover
if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
    print("MACD bullish crossover")

# Histogram strength
hist_value = histogram.iloc[-1]
print(f"Histogram: {hist_value:+.0f} (positive = bullish momentum)")
```

---

#### `calculate_bollinger_bands(df, window=20, num_std=2) -> Tuple[pd.Series, pd.Series, pd.Series]`

Bollinger Bands.

**Parameters**:
- `df` (pd.DataFrame): OHLCV data
- `window` (int): MA period
- `num_std` (float): Standard deviation multiplier

**Returns**:
- Tuple: `(upper_band, middle_band, lower_band)`

**Example**:
```python
from strategy import calculate_bollinger_bands

upper, middle, lower = calculate_bollinger_bands(df, 20, 2.0)
current_price = df['close'].iloc[-1]

# Band position
bb_position = (current_price - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])

if bb_position < 0.2:
    print("Price near lower band (potential buy)")
elif bb_position > 0.8:
    print("Price near upper band (potential sell)")
```

---

#### `calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series`

Average True Range (ATR) - volatility indicator.

**Parameters**:
- `df` (pd.DataFrame): OHLCV data with 'high', 'low', 'close'
- `period` (int): Lookback period

**Returns**:
- `pd.Series`: ATR values (in price units)

**Example**:
```python
from strategy import calculate_atr, calculate_atr_percent

atr = calculate_atr(df, 14)
atr_pct = calculate_atr_percent(df, 14)

current_atr = atr.iloc[-1]
current_atr_pct = atr_pct.iloc[-1]

print(f"ATR: {current_atr:,.0f} KRW ({current_atr_pct:.2%})")

# Position sizing
if current_atr_pct > 0.03:  # 3%
    print("High volatility - reduce position size")
```

---

#### `calculate_stochastic(df, k_period=14, d_period=3) -> Tuple[pd.Series, pd.Series]`

Stochastic Oscillator.

**Parameters**:
- `df` (pd.DataFrame): OHLCV data
- `k_period` (int): %K period
- `d_period` (int): %D smoothing period

**Returns**:
- Tuple: `(stoch_k, stoch_d)` (values 0-100)

**Example**:
```python
from strategy import calculate_stochastic

k, d = calculate_stochastic(df, 14, 3)

if k.iloc[-1] < 20 and k.iloc[-1] > d.iloc[-1]:
    print("Stochastic: Oversold + bullish crossover")
```

---

#### `calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series`

ADX (Average Directional Index) - trend strength.

**Parameters**:
- `df` (pd.DataFrame): OHLCV data
- `period` (int): Lookback period

**Returns**:
- `pd.Series`: ADX values (0-100)

**Example**:
```python
from strategy import calculate_adx

adx = calculate_adx(df, 14)
current_adx = adx.iloc[-1]

if current_adx > 25:
    print("Strong trend - use trend-following strategy")
elif current_adx < 15:
    print("Weak trend - use mean-reversion strategy")
```

---

#### `calculate_volume_ratio(df: pd.DataFrame, window: int = 10) -> pd.Series`

Volume ratio (current volume / average volume).

**Parameters**:
- `df` (pd.DataFrame): OHLCV data with 'volume' column
- `window` (int): Average period

**Returns**:
- `pd.Series`: Volume ratios (e.g., 1.5 = 150% of average)

**Example**:
```python
from strategy import calculate_volume_ratio

vol_ratio = calculate_volume_ratio(df, 20)

if vol_ratio.iloc[-1] > 1.5:
    print("High volume - signals are more reliable")
```

---

## Trading Bot API

### Module: `trading_bot.py`

Main trading execution coordinator.

---

### Class: `TradingBot`

Orchestrates market analysis, signal generation, and trade execution.

#### Constructor

```python
TradingBot(
    config: Optional[Dict] = None,
    logger: Optional[TradingLogger] = None,
    dry_run: bool = False
)
```

**Parameters**:
- `config` (dict, optional): Configuration override
- `logger` (TradingLogger, optional): Custom logger instance
- `dry_run` (bool, default=False): Paper trading mode

**Example**:
```python
from trading_bot import TradingBot
from logger import TradingLogger

logger = TradingLogger()
bot = TradingBot(logger=logger, dry_run=True)
```

---

#### `execute_trading_cycle(ticker: str = None, interval: str = None) -> Dict[str, Any]`

Execute one complete trading cycle: analyze → decide → trade.

**Parameters**:
- `ticker` (str, optional): Override default ticker
- `interval` (str, optional): Override default interval

**Returns**:
- `dict`: Cycle results
  ```python
  {
      'timestamp': datetime,
      'ticker': str,
      'decision': str,  # 'BUY' | 'SELL' | 'HOLD'
      'action_taken': bool,
      'analysis': dict,  # From analyze_market_data()
      'signals': dict,   # From generate_weighted_signals()
      'trade_result': dict | None,  # If action taken
      'reason': str  # Why action was/wasn't taken
  }
  ```

**Example**:
```python
bot = TradingBot(dry_run=True)
result = bot.execute_trading_cycle('BTC', '1h')

if result['action_taken']:
    print(f"Executed {result['decision']} at {result['trade_result']['price']}")
else:
    print(f"No action: {result['reason']}")
```

**Safety Checks Performed**:
1. Daily trade limit check
2. Consecutive loss limit check
3. Daily loss percentage check
4. Emergency stop flag check
5. Minimum confidence threshold check

---

#### `buy_coin(ticker: str, amount_krw: float) -> Dict[str, Any]`

Execute buy order (market order).

**Parameters**:
- `ticker` (str): Cryptocurrency to buy
- `amount_krw` (float): Amount in KRW to spend

**Returns**:
- `dict`: Trade result
  ```python
  {
      'success': bool,
      'action': 'BUY',
      'ticker': str,
      'amount_krw': float,
      'price': float,
      'quantity': float,
      'fee': float,
      'timestamp': datetime,
      'dry_run': bool
  }
  ```

**Raises**:
- `Exception`: Trade execution failed

**Example**:
```python
try:
    result = bot.buy_coin('BTC', 50000)  # Buy 50,000 KRW worth
    print(f"Bought {result['quantity']:.8f} BTC at {result['price']:,.0f}")
except Exception as e:
    print(f"Buy failed: {e}")
```

**Notes**:
- In dry-run mode, simulates trade without API call
- Includes 0.25% fee calculation
- Updates portfolio tracking

---

#### `sell_coin(ticker: str, quantity: float = None, amount_krw: float = None) -> Dict[str, Any]`

Execute sell order (market order).

**Parameters**:
- `ticker` (str): Cryptocurrency to sell
- `quantity` (float, optional): Amount of coins to sell
- `amount_krw` (float, optional): Value in KRW to sell (one must be specified)

**Returns**:
- `dict`: Trade result (same structure as `buy_coin`)

**Example**:
```python
# Sell by quantity
result = bot.sell_coin('BTC', quantity=0.001)

# Sell by KRW value
result = bot.sell_coin('BTC', amount_krw=50000)
```

**Notes**:
- Calculates profit using FIFO method
- Updates portfolio tracking
- In dry-run, simulates without API call

---

#### Properties

```python
bot.daily_trade_count       # int: Trades executed today
bot.consecutive_losses      # int: Current loss streak
bot.total_profit            # float: Cumulative profit (KRW)
bot.win_count              # int: Successful trades
bot.loss_count             # int: Losing trades
bot.emergency_stop          # bool: Emergency stop flag
```

**Example**:
```python
print(f"Today's trades: {bot.daily_trade_count}/{bot.max_daily_trades}")
print(f"Win/Loss: {bot.win_count}/{bot.loss_count}")
print(f"Total profit: {bot.total_profit:,.0f} KRW")
```

---

## Configuration Manager API

### Module: `config_manager.py`

Dynamic configuration updates without bot restart.

---

### Class: `ConfigManager`

Runtime configuration management.

#### Constructor

```python
ConfigManager(config_path: str = 'config.py')
```

**Parameters**:
- `config_path` (str): Path to config file

---

#### `update_strategy_param(param_name: str, value: Any) -> bool`

Update a single strategy parameter.

**Parameters**:
- `param_name` (str): Parameter key (e.g., 'rsi_period')
- `value` (Any): New value

**Returns**:
- `bool`: Success status

**Example**:
```python
from config_manager import ConfigManager

cm = ConfigManager()
cm.update_strategy_param('rsi_period', 21)
cm.update_strategy_param('confidence_threshold', 0.7)
```

---

#### `apply_interval_preset(interval: str) -> bool`

Apply optimized preset for a timeframe.

**Parameters**:
- `interval` (str): '30m' | '1h' | '6h' | '12h' | '24h'

**Returns**:
- `bool`: Success status

**Example**:
```python
cm = ConfigManager()
cm.apply_interval_preset('6h')  # Switch to 6-hour strategy
```

---

#### `update_signal_weights(weights: Dict[str, float]) -> bool`

Update indicator signal weights.

**Parameters**:
- `weights` (dict): New weights (must sum to 1.0)

**Returns**:
- `bool`: Success status

**Example**:
```python
new_weights = {
    'macd': 0.40,
    'ma': 0.30,
    'rsi': 0.20,
    'bb': 0.05,
    'volume': 0.05
}
cm.update_signal_weights(new_weights)
```

---

#### `get_current_config() -> Dict[str, Any]`

Get current configuration snapshot.

**Returns**:
- `dict`: Full configuration

**Example**:
```python
config = cm.get_current_config()
print(f"Current interval: {config['strategy']['candlestick_interval']}")
print(f"RSI period: {config['strategy']['rsi_period']}")
```

---

## Logging System API

### Module: `logger.py`

Multi-channel logging and transaction history.

---

### Class: `TradingLogger`

Comprehensive logging system.

#### Constructor

```python
TradingLogger(
    log_dir: str = 'logs',
    log_level: str = 'INFO',
    enable_console: bool = True,
    enable_file: bool = True
)
```

---

#### `log_decision(ticker: str, decision: str, analysis: Dict, signals: Dict)`

Log trading decision with full analysis.

**Parameters**:
- `ticker` (str): Cryptocurrency
- `decision` (str): 'BUY' | 'SELL' | 'HOLD'
- `analysis` (dict): Market analysis data
- `signals` (dict): Signal generation data

**Example**:
```python
from logger import TradingLogger

logger = TradingLogger()
logger.log_decision('BTC', 'BUY', analysis, signals)
```

---

#### `log_trade(ticker: str, action: str, price: float, amount: float, fee: float = 0)`

Log executed trade.

**Parameters**:
- `ticker` (str): Cryptocurrency
- `action` (str): 'BUY' | 'SELL'
- `price` (float): Execution price
- `amount` (float): Quantity traded
- `fee` (float): Transaction fee

**Example**:
```python
logger.log_trade('BTC', 'BUY', 98500000, 0.001, 246.25)
```

---

#### `log_error(message: str, exception: Exception = None)`

Log errors with optional stack trace.

**Example**:
```python
try:
    # ... code ...
except Exception as e:
    logger.log_error("Failed to execute trade", e)
```

---

### Class: `TransactionHistory`

Transaction tracking and profit calculation.

#### `record_transaction(transaction: Dict) -> bool`

Record a transaction with all details.

**Parameters**:
- `transaction` (dict): Transaction data
  ```python
  {
      'timestamp': datetime,
      'ticker': str,
      'action': 'BUY' | 'SELL',
      'price': float,
      'quantity': float,
      'amount_krw': float,
      'fee': float,
      'profit': float | None,  # For sells
      'profit_pct': float | None
  }
  ```

**Returns**:
- `bool`: Success status

**Example**:
```python
from logger import TransactionHistory

history = TransactionHistory()
history.record_transaction({
    'timestamp': datetime.now(),
    'ticker': 'BTC',
    'action': 'BUY',
    'price': 98500000,
    'quantity': 0.001,
    'amount_krw': 98500,
    'fee': 246.25,
    'profit': None,
    'profit_pct': None
})
```

---

#### `get_transactions(ticker: str = None, start_date: datetime = None, end_date: datetime = None) -> List[Dict]`

Query transaction history.

**Parameters**:
- `ticker` (str, optional): Filter by cryptocurrency
- `start_date` (datetime, optional): Start date filter
- `end_date` (datetime, optional): End date filter

**Returns**:
- `list`: Matching transactions

**Example**:
```python
# All BTC transactions
btc_txs = history.get_transactions(ticker='BTC')

# Last 7 days
week_ago = datetime.now() - timedelta(days=7)
recent_txs = history.get_transactions(start_date=week_ago)
```

---

#### `calculate_statistics(ticker: str = None) -> Dict[str, Any]`

Calculate performance statistics.

**Returns**:
```python
{
    'total_trades': int,
    'buy_count': int,
    'sell_count': int,
    'total_profit': float,
    'win_count': int,
    'loss_count': int,
    'win_rate': float,  # 0.0-1.0
    'avg_profit': float,
    'max_profit': float,
    'max_loss': float,
    'total_fees': float
}
```

**Example**:
```python
stats = history.calculate_statistics('BTC')
print(f"Win Rate: {stats['win_rate']:.1%}")
print(f"Total Profit: {stats['total_profit']:,.0f} KRW")
print(f"Avg Profit: {stats['avg_profit']:,.0f} KRW")
```

---

## GUI Components API

### Module: `gui_app.py`

Main GUI application.

---

### Class: `TradingBotGUI`

Tkinter-based graphical interface.

#### Constructor

```python
TradingBotGUI(root: tk.Tk)
```

**Parameters**:
- `root` (tk.Tk): Tkinter root window

**Example**:
```python
import tkinter as tk
from gui_app import TradingBotGUI

root = tk.Tk()
app = TradingBotGUI(root)
root.mainloop()
```

---

#### Key Methods (Internal)

These are typically not called directly but documented for reference.

```python
def start_bot(self):
    """Start trading bot in background thread"""

def stop_bot(self):
    """Stop trading bot gracefully"""

def update_gui(self):
    """Update all GUI elements (called every 100ms)"""

def apply_settings(self):
    """Apply user configuration changes"""
```

---

### Module: `chart_widget.py`

Real-time chart widget.

---

### Class: `ChartWidget`

Candlestick chart with indicators.

#### Constructor

```python
ChartWidget(parent_frame: tk.Frame, config: Dict)
```

**Example**:
```python
from chart_widget import ChartWidget

chart_frame = tk.Frame(parent)
chart_widget = ChartWidget(chart_frame, config)
```

---

#### `update_chart(ticker: str = 'BTC', interval: str = '1h')`

Refresh chart data and redraw.

**Parameters**:
- `ticker` (str): Cryptocurrency symbol
- `interval` (str): Timeframe

**Example**:
```python
chart_widget.update_chart('BTC', '1h')
```

---

## Utility Functions

### Module: `strategy.py`

---

#### `detect_market_regime(adx: float, atr_pct: float) -> Dict[str, Any]`

Classify market conditions.

**Parameters**:
- `adx` (float): ADX value (0-100)
- `atr_pct` (float): ATR as percentage of price

**Returns**:
```python
{
    'regime': 'Trending' | 'Ranging' | 'Transitional',
    'volatility': 'LOW' | 'NORMAL' | 'HIGH',
    'adx_value': float,
    'atr_pct': float,
    'recommendation': str
}
```

**Example**:
```python
from strategy import detect_market_regime

regime = detect_market_regime(adx=28.5, atr_pct=0.018)
print(f"Market: {regime['regime']}")
print(f"Volatility: {regime['volatility']}")
print(f"Recommendation: {regime['recommendation']}")
```

---

#### `calculate_atr_risk_levels(current_price: float, atr: float, multiplier: float = 2.0) -> Dict[str, Any]`

Calculate stop-loss and take-profit levels.

**Parameters**:
- `current_price` (float): Entry price
- `atr` (float): ATR value
- `multiplier` (float): Stop distance multiplier

**Returns**:
```python
{
    'entry_price': float,
    'stop_loss': float,
    'take_profit_1': float,
    'take_profit_2': float,
    'stop_pct': float,
    'tp1_pct': float,
    'tp2_pct': float,
    'rr_ratio_tp1': str,
    'rr_ratio_tp2': str,
    'position_sizing_advice': str
}
```

**Example**:
```python
from strategy import calculate_atr_risk_levels

levels = calculate_atr_risk_levels(
    current_price=100000,
    atr=1500,
    multiplier=2.0
)

print(f"Entry: {levels['entry_price']:,.0f}")
print(f"Stop: {levels['stop_loss']:,.0f} ({levels['stop_pct']:+.2f}%)")
print(f"TP1: {levels['take_profit_1']:,.0f} ({levels['tp1_pct']:+.2f}%)")
print(f"TP2: {levels['take_profit_2']:,.0f} ({levels['tp2_pct']:+.2f}%)")
print(f"R:R (TP2): {levels['rr_ratio_tp2']}")
```

---

## Error Handling

### Exception Types

The bot uses standard Python exceptions with descriptive messages.

---

### Common Exceptions

#### API Errors

```python
try:
    data = get_ticker('BTC')
except requests.RequestException as e:
    # Network error, API down, rate limit
    logger.log_error("API request failed", e)
except KeyError as e:
    # Unexpected API response format
    logger.log_error("Invalid API response", e)
```

#### Data Validation Errors

```python
try:
    analysis = strategy.analyze_market_data('BTC', '1h')
except ValueError as e:
    # Invalid parameters
    logger.log_error("Invalid input", e)
```

#### Trading Errors

```python
try:
    result = bot.buy_coin('BTC', 50000)
except Exception as e:
    # Insufficient balance, API error, etc.
    logger.log_error("Trade execution failed", e)
```

---

### Error Recovery Patterns

#### Retry with Exponential Backoff

```python
import time

def safe_api_call(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except requests.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait_time = 2 ** attempt
            print(f"Retry in {wait_time}s...")
            time.sleep(wait_time)

# Usage
data = safe_api_call(lambda: get_ticker('BTC'))
```

#### Graceful Degradation

```python
def execute_trading_cycle():
    try:
        analysis = strategy.analyze_market_data('BTC')
        # ... trading logic ...
    except Exception as e:
        logger.log_error("Trading cycle failed", e)
        # Don't crash - wait for next cycle
        return {'success': False, 'error': str(e)}
```

---

## Best Practices

### 1. Always Use Dry-Run for Testing

```python
bot = TradingBot(dry_run=True)  # Safe testing
# Test thoroughly before:
bot = TradingBot(dry_run=False)  # Live trading
```

### 2. Handle All API Exceptions

```python
try:
    data = get_ticker('BTC')
except Exception as e:
    logger.log_error("API call failed", e)
    # Have fallback logic
    return None
```

### 3. Validate Configuration

```python
from config import validate_config

if not validate_config():
    print("Invalid configuration!")
    exit(1)
```

### 4. Log Everything Important

```python
logger.log_decision('BTC', 'BUY', analysis, signals)
logger.log_trade('BTC', 'BUY', price, amount, fee)
# Logs are crucial for debugging and backtesting
```

### 5. Use Type Hints

```python
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    # Clear function signature
    pass
```

---

## Integration Examples

### Example 1: Custom Trading Script

```python
from trading_bot import TradingBot
from logger import TradingLogger
import schedule
import time

# Setup
logger = TradingLogger()
bot = TradingBot(logger=logger, dry_run=False)

# Define trading task
def trade():
    result = bot.execute_trading_cycle('BTC', '1h')
    print(f"Cycle complete: {result['decision']}")

# Schedule every 15 minutes
schedule.every(15).minutes.do(trade)

# Run forever
while True:
    schedule.run_pending()
    time.sleep(60)
```

### Example 2: Custom Indicator

```python
from strategy import TradingStrategy
import pandas as pd

class CustomStrategy(TradingStrategy):
    def calculate_custom_indicator(self, df: pd.DataFrame) -> pd.Series:
        # Your custom indicator logic
        return df['close'].rolling(window=14).mean() / df['close'].rolling(window=28).mean()

    def analyze_market_data(self, ticker, interval='1h'):
        # Call parent method
        analysis = super().analyze_market_data(ticker, interval)

        # Add custom indicator
        analysis['indicators']['custom'] = self.calculate_custom_indicator(analysis['price_data'])

        return analysis
```

### Example 3: Alert System

```python
from trading_bot import TradingBot

class AlertBot(TradingBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.alert_threshold = 0.8  # High confidence only

    def send_alert(self, message: str):
        # Implement email/SMS/Telegram notification
        print(f"ALERT: {message}")

    def execute_trading_cycle(self, *args, **kwargs):
        result = super().execute_trading_cycle(*args, **kwargs)

        # Send alert on high-confidence signals
        if result['signals']['confidence'] >= self.alert_threshold:
            self.send_alert(
                f"{result['decision']} signal for {result['ticker']}\n"
                f"Confidence: {result['signals']['confidence']:.1%}\n"
                f"Price: {result['analysis']['current_price']:,.0f} KRW"
            )

        return result
```

---

## API Changelog

### Version 2.0 (Elite Strategy) - 2025-10-01
- Added 4 new indicators: MACD, ATR, Stochastic, ADX
- Implemented weighted signal system
- Added market regime detection
- Added ATR-based risk management
- Changed default interval from 24h to 1h
- Added interval presets (30m, 1h, 6h, 12h, 24h)

### Version 1.0 - 2025-09-28
- Initial release
- Basic 4 indicators: MA, RSI, BB, Volume
- Simple voting-based signals
- CLI and GUI interfaces
- Transaction history tracking

---

## Support & Resources

- **Project Repository**: `/Users/seongwookjang/project/git/violet_sw/005_money/`
- **Main Documentation**: `CLAUDE.md`, `ARCHITECTURE.md`
- **User Guides**: `QUICK_START_GUIDE.md`, `COMPREHENSIVE_USER_MANUAL.md`
- **Strategy Guide**: `STRATEGY_TUNING_GUIDE.md`
- **Bithumb API Docs**: https://apidocs.bithumb.com/

---

**Document Version**: 1.0
**Last Updated**: 2025-10-02
**Maintained By**: Project Development Team
