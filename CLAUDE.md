# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Repository Overview

Multi-language learning and development repository.

| Directory | Description | Language |
|-----------|-------------|----------|
| `000_personal_lib_code/` | Reusable utility libraries | Python |
| `001_coding_test_question/` | Coding test solutions | Python |
| `002_study_swift/` | Swift/iOS learning materials | Swift |
| `003_script/` | Utility scripts | Bash/Python |
| `004_hacker_rank/` | HackerRank solutions | Python |
| `005_money/` | **Cryptocurrency Trading Bot** | Python |

## Main Project: Trading Bot (005_money/)

Bithumb exchange automated trading bot with multiple strategy versions.

### Quick Start

```bash
cd 005_money
./scripts/run_v3_cli.sh    # CLI mode
./scripts/run_v3_gui.sh    # GUI mode
```

### Documentation

Detailed documentation is in `005_money/`:
- `CLAUDE.md` - Project overview and quick reference
- `.claude/rules/` - Detailed code analysis and development guide
  - `01-project-overview.md` - Architecture and tech stack
  - `02-ver3-strategy.md` - Trading strategy details
  - `03-code-structure.md` - Code structure and class relationships
  - `04-telegram-commands.md` - Telegram bot commands
  - `05-development-guide.md` - Development and debugging guide

### Key Components

```
005_money/001_python_code/
├── ver3/                    # Current version (Portfolio Multi-Coin)
│   ├── trading_bot_v3.py    # Main bot orchestrator
│   ├── strategy_v3.py       # Trading strategy
│   └── ...
└── lib/                     # Shared libraries
    ├── api/                 # Bithumb API wrapper
    ├── core/                # Telegram, logging
    └── gui/                 # GUI components
```

## Other Projects

### Swift Projects (002_study_swift/)

```bash
open 002_study_swift/HelloWorld/HelloWorld.xcodeproj
swift 002_study_swift/hello.swift
```

### Coding Test (001_coding_test_question/)

```bash
python 001_coding_test_question/chapter03/3-1.py
```

## Development Guidelines

- **File creation**: Only create new files when absolutely necessary
- **Documentation**: Do not create .md files unless explicitly requested
- **Code changes**: Focus on what was asked; avoid unnecessary refactoring
- **Version awareness**: Check which version (ver1/ver2/ver3) before modifying
- **Shared lib changes**: Ensure backward compatibility with all versions
