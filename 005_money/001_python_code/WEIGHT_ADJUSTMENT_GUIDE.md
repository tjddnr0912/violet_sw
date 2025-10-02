# Weight Adjustment Feature - User Guide

## Overview

The weight adjustment feature allows users to interactively customize the signal weights for the 5 main technical indicators in the cryptocurrency trading bot. This provides fine-tuned control over how much each indicator influences trading decisions.

## Feature Location

**GUI:** Settings Panel → "⚖️ 신호 가중치 조정" (Signal Weight Adjustment)

Located in the scrollable left panel, below the main settings panel.

## Components

### 1. Weight Sliders (5 Indicators)

Each indicator has a horizontal slider controlling its weight (0.0 to 1.0):

- **MACD**: Trend-following momentum indicator (Default: 0.35)
- **Moving Average (MA)**: Trend confirmation (Default: 0.25)
- **RSI**: Overbought/oversold filter (Default: 0.20)
- **Bollinger Bands (BB)**: Mean reversion signal (Default: 0.10)
- **Volume**: Trade confirmation (Default: 0.10)

**Display Format:** `0.35 (35%)`
- First number: Decimal weight
- Percentage: Visual representation

### 2. Total Weight Display

Shows the sum of all weights with color-coded status:

- **Green (✓)**: 0.99 ≤ total ≤ 1.01 (Valid)
- **Orange (⚠)**: 0.95 ≤ total ≤ 1.05 (Warning)
- **Red (✗)**: Outside valid range (Error)

### 3. Auto-Normalize Checkbox

**Enabled (Default):** When you adjust one slider, others automatically adjust proportionally to maintain total = 1.0

**Disabled (Manual Mode):** You can freely adjust each slider independently. System warns if total ≠ 1.0 when saving.

### 4. Threshold Sliders

**Signal Threshold (-1.0 to 1.0):**
- Minimum signal strength required to trigger a trade
- Default: 0.5
- Higher = More conservative (fewer trades)
- Lower = More aggressive (more trades)

**Confidence Threshold (0.0 to 1.0):**
- Minimum confidence level required to execute a trade
- Default: 0.6
- Higher = Only trade when very confident
- Lower = Trade with less certainty

### 5. Action Buttons

**🔄 Reset to Default:**
- Restores all weights to original values
- Resets thresholds to defaults
- Requires confirmation

**💾 Save Weights:**
- Validates and saves current settings
- Updates ConfigManager
- Applies to next trading cycle
- Offers to restart bot if running

## Usage Examples

### Example 1: Trend-Following Strategy

Emphasize MACD and MA for strong trend signals:

```
MACD:   0.40 (40%)  [====●=====]
MA:     0.30 (30%)  [===●======]
RSI:    0.15 (15%)  [==●=======]
BB:     0.10 (10%)  [=●========]
Volume: 0.05 (5%)   [●=========]
```

**Use Case:** Bull/bear markets with clear trends

### Example 2: Mean Reversion Strategy

Emphasize RSI and Bollinger Bands for ranging markets:

```
MACD:   0.15 (15%)  [==●=======]
MA:     0.15 (15%)  [==●=======]
RSI:    0.35 (35%)  [====●=====]
BB:     0.25 (25%)  [===●======]
Volume: 0.10 (10%)  [=●========]
```

**Use Case:** Sideways/ranging markets, scalping

### Example 3: Conservative Balanced

Original balanced strategy with stricter thresholds:

```
MACD:   0.35 (35%)  [====●=====]
MA:     0.25 (25%)  [===●======]
RSI:    0.20 (20%)  [==●=======]
BB:     0.10 (10%)  [=●========]
Volume: 0.10 (10%)  [=●========]

Signal Threshold:     0.7  (High - fewer signals)
Confidence Threshold: 0.8  (Very conservative)
```

**Use Case:** Risk-averse trading, volatile markets

## How Auto-Normalization Works

### Scenario: You move MACD slider to 0.50

**Before:**
```
MACD:   0.35, MA: 0.25, RSI: 0.20, BB: 0.10, Volume: 0.10
Total: 1.00
```

**Action:** Drag MACD to 0.50

**After (Auto-Normalized):**
```
MACD:   0.50  (changed by user)
MA:     0.19  (0.25 / 0.65 × 0.50 = adjusted)
RSI:    0.15  (0.20 / 0.65 × 0.50 = adjusted)
BB:     0.08  (0.10 / 0.65 × 0.50 = adjusted)
Volume: 0.08  (0.10 / 0.65 × 0.50 = adjusted)
Total: 1.00 ✓
```

**Logic:**
1. Remaining weight = 1.0 - 0.50 = 0.50
2. Other indicators' proportion = 0.25:0.20:0.10:0.10 (total 0.65)
3. Each redistributed: (old_value / 0.65) × 0.50

## Validation Rules

### Weight Validation

✅ **Valid:**
- Each weight: 0.0 ≤ weight ≤ 1.0
- Sum of all weights: 0.99 ≤ sum ≤ 1.01
- At least 1 indicator enabled

❌ **Invalid:**
- Negative weights
- Weights > 1.0
- Sum significantly different from 1.0 (without normalization)

### Threshold Validation

✅ **Valid Signal Threshold:** -1.0 ≤ value ≤ 1.0
✅ **Valid Confidence Threshold:** 0.0 ≤ value ≤ 1.0

## Backend Integration

### Files Modified

1. **config_manager.py**
   - `update_signal_weights(weights)`: Update weights with validation
   - `update_thresholds(signal, confidence)`: Update thresholds
   - `normalize_weights(weights)`: Normalize weights to sum = 1.0

2. **gui_app.py**
   - `create_weight_adjustment_panel()`: UI construction
   - `on_weight_changed()`: Real-time slider updates
   - `auto_normalize_weights()`: Auto-normalization logic
   - `save_weight_settings()`: Persist changes
   - `reset_weights_to_default()`: Reset functionality

### Configuration Storage

Weights are stored in `config['strategy']['signal_weights']`:

```python
{
    'macd': 0.35,
    'ma': 0.25,
    'rsi': 0.20,
    'bb': 0.10,
    'volume': 0.10
}
```

Thresholds in `config['strategy']`:
```python
{
    'signal_threshold': 0.5,
    'confidence_threshold': 0.6
}
```

## Real-Time Application

### During Bot Execution

- Changes apply to **next trading cycle** (15-minute interval by default)
- No restart needed for settings to take effect
- ConfigManager updates immediately upon save

### Restart Bot Option

When saving weights while bot is running:
- System asks: "Restart bot to apply immediately?"
- **Yes**: Stop → Wait 1 second → Start (new weights active now)
- **No**: Changes apply at next scheduled cycle

## Testing

Test script included: `test_weight_adjustment.py`

```bash
cd 005_money/001_python_code
python3 test_weight_adjustment.py
```

**Tests:**
- ✅ Normal weight update
- ✅ Invalid weight rejection (sum ≠ 1.0)
- ✅ Weight normalization
- ✅ Threshold updates
- ✅ Range validation

## Best Practices

### 1. Start with Defaults
Don't change weights until you understand how each indicator behaves.

### 2. Small Adjustments
Make incremental changes (±0.05) and observe results over several days.

### 3. Market-Dependent
- **Trending markets**: Increase MACD, MA weights
- **Ranging markets**: Increase RSI, BB weights
- **High volume breakouts**: Increase Volume weight

### 4. Backtesting
Use transaction history to analyze which weight combinations work best for your trading style.

### 5. Emergency Fallback
Keep "Reset to Default" as a quick recovery option if custom weights underperform.

## Troubleshooting

### Issue: Weights won't save

**Cause:** Sum ≠ 1.0 in manual mode

**Solution:**
1. Enable "Auto-Normalize" checkbox
2. OR manually adjust until sum = 1.00
3. OR click "Normalize" when prompted during save

### Issue: Too many/few trades

**Cause:** Signal threshold too low/high

**Solution:**
- More trades → Increase signal threshold (0.5 → 0.7)
- Fewer trades → Decrease signal threshold (0.5 → 0.3)

### Issue: Changes not applying

**Cause:** Forgot to click "Save Weights"

**Solution:**
- Always click 💾 Save button after adjusting
- Check log for "가중치가 저장되었습니다" message

## Advanced Tips

### Strategy Presets

The main settings panel has preset strategies that auto-adjust weights:

- **Balanced Elite**: Default (0.35/0.25/0.20/0.10/0.10)
- **MACD + RSI Filter**: Trend-focused (0.40/0.20/0.30/0.10/0.00)
- **Trend Following**: Strong trends (0.40/0.30/0.15/0.05/0.10)
- **Mean Reversion**: Ranging markets (0.15/0.15/0.35/0.25/0.10)

### Threshold Tuning

**Conservative (Risk-Averse):**
```
Signal: 0.7, Confidence: 0.8
Result: Few high-quality trades
```

**Aggressive (Profit-Maximizing):**
```
Signal: 0.3, Confidence: 0.5
Result: Many trades, higher risk
```

**Balanced (Recommended):**
```
Signal: 0.5, Confidence: 0.6
Result: Moderate trade frequency
```

## Future Enhancements

Potential additions (not yet implemented):

- [ ] Save/Load custom weight profiles
- [ ] Performance metrics per weight configuration
- [ ] A/B testing between weight sets
- [ ] Machine learning-based weight optimization
- [ ] Dynamic weight adjustment based on market regime

## Support

For issues or questions:
1. Check logs: `logs/trading_YYYYMMDD.log`
2. Run test script: `test_weight_adjustment.py`
3. Reset to defaults if problems persist
4. Review transaction history for performance analysis

---

**Version:** 1.0
**Last Updated:** 2025-10-02
**Author:** Claude (System Architect)
**Project:** Cryptocurrency Trading Bot - Elite Strategy
