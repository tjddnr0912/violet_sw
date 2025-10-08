# Quick Start: Live Trading Activation

**⚠️ WARNING: REAL MONEY WILL BE USED. READ COMPLETELY BEFORE PROCEEDING.**

---

## For Impatient Users: 3-Step Activation

### Step 1: Set API Keys
```bash
export BITHUMB_CONNECT_KEY="your_connect_key"
export BITHUMB_SECRET_KEY="your_secret_key"
```

### Step 2: Edit Config
Edit `config_v2.py` (lines 197-200):
```python
EXECUTION_CONFIG = {
    'mode': 'live',
    'dry_run': False,  # ⚠️ THIS ENABLES REAL TRADING
    'confirmation_required': True,
}
```

### Step 3: Run Bot
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2
source ../../.venv/bin/activate
python gui_app_v2.py
```

**Look for:** `⚠️ WARNING: REAL TRADING MODE ACTIVE - Real money will be used!`

---

## Safety Checklist (DO NOT SKIP)

- [ ] Have Bithumb API keys with trading permissions
- [ ] Have ≥50,000 KRW in account
- [ ] Understand entry scoring (read `SCORE_MONITORING_GUIDE.md`)
- [ ] Know how to stop bot (`emergency_stop: True` in config)
- [ ] Trading only money you can afford to lose
- [ ] Tested in dry-run mode first

---

## How to Test Without Real Money

### Option 1: No API Keys
```bash
# Don't set API keys
# Bot automatically runs in dry-run
python gui_app_v2.py
```

### Option 2: Dry-Run Flag
Edit `config_v2.py`:
```python
EXECUTION_CONFIG = {
    'mode': 'live',
    'dry_run': True,  # Simulates trades
    ...
}
```

**Look for:** `💚 DRY-RUN` prefix in logs (not `🔴 LIVE`)

---

## How to Stop Trading Immediately

### Method 1: Close GUI
Click X button on GUI window.

### Method 2: Emergency Stop Flag
Edit `config_v2.py`:
```python
SAFETY_CONFIG = {
    'emergency_stop': True,  # Stops all trading
    ...
}
```

### Method 3: Remove API Keys
```bash
unset BITHUMB_CONNECT_KEY
unset BITHUMB_SECRET_KEY
```
Bot falls back to dry-run.

---

## Common Issues

### "API keys not found"
**Fix:** Set environment variables before running bot.

### "LIVE ORDER FAILED: Invalid API key"
**Fix:**
1. Check keys in Bithumb account
2. Verify trading permissions enabled
3. Regenerate keys if expired

### "Score insufficient (1/4), waiting for 2+"
**This is normal.** Bot waits for entry score ≥2.

### Not seeing any signals
**Check:**
1. Market regime (must be BULLISH)
2. Entry score threshold (`min_entry_score: 2` in config)
3. 4H candlestick data availability

---

## What Happens When Entry Signal Triggers

### Dry-Run Mode
```
💚 DRY-RUN: Simulating BUY order...
💚 DRY-RUN ORDER SIMULATED: 0.000500 BTC @ 100,000,000 KRW
```
**No real money used.**

### Live Trading Mode
```
🚨 REAL TRADING: Executing LIVE BUY order via LiveExecutorV2...
✅ LIVE ORDER EXECUTED: Order ID 12345678
   Units: 0.000500 BTC
   Price: 100,000,000 KRW
```
**Real order placed on Bithumb.**

---

## Files You Should Read

1. **LIVE_EXECUTOR_INTEGRATION_REPORT.md** - Complete documentation
2. **SCORE_MONITORING_GUIDE.md** - Entry scoring system
3. **config_v2.py** - All configuration options

---

## Quick Configuration Reference

### Minimum Trade Amount
```python
# config_v2.py, line 215
'trade_amount_krw': 50000,  # Adjust this (min: 10,000)
```

### Entry Threshold
```python
# config_v2.py, line 56
'min_entry_score': 2,  # 0-4, lower = more trades
```

### Safety Limits
```python
# config_v2.py, line 225-227
'max_daily_trades': 5,           # Max trades per day
'max_consecutive_losses': 3,     # Circuit breaker
'max_daily_loss_pct': 3.0,      # Daily loss limit
```

---

## Support

**Full Documentation:** `LIVE_EXECUTOR_INTEGRATION_REPORT.md`

**Test Integration:**
```bash
python test_live_integration.py
```

**Check Logs:**
```bash
tail -f logs/trading_$(date +%Y%m%d).log
```

---

**Last Updated:** 2025-10-07
**Status:** Production Ready ✅
