# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Structure

This is a multi-language learning and development repository with the following main directories:

- `000_personal_lib_code/` - Reusable Python utility libraries (e.g., timing/performance measurement tools)
- `001_coding_test_question/` - Python coding test solutions organized by chapters (chapter03-06)
- `002_study_swift/` - Swift learning materials including iOS projects and standalone Swift files
- `003_script/` - Utility scripts including Verilog-related tools
- `004_hacker_rank/` - HackerRank problem solutions in Python
- `005_money/` - Cryptocurrency trading bot project with Bithumb API integration

## Development Commands

### Cryptocurrency Trading Bot (005_money/)
```bash
# Quick start (recommended - handles all setup automatically)
cd 005_money
./run.sh                          # Bash script with full environment setup
python run.py                     # Python script with argument parsing

# GUI mode
./gui                             # Direct GUI executable
./run.sh --gui                    # GUI through run script
python run_gui.py                 # Python GUI launcher

# Manual setup
python3 -m venv .venv
source .venv/bin/activate  # On macOS/Linux
pip install -r requirements.txt
python main.py

# Advanced usage with parameters
python run.py --interval 30s --coin ETH --amount 50000
./run.sh --coin BTC --live        # Real trading mode (careful!)
python main.py --interactive      # Interactive configuration
```

### Swift Projects (002_study_swift/)
```bash
# Open Xcode projects (iOS apps)
open 002_study_swift/HelloWorld/HelloWorld.xcodeproj
open 002_study_swift/ImageView/ImageView.xcodeproj

# Compile standalone Swift files
swift 002_study_swift/hello.swift
swift 002_study_swift/tuple_test.swift
```

### Running Individual Python Scripts
Most Python files in coding test and HackerRank directories are standalone:
```bash
python 001_coding_test_question/chapter03/3-1.py
python 004_hacker_rank/calendar_module.py
```

## Architecture Overview

### Cryptocurrency Trading Bot (005_money/)

**Core Trading System:**
- `main.py` - Entry point with scheduling loop, coordinates bot execution every 15 minutes (configurable)
- `trading_bot.py` - Trading logic coordinator, calls strategy analysis and executes trades via API
- `strategy.py` - **Elite trading strategy implementation** with 8 technical indicators:
  - Classic: MA (Moving Average), RSI, Bollinger Bands, Volume
  - Elite additions: MACD, ATR (volatility), Stochastic, ADX (trend strength)
  - Market regime detection (Trending/Ranging/Transitional)
  - Weighted signal combination system (returns -1.0 to +1.0 gradual signals instead of binary)
  - ATR-based dynamic stop-loss and position sizing

**API & Data:**
- `bithumb_api.py` - Bithumb exchange API wrapper (public ticker, candlestick data)
- `pybithumb/` - Third-party Bithumb library (cloned from GitHub if missing)
- Balance inquiry intentionally disabled for security in this implementation

**Configuration:**
- `config.py` - **Central configuration hub**:
  - Default candlestick interval: `1h` (changed from 24h)
  - Interval presets: 30m, 1h, 6h, 12h, 24h with optimized parameters
  - Signal weights: MACD=0.35, MA=0.25, RSI=0.20, BB=0.10, Volume=0.10
  - Risk management: max daily loss, consecutive losses, ATR-based stops
  - All indicator parameters (MACD fast/slow/signal, ATR period, Stochastic K/D, etc.)
- `config_manager.py` - Dynamic configuration updates during runtime

**GUI System (Tkinter-based):**
- `gui_app.py` - Main GUI application with 4 tabs:
  1. "거래 현황" - Trading status, logs, profit tracking
  2. "📊 실시간 차트" - Real-time candlestick chart with indicator overlays
  3. "📋 신호 히스토리" - Signal history tracking
  4. "📜 거래 내역" - Transaction history
- `chart_widget.py` - **Chart visualization module (v3.0)**:
  - Pure matplotlib implementation (no mplfinance dependency issues)
  - 8 indicator checkboxes for on/off control (all off by default)
  - Dynamic subplot layout (adjusts based on active indicators)
  - Main chart overlays: MA lines, Bollinger Bands
  - Separate subplots: RSI, MACD, Volume bar chart
  - Info box display: Stochastic, ATR, ADX values
  - Real-time updates when checkboxes toggled (no refresh needed)
- `gui_trading_bot.py` - GUI-specific trading bot adapter, integrates with weighted signal system
- `signal_history_widget.py` - Displays historical trading signals

**Logging & History:**
- `logger.py` - Multi-channel logging system:
  - Trade log, decision log, error log, transaction history
  - Separate log files per day in `logs/` directory
- Transaction history stored in JSON format

**Launchers & Utilities:**
- `run.py` / `run.sh` - Environment setup scripts with argument parsing
- `run_gui.py` - GUI launcher with dependency checks
- `./gui` - Precompiled GUI executable
- `portfolio_manager.py` - Portfolio tracking (if multi-coin trading enabled)

**Key Design Patterns:**
- **Strategy pattern**: Indicator calculations separated into individual functions in `strategy.py`
- **Weighted signal combination**: Each indicator returns gradual strength (-1.0 to +1.0), combined with configurable weights instead of simple binary vote counting
- **Market regime awareness**: Different strategies applied based on detected market conditions (trending vs ranging)
- **Risk-first design**: ATR-based position sizing, daily loss limits, consecutive loss tracking
- **Separation of concerns**: API layer, strategy layer, execution layer, GUI layer all independent

### Swift Learning Projects
- Basic iOS apps with UIKit framework
- `HelloWorld` - Simple text input/output app
- `ImageView` - Image manipulation and display app
- Standalone Swift files for language feature exploration

### Coding Test Solutions
- Organized by difficulty/chapter progression
- Each file typically contains a single algorithm problem solution
- Focuses on common algorithmic patterns (greedy algorithms, implementation, etc.)

## Dependencies

### Python (005_money/)
Required packages (installed via `pip install -r requirements.txt`):
- `pandas` - DataFrame operations for OHLCV data and indicator calculations
- `numpy` - Numerical computations (ATR, moving averages, statistical operations)
- `requests` - HTTP requests for Bithumb API calls
- `schedule` - Task scheduling (periodic execution every 15 min by default)
- `matplotlib` - Chart plotting (candlesticks, indicators, subplots)
- `mplfinance` - Financial chart utilities (optional, v3.0 chart uses pure matplotlib)
- `tkinter` - GUI framework (usually bundled with Python, no pip install needed)

**Installation troubleshooting:**
If you encounter ModuleNotFoundError, run:
```bash
cd 005_money
source .venv/bin/activate  # if using venv
pip install -r requirements.txt
```

**pybithumb library:**
The system automatically clones pybithumb from GitHub if not found:
```bash
if [ ! -d "pybithumb" ]; then
  git clone --depth 1 https://github.com/sharebook-kr/pybithumb.git
fi
```

### Swift/iOS (002_study_swift/)
- UIKit framework for iOS app development
- Xcode required for building iOS projects

## Key Features & Implementation Notes

### Trading Bot (005_money/)

**Execution Modes:**
- CLI mode: `python main.py` - Headless automated trading with scheduling
- GUI mode: `python run_gui.py` or `./gui` - Visual interface with live chart
- Interactive mode: `python main.py --interactive` - Step-by-step configuration

**Elite Trading Strategy (Implemented 2025-10):**
- **8 Technical Indicators**: MA, RSI, Bollinger Bands, Volume, MACD, ATR, Stochastic, ADX
- **Weighted Signal System**: Indicators contribute gradual strength (-1.0 to +1.0) with configurable weights
  - Example: Strong bullish MACD (0.9) + neutral RSI (0.0) + bearish MA (-0.5) = weighted combination
  - Replaces old binary voting system (simple sum of -1, 0, +1)
- **Market Regime Detection**: Automatically detects Trending/Ranging/Transitional markets using ADX and ATR
- **ATR-Based Risk Management**:
  - Dynamic stop-loss: `stop_price = entry - (ATR × multiplier)`
  - Position sizing: Adjusts trade amount based on volatility
  - Exit levels: TP1 (1:1.5 R:R), TP2 (1:2.5 R:R)
- **Interval Optimization**: Each timeframe (30m, 1h, 6h, 12h, 24h) has preset indicator parameters
  - Default: 1h candlesticks with MACD(8,17,9), RSI(14), MA(20,50)

**Chart Visualization (v3.0 - Rebuilt 2025-10):**
- **Problem solved**: Previous x-axis compression issue resolved by using pure matplotlib instead of mplfinance
- **User control**: 8 checkboxes to enable/disable indicators (all off by default)
- **Dynamic layout**: Chart automatically adjusts subplot count based on active indicators
- **Real-time updates**: Checkbox changes apply immediately without refresh button
- **Display locations**:
  - Main chart overlays: MA lines (orange/purple), Bollinger Bands (gray dashed)
  - Subplots (below main): RSI (with 30/70 levels), MACD (line/signal/histogram), Volume (color-coded bars)
  - Info box (top-right): Stochastic K/D values, ATR value/%, ADX trend strength

**Safety Features:**
- **Dry-run mode**: Test strategies without real trades (set in `config.py`)
- **Trade limits**: Max daily trades, max consecutive losses, daily loss percentage cap
- **API key security**: Environment variables recommended, warnings if hardcoded
- **Balance checks**: Periodic verification (every 60 min) to prevent overdrafts
- **Emergency stop**: Quick kill switch in GUI or config

**Configuration Management:**
- **Central config**: `config.py` contains all parameters (150+ settings)
- **Runtime updates**: `config_manager.py` allows changing settings without restart
- **Preset switching**: Switch between 30m/1h/6h/12h/24h presets, auto-adjusts all indicator periods
- **Signal weight tuning**: Adjust MACD/MA/RSI/BB/Volume weights to customize strategy bias

**Logging System:**
- **Multi-channel**: Separate logs for trades, decisions, errors, transactions
- **Daily rotation**: New log files created each day in `logs/trading_YYYYMMDD.log`
- **Transaction history**: JSON format for backtesting and analysis
- **GUI integration**: Real-time log display in scrollable text widget

## Common Debugging Issues

### Trading Bot (005_money/)

**"ModuleNotFoundError: No module named 'requests'" (or pandas, numpy, etc.):**
```bash
cd 005_money
source .venv/bin/activate  # Activate venv if using one
pip install -r requirements.txt
```

**Chart x-axis compression / Graph looks squished:**
- Fixed in v3.0 of `chart_widget.py` (2025-10 rebuild)
- If you see older code using mplfinance or fixed figure sizes, the chart was rebuilt to use pure matplotlib with dynamic sizing

**"Object of type DataFrame is not JSON serializable":**
- This occurs when trying to serialize analysis results containing pandas DataFrames
- Solution: Exclude 'price_data' field from JSON serialization in GUI code
- The `analyze_market_data()` method in `strategy.py` returns a dict with DataFrames that must be handled carefully

**API authentication errors (401 Unauthorized):**
- Check API keys are set via environment variables or in `config.py`
- For testing, set `dry_run: True` in `SAFETY_CONFIG` to skip real API calls
- Balance inquiry is intentionally disabled in current implementation

**pybithumb not found:**
- The system should auto-clone from GitHub: `git clone --depth 1 https://github.com/sharebook-kr/pybithumb.git`
- Manual: `cd 005_money && git clone https://github.com/sharebook-kr/pybithumb.git`

**Chart not updating when checkboxes toggled:**
- Ensure you're using v3.0 of `chart_widget.py` which has `on_indicator_toggle()` method
- Check that checkboxes are connected: `indicator_var.trace('w', lambda *args: self.update_chart())`

## Important Development Guidelines

- **File creation**: Only create new files when absolutely necessary; prefer editing existing files
- **Documentation**: Do not proactively create .md or README files unless explicitly requested
- **Code changes**: Focus on what was asked; avoid unnecessary refactoring or improvements
- **Strategy modifications**: When changing trading logic, always update corresponding config presets in `config.py`
- **Indicator additions**: If adding new indicators, update:
  1. Calculation function in `strategy.py`
  2. Signal generation in `generate_weighted_signals()`
  3. Chart display in `chart_widget.py`
  4. Checkbox in GUI if user-controllable
  5. Signal weights in `config.py`
