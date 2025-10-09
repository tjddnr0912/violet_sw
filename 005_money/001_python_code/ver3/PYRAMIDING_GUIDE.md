# Pyramiding Strategy Guide - Version 3

## Overview

Ver3 now supports **pyramiding**, which allows adding to existing positions when strong buy signals continue to occur. This feature enables scaling into winning positions while managing risk through reduced position sizes and strict entry criteria.

## What is Pyramiding?

Pyramiding is a position management technique where you add to a winning position as the price moves in your favor. Instead of a single entry, you can make multiple entries (up to 3) when conditions align.

### Example Scenario

1. **Entry #1**: BTC @ 50,000,000 KRW (100% position size = 50,000 KRW)
2. **Entry #2**: BTC @ 51,000,000 KRW (50% position size = 25,000 KRW) - Price increased 2%
3. **Entry #3**: BTC @ 52,000,000 KRW (25% position size = 12,500 KRW) - Price increased another 2%

**Result**: Total position worth 87,500 KRW with average entry at 50,571,429 KRW

## Configuration

### Pyramiding Settings (`config_v3.py`)

```python
PYRAMIDING_CONFIG = {
    'enabled': True,                     # Enable/disable pyramiding
    'max_entries_per_coin': 3,           # Maximum pyramid entries (1st + 2 pyramids)
    'min_score_for_pyramid': 3,          # Require score 3+ for additional entries
    'min_signal_strength_for_pyramid': 0.7,  # Require high signal strength (0-1)
    'position_size_multiplier': [1.0, 0.5, 0.25],  # 100%, 50%, 25% of base
    'min_price_increase_pct': 2.0,       # Only pyramid if price increased 2%+
    'allow_pyramid_in_regime': ['bullish', 'neutral'],  # Only pyramid in these regimes
}
```

### Configuration Parameters Explained

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enabled` | `True` | Master switch for pyramiding feature |
| `max_entries_per_coin` | `3` | Maximum number of entries per coin (including initial) |
| `min_score_for_pyramid` | `3` | Minimum entry score (0-4) required for pyramid entries |
| `min_signal_strength_for_pyramid` | `0.7` | Minimum signal strength (0-1) for pyramids |
| `position_size_multiplier` | `[1.0, 0.5, 0.25]` | Position size reduction for each entry |
| `min_price_increase_pct` | `2.0` | Price must increase 2% from last entry to pyramid |
| `allow_pyramid_in_regime` | `['bullish', 'neutral']` | Only pyramid in specified market regimes |

## Pyramiding Logic

### Entry Decision Criteria

For a pyramid entry to be allowed, ALL of the following conditions must be met:

1. **Pyramiding Enabled**: `PYRAMIDING_CONFIG['enabled'] == True`
2. **Entry Limit**: Current entry count < `max_entries_per_coin`
3. **High Score**: Entry score >= `min_score_for_pyramid` (typically 3 or 4)
4. **Strong Signal**: Signal strength >= `min_signal_strength_for_pyramid`
5. **Price Confirmation**: Price increased >= `min_price_increase_pct` from last entry
6. **Market Regime**: Current regime in `allow_pyramid_in_regime` list

### Position Size Reduction

Each pyramid entry uses a progressively smaller position size:

```python
Entry #1: 50,000 KRW × 1.0  = 50,000 KRW (100%)
Entry #2: 50,000 KRW × 0.5  = 25,000 KRW (50%)
Entry #3: 50,000 KRW × 0.25 = 12,500 KRW (25%)
---------------------------------------------------
Total:                        87,500 KRW (175% of base)
```

This ensures you're not over-committing capital as the position size grows.

## Implementation Details

### Modified Files

1. **`config_v3.py`**: Added `PYRAMIDING_CONFIG` section
2. **`live_executor_v3.py`**:
   - Updated `Position` class to track multiple entries
   - Added `get_entry_count()`, `get_last_entry_price()` methods
   - Modified `_update_position_after_trade()` to handle pyramiding
3. **`portfolio_manager_v3.py`**:
   - Added `_can_pyramid()` method to check pyramid conditions
   - Modified `make_portfolio_decision()` to detect pyramid opportunities
   - Updated `execute_decisions()` to handle position sizing

### Position Tracking

Each position now tracks:

```python
class Position:
    entry_count: int              # Number of entries (1, 2, or 3)
    entry_prices: List[float]     # All entry prices
    entry_times: List[datetime]   # Entry timestamps
    entry_sizes: List[float]      # Size of each entry
    entry_price: float            # Weighted average entry price
```

### Average Entry Price Calculation

When pyramiding, the average entry price is calculated using weighted average:

```python
old_value = current_size * current_avg_price
new_value = new_units * new_price
total_size = current_size + new_units

new_avg_price = (old_value + new_value) / total_size
```

## Example Log Output

```
2025-10-09 17:55:37 - INFO - Portfolio status: 1/2 positions
2025-10-09 17:55:37 - INFO - Active positions: ['BTC']
2025-10-09 17:55:37 - INFO - Pyramid opportunity: BTC (entry #2)
2025-10-09 17:55:37 - INFO - Entry candidates: [('BTC', '#2')]
2025-10-09 17:55:37 - INFO - Pyramid allowed for BTC: Score=4, Strength=0.85, Price increase=2.50%
2025-10-09 17:55:37 - INFO - Pyramid decision: BTC entry #2 (score: 4/4, strength: 0.85)
2025-10-09 17:55:37 - INFO - Pyramid entry #2 for BTC: Using 50% position size (25,000 KRW)
2025-10-09 17:55:37 - INFO - PYRAMID ENTRY #2: BTC | Added: 0.000500 @ 51,000,000 KRW | Total size: 0.001500 | Avg entry: 50,333,333 KRW
```

## Risk Management

### Benefits of Pyramiding

1. **Builds larger positions on strong trends**: Capitalize on confirmed momentum
2. **Reduces initial risk**: Start with smaller position, add only on confirmation
3. **Improves average entry**: Averaging up in trending markets can be profitable
4. **Disciplined scaling**: Strict criteria prevent emotional overtrading

### Risk Controls

1. **Maximum entries limited**: Default 3 entries prevents excessive pyramiding
2. **Position size reduction**: Each entry is smaller, limiting total exposure
3. **Price confirmation required**: Only pyramid when price moves favorably
4. **High score threshold**: Only pyramid on very strong signals (score 3+)
5. **Regime filtering**: Only pyramid in bullish/neutral markets
6. **Portfolio limit respected**: Pyramids don't count against new position limit

## Usage Examples

### Enabling/Disabling Pyramiding

```python
# In config_v3.py
PYRAMIDING_CONFIG = {
    'enabled': True,  # Set to False to disable pyramiding completely
    # ... other settings
}
```

### Adjusting Pyramid Aggressiveness

**More Conservative** (only very strong signals):
```python
PYRAMIDING_CONFIG = {
    'max_entries_per_coin': 2,           # Limit to 2 entries total
    'min_score_for_pyramid': 4,          # Only perfect scores
    'min_signal_strength_for_pyramid': 0.8,  # Very high strength
    'min_price_increase_pct': 3.0,       # Require 3% price increase
}
```

**More Aggressive** (more frequent pyramiding):
```python
PYRAMIDING_CONFIG = {
    'max_entries_per_coin': 4,           # Allow up to 4 entries
    'min_score_for_pyramid': 2,          # Lower score threshold
    'min_signal_strength_for_pyramid': 0.6,  # Lower strength threshold
    'min_price_increase_pct': 1.0,       # Only 1% price increase
}
```

### Custom Position Sizing

```python
# Equal sizing (50% each pyramid)
'position_size_multiplier': [1.0, 0.5, 0.5]

# Aggressive sizing (maintain large positions)
'position_size_multiplier': [1.0, 0.75, 0.5]

# Conservative sizing (very small pyramids)
'position_size_multiplier': [1.0, 0.3, 0.15]
```

## Testing

Run the pyramiding test suite:

```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
source .venv/bin/activate
python 001_python_code/ver3/test_pyramiding.py
```

Expected output:
```
TEST RESULTS: 4 passed, 0 failed
```

## Monitoring Pyramiding

### Check Position Details

```python
from ver3.live_executor_v3 import LiveExecutorV3

executor = LiveExecutorV3(api, logger, config)
summary = executor.get_position_summary('BTC')

print(f"Entry count: {summary['entry_count']}")
print(f"Entry prices: {summary['entry_prices']}")
print(f"Entry sizes: {summary['entry_sizes']}")
print(f"Average entry: {summary['entry_price']:,.0f} KRW")
```

### Position State File

Positions are persisted to `logs/positions_v3.json`:

```json
{
  "BTC": {
    "ticker": "BTC",
    "size": 0.00175,
    "entry_price": 50571429,
    "entry_count": 3,
    "entry_prices": [50000000, 51000000, 52000000],
    "entry_sizes": [0.001, 0.0005, 0.00025]
  }
}
```

## Backward Compatibility

The pyramiding implementation is fully backward compatible:

1. **Existing positions**: Old positions without pyramid fields load correctly
2. **Disabled mode**: Set `enabled: False` to revert to single-entry behavior
3. **State files**: Old state files are automatically upgraded on load

## Best Practices

1. **Start conservative**: Begin with default settings before adjusting
2. **Monitor performance**: Track pyramid vs non-pyramid position performance
3. **Review logs**: Check pyramid decision logs to understand trigger frequency
4. **Adjust gradually**: Change one parameter at a time to measure impact
5. **Test with dry-run**: Always test configuration changes in dry-run mode first

## Troubleshooting

### Pyramiding Not Triggering

Check these in order:

1. **Is pyramiding enabled?** `PYRAMIDING_CONFIG['enabled'] == True`
2. **Is score high enough?** Entry score >= `min_score_for_pyramid`
3. **Is signal strong enough?** Signal strength >= `min_signal_strength_for_pyramid`
4. **Has price increased?** Price must be >= `min_price_increase_pct` higher
5. **Is regime allowed?** Market regime must be in `allow_pyramid_in_regime`
6. **Check entry count**: Already at `max_entries_per_coin`?

Enable debug logging to see why pyramids are blocked:

```python
# In config_v3.py
LOGGING_CONFIG = {
    'log_level': 'DEBUG',  # Change from 'INFO' to 'DEBUG'
    # ...
}
```

### Too Many Pyramids

If pyramiding too frequently:

1. Increase `min_score_for_pyramid` (require higher scores)
2. Increase `min_signal_strength_for_pyramid` (require stronger signals)
3. Increase `min_price_increase_pct` (require larger price moves)
4. Reduce `max_entries_per_coin` (limit total entries)

## Summary

Pyramiding in Ver3 provides a sophisticated way to scale into winning positions while maintaining strict risk controls. The implementation:

- ✅ Tracks multiple entries per position
- ✅ Calculates weighted average entry prices
- ✅ Reduces position size with each pyramid
- ✅ Enforces strict entry criteria
- ✅ Maintains backward compatibility
- ✅ Persists state across restarts
- ✅ Provides detailed logging

For questions or issues, review the test suite in `test_pyramiding.py` or check the implementation in `portfolio_manager_v3.py` and `live_executor_v3.py`.
