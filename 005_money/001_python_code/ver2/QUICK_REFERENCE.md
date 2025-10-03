# Version 2 GUI - Quick Reference Card

## 🚀 Launch GUI

```bash
cd 005_money/001_python_code/ver2
python run_gui_v2.py
```

## 📊 GUI Layout (5 Tabs)

### Tab 1: 거래 현황 (Main Status)
```
┌─────────────────┬─────────────────┐
│ Left Column     │ Right Column    │
├─────────────────┼─────────────────┤
│ 🔍 Market Regime│ 📊 Trading Status│
│   - BULLISH/    │   - BTC         │
│     BEARISH     │   - Price       │
│   - EMA 50/200  │   - Last Action │
├─────────────────┼─────────────────┤
│ 🎯 Entry Score  │ 📉 Chandelier   │
│   - Total (0-4) │   - Stop Price  │
│   - BB Touch +1 │   - Highest High│
│   - RSI <30 +1  │   - Breakeven   │
│   - Stoch X +2  │                 │
├─────────────────┼─────────────────┤
│ 💼 Position     │ 💰 Profit/Loss  │
│   - Phase       │   - Total P&L   │
│   - Entry Price │   - Win Rate    │
│   - Size        │   - Total Trades│
└─────────────────┴─────────────────┘
┌───────────────────────────────────┐
│ 📋 Console Log (Full Width)       │
│   Real-time messages, signals,    │
│   regime changes, exits           │
└───────────────────────────────────┘
```

### Tab 2: 📊 실시간 차트
- Timeframe: 1h / 4h / 1d
- Indicators: EMA, BB, RSI, Stoch RSI, ATR
- Multi-subplot layout
- Refresh button

### Tab 3: 📊 멀티 타임프레임
- Coming Soon (Placeholder)

### Tab 4: 📋 신호 히스토리
- Entry signals with score breakdown
- Exit signals with P&L
- Position events
- Statistics (avg score, win rate)

### Tab 5: 📜 거래 내역
- Transaction log
- Time, Type, Price, Amount, P&L

## 🎯 v2 Strategy Flowchart

```
Daily Data
    ↓
EMA 50 vs EMA 200
    ↓
┌─────────────┬─────────────┐
│ BULLISH     │ BEARISH     │
│ (50 > 200)  │ (50 ≤ 200)  │
├─────────────┼─────────────┤
│ Trade ✓     │ No Entry ✗  │
│ Check 4H    │ Exit Only   │
└─────────────┴─────────────┘
         ↓
    4H Data
         ↓
   Entry Score
         ↓
┌──────────────────────────┐
│ BB Lower Touch:      +1  │
│ RSI < 30:            +1  │
│ Stoch RSI Cross:     +2  │
│─────────────────────────│
│ Total Score:       0-4   │
└──────────────────────────┘
         ↓
    Score ≥ 3?
         ↓
    ┌─────┴─────┐
    │ YES │ NO  │
    ↓     ↓
  ENTRY  WAIT
    ↓
50% Position
    ↓
Position Management
    ↓
┌────────────────────────┐
│ BB Mid  → Scale 50%    │
│           Move to BE   │
├────────────────────────┤
│ BB Upper → Exit 100%   │
├────────────────────────┤
│ Chandelier → Exit Stop │
└────────────────────────┘
```

## 🔑 Key Metrics

### Regime Filter (Daily)
- **Bullish:** EMA50 > EMA200 → Trade allowed
- **Bearish:** EMA50 ≤ EMA200 → No new entries

### Entry Score (4H)
| Component | Condition | Points |
|-----------|-----------|--------|
| BB Touch | Low ≤ BB Lower | +1 |
| RSI Oversold | RSI < 30 | +1 |
| Stoch Cross | K↑D in oversold | +2 |
| **Threshold** | **≥ 3 points** | **Entry** |

### Position Phases
1. **INITIAL_ENTRY** → Just entered (50%)
2. **RISK_FREE_RUNNER** → 1st target hit, at breakeven
3. **NONE** → No position

### Chandelier Exit
```
Stop = Highest High - (ATR × 3.0)
```
- Trails upward only
- Moves to breakeven after 1st target

## 🎨 Color Codes

### Regime Status
- 🟢 **Green:** BULLISH (Trading allowed)
- 🔴 **Red:** BEARISH (No new entries)
- ⚪ **Gray:** NEUTRAL (Insufficient data)

### Entry Score
- 🔵 **Blue:** Score display (0-4)
- **Bold:** Total score

### Profit/Loss
- 🟢 **Green:** Positive P&L
- 🔴 **Red:** Negative P&L

## 📱 Control Panel Buttons

- 🚀 **봇 시작:** Start bot
- ⏹ **봇 정지:** Stop bot
- 🔄 **새로고침:** Refresh chart
- 💾 **내보내기:** Export signals
- 🗑️ **기록 삭제:** Clear history

## 🔔 Status Indicators

### Bot Status
- ⚪ **대기 중:** Standby
- 🟢 **실행 중:** Running
- 🔴 **정지됨:** Stopped

### Trading Mode
- 🟡 **백테스팅 모드:** Simulation (default)
- 🔴 **실제 거래:** Live (not implemented)

## 📋 Console Messages

### Regime Changes
```
Regime changed to BULLISH (EMA50: 95000 > EMA200: 88000)
Regime changed to BEARISH (EMA50: 87000 <= EMA200: 88000)
```

### Entry Signals
```
ENTRY SIGNAL: Score 3/4 - {'bb_touch': 1, 'rsi_oversold': 0, 'stoch_cross': 2}
ENTRY EXECUTED: Price $92000, Stop $89000
  Score: 3/4, Components: BB(+1), Stoch(+2)
```

### Position Management
```
FIRST TARGET HIT: $94000
  Stop moved to BREAKEVEN
STOP TRAILED: $89000 -> $90500
EXIT: FINAL_TARGET at $96000
  P&L: $4000 (+4.35%)
```

## 🛠️ Troubleshooting

### Issue: GUI won't start
```bash
# Check dependencies
python run_gui_v2.py  # Auto-checks

# Manual install
pip install pandas numpy matplotlib requests
```

### Issue: Import errors
```bash
# Use launcher (handles paths)
cd ver2
python run_gui_v2.py
```

### Issue: No data displayed
- Check internet connection
- Verify Bithumb API access
- Click refresh button

### Issue: Chart not updating
- Toggle timeframe selector
- Toggle indicator checkboxes
- Click 🔄 새로고침

## 📊 Signal Quality Guide

### Perfect Setup (4 points) - RARE
```
✓ BB Lower Touch  (+1)
✓ RSI < 30        (+1)
✓ Stoch RSI Cross (+2)
────────────────────────
  Total: 4/4 ⭐⭐⭐⭐
  Frequency: 1-2 per month
```

### Strong Setup (3 points) - TARGET
```
✓ BB Lower Touch  (+1)
✗ RSI = 35        (0)
✓ Stoch RSI Cross (+2)
────────────────────────
  Total: 3/4 ⭐⭐⭐
  Frequency: 3-5 per month
```

### Weak Setup (2 points) - SKIP
```
✓ BB Lower Touch  (+1)
✓ RSI < 30        (+1)
✗ No Stoch Cross  (0)
────────────────────────
  Total: 2/4 ⭐⭐
  Action: WAIT (not enough)
```

## 📈 Expected Performance

### Signal Frequency
- **4-point setups:** 1-2 per month (rare)
- **3-point setups:** 3-5 per month (target)
- **Total opportunities:** 4-7 per month

### Win Rate Targets
- **Overall:** 60-70%
- **Bullish regime only:** 65-75%
- **4-point setups:** 75-85%

### Risk-Reward
- **Initial Stop:** -1.0R (3× ATR below entry)
- **First Target:** +0.5R (BB mid, 50% exit)
- **Final Target:** +1.0R to +2.5R (BB upper, 50% exit)
- **Average:** +0.3R to +0.8R per trade

## 🔗 File Locations

```
ver2/
├── run_gui_v2.py              ← START HERE
├── gui_app_v2.py              (Main GUI)
├── gui_trading_bot_v2.py      (Bot logic)
├── chart_widget_v2.py         (Charts)
├── signal_history_widget_v2.py (Signals)
├── GUI_README.md              (Full guide)
└── QUICK_REFERENCE.md         (This file)
```

## 📞 Quick Help

1. **Can't launch?** → `python run_gui_v2.py` (auto-fixes paths)
2. **No signals?** → Check regime (must be BULLISH)
3. **Want to test?** → Bot runs in simulation mode by default
4. **Need logs?** → Check console panel at bottom
5. **Export data?** → Tab 4 → 💾 내보내기 button

---

**Version:** 2.0
**Last Updated:** 2025-10-03
**Print this card and keep it handy!** 📌
