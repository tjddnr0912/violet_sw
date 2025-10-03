# Bitcoin Multi-Timeframe Strategy v2 - GUI Documentation

## Overview

The v2 GUI maintains the **exact 5-tab layout** from v1 while integrating all v2-specific features:

- **Daily EMA Regime Filter** (EMA 50/200 Golden/Death Cross)
- **4H Score-Based Entry System** (3+ points required)
- **Chandelier Exit** trailing stop (3x ATR)
- **Position Scaling** (50% at BB mid, 100% at BB upper)

## Quick Start

### Method 1: Python Launcher (Recommended)
```bash
cd 005_money/001_python_code/ver2
python run_gui_v2.py
```

### Method 2: Direct Launch
```bash
cd 005_money/001_python_code
python -m ver2.gui_app_v2
```

### Method 3: From Project Root
```bash
cd 005_money
python 001_python_code/ver2/run_gui_v2.py
```

## GUI Layout

### Tab 1: 거래 현황 (Trading Status) - MAIN TAB

**Left Column:**
- 🔍 **시장 상태 (Market Regime)**
  - Regime: BULLISH/BEARISH/NEUTRAL
  - EMA 50/200 values
  - Trading permission status

- 🎯 **진입 신호 점수 (Entry Score)**
  - Total score (0-4 points)
  - BB Lower Touch (+1)
  - RSI Oversold (+1)
  - Stoch RSI Cross (+2)
  - Entry threshold: 3+ points

- 💼 **포지션 상태 (Position State)**
  - Position phase (INITIAL_ENTRY/RISK_FREE_RUNNER/NONE)
  - Entry price
  - Position size
  - First target status

**Right Column:**
- 📊 **거래 상태 (Trading Status)**
  - Current coin (BTC)
  - Current price
  - Execution interval (4H)
  - Last action

- 📉 **Chandelier Exit**
  - Stop loss price
  - ATR multiplier (3.0x)
  - Highest high
  - Breakeven status

- 💰 **수익 현황 (Profit/Loss)**
  - Total profit
  - Win rate
  - Total trades

**Bottom Console:**
- Real-time log messages
- System events
- Trading decisions

### Tab 2: 📊 실시간 차트 (Real-time Chart)

**Features:**
- Timeframe selector (1h, 4h, 1d)
- Indicator toggles:
  - ✓ EMA (50/200)
  - ✓ Bollinger Bands
  - ✓ RSI
  - ✓ Stochastic RSI
  - ✓ ATR
- Refresh button
- Multi-subplot layout (price + indicators)

**Chart Subplots:**
1. **Main Chart**: Candlesticks + BB + EMA
2. **RSI**: 14-period RSI with 30/70 levels
3. **Stoch RSI**: %K and %D lines with 20/80 levels
4. **ATR**: 14-period ATR

### Tab 3: 📊 멀티 타임프레임 (Multi Timeframe)

**Status:** Placeholder (Coming Soon)
- Will display 3-column multi-timeframe analysis
- Daily/4H/1H synchronized view

### Tab 4: 📋 신호 히스토리 (Signal History)

**Statistics Header:**
- Total signals count
- Average entry score
- Bullish regime signal count
- Success rate

**Signal Table:**
- Time: Signal timestamp
- Type: ENTRY/EXIT/EVENT
- Regime: Market regime at signal time
- Score: Entry score (0-4)
- Components: Score breakdown (BB+1, RSI+1, Stoch+2)
- Price: Signal price
- Result: P&L percentage

**Features:**
- Double-click for detailed view
- Export to JSON
- Clear history
- Automatic filtering

### Tab 5: 📜 거래 내역 (Transaction History)

**Transaction Table:**
- Time: Transaction timestamp
- Type: BUY/SELL
- Price: Execution price
- Amount: Order size
- Total: Total value
- P&L: Profit/loss

## v2-Specific Features

### Regime Filter Display
- **BULLISH** (Green): EMA 50 > EMA 200
  - Trading allowed
  - Entry signals evaluated
  - Full position management

- **BEARISH** (Red): EMA 50 ≤ EMA 200
  - Trading blocked
  - No new entries
  - Exit-only mode

- **NEUTRAL** (Gray): Insufficient data
  - Waiting for data
  - No trading

### Entry Score Components

**Score Calculation:**
```
Total Score = BB Touch + RSI Oversold + Stoch Cross
              (0-1)      (0-1)         (0-2)
Minimum Required: 3 points
```

**Component Details:**
1. **BB Lower Touch (+1)**
   - Low ≤ BB Lower
   - Mean reversion zone
   - Frequency: 2-3x/month

2. **RSI Oversold (+1)**
   - RSI < 30
   - Momentum exhaustion
   - Frequency: 1-2x/month

3. **Stoch RSI Cross (+2)**
   - %K crosses above %D
   - Both in oversold (<20)
   - Timing signal
   - Frequency: 3-5x/month

### Position Phases

**1. INITIAL_ENTRY**
- Just entered position (50%)
- Chandelier stop active
- Watching for first target

**2. RISK_FREE_RUNNER**
- First target hit (BB mid)
- 50% exited
- Stop moved to breakeven
- Trailing remaining 50%

**3. NONE**
- No position
- Waiting for entry signal

### Chandelier Exit Tracking

**Display Information:**
- **Stop Price**: Current trailing stop level
- **ATR Multiplier**: Fixed at 3.0x
- **Highest High**: Peak price since entry
- **Breakeven Status**: Moved/Not Moved

**Stop Calculation:**
```
Stop = Highest High - (ATR × 3.0)
```

**Behavior:**
- Trails upward only (never down)
- Moves to breakeven after first target
- Protects profits automatically

## File Structure

```
ver2/
├── gui_app_v2.py              # Main GUI application
├── chart_widget_v2.py         # Chart visualization
├── signal_history_widget_v2.py # Signal tracking
├── gui_trading_bot_v2.py      # Bot integration adapter
├── run_gui_v2.py              # Launcher script
├── GUI_README.md              # This file
│
├── backtrader_strategy_v2.py  # Backtrader strategy (for backtesting)
├── config_v2.py               # v2 configuration
├── regime_filter_v2.py        # Daily EMA filter
├── entry_signals_v2.py        # Entry scoring
├── position_manager_v2.py     # Position management
├── indicators_v2.py           # Indicator calculations
└── risk_manager_v2.py         # Risk controls
```

## Architecture

### Real-Time vs Backtesting

**Backtesting Mode** (main_v2.py):
- Uses backtrader framework
- Event-driven architecture
- Historical data replay
- Precise execution simulation

**GUI Mode** (gui_trading_bot_v2.py):
- Live market data fetching
- Manual indicator calculation
- Real-time decision making
- Simulates v2 strategy logic

### Data Flow

```
API (Bithumb)
    ↓
GUI Trading Bot
    ↓
[Regime Filter] → Daily EMA 50/200 → Bullish/Bearish
    ↓
[Entry Signals] → 4H Score System → 3+ points?
    ↓
[Position Manager] → Entry/Scaling/Exit
    ↓
GUI Display → Status Updates
```

## Important Notes

### Regime Filter Behavior
- **Hysteresis**: Regime change requires 2 consecutive bars confirmation
- **Trading Permission**: Only BULLISH allows new entries
- **Existing Positions**: Managed even in BEARISH regime

### Entry Signal Quality
- **Perfect Setup (4 points)**: All components aligned (rare, 1-2x/month)
- **Strong Setup (3 points)**: Minimum threshold (3-5x/month)
- **Quality over Quantity**: Stability-focused approach

### Position Scaling Logic
```
Entry: 50% position at entry
  ↓
BB Mid reached: Exit 50% (lock profit)
  ↓
Move stop to breakeven (risk-free)
  ↓
BB Upper reached: Exit remaining 50% (final target)
OR
Chandelier stop hit: Exit remaining 50% (trailing stop)
```

### Risk Management
- **Max Risk**: 2% per trade
- **Initial Entry**: 50% of calculated size
- **Stop Loss**: 3x ATR below highest high
- **Breakeven**: Auto-move after first target

## Troubleshooting

### GUI Won't Launch
```bash
# Check dependencies
python run_gui_v2.py  # Auto-checks and reports missing packages

# Manual check
python -c "import tkinter, pandas, numpy, matplotlib"
```

### Import Errors
```bash
# From ver2 directory
cd 005_money/001_python_code/ver2
python run_gui_v2.py  # Handles paths automatically

# Or set PYTHONPATH
export PYTHONPATH=/path/to/005_money/001_python_code:$PYTHONPATH
python -m ver2.gui_app_v2
```

### No Market Data
- Check Bithumb API connectivity
- Verify internet connection
- Check API rate limits

### Chart Not Updating
- Click "🔄 새로고침" button
- Toggle timeframe to force refresh
- Check console for errors

## Comparison: v1 vs v2 GUI

### Layout (IDENTICAL)
✓ Same 5-tab structure
✓ Same 2-column main layout
✓ Same console position and size
✓ Same control panel

### Content (DIFFERENT)
**v1 Shows:**
- 8 indicators (MA, RSI, BB, MACD, Volume, Stoch, ATR, ADX)
- Weighted signal system
- Market regime detection (Trending/Ranging)

**v2 Shows:**
- Daily EMA regime filter (Golden/Death Cross)
- 4H score-based entry (BB/RSI/Stoch)
- Chandelier Exit trailing stop
- Position scaling phases

### Philosophy
**v1:** Multi-indicator confluence, gradual signals
**v2:** Regime-filtered, score-based, stability-first

## Advanced Usage

### Testing Without Trading
The GUI operates in **simulation mode** by default:
- Fetches live data
- Calculates signals
- Shows decisions
- No actual orders placed

### Logging
Console messages show:
- Regime changes
- Entry signals with score breakdown
- Position state transitions
- Stop movements
- Exit executions

### Signal Export
Signal history can be exported to JSON:
1. Go to "📋 신호 히스토리" tab
2. Click "💾 내보내기"
3. Select file location
4. Analyze in external tools

## Future Enhancements

- [ ] Live trading integration (with risk controls)
- [ ] Multi-timeframe chart synchronization
- [ ] Performance analytics dashboard
- [ ] Alert notifications (sound/desktop)
- [ ] Strategy parameter tuning interface
- [ ] Position size calculator
- [ ] Backtest comparison view

## Support

For issues or questions:
1. Check logs in console panel
2. Verify configuration in config_v2.py
3. Test components individually:
   ```bash
   python -m ver2.gui_trading_bot_v2  # Test bot
   python -m ver2.chart_widget_v2     # Test chart
   ```

---

**Version:** 2.0
**Last Updated:** 2025-10-03
**Maintained By:** Trading Bot Team
