# Developer Onboarding Guide

**Project**: Bithumb Cryptocurrency Trading Bot
**Version**: 2.0 (Elite Strategy)
**Last Updated**: 2025-10-02
**Welcome aboard!**

---

## Welcome to the Project

This guide will help you get up and running as a contributor to the Bithumb Trading Bot project. By the end of this document, you'll understand the codebase structure, development workflow, and how to make your first contribution.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Project Overview](#project-overview)
4. [Codebase Tour](#codebase-tour)
5. [Development Workflow](#development-workflow)
6. [Testing Strategy](#testing-strategy)
7. [Common Development Tasks](#common-development-tasks)
8. [Code Style Guide](#code-style-guide)
9. [Debugging Tips](#debugging-tips)
10. [Contributing Guidelines](#contributing-guidelines)

---

## Prerequisites

### Required Knowledge
- **Python 3.7+**: Strong proficiency
- **Pandas/NumPy**: Data manipulation and numerical computing
- **Git**: Version control basics
- **REST APIs**: HTTP requests and JSON
- **Trading Basics**: Understanding of technical indicators (MA, RSI, MACD, etc.)

### Nice to Have
- **Tkinter**: For GUI development
- **Matplotlib**: For chart visualization
- **Cryptocurrency Trading**: Experience with exchanges
- **Financial Markets**: Technical analysis knowledge

### Required Software
- **Python**: 3.7 or higher
- **Git**: Latest version
- **Code Editor**: VS Code, PyCharm, or similar
- **Terminal**: Bash (macOS/Linux) or PowerShell (Windows)

---

## Environment Setup

### Step 1: Clone the Repository

```bash
cd ~/project/git/violet_sw
# Repository should already be cloned at this location
cd 005_money
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate  # macOS/Linux
# OR
.venv\Scripts\activate     # Windows
```

**Verify activation**:
```bash
which python
# Should show: /path/to/005_money/.venv/bin/python
```

### Step 3: Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**Required packages**:
- `pandas`: Data manipulation
- `numpy`: Numerical operations
- `matplotlib`: Chart plotting
- `requests`: API calls
- `schedule`: Task scheduling
- `tkinter`: GUI (usually pre-installed with Python)

**Verify installation**:
```bash
python -c "import pandas, numpy, matplotlib, requests, schedule; print('All dependencies installed')"
```

### Step 4: Configure API Keys (Optional for Development)

```bash
# Copy example file
cp .env.example .env

# Edit .env file (optional - not needed for most development)
# BITHUMB_CONNECT_KEY=your_key_here
# BITHUMB_SECRET_KEY=your_secret_here
```

**Note**: Most development can be done without real API keys using dry-run mode.

### Step 5: Run Initial Tests

```bash
# Test CLI bot (dry-run mode)
python main.py --dry-run

# Test GUI (if you see the window, it works!)
python gui_app.py
```

### Step 6: IDE Setup (VS Code Example)

**Install Extensions**:
- Python (Microsoft)
- Pylance (Microsoft)
- Python Docstring Generator
- GitLens

**VS Code Settings** (`.vscode/settings.json`):
```json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.pylintEnabled": true,
    "python.formatting.provider": "black",
    "editor.formatOnSave": true,
    "python.testing.pytestEnabled": true
}
```

---

## Project Overview

### Architecture at a Glance

```
User Interface Layer
  ├─ GUI (gui_app.py)
  └─ CLI (main.py)
       ↓
Application Layer
  ├─ TradingBot (trading_bot.py)
  └─ GUITradingBot (gui_trading_bot.py)
       ↓
Business Logic Layer
  ├─ Strategy (strategy.py) - 8 indicators
  ├─ Config (config.py, config_manager.py)
  └─ Portfolio (portfolio_manager.py)
       ↓
Infrastructure Layer
  ├─ API (bithumb_api.py)
  └─ Logging (logger.py)
```

### Key Concepts

**1. Weighted Signal System**:
- Each indicator returns a value from -1.0 (strong sell) to +1.0 (strong buy)
- Signals are multiplied by configurable weights
- Final decision based on combined signal strength and confidence

**2. Market Regime Detection**:
- ADX indicator classifies markets as Trending/Ranging/Transitional
- Strategy can adapt weights based on detected regime

**3. ATR-Based Risk Management**:
- Stop-loss and take-profit levels calculated dynamically
- Position sizing adjusted based on volatility

**4. Dry-Run Mode**:
- All trading logic works without real money
- Essential for testing and development

---

## Codebase Tour

Let's walk through the most important files you'll work with.

### Entry Points

#### `main.py` (CLI Entry Point)
**Purpose**: Headless bot operation with scheduling
**Key Functions**:
- `main()`: Initialize and run bot with schedule
- Command-line argument parsing

**When to Edit**: Adding CLI features, changing scheduling logic

**Quick Look**:
```bash
head -50 main.py
```

#### `gui_app.py` (GUI Entry Point)
**Purpose**: Tkinter graphical interface
**Key Classes**:
- `TradingBotGUI`: Main window controller
- Tab management (Trading, Charts, History, Transactions)

**When to Edit**: GUI layout changes, new UI features

**Lines of Interest**:
- Line 25-60: GUI initialization
- Line 85-100: Tab creation
- Line 500+: Signal update methods

### Core Logic

#### `strategy.py` (Strategy Engine)
**Purpose**: Technical indicator calculations and signal generation
**Key Functions**:
- `analyze_market_data()`: Master analysis function
- `generate_weighted_signals()`: Signal combination
- `calculate_*()`: Individual indicator functions

**When to Edit**: Adding new indicators, changing signal logic

**Important Sections**:
```python
# Line 1-100: Individual indicator functions
# Line 200-400: analyze_market_data() implementation
# Line 450-600: generate_weighted_signals()
# Line 650+: Market regime detection
```

**Exercise**: Add a new indicator
```python
def calculate_new_indicator(df: pd.DataFrame, period: int) -> pd.Series:
    """
    Your new indicator calculation
    """
    # TODO: Implement your indicator
    return pd.Series()
```

#### `trading_bot.py` (Trading Orchestrator)
**Purpose**: Coordinate analysis, decision-making, and execution
**Key Methods**:
- `execute_trading_cycle()`: Main trading loop
- `buy_coin()`, `sell_coin()`: Trade execution
- Safety checks and risk management

**When to Edit**: Changing trading logic, adding safety features

**Critical Code**:
```python
# Line 100-200: execute_trading_cycle()
# Line 250-300: buy_coin()
# Line 300-350: sell_coin()
```

### Configuration

#### `config.py` (Central Configuration)
**Purpose**: All configurable parameters (150+ settings)
**Key Sections**:
- `TRADING_CONFIG`: Trade amounts, fees
- `STRATEGY_CONFIG`: Indicator parameters, signal weights
- `SAFETY_CONFIG`: Risk limits, dry-run mode

**When to Edit**: Changing defaults, adding new parameters

**Most Edited Lines**:
```python
# Line 34: 'candlestick_interval' (default timeframe)
# Line 76-83: 'signal_weights' (indicator weights)
# Line 96-177: 'interval_presets' (timeframe optimization)
```

#### `config_manager.py` (Runtime Config Updates)
**Purpose**: Change settings without restarting bot
**Key Methods**:
- `update_strategy_param()`
- `apply_interval_preset()`
- `update_signal_weights()`

**When to Edit**: Adding new runtime configuration options

### Visualization

#### `chart_widget.py` (Chart Component)
**Purpose**: Real-time candlestick chart with indicators
**Key Methods**:
- `update_chart()`: Fetch data and redraw
- `create_indicator_checkboxes()`: User controls
- `plot_candlesticks()`: Chart rendering

**When to Edit**: Adding new chart indicators, changing layout

**Important**: This is v3.0 (rebuilt 2025-10), uses pure matplotlib

**Lines to Know**:
```python
# Line 38-52: ChartWidget class init
# Line 80-120: Indicator checkbox creation
# Line 200-400: Chart plotting logic
```

### Utilities

#### `bithumb_api.py` (API Wrapper)
**Purpose**: Bithumb REST API calls
**Functions**:
- `get_ticker()`: Current price
- `get_candlestick()`: OHLCV data
- `get_orderbook()`: Bid/ask data

**When to Edit**: Adding new API endpoints, changing data format

**Note**: Private API endpoints (balance, trading) intentionally not used for security

#### `logger.py` (Logging System)
**Purpose**: Multi-channel logging and transaction tracking
**Classes**:
- `TradingLogger`: General logging
- `TransactionHistory`: Trade record keeping

**When to Edit**: Adding new log channels, changing log format

---

## Development Workflow

### Workflow Overview

```
1. Create feature branch
        ↓
2. Write code + tests
        ↓
3. Test locally (dry-run)
        ↓
4. Run linters/formatters
        ↓
5. Commit with clear message
        ↓
6. Push and create PR
        ↓
7. Code review
        ↓
8. Merge to main
```

### Step-by-Step: Adding a New Feature

#### Example: Add EMA (Exponential Moving Average) Indicator

**Step 1: Create Feature Branch**
```bash
git checkout -b feature/add-ema-indicator
```

**Step 2: Implement Indicator Function** (`strategy.py`)
```python
def calculate_ema(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Calculate Exponential Moving Average

    Args:
        df: OHLCV DataFrame with 'close' column
        window: EMA period

    Returns:
        EMA series
    """
    return df['close'].ewm(span=window, adjust=False).mean()
```

**Step 3: Integrate into Analysis** (`strategy.py` - `analyze_market_data()`)
```python
# Add to analyze_market_data() method
def analyze_market_data(self, ticker, interval='1h'):
    # ... existing code ...

    # Add EMA calculation
    ema_20 = calculate_ema(df, self.config['ema_window'])
    indicators['ema'] = ema_20
    current_values['ema'] = float(ema_20.iloc[-1])

    # ... rest of code ...
```

**Step 4: Add Signal Generation** (`strategy.py` - `generate_weighted_signals()`)
```python
def generate_weighted_signals(analysis):
    # ... existing code ...

    # EMA signal (compare to price)
    ema_signal = 0.0
    if current_price > current_values['ema']:
        ema_signal = 1.0  # Price above EMA = bullish
    elif current_price < current_values['ema']:
        ema_signal = -1.0  # Price below EMA = bearish

    individual_signals['ema'] = ema_signal

    # ... rest of code ...
```

**Step 5: Add Configuration** (`config.py`)
```python
STRATEGY_CONFIG = {
    # ... existing config ...
    'ema_window': 20,  # New parameter

    'signal_weights': {
        'macd': 0.30,   # Reduced
        'ma': 0.20,     # Reduced
        'rsi': 0.20,
        'bb': 0.10,
        'volume': 0.10,
        'ema': 0.10     # New weight
    }
}
```

**Step 6: Add to GUI** (`gui_app.py`)
```python
# Add EMA checkbox to indicator panel
self.ema_var = tk.BooleanVar(value=True)
ttk.Checkbutton(
    indicator_frame,
    text="EMA",
    variable=self.ema_var
).pack(side=tk.LEFT)

# Add EMA display to signal panel
self.ema_label = ttk.Label(signal_frame, text="EMA: --")
self.ema_label.pack()
```

**Step 7: Add to Chart** (`chart_widget.py`)
```python
def plot_indicators(self, df, analysis):
    # ... existing code ...

    # Plot EMA if enabled
    if self.indicator_checkboxes['ema'].get():
        ema = analysis['indicators']['ema']
        ax.plot(df.index, ema, label='EMA(20)', color='green', linewidth=1.5)
```

**Step 8: Test**
```bash
# Run bot in dry-run
python main.py --dry-run

# Open GUI to verify
python gui_app.py
```

**Step 9: Commit**
```bash
git add strategy.py config.py gui_app.py chart_widget.py
git commit -m "Add EMA indicator to elite strategy

- Implement calculate_ema() function
- Add EMA signal generation (price vs EMA)
- Add EMA weight (0.10) to signal_weights
- Add EMA checkbox to GUI
- Add EMA line to chart
- Tested in dry-run mode"
```

**Step 10: Push and PR**
```bash
git push origin feature/add-ema-indicator
# Create pull request on GitHub/GitLab
```

---

## Testing Strategy

### Test Pyramid

```
           /\
          /  \         E2E Tests (GUI, full cycles)
         /____\
        /      \       Integration Tests (bot + API)
       /________\
      /          \     Unit Tests (indicators, utilities)
     /____________\
```

### Unit Testing Example

**Test File**: `test_strategy.py` (you'll need to create this)

```python
import unittest
import pandas as pd
import numpy as np
from strategy import calculate_rsi, calculate_ma, generate_weighted_signals

class TestIndicators(unittest.TestCase):
    def setUp(self):
        """Create sample data for testing"""
        self.df = pd.DataFrame({
            'close': [100, 105, 103, 108, 107, 110, 115, 112, 118, 120],
            'high': [102, 107, 105, 110, 109, 112, 117, 114, 120, 122],
            'low': [98, 103, 101, 106, 105, 108, 113, 110, 116, 118],
            'volume': [1000, 1100, 950, 1200, 1050, 1150, 1300, 1100, 1250, 1400]
        })

    def test_rsi_range(self):
        """RSI should be between 0 and 100"""
        rsi = calculate_rsi(self.df, period=5)
        self.assertTrue((rsi >= 0).all())
        self.assertTrue((rsi <= 100).all())

    def test_rsi_values(self):
        """RSI should be ~60-70 for uptrend"""
        rsi = calculate_rsi(self.df, period=5)
        latest_rsi = rsi.iloc[-1]
        self.assertGreater(latest_rsi, 50)  # Uptrending data

    def test_ma_calculation(self):
        """MA should be average of last N periods"""
        ma = calculate_ma(self.df, window=3)
        # Last 3 values: 118, 120, ? → avg = 119
        expected = (112 + 118 + 120) / 3
        self.assertAlmostEqual(ma.iloc[-1], expected, places=2)

    def test_signal_generation(self):
        """Signals should be in valid range"""
        analysis = {
            'current_values': {
                'ma_short': 120,
                'ma_long': 110,
                'rsi': 65,
                'bb_position': 0.6,
                'macd_histogram': 5.0,
                # ... other values
            }
        }
        signals = generate_weighted_signals(analysis)

        self.assertIn(signals['decision'], ['BUY', 'SELL', 'HOLD'])
        self.assertGreaterEqual(signals['overall_signal'], -1.0)
        self.assertLessEqual(signals['overall_signal'], 1.0)
        self.assertGreaterEqual(signals['confidence'], 0.0)
        self.assertLessEqual(signals['confidence'], 1.0)

if __name__ == '__main__':
    unittest.main()
```

**Run Tests**:
```bash
python -m unittest test_strategy.py
```

### Integration Testing

**Test Full Trading Cycle** (dry-run):
```python
# test_integration.py
from trading_bot import TradingBot
from logger import TradingLogger

def test_full_cycle():
    logger = TradingLogger()
    bot = TradingBot(logger=logger, dry_run=True)

    # Execute one cycle
    result = bot.execute_trading_cycle('BTC', '1h')

    # Assertions
    assert 'decision' in result
    assert result['decision'] in ['BUY', 'SELL', 'HOLD']
    assert 'signals' in result
    assert result['signals']['confidence'] >= 0.0

    print("✓ Integration test passed")

if __name__ == '__main__':
    test_full_cycle()
```

### Manual Testing Checklist

Before submitting a PR, test:

- [ ] CLI bot runs without errors (dry-run)
- [ ] GUI launches and displays data
- [ ] Chart refreshes correctly
- [ ] Indicator checkboxes toggle indicators
- [ ] Configuration changes apply
- [ ] Logs are written correctly
- [ ] No API errors (check logs)
- [ ] Bot stops gracefully (Ctrl+C or Stop button)

---

## Common Development Tasks

### Task 1: Change Default Interval from 1h to 6h

**File**: `config.py`
```python
STRATEGY_CONFIG = {
    'candlestick_interval': '6h',  # Changed from '1h'
    # ...
}

SCHEDULE_CONFIG = {
    'check_interval_minutes': 60,  # Changed from 15
    # ...
}
```

**Test**:
```bash
python main.py --dry-run
# Check logs: Should see "Interval: 6h"
```

### Task 2: Adjust Signal Weights (Increase MACD Emphasis)

**File**: `config.py`
```python
'signal_weights': {
    'macd': 0.45,       # Increased from 0.35
    'ma': 0.20,         # Reduced from 0.25
    'rsi': 0.20,
    'bb': 0.10,
    'volume': 0.05      # Reduced from 0.10
}
```

**Test**:
```bash
python main.py --dry-run
# Check decision log: MACD should have more influence
```

### Task 3: Add New Strategy Preset

**File**: `config.py`
```python
# Add to GUI presets (in gui_app.py)
STRATEGY_PRESETS = {
    # ... existing presets ...

    'Scalping': {
        'name': 'Scalping (High Frequency)',
        'weights': {
            'macd': 0.40,
            'rsi': 0.30,
            'volume': 0.20,  # High volume importance
            'ma': 0.05,
            'bb': 0.05
        },
        'confidence_threshold': 0.5,  # Lower for more signals
        'description': 'Fast trading with high volume confirmation'
    }
}
```

**File**: `gui_app.py`
```python
# Add to dropdown
self.strategy_selector.config(values=[
    'Balanced Elite',
    'Trend Following',
    'Mean Reversion',
    'MACD + RSI Filter',
    'Scalping',  # New option
    'Custom'
])
```

### Task 4: Add Email Alerts on Signals

**New File**: `alert_manager.py`
```python
import smtplib
from email.mime.text import MIMEText

class AlertManager:
    def __init__(self, smtp_config):
        self.smtp_config = smtp_config

    def send_alert(self, subject: str, message: str):
        """Send email alert"""
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = self.smtp_config['from']
        msg['To'] = self.smtp_config['to']

        with smtplib.SMTP(self.smtp_config['server'], self.smtp_config['port']) as server:
            server.starttls()
            server.login(self.smtp_config['user'], self.smtp_config['password'])
            server.send_message(msg)

    def alert_on_signal(self, decision: str, confidence: float, price: float):
        """Send alert when strong signal detected"""
        if confidence >= 0.75:
            subject = f"Trading Bot: {decision} Signal"
            message = f"""
            Strong {decision} signal detected!

            Confidence: {confidence:.1%}
            Current Price: {price:,.0f} KRW

            Review bot status and consider taking action.
            """
            self.send_alert(subject, message)
```

**Integrate**: `trading_bot.py`
```python
from alert_manager import AlertManager

class TradingBot:
    def __init__(self, ..., alert_manager=None):
        # ...
        self.alert_manager = alert_manager

    def execute_trading_cycle(self, ...):
        # ... existing code ...

        # Send alert if strong signal
        if self.alert_manager and signals['confidence'] >= 0.75:
            self.alert_manager.alert_on_signal(
                signals['decision'],
                signals['confidence'],
                analysis['current_price']
            )
```

### Task 5: Debug Why Bot Isn't Trading

**Step 1**: Check logs
```bash
tail -50 logs/trading_$(date +%Y%m%d).log
```

**Step 2**: Look for decision logs
```bash
grep "Decision:" logs/trading_*.log | tail -10
```

**Step 3**: Check signal values
```bash
grep "Signal strength" logs/trading_*.log
```

**Common Issues**:
1. **Confidence too low**: Reduce `confidence_threshold` in config
2. **Signal too weak**: Check `signal_threshold`
3. **Daily limit reached**: Check `max_daily_trades`
4. **Emergency stop enabled**: Check `SAFETY_CONFIG['emergency_stop']`
5. **API errors**: Check for "Error" in logs

---

## Code Style Guide

### Python Style (PEP 8)

**Imports**:
```python
# Standard library
import os
import sys
from typing import Dict, List, Any

# Third-party
import pandas as pd
import numpy as np

# Local
from config import STRATEGY_CONFIG
from logger import TradingLogger
```

**Naming Conventions**:
```python
# Functions and variables: snake_case
def calculate_moving_average(df, window):
    total_sum = 0
    # ...

# Classes: PascalCase
class TradingBot:
    pass

# Constants: UPPER_SNAKE_CASE
MAX_DAILY_TRADES = 10
```

**Docstrings**:
```python
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI)

    Args:
        df: OHLCV DataFrame with 'close' column
        period: Lookback period (default: 14)

    Returns:
        RSI series with values from 0 to 100

    Raises:
        ValueError: If period < 2 or df is empty

    Example:
        >>> df = get_candlestick('BTC', '1h')
        >>> rsi = calculate_rsi(df, 14)
        >>> print(rsi.iloc[-1])  # Latest RSI value
        65.42
    """
    # Implementation...
```

**Type Hints**:
```python
from typing import Dict, List, Optional, Tuple

def analyze_market_data(
    self,
    ticker: str,
    interval: str = '1h'
) -> Dict[str, Any]:
    """..."""

def get_transactions(
    self,
    ticker: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """..."""
```

**Error Handling**:
```python
# Good: Specific exceptions, clear messages
try:
    data = get_ticker('BTC')
    price = float(data['closing_price'])
except KeyError as e:
    logger.log_error(f"Missing field in API response: {e}")
    raise ValueError(f"Invalid API response format") from e
except requests.RequestException as e:
    logger.log_error(f"API request failed: {e}")
    # Retry logic...

# Bad: Bare except
try:
    data = get_ticker('BTC')
except:  # Don't do this!
    pass
```

### Configuration Management

**Don't hardcode values**:
```python
# Bad
if rsi < 30:
    signal = -1.0

# Good
if rsi < self.config['rsi_oversold']:
    signal = -1.0
```

### Logging Best Practices

```python
# Bad: Print statements
print(f"Price: {price}")

# Good: Use logger
logger.info(f"Current price: {price:,.0f} KRW")

# Better: Structured logging
logger.log_decision(
    ticker='BTC',
    decision='BUY',
    analysis=analysis,
    signals=signals
)
```

---

## Debugging Tips

### Enable Debug Logging

**File**: `config.py`
```python
LOGGING_CONFIG = {
    'log_level': 'DEBUG',  # Changed from 'INFO'
    # ...
}
```

### Use Python Debugger (pdb)

```python
import pdb

def execute_trading_cycle(self):
    analysis = self.strategy.analyze_market_data('BTC')

    # Drop into debugger
    pdb.set_trace()

    signals = self.strategy.generate_weighted_signals(analysis)
```

**Debugger Commands**:
- `n` (next): Execute next line
- `s` (step): Step into function
- `c` (continue): Continue execution
- `p variable`: Print variable value
- `l` (list): Show current code
- `q` (quit): Exit debugger

### Inspect DataFrame in Analysis

```python
analysis = strategy.analyze_market_data('BTC')

# Check price data
print(analysis['price_data'].tail())

# Check indicators
print(f"RSI: {analysis['current_values']['rsi']:.2f}")
print(f"MACD: {analysis['current_values']['macd_histogram']:.2f}")

# Check for NaN values
if analysis['indicators']['rsi'].isna().any():
    print("WARNING: RSI contains NaN values!")
```

### Common Issues

#### Issue: "KeyError: 'closing_price'"
**Cause**: API response format changed or API error
**Fix**: Add error handling in `bithumb_api.py`
```python
try:
    price = data['closing_price']
except KeyError:
    logger.log_error(f"API response: {data}")
    raise
```

#### Issue: "RuntimeWarning: invalid value encountered in double_scalars"
**Cause**: Division by zero or NaN in indicator calculation
**Fix**: Add NaN checks
```python
rsi = calculate_rsi(df, 14)
if rsi.isna().any():
    rsi = rsi.fillna(50)  # Fill NaN with neutral value
```

#### Issue: Bot not trading despite good signals
**Cause**: Safety limits triggered
**Debug**:
```python
# In execute_trading_cycle()
print(f"Daily trades: {self.daily_trade_count}/{self.max_daily_trades}")
print(f"Consecutive losses: {self.consecutive_losses}/{self.max_consecutive_losses}")
print(f"Confidence: {signals['confidence']:.2f}/{self.confidence_threshold}")
```

---

## Contributing Guidelines

### Branch Naming

```
feature/add-sma-indicator
bugfix/fix-chart-rendering
hotfix/api-error-handling
refactor/simplify-signal-logic
docs/update-architecture
```

### Commit Messages

**Format**:
```
<type>: <short summary>

<detailed description>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring
- `docs`: Documentation changes
- `test`: Test additions/changes
- `style`: Code style changes (formatting, no logic change)
- `chore`: Maintenance tasks

**Examples**:
```
feat: Add EMA indicator to elite strategy

- Implement calculate_ema() with configurable period
- Add EMA signal generation (price vs EMA crossover)
- Integrate into weighted signal system with 0.10 weight
- Add EMA display to GUI and chart widget
- Add tests for EMA calculation

Closes #42
```

```
fix: Chart x-axis compression on 30m interval

The chart was displaying compressed x-axis labels when using
30m interval due to excessive data points. Limited display to
most recent 200 candles and improved label formatting.

Fixes #58
```

### Pull Request Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] New feature
- [ ] Bug fix
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tested in dry-run mode
- [ ] GUI verified
- [ ] Unit tests added/updated
- [ ] Existing tests pass

## Checklist
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No hardcoded values
- [ ] Logging added where appropriate
- [ ] Error handling implemented

## Screenshots (if applicable)
```

### Code Review Checklist

**As Reviewer**:
- [ ] Code is clear and well-commented
- [ ] No hardcoded values (use config)
- [ ] Error handling is appropriate
- [ ] Logging is sufficient
- [ ] Performance impact is acceptable
- [ ] Tests are included
- [ ] Documentation is updated

**As Author**:
- [ ] Self-reviewed code
- [ ] Tested all changes
- [ ] Ran linters/formatters
- [ ] Updated CHANGELOG.md
- [ ] Added tests
- [ ] Updated relevant docs

---

## Next Steps

### Week 1: Get Familiar
- [ ] Read ARCHITECTURE.md thoroughly
- [ ] Run bot in dry-run mode, observe logs
- [ ] Open GUI, explore all tabs
- [ ] Read through strategy.py (main logic)
- [ ] Experiment with changing config values

### Week 2: Small Contributions
- [ ] Fix a simple bug or typo
- [ ] Add documentation improvements
- [ ] Add unit tests for existing functions
- [ ] Improve log messages

### Week 3: Feature Development
- [ ] Add a new indicator
- [ ] Implement a new strategy preset
- [ ] Improve GUI visualization
- [ ] Add alert/notification system

### Advanced Topics
- [ ] Implement backtesting system
- [ ] Add multi-coin support
- [ ] Integrate with other exchanges
- [ ] Build ML-based signal optimization

---

## Resources

### Internal Documentation
- `ARCHITECTURE.md`: System design deep-dive
- `STRATEGY_TUNING_GUIDE.md`: Strategy optimization
- `API_REFERENCE.md`: Complete API documentation
- `CLAUDE.md`: Project-level instructions

### External Resources
- **Bithumb API**: https://apidocs.bithumb.com/
- **Pandas Docs**: https://pandas.pydata.org/docs/
- **Technical Analysis**: Investopedia (RSI, MACD, etc.)
- **Python Testing**: https://docs.python.org/3/library/unittest.html

### Community
- **Discussions**: Use GitHub Discussions for questions
- **Issues**: Report bugs or request features
- **Wiki**: Check wiki for FAQs and tips

---

## Getting Help

**Stuck on something?**

1. **Check documentation** first (you're reading it!)
2. **Search existing issues** on GitHub
3. **Ask in discussions** with context and error logs
4. **Pair program** with another contributor

**When asking for help, include**:
- What you're trying to do
- What you expected to happen
- What actually happened
- Relevant code snippets
- Error messages and logs
- Your environment (Python version, OS, etc.)

---

## Welcome Aboard!

You're now ready to contribute to the Bithumb Trading Bot project. Remember:

- **Ask questions** - no question is too simple
- **Start small** - small PRs are easier to review
- **Read code** - the codebase is your best teacher
- **Test thoroughly** - dry-run mode is your friend
- **Have fun** - you're building something cool!

Happy coding! 🚀

---

**Document Version**: 1.0
**Last Updated**: 2025-10-02
**Maintained By**: Project Lead & Contributors
