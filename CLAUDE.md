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
- `main.py` - Entry point with scheduling and main execution loop
- `trading_bot.py` - Core trading bot logic and decision making
- `strategy.py` - Trading decision algorithms (MA, RSI, Bollinger bands)
- `bithumb_api.py` - Bithumb exchange API integration (balance inquiry disabled for security)
- `config.py` / `config_manager.py` - Configuration management (API keys, parameters)
- `logger.py` - Comprehensive logging system for trades and analysis
- `gui_app.py` / `gui_trading_bot.py` - Tkinter-based GUI interface
- `run.py` / `run.sh` - Environment setup and launcher scripts with argument parsing
- `./gui` - Compiled GUI executable for easy access
- Uses `schedule` library for periodic execution
- Supports both CLI and GUI modes with comprehensive parameter control
- Designed for multiple cryptocurrencies with safety features (dry-run mode, trade limits)

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
- `pandas` - Data manipulation for trading analysis
- `requests` - HTTP requests for API calls
- `schedule` - Task scheduling for automated trading
- `numpy` - Numerical computations for technical indicators
- `tkinter` - GUI framework (included with Python)

### Swift/iOS (002_study_swift/)
- UIKit framework for iOS app development
- Xcode required for building iOS projects

## Key Features

### Trading Bot (005_money/)
- **Multiple execution modes**: CLI, GUI, and executable
- **Advanced setup scripts**: Automatic environment detection and dependency management
- **Comprehensive parameter system**: Interval timing, coin selection, trading amounts
- **Safety features**: Dry-run mode (default), trade limits, emergency stops
- **Professional logging**: Separate logs for trades, decisions, errors, and transaction history
- **Real-time configuration**: Interactive mode for dynamic settings
- **Multi-strategy support**: Configurable technical indicators and thresholds