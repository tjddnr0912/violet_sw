# Strategy Configuration & Tuning Guide

**Project**: Bithumb Cryptocurrency Trading Bot
**Version**: 2.0 (Elite Strategy)
**Last Updated**: 2025-10-02
**Audience**: Advanced Users, Strategy Developers

---

## Table of Contents

1. [Understanding the Elite Strategy](#understanding-the-elite-strategy)
2. [Configuration Files](#configuration-files)
3. [Indicator Parameters](#indicator-parameters)
4. [Signal Weights Tuning](#signal-weights-tuning)
5. [Interval Optimization](#interval-optimization)
6. [Risk Management Settings](#risk-management-settings)
7. [Strategy Presets](#strategy-presets)
8. [Optimization Workflows](#optimization-workflows)
9. [Advanced Techniques](#advanced-techniques)

---

## Understanding the Elite Strategy

### Core Philosophy

The Elite Strategy is based on **weighted signal combination** from 8 technical indicators, rather than simple binary voting. This approach provides:

1. **Gradual Signal Strength**: Each indicator contributes a value from -1.0 (strong sell) to +1.0 (strong buy)
2. **Configurable Weights**: Prioritize certain indicators based on market conditions
3. **Confidence Filtering**: Only trade when multiple indicators agree (high confidence)
4. **Market Regime Awareness**: Adjust strategy based on trending vs ranging markets

### Signal Flow

```
Market Data (OHLCV)
        │
        ▼
┌────────────────────────────────────────────┐
│  Calculate 8 Indicators                    │
│  - MA, RSI, MACD, BB, Volume               │
│  - Stochastic, ATR, ADX                    │
└────────────────┬───────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────┐
│  Generate Individual Signals (-1.0 to +1.0)│
│  - MA signal = trend difference            │
│  - RSI signal = overbought/oversold        │
│  - MACD signal = histogram strength        │
│  - etc.                                    │
└────────────────┬───────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────┐
│  Apply Weights & Combine                   │
│  overall_signal = Σ(signal[i] × weight[i]) │
│  confidence = Σ(|signal[i]| × weight[i])   │
└────────────────┬───────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────────────┐
│  Decision Logic                            │
│  IF overall_signal >= 0.5 AND              │
│     confidence >= 0.6                      │
│  THEN BUY                                  │
│                                            │
│  IF overall_signal <= -0.5 AND             │
│     confidence >= 0.6                      │
│  THEN SELL                                 │
│                                            │
│  ELSE HOLD                                 │
└────────────────────────────────────────────┘
```

---

## Configuration Files

### Primary Configuration: `config.py`

Location: `/Users/seongwookjang/project/git/violet_sw/005_money/config.py`

**Structure**:
```python
# API Configuration
BITHUMB_CONNECT_KEY = os.getenv("BITHUMB_CONNECT_KEY")
BITHUMB_SECRET_KEY = os.getenv("BITHUMB_SECRET_KEY")

# Trading Configuration
TRADING_CONFIG = {...}

# Strategy Configuration (150+ parameters)
STRATEGY_CONFIG = {
    'candlestick_interval': '1h',  # Core setting

    # Classic indicator parameters
    'short_ma_window': 20,
    'long_ma_window': 50,
    'rsi_period': 14,
    # ...

    # Elite indicator parameters
    'macd_fast': 8,
    'macd_slow': 17,
    'macd_signal': 9,
    'atr_period': 14,
    'stoch_k_period': 14,
    'adx_period': 14,
    # ...

    # Signal weights (CRITICAL)
    'signal_weights': {
        'macd': 0.35,
        'ma': 0.25,
        'rsi': 0.20,
        'bb': 0.10,
        'volume': 0.10
    },

    # Decision thresholds
    'confidence_threshold': 0.6,
    'signal_threshold': 0.5,

    # Interval presets (30m, 1h, 6h, 12h, 24h)
    'interval_presets': {...}
}

# Schedule, Logging, Safety configurations
SCHEDULE_CONFIG = {...}
LOGGING_CONFIG = {...}
SAFETY_CONFIG = {...}
```

### Runtime Configuration: `config_manager.py`

Used for dynamic updates without restarting the bot.

**Key Methods**:
```python
config_manager = ConfigManager()

# Update single parameter
config_manager.update_strategy_param('rsi_period', 21)

# Apply interval preset
config_manager.apply_interval_preset('6h')

# Update signal weights
config_manager.update_signal_weights({
    'macd': 0.40,
    'rsi': 0.30,
    'ma': 0.20,
    'bb': 0.05,
    'volume': 0.05
})

# Get current config
current = config_manager.get_current_config()
```

---

## Indicator Parameters

### 1. Moving Averages (MA)

**Purpose**: Trend identification and direction
**Parameters**:
```python
'short_ma_window': 20,   # Fast MA period
'long_ma_window': 50,    # Slow MA period
```

**Tuning Guidelines**:
- **Faster response**: Decrease windows (e.g., 10/30)
- **Smoother trend**: Increase windows (e.g., 50/200)
- **Short-term trading**: Use 5/20 or 10/30
- **Long-term trading**: Use 50/200

**Signal Generation**:
```python
signal = (short_ma - long_ma) / current_price
# Positive = uptrend, Negative = downtrend
# Normalized to -1.0 to +1.0 range
```

**Optimal Values by Timeframe**:
| Interval | Short MA | Long MA | Rationale |
|----------|----------|---------|-----------|
| 30m      | 20 (10h) | 50 (25h)| Responsive to intraday moves |
| 1h       | 20 (20h) | 50 (50h)| Balanced trend detection |
| 6h       | 10 (60h) | 30 (180h)| Multi-day trends |
| 24h      | 5 (5d)   | 20 (20d)| Long-term trends |

### 2. Relative Strength Index (RSI)

**Purpose**: Overbought/oversold detection
**Parameters**:
```python
'rsi_period': 14,         # Lookback period
'rsi_overbought': 70,     # Upper threshold
'rsi_oversold': 30,       # Lower threshold
```

**Tuning Guidelines**:
- **Crypto markets**: Use 14 (standard)
- **Volatile markets**: Increase to 21 (smoother)
- **Fast scalping**: Decrease to 7-9 (more signals)
- **Thresholds**: Crypto can use 20/80 instead of 30/70 (extreme)

**Signal Generation**:
```python
if rsi < 30:
    signal = -1.0  # Oversold, buy signal
elif rsi > 70:
    signal = +1.0  # Overbought, sell signal
else:
    signal = 0.0   # Neutral
```

**Advanced Tip**: In strong trends, RSI can stay overbought/oversold for extended periods. Consider using RSI divergence or combining with trend filters.

### 3. MACD (Moving Average Convergence Divergence)

**Purpose**: Momentum and trend strength
**Parameters** (1h optimized):
```python
'macd_fast': 8,           # Fast EMA period (8 hours)
'macd_slow': 17,          # Slow EMA period (17 hours)
'macd_signal': 9,         # Signal line EMA (9 hours)
```

**Tuning Guidelines**:
- **Standard**: 12/26/9 (daily chart default)
- **Crypto 1h**: 8/17/9 (faster reaction)
- **Crypto 30m**: 6/13/7 (even faster)
- **Smoothing**: Increase all proportionally (e.g., 16/34/18)

**Signal Generation**:
```python
histogram = macd_line - signal_line
signal = np.tanh(histogram / price * 1000)  # Normalized
# Positive = bullish momentum
# Negative = bearish momentum
```

**Why MACD Has Highest Weight (0.35)**:
- Combines trend direction and momentum
- Less prone to false signals than MA alone
- Works well in both trending and ranging markets
- Histogram provides clear signal strength

### 4. Bollinger Bands (BB)

**Purpose**: Mean reversion and volatility measurement
**Parameters**:
```python
'bb_period': 20,          # MA period for middle band
'bb_std': 2.0,            # Standard deviation multiplier
```

**Tuning Guidelines**:
- **Crypto markets**: Use 2.0-2.5 std (higher volatility)
- **Low volatility**: Use 1.5-2.0 std
- **Shorter period**: 10-15 for faster adaptation
- **Longer period**: 30-50 for smoother bands

**Signal Generation**:
```python
position = (price - lower_band) / (upper_band - lower_band)
if position < 0.2:
    signal = -1.0  # Near lower band, buy
elif position > 0.8:
    signal = +1.0  # Near upper band, sell
else:
    signal = 0.0   # Middle range, neutral
```

**Best Use Case**: Range-bound markets (ADX < 20)

### 5. Stochastic Oscillator

**Purpose**: Momentum confirmation, secondary overbought/oversold
**Parameters**:
```python
'stoch_k_period': 14,     # %K period
'stoch_d_period': 3,      # %D period (smoothing)
```

**Tuning Guidelines**:
- **Standard**: 14/3 (Williams' original)
- **Faster**: 9/3 or 5/3
- **Smoother**: 21/3 or 14/5

**Signal Generation**:
```python
if k < 20 and k > d:
    signal = -1.0  # Oversold + bullish crossover
elif k > 80 and k < d:
    signal = +1.0  # Overbought + bearish crossover
else:
    signal = 0.0
```

**Best Combined With**: RSI (confirms overbought/oversold)

### 6. ATR (Average True Range)

**Purpose**: Volatility measurement, risk management
**Parameters**:
```python
'atr_period': 14,              # Lookback period
'atr_stop_multiplier': 2.0,    # Stop-loss distance
```

**Tuning Guidelines**:
- **Standard**: 14 (Wilder's original)
- **More reactive**: 7-10
- **Smoother**: 21-28
- **Stop multiplier**: 1.5-2.5 (higher = wider stops)

**Signal Generation**:
```python
# ATR doesn't generate buy/sell signals directly
# Used for position sizing and stop-loss calculation

atr_pct = atr / current_price
if atr_pct > 0.03:  # 3% volatility
    volatility = "HIGH"
    # Recommendation: reduce position size
elif atr_pct > 0.01:
    volatility = "NORMAL"
else:
    volatility = "LOW"
    # Can use tighter stops
```

**ATR-Based Stop Loss**:
```python
entry_price = 100000
atr_value = 1500
multiplier = 2.0

stop_loss = entry_price - (atr_value * multiplier)
# = 100000 - 3000 = 97000
```

### 7. ADX (Average Directional Index)

**Purpose**: Trend strength measurement (not direction)
**Parameters**:
```python
'adx_period': 14,                    # Lookback period
'adx_trending_threshold': 25,        # Strong trend > 25
'adx_ranging_threshold': 15,         # Weak trend < 15
```

**Tuning Guidelines**:
- **Standard**: 14 (Wilder's original)
- **Faster**: 7-10 (more responsive)
- **Smoother**: 21-28 (less noise)
- **Thresholds**: Crypto can use 20/10 (more sensitive)

**Signal Generation**:
```python
# ADX doesn't generate buy/sell signals
# Used for market regime detection

if adx > 25:
    market_regime = "Trending"
    # Use trend-following strategies (MACD, MA)
elif adx < 15:
    market_regime = "Ranging"
    # Use mean-reversion strategies (RSI, BB)
else:
    market_regime = "Transitional"
    # Be cautious, mixed signals likely
```

**Regime-Based Weight Adjustment** (Advanced):
```python
if market_regime == "Trending":
    weights = {
        'macd': 0.40,  # Increase MACD
        'ma': 0.30,    # Increase MA
        'rsi': 0.15,   # Reduce RSI
        'bb': 0.05,    # Reduce BB
        'volume': 0.10
    }
elif market_regime == "Ranging":
    weights = {
        'macd': 0.20,
        'ma': 0.15,
        'rsi': 0.30,   # Increase RSI
        'bb': 0.25,    # Increase BB
        'volume': 0.10
    }
```

### 8. Volume

**Purpose**: Signal confirmation, liquidity check
**Parameters**:
```python
'volume_window': 20,          # Average volume period
'volume_threshold': 1.5,      # Threshold for "high volume"
```

**Tuning Guidelines**:
- **Standard**: 20 (matches BB period)
- **Shorter**: 10 (more sensitive to recent volume)
- **Longer**: 50 (smoother average)
- **Threshold**: 1.5-2.0 (1.5x-2.0x average)

**Signal Generation**:
```python
volume_ratio = current_volume / avg_volume

if volume_ratio > 1.5:
    volume_signal = 1.0  # Confirms other signals
else:
    volume_signal = 0.0  # Weak confirmation
```

**Best Practice**: Volume doesn't generate independent signals, but acts as a **multiplier** for other signals. High volume = more reliable signal.

---

## Signal Weights Tuning

### Default Weights (Balanced Elite)

```python
'signal_weights': {
    'macd': 0.35,       # Highest (trend + momentum)
    'ma': 0.25,         # High (trend confirmation)
    'rsi': 0.20,        # Medium (overbought/oversold filter)
    'bb': 0.10,         # Low (mean reversion)
    'volume': 0.10      # Low (confirmation only)
}
```

**Sum must equal 1.0** (100% total weight)

### Weight Adjustment Strategies

#### 1. Trend-Following Emphasis
**Use When**: ADX > 25, strong directional moves
```python
'signal_weights': {
    'macd': 0.40,       # ↑ Increase momentum
    'ma': 0.35,         # ↑ Increase trend
    'rsi': 0.10,        # ↓ Reduce mean reversion
    'bb': 0.05,         # ↓ Reduce mean reversion
    'volume': 0.10
}
```

#### 2. Mean Reversion Emphasis
**Use When**: ADX < 20, sideways/choppy markets
```python
'signal_weights': {
    'macd': 0.20,       # ↓ Reduce momentum
    'ma': 0.15,         # ↓ Reduce trend
    'rsi': 0.30,        # ↑ Increase oscillators
    'bb': 0.25,         # ↑ Increase oscillators
    'volume': 0.10
}
```

#### 3. Momentum-Focused
**Use When**: High volatility, fast-moving markets
```python
'signal_weights': {
    'macd': 0.50,       # ↑↑ Maximum momentum
    'ma': 0.20,
    'rsi': 0.20,
    'bb': 0.05,
    'volume': 0.05
}
```

#### 4. Conservative (High Confirmation)
**Use When**: Uncertain conditions, want fewer but better trades
```python
'signal_weights': {
    'macd': 0.30,
    'ma': 0.25,
    'rsi': 0.20,
    'bb': 0.15,
    'volume': 0.10      # Equal weighting for consensus
}

# Also increase confidence threshold
'confidence_threshold': 0.75  # Higher bar for trading
```

### Empirical Weight Optimization

**Process**:
1. Run bot in dry-run mode for 1-2 weeks with default weights
2. Analyze transaction history JSON
3. Identify which signals were most accurate
4. Adjust weights to favor accurate indicators
5. Repeat testing

**Example Analysis**:
```python
# Pseudocode for backtest analysis
correct_signals = {}
for trade in transaction_history:
    if trade['profit'] > 0:
        # Which indicators signaled correctly?
        for indicator, signal in trade['signals'].items():
            if signal == trade['direction']:
                correct_signals[indicator] += 1

# Indicators with higher accuracy get higher weights
```

---

## Interval Optimization

### Interval Presets

The system includes 5 optimized presets for different timeframes.

#### 30m (Short-Term Swing Trading)
**Best For**: Active day trading, quick moves
**Check Interval**: Every 10 minutes
```python
'30m': {
    'short_ma_window': 20,      # 10 hours
    'long_ma_window': 50,       # 25 hours
    'rsi_period': 9,            # Faster reaction
    'macd_fast': 8,
    'macd_slow': 17,
    'macd_signal': 9,
    'bb_std': 2.5,              # Higher for crypto
    'analysis_period': 100,     # 50 hours data
}
```

**Pros**: More trading opportunities, catches short-term moves
**Cons**: More false signals, higher transaction costs, requires frequent monitoring

#### 1h (Medium-Term Trading) **[DEFAULT]**
**Best For**: Balanced approach, part-time traders
**Check Interval**: Every 15 minutes
```python
'1h': {
    'short_ma_window': 20,      # 20 hours
    'long_ma_window': 50,       # 50 hours (~2 days)
    'rsi_period': 14,
    'macd_fast': 8,
    'macd_slow': 17,
    'macd_signal': 9,
    'bb_std': 2.0,
    'analysis_period': 100,     # 100 hours (~4 days)
}
```

**Pros**: Good balance of signal quality and frequency
**Cons**: May miss very short-term opportunities

**Recommended Starting Point**

#### 6h (Medium-Long Term)
**Best For**: Swing trading, reduced monitoring
**Check Interval**: Every 60 minutes
```python
'6h': {
    'short_ma_window': 10,      # 60 hours (2.5 days)
    'long_ma_window': 30,       # 180 hours (7.5 days)
    'macd_fast': 12,            # Standard MACD
    'macd_slow': 26,
    'macd_signal': 9,
    'analysis_period': 50,      # 300 hours (12.5 days)
}
```

**Pros**: Fewer false signals, less monitoring needed
**Cons**: Slower to react, fewer trades

#### 12h (Position Trading)
**Best For**: Part-time traders, longer holds
**Check Interval**: Every 2 hours
```python
'12h': {
    'short_ma_window': 7,       # 84 hours (3.5 days)
    'long_ma_window': 25,       # 300 hours (12.5 days)
    'macd_fast': 12,
    'analysis_period': 40,      # 480 hours (20 days)
}
```

#### 24h (Long-Term Investment)
**Best For**: Position trading, minimal effort
**Check Interval**: Every 4 hours
```python
'24h': {
    'short_ma_window': 5,       # 5 days
    'long_ma_window': 20,       # 20 days
    'macd_fast': 12,
    'macd_slow': 26,
    'analysis_period': 30,      # 30 days
}
```

**Pros**: Very high quality signals, minimal monitoring
**Cons**: Very few trades, slow to react to news

### Switching Intervals

**Via Configuration File**:
```python
# Edit config.py
STRATEGY_CONFIG = {
    'candlestick_interval': '6h',  # Change from 1h to 6h
    # ...
}

# Restart bot to apply
```

**Via GUI**:
1. Open GUI
2. Select interval from dropdown (거래 설정 section)
3. Click "설정 적용" button
4. Bot automatically applies preset parameters

**Via ConfigManager**:
```python
config_manager = ConfigManager()
config_manager.apply_interval_preset('6h')
```

### Custom Interval Parameters

**Advanced**: Create your own optimized parameters for an interval.

**Process**:
1. Calculate time coverage:
   - Example: 30m interval, MA window=20 → 20 × 0.5h = 10 hours
   - Want 2-day coverage? 48h / 0.5h = 96 candles → use window=96

2. Test parameter combinations:
   ```python
   # Run backtests with variations
   test_configs = [
       {'short_ma': 15, 'long_ma': 40},
       {'short_ma': 20, 'long_ma': 50},
       {'short_ma': 25, 'long_ma': 60}
   ]
   ```

3. Add to `interval_presets` in config.py

---

## Risk Management Settings

### Trade Limits

```python
SAFETY_CONFIG = {
    'max_daily_trades': 10,        # Hard limit per day
    'max_consecutive_losses': 3,   # Stop after N losses
    'dry_run': False,              # Paper trading mode
}

STRATEGY_CONFIG = {
    'max_daily_loss_pct': 3.0,     # Max daily drawdown (%)
    'position_risk_pct': 1.0,      # Risk per trade (%)
}
```

**Tuning Guidelines**:

#### max_daily_trades
- **Conservative**: 3-5 trades/day
- **Balanced**: 10 trades/day (default)
- **Aggressive**: 20+ trades/day
- Consider: Transaction fees (0.25% per trade) add up

#### max_consecutive_losses
- **Conservative**: 2-3 (stop quickly)
- **Balanced**: 3-5 (default)
- **Aggressive**: No limit (not recommended)

#### max_daily_loss_pct
- **Conservative**: 1-2% (preserve capital)
- **Balanced**: 3% (default)
- **Aggressive**: 5-10% (high risk)
- Formula: Max loss = account_balance × (max_daily_loss_pct / 100)

#### position_risk_pct
- **Conservative**: 0.5% per trade
- **Balanced**: 1% per trade (default)
- **Aggressive**: 2-5% per trade
- Example: $10,000 account, 1% risk = $100 risk per trade

### ATR-Based Risk Management

```python
STRATEGY_CONFIG = {
    'atr_stop_multiplier': 2.0,    # Stop-loss distance
    # TP1 = 1.5x ATR (fixed in code)
    # TP2 = 2.5x ATR (fixed in code)
}
```

**Stop Multiplier Tuning**:
- **Tight stops** (1.5x ATR): Higher win rate, smaller profits, more stopped out
- **Medium stops** (2.0x ATR): Balanced (default)
- **Wide stops** (3.0x ATR): Lower win rate, larger profits, less stopped out

**Example Calculation**:
```
Entry Price: 100,000 KRW
ATR: 1,500 KRW (1.5%)
Multiplier: 2.0

Stop Loss = 100,000 - (1,500 × 2.0) = 97,000 KRW (-3%)
TP1 = 100,000 + (1,500 × 1.5) = 102,250 KRW (+2.25%)
TP2 = 100,000 + (1,500 × 2.5) = 103,750 KRW (+3.75%)

R:R Ratio (TP1) = 2,250 / 3,000 = 1:0.75 (not ideal)
R:R Ratio (TP2) = 3,750 / 3,000 = 1:1.25 (acceptable)
```

**Optimal R:R**: Target at least 1:1.5 (risk $1 to make $1.50)

### Decision Thresholds

```python
STRATEGY_CONFIG = {
    'confidence_threshold': 0.6,   # Minimum confidence to trade
    'signal_threshold': 0.5,       # Minimum signal strength
}
```

**Confidence Threshold** (0.0 to 1.0):
- **Aggressive** (0.4-0.5): More trades, lower quality
- **Balanced** (0.6): Default, good filter
- **Conservative** (0.7-0.8): Fewer trades, higher quality

**Signal Threshold** (-1.0 to +1.0):
- **Aggressive** (0.3 / -0.3): Weaker signals accepted
- **Balanced** (0.5 / -0.5): Default
- **Conservative** (0.7 / -0.7): Only very strong signals

**Example Impact**:
```
Scenario A: confidence=0.55, signal=0.45
Default (0.6, 0.5): NO TRADE (confidence too low)
Aggressive (0.5, 0.4): TRADE (both thresholds met)

Scenario B: confidence=0.75, signal=0.65
All settings: TRADE (clear signal)
```

---

## Strategy Presets

### GUI Strategy Selector

The GUI provides 5 preset strategies accessible via dropdown.

### 1. Balanced Elite (Default)

**Use Case**: Starting out, all-weather strategy
**Signal Weights**:
```python
{
    'macd': 0.35,
    'ma': 0.25,
    'rsi': 0.20,
    'bb': 0.10,
    'volume': 0.10
}
```

**Characteristics**:
- Balanced between trend-following and mean reversion
- Works in most market conditions
- Medium signal frequency
- Medium risk

**Expected Performance**:
- Win rate: 50-60%
- Average R:R: 1:1.5
- Trades/week: 3-7 (on 1h interval)

### 2. Trend Following

**Use Case**: Strong uptrends or downtrends (ADX > 25)
**Signal Weights**:
```python
{
    'macd': 0.45,    # ↑ High momentum weight
    'ma': 0.35,      # ↑ High trend weight
    'rsi': 0.10,     # ↓ Low mean reversion
    'bb': 0.05,      # ↓ Low mean reversion
    'volume': 0.05
}
```

**Characteristics**:
- Rides strong trends for maximum profit
- Ignores small pullbacks
- Fewer signals, but larger moves
- Higher risk (wider stops)

**Expected Performance**:
- Win rate: 40-50% (fewer but bigger wins)
- Average R:R: 1:2.5
- Trades/week: 1-3

**Caution**: Performs poorly in ranging markets (ADX < 20)

### 3. Mean Reversion

**Use Case**: Sideways/consolidation (ADX < 20)
**Signal Weights**:
```python
{
    'macd': 0.20,    # ↓ Low momentum
    'ma': 0.15,      # ↓ Low trend
    'rsi': 0.30,     # ↑ High oscillator
    'bb': 0.25,      # ↑ High oscillator
    'volume': 0.10
}
```

**Characteristics**:
- Buys dips, sells rallies
- Works in range-bound markets
- More frequent signals
- Lower risk (tighter stops)

**Expected Performance**:
- Win rate: 60-70% (smaller, more consistent wins)
- Average R:R: 1:1.0
- Trades/week: 5-10

**Caution**: Gets stopped out in strong trends

### 4. MACD + RSI Filter

**Use Case**: Clear trends with momentum confirmation
**Signal Weights**:
```python
{
    'macd': 0.50,    # ↑↑ Dominant
    'ma': 0.15,
    'rsi': 0.25,     # ↑ Strong filter
    'bb': 0.05,
    'volume': 0.05
}
```

**Characteristics**:
- Only trades when MACD and RSI align
- High quality signals
- Very low false positive rate
- Conservative approach

**Expected Performance**:
- Win rate: 60-70%
- Average R:R: 1:2.0
- Trades/week: 1-2 (very selective)

**Best For**: Beginners wanting fewer but safer trades

### 5. Custom

**Use Case**: Advanced users with specific requirements
**Configuration**: User manually sets weights via config.py

**Example Custom Strategies**:

**Scalping Strategy** (30m interval):
```python
{
    'macd': 0.40,
    'rsi': 0.30,
    'volume': 0.20,  # ↑ High volume importance
    'ma': 0.05,
    'bb': 0.05
}
# Fast indicators, high volume filter
```

**Position Trading** (24h interval):
```python
{
    'ma': 0.40,      # ↑ Long-term trend
    'macd': 0.30,
    'adx': 0.20,     # ↑ Trend strength
    'rsi': 0.05,
    'bb': 0.05
}
# Long-term trend confirmation
```

---

## Optimization Workflows

### Workflow 1: New User Initial Setup

**Goal**: Find a working configuration quickly

**Steps**:
1. **Start with defaults** (Balanced Elite, 1h interval)
2. **Run dry-run mode** for 1 week
3. **Review logs**: Check decision quality
   ```bash
   tail -100 logs/trading_YYYYMMDD.log
   ```
4. **Count signals**: Should see 3-7 per week
   - Too many? Increase confidence_threshold to 0.7
   - Too few? Decrease to 0.5
5. **If working well**: Continue to live trading with small amounts
6. **If not working**: Try different interval or preset

### Workflow 2: Strategy Optimization (Intermediate)

**Goal**: Improve win rate and profitability

**Steps**:
1. **Analyze past performance**:
   ```python
   # Review transaction_history.json
   win_rate = wins / total_trades
   avg_profit = sum(profits) / len(profits)
   ```

2. **Identify weak indicators**:
   - Which indicators signaled incorrectly most often?
   - Reduce their weights

3. **Identify strong indicators**:
   - Which indicators were most accurate?
   - Increase their weights

4. **Test modifications** (dry-run for 1-2 weeks)

5. **Compare results**:
   | Metric | Before | After | Change |
   |--------|--------|-------|--------|
   | Win rate | 52% | 58% | +6% |
   | Avg profit | +1.5% | +2.1% | +0.6% |
   | Trades/week | 5 | 3 | -2 (good) |

6. **Iterate**: Repeat process monthly

### Workflow 3: Market Regime Adaptation (Advanced)

**Goal**: Dynamically adjust strategy based on market conditions

**Steps**:
1. **Monitor ADX** in GUI (Market Regime panel)

2. **Set rules**:
   ```python
   if adx > 25:  # Trending
       apply_preset('Trend Following')
   elif adx < 15:  # Ranging
       apply_preset('Mean Reversion')
   else:  # Transitional
       apply_preset('Balanced Elite')
   ```

3. **Manual switching** via GUI for now
   - Future: Automated regime-based switching

4. **Track performance by regime**:
   ```
   Trending markets (ADX > 25): +8% total
   Ranging markets (ADX < 15): +3% total
   Transitional (15-25): -2% total (avoid?)
   ```

### Workflow 4: Parameter Grid Search (Expert)

**Goal**: Find optimal parameters via systematic testing

**Setup**:
```python
# Create test script
param_grid = {
    'confidence_threshold': [0.5, 0.6, 0.7],
    'signal_threshold': [0.4, 0.5, 0.6],
    'macd_weight': [0.30, 0.35, 0.40]
}

# Test all combinations (3 × 3 × 3 = 27 tests)
for conf in param_grid['confidence_threshold']:
    for sig in param_grid['signal_threshold']:
        for macd in param_grid['macd_weight']:
            # Run backtest
            results = run_backtest(conf, sig, macd)
            # Record performance
```

**Metrics to Track**:
- Total profit
- Win rate
- Max drawdown
- Sharpe ratio (risk-adjusted return)
- Number of trades

**Select Best Configuration**:
- Highest Sharpe ratio (not highest profit)
- Reasonable trade frequency (3-10/week)
- Max drawdown < 10%

---

## Advanced Techniques

### 1. Indicator Correlation Analysis

**Problem**: Some indicators may be redundant (highly correlated)

**Solution**: Measure correlation between indicators
```python
import pandas as pd

# Collect indicator values over time
indicator_data = pd.DataFrame({
    'ma_signal': [...],
    'macd_signal': [...],
    'rsi_signal': [...],
    # etc.
})

# Calculate correlation matrix
correlation = indicator_data.corr()
print(correlation)

# Example output:
#       ma    macd   rsi    bb
# ma   1.00  0.85  -0.45  -0.30
# macd 0.85  1.00  -0.40  -0.25
# rsi  -0.45 -0.40  1.00   0.75
# bb   -0.30 -0.25  0.75   1.00
```

**Interpretation**:
- MA and MACD are highly correlated (0.85) → May be redundant
- RSI and BB are highly correlated (0.75) → Both measure mean reversion
- Negative correlation (-0.45) → MA and RSI oppose each other (good diversity)

**Action**:
- If two indicators correlate > 0.8, consider reducing one's weight
- Aim for diverse signals (mix of positive and negative correlations)

### 2. Signal Decay (Time-Based Weight Adjustment)

**Concept**: Recent signals should have more weight than older ones

**Implementation**:
```python
def calculate_time_weighted_signal(signals, timestamps):
    """
    Apply exponential decay to older signals
    """
    current_time = datetime.now()
    weighted_sum = 0
    total_weight = 0

    for signal, timestamp in zip(signals, timestamps):
        age_hours = (current_time - timestamp).total_seconds() / 3600
        decay_factor = np.exp(-age_hours / 24)  # Half-life of 24 hours

        weighted_sum += signal * decay_factor
        total_weight += decay_factor

    return weighted_sum / total_weight
```

**Use Case**: Gives more importance to recent signals, adapts faster to changing conditions

### 3. Volatility-Adjusted Position Sizing

**Concept**: Trade smaller size in high volatility, larger in low volatility

**Implementation**:
```python
def calculate_position_size(account_balance, atr_pct, base_risk_pct=1.0):
    """
    Adjust position size based on volatility
    """
    # Normalize ATR to 0-1 scale (0.5% ATR = 0, 5% ATR = 1)
    volatility_factor = np.clip((atr_pct - 0.005) / 0.045, 0, 1)

    # Reduce risk in high volatility (scale from 100% to 50%)
    adjusted_risk = base_risk_pct * (1 - 0.5 * volatility_factor)

    # Calculate position size
    position_size = account_balance * (adjusted_risk / 100)

    return position_size

# Example:
# Low vol (ATR = 0.5%): risk = 1.0% of account
# Med vol (ATR = 2.5%): risk = 0.75% of account
# High vol (ATR = 5.0%): risk = 0.5% of account
```

### 4. Multi-Timeframe Analysis

**Concept**: Check higher timeframe for trend direction, trade on lower timeframe

**Implementation**:
```python
def multi_timeframe_signal(ticker):
    """
    Combine signals from multiple timeframes
    """
    # Higher timeframe (24h) for trend direction
    ht_analysis = analyze_market_data(ticker, '24h')
    ht_trend = ht_analysis['signals']['ma']  # -1, 0, or +1

    # Lower timeframe (1h) for entry timing
    lt_analysis = analyze_market_data(ticker, '1h')
    lt_signals = generate_weighted_signals(lt_analysis)

    # Only trade if both align
    if ht_trend == 1 and lt_signals['decision'] == 'BUY':
        return 'BUY'
    elif ht_trend == -1 and lt_signals['decision'] == 'SELL':
        return 'SELL'
    else:
        return 'HOLD'  # Conflicting timeframes
```

**Benefits**:
- Reduces false signals (requires alignment)
- Trades in direction of higher trend
- Better win rate

### 5. Machine Learning Signal Weights

**Concept**: Use ML to optimize weights based on historical performance

**Steps**:
1. Collect training data (indicator signals + actual price movement)
2. Train model to predict optimal weights
3. Periodically retrain on recent data

**Simple Example** (Linear Regression):
```python
from sklearn.linear_model import LinearRegression

# Training data
X = indicator_signals  # Shape: (n_samples, 8_indicators)
y = future_returns     # Shape: (n_samples, 1)

# Train model
model = LinearRegression()
model.fit(X, y)

# Model coefficients = optimal weights
optimal_weights = model.coef_
# Normalize to sum to 1.0
optimal_weights = optimal_weights / np.sum(np.abs(optimal_weights))
```

**Caution**: Requires significant historical data and expertise to avoid overfitting

---

## Troubleshooting

### Issue: Too many false signals

**Symptoms**: Bot trades frequently but loses money
**Solutions**:
1. Increase `confidence_threshold` (0.6 → 0.7)
2. Increase `signal_threshold` (0.5 → 0.6)
3. Add volume filter (increase volume weight)
4. Switch to higher timeframe (1h → 6h)

### Issue: Missing good opportunities

**Symptoms**: Bot rarely trades, misses obvious moves
**Solutions**:
1. Decrease `confidence_threshold` (0.6 → 0.5)
2. Decrease `signal_threshold` (0.5 → 0.4)
3. Check indicator parameters (may be too slow)
4. Switch to lower timeframe (6h → 1h)

### Issue: Getting stopped out frequently

**Symptoms**: Many trades hit stop-loss
**Solutions**:
1. Increase `atr_stop_multiplier` (2.0 → 2.5 or 3.0)
2. Check if strategy suits market regime
3. Reduce position size (`position_risk_pct`)
4. Use wider timeframe for less noise

### Issue: Low profitability despite good win rate

**Symptoms**: Win rate > 60% but overall profit is low
**Solutions**:
1. R:R ratio too low (wins too small, losses too big)
2. Transaction fees eating profits (reduce trade frequency)
3. Adjust TP levels (increase TP2 target)
4. Hold winners longer (consider trailing stops)

---

## Further Reading

- **Technical Analysis of Financial Markets** by John Murphy (MA, RSI, MACD theory)
- **New Concepts in Technical Trading Systems** by J. Welles Wilder (RSI, ATR, ADX original papers)
- **Bollinger on Bollinger Bands** by John Bollinger
- **Cryptocurrency Trading Course** (online resources on crypto-specific strategies)

---

**Document Version**: 1.0
**Last Updated**: 2025-10-02
**Maintained By**: Project Lead
