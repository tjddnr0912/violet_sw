# Dual Profit-Taking System Implementation

## Overview

Implemented a dual profit-taking system for Ver3 trading bot with two modes:
1. **BB-based mode**: Uses Bollinger Band levels (middle and upper) as profit targets (existing behavior)
2. **Percentage-based mode**: Uses fixed percentage gains from entry price (new feature)

## Features

- **Mode Selection**: Radio buttons in Settings panel to choose between modes
- **Configurable Percentages**: TP1 and TP2 percentage inputs (enabled only in percentage mode)
- **Persistent Settings**: Mode and percentages saved to `user_preferences_v3.json`
- **Position Locking**: Each position remembers the mode used when it was opened
- **Backward Compatibility**: Existing positions default to BB-based mode

## Implementation Details

### 1. Configuration (`config_v3.py`)

Added to `EXIT_CONFIG`:
```python
EXIT_CONFIG['profit_target_mode'] = 'bb_based'  # or 'percentage_based'
EXIT_CONFIG['tp1_percentage'] = 1.5  # First target %
EXIT_CONFIG['tp2_percentage'] = 2.5  # Second target %
```

### 2. Strategy (`strategy_v2.py`)

Modified `_calculate_target_prices()` to accept `entry_price` parameter and calculate targets based on mode:

**BB-based mode:**
```python
{
    'first_target': bb_middle,
    'second_target': bb_upper,
    'mode': 'bb_based'
}
```

**Percentage-based mode:**
```python
{
    'first_target': entry_price * (1 + tp1_pct/100),
    'second_target': entry_price * (1 + tp2_pct/100),
    'mode': 'percentage_based',
    'tp1_pct': 1.5,
    'tp2_pct': 2.5
}
```

### 3. Position Storage (`live_executor_v3.py`)

Enhanced `Position` class to store profit target settings:
```python
def __init__(
    self,
    ticker: str,
    size: float,
    entry_price: float,
    entry_time: datetime,
    # ... other params ...
    profit_target_mode: str = 'bb_based',
    tp1_percentage: float = 1.5,
    tp2_percentage: float = 2.5
):
```

Settings are locked when position is opened, ensuring consistency even if global settings change.

### 4. Portfolio Manager (`portfolio_manager_v3.py`)

Modified profit target checking to:
1. Get position's stored profit target mode
2. Temporarily override strategy's exit_config with position's settings
3. Calculate targets using position's locked-in mode and entry price
4. Restore original exit_config

This ensures positions opened in one mode continue using that mode.

### 5. GUI Settings Panel (`settings_panel_widget.py`)

Added controls in Exit Settings tab:
- **Profit Target Mode**: Radio buttons for "BB-based" or "Percentage-based"
- **TP1 %**: Spinbox for first target percentage (0.5-5.0%)
- **TP2 %**: Spinbox for second target percentage (1.0-10.0%)
- Percentage inputs auto-enable/disable based on mode
- Validation ensures TP2 > TP1

### 6. Preferences (`preference_manager_v3.py`)

Updated to persist mode in `user_preferences_v3.json`:
```json
{
  "exit_scoring": {
    "profit_target_mode": "bb_based",
    "tp1_target": 1.5,
    "tp2_target": 2.5
  }
}
```

## Files Modified

1. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver3/config_v3.py`
2. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2/strategy_v2.py`
3. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver3/portfolio_manager_v3.py`
4. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver3/widgets/settings_panel_widget.py`
5. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver3/live_executor_v3.py`
6. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver3/preference_manager_v3.py`
7. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver3/user_preferences_v3.json`

## Usage

### Changing Profit Target Mode (GUI)

1. Open Ver3 GUI
2. Go to Settings panel → Exit Scoring tab
3. Select mode:
   - **BB-based**: Targets use Bollinger Band middle and upper levels
   - **Percentage-based**: Targets use fixed % from entry price
4. If Percentage mode selected, set TP1% and TP2%
5. Click "Apply Settings"

Settings are saved automatically and persist across restarts.

### Example Scenarios

**Scenario 1: BB-based (Dynamic Targets)**
- Mode: BB-based
- Position opened at 100,000,000 KRW (100M)
- Current BB middle: 102,000,000 KRW
- Current BB upper: 104,000,000 KRW
- **TP1**: 102M (BB middle)
- **TP2**: 104M (BB upper)

**Scenario 2: Percentage-based (Fixed Targets)**
- Mode: Percentage-based (TP1: 2%, TP2: 4%)
- Position opened at 100,000,000 KRW (100M)
- **TP1**: 102,000,000 KRW (100M + 2% = 102M) - fixed
- **TP2**: 104,000,000 KRW (100M + 4% = 104M) - fixed
- Targets remain constant regardless of BB movement

**Scenario 3: Position Locking**
1. User sets mode to "Percentage-based" (TP1: 2%, TP2: 4%)
2. Bot opens BTC position at 100M
3. User changes mode to "BB-based"
4. Bot opens ETH position (new position uses BB mode)
5. **Result**: BTC uses percentage targets (locked), ETH uses BB targets

## Validation

Run validation script to verify implementation:
```bash
cd 005_money
python 001_python_code/ver3/validate_profit_target_implementation.py
```

Expected output: All checks should pass ✓

## Testing Checklist

- [x] Config has profit_target_mode fields
- [x] Strategy calculates BB-based targets correctly
- [x] Strategy calculates percentage-based targets correctly
- [x] Position stores mode when opened
- [x] Position serializes/deserializes mode correctly
- [x] Settings panel shows mode controls
- [x] Settings panel enables/disables percentage inputs
- [x] Preferences save mode to JSON
- [x] Preferences load mode from JSON
- [x] Portfolio manager uses position's locked mode
- [ ] GUI test: Mode switching works
- [ ] GUI test: Settings persist across restart
- [ ] GUI test: Old positions keep old mode after mode change

## Notes

- **Backward Compatibility**: Old positions without profit_target_mode default to 'bb_based'
- **Validation**: TP2 must be greater than TP1 (enforced in settings panel)
- **Thread Safety**: Mode locking ensures thread-safe multi-coin trading
- **Logging**: Position open logs include mode information for debugging

## Future Enhancements

Potential improvements:
- Add ATR-based dynamic percentage targets
- Support trailing percentage targets
- Add risk/reward ratio-based targets
- Visualize targets on chart widget
- Add statistics comparing mode performance
