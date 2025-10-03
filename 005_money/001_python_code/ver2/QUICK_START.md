# Quick Start Guide - Version 2 Live Trading

## 🚀 Get Started in 5 Minutes

### Prerequisites

1. **Python Environment**
   ```bash
   cd /Users/seongwookjang/project/git/violet_sw/005_money
   source .venv/bin/activate  # Activate virtual environment
   ```

2. **Required Packages**
   ```bash
   pip install pandas numpy requests schedule python-binance backtrader
   ```

3. **API Keys** (for live trading only)
   - Set in `001_python_code/config.py`
   - Or use environment variables

---

## 🧪 Test Mode (Safe - Recommended First)

### 1. Dry-Run Mode (No Real Trades)

```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2

# Start dry-run mode (default, safest)
python main_v2.py --mode live

# Custom amount (still simulated)
python main_v2.py --mode live --amount 100000
```

**What happens:**
- ✅ Fetches real market data from Bithumb
- ✅ Runs real strategy analysis
- ✅ Logs trading decisions
- ✅ **Simulates** trades (no real orders)
- ✅ Safe to run 24/7

**Check logs:**
```bash
tail -f ../logs/trading_20251003.log
```

### 2. Backtest Mode (Historical Data)

```bash
# Standard 10-month backtest
python main_v2.py --mode backtest

# With plotting
python main_v2.py --mode backtest --plot

# Custom period
python main_v2.py --mode backtest --months 6 --capital 10000
```

---

## ⚠️ Live Trading Mode (Real Money!)

### Requirements Before Going Live

- [ ] Tested dry-run for at least 24 hours
- [ ] Verified strategy signals are correct
- [ ] Checked all safety features work
- [ ] Set API keys correctly
- [ ] Understand the risks
- [ ] Start with SMALL amounts

### Start Live Trading

```bash
# Step 1: Run with SMALL amount first (e.g., 20,000 KRW)
python main_v2.py --mode live --live --amount 20000

# You will be prompted to confirm:
# Type 'I UNDERSTAND THE RISKS' to continue

# Step 2: Monitor closely
tail -f ../logs/trading_20251003.log

# Step 3: Check positions
cat ../logs/positions_v2.json

# Step 4: Stop anytime with Ctrl+C
```

---

## 📊 Understanding the Strategy

### Entry Conditions (Must have ALL)

1. **Daily Regime: BULLISH**
   - EMA 50 > EMA 200 (Golden Cross)

2. **4H Entry Score: 3+ points**
   - BB Touch (low ≤ BB lower): +1
   - RSI < 30: +1
   - StochRSI bullish cross < 20: +2

3. **Position: 50% initial entry**

### Exit Conditions (Any triggers exit)

1. **Stop-Loss:** Chandelier Exit (Highest High - 3×ATR)
2. **First Target:** BB Middle (exit 50%)
3. **Second Target:** BB Upper (exit 100%)

---

## 📁 Important Files

### Configuration
```
ver2/config_v2.py          # All strategy parameters
```

### Logs
```
logs/trading_YYYYMMDD.log  # Daily trading log
logs/transactions.json     # All transactions
logs/positions_v2.json     # Current positions
```

### Code
```
ver2/main_v2.py            # Entry point
ver2/trading_bot_v2.py     # Main bot logic
ver2/strategy_v2.py        # Strategy logic
ver2/live_executor_v2.py   # Order execution
```

---

## 🛡️ Safety Features (Built-In)

### Default Safety Settings

```python
SAFETY_CONFIG = {
    'dry_run': True,              # ✅ Simulated trades by default
    'max_daily_trades': 5,        # ✅ Max 5 trades per day
    'max_consecutive_losses': 3,  # ✅ Stop after 3 losses
    'max_daily_loss_pct': 3.0,    # ✅ Stop at 3% daily loss
    'emergency_stop': False,      # ✅ Emergency brake
}
```

### How to Activate Emergency Stop

If you need to immediately stop trading:

**Option 1: Ctrl+C**
```bash
# Press Ctrl+C in terminal
# Bot will stop gracefully
```

**Option 2: Config File**
```python
# Edit ver2/config_v2.py
SAFETY_CONFIG = {
    'emergency_stop': True,  # Change to True
}
```

**Option 3: Kill Process**
```bash
# Find process
ps aux | grep main_v2

# Kill it
kill <PID>
```

---

## 🔍 Monitoring

### Real-Time Log Monitoring

```bash
# Follow trading log
tail -f ../logs/trading_20251003.log

# Watch for specific events
tail -f ../logs/trading_20251003.log | grep "Entry\|Exit\|Position"

# Check errors
tail -f ../logs/trading_20251003.log | grep "ERROR"
```

### Check Current Position

```bash
# View position state
cat ../logs/positions_v2.json | python -m json.tool

# Check transaction history
cat ../logs/transactions.json | python -m json.tool | tail -50
```

### Performance Summary

```python
# Run in Python REPL
from ver2.trading_bot_v2 import TradingBotV2

bot = TradingBotV2()
print(bot.generate_daily_report())
```

---

## 🐛 Troubleshooting

### "ModuleNotFoundError"

```bash
# Install missing packages
pip install pandas numpy requests schedule backtrader
```

### "Insufficient data" error

```bash
# Check internet connection
ping api.bithumb.com

# Try with different ticker
python main_v2.py --mode live --symbol ETH
```

### "Authentication failed"

```bash
# Check API keys in config.py
cat ../config.py | grep -A 5 "API_CONFIG"

# For dry-run, API keys not needed
python main_v2.py --mode live  # Works without API keys
```

### Position state corrupted

```bash
# Backup old state
cp ../logs/positions_v2.json ../logs/positions_v2.json.bak

# Delete state file (will recreate)
rm ../logs/positions_v2.json

# Restart bot
python main_v2.py --mode live
```

---

## 📈 Expected Behavior

### Dry-Run Mode

```
============================================================
Bitcoin Multi-Timeframe Trading Strategy v2.0
Mode: LIVE
============================================================

🤖 Initializing Trading Bot V2...
Trading Bot V2 Initialized
Strategy: Multi-Timeframe Stability Strategy
============================================================

============================================================
LIVE TRADING MODE
============================================================
✅ API authentication ready (verified on first trade)

📊 Trading Bot Configuration:
  Strategy: Multi-Timeframe Stability Strategy
  Check Interval: 14400s (4.0h)
  Target Ticker: BTC
  Trade Amount: 50,000 KRW

🔧 MODE: DRY-RUN (No real trades)

⏰ Starting scheduled trading...
  First cycle will run immediately
  Subsequent cycles every 4.0 hours

  Press Ctrl+C to stop

============================================================
Trading Cycle Start: BTC | 2025-10-03 22:30:00
============================================================
📥 Fetching 1d data (250 candles)
📥 Fetching 4h data (200 candles)
✅ Data fetched: 250 daily, 200 4H candles
Market Regime: BULLISH
Entry Score: 2/4 | Details: ['BB touch ✓', 'RSI<30 ✗', 'Stoch cross<20 ✗']
Signal: HOLD | Confidence: 0.00 | Reason: Score too low: 2/4 (need >= 3)
============================================================
```

---

## 💡 Tips for Success

1. **Start Small:** Use minimum amounts (10,000-20,000 KRW) initially
2. **Monitor Actively:** Watch logs for first 24 hours
3. **Understand Signals:** Review why trades are executed
4. **Check Position State:** Ensure position tracking is accurate
5. **Use Dry-Run First:** Test thoroughly before live trading
6. **Set Realistic Expectations:** Strategy may not trade frequently
7. **Have Exit Plan:** Know how to stop bot if needed

---

## 📞 Need Help?

### Debug Mode

Enable verbose logging:
```python
# In ver2/config_v2.py
LOGGING_CONFIG = {
    'log_level': 'DEBUG',  # More detailed logs
}
```

### Check System Status

```bash
# Python version
python --version  # Should be 3.8+

# Packages installed
pip list | grep -E "pandas|numpy|backtrader|schedule"

# Current directory
pwd  # Should be .../005_money/001_python_code/ver2
```

---

## ✅ Ready to Start?

### Recommended First Steps:

1. **Test Backtest Mode**
   ```bash
   python main_v2.py --mode backtest --months 3
   ```

2. **Run Dry-Run for 24H**
   ```bash
   python main_v2.py --mode live
   # Let it run, monitor logs
   ```

3. **Review Results**
   ```bash
   cat ../logs/transactions.json
   ```

4. **Go Live (Carefully!)**
   ```bash
   python main_v2.py --mode live --live --amount 20000
   ```

---

**Remember:**
- 🔧 Dry-run is DEFAULT (safe)
- 🔴 Live requires `--live` flag AND confirmation
- 💰 Start small, scale gradually
- 📊 Monitor constantly when live
- ⏹️ Stop anytime with Ctrl+C

**Good luck trading! 🚀**
