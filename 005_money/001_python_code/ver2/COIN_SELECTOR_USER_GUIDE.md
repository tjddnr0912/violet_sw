# Coin Selector - Quick User Guide

## What is This?

The coin selector dropdown allows you to switch between different cryptocurrencies on Bithumb **without restarting the bot**. All charts and data automatically update to the new coin.

## How to Use

### Step 1: Locate the Coin Selector
In **Tab 1 (거래 현황)**, look for the **"💰 거래 코인 선택"** panel:

```
┌─ 💰 거래 코인 선택 ─────────────────┐
│ 거래 코인: [BTC ▼] [변경]           │
│ 현재: BTC                           │
└─────────────────────────────────────┘
```

### Step 2: Select Your Coin

1. Click the dropdown **[BTC ▼]**
2. You'll see:
   - **Top Section**: Popular coins (BTC, ETH, XRP, ADA, SOL, DOGE, DOT, MATIC, LINK, UNI)
   - **Separator**: ─────────
   - **Bottom Section**: All 427 coins in alphabetical order

Example:
```
BTC - Bitcoin
ETH - Ethereum
XRP - Ripple
ADA - Cardano
SOL - Solana
DOGE - Dogecoin
DOT - Polkadot
MATIC - Polygon
LINK - Chainlink
UNI - Uniswap
─────────────
AAVE
ACE
ACH
...
```

### Step 3: Click "변경" (Change)

1. After selecting a coin, click the **"변경"** button
2. You'll see a confirmation dialog:
   ```
   거래 코인을 BTC에서 ETH(으)로 변경하시겠습니까?

   모든 차트와 데이터가 새로고침됩니다.

   [예]  [아니오]
   ```
3. Click **"예"** to confirm

### Step 4: Wait for Refresh

The system will automatically:
- ✓ Update config with new coin
- ✓ Update bot symbol
- ✓ Refresh all price displays
- ✓ Reload all charts (Tab 2 & Tab 3)
- ✓ Clear score monitoring (Tab 4)
- ✓ Clear signal history (Tab 5)
- ✓ Update window title

You'll see progress in the console log:
```
⏳ 코인 변경 중: BTC → ETH
✅ Bot symbol updated to ETH
🔄 모든 탭 새로고침 중...
  - 거래 현황 새로고침
  - 실시간 차트 새로고침
  - 멀티 타임프레임 차트 새로고침
  - 점수 모니터링 초기화
  - 신호 히스토리 초기화
✅ 모든 탭 새로고침 완료
✅ 코인 변경 완료: ETH
```

## Important Restrictions

### ⚠️ Cannot Change While Bot Running
If you try to change coin while bot is running:
```
경고: 봇 실행 중에는 코인을 변경할 수 없습니다.
먼저 봇을 정지하세요.
```

**Solution:** Click **"⏹ 봇 정지"** first

### ⚠️ Cannot Change With Open Position
If you try to change coin while holding a position:
```
경고: 포지션 청산 후 코인을 변경할 수 있습니다.
```

**Solution:** Wait for position to close or manually close it

## What Happens to Data?

### Data That Is CLEARED:
- ❌ **Score Monitoring (Tab 4)**: All previous score checks cleared
- ❌ **Signal History (Tab 5)**: All previous signals cleared

**Reason:** These are coin-specific data. When you switch coins, you start fresh tracking for the new coin.

### Data That Is UPDATED:
- ✓ **Current Price**: Updates to new coin immediately
- ✓ **All Charts**: Reload with new coin's candlestick data
- ✓ **Indicators**: Recalculate for new coin (BB, RSI, Stoch RSI, ATR)
- ✓ **Regime Status**: Shows new coin's EMA 50/200 status
- ✓ **Entry Signals**: Shows new coin's current score

## Quick Tips

### Tip 1: Popular Coins at Top
The 10 most popular coins are always at the top for quick access:
- BTC, ETH, XRP, ADA, SOL, DOGE, DOT, MATIC, LINK, UNI

### Tip 2: Check Window Title
After changing, verify the window title updates:
```
🤖 Bitcoin Multi-Timeframe Strategy v2.0 - 💚 DRY-RUN - ETH
```
The last part shows current coin.

### Tip 3: Use Console Log
Watch the console log (bottom of Tab 1) for detailed progress updates.

### Tip 4: Try Different Coins
Experiment with different coins to see which ones have good entry signals!

## Troubleshooting

### Problem: Dropdown Shows "─────────"
**Cause:** You clicked the separator line
**Solution:** Click an actual coin name above or below the separator

### Problem: Change Failed with Error
**Cause:** Invalid coin or network error
**Solution:**
1. Check console log for error details
2. Try again
3. If persistent, restart GUI

### Problem: Charts Don't Update
**Cause:** Network issue or data unavailable
**Solution:**
1. Check internet connection
2. Try a more popular coin (BTC, ETH)
3. Check console log for errors

### Problem: Old Coin Still Showing
**Cause:** Change was cancelled or failed
**Solution:** Dropdown reverts to previous coin on failure - this is normal

## Example Workflow

### Scenario: Switch from BTC to Ethereum

1. **Stop bot** (if running): Click "⏹ 봇 정지"
2. **Close positions** (if any): Wait for exit or manual close
3. **Open dropdown**: Click **[BTC ▼]**
4. **Select ETH**: Click on "ETH - Ethereum"
5. **Click "변경"**: Confirm in dialog
6. **Wait**: Watch console log for "✅ 코인 변경 완료: ETH"
7. **Verify**:
   - Window title shows "ETH"
   - "현재: ETH" in coin selector panel
   - Charts show ETH data
8. **Restart bot**: Click "🚀 봇 시작" (if desired)

## Summary

The coin selector gives you flexibility to:
- ✓ Trade different cryptocurrencies
- ✓ Compare strategies across coins
- ✓ Respond to market opportunities
- ✓ Test strategies on various assets

All without restarting the application!

---

**Need Help?** Check the console log at the bottom of Tab 1 for detailed error messages and progress updates.
