# Ver3 GUI Quick Start Guide

## What is Ver3?

Ver3 is the **Portfolio Multi-Coin Strategy** that monitors and trades 2-3 cryptocurrencies simultaneously with intelligent portfolio-level risk management.

**Key Features:**
- Monitor BTC, ETH, XRP (and SOL) at the same time
- Max 2 positions open at any time
- Highest-scoring coin gets priority for entry
- Each coin analyzed using Ver2 strategy
- 15-minute analysis cycles

---

## Launch Ver3 GUI

### Option 1: Simple Python Command (Recommended)
```bash
cd 005_money
python run_gui.py --version ver3
```

### Option 2: Direct Script
```bash
cd 005_money
python 003_Execution_script/run_gui.py --version ver3
```

### Option 3: Bash Script
```bash
cd 005_money
./003_Execution_script/run_gui.sh --version ver3
```

---

## First Time Setup

When you launch Ver3 GUI for the first time:

1. **Startup Screen** appears with Ver3 features
2. Click **"🚀 GUI Start"** to proceed
3. Main GUI window opens with 4 tabs

---

## GUI Overview

### Tab 1: Portfolio Overview (Main Dashboard)

**Portfolio Overview Table:**
- Shows all monitored coins (BTC, ETH, XRP by default)
- Columns: Coin | Status | Entry Score | Position | P&L | Action
- Green = Bullish, Red = Bearish, Gray = Neutral
- Yellow background = Position open

**Summary Statistics:**
- Top right: "Positions: 0/2 | Total P&L: +0 KRW | Risk: 0%"

**Portfolio Details (3 panels below table):**
1. **Portfolio Statistics:** Total positions, P&L, cycle count
2. **Recent Decisions:** Latest entry/exit actions
3. **Active Positions:** Open position details with P&L

### Tab 2: Coin Selection

**Coin Selector:**
- Checkboxes for BTC, ETH, XRP, SOL
- Default: BTC, ETH, XRP (checked)
- Min 1, Max 4 coins
- "Apply Changes" button (requires bot stop)
- "Reset to Default" button

**Info Panel:**
- Ver3 strategy explanation
- How portfolio management works

### Tab 3: Logs

**Log Display:**
- Real-time log messages
- Color-coded by coin (BTC=Yellow, ETH=Blue, XRP=Green)
- Color-coded by level (ERROR=Red, WARNING=Orange, INFO=Blue)
- Filter dropdown: ALL | BTC | ETH | XRP | SOL
- "Clear Logs" button

### Tab 4: Transaction History

**Transaction Table:**
- Columns: Timestamp | Coin | Action | Price | Amount | P&L
- Last 50 transactions shown
- Auto-updates as trades execute

---

## Control Panel (Top Bar)

**Buttons:**
- **▶️ Start Bot** - Starts trading bot (with confirmation)
- **⏹️ Stop Bot** - Gracefully stops bot
- **🚨 Emergency Stop** - Immediate halt (keeps positions)

**Indicators:**
- **🔒 Dry-run Mode** - Checkbox (enable for safe testing)
- **Status** - 🟢 Running | ⚪ Stopped | 🔴 Emergency
- **Mode** - DRY-RUN MODE (SAFE) | LIVE TRADING

---

## How to Use

### Step 1: Select Coins (Optional)

1. Go to **Tab 2: Coin Selection**
2. Check/uncheck coins you want to monitor
3. Click **"Apply Changes"**
4. Confirm the dialog

**Default coins:** BTC, ETH, XRP (good starting point)

### Step 2: Enable Dry-Run Mode (Recommended)

1. In Control Panel, check **"🔒 Dry-run Mode (Safe)"**
2. This prevents real trades while testing

### Step 3: Start Bot

1. Click **"▶️ Start Bot"**
2. Confirm dialog: "Start bot in DRY-RUN mode?"
3. Status changes to **"🟢 Bot Running"**
4. Bot begins analyzing coins every 15 minutes

### Step 4: Monitor Portfolio

**Watch Tab 1: Portfolio Overview**
- Table updates every 5 seconds
- Check entry scores (0-4) for each coin
- Monitor positions and P&L
- Review recent decisions

**Watch Tab 3: Logs**
- See real-time analysis results
- Each cycle logs: Coin | Regime | Score | Action
- Example: `[BTC] BULLISH | Score: 3/4 | Action: BUY`

### Step 5: Stop Bot (When Done)

1. Click **"⏹️ Stop Bot"**
2. Confirm dialog
3. Bot stops gracefully
4. Status changes to **"⚪ Bot Stopped"**

---

## Understanding the Bot's Behavior

### Analysis Cycle (Every 15 Minutes)

1. **Parallel Analysis:**
   - All selected coins analyzed simultaneously
   - Each coin gets entry score (0-4) and market regime

2. **Portfolio Decision:**
   - Count current positions
   - If positions < 2, consider entry signals
   - Prioritize by score (highest first)
   - If score tied, use coin rank (BTC > ETH > XRP > SOL)

3. **Execution:**
   - Enter position if score high enough (≥3)
   - Exit position if exit signal triggered
   - Log all decisions and results

### Entry Scoring (Per Coin)

**Ver2 Strategy Applied:**
- Daily EMA regime filter (bullish/bearish/neutral)
- 4H score-based entry (0-4 points):
  - +1: BB lower band touch
  - +1: RSI oversold (< 30)
  - +2: Stochastic cross below 20
- Only enters on bullish regime + score ≥ 3

### Portfolio Limits

- **Max Positions:** 2 (portfolio-wide)
- **Max Per Coin:** 1 (can't double-up on same coin)
- **Entry Priority:** Highest score first
- **Risk Limit:** 6% total portfolio risk

---

## Example Scenario

**Situation:**
- Selected coins: BTC, ETH, XRP
- Current positions: 0

**Cycle 1 (10:00 AM):**
```
Analysis Results:
  [BTC] BULLISH | Score: 4/4 | Action: BUY
  [ETH] BULLISH | Score: 3/4 | Action: BUY
  [XRP] NEUTRAL | Score: 1/4 | Action: HOLD

Portfolio Decision:
  - Positions: 0/2 → Can enter 2 coins
  - Priority: BTC (score 4) > ETH (score 3) > XRP (score 1)
  - Decision: Enter BTC, Enter ETH

Execution:
  ✅ BTC position opened @ 50,000,000 KRW
  ✅ ETH position opened @ 3,500,000 KRW
```

**Cycle 2 (10:15 AM):**
```
Analysis Results:
  [BTC] BULLISH | Score: 2/4 | Action: HOLD (position open)
  [ETH] BULLISH | Score: 3/4 | Action: HOLD (position open)
  [XRP] BULLISH | Score: 4/4 | Action: BUY

Portfolio Decision:
  - Positions: 2/2 → Limit reached
  - Decision: Hold BTC, Hold ETH, Skip XRP (limit)

Execution:
  ⏸️ XRP skipped (portfolio limit reached)
```

**Cycle 3 (10:30 AM):**
```
Analysis Results:
  [BTC] NEUTRAL | Score: 0/4 | Action: SELL (exit signal)
  [ETH] BULLISH | Score: 3/4 | Action: HOLD
  [XRP] BULLISH | Score: 4/4 | Action: BUY

Portfolio Decision:
  - Exit BTC (exit signal)
  - Hold ETH
  - Positions: 1/2 → Can enter 1 more
  - Decision: Exit BTC, Enter XRP

Execution:
  ✅ BTC position closed @ 50,200,000 KRW | P&L: +200,000 KRW
  ✅ XRP position opened @ 800 KRW
```

---

## Tips for Success

### 1. Start with Dry-Run
Always test new strategies in dry-run mode first:
- Check **"🔒 Dry-run Mode"** before starting
- Run for a few days to verify behavior
- Review logs and decisions

### 2. Choose Liquid Coins
Default selection (BTC, ETH, XRP) recommended:
- High liquidity (easy to enter/exit)
- Lower slippage
- Better price discovery

### 3. Monitor Regularly
Check GUI periodically:
- Watch entry scores fluctuate
- Verify positions opening/closing as expected
- Review P&L in real-time

### 4. Understand Limitations
- Coin changes require bot restart
- Max 2 positions at any time
- 15-minute analysis interval (not real-time tick data)

### 5. Risk Management
Ver3 has built-in safeguards:
- 6% max portfolio risk
- Stop-loss on every position
- Consecutive loss limits
- Daily loss caps

---

## Troubleshooting

### GUI Won't Launch

**Error: "backtrader not found"**
```bash
# Install dependencies
cd 005_money
source .venv/bin/activate  # if using venv
pip install -r requirements.txt
```

**Error: "Ver3 module not found"**
```bash
# Verify you're in correct directory
pwd  # Should end with /005_money
ls 001_python_code/ver3/  # Should show ver3 files
```

### Bot Won't Start

**Check:**
1. Is dry-run mode enabled? (Safer for testing)
2. Are dependencies installed?
3. Check logs tab for error messages

### No Trades Executing

**Possible reasons:**
1. Entry scores too low (need ≥3)
2. Market regime not bullish
3. Portfolio limit reached (2 positions)
4. Dry-run mode enabled (no real trades)

### Coin Selection Not Applying

**Remember:**
1. Bot must be stopped first
2. Click "Apply Changes" after selecting
3. Restart bot to use new coins
4. Preferences saved automatically

---

## Comparison with Ver1 and Ver2

| Feature | Ver1 | Ver2 | Ver3 |
|---------|------|------|------|
| **Coins** | Single | Single | Multi (2-3) |
| **Positions** | 1 | 1 | Max 2 |
| **Strategy** | 8-Indicator | Multi-Timeframe | Portfolio + Ver2 |
| **Analysis** | 1h intervals | Daily + 4H | Parallel 15min |
| **Risk Mgmt** | Per-trade | Per-trade | Portfolio-level |
| **GUI Tabs** | 5 | 6 | 4 |
| **Best For** | Simple trading | Single coin advanced | Multi-coin portfolio |

**When to use Ver3:**
- Want to trade multiple coins simultaneously
- Need portfolio-level risk management
- Prefer diversification over concentration
- Comfortable with parallel analysis

---

## Advanced Features

### User Preferences (Auto-Saved)

File: `001_python_code/ver3/user_preferences_v3.json`

Automatically saves:
- Selected coins
- Window position (future)
- Last used settings (future)

### Transaction History Export (Future)

Currently stored in: `logs/transactions.json`

Future feature: Export to CSV from GUI

### Performance Metrics (Future)

Coming in v3.1:
- Sharpe ratio
- Max drawdown
- Win rate per coin
- Correlation matrix

---

## Next Steps

**After Testing in Dry-Run:**

1. **Review Performance**
   - Check transaction history
   - Analyze P&L by coin
   - Review decision logs

2. **Adjust Settings (if needed)**
   - Change coin selection
   - Modify risk limits in `config_v3.py`
   - Tune entry score thresholds

3. **Go Live (Carefully)**
   - Uncheck dry-run mode
   - Start with small amounts
   - Monitor closely for first few cycles
   - Keep emergency stop accessible

**Safety First:**
- Start small
- Use stop-losses
- Never risk more than you can afford to lose
- Monitor regularly

---

## Support and Documentation

**Main Documentation:**
- `GUI_IMPLEMENTATION_SUMMARY.md` - Complete implementation details
- `ver3/README.md` - Ver3 strategy overview
- `ver3/config_v3.py` - Configuration reference

**Logs Location:**
- `logs/ver3_*.log` - Daily log files
- `logs/transactions.json` - Trade history

**Community:**
- Check existing Ver2 GUI for similar features
- Refer to CLAUDE.md for project structure

---

**Ready to start? Run:** `python run_gui.py --version ver3`

**Happy Trading! 🚀**
