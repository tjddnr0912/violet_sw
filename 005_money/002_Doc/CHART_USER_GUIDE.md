# Chart User Guide
## How to Use the Real-Time Chart with Technical Indicators

---

## Quick Start

### 1. Open the Chart Tab
```
빗썸 자동매매 봇 GUI
├── 거래 현황 (tab)
├── 📊 실시간 차트 (tab) ← Click here!
├── 📋 신호 히스토리 (tab)
└── 거래 내역 (tab)
```

### 2. Load the Chart
Click the **🔄 차트 새로고침** button

Wait 2-3 seconds for data to load...

### 3. Enable Indicators
Check any combination of indicators you want to see!

---

## Indicator Reference Guide

### 📊 Main Chart Overlays

#### ☐ MA (이동평균선)
**What it shows**: Moving average lines overlay on the price chart

**When to use**:
- Identify trend direction
- Find support/resistance levels
- Golden cross / Death cross signals

**What you'll see**:
- Orange line = Short-term MA (10 periods)
- Purple line = Long-term MA (30 periods)

**Trading signals**:
- ✅ BUY: Short MA crosses above Long MA
- ❌ SELL: Short MA crosses below Long MA

---

#### ☐ Bollinger Bands
**What it shows**: Volatility bands around the price

**When to use**:
- Identify overbought/oversold conditions
- Detect volatility changes
- Find potential breakouts

**What you'll see**:
- Gray dashed upper band
- Gray dashed lower band
- Shaded area between bands

**Trading signals**:
- ✅ BUY: Price touches lower band (oversold)
- ❌ SELL: Price touches upper band (overbought)
- ⚠️ BREAKOUT: Price breaks outside bands

---

### 📈 Momentum Indicators (Separate Panels)

#### ☐ RSI
**What it shows**: Relative Strength Index (0-100 scale)

**When to use**:
- Identify overbought/oversold conditions
- Detect divergences
- Confirm trend strength

**What you'll see**:
- Purple line showing RSI value
- Red line at 70 (overbought level)
- Blue line at 30 (oversold level)
- Shaded red/blue zones

**Trading signals**:
- ✅ BUY: RSI < 30 (oversold)
- ❌ SELL: RSI > 70 (overbought)
- 🔄 NEUTRAL: RSI between 30-70

---

#### ☐ MACD
**What it shows**: Moving Average Convergence Divergence

**When to use**:
- Identify trend changes
- Find momentum shifts
- Confirm entry/exit points

**What you'll see**:
- Blue line = MACD line
- Red dashed line = Signal line
- Green/Red bars = Histogram

**Trading signals**:
- ✅ BUY: MACD crosses above Signal line
- ❌ SELL: MACD crosses below Signal line
- 📊 STRENGTH: Histogram size shows momentum

---

#### ☐ Volume
**What it shows**: Trading volume over time

**When to use**:
- Confirm price movements
- Detect institutional activity
- Validate breakouts

**What you'll see**:
- Red bars = Volume on up days
- Blue bars = Volume on down days

**Trading signals**:
- ✅ STRONG: High volume + price increase
- ⚠️ WEAK: Low volume + price increase
- 🚨 ALERT: Sudden volume spike

---

### 📊 Info Box Indicators (Top-Right Corner)

#### ☐ Stochastic
**What it shows**: Momentum oscillator (K and D values)

**Information displayed**:
```
Stochastic: K=75.3, D=72.1
```

**Interpretation**:
- K > 80: Overbought
- K < 20: Oversold
- K crosses above D: Buy signal
- K crosses below D: Sell signal

---

#### ☐ ATR
**What it shows**: Average True Range (volatility measure)

**Information displayed**:
```
ATR: 125,000 (2.34%)
```

**Interpretation**:
- High ATR: High volatility (larger stop losses needed)
- Low ATR: Low volatility (tighter stop losses)
- Used for position sizing

---

#### ☐ ADX
**What it shows**: Average Directional Index (trend strength)

**Information displayed**:
```
ADX: 28.5 (강한 추세)
```

**Interpretation**:
- ADX > 25: Strong trend (use trend-following strategies)
- ADX < 20: Weak trend (use range-bound strategies)
- ADX rising: Trend strengthening
- ADX falling: Trend weakening

---

## Recommended Indicator Combinations

### 🎯 For Beginners
**Enable**: MA + RSI + Volume

**Why**: Simple trend + momentum + confirmation
- MA shows direction
- RSI shows entry timing
- Volume confirms the move

---

### 📊 For Trend Traders
**Enable**: MA + MACD + ADX + Volume

**Why**: Complete trend analysis
- MA shows trend direction
- MACD shows momentum
- ADX confirms trend strength
- Volume validates moves

---

### 🔄 For Range Traders
**Enable**: BB + RSI + Stochastic

**Why**: Overbought/oversold focus
- BB shows volatility boundaries
- RSI shows momentum extremes
- Stochastic confirms reversals

---

### 🏆 For Advanced Traders
**Enable**: All indicators

**Why**: Complete market picture
- Multiple confirmation signals
- Risk management with ATR
- Trend vs range detection with ADX

---

## Chart Controls

### Refresh Button
**🔄 차트 새로고침**
- Reloads latest market data
- Updates all indicator calculations
- Use when you want fresh data

### Indicator Checkboxes
**Real-time toggle**
- Check to show indicator
- Uncheck to hide indicator
- Chart updates immediately (no refresh needed)

---

## Tips & Best Practices

### 1. Start Simple
✅ Begin with 2-3 indicators
❌ Don't enable all indicators at once

### 2. Understand Each Indicator
✅ Learn what each indicator shows
❌ Don't just look at pretty colors

### 3. Look for Confluence
✅ Multiple indicators agreeing = stronger signal
❌ Single indicator signal = weaker

### 4. Adjust for Market Conditions
✅ Trending market: Use MA, MACD, ADX
✅ Range-bound market: Use BB, RSI, Stochastic

### 5. Use Volume for Confirmation
✅ Price + Volume = Strong signal
❌ Price alone = Weak signal

---

## Troubleshooting

### Chart doesn't load?
1. Click **🔄 차트 새로고침** button
2. Wait 2-3 seconds
3. Check if bot is connected to Bithumb
4. Verify internet connection

### Indicators not showing?
1. Make sure checkbox is CHECKED ✓
2. Try unchecking and checking again
3. Click refresh button
4. Verify data is loading (check console)

### Chart looks compressed?
1. This shouldn't happen in v3.0!
2. If it does, resize the window
3. Click refresh button
4. Report the issue

### X-axis labels overlap?
1. Resize window wider
2. Labels auto-adjust to available space
3. Maximum 12 time labels shown

---

## Understanding the Chart

### Candlestick Colors
- 🔴 **Red Candle**: Closing price HIGHER than opening price (bullish)
- 🔵 **Blue Candle**: Closing price LOWER than opening price (bearish)

### Candlestick Parts
```
     High ─┐
           │ ← Wick (thin line)
     Open ─┤
           │ ← Body (thick rectangle)
    Close ─┤
           │ ← Wick (thin line)
      Low ─┘
```

### Time Display
- Format: `MM/DD HH:MM`
- Example: `10/02 15:30`
- Shows last 100 candles
- Interval based on settings (default: 1h)

---

## Keyboard Shortcuts (Future)

Currently not implemented, but planned:
- `R` - Refresh chart
- `M` - Toggle MA
- `B` - Toggle Bollinger Bands
- `1-8` - Toggle indicators 1-8
- `A` - Toggle all indicators
- `ESC` - Close chart

---

## FAQ

### Q: Why are all indicators off by default?
**A**: Clean chart view. Enable only what you need. Less clutter = better analysis.

### Q: Can I save my indicator preferences?
**A**: Not yet implemented. Coming in future update.

### Q: How often does the chart update?
**A**: Manual refresh only. Click 🔄 button to get latest data.

### Q: Can I change indicator settings (e.g., MA periods)?
**A**: Settings are in the strategy configuration. Chart shows calculated indicators.

### Q: Why use checkboxes instead of dropdown?
**A**: Multiple indicators can be shown simultaneously. Checkboxes make this clear.

### Q: What's the difference between MA and Bollinger Bands?
**A**: MA shows average price. BB shows average ± volatility range.

### Q: Should I use all indicators?
**A**: No! Use 3-5 indicators that complement each other. Too many = confusion.

---

## Support

For help with the chart:
1. Read this guide thoroughly
2. Check `CHART_REBUILD_REPORT.md` for technical details
3. Review indicator documentation
4. Test different combinations
5. Start simple and gradually add complexity

---

**Last Updated**: 2025-10-02
**Chart Version**: 3.0 - Clean Rebuild
**Status**: Production Ready ✅

Happy Trading! 📈🚀
