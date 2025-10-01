# Technical Architecture Documentation

**Project**: Bithumb Cryptocurrency Trading Bot
**Version**: 2.0 (Elite Strategy)
**Last Updated**: 2025-10-02
**Status**: Production Ready

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Layers](#architecture-layers)
3. [Core Components](#core-components)
4. [Data Flow](#data-flow)
5. [Technology Stack](#technology-stack)
6. [Design Patterns](#design-patterns)
7. [Security Architecture](#security-architecture)
8. [Performance Considerations](#performance-considerations)

---

## System Overview

### Purpose
Automated cryptocurrency trading system that analyzes market data using 8 technical indicators, detects market regimes, and executes trades via Bithumb API with sophisticated risk management.

### Key Features
- **Elite Trading Strategy**: 8-indicator weighted signal system (MA, RSI, MACD, BB, Stochastic, ATR, ADX, Volume)
- **Market Regime Detection**: Trending vs Ranging market classification
- **ATR-Based Risk Management**: Dynamic stop-loss and position sizing
- **Real-time GUI**: Tkinter-based interface with live charts and monitoring
- **Multi-Timeframe Support**: 30m, 1h, 6h, 12h, 24h with optimized parameters
- **Comprehensive Logging**: Multi-channel logging system with transaction history

### Architecture Style
- **Modular Monolith**: Single Python application with well-separated concerns
- **Event-Driven**: Scheduled execution with real-time updates
- **Stateless**: No persistent in-memory state (relies on API and log files)

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                       │
│  ┌──────────────────┐              ┌──────────────────┐    │
│  │   GUI (Tkinter)  │              │   CLI Interface  │    │
│  │  - gui_app.py    │              │   - main.py      │    │
│  │  - chart_widget  │              │   - run.py/sh    │    │
│  └──────────────────┘              └──────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                        │
│  ┌──────────────────┐    ┌──────────────────────────────┐  │
│  │  Trading Bot     │◄───┤  GUI Trading Bot Adapter    │  │
│  │  trading_bot.py  │    │  gui_trading_bot.py          │  │
│  └──────────────────┘    └──────────────────────────────┘  │
│           │                                                 │
│           ├─► Strategy Execution                           │
│           ├─► Trade Execution                              │
│           └─► Risk Management                              │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     BUSINESS LOGIC LAYER                    │
│  ┌──────────────────┐    ┌──────────────────────────────┐  │
│  │  Strategy Engine │    │  Portfolio Manager           │  │
│  │  strategy.py     │    │  portfolio_manager.py        │  │
│  │                  │    │                              │  │
│  │  - 8 Indicators  │    │  - Transaction Tracking      │  │
│  │  - Signal Gen    │    │  - FIFO Profit Calculation   │  │
│  │  - Regime Detect │    │  - Position Management       │  │
│  └──────────────────┘    └──────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Configuration Manager                               │  │
│  │  config.py / config_manager.py                       │  │
│  │  - Strategy Parameters                               │  │
│  │  - Risk Settings                                     │  │
│  │  - Interval Presets                                  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     INFRASTRUCTURE LAYER                    │
│  ┌──────────────────┐    ┌──────────────────────────────┐  │
│  │  Bithumb API     │    │  Logging System              │  │
│  │  bithumb_api.py  │    │  logger.py                   │  │
│  │  pybithumb/      │    │                              │  │
│  │                  │    │  - Trade Log                 │  │
│  │  - Public API    │    │  - Decision Log              │  │
│  │  - Private API   │    │  - Error Log                 │  │
│  │  - Candlestick   │    │  - Transaction History       │  │
│  └──────────────────┘    └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     EXTERNAL SERVICES                       │
│     [Bithumb Exchange API]      [File System]              │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Entry Points

#### `main.py`
**Purpose**: CLI entry point for headless/scheduled bot operation
**Responsibilities**:
- Command-line argument parsing
- Environment initialization
- Scheduled task execution (every 15 minutes default)
- Bot lifecycle management

**Key Functions**:
```python
def main():
    # Initialize configuration
    # Create TradingBot instance
    # Setup scheduling
    # Run infinite loop with exception handling
```

**Execution Flow**:
```
Parse CLI args → Validate config → Initialize bot → Schedule task → Loop
```

#### `gui_app.py`
**Purpose**: GUI entry point with Tkinter interface
**Responsibilities**:
- GUI window management
- User input handling
- Real-time status updates
- Tab-based interface (Trading, Charts, History, Transactions)

**Key Classes**:
- `TradingBotGUI`: Main GUI application controller
- Tab management with ttk.Notebook
- Real-time log streaming via queue

### 2. Trading Core

#### `trading_bot.py`
**Purpose**: Main trading orchestration engine
**Responsibilities**:
- Market data retrieval
- Strategy analysis coordination
- Trade execution decision
- Risk management enforcement

**Key Methods**:
```python
class TradingBot:
    def execute_trading_cycle(self):
        # 1. Fetch market data
        # 2. Analyze with strategy
        # 3. Generate signals
        # 4. Check risk limits
        # 5. Execute trade if conditions met
        # 6. Log results

    def buy_coin(self, ticker, amount_krw):
        # Execute buy order with safety checks

    def sell_coin(self, ticker, amount_krw):
        # Execute sell order with FIFO profit calculation
```

**State Management**:
- Daily trade counter
- Consecutive loss tracking
- Emergency stop flag

#### `gui_trading_bot.py`
**Purpose**: GUI-specific trading bot adapter
**Responsibilities**:
- Wraps TradingBot for GUI integration
- Status update callbacks
- Non-blocking execution
- Enhanced signal reporting

**Key Differences from CLI Bot**:
- Returns elite analysis data for GUI display
- Provides real-time status updates via callbacks
- Includes LED signal states

### 3. Strategy Engine

#### `strategy.py`
**Purpose**: Elite trading strategy implementation
**Responsibilities**:
- Technical indicator calculations (8 indicators)
- Weighted signal generation
- Market regime detection
- Risk management calculations

**Indicator Functions**:
```python
# Classic Indicators
calculate_moving_average(df, window) → pd.Series
calculate_rsi(df, period) → pd.Series
calculate_bollinger_bands(df, window, std) → (upper, ma, lower)
calculate_volume_ratio(df, window) → pd.Series

# Elite Indicators (Added in v2.0)
calculate_macd(df, fast, slow, signal) → (macd, signal, histogram)
calculate_atr(df, period) → pd.Series
calculate_stochastic(df, k_period, d_period) → (K, D)
calculate_adx(df, period) → pd.Series
```

**Signal Generation**:
```python
def generate_weighted_signals(analysis: Dict) → Dict:
    # Returns:
    # {
    #   'overall_signal': -1.0 to +1.0,
    #   'confidence': 0.0 to 1.0,
    #   'individual_signals': {...},
    #   'decision': 'BUY' | 'SELL' | 'HOLD'
    # }
```

**Market Regime Detection**:
```python
def detect_market_regime(adx_value, atr_pct) → str:
    # Returns: 'Trending', 'Ranging', 'Transitional'
    # Based on ADX threshold (25/15) and ATR volatility
```

**ATR-Based Risk Management**:
```python
def calculate_atr_risk_levels(current_price, atr_value, multiplier):
    # Returns stop-loss, TP1, TP2, R:R ratios
```

### 4. Configuration System

#### `config.py`
**Purpose**: Central configuration hub
**Structure**:
```python
# API Credentials (from env vars)
BITHUMB_CONNECT_KEY
BITHUMB_SECRET_KEY

# Trading Config
TRADING_CONFIG = {
    'target_ticker': 'BTC',
    'trade_amount_krw': 10000,
    'stop_loss_percent': 5.0,
    # ...
}

# Strategy Config
STRATEGY_CONFIG = {
    'candlestick_interval': '1h',  # DEFAULT
    'short_ma_window': 20,
    'long_ma_window': 50,
    # ... 50+ parameters

    'signal_weights': {
        'macd': 0.35,  # Highest weight
        'ma': 0.25,
        'rsi': 0.20,
        'bb': 0.10,
        'volume': 0.10
    },

    'interval_presets': {
        '30m': {...},
        '1h': {...},   # Default preset
        '6h': {...},
        '12h': {...},
        '24h': {...}
    }
}

# Schedule, Logging, Safety configs...
```

**Interval Presets**: Optimized indicator parameters for each timeframe (e.g., 1h uses MACD(8,17,9), 24h uses MACD(12,26,9)).

#### `config_manager.py`
**Purpose**: Runtime configuration updates
**Responsibilities**:
- Load/save config changes
- Apply interval preset switching
- Validate configuration values
- Notify components of changes

### 5. GUI Components

#### `chart_widget.py` (v3.0)
**Purpose**: Real-time candlestick chart with indicators
**Recent Changes**:
- Rebuilt from scratch using pure matplotlib (v3.0)
- Fixed x-axis compression issue
- Dynamic subplot layout based on active indicators

**Features**:
- 8 indicator checkboxes (all off by default)
- Main chart overlays: MA lines, Bollinger Bands
- Subplots: RSI (30/70 levels), MACD (histogram), Volume (color-coded bars)
- Info box: Stochastic K/D, ATR value/%, ADX trend strength
- Real-time toggle: Checkbox changes apply immediately without refresh

**Implementation**:
```python
class ChartWidget:
    def update_chart(self):
        # Clear and recreate chart
        # Count active indicators
        # Create dynamic subplot layout
        # Plot candlesticks
        # Plot enabled indicators
        # Redraw canvas
```

#### `signal_history_widget.py`
**Purpose**: Historical signal tracking
**Features**:
- Table view of past signals
- Timestamp, signal type, confidence
- Individual indicator values snapshot

### 6. Logging System

#### `logger.py`
**Purpose**: Multi-channel logging with transaction history
**Log Channels**:
1. **Trade Log**: All trade decisions and executions
2. **Decision Log**: Strategy analysis results
3. **Error Log**: Exceptions and API failures
4. **Transaction History**: JSON format for backtesting

**Features**:
- Daily log rotation (`trading_YYYYMMDD.log`)
- Markdown table format for transaction history
- FIFO profit calculation on sell orders
- Thread-safe logging

**Classes**:
```python
class TradingLogger:
    def log_decision(self, ticker, decision, analysis)
    def log_trade(self, ticker, action, price, amount)
    def log_error(self, error_msg, exception)

class TransactionHistory:
    def record_transaction(self, tx_data)
    def get_transactions(self, filters)
    def calculate_profit(self, sell_tx)  # FIFO
```

### 7. API Layer

#### `bithumb_api.py`
**Purpose**: Bithumb API wrapper (public endpoints only)
**Functions**:
```python
get_ticker(ticker) → Dict
    # Returns current price, 24h high/low, volume

get_candlestick(ticker, interval) → pd.DataFrame
    # Returns OHLCV data
    # Columns: open, high, low, close, volume, timestamp

get_orderbook(ticker) → Dict
    # Returns bid/ask data (not used in current implementation)
```

**Note**: Balance inquiry and private trading endpoints intentionally disabled for security.

#### `pybithumb/`
**Purpose**: Third-party Bithumb library
**Source**: https://github.com/sharebook-kr/pybithumb
**Setup**: Auto-cloned by run scripts if missing
**Usage**: Provides additional API utilities (not heavily used)

### 8. Utility Components

#### `portfolio_manager.py`
**Purpose**: Portfolio tracking and management
**Features**:
- Multi-coin position tracking
- Transaction history aggregation
- FIFO-based profit/loss calculation
- Portfolio performance metrics

**Note**: Balance inquiry feature disabled in current version for security.

---

## Data Flow

### 1. CLI Trading Cycle

```
┌────────────────────────────────────────────────────────────────┐
│                         SCHEDULED TRIGGER                      │
│                    (Every 15 minutes default)                  │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  main.py: trading_bot.execute_trading_cycle()                  │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  bithumb_api.py: get_ticker() + get_candlestick()              │
│  ↓ Returns: Current price + OHLCV DataFrame                    │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  strategy.py: TradingStrategy.analyze_market_data()            │
│  ↓ Calculates 8 indicators                                     │
│  ↓ Generates weighted signals                                  │
│  ↓ Detects market regime                                       │
│  ↓ Calculates ATR risk levels                                  │
│  ↓ Returns: analysis dict                                      │
└───────────────────────────┬────────────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────────────┐
│  trading_bot.py: Process signals                               │
│  ↓ Check confidence >= 0.6                                     │
│  ↓ Check signal strength >= 0.5 (buy) or <= -0.5 (sell)       │
│  ↓ Check daily trade limits                                    │
│  ↓ Check consecutive loss limits                               │
│  ↓ Check emergency stop flag                                   │
└───────────────────────────┬────────────────────────────────────┘
                            │
                ┌───────────┴───────────┐
                │                       │
                ▼                       ▼
        [Conditions Met]        [Conditions Not Met]
                │                       │
                ▼                       ▼
    ┌──────────────────┐      ┌──────────────────┐
    │ Execute Trade    │      │ Log HOLD         │
    │ - buy_coin()     │      │ - Decision log   │
    │ - sell_coin()    │      └──────────────────┘
    │ - Update counters│
    │ - Log transaction│
    └──────────────────┘
                │
                ▼
    ┌──────────────────────────────────┐
    │  logger.py: Record Transaction   │
    │  - JSON history                  │
    │  - Markdown table                │
    │  - FIFO profit calculation       │
    └──────────────────────────────────┘
```

### 2. GUI Real-time Updates

```
┌────────────────────────────────────────────────────────────────┐
│  GUI Main Loop: update_gui() (every 100ms)                     │
└───────────────────────────┬────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐  ┌──────────────────┐  ┌──────────────┐
│ Price Update │  │ Log Queue Check  │  │ Status Update│
│ (5s interval)│  │ (Real-time)      │  │ (Bot status) │
└──────────────┘  └──────────────────┘  └──────────────┘
        │                   │                   │
        ▼                   ▼                   ▼
┌────────────────────────────────────────────────────────────────┐
│  Update GUI Elements:                                          │
│  - Current price label                                         │
│  - LED indicators (8 indicators)                               │
│  - Signal strength bars                                        │
│  - Confidence meter                                            │
│  - Market regime panel                                         │
│  - ATR risk levels                                             │
│  - Log text widget                                             │
└────────────────────────────────────────────────────────────────┘
```

### 3. Chart Update Flow

```
User clicks "Refresh" or toggles indicator checkbox
                │
                ▼
chart_widget.py: update_chart()
                │
                ▼
strategy.analyze_market_data(ticker, interval)
                │
                ▼
Calculate all 8 indicators
                │
                ▼
Check which indicators are enabled (checkboxes)
                │
                ▼
Create dynamic subplot layout (1 main + N subplots)
                │
                ▼
Plot main candlestick chart
                │
                ▼
Overlay enabled indicators:
  - Main chart: MA lines, Bollinger Bands
  - Subplot 1: RSI (if enabled)
  - Subplot 2: MACD (if enabled)
  - Subplot 3: Volume (if enabled)
                │
                ▼
Display info box: Stochastic, ATR, ADX (if enabled)
                │
                ▼
Redraw canvas (instant update)
```

---

## Technology Stack

### Core Technologies
- **Language**: Python 3.7+
- **GUI Framework**: Tkinter (built-in)
- **Charting**: Matplotlib 3.x
- **Data Processing**: Pandas, NumPy

### Key Libraries
```
pandas >= 1.3.0          # DataFrame operations, indicator calculations
numpy >= 1.21.0          # Numerical computations
matplotlib >= 3.4.0      # Chart plotting
requests >= 2.26.0       # HTTP API calls
schedule >= 1.1.0        # Task scheduling
tkinter (built-in)       # GUI framework
```

### External Services
- **Bithumb REST API**: Market data and trading endpoints
- **File System**: Log storage, transaction history

### Development Tools
- **Git**: Version control
- **Virtual Environment**: `.venv` for dependency isolation
- **Shell Scripts**: `run.sh`, `run_gui.sh` for easy deployment

---

## Design Patterns

### 1. Strategy Pattern
**Applied In**: `strategy.py`
**Purpose**: Separate indicator calculations from execution logic
**Implementation**:
- Each indicator is a standalone function
- TradingStrategy class coordinates indicator calls
- Easy to add/remove indicators without touching bot code

### 2. Adapter Pattern
**Applied In**: `gui_trading_bot.py`
**Purpose**: Adapt TradingBot for GUI-specific requirements
**Implementation**:
- GUITradingBot wraps TradingBot
- Adds status callbacks and enhanced reporting
- Maintains same core trading logic

### 3. Observer Pattern
**Applied In**: GUI logging system
**Purpose**: Real-time log streaming to GUI
**Implementation**:
- Logger writes to queue.Queue
- GUI polls queue and updates text widget
- Decouples logging from GUI update logic

### 4. Singleton Pattern (Implicit)
**Applied In**: Configuration
**Purpose**: Single source of truth for config
**Implementation**:
- `config.py` module-level variables
- ConfigManager for runtime updates
- All components import from same config

### 5. Template Method Pattern
**Applied In**: Trading cycle execution
**Purpose**: Define trading algorithm skeleton
**Implementation**:
```python
def execute_trading_cycle(self):
    data = self._fetch_data()
    analysis = self._analyze(data)
    decision = self._decide(analysis)
    if self._check_safety(decision):
        self._execute(decision)
    self._log_result(decision)
```

### 6. Factory Pattern (Partial)
**Applied In**: Interval preset switching
**Purpose**: Create optimized config based on timeframe
**Implementation**:
- `config.py` contains `interval_presets` dict
- ConfigManager applies preset parameters
- Strategy automatically adjusts to new parameters

---

## Security Architecture

### 1. API Key Management
**Best Practices Enforced**:
- Environment variables for key storage (`BITHUMB_CONNECT_KEY`, `BITHUMB_SECRET_KEY`)
- `.env` file support with `.gitignore` protection
- Warnings if keys are hardcoded
- No keys in log files

**Security Features**:
- Balance inquiry intentionally disabled (reduces attack surface)
- Read-only public API usage for market data
- Private API only used in test files (not in production bot)

### 2. Trading Safety
**Dry-Run Mode** (default):
- `SAFETY_CONFIG['dry_run'] = False` (CLI trading is live by default)
- `SAFETY_CONFIG['dry_run'] = True` for paper trading
- Simulates trades without actual execution
- Logs show "[DRY RUN]" prefix

**Risk Limits**:
- Daily trade limit (`max_daily_trades`: 10)
- Daily loss limit (`max_daily_loss_pct`: 3%)
- Consecutive loss limit (`max_consecutive_losses`: 3)
- Emergency stop flag (`emergency_stop`: manual kill switch)

**ATR-Based Stops**:
- Dynamic stop-loss calculation
- Position sizing based on volatility
- Prevents overleveraging in high-volatility conditions

### 3. Error Handling
**Exception Management**:
- Try-catch blocks around all API calls
- Graceful degradation on network errors
- Error logging with stack traces
- Bot continues running after non-critical errors

**Validation**:
- Config validation on startup (`validate_config()`)
- Minimum trade amount checks
- API response validation
- Data integrity checks (NaN handling in indicators)

---

## Performance Considerations

### 1. Computational Efficiency
**Optimizations**:
- Pandas vectorized operations (no loops for indicator calculations)
- Minimal API calls (15-minute default interval)
- Cached analysis results within trading cycle
- Lazy loading of indicator data

**Resource Usage**:
- Memory: ~50-100 MB (with GUI)
- CPU: <5% on modern hardware
- Network: ~1 KB per API call (15 min intervals = 4 KB/hour)

### 2. GUI Responsiveness
**Techniques**:
- Threading for bot execution (non-blocking GUI)
- Queue-based log streaming (100ms poll interval)
- Throttled price updates (5-second interval)
- On-demand chart updates (manual refresh)

**Chart Performance**:
- Matplotlib figure caching
- Maximum 200 candlesticks displayed
- Dynamic subplot creation only when needed
- Instant checkbox toggle (no re-fetch data)

### 3. Data Management
**Storage Strategy**:
- Daily log file rotation (prevents large files)
- JSON transaction history (append-only)
- Markdown table history (human-readable backup)
- No database required (file-based)

**Log Retention**:
- Default: 30 days of logs
- Configurable: `max_log_files` parameter
- Automatic cleanup of old files

### 4. API Rate Limiting
**Protection**:
- 15-minute default interval (96 calls/day)
- Configurable interval based on candlestick timeframe
- No unnecessary balance checks
- Single API call per trading cycle

---

## Extension Points

### Adding New Indicators
1. Add calculation function to `strategy.py`:
   ```python
   def calculate_new_indicator(df: pd.DataFrame, params) -> pd.Series:
       # Calculation logic
       return result
   ```

2. Call in `analyze_market_data()`:
   ```python
   new_indicator = calculate_new_indicator(df, params)
   analysis['new_indicator'] = new_indicator
   ```

3. Add signal generation in `generate_weighted_signals()`:
   ```python
   new_signal = generate_new_indicator_signal(analysis['new_indicator'])
   individual_signals['new'] = new_signal
   ```

4. Add weight to `config.py`:
   ```python
   'signal_weights': {
       'new': 0.05,
       # Adjust other weights to sum to 1.0
   }
   ```

5. Add GUI display in `chart_widget.py` and `gui_app.py`

### Adding New Strategy Presets
1. Define preset in `config.py`:
   ```python
   'custom_preset': {
       'macd': 0.50,  # High MACD weight
       'rsi': 0.30,
       'ma': 0.20
   }
   ```

2. Add to GUI dropdown in `gui_app.py`

3. Document in user guides

### Adding New Timeframes
1. Add interval preset to `config.py`:
   ```python
   '4h': {
       'short_ma_window': 15,
       # ... optimized parameters
   }
   ```

2. Add to `interval_check_periods` in SCHEDULE_CONFIG

3. Update chart widget dropdown

---

## Deployment Architecture

### Development Setup
```bash
cd 005_money
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py  # CLI mode
python gui_app.py  # GUI mode
```

### Production Deployment
**Option 1: Screen/tmux** (headless server)
```bash
screen -S trading_bot
./run.sh
# Ctrl+A, D to detach
```

**Option 2: Systemd Service** (Linux)
```ini
[Unit]
Description=Bithumb Trading Bot

[Service]
Type=simple
User=trader
WorkingDirectory=/path/to/005_money
ExecStart=/path/to/005_money/.venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

**Option 3: Docker** (containerized)
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

---

## Maintenance and Monitoring

### Health Checks
- Log file monitoring (check for ERROR entries)
- Daily trade count tracking
- Consecutive loss monitoring
- API connectivity verification

### Updates
- Pull latest code: `git pull`
- Update dependencies: `pip install --upgrade -r requirements.txt`
- Review config changes: `git diff config.py`
- Test in dry-run mode before live trading

### Backup Strategy
- Transaction history JSON files (critical)
- Configuration backups before changes
- Log file archival (optional)

---

## Known Limitations

1. **No Multi-Exchange Support**: Only Bithumb API
2. **Single Coin Trading**: One ticker at a time (BTC default)
3. **No Backtesting**: Historical strategy testing not implemented
4. **Limited Order Types**: Market orders only (no limit orders)
5. **No WebSocket**: Polling-based updates (15-min default)
6. **No Advanced Orders**: No stop-loss orders placed on exchange (calculated client-side)

---

## Future Architecture Improvements

### Proposed Enhancements
1. **WebSocket Integration**: Real-time price updates
2. **Database Layer**: PostgreSQL/SQLite for transaction history
3. **Microservices**: Separate strategy engine, execution engine
4. **Multi-Exchange**: Abstract API layer, exchange adapters
5. **Backtesting Module**: Historical data testing framework
6. **Alert System**: Email/SMS/Telegram notifications
7. **Web Dashboard**: React/Vue.js frontend with REST API backend

### Scalability Path
```
Current: Single-process monolith
         ↓
Phase 1: Multi-threaded (separate strategy/execution)
         ↓
Phase 2: Multi-process (message queue for IPC)
         ↓
Phase 3: Microservices (Docker, Kubernetes)
```

---

## References

- **Bithumb API Docs**: https://apidocs.bithumb.com/
- **pybithumb Library**: https://github.com/sharebook-kr/pybithumb
- **Technical Analysis**: Standard indicator formulas (Wilder, Murphy, etc.)
- **Project CLAUDE.md**: `/Users/seongwookjang/project/git/violet_sw/CLAUDE.md`

---

**Document Version**: 1.0
**Contributors**: Project Lead, Development Team
**Last Reviewed**: 2025-10-02
