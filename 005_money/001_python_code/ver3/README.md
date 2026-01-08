# Version 3: Portfolio Multi-Coin Trading Strategy

**Status:** Production Ready
**Date:** 2025-10-08 (Updated: 2026-01-08)
**Author:** Claude AI

---

## Overview

Version 3 is the **production trading system** with **multi-coin portfolio management capabilities**, enabling simultaneous trading of 2-3 cryptocurrencies with coordinated risk management and parallel market analysis.

### Key Features

- ✅ **Multi-Coin Portfolio Trading** - Simultaneously trade BTC, ETH, XRP, SOL
- ✅ **Pyramiding Support** - Scale into winning positions (up to 3 entries per coin)
- ✅ **Parallel Market Analysis** - ThreadPoolExecutor for concurrent coin analysis
- ✅ **Portfolio-Level Risk Management** - Max 2 positions, 6% total risk limit
- ✅ **Smart Entry Prioritization** - Highest-scoring signals executed first
- ✅ **Thread-Safe Execution** - Safe concurrent order placement
- ✅ **StrategyV3 Per Coin** - Proven EMA regime + score-based entry system
- ✅ **Self-Contained** - All dependencies included within ver3

---

## Architecture: Portfolio Manager Pattern

```
┌──────────────────────────────────────────────────────────┐
│  TradingBotV3 (Main Coordinator)                         │
│  ┌────────────────────────────────────────────────────┐  │
│  │  PortfolioManagerV3                                │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  CoinMonitor(BTC) → StrategyV3               │  │  │
│  │  │  CoinMonitor(ETH) → StrategyV3 (shared)      │  │  │
│  │  │  CoinMonitor(XRP) → StrategyV3               │  │  │
│  │  │                                              │  │  │
│  │  │  LiveExecutorV3 (thread-safe, shared)       │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │                                                    │  │
│  │  Portfolio Decision Logic:                        │  │
│  │  - Count active positions                         │  │
│  │  - Prioritize signals by score                    │  │
│  │  - Apply position limits                          │  │
│  │  - Execute highest-priority trades                │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### Core Components

1. **TradingBotV3** - Main coordinator
   - Runs 15-minute analysis cycles
   - Manages portfolio lifecycle
   - Provides logging and status

2. **PortfolioManagerV3** - Multi-coin coordinator
   - Analyzes all coins in parallel
   - Makes portfolio-level decisions
   - Enforces position limits
   - Executes trades

3. **CoinMonitor** - Single coin wrapper
   - Delegates to StrategyV3 for analysis
   - Caches last result
   - Tracks update timestamp

4. **LiveExecutorV3** - Thread-safe executor
   - Thread-safe with threading.Lock
   - Manages multi-coin positions
   - Safe concurrent execution

5. **StrategyV3 (Shared)** - Per-coin analysis
   - Daily EMA(50/200) regime filter
   - 4H score-based entry (BB/RSI/Stoch)
   - ATR-based Chandelier Exit

---

## Configuration

### Default Portfolio Settings

```python
PORTFOLIO_CONFIG = {
    'max_positions': 2,              # Max simultaneous positions
    'default_coins': ['BTC', 'ETH', 'XRP'],
    'entry_priority': 'score',       # Prioritize by score
    'max_portfolio_risk_pct': 6.0,   # 6% total risk
    'parallel_analysis': True,       # Enable parallel analysis
    'max_workers': 3,                # Thread pool size
}
```

### Trading Settings

```python
TRADING_CONFIG = {
    'symbols': ['BTC', 'ETH', 'XRP'],
    'trade_amount_krw': 50000,       # Per coin (not total)
    'min_trade_amount': 10000,
}

SCHEDULE_CONFIG = {
    'check_interval_seconds': 900,   # 15 minutes
}

EXECUTION_CONFIG = {
    'mode': 'live',
    'dry_run': True,                 # Start in dry-run mode
}
```

---

## Usage

### Quick Start (Command Line)

```bash
# Navigate to project directory
cd /Users/seongwookjang/project/git/violet_sw/005_money

# Run Ver3 with Watchdog (Recommended)
./scripts/run_v3_watchdog.sh

# Or run Ver3 CLI directly
./scripts/run_v3_cli.sh

# Verify Ver3 is running
# Check logs: tail -f logs/ver3_cli_$(date +%Y%m%d).log
```

### Programmatic Usage

```python
from ver3.trading_bot_v3 import TradingBotV3
from ver3.config_v3 import get_version_config

# Get configuration
config = get_version_config()

# Customize coins (optional)
config['PORTFOLIO_CONFIG']['default_coins'] = ['BTC', 'ETH']

# Create and run bot
bot = TradingBotV3(config)
bot.run()
```

### Testing

```bash
# Run comprehensive test suite
cd /Users/seongwookjang/project/git/violet_sw/005_money
python 001_python_code/ver3/test_portfolio_v3.py

# Expected output:
# ✅ PASS: Configuration Loading
# ✅ PASS: Portfolio Manager Init
# ✅ PASS: Parallel Analysis
# ✅ PASS: Portfolio Decision Logic
# ✅ PASS: Portfolio Summary
# ✅ PASS: TradingBotV3 Initialization
# Total: 6/6 tests passed
```

---

## How It Works

### Analysis Cycle (Every 15 Minutes)

```
1. Parallel Analysis (ThreadPoolExecutor)
   ├─ BTC analysis (StrategyV3) ──┐
   ├─ ETH analysis (StrategyV3) ──┤ Concurrent
   └─ XRP analysis (StrategyV3) ──┘
   ↓
2. Portfolio Decision Making
   ├─ Count current positions (e.g., 1/2)
   ├─ Collect entry signals (e.g., BTC=3/4, ETH=4/4, XRP=1/4)
   ├─ Prioritize by score: ETH(4) > BTC(3) > XRP(1)
   ├─ Apply portfolio limit: Only 1 slot available
   └─ Decision: Enter ETH (highest score)
   ↓
3. Trade Execution (Thread-Safe)
   ├─ Execute BUY ETH order
   ├─ Update position tracking
   └─ Log transaction
   ↓
4. Portfolio Summary
   ├─ Calculate total P&L
   ├─ Log individual coin status
   └─ Update GUI (if running)
   ↓
5. Sleep until next cycle (15 min)
```

### Entry Signal Prioritization Example

**Scenario:** BTC, ETH, and XRP all signal BUY

| Coin | Entry Score | Signal Strength | Current Positions | Decision |
|------|-------------|-----------------|-------------------|----------|
| BTC  | 3/4         | 0.75            | 1/2 slots used    | Skip (lower score) |
| ETH  | 4/4         | 1.00            |                   | ✅ Enter (highest) |
| XRP  | 2/4         | 0.50            |                   | Skip (limit reached) |

**Result:** Only ETH enters (1 slot available, ETH has highest score)

---

## Portfolio Risk Management

### Position Limits

- **Max Simultaneous Positions:** 2 (configurable)
- **Max Entries Per Coin:** Up to 3 pyramid entries (configurable)
- **Total Portfolio Risk:** 6% maximum

### Risk Controls

1. **Portfolio-Level Limits**
   - Enforced before each entry
   - Highest-scoring signals enter first
   - Exits always allowed (risk reduction)

2. **Per-Trade Risk**
   - 2% risk per coin
   - ATR-based position sizing
   - Stop-loss: Chandelier Exit

3. **Daily Limits**
   - Max daily trades: 5
   - Max consecutive losses: 3
   - Max daily loss: 3%

---

## Individual Coin Strategy (StrategyV3)

Each coin analyzed using the proven strategy:

### 1. Market Regime Filter (Daily Timeframe)
- **Golden Cross:** EMA50 > EMA200 → Trade allowed
- **Death Cross:** EMA50 ≤ EMA200 → No trades

### 2. Entry Scoring System (4H Timeframe)

Requires **2+ points** to enter:

| Signal | Points | Condition |
|--------|--------|-----------|
| BB Lower Touch | 1 | Low ≤ BB Lower Band |
| RSI Oversold | 1 | RSI < 35 |
| Stoch Cross | 2 | Stoch K crosses above D below 20 |

**Max Score:** 4 points

### 3. Exit Strategy
- **First Target:** BB Middle (50% position exit)
- **Second Target:** BB Upper (remaining 50%)
- **Stop-Loss:** Chandelier Exit (ATR × 3.0)

---

## Thread Safety

### Critical Sections Protected

1. **Position Updates** - `threading.Lock` in LiveExecutorV3
   ```python
   with self._position_lock:
       self.positions[ticker] = new_position
       self._save_positions()
   ```

2. **Parallel Analysis** - ThreadPoolExecutor isolation
   - Each CoinMonitor operates independently
   - No shared mutable state during analysis

3. **File I/O** - Locked writes
   - `positions_v3.json` written atomically
   - Transaction logs append-only

---

## File Structure

```
ver3/
├── __init__.py                    # Version factory and metadata
├── config_v3.py                   # Configuration
├── config_base.py                 # Base configuration
├── portfolio_manager_v3.py        # Core portfolio management
├── trading_bot_v3.py              # Main coordinator
├── live_executor_v3.py            # Thread-safe executor
├── strategy_v3.py                 # Trading strategy
├── regime_detector.py             # Market regime detection
├── dynamic_factor_manager.py      # Dynamic parameter management
├── run_cli.py                     # CLI entry point
└── README.md                      # This file
```

---

## Dependencies

### Required
- `lib/api/bithumb_api.py` - Exchange API wrapper
- `lib/core/logger.py` - Logging infrastructure
- `lib/core/telegram_notifier.py` - Telegram notifications
- `lib/core/telegram_bot_handler.py` - Telegram commands

### Python Packages
- `pandas` - Data manipulation
- `numpy` - Numerical computations
- `threading` - Concurrency
- `concurrent.futures` - Thread pool

---

## Key Capabilities

| Feature | Description |
|---------|-------------|
| **Coins** | Multi-coin (2-3 simultaneously) |
| **Analysis** | Parallel (all coins together) |
| **Position Limits** | Portfolio-level management |
| **Pyramiding** | Up to 3 entries per coin |
| **Entry Selection** | Prioritized by score |
| **Risk Management** | Portfolio-wide |
| **Thread Safety** | Full threading.Lock |
| **Analysis Interval** | 15 minutes |
| **Watchdog** | Auto-restart on hang |

---

## Performance Expectations

### Analysis Time
- **Parallel (3 coins):** 4-5 seconds for all coins (concurrent)

### API Usage
- **Calls per Cycle:** 6 (1D + 4H for each coin)
- **Calls per Hour:** ~24 (15-min intervals)
- **Well within Bithumb limit:** <20/min

### Memory Usage
- **Ver3:** ~150 MB (3 coins, minor overhead)

---

## Success Metrics

### Technical Metrics
- ✅ Parallel analysis <5 seconds
- ✅ API calls <20/min
- ✅ Zero thread deadlocks
- ✅ GUI responsive <100ms

### Trading Metrics
- **Entry Frequency:** Multiple signals from 3 coins
- **Win Rate:** Track performance over time
- **Portfolio Sharpe Ratio:** Measure risk-adjusted returns
- **Max Drawdown:** Lower through diversification

---

## Troubleshooting

### Issue: "Portfolio Manager is None"
**Cause:** API keys not found
**Fix:**
```bash
export BITHUMB_CONNECT_KEY="your_key"
export BITHUMB_SECRET_KEY="your_secret"
```

### Issue: "Thread deadlock detected"
**Cause:** Race condition in position updates
**Fix:** Verify `_position_lock` added to LiveExecutorV3

### Issue: "All coins skipped - portfolio limit"
**Cause:** Position limit too restrictive
**Fix:**
1. Check `PORTFOLIO_CONFIG['max_positions']`
2. Verify positions cleared: check `logs/positions_v3.json`
3. Reset if needed: `rm logs/positions_v3.json`

### Issue: "Analysis timeout detected"
**Cause:** Bithumb API slow response or network issue
**Fix:** Ver3 has multi-layer timeout protection. If issue persists:
1. Check network connectivity
2. Watchdog will auto-restart if hung for 10 minutes
3. Check logs for specific timeout layer

---

## Future Enhancements

### Planned Features
- **Correlation Filtering:** Don't enter if coins >0.7 correlated
- **Dynamic Position Sizing:** Larger positions for higher scores
- **Multi-Exchange Support:** Binance, Upbit integration
- **GUI Enhancement:** Multi-coin portfolio dashboard

### Recently Implemented
- ✅ **Pyramiding Strategy** - Scale into winning positions with decreasing size (100% → 50% → 25%)

### Scaling Considerations
- **4+ Coins:** Consider async architecture (Option D)
- **10+ Coins:** Microservices approach (Option A)
- **Different Strategies:** Per-coin strategy customization

---

## Deployment

### Getting Started

```bash
# Navigate to project
cd /Users/seongwookjang/project/git/violet_sw/005_money

# Start with watchdog (recommended for production)
./scripts/run_v3_watchdog.sh

# Or start CLI directly
./scripts/run_v3_cli.sh

# Or start with GUI
./scripts/run_v3_gui.sh
```

### Gradual Adoption for Live Trading

1. **Week 1:** Run Ver3 in dry-run mode, verify analysis
2. **Week 2:** Enable small live positions (10,000 KRW)
3. **Week 3:** Increase to normal sizes (50,000 KRW)
4. **Week 4:** Full deployment, monitor performance

---

## Support & Documentation

### Documentation
- **Main Documentation:** `CLAUDE.md` in project root
- **Development Rules:** `.claude/rules/` directory
- **CLI Operation Guide:** `ver3/VER3_CLI_OPERATION_GUIDE.md`

### Logs
- **Main Log:** `logs/ver3_cli_YYYYMMDD.log`
- **Positions:** `logs/positions_v3.json`
- **Transactions:** `logs/transaction_history.json`
- **Dynamic Factors:** `logs/dynamic_factors_v3.json`

---

## License & Credits

**Version 3** - Production Trading System

**Original Date:** 2025-10-08
**Last Updated:** 2026-01-08 (Legacy cleanup refactoring)
**Status:** Production Ready

---

## Quick Reference

### Start Ver3
```bash
./scripts/run_v3_watchdog.sh   # With watchdog (recommended)
./scripts/run_v3_cli.sh        # CLI only
./scripts/run_v3_gui.sh        # GUI mode
```

### Check Logs
```bash
tail -f logs/ver3_cli_$(date +%Y%m%d).log
```

### View Positions
```bash
cat logs/positions_v3.json
```

### Telegram Commands
```
/status     - Bot status
/positions  - Current positions
/factors    - Dynamic factors
/close BTC  - Close specific position
/stop       - Stop bot
```

### Stop Bot
```
Ctrl+C (KeyboardInterrupt)
```

---

**For questions or issues, refer to `CLAUDE.md` and `.claude/rules/` documentation.**
