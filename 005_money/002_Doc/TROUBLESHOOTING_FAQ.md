# Troubleshooting & FAQ Guide

**Project**: Bithumb Cryptocurrency Trading Bot
**Version**: 2.0 (Elite Strategy)
**Last Updated**: 2025-10-02

---

## Quick Issue Resolution

Use this guide to quickly diagnose and fix common problems.

---

## Table of Contents

1. [Installation & Setup Issues](#installation--setup-issues)
2. [API & Connection Problems](#api--connection-problems)
3. [Trading Logic Issues](#trading-logic-issues)
4. [GUI Problems](#gui-problems)
5. [Performance & Resource Issues](#performance--resource-issues)
6. [Configuration Errors](#configuration-errors)
7. [Logging & Debugging](#logging--debugging)
8. [Frequently Asked Questions](#frequently-asked-questions)

---

## Installation & Setup Issues

### ModuleNotFoundError: No module named 'pandas' (or other packages)

**Symptoms**:
```
ModuleNotFoundError: No module named 'pandas'
ModuleNotFoundError: No module named 'requests'
```

**Cause**: Dependencies not installed in current environment

**Solution**:
```bash
# 1. Verify you're in virtual environment
which python
# Should show: .venv/bin/python

# 2. If not, activate it
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify installation
pip list | grep pandas
pip list | grep requests
```

**Still not working?**
```bash
# Create fresh virtual environment
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

### ImportError: No module named 'tkinter'

**Symptoms**:
```
ImportError: No module named 'tkinter'
ModuleNotFoundError: No module named '_tkinter'
```

**Cause**: Tkinter not included with Python installation

**Solution**:

**macOS**:
```bash
# Tkinter comes with Python from python.org
# If using Homebrew Python, install tcl-tk
brew install python-tk@3.9  # Match your Python version
```

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install python3-tk
```

**Windows**:
- Tkinter should be included by default
- If missing, reinstall Python from python.org and check "tcl/tk" option

**Verify**:
```bash
python -c "import tkinter; print('Tkinter OK')"
```

---

### Permission Denied: ./run.sh

**Symptoms**:
```
-bash: ./run.sh: Permission denied
```

**Cause**: Script not marked as executable

**Solution**:
```bash
chmod +x run.sh run_gui.sh gui
./run.sh  # Should work now
```

---

### pybithumb not found

**Symptoms**:
```
ModuleNotFoundError: No module named 'pybithumb'
```

**Cause**: pybithumb library not cloned/installed

**Solution**:
```bash
cd 005_money

# Auto-clone (preferred)
./run.sh  # Script will clone pybithumb automatically

# Manual clone
git clone --depth 1 https://github.com/sharebook-kr/pybithumb.git

# Verify
ls pybithumb/  # Should show files
```

---

## API & Connection Problems

### Bad Request (Auth Data) - API Authentication Failed

**Symptoms**:
```
API Error: Bad Request.(Auth Data)
401 Unauthorized
```

**Cause**: Invalid or missing API keys

**Solution**:

**Step 1**: Verify API keys are set
```bash
# Check environment variables
echo $BITHUMB_CONNECT_KEY
echo $BITHUMB_SECRET_KEY

# Check .env file
cat .env
```

**Step 2**: Regenerate API keys
1. Go to https://www.bithumb.com/mypage/api
2. Delete old API key
3. Create new key with permissions:
   - ✅ Asset inquiry (자산 조회)
   - ⚠️ Trading (거래) - only if live trading
   - ❌ Withdrawal (출금) - NEVER enable
4. Copy new Connect Key and Secret Key

**Step 3**: Update configuration
```bash
# Edit .env file
nano .env

# Add keys (no quotes, no spaces)
BITHUMB_CONNECT_KEY=your_actual_connect_key_here
BITHUMB_SECRET_KEY=your_actual_secret_key_here

# Save and restart bot
```

**Workaround**: Use dry-run mode (no API keys needed)
```bash
python main.py --dry-run
```

---

### Connection Error: API Request Failed

**Symptoms**:
```
ConnectionError: [Errno 8] nodename nor servname provided
requests.exceptions.ConnectionError
```

**Cause**: Network issues or Bithumb API down

**Solution**:

**Step 1**: Check internet connection
```bash
ping api.bithumb.com
```

**Step 2**: Check Bithumb API status
- Visit https://www.bithumb.com/
- Check Twitter/Telegram for outage announcements

**Step 3**: Check firewall/VPN
```bash
# Test API manually
curl https://api.bithumb.com/public/ticker/BTC_KRW
```

**Step 4**: Use retry logic (already implemented in bot)
- Bot will automatically retry failed requests
- Check logs for retry attempts

**Temporary workaround**: Increase check interval
```python
# config.py
SCHEDULE_CONFIG = {
    'check_interval_minutes': 30,  # Increase from 15
}
```

---

### Rate Limiting: Too Many Requests

**Symptoms**:
```
429 Too Many Requests
Rate limit exceeded
```

**Cause**: Too frequent API calls

**Solution**:

**Step 1**: Increase check interval
```python
# config.py
SCHEDULE_CONFIG = {
    'check_interval_minutes': 30,  # Or higher
}
```

**Step 2**: Reduce API calls in code
- Bot is already optimized (1 call per cycle)
- Avoid manual refresh spam in GUI

**Step 3**: Wait and retry
- Rate limits reset after time period (usually 1 minute)

---

## Trading Logic Issues

### Bot Not Trading Despite Good Signals

**Symptoms**:
- Bot shows BUY/SELL signals but doesn't execute
- "Decision: HOLD" in logs despite indicators pointing to trade

**Diagnosis**:

**Step 1**: Check safety limits
```bash
grep "Daily trade limit" logs/trading_*.log
grep "Consecutive losses" logs/trading_*.log
```

**Possible causes**:
1. **Daily trade limit reached**
   ```python
   # config.py - Increase limit
   SAFETY_CONFIG = {
       'max_daily_trades': 20,  # From 10
   }
   ```

2. **Consecutive loss limit**
   ```python
   STRATEGY_CONFIG = {
       'max_consecutive_losses': 5,  # From 3
   }
   ```

3. **Confidence too low**
   ```bash
   grep "Confidence:" logs/trading_*.log | tail
   # If confidence < 0.6, reduce threshold
   ```
   ```python
   STRATEGY_CONFIG = {
       'confidence_threshold': 0.5,  # From 0.6
   }
   ```

4. **Signal too weak**
   ```python
   STRATEGY_CONFIG = {
       'signal_threshold': 0.4,  # From 0.5 (for buy/sell)
   }
   ```

5. **Emergency stop enabled**
   ```python
   SAFETY_CONFIG = {
       'emergency_stop': False,  # Should be False
   }
   ```

**Step 2**: Check logs for exact reason
```bash
tail -50 logs/trading_$(date +%Y%m%d).log | grep -A 5 "Decision:"
```

---

### Too Many False Signals / Frequent Losses

**Symptoms**:
- Bot trades frequently but loses money
- Low win rate (<40%)

**Solution**:

**Step 1**: Increase quality filters
```python
# config.py
STRATEGY_CONFIG = {
    'confidence_threshold': 0.7,  # From 0.6 (higher bar)
    'signal_threshold': 0.6,      # From 0.5 (stronger signals only)
}
```

**Step 2**: Switch to higher timeframe
```python
STRATEGY_CONFIG = {
    'candlestick_interval': '6h',  # From 1h (fewer but better signals)
}
```

**Step 3**: Add volume filter
```python
'signal_weights': {
    'macd': 0.30,
    'ma': 0.20,
    'rsi': 0.20,
    'bb': 0.10,
    'volume': 0.20  # Increased from 0.10
}
```

**Step 4**: Reduce trade frequency
```python
SAFETY_CONFIG = {
    'max_daily_trades': 3,  # From 10 (more selective)
}
```

---

### Missing Good Opportunities

**Symptoms**:
- Bot rarely trades
- Obvious moves not captured

**Solution**:

**Step 1**: Lower entry thresholds
```python
STRATEGY_CONFIG = {
    'confidence_threshold': 0.5,  # From 0.6
    'signal_threshold': 0.4,      # From 0.5
}
```

**Step 2**: Switch to lower timeframe
```python
STRATEGY_CONFIG = {
    'candlestick_interval': '1h',  # From 6h (more opportunities)
}
```

**Step 3**: Increase trade limit
```python
SAFETY_CONFIG = {
    'max_daily_trades': 20,  # From 10
}
```

**Step 4**: Check indicator parameters
```bash
# May be too slow-reacting
STRATEGY_CONFIG = {
    'rsi_period': 9,  # From 14 (faster)
    'macd_fast': 6,   # From 8 (faster)
}
```

---

### Getting Stopped Out Frequently

**Symptoms**:
- Many trades hit stop-loss
- Win rate OK but stops too tight

**Solution**:

**Step 1**: Widen stops
```python
STRATEGY_CONFIG = {
    'atr_stop_multiplier': 3.0,  # From 2.0 (wider stops)
}
```

**Step 2**: Check volatility
```bash
grep "ATR%" logs/trading_*.log | tail
# If ATR% > 3%, market is very volatile
```

**Step 3**: Reduce position size in high volatility
```python
STRATEGY_CONFIG = {
    'position_risk_pct': 0.5,  # From 1.0 (half the risk)
}
```

**Step 4**: Avoid trading in high volatility
```python
# Add logic to skip trades when ATR% > threshold
if atr_pct > 0.03:  # 3%
    return 'HOLD'  # Skip trade
```

---

## GUI Problems

### GUI Window Doesn't Open / Crashes Immediately

**Symptoms**:
- `python gui_app.py` shows no window
- Window flashes and closes
- Tkinter error messages

**Solution**:

**Step 1**: Check Tkinter installation
```bash
python -c "import tkinter; tkinter.Tk().destroy(); print('Tkinter OK')"
```

**Step 2**: Run with error output
```bash
python gui_app.py 2>&1 | tee gui_error.log
# Check gui_error.log for errors
```

**Step 3**: Try simple Tkinter test
```bash
python -c "import tkinter; root = tkinter.Tk(); root.mainloop()"
# Should show empty window
```

**Step 4**: Check display (for remote/SSH)
```bash
# If running over SSH, enable X11 forwarding
ssh -X user@host
# Or use CLI mode instead
python main.py
```

---

### Chart Not Displaying / Blank Chart Area

**Symptoms**:
- Chart tab shows white/blank area
- No candlesticks visible

**Solution**:

**Step 1**: Check matplotlib backend
```python
# In chart_widget.py, verify backend
import matplotlib
print(matplotlib.get_backend())  # Should be 'TkAgg'
```

**Step 2**: Manually refresh chart
- Click "🔄 차트 새로고침" button
- Wait 5-10 seconds

**Step 3**: Check data availability
```bash
python -c "from bithumb_api import get_candlestick; print(get_candlestick('BTC', '1h').shape)"
# Should show: (200, 5) or similar
```

**Step 4**: Restart GUI
```bash
# Stop bot (⏹ 봇 정지)
# Close GUI
# Reopen
python gui_app.py
```

---

### Chart X-Axis Compressed / Labels Overlapping

**Symptoms**:
- Chart x-axis labels overlap
- Candlesticks squished together

**Status**: **Fixed in v3.0** (2025-10-02)

**If still occurring**:
```bash
# Verify you have latest version
git pull
# Check chart_widget.py version
head -3 chart_widget.py
# Should show: v3.0 - Clean Rebuild
```

**Workaround** (older versions):
- Limit displayed candles to 200
- Increase figure DPI
- Rotate x-axis labels

---

### LEDs Not Blinking / Stuck on One Color

**Symptoms**:
- Indicator LEDs don't update
- All LEDs gray
- No blinking effect

**Solution**:

**Step 1**: Verify bot is running
- Check top-left: Should show "실행 중"
- Check log panel: Should see periodic updates

**Step 2**: Restart bot cycle
```bash
# In GUI:
1. Click "⏹ 봇 정지"
2. Wait 2 seconds
3. Click "🚀 봇 시작"
```

**Step 3**: Check check interval
```python
# If interval too long, LEDs update slowly
SCHEDULE_CONFIG = {
    'check_interval_minutes': 5,  # From 15 for faster updates
}
```

**Step 4**: Force update
```python
# In GUI, click "📝 설정 적용" to trigger refresh
```

---

## Performance & Resource Issues

### Bot Using Too Much Memory

**Symptoms**:
- High RAM usage (>500MB)
- System slowing down

**Solution**:

**Step 1**: Check analysis period
```python
# Reduce data loaded
STRATEGY_CONFIG = {
    'analysis_period': 50,  # From 100 (load less data)
}
```

**Step 2**: Clear old logs
```bash
# Delete old log files
rm logs/trading_202409*.log  # Keep only recent
```

**Step 3**: Disable unused features
```python
# If not using GUI, run CLI only
python main.py  # Instead of gui_app.py
```

**Step 4**: Restart bot periodically
```bash
# Set up cron job to restart daily
0 0 * * * cd /path/to/005_money && python main.py
```

---

### GUI Slow / Laggy

**Symptoms**:
- GUI freezes
- Slow response to clicks

**Solution**:

**Step 1**: Reduce update frequency
```python
# In gui_app.py
def update_gui(self):
    # Change from 100ms to 500ms
    self.root.after(500, self.update_gui)  # From 100
```

**Step 2**: Disable chart auto-refresh
- Use manual refresh button instead of auto-update
- Reduces computational load

**Step 3**: Close other programs
- Trading bot + chart can be CPU-intensive
- Close unnecessary applications

---

### High CPU Usage

**Symptoms**:
- CPU at 100%
- Fan running loud

**Solution**:

**Step 1**: Check if in infinite loop
```bash
# Monitor CPU
top -p $(pgrep -f gui_app.py)
# If constantly high, there's an issue
```

**Step 2**: Increase update intervals
```python
# Reduce frequency of calculations
SCHEDULE_CONFIG = {
    'check_interval_minutes': 30,  # From 15
}
```

**Step 3**: Profile code
```python
# Add timing
import time
start = time.time()
# ... code ...
print(f"Took {time.time() - start:.2f}s")
```

**Step 4**: Optimize indicator calculations
- Already using pandas vectorization (efficient)
- If adding custom indicators, avoid loops

---

## Configuration Errors

### ValueError: signal_weights must sum to 1.0

**Symptoms**:
```
ValueError: signal_weights must sum to 1.0, got 0.95
```

**Cause**: Incorrect weight distribution

**Solution**:
```python
# Ensure weights add up to exactly 1.0
'signal_weights': {
    'macd': 0.35,
    'ma': 0.25,
    'rsi': 0.20,
    'bb': 0.10,
    'volume': 0.10
}
# Sum: 0.35 + 0.25 + 0.20 + 0.10 + 0.10 = 1.00 ✓
```

**Quick fix**:
```python
# Use fractions that add to 1.0
# 4 indicators: 0.25 each = 1.0
# 5 indicators: 0.20 each = 1.0
# 8 indicators: 0.125 each = 1.0
```

---

### Invalid Interval Error

**Symptoms**:
```
ValueError: Invalid interval '2h'
KeyError: '2h'
```

**Cause**: Unsupported candlestick interval

**Solution**:
```python
# Use only supported intervals
'candlestick_interval': '1h',  # ✓ Valid

# Supported: '1m', '3m', '5m', '10m', '30m', '1h', '6h', '12h', '24h'
# NOT supported: '2h', '4h', '8h'
```

---

### Config File Not Found

**Symptoms**:
```
FileNotFoundError: [Errno 2] No such file or directory: 'config.py'
```

**Cause**: Running bot from wrong directory

**Solution**:
```bash
# Always run from 005_money directory
cd /path/to/005_money
python main.py  # ✓ Correct

# NOT from parent directory
cd /path/to
python 005_money/main.py  # ✗ Wrong (can't find config)
```

---

## Logging & Debugging

### Log File Empty / Not Created

**Symptoms**:
- `logs/` directory empty
- No trading_YYYYMMDD.log files

**Solution**:

**Step 1**: Check logging config
```python
# config.py
LOGGING_CONFIG = {
    'enable_file_log': True,  # Should be True
    'log_dir': 'logs',
}
```

**Step 2**: Create logs directory
```bash
mkdir -p logs
chmod 755 logs
```

**Step 3**: Check permissions
```bash
ls -ld logs/
# Should show: drwxr-xr-x
```

**Step 4**: Verify logger initialization
```bash
python -c "from logger import TradingLogger; logger = TradingLogger(); logger.info('Test'); print('Logger OK')"
```

---

### Can't Find Specific Log Entry

**Symptoms**:
- Need to find when a trade happened
- Need to see why a decision was made

**Solution**:

**Search logs**:
```bash
# Find all BUY decisions
grep "Decision: BUY" logs/trading_*.log

# Find trades on specific day
grep "Trade executed" logs/trading_20251001.log

# Find errors
grep -i "error" logs/trading_*.log

# Find specific ticker
grep "BTC" logs/trading_*.log | grep "Decision"

# Get last 100 lines
tail -100 logs/trading_$(date +%Y%m%d).log

# Watch real-time
tail -f logs/trading_$(date +%Y%m%d).log
```

**Check transaction history**:
```bash
# JSON format (detailed)
cat transaction_history.json | jq '.transactions[] | select(.ticker=="BTC")'

# Markdown format (readable)
cat logs/trading_history.md
```

---

### Enable Debug Mode

**For detailed troubleshooting**:

**Step 1**: Enable debug logging
```python
# config.py
LOGGING_CONFIG = {
    'log_level': 'DEBUG',  # From 'INFO'
}
```

**Step 2**: Add debug prints
```python
# In any file
import logging
logger = logging.getLogger(__name__)
logger.debug(f"Variable value: {some_variable}")
```

**Step 3**: Run with verbose output
```bash
python main.py --dry-run 2>&1 | tee debug.log
```

---

## Frequently Asked Questions

### General Questions

#### Q: Is this bot profitable?

**A**: The bot is a **tool**, not a guaranteed profit system. Profitability depends on:
- Market conditions (trending vs sideways)
- Strategy configuration (weights, thresholds)
- Risk management (position sizing, stops)
- Timeframe selection
- User discipline (not overriding signals)

**Always test thoroughly in dry-run mode first.**

---

#### Q: Can I run multiple bots for different coins?

**A**: Current version supports one coin at a time. For multiple coins:

**Option 1**: Run multiple instances
```bash
# Terminal 1
cd 005_money_btc && python main.py

# Terminal 2
cd 005_money_eth && python main.py
```

**Option 2**: Modify code for multi-coin support
- See `portfolio_manager.py` for framework
- Requires development work

---

#### Q: What's the difference between dry-run and live mode?

**A**:

**Dry-Run Mode** (`dry_run: True`):
- No real trades executed
- Simulates trades with current prices
- No money at risk
- Perfect for testing strategies
- API keys not required

**Live Mode** (`dry_run: False`):
- Real trades executed
- Real money at risk
- Requires API keys with trading permission
- Use extreme caution

**Always test in dry-run for 1-2 weeks minimum!**

---

#### Q: How much money do I need to start?

**A**: Minimum requirements:
- **Bithumb minimum order**: 5,000 KRW (~$4 USD)
- **Recommended starting**: 100,000 KRW (~$80 USD)
- **Comfortable amount**: 1,000,000 KRW (~$800 USD)

**Risk management**:
- Only invest what you can afford to lose
- Start with minimum to learn the system
- Increase gradually as you gain confidence

---

#### Q: What timeframe should I use?

**A**: Depends on your trading style:

| Timeframe | Style | Commitment | Signals/Week |
|-----------|-------|------------|--------------|
| 30m | Scalping | High (active monitoring) | 15-30 |
| 1h | Day trading | Medium (check 3-4x/day) | 5-10 |
| 6h | Swing trading | Low (check 1-2x/day) | 1-3 |
| 24h | Position trading | Very low (weekly) | 0-1 |

**Recommendation**: Start with 1h (default) for balance.

---

### Technical Questions

#### Q: Why do indicators have different weights?

**A**: Indicators have different reliability and roles:

- **MACD (0.35)**: Highest weight because it combines trend + momentum
- **MA (0.25)**: High weight for trend confirmation
- **RSI (0.20)**: Medium weight for overbought/oversold filter
- **BB/Volume (0.10 each)**: Lower weights for secondary confirmation

These weights are optimized through backtesting but can be customized.

---

#### Q: What's the difference between confidence and signal strength?

**A**:

**Signal Strength** (-1.0 to +1.0):
- Direction and magnitude of signal
- Positive = bullish, Negative = bearish
- Magnitude = how strong

**Confidence** (0.0 to 1.0):
- How much indicators agree
- 1.0 = all indicators aligned
- 0.5 = indicators mixed/conflicting
- 0.0 = no clear signal

**Both must be high for trade execution.**

---

#### Q: Can I add my own custom indicator?

**A**: Yes! See `DEVELOPER_ONBOARDING.md` for step-by-step guide. Basic steps:

1. Add calculation function to `strategy.py`
2. Integrate into `analyze_market_data()`
3. Add signal generation to `generate_weighted_signals()`
4. Add weight to `config.py`
5. Update GUI if desired

---

#### Q: Why did the bot not trade when I expected it to?

**A**: Common reasons:

1. **Confidence too low** (< 0.6)
2. **Signal too weak** (< 0.5 for buy, > -0.5 for sell)
3. **Daily trade limit reached**
4. **Consecutive loss limit hit**
5. **Emergency stop enabled**
6. **Insufficient balance** (if live)
7. **API error** (check logs)

Check logs for specific reason:
```bash
grep "Decision: HOLD" logs/trading_*.log | tail -5
```

---

#### Q: How does the ATR-based stop loss work?

**A**: ATR (Average True Range) measures volatility:

```
Stop Loss = Entry Price - (ATR × Multiplier)

Example:
Entry: 100,000 KRW
ATR: 1,500 KRW (1.5% volatility)
Multiplier: 2.0

Stop Loss = 100,000 - (1,500 × 2.0) = 97,000 KRW (-3%)
```

**Benefits**:
- Adapts to market volatility
- Wider stops in volatile markets (avoid getting stopped out)
- Tighter stops in calm markets (preserve capital)

---

### Strategy Questions

#### Q: Which strategy preset should I use?

**A**: Depends on market conditions:

**Check ADX first**:
```bash
# In GUI, look at "시장 국면" panel
# Or check logs
grep "ADX:" logs/trading_*.log | tail -1
```

**Then choose**:
- **ADX > 25**: Use "Trend Following"
- **ADX < 20**: Use "Mean Reversion"
- **ADX 20-25**: Use "Balanced Elite" (default)
- **Unsure**: Use "MACD + RSI Filter" (conservative)

---

#### Q: Why is MACD weighted highest (0.35)?

**A**: MACD is the most reliable indicator because:

1. Combines trend direction (like MA)
2. Includes momentum strength (like RSI)
3. Works in both trending and ranging markets
4. Less prone to false signals than individual indicators
5. Widely used and battle-tested by traders

**Other indicators complement MACD but don't replace it.**

---

#### Q: Can I backtest strategies?

**A**: Currently no built-in backtesting. Workarounds:

**Option 1**: Manual historical analysis
```python
# Fetch old data
df = get_candlestick('BTC', '1h')
# Manually apply strategy to historical candles
```

**Option 2**: Dry-run forward testing
- Run bot in dry-run mode for 1-2 weeks
- Track simulated performance
- Adjust strategy
- Repeat

**Option 3**: Implement backtesting module
- Feature request for future development
- Contributions welcome!

---

### Safety & Security Questions

#### Q: Is my API key safe?

**A**: Best practices implemented:

✅ **Good practices**:
- Store in environment variables or `.env` file
- `.env` is in `.gitignore` (not committed to Git)
- Balance inquiry disabled by default
- Only read operations in production bot

⚠️ **Important**:
- NEVER enable "Withdrawal" permission
- Use separate API key for bot (not your main account key)
- Regularly rotate keys
- Start with small amounts

---

#### Q: What if the bot makes a bad trade?

**A**: Risk management protections:

1. **ATR Stop Loss**: Automatically calculated, exit if hit
2. **Daily Loss Limit**: Bot stops if losing > 3% in one day
3. **Consecutive Loss Limit**: Bot stops after 3 losses in a row
4. **Trade Limit**: Maximum trades per day (prevents revenge trading)
5. **Emergency Stop**: Manual override to stop immediately

**You should always monitor the bot and be ready to intervene.**

---

#### Q: Can the bot lose all my money?

**A**: Theoretically yes, but extremely unlikely due to:

1. **Position Sizing**: Only risk 1% per trade (configurable)
2. **Daily Loss Limit**: 3% max loss per day
3. **Stop Losses**: Exit losing trades quickly
4. **Trade Limits**: Can't over-trade

**Example**:
- Account: 1,000,000 KRW
- Risk per trade: 1% = 10,000 KRW
- Max daily loss: 3% = 30,000 KRW
- Worst case day: -30,000 KRW (97% preserved)

**However**: Markets can gap, stops can slip. Never invest more than you can afford to lose.

---

## Emergency Procedures

### Emergency Stop

**When to use**:
- Market crash
- Unexpected bot behavior
- API issues
- Need to stop immediately

**How to stop**:

**GUI**:
1. Click "⏹ 봇 정지" button
2. Close GUI window

**CLI**:
```bash
# Ctrl+C in terminal
^C

# Or kill process
pkill -f main.py
```

**Configuration**:
```python
# config.py - Set emergency stop flag
SAFETY_CONFIG = {
    'emergency_stop': True,  # Stops all trading
}
```

---

### Recover from Crash

**If bot crashed**:

**Step 1**: Check logs
```bash
tail -100 logs/trading_$(date +%Y%m%d).log
```

**Step 2**: Look for error
```bash
grep -i "error" logs/trading_*.log | tail -20
```

**Step 3**: Fix issue (API, config, etc.)

**Step 4**: Restart bot
```bash
# CLI
python main.py

# GUI
python gui_app.py
```

**Step 5**: Verify restart
- Check logs for startup message
- GUI should show "실행 중"
- Monitor for 5-10 minutes

---

### Data Corruption / Reset

**If something is very wrong**:

**Nuclear option - Fresh start**:
```bash
# Backup data
cp -r logs logs_backup
cp transaction_history.json transaction_history_backup.json

# Clean slate
rm -rf .venv
rm logs/trading_*.log
rm transaction_history.json

# Reinstall
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Restart
python main.py --dry-run
```

---

## Getting More Help

**If this guide didn't solve your problem**:

1. **Check other documentation**:
   - `ARCHITECTURE.md` - System design
   - `API_REFERENCE.md` - Code documentation
   - `DEVELOPER_ONBOARDING.md` - Development guide

2. **Search project issues** (if using GitHub):
   ```bash
   # Search closed issues - problem may be solved
   ```

3. **Check logs thoroughly**:
   ```bash
   # Look for ERROR, WARNING, Exception
   grep -E "ERROR|WARNING|Exception" logs/trading_*.log
   ```

4. **Ask for help** (provide):
   - What you're trying to do
   - What happened (with error messages)
   - Relevant log snippets (last 50 lines)
   - Your configuration (without API keys!)
   - Python version, OS
   - Steps you've already tried

---

## Preventive Maintenance

**To avoid issues**:

### Daily
- [ ] Check bot is running (GUI status or logs)
- [ ] Review trades in transaction history
- [ ] Check error count in logs
- [ ] Monitor profit/loss

### Weekly
- [ ] Review strategy performance
- [ ] Check win rate and adjust if needed
- [ ] Clean old logs (keep last 30 days)
- [ ] Update configuration if market regime changed

### Monthly
- [ ] Update bot code (`git pull`)
- [ ] Update dependencies (`pip install --upgrade -r requirements.txt`)
- [ ] Rotate API keys (security)
- [ ] Backup transaction history
- [ ] Review and optimize strategy weights

---

**Document Version**: 1.0
**Last Updated**: 2025-10-02
**Maintained By**: Project Support Team

**Remember**: When in doubt, use dry-run mode!
