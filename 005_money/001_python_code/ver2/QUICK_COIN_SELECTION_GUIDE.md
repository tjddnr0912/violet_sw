# Quick Coin Selection Guide

## Overview
The ver2 GUI now remembers your selected coin and displays it dynamically throughout the interface.

---

## How to Change Coins

### Step 1: Open the GUI
```bash
cd 005_money
python3 001_python_code/ver2/gui_app_v2.py
```

### Step 2: Find the Coin Selector
Located in the left panel under "💰 거래 코인 선택" (Trading Coin Selection)

### Step 3: Select Your Coin
Click the dropdown menu to see available coins:
- **BTC** - Bitcoin (Market Leader)
- **ETH** - Ethereum (Smart Contracts)
- **XRP** - Ripple (Fast Payments)
- **SOL** - Solana (High Performance)

### Step 4: Apply the Change
Click the "변경" (Change) button

### Step 5: Confirmation
You'll see a popup asking: "거래 코인을 [OLD] 에서 [NEW](으)로 변경하시겠습니까?"
Click "Yes" to confirm

---

## What Changes When You Select a Coin

### 1. Window Title
```
Before: 🤖 Bitcoin Multi-Timeframe Strategy v2.0 - 💚 DRY-RUN
After:  🤖 Bitcoin Multi-Timeframe Strategy v2.0 - 💚 DRY-RUN - ETH
```

### 2. Holdings Label
```
Before: 보유 BTC: 0.00000000
After:  보유 ETH: 0.00000000
```

### 3. All Charts
All tabs (Real-time Chart, Multi-Chart, Score Monitor) refresh with new coin data

### 4. Status Display
Shows "현재: ETH" in the coin status area

---

## Persistence Feature

### Your Selection is Remembered
When you close and reopen the GUI, your last selected coin is automatically loaded.

**Example:**
```
1. Select SOL, click "변경"
2. Close GUI
3. Open GUI again
4. GUI automatically loads with SOL selected
```

### Where It's Saved
Your preference is saved to:
```
001_python_code/ver2/user_preferences_v2.json
```

**File Format:**
```json
{
  "selected_coin": "SOL",
  "last_updated": "2025-10-08 16:47:29"
}
```

---

## Restrictions

### Cannot Change Coin When:

1. **Bot is Running**
   - Message: "봇 실행 중에는 코인을 변경할 수 없습니다"
   - Action: Stop bot first, then change coin

2. **Position is Open**
   - Message: "포지션 청산 후 코인을 변경할 수 있습니다"
   - Action: Close position first, then change coin

---

## Troubleshooting

### Q: My selection isn't saving
**A:** Check that you have write permissions in `001_python_code/ver2/` directory

### Q: GUI loads with wrong coin
**A:** Check `user_preferences_v2.json` file and ensure it contains a valid coin (BTC, ETH, XRP, or SOL)

### Q: Can I manually edit the preferences file?
**A:** Yes, but ensure the coin symbol is uppercase and valid. Example:
```json
{
  "selected_coin": "XRP",
  "last_updated": "2025-10-08 18:00:00"
}
```

### Q: What happens if I delete the preferences file?
**A:** GUI will use the default coin (BTC) from `config_v2.py`. A new preferences file will be created when you change coins.

---

## Visual Guide

### Before Changing Coin
```
┌─────────────────────────────────────────────┐
│ 💰 거래 코인 선택                           │
│ ┌─────────────────────────────────────────┐ │
│ │ 거래 코인: BTC - Bitcoin (Market Leader)│ │
│ │            [  변경  ]                   │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ Trading Status                              │
│ ┌─────────────────────────────────────────┐ │
│ │ 보유 BTC:    0.00000000                 │ │
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

### After Changing to ETH
```
┌─────────────────────────────────────────────┐
│ 💰 거래 코인 선택                           │
│ ┌─────────────────────────────────────────┐ │
│ │ 거래 코인: ETH - Ethereum (Smart...)    │ │
│ │            [  변경  ]                   │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ Trading Status                              │
│ ┌─────────────────────────────────────────┐ │
│ │ 보유 ETH:    0.00000000                 │ │  ← Changed!
│ └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

---

## Console Log Messages

When you change coins, you'll see these messages in the log:

```
⏳ 코인 변경 중: BTC → ETH
💾 사용자 설정 저장: ETH
✅ Bot symbol updated to ETH
✅ 코인 라벨 업데이트: 보유 ETH
🔄 모든 탭 새로고침 중...
✅ 코인 변경 완료: ETH
```

---

## Advanced: Testing Persistence

### Test Script
Run this to verify persistence is working:
```bash
cd 005_money
python3 001_python_code/ver2/test_gui_coin_label.py
```

### What the Test Shows
1. Loads saved coin from preferences
2. Displays current coin in label
3. Allows you to change coin
4. Shows label updating in real-time
5. Saves preference on change

### Test Procedure
1. Run test script
2. Note initial coin (e.g., BTC)
3. Select different coin (e.g., SOL)
4. Click "변경"
5. Watch label change to "보유 SOL:"
6. Close window
7. Run test script again
8. Verify SOL is loaded automatically

---

## FAQ

**Q: Which coin should I choose?**
A: Depends on your trading strategy. BTC has highest liquidity, ETH has smart contracts ecosystem, XRP has fast transactions, SOL has high performance.

**Q: Can I add more coins?**
A: Yes, edit `AVAILABLE_COINS` in `config_v2.py`, but ensure they're supported on Bithumb.

**Q: Does changing coins affect my trading history?**
A: No, transaction history is stored separately per coin.

**Q: Can I trade multiple coins simultaneously?**
A: No, the bot trades one coin at a time. Change coins only when not in a position.

---

## Summary

✅ **Easy to Use** - Just select from dropdown and click "변경"
✅ **Persists** - Your choice is saved across sessions
✅ **Dynamic** - UI updates everywhere automatically
✅ **Safe** - Cannot change during active trades

Enjoy seamless coin switching!
