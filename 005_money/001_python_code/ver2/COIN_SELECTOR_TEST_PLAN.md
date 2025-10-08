# Coin Selector Testing Plan

## Pre-Test Checklist

- [ ] Ensure you're in the project directory: `005_money/`
- [ ] Activate virtual environment (if using one)
- [ ] Verify dependencies installed: `pip install -r requirements.txt`
- [ ] Verify Bithumb API connection (price fetching works)

## Test 1: GUI Loads Correctly

**Objective:** Verify coin selector panel appears and initializes correctly

**Steps:**
1. Run GUI: `python 001_python_code/ver2/gui_app_v2.py` or `python run_gui.py`
2. Navigate to **Tab 1 (거래 현황)**
3. Locate **"💰 거래 코인 선택"** panel

**Expected Results:**
- [ ] Panel appears between "진입 신호 시스템" and "⚙️ 전략 설정"
- [ ] Dropdown shows current coin (default: BTC)
- [ ] "변경" button is visible
- [ ] Status label shows "현재: BTC"
- [ ] No errors in console log

## Test 2: Dropdown Displays All Coins

**Objective:** Verify dropdown shows all 427 coins correctly

**Steps:**
1. Click dropdown **[BTC ▼]**
2. Scroll through list

**Expected Results:**
- [ ] First 10 items are popular coins (BTC, ETH, XRP, ADA, SOL, DOGE, DOT, MATIC, LINK, UNI)
- [ ] Separator "─────────" appears after popular coins
- [ ] Remaining coins appear alphabetically
- [ ] Dropdown is scrollable
- [ ] Total items = 10 popular + 1 separator + 417 others = 428 items

## Test 3: Separator Cannot Be Selected

**Objective:** Verify separator prevents selection

**Steps:**
1. Click dropdown
2. Try to select "─────────"
3. Observe behavior

**Expected Results:**
- [ ] Dropdown reverts to previous coin
- [ ] No error message
- [ ] "현재:" status unchanged

## Test 4: Change Coin (Bot Stopped, No Position)

**Objective:** Verify successful coin change with all tabs updating

**Steps:**
1. Ensure bot is STOPPED (status shows "⚪ 대기 중")
2. Ensure NO position open
3. Select **ETH** from dropdown
4. Click **"변경"** button
5. Confirm in dialog
6. Wait for refresh to complete

**Expected Results:**
- [ ] Confirmation dialog appears
- [ ] Console shows: "⏳ 코인 변경 중: BTC → ETH"
- [ ] Console shows: "✅ Bot symbol updated to ETH"
- [ ] Console shows: "🔄 모든 탭 새로고침 중..."
- [ ] Console shows: "✅ 모든 탭 새로고침 완료"
- [ ] Success message dialog appears
- [ ] Dropdown shows ETH
- [ ] Status shows "현재: ETH"
- [ ] Window title includes "- ETH"
- [ ] "거래 코인:" in status panel shows ETH
- [ ] Current price updates to ETH price

**Tab Verifications:**
- [ ] **Tab 1**: Current price shows ETH price (different from BTC)
- [ ] **Tab 2 (실시간 차트)**: Chart title shows ETH, candlesticks reload
- [ ] **Tab 3 (멀티 타임프레임)**: All 4 charts (24h, 12h, 4h, 1h) show ETH data
- [ ] **Tab 4 (점수 모니터링)**: Table cleared (no previous BTC scores)
- [ ] **Tab 5 (신호 히스토리)**: Table cleared (no previous BTC signals)

## Test 5: Blocked Change (Bot Running)

**Objective:** Verify coin change is blocked when bot is running

**Steps:**
1. Click **"🚀 봇 시작"** (status shows "🟢 실행 중")
2. Select different coin from dropdown (e.g., XRP)
3. Click **"변경"** button

**Expected Results:**
- [ ] Warning dialog appears: "봇 실행 중에는 코인을 변경할 수 없습니다"
- [ ] Dropdown reverts to current coin (ETH)
- [ ] No coin change occurs
- [ ] Bot continues running normally

## Test 6: Blocked Change (Position Open)

**Objective:** Verify coin change is blocked when position is open

**Steps:**
1. Stop bot if running
2. Manually set `bot.position` to simulate open position (or wait for actual entry)
3. Select different coin from dropdown
4. Click **"변경"** button

**Expected Results:**
- [ ] Warning dialog appears: "포지션 청산 후 코인을 변경할 수 있습니다"
- [ ] Dropdown reverts to current coin
- [ ] No coin change occurs

## Test 7: Invalid Coin Selection

**Objective:** Verify validation prevents invalid coins

**Steps:**
1. Temporarily modify dropdown to include "INVALID" coin
2. Select "INVALID"
3. Click **"변경"**

**Expected Results:**
- [ ] Error dialog appears with validation message
- [ ] Dropdown reverts to previous coin
- [ ] No coin change occurs

## Test 8: Cancel Confirmation Dialog

**Objective:** Verify coin change can be cancelled

**Steps:**
1. Select different coin from dropdown (e.g., XRP)
2. Click **"변경"**
3. Click **"아니오"** in confirmation dialog

**Expected Results:**
- [ ] Dialog closes
- [ ] No coin change occurs
- [ ] Dropdown reverts to current coin
- [ ] No errors in console

## Test 9: Multiple Coin Changes

**Objective:** Verify multiple sequential coin changes work correctly

**Steps:**
1. Change from BTC → ETH (verify successful)
2. Change from ETH → XRP (verify successful)
3. Change from XRP → ADA (verify successful)
4. Change from ADA → BTC (verify successful)

**Expected Results:**
For each change:
- [ ] All tabs update correctly
- [ ] Price updates to new coin
- [ ] Charts reload with new data
- [ ] Score monitoring and signal history clear
- [ ] No memory leaks or performance degradation

## Test 10: Chart Data Refresh

**Objective:** Verify chart widgets correctly fetch new coin data

**Steps:**
1. Change coin from BTC → ETH
2. Navigate to **Tab 2 (실시간 차트)**
3. Observe chart

**Expected Results:**
- [ ] Chart shows ETH candlesticks (not BTC)
- [ ] Chart title includes "ETH"
- [ ] All indicators calculated for ETH
- [ ] No "No data available" errors

**Repeat for Tab 3:**
- [ ] Daily chart shows ETH data
- [ ] 12H chart shows ETH data
- [ ] 4H chart shows ETH data
- [ ] 1H chart shows ETH data

## Test 11: Price Update Loop

**Objective:** Verify price updates continue with new coin

**Steps:**
1. Change coin to ETH
2. Wait 10 seconds
3. Observe "현재 가격:" field updating

**Expected Results:**
- [ ] Price updates every ~1 second
- [ ] Price is for ETH (verify against Bithumb website)
- [ ] No "조회 실패" errors
- [ ] Price format is correct (comma separators)

## Test 12: Bot Integration

**Objective:** Verify bot uses new coin when started

**Steps:**
1. Change coin to XRP
2. Start bot
3. Wait for first market analysis
4. Check console log

**Expected Results:**
- [ ] Console shows: "[ANALYZE] Starting market analysis..."
- [ ] Bot fetches XRP candlestick data (not BTC or ETH)
- [ ] Regime filter uses XRP daily data
- [ ] Entry signals calculate for XRP 4H data
- [ ] No symbol mismatch errors

## Test 13: Error Recovery

**Objective:** Verify graceful error handling

**Steps:**
1. Disconnect internet
2. Try to change coin
3. Reconnect internet

**Expected Results:**
- [ ] Error message shown to user
- [ ] Dropdown reverts to previous coin
- [ ] Application doesn't crash
- [ ] After reconnection, coin change works again

## Test 14: Persistence Check

**Objective:** Verify selected coin persists during session

**Steps:**
1. Change coin to DOT
2. Navigate through all tabs
3. Return to Tab 1
4. Check coin selector panel

**Expected Results:**
- [ ] Dropdown still shows DOT
- [ ] Status still shows "현재: DOT"
- [ ] Window title still includes "- DOT"
- [ ] All tabs still show DOT data

## Test 15: Popular Coins Quick Access

**Objective:** Verify popular coins are easily accessible

**Steps:**
1. Click dropdown
2. Note position of BTC, ETH, XRP, SOL

**Expected Results:**
- [ ] All popular coins in first 10 items
- [ ] No need to scroll to find popular coins
- [ ] Separator clearly divides popular from others

## Performance Tests

### Test 16: Chart Refresh Speed

**Objective:** Measure time to refresh all charts

**Steps:**
1. Change coin from BTC → ETH
2. Note timestamp in console: "⏳ 코인 변경 중..."
3. Note timestamp in console: "✅ 모든 탭 새로고침 완료"

**Expected Results:**
- [ ] Total refresh time < 10 seconds
- [ ] No UI freezing
- [ ] Smooth transition

### Test 17: Memory Leak Check

**Objective:** Verify no memory leaks with repeated changes

**Steps:**
1. Note initial memory usage
2. Change coin 20 times (BTC → ETH → XRP → ... → BTC)
3. Note final memory usage

**Expected Results:**
- [ ] Memory increase < 100 MB
- [ ] No significant memory leak
- [ ] Application remains responsive

## Edge Cases

### Test 18: Same Coin Selection

**Objective:** Verify handling of selecting already-selected coin

**Steps:**
1. Current coin is BTC
2. Select BTC again from dropdown
3. Click "변경"

**Expected Results:**
- [ ] Info dialog: "이미 BTC을(를) 사용 중입니다"
- [ ] No refresh triggered
- [ ] No errors

### Test 19: Rapid Clicking

**Objective:** Verify handling of rapid button clicks

**Steps:**
1. Select ETH
2. Rapidly click "변경" button 5 times

**Expected Results:**
- [ ] Only one confirmation dialog appears
- [ ] Coin changes only once
- [ ] No duplicate refreshes
- [ ] No errors

## Final Verification

- [ ] All tests passed
- [ ] No Python exceptions in terminal
- [ ] No JavaScript errors (if applicable)
- [ ] GUI remains responsive throughout
- [ ] All tabs functional after multiple coin changes
- [ ] Can successfully start/stop bot after coin changes

## Test Summary Report Template

```
Date: _______________
Tester: _______________

Tests Passed: _____ / 19
Tests Failed: _____

Failed Tests:
- Test #: _____
  Reason: _______________

Critical Issues:
- _______________

Minor Issues:
- _______________

Overall Status: [ ] PASS  [ ] FAIL
```

## Automated Testing (Optional)

For automated testing, consider:
```python
# test_coin_selector.py
import unittest
from ver2 import config_v2

class TestCoinSelector(unittest.TestCase):
    def test_validate_symbol(self):
        self.assertTrue(config_v2.validate_symbol('BTC')[0])
        self.assertTrue(config_v2.validate_symbol('ETH')[0])
        self.assertFalse(config_v2.validate_symbol('INVALID')[0])

    def test_set_symbol(self):
        config = config_v2.set_symbol_in_config('XRP')
        self.assertEqual(config['symbol'], 'XRP')

if __name__ == '__main__':
    unittest.main()
```

Run with: `python -m unittest test_coin_selector.py`
