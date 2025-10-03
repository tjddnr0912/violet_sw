# Multi-Timeframe Chart System - Testing Guide

## 🎯 Test Status: READY FOR MANUAL TESTING

All automated tests passed. The system is ready for GUI interaction testing.

## ✅ Automated Tests Completed

### 1. Import Tests ✓
- ✅ DataManager imports successfully
- ✅ IndicatorCalculator imports successfully
- ✅ ChartColumn imports successfully
- ✅ MultiTimeframeChartTab imports successfully
- ✅ gui_app imports successfully

### 2. Component Tests ✓
- ✅ DataManager caching works (instant cache retrieval <0.0001s)
- ✅ DataManager force refresh works
- ✅ DataManager multi-interval fetch works (30m, 6h, 24h)
- ✅ IndicatorCalculator wrapper functions work
- ✅ ChartColumn widget creates without errors

### 3. GUI Launch Tests ✓
- ✅ GUI window creates successfully
- ✅ Notebook widget contains 5 tabs
- ✅ "📊 멀티 타임프레임" tab is visible (Tab 2)
- ✅ multi_chart_widget attribute exists

### 4. Issues Fixed During Testing ✓
- ✅ **Issue #1-2**: Module path issues with numbered directory (001_python_code)
- ✅ **Issue #3**: DataManager requires coin_symbol parameter
- ✅ **Issue #4-8**: IndicatorCalculator API returns dictionaries, not tuples
- ✅ **Issue #9**: Geometry manager conflict (pack vs grid) - fixed ChartColumn
- ✅ **Issue #10**: Variable name error (coin_symbol vs self.coin_symbol)

---

## 🖱️ Manual Testing Checklist

### How to Launch GUI
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money/001_python_code
source ../.venv/bin/activate
python gui_app.py
```

### Test 1: Tab Visibility ☐
1. Launch GUI
2. Click on "📊 멀티 타임프레임" tab (should be Tab 2)
3. **Expected**: 3 columns of charts side-by-side
4. **Expected**: Each column has title, checkboxes, and chart area
5. **Expected**: Column 1 has interval dropdown

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 2: Initial Chart Display ☐
1. Wait for initial data load (~5-10 seconds due to rate limiting)
2. **Expected**: All 3 charts show candlesticks
3. **Expected**: No indicators visible (all checkboxes unchecked by default)
4. **Expected**: Column 1 shows 1h candles (default)
5. **Expected**: Column 2 shows 4h candles
6. **Expected**: Column 3 shows 24h candles

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 3: Checkbox Toggle - MA (Moving Average) ☐
1. Check the "MA" checkbox on Column 1
2. **Expected**: Two moving average lines appear on chart (orange/purple)
3. **Expected**: Only Column 1 is affected, not Column 2 or 3
4. Uncheck the "MA" checkbox
5. **Expected**: MA lines disappear

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 4: Checkbox Toggle - RSI ☐
1. Check the "RSI" checkbox on Column 2
2. **Expected**: New subplot appears below candlesticks
3. **Expected**: RSI line (0-100) with 30/70 threshold lines
4. **Expected**: Only Column 2 affected
5. Uncheck RSI
6. **Expected**: RSI subplot disappears

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 5: Checkbox Toggle - Multiple Indicators ☐
1. On Column 1, check: MA, RSI, MACD
2. **Expected**: MA overlays on main chart
3. **Expected**: RSI subplot appears below
4. **Expected**: MACD subplot appears below RSI
5. **Expected**: Total of 3 subplots (main + RSI + MACD)
6. **Expected**: No errors in console

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 6: Checkbox Toggle - All Indicators ☐
1. On Column 3, check all 8 checkboxes:
   - MA, RSI, BB, Volume, MACD, Stochastic, ATR, ADX
2. **Expected**: Main chart shows MA lines and Bollinger Bands
3. **Expected**: Multiple subplots appear (RSI, MACD, Volume)
4. **Expected**: Info box shows Stochastic, ATR, ADX values
5. **Expected**: Chart resizes smoothly, no overlap

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 7: Interval Dropdown (Column 1 Only) ☐
1. Click Column 1 interval dropdown
2. **Expected**: Shows options: 30m, 1h, 4h, 6h, 12h, 24h
3. Select "6h"
4. **Expected**: Column 1 refreshes and shows 6h candles
5. **Expected**: Columns 2 and 3 unchanged (still 4h and 24h)
6. **Expected**: Chart updates within 1-2 seconds

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 8: Manual Refresh Button ☐
1. Click "🔄 전체 새로고침" button at top
2. **Expected**: All 3 columns refresh simultaneously
3. **Expected**: Console shows API calls with rate limiting (1s gaps)
4. **Expected**: Status bar shows "새로고침 중..." then "마지막 업데이트: HH:MM:SS"

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 9: Auto-Refresh Mechanism ☐
1. Wait 15-20 seconds without interaction
2. **Expected**: Charts auto-refresh (status bar updates)
3. **Expected**: No crashes or errors
4. Click "자동 새로고침" toggle to disable
5. Wait 15-20 seconds
6. **Expected**: No auto-refresh occurs
7. Re-enable auto-refresh
8. **Expected**: Auto-refresh resumes

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 10: Rapid Checkbox Toggling (Stress Test) ☐
1. Rapidly toggle MA checkbox on/off 10 times
2. **Expected**: Chart updates smoothly with debouncing
3. **Expected**: No crashes or UI freezing
4. **Expected**: Final state matches checkbox state

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 11: Window Resize ☐
1. Resize window smaller (minimum size)
2. **Expected**: Charts shrink proportionally
3. **Expected**: All 3 columns remain visible
4. Resize window larger
5. **Expected**: Charts expand to fill space
6. **Expected**: No layout breakage

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

### Test 12: Error Handling - Network Interruption ☐
1. Disconnect network (turn off WiFi)
2. Click manual refresh
3. **Expected**: Error logged in console
4. **Expected**: GUI doesn't crash
5. Reconnect network
6. Click refresh again
7. **Expected**: Data loads successfully

**Status**: ☐ PASS ☐ FAIL (Skip if cannot test)
**Notes**: _______________________

### Test 13: Memory Leak Check (Long Run) ☐
1. Leave GUI running for 5+ minutes
2. Observe Activity Monitor / Task Manager
3. **Expected**: Memory usage stable (~100-200MB)
4. **Expected**: No continuous memory growth
5. Toggle checkboxes several times
6. **Expected**: Memory returns to baseline

**Status**: ☐ PASS ☐ FAIL
**Notes**: _______________________

---

## 🐛 Bug Reporting Template

If you find any issues, document them using this format:

```
**Bug #X**: [Short Description]

**Steps to Reproduce**:
1.
2.
3.

**Expected Behavior**:
[What should happen]

**Actual Behavior**:
[What actually happened]

**Error Message** (if any):
```
[Paste error message or screenshot]
```

**Severity**: ☐ Critical ☐ High ☐ Medium ☐ Low
```

---

## 📊 Performance Benchmarks

Expected performance metrics:

- **Initial load time**: 5-10 seconds (due to API rate limiting)
- **Cache hit response**: <0.001 seconds
- **Chart redraw time**: <0.5 seconds
- **Checkbox toggle latency**: <0.2 seconds (with debouncing)
- **Auto-refresh interval**: 15 seconds (configurable)
- **Memory usage**: 100-200 MB
- **CPU usage (idle)**: <5%
- **CPU usage (refresh)**: 10-20% spike, then back to idle

---

## 🎓 Testing Tips

1. **Open Developer Console**: Keep console visible to catch errors
2. **Test One Feature at a Time**: Don't mix multiple actions
3. **Document Everything**: Note exact steps that caused issues
4. **Take Screenshots**: Especially for UI bugs
5. **Check Logs**: Review console output for warnings/errors
6. **Test Edge Cases**: Empty data, network errors, rapid clicks, etc.

---

## ✅ Sign-Off

**Tester**: _______________
**Date**: _______________
**Overall Status**: ☐ PASS ☐ FAIL
**Ready for Production**: ☐ YES ☐ NO ☐ WITH FIXES

**Summary Comments**:
_______________________________________________________
_______________________________________________________
_______________________________________________________
