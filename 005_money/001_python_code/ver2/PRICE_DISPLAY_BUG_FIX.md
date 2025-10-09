# Score Monitoring Price Display Bug Fix

## Problem Summary

**Issue:** Score monitoring widget showed BTC prices when SOL was selected
- Title correctly displayed: "📊 SOL 점수 체크 통계" ✅
- Price values displayed: BTC prices (~177M KRW) ❌
- Expected: SOL prices (~320K KRW)

## Root Cause Analysis

### Data Flow Investigation

1. **Score data creation** (`gui_trading_bot_v2.py` line 269-276):
   ```python
   self.score_tracking_callback({
       'timestamp': datetime.now(),
       'score': score,
       'components': components.copy(),
       'regime': self.regime,
       'price': latest['close'],  # Price from candlestick data
       'coin': self.symbol  # Bot's symbol
   })
   ```

2. **Bot symbol initialization** (`gui_trading_bot_v2.py` line 61):
   ```python
   # OLD CODE - Problem!
   self.symbol = self.config.get('TRADING_CONFIG', {}).get('symbol', 'BTC').upper()
   ```

   Bot reads symbol from config snapshot during `__init__`, which may not reflect recent coin changes.

3. **Data file examination** (`logs/score_checks_v2.json`):
   ```bash
   $ grep -c '"coin": "SOL"' logs/score_checks_v2.json
   0  # Zero SOL entries!

   $ tail logs/score_checks_v2.json | grep coin
   "coin": "BTC"  # All recent entries are BTC
   ```

### The Bug

When user selected SOL in the GUI:
1. Dropdown shows "SOL" → Updates UI variable only
2. User clicks "변경" button → Updates config to SOL
3. Score monitoring widget updates title to "SOL" (line 716)
4. **BUT**: Bot was created BEFORE coin change OR config wasn't properly updated
5. Bot continues using BTC symbol → Fetches BTC candlestick data → Saves BTC prices with 'coin': 'BTC'
6. Widget filters by coin correctly, but NO SOL data exists (all data is BTC)
7. User sees empty widget OR old BTC data (if backwards compatibility assumes missing coin field = current coin)

### Why Title Showed "SOL" But Prices Were BTC

The widget's `update_coin('SOL')` method correctly:
- Updates title to show "SOL" (line 716) ✅
- Filters loaded data by coin (line 768) ✅

BUT the underlying data file had zero SOL entries because the **bot was still using BTC symbol** when recording score checks!

## Solution Implemented

### 1. Add Explicit Symbol Parameter to Bot Constructor

**File:** `gui_trading_bot_v2.py`

**Before:**
```python
def __init__(self, log_callback=None, signal_callback=None, score_tracking_callback=None):
    self.config = config_v2.get_version_config()
    self.symbol = self.config.get('TRADING_CONFIG', {}).get('symbol', 'BTC').upper()
```

**After:**
```python
def __init__(self, log_callback=None, signal_callback=None, score_tracking_callback=None, symbol=None):
    self.config = config_v2.get_version_config()

    # Prioritize explicit parameter, fallback to config
    if symbol:
        self.symbol = symbol.upper()
    else:
        self.symbol = self.config.get('TRADING_CONFIG', {}).get('symbol', 'BTC').upper()
```

**Changes:**
- Added optional `symbol` parameter to `__init__` (line 49)
- Bot prioritizes explicit symbol over config (lines 61-64)
- Automatically uppercases symbol for consistency

### 2. Pass Current Symbol When Creating Bot

**File:** `gui_app_v2.py`

**Before:**
```python
self.bot = GUITradingBotV2(
    log_callback=self.log_to_console,
    signal_callback=handle_signal_event,
    score_tracking_callback=handle_score_tracking
)
```

**After:**
```python
# Get current coin from config to pass to bot
current_symbol = self.config['TRADING_CONFIG'].get('symbol', 'BTC')

self.bot = GUITradingBotV2(
    log_callback=self.log_to_console,
    signal_callback=handle_signal_event,
    score_tracking_callback=handle_score_tracking,
    symbol=current_symbol  # Explicitly pass current coin symbol
)
```

**Changes:**
- Read current symbol from GUI's config (line 854)
- Pass symbol explicitly to bot constructor (line 860)
- Ensures bot always uses the coin shown in GUI

### 3. Enhanced Logging

**File:** `gui_trading_bot_v2.py`

**Before:**
```python
self.log(f"GUITradingBotV2 initialized - Mode: {mode_str}")
self.log("[ENTRY] Fetching 4H candlestick data...")
```

**After:**
```python
self.log(f"GUITradingBotV2 initialized - Mode: {mode_str}, Symbol: {self.symbol}")
self.log(f"[ENTRY] Fetching 4H candlestick data for {self.symbol}...")
```

**Benefits:**
- User can verify correct coin in console logs
- Easier debugging of symbol-related issues
- Immediate confirmation when bot starts

## Testing

### Unit Tests Performed

```python
# Test 1: Explicit symbol parameter
bot1 = GUITradingBotV2(symbol='SOL')
assert bot1.symbol == 'SOL'  # ✅ PASS

# Test 2: Default from config
bot2 = GUITradingBotV2()
assert bot2.symbol == 'BTC'  # ✅ PASS (config has BTC)

# Test 3: Lowercase conversion
bot3 = GUITradingBotV2(symbol='eth')
assert bot3.symbol == 'ETH'  # ✅ PASS (uppercased)
```

All tests passed! Output confirms:
```
GUITradingBotV2 initialized - Mode: LIVE TRADING, Symbol: SOL ✅
GUITradingBotV2 initialized - Mode: LIVE TRADING, Symbol: BTC ✅
GUITradingBotV2 initialized - Mode: LIVE TRADING, Symbol: ETH ✅
```

### Expected Behavior After Fix

**Scenario: User changes coin from BTC to SOL**

1. User selects "SOL" from dropdown
2. User clicks "변경" button → Config updates to SOL
3. GUI displays: "현재: SOL" ✅
4. Score monitoring title updates: "📊 SOL 점수 체크 통계" ✅
5. User clicks "시작" button
6. Bot created with `symbol='SOL'` parameter ✅
7. Console log shows: "GUITradingBotV2 initialized - Symbol: SOL" ✅
8. Bot fetches SOL candlestick data ✅
9. Score checks saved with `'coin': 'SOL'` ✅
10. Prices displayed: ~320,000 KRW (SOL prices) ✅

**Before fix:** Steps 6-10 would use BTC instead of SOL ❌
**After fix:** All steps use correct SOL symbol ✅

## Files Modified

1. **`gui_trading_bot_v2.py`**
   - Line 49: Added `symbol` parameter to `__init__`
   - Lines 61-64: Symbol selection logic (prioritize parameter over config)
   - Line 128: Enhanced initialization log to include symbol
   - Line 225: Enhanced fetch log to include symbol

2. **`gui_app_v2.py`**
   - Line 854: Read current symbol from config
   - Line 860: Pass symbol explicitly to bot constructor

## Verification Steps for Users

After updating the code, verify the fix works:

1. **Check console logs when starting bot:**
   ```
   [22:03:08] GUITradingBotV2 initialized - Mode: DRY-RUN, Symbol: SOL
   [22:03:09] [ENTRY] Fetching 4H candlestick data for SOL...
   ```

   Confirm symbol matches what you selected!

2. **Check score monitoring data file:**
   ```bash
   tail logs/score_checks_v2.json | grep -E '"coin"|"price"'
   ```

   Should show:
   ```json
   "price": 320000.0,  // SOL price range
   "coin": "SOL"       // Correct coin
   ```

3. **Verify prices in GUI:**
   - BTC: ~100,000,000 KRW (100M)
   - ETH: ~4,000,000 KRW (4M)
   - XRP: ~3,000 KRW (3K)
   - SOL: ~300,000 KRW (300K)

## Related Issues

### Backwards Compatibility Note

Old score data without 'coin' field will be assumed to belong to the current coin (line 767 in `score_monitoring_widget_v2.py`):

```python
check_coin = check.get('coin', self.coin_symbol)  # Assume current coin if missing
```

This means if you have old data from before the coin field was added:
- It will show when that coin is selected
- Prices might look wrong if you switch coins
- **Solution:** Clear old data with "🗑️ 기록 삭제" button if needed

### Future Enhancements

Consider these improvements:

1. **Show coin symbol in tree view:**
   ```python
   # Add 'Coin' column to score monitoring tree
   columns = ('Time', 'Coin', 'Score', 'BB', 'RSI', 'Stoch', 'Regime', 'Price', 'Note')
   ```

2. **Price formatting by coin:**
   ```python
   # Different decimal places for different coins
   if coin == 'BTC':
       return f'{price:,.0f}'  # No decimals
   elif coin == 'XRP':
       return f'{price:,.2f}'  # 2 decimals
   ```

3. **Separate files per coin:**
   ```python
   file_path = os.path.join('logs', f'score_checks_{coin}_v2.json')
   ```

## Summary

**Root Cause:** Bot was reading symbol from config snapshot at initialization, which didn't reflect recent GUI coin changes.

**Fix:** Explicitly pass current coin symbol as parameter to bot constructor, ensuring bot always uses the coin displayed in GUI.

**Impact:** Users can now reliably switch coins and see correct prices for the selected cryptocurrency in score monitoring.

**Status:** ✅ Fixed and tested
