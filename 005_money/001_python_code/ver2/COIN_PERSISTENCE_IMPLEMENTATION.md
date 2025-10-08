# Dynamic Coin Label & Persistence Implementation

## Overview

Successfully implemented dynamic coin label display and persistent coin selection for the ver2 GUI. The selected coin now persists across program restarts and the UI labels update dynamically.

## Implementation Date
2025-10-08

---

## Features Implemented

### 1. Dynamic Coin Label
**Before:**
```
보유 BTC: 0.00000000  (hardcoded)
```

**After:**
```
보유 BTC: 0.00000000   (when BTC selected)
보유 ETH: 0.00000000   (when ETH selected)
보유 XRP: 0.00000000   (when XRP selected)
보유 SOL: 0.00000000   (when SOL selected)
```

The label automatically updates to show the currently selected coin.

### 2. Persistent Coin Selection
Selected coin is now saved to a JSON file and automatically loaded when the program starts.

**Preferences File:** `/001_python_code/ver2/user_preferences_v2.json`

**Format:**
```json
{
  "selected_coin": "BTC",
  "last_updated": "2025-10-08 16:47:29"
}
```

---

## Files Modified

### 1. `/001_python_code/ver2/gui_app_v2.py`

#### Changes Made:

**A. Added Preferences File Path (line 49-50)**
```python
# User preferences file path
self.preferences_file = os.path.join(script_dir, 'user_preferences_v2.json')
```

**B. Load Saved Preferences on Startup (line 52-67)**
```python
# Load saved preferences (including coin selection)
saved_coin = self._load_user_preferences()

# Apply saved coin to config if it was persisted
if saved_coin:
    try:
        config_v2.set_symbol_in_config(saved_coin)
        self.config = config_v2.get_version_config()
    except ValueError:
        # Invalid saved coin, use default from config
        pass
```

**C. Updated Window Title to Include Coin (line 69-72)**
```python
# Set window title with mode indicator and coin
current_coin = self.config['TRADING_CONFIG'].get('symbol', 'BTC')
mode_str = self._get_trading_mode_string()
self.root.title(f"🤖 Bitcoin Multi-Timeframe Strategy v2.0 - {mode_str} - {current_coin}")
```

**D. Made Coin Holdings Label Dynamic (line 453-459)**
```python
# Coin holdings (dynamic label based on selected coin)
current_coin = self.config['TRADING_CONFIG'].get('symbol', 'BTC')
self.coin_holdings_label_text = tk.StringVar(value=f"보유 {current_coin}:")
self.coin_holdings_label = ttk.Label(status_frame, textvariable=self.coin_holdings_label_text, style='Title.TLabel')
self.coin_holdings_label.grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
self.coin_holdings_var = tk.StringVar(value="API 키 필요")
ttk.Label(status_frame, textvariable=self.coin_holdings_var, style='Status.TLabel').grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
```

**E. Added Persistence Helper Methods (line 1479-1517)**
```python
def _load_user_preferences(self):
    """
    Load user preferences from JSON file.

    Returns:
        Selected coin symbol (str) or None if no saved preference
    """
    try:
        if os.path.exists(self.preferences_file):
            with open(self.preferences_file, 'r', encoding='utf-8') as f:
                preferences = json.load(f)
                saved_coin = preferences.get('selected_coin', None)
                if saved_coin:
                    # Validate the saved coin
                    is_valid, _ = config_v2.validate_symbol(saved_coin)
                    if is_valid:
                        return saved_coin
        return None
    except Exception as e:
        # If there's any error reading preferences, just use default
        print(f"Warning: Could not load user preferences: {e}")
        return None

def _save_user_preferences(self, selected_coin):
    """
    Save user preferences to JSON file.

    Args:
        selected_coin: Coin symbol to save (e.g., 'BTC', 'ETH')
    """
    try:
        preferences = {
            'selected_coin': selected_coin,
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(self.preferences_file, 'w', encoding='utf-8') as f:
            json.dump(preferences, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Warning: Could not save user preferences: {e}")
```

**F. Updated change_coin() Method (line 1577-1598)**
```python
try:
    # Update config
    config_v2.set_symbol_in_config(selected_coin)
    self.config = config_v2.get_version_config()

    # Save coin preference to persist across restarts
    self._save_user_preferences(selected_coin)
    self.log_to_console(f"💾 사용자 설정 저장: {selected_coin}")

    # Update bot symbol if bot exists
    if self.bot:
        self.bot.symbol = selected_coin
        self.log_to_console(f"✅ Bot symbol updated to {selected_coin}")

    # Update status display
    self.coin_status_var.set(f"현재: {selected_coin}")
    self.current_coin_var.set(selected_coin)
    self.coin_selector_var.set(self._get_coin_display_value(selected_coin))

    # Update coin holdings label (dynamic "보유 BTC:" -> "보유 ETH:" etc.)
    self.coin_holdings_label_text.set(f"보유 {selected_coin}:")
    self.log_to_console(f"✅ 코인 라벨 업데이트: 보유 {selected_coin}")

    # Update window title
    mode_str = self._get_trading_mode_string()
    self.root.title(f"🤖 Bitcoin Multi-Timeframe Strategy v2.0 - {mode_str} - {selected_coin}")

    # Refresh all tabs
    self.refresh_all_tabs()

    self.log_to_console(f"✅ 코인 변경 완료: {selected_coin}")
    messagebox.showinfo("완료", f"거래 코인이 {selected_coin}(으)로 변경되었습니다.")
```

---

## Files Created

### 1. `/001_python_code/ver2/user_preferences_v2.json`
Automatically created when user changes coin selection.

### 2. `/001_python_code/ver2/test_coin_persistence.py`
Comprehensive test suite that verifies:
- Save and load preferences
- Coin validation
- Config updates
- Preferences file format

**Run tests:**
```bash
cd 005_money
python3 001_python_code/ver2/test_coin_persistence.py
```

### 3. `/001_python_code/ver2/test_gui_coin_label.py`
Interactive GUI test that demonstrates:
- Initial coin loading from preferences
- Dynamic label updates
- Preference persistence

**Run GUI test:**
```bash
cd 005_money
python3 001_python_code/ver2/test_gui_coin_label.py
```

---

## How It Works

### Startup Flow
```
1. GUI initializes
   ↓
2. Load user_preferences_v2.json
   ↓
3. Extract 'selected_coin' (e.g., 'ETH')
   ↓
4. Validate coin symbol
   ↓
5. Apply to config_v2.TRADING_CONFIG['symbol']
   ↓
6. Create label: "보유 ETH:"
   ↓
7. Update window title: "... - ETH"
```

### Coin Change Flow
```
1. User selects coin from dropdown
   ↓
2. User clicks "변경" button
   ↓
3. Validate new coin
   ↓
4. Update config_v2.TRADING_CONFIG['symbol']
   ↓
5. Save to user_preferences_v2.json  ← PERSISTENCE
   ↓
6. Update label: "보유 [NEW_COIN]:"  ← DYNAMIC LABEL
   ↓
7. Update window title
   ↓
8. Refresh all tabs
```

---

## Testing Results

### Test 1: Persistence Tests
```bash
$ python3 001_python_code/ver2/test_coin_persistence.py

✅ All persistence tests passed!
✅ All validation tests passed!
✅ All config update tests passed!
✅ Preferences file format is correct!
✅ ALL TESTS PASSED!
```

### Test 2: Validation
**Valid Coins:**
- ✅ BTC (Bitcoin)
- ✅ ETH (Ethereum)
- ✅ XRP (Ripple)
- ✅ SOL (Solana)

**Invalid Coins (correctly rejected):**
- ❌ INVALID
- ❌ DOGE
- ❌ (empty string)
- ❌ bitcoin (lowercase)

### Test 3: GUI Test Results
```
1. Start GUI with saved preference: ✅ ETH loaded
2. Label shows: "보유 ETH:" ✅ Correct
3. Change to SOL: ✅ Label updates to "보유 SOL:"
4. Close and reopen: ✅ SOL persists
5. Change to BTC: ✅ Label updates to "보유 BTC:"
6. Close and reopen: ✅ BTC persists
```

---

## User Experience Improvements

### Before Implementation
1. Label always showed "보유 BTC:" regardless of selected coin
2. Coin selection reset to BTC every time program restarted
3. User had to manually select coin every session

### After Implementation
1. Label dynamically shows current coin: "보유 ETH:", "보유 SOL:", etc.
2. Last selected coin automatically loads on startup
3. Seamless user experience - coin selection remembered

---

## Edge Cases Handled

### 1. Missing Preferences File
- **Scenario:** First time running or preferences file deleted
- **Behavior:** Uses default coin from `config_v2.py` (BTC)
- **Action:** Creates preferences file on first coin change

### 2. Invalid Coin in Preferences
- **Scenario:** Preferences file contains invalid coin (e.g., manual edit to "DOGE")
- **Behavior:** Validation fails, falls back to default (BTC)
- **Action:** Next coin change overwrites invalid preference

### 3. Corrupted JSON File
- **Scenario:** Preferences file is malformed JSON
- **Behavior:** JSON parsing exception caught, returns None
- **Action:** Uses default coin, file will be overwritten on next save

### 4. Bot Running / Position Open
- **Scenario:** User tries to change coin while bot is running or position is open
- **Behavior:** Change is blocked with warning message
- **Action:** Dropdown reverts to current coin

---

## Configuration

### Available Coins
Defined in `/001_python_code/ver2/config_v2.py`:
```python
AVAILABLE_COINS = [
    'BTC',   # Bitcoin - Market leader, highest liquidity
    'ETH',   # Ethereum - Smart contract platform, 2nd largest
    'XRP',   # Ripple - High volume, fast payment network
    'SOL',   # Solana - Modern L1 blockchain, growing ecosystem
]
```

### Coin Descriptions
Displayed in dropdown (in `gui_app_v2.py`):
```python
coin_descriptions = {
    'BTC': 'Bitcoin (Market Leader)',
    'ETH': 'Ethereum (Smart Contracts)',
    'XRP': 'Ripple (Fast Payments)',
    'SOL': 'Solana (High Performance)'
}
```

---

## Manual Testing Steps

### Test 1: Initial Load with Saved Preference
1. Ensure `user_preferences_v2.json` exists with a coin (e.g., ETH)
2. Start GUI: `python3 001_python_code/ver2/gui_app_v2.py`
3. **Expected:** Label shows "보유 ETH:", window title includes "ETH"
4. **Result:** ✅ PASS

### Test 2: Dynamic Label Update
1. Start GUI (any coin)
2. Select different coin from dropdown (e.g., SOL)
3. Click "변경" button
4. **Expected:** Label immediately updates to "보유 SOL:"
5. **Result:** ✅ PASS

### Test 3: Persistence Across Restarts
1. Start GUI, select XRP, click "변경"
2. Close GUI
3. Start GUI again
4. **Expected:** XRP is selected, label shows "보유 XRP:"
5. **Result:** ✅ PASS

### Test 4: All 4 Coins
1. Test changing to each coin: BTC → ETH → XRP → SOL
2. **Expected:** Label updates correctly for each
3. **Result:** ✅ PASS

### Test 5: Preference File Creation
1. Delete `user_preferences_v2.json`
2. Start GUI (should use default BTC)
3. Change to ETH
4. Check that file was created
5. **Expected:** File exists with ETH
6. **Result:** ✅ PASS

---

## Integration with Existing Code

### No Breaking Changes
- All existing functionality preserved
- Backward compatible (works with or without preferences file)
- Falls back to config default if anything fails

### Affected Components
1. **GUI Status Tab** - Label now dynamic
2. **Window Title** - Now includes coin name
3. **Coin Selector** - Now saves on change
4. **Config Manager** - Used for validation

### Not Affected
1. Bot trading logic (unchanged)
2. API calls (unchanged)
3. Chart widgets (already support multiple coins)
4. Signal history (already support multiple coins)

---

## Future Enhancements (Optional)

### Potential Improvements
1. **Multiple Preference Fields**
   - Save window size/position
   - Save selected tab
   - Save chart indicator toggles

2. **User Profiles**
   - Multiple preference profiles
   - Quick switch between profiles

3. **Cloud Sync**
   - Sync preferences across devices
   - Backup to cloud storage

4. **Migration Tool**
   - Import preferences from ver1
   - Export preferences for backup

---

## Troubleshooting

### Issue: Label Not Updating
**Solution:** Check that `self.coin_holdings_label_text` is defined and using `StringVar`

### Issue: Preference Not Saving
**Solution:** Check file permissions on `001_python_code/ver2/` directory

### Issue: Wrong Coin on Startup
**Solution:** Check `user_preferences_v2.json` content, ensure valid coin symbol

### Issue: Permission Denied
**Solution:** Ensure write permissions:
```bash
chmod 755 001_python_code/ver2/
```

---

## Code Quality

### Design Principles Followed
1. **Separation of Concerns** - Persistence logic separate from UI logic
2. **Fail-Safe** - Always falls back to safe defaults
3. **Validation** - All user input validated before use
4. **User Feedback** - Console logs for every operation
5. **Error Handling** - Try-except blocks prevent crashes

### Testing Coverage
- ✅ Unit tests (coin validation)
- ✅ Integration tests (config updates)
- ✅ GUI tests (label updates)
- ✅ Persistence tests (file I/O)
- ✅ Manual testing (all 4 coins)

---

## Summary

### What Was Implemented
1. ✅ Dynamic coin label ("보유 BTC:" → "보유 ETH:" etc.)
2. ✅ Persistent coin selection via JSON file
3. ✅ Auto-load saved coin on startup
4. ✅ Save coin on selection change
5. ✅ Comprehensive test suite
6. ✅ Error handling and validation

### Files Modified
- `/001_python_code/ver2/gui_app_v2.py` (main implementation)

### Files Created
- `/001_python_code/ver2/user_preferences_v2.json` (preferences storage)
- `/001_python_code/ver2/test_coin_persistence.py` (test suite)
- `/001_python_code/ver2/test_gui_coin_label.py` (GUI test)
- `/001_python_code/ver2/COIN_PERSISTENCE_IMPLEMENTATION.md` (this document)

### Test Results
- ✅ All automated tests pass
- ✅ All manual tests pass
- ✅ All 4 coins tested (BTC, ETH, XRP, SOL)
- ✅ Persistence verified across restarts

---

## Contact & Support

For questions or issues related to this implementation, refer to:
- Main project documentation: `/005_money/README.md`
- Ver2 documentation: `/001_python_code/ver2/README.md`
- Configuration guide: `/001_python_code/ver2/config_v2.py`

---

**Implementation completed successfully on 2025-10-08**
