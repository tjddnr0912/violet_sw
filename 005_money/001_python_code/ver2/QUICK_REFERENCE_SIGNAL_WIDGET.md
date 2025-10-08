# V2 Signal History Widget - Quick Reference

## API Usage

### 1. Add Entry Signal

```python
# New dictionary-based API
widget.add_entry_signal({
    'timestamp': datetime.now(),
    'regime': 'BULLISH',  # or 'BEARISH', 'NEUTRAL'
    'score': 3,           # 0 to 4
    'components': {
        'bb_touch': 1,       # 0 or 1
        'rsi_oversold': 1,   # 0 or 1
        'stoch_cross': 2     # 0 or 2
    },
    'price': 50000000,
    'coin': 'BTC'  # Optional, defaults to 'BTC'
})
```

**Score Calculation:**
- BB Lower Touch: +1 point
- RSI < 30: +1 point
- Stochastic Cross: +2 points
- **Total: 0 to 4 points**

### 2. Add Exit Signal

```python
widget.add_exit_signal({
    'timestamp': datetime.now(),
    'exit_type': 'FIRST_TARGET',  # or 'FINAL_TARGET', 'STOP_LOSS', 'BREAKEVEN'
    'price': 52000000,
    'pnl': 2000000,      # Absolute profit/loss
    'pnl_pct': 4.0,      # Percentage profit/loss
    'coin': 'BTC'        # Optional
})
```

### 3. Add Position Event

```python
widget.add_position_event({
    'timestamp': datetime.now(),
    'event_type': 'STOP_TRAIL',  # or 'FIRST_TARGET_HIT', 'BREAKEVEN', etc.
    'description': 'Stop trailed upward',
    'price': 51000000,
    'coin': 'BTC'  # Optional
})
```

---

## Color Scheme Reference

### Score Colors (Background)
```python
4/4: '#E6FFE6'  # Pale green
3/4: '#F0FFF0'  # Very light green
2/4: '#FFF8DC'  # Cornsilk (yellow)
1/4: '#FFE4E1'  # Misty rose (light red)
0/4: '#FFCCCC'  # Light red
```

### Text Colors
```python
BULLISH: 'green'
BEARISH: 'red'
NEUTRAL: 'gray'
Profit: '#006400' (dark green)
Loss: '#DC143C' (crimson)
Events: '#4169E1' (royal blue)
```

---

## Statistics Interpretation

### Score Distribution Example
```
[4/4] 12  [3/4] 25  [2/4] 18  [1/4] 8  [0/4] 3
```
- **4/4**: Highest quality (all conditions met)
- **3/4**: Good quality (2 major conditions)
- **2/4**: Marginal (minimum threshold)
- **1/4**: Poor quality (1 condition only)
- **0/4**: No conditions met

### Win Rate Guidelines
- **≥ 60%**: Excellent (green)
- **40-60%**: Acceptable (orange)
- **< 40%**: Needs improvement (red)

### Regime Performance
```
BULLISH: 15 (65% win)  ← Best performance in uptrend
BEARISH: 8 (40% win)   ← Strategy struggles in downtrend
NEUTRAL: 5 (50% win)   ← Mixed results
```

**Insight**: Consider only taking 3-4 score signals in BULLISH regime.

---

## Filter Combinations

### High-Probability Setup
```
최소 점수: 3
Regime: BULLISH
결과: ALL
```
Shows only high-quality signals in bullish regime (best edge).

### Performance Review
```
최소 점수: 0
Regime: ALL
결과: PROFIT
```
Study all winning trades to find common patterns.

### Low-Score Analysis
```
최소 점수: 0
Regime: ALL
결과: LOSS
```
Filter to show 0-2 scores that lost money (avoid these setups).

---

## Export Use Cases

### CSV for Spreadsheet Analysis
1. Export to CSV
2. Open in Excel/Google Sheets
3. Create pivot table:
   - Rows: Score
   - Columns: Regime
   - Values: Average of PnL %
4. Identify optimal combinations

### JSON for Backtesting
1. Export to JSON
2. Load in Python script
3. Run statistical analysis
4. Compare with backtest results
5. Optimize score thresholds

---

## Detailed Statistics Window

### Reading the Stats

#### Score Performance Section
```
점수 4/4:
  총 신호: 12개
  완료 거래: 10개
  승률: 80.0% (8승 2패)
  평균 수익률: +4.23%
```

**Interpretation**: 4/4 scores have 80% win rate with +4.23% avg profit. **This is your best setup.**

#### Regime Analysis Section
```
BULLISH:
  총 신호: 25개
  완료 거래: 20개
  승률: 65.0% (13승 7패)
  평균 수익률: +3.12%
  평균 진입 점수: 2.8/4
```

**Interpretation**: BULLISH regime signals average 2.8/4 score with 65% win rate. Focus on getting 3+ scores in BULLISH regime.

#### Component Contribution
```
BB Lower Touch (+1):
  발생 횟수: 45개
  완료 거래: 35개
  승률: 62.8%
```

**Interpretation**: BB lower touch appears in 62.8% winners. Important signal component.

---

## Integration Example

### In Trading Bot (gui_trading_bot_v2.py)

```python
# When entry is executed
if self.signal_callback:
    self.signal_callback('entry', {
        'timestamp': datetime.now(),
        'regime': self.regime,
        'score': self.entry_score,
        'components': self.entry_components,
        'price': entry_price
    })

# When exit is executed
if self.signal_callback:
    self.signal_callback('exit', {
        'timestamp': datetime.now(),
        'exit_type': exit_type,
        'price': exit_price,
        'pnl': pnl,
        'pnl_pct': pnl_pct
    })

# When position event occurs
if self.signal_callback:
    self.signal_callback('event', {
        'timestamp': datetime.now(),
        'event_type': 'STOP_TRAIL',
        'description': f"Stop: ${old_stop:.0f} → ${new_stop:.0f}",
        'price': current_price
    })
```

---

## Common Tasks

### View Only High-Quality Signals
1. Set "최소 점수: 3"
2. Result shows 3/4 and 4/4 scores only

### Analyze Bullish Regime Performance
1. Set "Regime: BULLISH"
2. Click "📊 상세 통계"
3. Review BULLISH section

### Find Best Combination
1. Click "📊 상세 통계"
2. Scroll to "⭐ 최적 조합 분석"
3. Review "BULLISH + 3-4점" stats

### Export for Analysis
1. Click "💾 CSV 내보내기"
2. Save file
3. Open in spreadsheet
4. Create charts and pivot tables

### Clear Old Data
1. Click "🗑️ 기록 삭제"
2. Confirm deletion
3. Start fresh session

---

## Troubleshooting

### Issue: Statistics show 0%
**Cause**: No completed trades yet (all pending)
**Solution**: Wait for exits to occur

### Issue: Filter shows no results
**Cause**: No signals match filter criteria
**Solution**: Reset filters with "필터 초기화"

### Issue: Export fails
**Cause**: No signals to export
**Solution**: Generate some signals first

### Issue: Widget looks different
**Cause**: May be using old version
**Solution**: Verify using `signal_history_widget_v2.py`

---

## Performance Tips

### For Better Statistics
- Let widget accumulate 50+ signals before analyzing
- Focus on completed trades (not pending)
- Compare score 3-4 vs 0-2 win rates

### For Optimal Trading
- Use "최소 점수: 3" filter regularly
- Check regime win rates in detailed stats
- Only trade BULLISH + 3-4 score setups

### For Data Management
- Export to CSV weekly for records
- Keep max 200 signals in memory (auto-limited)
- Archive old exports for historical analysis

---

## Quick Test

```bash
# Run standalone test
cd /Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2
python test_signal_widget_v2.py
```

Generates 20 sample signals to test all features.

---

## Support

**File Location**: `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2/signal_history_widget_v2.py`

**Documentation**:
- `SIGNAL_WIDGET_V2_ENHANCEMENTS.md` - Detailed feature documentation
- `IMPLEMENTATION_CHECKLIST.md` - Implementation verification
- `QUICK_REFERENCE_SIGNAL_WIDGET.md` - This file

**Test Script**: `test_signal_widget_v2.py`
