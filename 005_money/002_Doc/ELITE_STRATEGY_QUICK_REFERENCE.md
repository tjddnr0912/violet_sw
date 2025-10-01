# Elite Strategy Quick Reference Guide

**For**: Developers & GUI Designers
**Updated**: 2025-10-01

---

## Critical Changes

### 🔴 DEFAULT INTERVAL CHANGED
```python
# OLD DEFAULT:
'candlestick_interval': '24h'

# NEW DEFAULT:
'candlestick_interval': '1h'  # ← 1-HOUR CANDLES NOW
```

**Impact**: All code using default interval now analyzes 1-hour data instead of 24-hour data.

---

## New Indicators Available

### 1. MACD (Moving Average Convergence Divergence)
```python
from strategy import calculate_macd

macd_line, signal_line, histogram = calculate_macd(df, fast=8, slow=17, signal=9)

# Access from analysis:
analysis = strategy.analyze_market_data("BTC", interval="1h")
analysis['macd_line']       # Current MACD line value
analysis['macd_signal']     # Signal line value
analysis['macd_histogram']  # Histogram (MACD - Signal)
```

**Interpretation**:
- `macd_line > signal_line` → Bullish (Golden Cross)
- `macd_line < signal_line` → Bearish (Death Cross)
- `histogram > 0` → Momentum increasing
- `histogram < 0` → Momentum decreasing

---

### 2. ATR (Average True Range)
```python
from strategy import calculate_atr, calculate_atr_percent

atr = calculate_atr(df, period=14)
atr_pct = calculate_atr_percent(df, period=14)

# Access from analysis:
analysis['atr']         # ATR in KRW (e.g., 1,000,000)
analysis['atr_percent'] # ATR as % of price (e.g., 2.5%)
```

**Usage**:
- Measure volatility
- Set dynamic stop-loss: `entry_price - (2.0 × ATR)`
- Calculate position size based on risk

---

### 3. Stochastic Oscillator
```python
from strategy import calculate_stochastic

stoch_k, stoch_d = calculate_stochastic(df, k_period=14, d_period=3)

# Access from analysis:
analysis['stoch_k']  # %K value (0-100)
analysis['stoch_d']  # %D value (0-100)
```

**Interpretation**:
- `%K < 20 and %D < 20` → Oversold (potential buy)
- `%K > 80 and %D > 80` → Overbought (potential sell)
- `%K crosses above %D` → Bullish signal
- `%K crosses below %D` → Bearish signal

---

### 4. ADX (Average Directional Index)
```python
from strategy import calculate_adx

adx = calculate_adx(df, period=14)

# Access from analysis:
analysis['adx']  # ADX value (0-100)
```

**Interpretation**:
- `ADX > 25` → Strong trend (use trend-following)
- `ADX < 15` → Weak trend/ranging (use mean reversion)
- `15 ≤ ADX ≤ 25` → Transitional (be cautious)

---

## Market Regime Detection

```python
from strategy import detect_market_regime

analysis = strategy.analyze_market_data("BTC", interval="1h")
regime = analysis['regime']

print(regime['regime'])              # 'trending', 'ranging', or 'transitional'
print(regime['volatility_level'])    # 'low', 'normal', or 'high'
print(regime['recommendation'])      # 'TREND_FOLLOW', 'MEAN_REVERSION', etc.
print(regime['trend_strength'])      # 0.0 to 1.0
print(regime['current_adx'])         # Current ADX value
print(regime['current_atr_pct'])     # Current ATR percentage
```

**Trading Recommendations**:
| Regime | Volatility | Recommendation | Preferred Indicators |
|--------|-----------|----------------|---------------------|
| Trending | Normal | TREND_FOLLOW | MACD, MA |
| Ranging | Normal | MEAN_REVERSION | RSI, Bollinger Bands |
| Any | High | REDUCE_SIZE | All (reduce position) |
| Transitional | Any | WAIT | None (observe) |

---

## Weighted Signal System

### Basic Usage
```python
analysis = strategy.analyze_market_data("BTC", interval="1h")
signals = strategy.generate_weighted_signals(analysis)

# Key outputs:
signals['overall_signal']   # -1.0 to +1.0 (final signal strength)
signals['confidence']       # 0.0 to 1.0 (confidence level)
signals['final_action']     # 'BUY', 'SELL', or 'HOLD'
signals['reason']           # Detailed explanation
signals['regime']           # Market regime type
signals['volatility_level'] # Volatility classification

# Individual indicator signals:
signals['macd_signal']      # -1.0 to +1.0
signals['ma_signal']        # -1.0 to +1.0
signals['rsi_signal']       # -1.0 to +1.0
signals['bb_signal']        # -1.0 to +1.0
signals['volume_signal']    # -1.0 to +1.0

# Individual indicator strengths:
signals['macd_strength']    # 0.0 to 1.0
signals['ma_strength']      # 0.0 to 1.0
# ... etc.
```

### Signal Weights (Default)
```python
{
    'macd': 0.35,    # 35% weight (highest)
    'ma': 0.25,      # 25% weight
    'rsi': 0.20,     # 20% weight
    'bb': 0.10,      # 10% weight
    'volume': 0.10   # 10% weight
}
# Total: 1.00 (100%)
```

### Custom Weights (Regime-Based)
```python
# For trending markets:
trending_weights = {
    'macd': 0.40,
    'ma': 0.30,
    'rsi': 0.15,
    'bb': 0.05,
    'volume': 0.10
}

# For ranging markets:
ranging_weights = {
    'macd': 0.15,
    'ma': 0.15,
    'rsi': 0.35,
    'bb': 0.25,
    'volume': 0.10
}

# Use custom weights:
signals = strategy.generate_weighted_signals(analysis, weights_override=trending_weights)
```

---

## Risk Management Functions

### 1. ATR-Based Position Sizing
```python
from strategy import calculate_position_size_by_atr

position_size = calculate_position_size_by_atr(
    account_balance=1000000,    # Account balance in KRW
    risk_percent=1.0,           # Risk 1% of account
    entry_price=50000000,       # BTC price in KRW
    atr=1000000,                # Current ATR value
    atr_multiplier=2.0          # Stop at 2× ATR
)

# Returns: Position size in BTC (e.g., 0.005 BTC)
```

**Example Calculation**:
```
Account: 1,000,000 KRW
Risk: 1% = 10,000 KRW max loss
Entry: 50,000,000 KRW
ATR: 1,000,000 KRW
Stop Distance: 1,000,000 × 2.0 = 2,000,000 KRW

Position Size: 10,000 / 2,000,000 = 0.005 BTC
Position Value: 0.005 × 50,000,000 = 250,000 KRW
```

---

### 2. Dynamic Stop-Loss
```python
from strategy import calculate_dynamic_stop_loss

stop_loss = calculate_dynamic_stop_loss(
    entry_price=50000000,
    atr=1000000,
    direction='LONG',    # or 'SHORT'
    multiplier=2.0
)

# Returns: Stop loss price in KRW
# Example: 48,000,000 KRW (entry - 2×ATR)
```

---

### 3. Multi-Level Exit Strategy
```python
from strategy import calculate_exit_levels

exits = calculate_exit_levels(
    entry_price=50000000,
    atr=1000000,
    direction='LONG',
    volatility_level='normal'  # 'low', 'normal', or 'high'
)

# Returns:
exits['stop_loss']        # e.g., 48,000,000 KRW
exits['take_profit_1']    # e.g., 52,500,000 KRW (50% exit)
exits['take_profit_2']    # e.g., 54,000,000 KRW (100% exit)
exits['rr_ratio_1']       # e.g., 1.25 (Risk:Reward)
exits['rr_ratio_2']       # e.g., 2.00 (Risk:Reward)
exits['risk_amount']      # Risk in KRW
exits['reward_1']         # Potential profit at TP1
exits['reward_2']         # Potential profit at TP2
```

**Exit Level Multipliers by Volatility**:
| Volatility | Stop | TP1 | TP2 | RR Ratio |
|------------|------|-----|-----|----------|
| Low        | 1.5× | 2.0× | 3.5× | 1:1.33 / 1:2.33 |
| Normal     | 2.0× | 2.5× | 4.0× | 1:1.25 / 1:2.00 |
| High       | 2.5× | 3.0× | 5.0× | 1:1.20 / 1:2.00 |

---

## Interval Presets

### Available Intervals
```python
intervals = ['30m', '1h', '6h', '12h', '24h']
default = '1h'  # ← DEFAULT INTERVAL
```

### 30-Minute Preset (NEW)
```python
config.STRATEGY_CONFIG['interval_presets']['30m'] = {
    'short_ma_window': 20,      # 10 hours
    'long_ma_window': 50,       # 25 hours
    'rsi_period': 9,            # 4.5 hours (faster)
    'macd_fast': 8,             # 4 hours
    'macd_slow': 17,            # 8.5 hours
    'macd_signal': 9,           # 4.5 hours
    'atr_period': 14,           # 7 hours
    'bb_std': 2.5,              # Higher for crypto
    # ... more parameters
}
```

### 1-Hour Preset (DEFAULT)
```python
config.STRATEGY_CONFIG['interval_presets']['1h'] = {
    'short_ma_window': 20,      # 20 hours
    'long_ma_window': 50,       # 50 hours (~2 days)
    'rsi_period': 14,           # 14 hours
    'macd_fast': 8,             # 8 hours
    'macd_slow': 17,            # 17 hours
    'macd_signal': 9,           # 9 hours
    'atr_period': 14,           # 14 hours
    'bb_std': 2.0,              # Standard
    # ... more parameters
}
```

---

## GUI Integration Data

### Indicator Panel Data
```python
analysis = strategy.analyze_market_data("BTC", interval="1h")

# Display these values:
indicators = {
    'Price': analysis['current_price'],
    'MA (20/50)': f"{analysis['short_ma']:,.0f} / {analysis['long_ma']:,.0f}",
    'RSI': f"{analysis['rsi']:.1f}",
    'MACD': f"{analysis['macd_histogram']:,.0f}",
    'ATR%': f"{analysis['atr_percent']:.2f}%",
    'Stoch': f"{analysis['stoch_k']:.1f} / {analysis['stoch_d']:.1f}",
    'ADX': f"{analysis['adx']:.1f}",
    'BB Position': f"{analysis['bb_position']:.1%}",
    'Volume Ratio': f"{analysis['volume_ratio']:.2f}x"
}
```

### Market Regime Panel
```python
regime = analysis['regime']

# Display:
regime_display = {
    'Regime': regime['regime'],                    # trending/ranging/transitional
    'Trend Strength': regime['trend_strength'],    # 0.0 - 1.0 (progress bar)
    'Volatility': regime['volatility_level'],      # low/normal/high (color coded)
    'Recommendation': regime['recommendation'],     # TREND_FOLLOW / MEAN_REVERSION
    'ADX': regime['current_adx'],                  # Numeric value
    'ATR%': regime['current_atr_pct']              # Percentage
}

# Color coding:
colors = {
    'trending': 'green',
    'ranging': 'blue',
    'transitional': 'yellow',
    'low': 'green',
    'normal': 'blue',
    'high': 'red'
}
```

### Signal Strength Panel
```python
signals = strategy.generate_weighted_signals(analysis)

# Overall signal (progress bar: -1.0 to +1.0)
overall_signal = signals['overall_signal']
confidence = signals['confidence']

# Individual signals (mini progress bars)
signal_breakdown = {
    'MACD': (signals['macd_signal'], signals['macd_strength']),
    'MA': (signals['ma_signal'], signals['ma_strength']),
    'RSI': (signals['rsi_signal'], signals['rsi_strength']),
    'BB': (signals['bb_signal'], signals['bb_strength']),
    'Volume': (signals['volume_signal'], signals['volume_strength'])
}

# Final action (large button/label)
action = signals['final_action']  # 'BUY', 'SELL', 'HOLD'
reason = signals['reason']        # Explanation text

# Action colors:
action_colors = {
    'BUY': 'green',
    'SELL': 'red',
    'HOLD': 'gray'
}
```

### Risk Calculator Panel
```python
# User inputs:
account_balance = 1000000  # from user or API
risk_percent = 1.0         # from user setting
entry_price = analysis['current_price']
atr = analysis['atr']
volatility = analysis['regime']['volatility_level']

# Calculate:
position_size = calculate_position_size_by_atr(
    account_balance, risk_percent, entry_price, atr
)

exits = calculate_exit_levels(entry_price, atr, 'LONG', volatility)

# Display:
risk_display = {
    'Position Size': f"{position_size:.6f} BTC",
    'Position Value': f"{position_size * entry_price:,.0f} KRW",
    'Risk Amount': f"{exits['risk_amount']:,.0f} KRW",
    'Risk %': f"{risk_percent}%",
    'Entry': f"{entry_price:,.0f} KRW",
    'Stop Loss': f"{exits['stop_loss']:,.0f} KRW (-{((entry_price - exits['stop_loss']) / entry_price * 100):.2f}%)",
    'Take Profit 1': f"{exits['take_profit_1']:,.0f} KRW (+{((exits['take_profit_1'] - entry_price) / entry_price * 100):.2f}%)",
    'Take Profit 2': f"{exits['take_profit_2']:,.0f} KRW (+{((exits['take_profit_2'] - entry_price) / entry_price * 100):.2f}%)",
    'RR Ratio': f"1:{exits['rr_ratio_2']:.2f}"
}
```

---

## Common Patterns

### Pattern 1: Full Elite Analysis
```python
from strategy import TradingStrategy

strategy = TradingStrategy()

# 1. Analyze market with all indicators
analysis = strategy.analyze_market_data("BTC", interval="1h")

# 2. Generate weighted signals
signals = strategy.generate_weighted_signals(analysis)

# 3. Check regime and adjust if needed
regime = analysis['regime']
if regime['recommendation'] == 'WAIT':
    print("Market unclear - waiting for better setup")
    return

# 4. Calculate risk parameters
from strategy import calculate_position_size_by_atr, calculate_exit_levels

position_size = calculate_position_size_by_atr(
    account_balance=1000000,
    risk_percent=1.0,
    entry_price=analysis['current_price'],
    atr=analysis['atr']
)

exits = calculate_exit_levels(
    entry_price=analysis['current_price'],
    atr=analysis['atr'],
    direction='LONG',
    volatility_level=regime['volatility_level']
)

# 5. Make decision
if signals['final_action'] == 'BUY' and exits['rr_ratio_2'] >= 2.0:
    print(f"BUY {position_size:.6f} BTC")
    print(f"Stop: {exits['stop_loss']:,.0f}")
    print(f"Target 1: {exits['take_profit_1']:,.0f}")
    print(f"Target 2: {exits['take_profit_2']:,.0f}")
```

### Pattern 2: Regime-Adaptive Strategy
```python
analysis = strategy.analyze_market_data("BTC", interval="1h")
regime = analysis['regime']

# Adjust strategy based on regime
if regime['regime'] == 'trending':
    # Use trend-following weights
    weights = {'macd': 0.40, 'ma': 0.30, 'rsi': 0.15, 'bb': 0.05, 'volume': 0.10}
elif regime['regime'] == 'ranging':
    # Use mean-reversion weights
    weights = {'macd': 0.15, 'ma': 0.15, 'rsi': 0.35, 'bb': 0.25, 'volume': 0.10}
else:
    # Transitional - use defaults
    weights = None

signals = strategy.generate_weighted_signals(analysis, weights_override=weights)
```

### Pattern 3: Multi-Timeframe Confirmation
```python
# Analyze multiple timeframes
analysis_1h = strategy.analyze_market_data("BTC", interval="1h")
analysis_6h = strategy.analyze_market_data("BTC", interval="6h")

signals_1h = strategy.generate_weighted_signals(analysis_1h)
signals_6h = strategy.generate_weighted_signals(analysis_6h)

# Only trade if both timeframes agree
if (signals_1h['final_action'] == 'BUY' and
    signals_6h['final_action'] == 'BUY' and
    signals_1h['confidence'] > 0.6 and
    signals_6h['confidence'] > 0.6):
    print("Strong BUY - both timeframes aligned")
```

---

## Configuration Quick Access

### Get Current Config
```python
import config

# Default interval
default_interval = config.STRATEGY_CONFIG['candlestick_interval']  # '1h'

# MACD parameters
macd_fast = config.STRATEGY_CONFIG['macd_fast']   # 8
macd_slow = config.STRATEGY_CONFIG['macd_slow']   # 17
macd_signal = config.STRATEGY_CONFIG['macd_signal']  # 9

# ATR parameters
atr_period = config.STRATEGY_CONFIG['atr_period']  # 14
atr_mult = config.STRATEGY_CONFIG['atr_stop_multiplier']  # 2.0

# Signal weights
weights = config.STRATEGY_CONFIG['signal_weights']

# Risk management
max_daily_loss = config.STRATEGY_CONFIG['max_daily_loss_pct']  # 3.0%
max_trades = config.STRATEGY_CONFIG['max_daily_trades']  # 5
```

### Get Interval Preset
```python
# Get 1h preset
preset_1h = config.STRATEGY_CONFIG['interval_presets']['1h']

# Get 30m preset
preset_30m = config.STRATEGY_CONFIG['interval_presets']['30m']

# Access specific parameter
rsi_period = preset_1h['rsi_period']  # 14
bb_std = preset_30m['bb_std']  # 2.5
```

---

## Troubleshooting

### Issue: "Module not found" errors
**Solution**: Activate virtual environment
```bash
cd 005_money
source .venv/bin/activate
```

### Issue: NaN values in indicators
**Solution**: Check data length
```python
# Ensure sufficient data
analysis_period = config.STRATEGY_CONFIG['analysis_period']  # 100
if len(price_data) < analysis_period:
    print("Insufficient data")
    return None
```

### Issue: Signals too sensitive
**Solution**: Increase thresholds
```python
# In config.py:
'confidence_threshold': 0.7,  # Increase from 0.6
'signal_threshold': 0.6,      # Increase from 0.5
```

### Issue: Too many false signals
**Solution**: Use regime filtering
```python
signals = strategy.generate_weighted_signals(analysis)
regime = analysis['regime']

if regime['recommendation'] in ['REDUCE_SIZE', 'WAIT']:
    return 'HOLD'  # Skip unclear markets

if regime['volatility_level'] == 'high':
    # Reduce position size or skip
    return 'HOLD'
```

---

## Performance Tips

### 1. Cache Analysis Results
```python
# Don't recalculate on every call
analysis = strategy.analyze_market_data("BTC", interval="1h")
# Reuse 'analysis' for multiple signal calculations
```

### 2. Batch Indicator Calculation
```python
# analyze_market_data() calculates ALL indicators at once
# More efficient than calling each indicator function separately
```

### 3. Use Appropriate Intervals
```python
# For quick scanning: 30m or 1h
# For position trading: 6h or 24h
# Match check frequency to interval
```

---

## Quick Reference: Signal Interpretation

### Overall Signal Values
| Range | Meaning | Action |
|-------|---------|--------|
| +0.7 to +1.0 | Very Strong Buy | Consider large position |
| +0.5 to +0.7 | Strong Buy | Standard position |
| +0.3 to +0.5 | Moderate Buy | Small position or wait |
| -0.3 to +0.3 | Neutral | HOLD |
| -0.5 to -0.3 | Moderate Sell | Reduce position |
| -0.7 to -0.5 | Strong Sell | Exit position |
| -1.0 to -0.7 | Very Strong Sell | Exit all |

### Confidence Values
| Range | Meaning | Action |
|-------|---------|--------|
| 0.8 - 1.0 | Very High | High conviction trade |
| 0.6 - 0.8 | High | Standard trade |
| 0.4 - 0.6 | Medium | Cautious trade |
| 0.0 - 0.4 | Low | Skip trade |

### Combined Decision Matrix
| Overall Signal | Confidence | Action |
|---------------|-----------|---------|
| > +0.5 | > 0.6 | **BUY** |
| < -0.5 | > 0.6 | **SELL** |
| Any | < 0.6 | **HOLD** |
| -0.5 to +0.5 | Any | **HOLD** |

---

## Additional Resources

- **Full Implementation Details**: `ELITE_STRATEGY_IMPLEMENTATION_SUMMARY.md`
- **Original Analysis**: `trade_rule/ELITE_30M_TRADING_STRATEGY_ANALYSIS.md`
- **Configuration File**: `config.py`
- **Strategy Implementation**: `strategy.py`

---

**Last Updated**: 2025-10-01
**Version**: 1.0 (Elite Strategy Implementation)
