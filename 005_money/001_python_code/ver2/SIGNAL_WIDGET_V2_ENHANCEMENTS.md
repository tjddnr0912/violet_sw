# V2 Signal History Widget - Enhanced Design Summary

## Overview

The v2 signal history widget has been completely redesigned to showcase v2's unique **0-4 point entry scoring system** with modern visual design, comprehensive statistics, and powerful analysis tools.

---

## Key Enhancements

### 1. Visual Design Improvements

#### Score-Based Color Coding
- **4/4 points**: Dark green background (excellent signals)
- **3/4 points**: Light green background (good signals)
- **2/4 points**: Yellow/orange background (marginal signals)
- **1/4 points**: Light red background (poor signals)
- **0/4 points**: Red background (very poor signals)

#### Regime Color Coding
- **BULLISH**: Green text
- **BEARISH**: Red text
- **NEUTRAL**: Gray text

#### Profit/Loss Display
- **Profitable trades**: Dark green text with + prefix
- **Losing trades**: Crimson text
- **Events**: Royal blue text

### 2. Enhanced Column Layout

New column structure optimized for v2 data:

| Column | Content | Description |
|--------|---------|-------------|
| **시간** | YYYY-MM-DD HH:MM | Timestamp of signal |
| **점수** | 0/4 to 4/4 | Entry score with visual indicator |
| **구성요소** | BB(+1), RSI(+1), Stoch(+2) | Score breakdown showing which components triggered |
| **Regime** | BULLISH/BEARISH/NEUTRAL | Market regime at signal time |
| **코인** | BTC, ETH, etc. | Trading pair |
| **가격** | Formatted price | Entry/exit price |
| **유형** | ENTRY/EXIT/EVENT | Signal type |
| **결과** | +5.23% ($26,150) | P&L with both percentage and absolute value |

### 3. Advanced Statistics Panel

#### Row 1: Overall Metrics
- **총 신호**: Total entry signals count
- **평균 점수**: Average entry score (X.XX/4)
- **총 거래**: Completed trades
- **전체 성공률**: Win rate (color-coded: green ≥60%, orange 40-60%, red <40%)

#### Row 2: Score Distribution
Visual display of score frequency:
```
[4/4] 12  [3/4] 25  [2/4] 18  [1/4] 8  [0/4] 3
```
Each score shows colored badge + count

#### Row 3: Regime Distribution
- **BULLISH**: Count + win rate (e.g., "15 (65% win)")
- **BEARISH**: Count + win rate
- **NEUTRAL**: Count

### 4. Powerful Filter System

Three independent filters:
1. **최소 점수**: Show only signals with score ≥ X (0, 2, 3, 4)
2. **Regime**: Filter by BULLISH/BEARISH/NEUTRAL/ALL
3. **결과**: Show only PROFIT/LOSS/PENDING/ALL

**"필터 초기화"** button resets all filters to defaults.

### 5. Detailed Statistics Window

Click **"📊 상세 통계"** button to view comprehensive analysis:

#### Score Performance Analysis
For each score (0-4):
- Total signals
- Completed trades
- Win rate with W-L record
- Average profit percentage

Example output:
```
점수 4/4:
  총 신호: 12개
  완료 거래: 10개
  승률: 80.0% (8승 2패)
  평균 수익률: +4.23%
```

#### Regime-Based Analysis
For each regime:
- Total signals
- Win rate
- Average P&L
- Average entry score

#### Component Contribution Analysis
Shows effectiveness of each scoring component:
- **BB Lower Touch (+1)**: Occurrence rate, win rate
- **RSI Oversold (+1)**: Occurrence rate, win rate
- **Stochastic Cross (+2)**: Occurrence rate, win rate

#### Best Combination Analysis
Identifies most profitable patterns:
- **4/4 Perfect Score**: All conditions met
- **BULLISH + 3-4점**: Optimal combination analysis

### 6. Export Capabilities

#### CSV Export
Exports to spreadsheet-compatible format with columns:
```
Timestamp, Type, Score, BB Touch, RSI Oversold, Stoch Cross,
Regime, Coin, Price, Exit Type, PnL, PnL %, Description
```
Perfect for Excel/Google Sheets analysis.

#### JSON Export
Exports with metadata:
```json
{
  "export_time": "2025-10-04T12:30:00",
  "version": "v2",
  "total_signals": 50,
  "signals": [...]
}
```

### 7. Sortable Columns (Placeholder)

Column headers are clickable for future sorting implementation.

---

## Technical Improvements

### Code Quality
- **Increased max signals**: 100 → 200 for better historical analysis
- **Dictionary-based API**: Methods now accept `Dict[str, Any]` for flexibility
- **Auto-save**: Signals automatically saved to `logs/signals_v2.json`
- **Auto-load**: Previous session loaded on startup
- **Error handling**: Graceful handling of missing tree items during filtering

### Integration Changes

Updated `gui_app_v2.py` to pass full dictionaries instead of individual parameters:

**Before:**
```python
widget.add_entry_signal(timestamp, regime, score, components, price)
```

**After:**
```python
widget.add_entry_signal({
    'timestamp': timestamp,
    'regime': regime,
    'score': score,
    'components': components,
    'price': price,
    'coin': 'BTC'
})
```

---

## Usage Examples

### Test the Widget
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2
python test_signal_widget_v2.py
```

This generates 20 sample signals with realistic data to showcase all features.

### Integration in GUI App
The widget is automatically integrated in `gui_app_v2.py` tab 3 ("신호 히스토리").

### Filter Usage
1. Select **"최소 점수: 3"** to see only high-quality signals
2. Select **"Regime: BULLISH"** to analyze bullish-only performance
3. Select **"결과: PROFIT"** to study winning trades only

### Export Workflow
1. Click **"💾 CSV 내보내기"**
2. Open in Excel/Google Sheets
3. Create pivot tables for custom analysis
4. Filter by score, regime, date ranges

---

## Visual Comparison: V1 vs V2

### V1 Signal History
- Generic weighted signal display
- Simple columns: Time, Type, Regime, Action, Price
- Basic statistics
- No score breakdown
- No filtering

### V2 Signal History (Enhanced)
- **Score-based color coding** (0-4 visual indicators)
- **Detailed columns**: Score breakdown showing BB/RSI/Stoch contributions
- **Advanced statistics**: Score distribution, regime analysis, component effectiveness
- **Powerful filtering**: By score, regime, result
- **Detailed stats window**: Win rate by score, optimal combinations
- **CSV/JSON export**: For external analysis
- **Regime-aware insights**: Bullish vs bearish performance comparison

---

## Design Philosophy

1. **Information Density**: Show more data without overwhelming the user
2. **Visual Hierarchy**: Use color to communicate signal quality instantly
3. **Actionable Insights**: Help traders understand which signal combinations work best
4. **Data Export**: Enable external analysis in spreadsheets or custom tools
5. **Professional Aesthetics**: Modern, clean design with proper spacing and typography

---

## Future Enhancements (Potential)

- [ ] Actual column sorting implementation
- [ ] Charts/graphs for score distribution
- [ ] Real-time filtering without refresh
- [ ] Export to PDF with formatted reports
- [ ] Integration with backtesting results
- [ ] Alert system for high-score signals
- [ ] Custom score thresholds per regime

---

## Files Modified

1. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2/signal_history_widget_v2.py` - Complete redesign
2. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2/gui_app_v2.py` - Updated integration (lines 600-622)
3. `/Users/seongwookjang/project/git/violet_sw/005_money/001_python_code/ver2/test_signal_widget_v2.py` - New test script

---

## Color Scheme Reference

```python
score_colors = {
    4: '#006400',  # Dark green (excellent)
    3: '#32CD32',  # Light green (good)
    2: '#FFA500',  # Orange (marginal)
    1: '#FF6347',  # Tomato red (poor)
    0: '#DC143C'   # Crimson red (very poor)
}

# Background colors for tree rows
'score_4': '#E6FFE6'  # Light green background
'score_3': '#F0FFF0'  # Very light green
'score_2': '#FFF8DC'  # Cornsilk (yellow)
'score_1': '#FFE4E1'  # Misty rose (light red)
'score_0': '#FFCCCC'  # Light red

# Text colors
'profit': '#006400'   # Dark green
'loss': '#DC143C'     # Crimson
'event': '#4169E1'    # Royal blue
'regime_bullish': '#008000'  # Green
'regime_bearish': '#FF0000'  # Red
'regime_neutral': '#808080'  # Gray
```

---

## Summary

The enhanced v2 signal history widget transforms signal tracking from simple logging into a powerful analysis tool. By clearly displaying the 0-4 point scoring system with color coding and providing comprehensive statistics, traders can:

1. **Quickly identify high-quality signals** (3-4 points)
2. **Understand which components contribute to success** (BB, RSI, Stoch)
3. **Analyze regime-specific performance** (Bullish vs Bearish)
4. **Export data for deeper analysis** (CSV/JSON)
5. **Make data-driven decisions** about which signals to trust

This redesign makes the v2 signal history widget visually distinct from v1 while providing actionable insights that help traders optimize their strategy.
