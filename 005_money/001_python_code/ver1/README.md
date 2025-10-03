# Version 1: Elite 8-Indicator Trading Strategy

## Overview

The Elite 8-Indicator Strategy is an advanced cryptocurrency trading system that combines eight technical indicators using a weighted signal combination approach with market regime detection.

## Technical Indicators

### Core Indicators (4)
1. **Moving Averages (MA)** - Trend identification
   - Short MA (default: 20 periods)
   - Long MA (default: 50 periods)

2. **RSI (Relative Strength Index)** - Overbought/oversold conditions
   - Period: 14
   - Overbought threshold: 70
   - Oversold threshold: 30

3. **Bollinger Bands** - Volatility and mean reversion
   - Period: 20
   - Standard deviation: 2.0

4. **Volume** - Confirmation of price movements
   - Volume ratio window: 20 periods

### Elite Indicators (4)
5. **MACD (Moving Average Convergence Divergence)** - Momentum
   - Fast EMA: 8
   - Slow EMA: 17
   - Signal EMA: 9

6. **ATR (Average True Range)** - Volatility measurement
   - Period: 14
   - Used for dynamic stop-loss and position sizing

7. **Stochastic Oscillator** - Price momentum
   - %K period: 14
   - %D period: 3

8. **ADX (Average Directional Index)** - Trend strength
   - Period: 14
   - Trending threshold: >25
   - Ranging threshold: <15

## Signal Weighting System

The strategy uses a weighted signal combination (sum = 1.0):

- MACD: 35% (highest weight - primary trend indicator)
- MA: 25% (trend confirmation)
- RSI: 20% (momentum filter)
- Bollinger Bands: 10% (mean reversion)
- Volume: 10% (confirmation)

Each indicator generates a gradual signal from -1.0 (strong sell) to +1.0 (strong buy), and these are combined using the weights to produce a final weighted signal.

## Market Regime Detection

The strategy automatically detects three market regimes:

1. **Trending Market** (ADX > 25)
   - Follow trend indicators (MACD, MA)
   - Reduce mean-reversion signals (BB)

2. **Ranging Market** (ADX < 15)
   - Emphasize oscillators (RSI, Stochastic)
   - Use Bollinger Bands for mean reversion

3. **Transitional Market** (15 ≤ ADX ≤ 25)
   - Balanced approach
   - Wait for clear signals

## Risk Management

### ATR-Based Features
- **Dynamic Stop-Loss**: Entry price - (ATR × 2.0)
- **Chandelier Exit**: Trailing stop using ATR × 3.0
- **Position Sizing**: Adjusts based on volatility

### Risk Limits
- Max daily loss: 3.0%
- Max consecutive losses: 3
- Max daily trades: 5
- Position risk: 1.0% of account per trade

## Advanced Features

### Candlestick Pattern Recognition
- Detects bullish/bearish engulfing patterns
- Hammer and shooting star patterns
- Optional (default weight: 0.0)

### Divergence Detection
- Identifies price-RSI divergences
- Lookback period: 30 candles
- Adds confidence boost when detected

### Bollinger Band Squeeze
- Detects low volatility periods
- Predicts potential breakouts
- Threshold: 80% of historical average

## Supported Timeframes

The strategy is optimized for multiple timeframes with preset parameters:

- **30m** - Short-term swing trading
- **1h** - Medium-term trading (default)
- **6h** - Medium-term trading
- **12h** - Medium-long term trading
- **24h** - Long-term trading

Each timeframe has optimized indicator periods for best performance.

## Usage

### Direct Import
```python
from ver1 import get_version_instance

# Create strategy instance
strategy = get_version_instance()

# Analyze market
result = strategy.analyze_market(symbol="BTC", interval="1h")
print(f"Signal: {result['signal']:.2f}, Confidence: {result['confidence']:.2f}")
```

### Via Version Loader
```python
from lib.core.version_loader import load_version

# Load ver1
strategy = load_version("ver1")

# Analyze
result = strategy.analyze_market("ETH", "1h")
```

### Command Line
```bash
# CLI mode
python main.py --version ver1 --interval 1h --coin BTC

# GUI mode
python gui_app.py --version ver1
```

## Configuration

### Indicator Parameters
All indicator parameters can be customized in `config_v1.py`:
- Window sizes for MA, RSI, Bollinger Bands
- MACD periods (fast, slow, signal)
- ATR multipliers for stop-loss
- Stochastic periods
- ADX thresholds

### Signal Weights
Adjust weights in `SIGNAL_WEIGHTS` dict in `config_v1.py`:
```python
SIGNAL_WEIGHTS = {
    'macd': 0.35,   # Increase for more trend-following
    'ma': 0.25,
    'rsi': 0.20,    # Increase for more oscillation sensitivity
    'bb': 0.10,
    'volume': 0.10,
}
```

## Version Information

- **Name**: ver1
- **Display Name**: Elite 8-Indicator Strategy
- **Author**: Trading Bot Team
- **Date**: 2025-10
- **Status**: Production Ready

## Performance Characteristics

### Strengths
- Robust in trending markets (high ADX)
- Good risk management with ATR-based stops
- Multi-timeframe adaptability
- Comprehensive signal confirmation

### Limitations
- May lag in fast-reversing markets
- Requires sufficient historical data (>50 candles)
- Performance depends on proper weight tuning
- Higher computational cost due to 8 indicators

## Future Enhancements

Potential improvements for Version 2:
- Machine learning for dynamic weight adjustment
- Multi-asset correlation analysis
- Advanced order types (trailing stop, OCO)
- Backtesting integration with performance metrics
- Real-time parameter optimization
