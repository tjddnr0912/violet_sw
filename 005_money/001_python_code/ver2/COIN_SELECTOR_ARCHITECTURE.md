# Coin Selector Architecture & Data Flow

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         GUI Layer (Tkinter)                      │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ Tab 1: 거래 현황 (Trading Status)                          │  │
│  │                                                             │  │
│  │  ┌─────────────────────────────────────────────┐          │  │
│  │  │ 💰 거래 코인 선택 Panel                      │          │  │
│  │  │                                              │          │  │
│  │  │  거래 코인: [BTC ▼]  [변경]                 │          │  │
│  │  │              │         │                     │          │  │
│  │  │              │         └──────┐              │          │  │
│  │  │              │                │              │          │  │
│  │  │         Dropdown       Change Button         │          │  │
│  │  │        (Combobox)      (Command)             │          │  │
│  │  │              │                │              │          │  │
│  │  └──────────────┼────────────────┼──────────────┘          │  │
│  │                 │                │                          │  │
│  └─────────────────┼────────────────┼──────────────────────────┘  │
│                    │                │                             │
│         <<ComboboxSelected>>  on_coin_changed()                  │
│                    │                │                             │
│                    ▼                ▼                             │
│              Separator       change_coin()                        │
│              Check           ┌────────────┐                       │
│                              │ Validation │                       │
│                              └────┬───────┘                       │
│                                   │                               │
└───────────────────────────────────┼───────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Validation Layer                            │
│                                                                   │
│  1. Check separator selection                                    │
│  2. Check if already selected                                    │
│  3. Check bot running state                                      │
│  4. Check position open state                                    │
│  5. Validate symbol in AVAILABLE_COINS                           │
│  6. Show confirmation dialog                                     │
│                                                                   │
│  If any check fails: ──────────────┐                             │
│     - Show error message            │                             │
│     - Revert dropdown               │                             │
│     - Return without change         │                             │
└─────────────────────────────────────┼───────────────────────────┘
                                      │
                                      │ All checks passed ✓
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Configuration Update Layer                     │
│                                                                   │
│  config_v2.set_symbol_in_config(new_symbol)                     │
│      ├─ Updates TRADING_CONFIG['symbol']                        │
│      └─ Returns updated config dict                             │
│                                                                   │
│  self.config = config_v2.get_version_config()                   │
│      └─ Reloads entire config with new symbol                   │
│                                                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Bot Update Layer                            │
│                                                                   │
│  if self.bot:                                                    │
│      self.bot.symbol = new_symbol                                │
│          └─ Updates GUITradingBotV2 instance                     │
│                                                                   │
│  Bot now fetches data for new coin in:                           │
│      - update_regime_filter()   → Daily candlesticks             │
│      - check_entry_signals()    → 4H candlesticks                │
│      - manage_position()        → 4H candlesticks                │
│                                                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GUI State Update Layer                        │
│                                                                   │
│  self.coin_status_var.set(f"현재: {new_symbol}")                │
│  self.current_coin_var.set(new_symbol)                          │
│  self.root.title(f"...Strategy v2.0 - {mode} - {new_symbol}")  │
│                                                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Tab Refresh Layer                             │
│                   refresh_all_tabs()                             │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Tab 1: Trading Status                                       │ │
│  │   - update_current_price()      → Fetch new coin price     │ │
│  │   - Clear entry_score                                       │ │
│  │   - Clear entry_components                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Tab 2: Real-time Chart                                      │ │
│  │   chart_widget.coin_symbol = new_symbol                     │ │
│  │   chart_widget.update_chart()                               │ │
│  │       └─ Fetches new coin's candlestick data                │ │
│  │       └─ Recalculates indicators (BB, RSI, Stoch RSI, ATR)  │ │
│  │       └─ Redraws chart canvas                               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Tab 3: Multi-Timeframe Charts                               │ │
│  │   multi_chart_widget.coin_symbol = new_symbol               │ │
│  │   multi_chart_widget.load_all_data()                        │ │
│  │       └─ Fetches 24h candlesticks (Daily)                   │ │
│  │       └─ Fetches 12h candlesticks                           │ │
│  │       └─ Fetches 4h candlesticks                            │ │
│  │       └─ Fetches 1h candlesticks                            │ │
│  │       └─ Redraws all 4 charts in 2x2 grid                   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Tab 4: Score Monitoring                                     │ │
│  │   score_monitoring_widget.clear_scores()                    │ │
│  │       └─ Clears score_checks deque                          │ │
│  │       └─ Resets statistics display                          │ │
│  │       └─ Clears graph (if open)                             │ │
│  │       └─ Deletes persisted JSON file                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Tab 5: Signal History                                       │ │
│  │   signal_history_widget.clear_signals()                     │ │
│  │       └─ Clears signals list                                │ │
│  │       └─ Clears treeview display                            │ │
│  │       └─ Resets statistics                                  │ │
│  │       └─ Deletes persisted JSON file                        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
                    Success Notification
                           │
                           ▼
          ┌────────────────────────────────────┐
          │  messagebox.showinfo()              │
          │  "거래 코인이 {coin}(으)로          │
          │   변경되었습니다."                  │
          └─────────────────────────────────────┘
```

---

## Component Interaction Diagram

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│              │         │              │         │              │
│   Dropdown   │────────▶│ change_coin()│────────▶│  config_v2   │
│  (Combobox)  │ Select  │   Method     │ Update  │   Module     │
│              │         │              │         │              │
└──────────────┘         └──────┬───────┘         └──────┬───────┘
                                │                        │
                                │ Validate               │ Get Config
                                │                        │
                                ▼                        ▼
                    ┌───────────────────────────────────────┐
                    │     Validation Checks (6 layers)      │
                    │  1. Separator check                   │
                    │  2. Already selected check            │
                    │  3. Bot running check                 │
                    │  4. Position open check               │
                    │  5. Symbol validity check             │
                    │  6. User confirmation                 │
                    └─────────────┬─────────────────────────┘
                                  │
                                  │ All Passed ✓
                                  │
        ┌─────────────────────────┴──────────────────────────┐
        │                                                     │
        ▼                                                     ▼
┌───────────────┐                                   ┌────────────────┐
│  Bot Instance │                                   │  GUI Variables │
│               │                                   │                │
│  .symbol      │◀───── Update                      │  coin_status   │
│               │                                   │  current_coin  │
│               │                                   │  window_title  │
└───────────────┘                                   └────────────────┘
        │
        │ New Symbol Set
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│                    Tab Refresh Cascade                        │
│                                                               │
│  Tab 1 ──▶ Tab 2 ──▶ Tab 3 ──▶ Tab 4 ──▶ Tab 5              │
│   │         │         │         │         │                  │
│   │         │         │         │         │                  │
│   ▼         ▼         ▼         ▼         ▼                  │
│ Price    Chart   MultiChart  Scores   Signals                │
│ Update   Reload    Reload     Clear    Clear                 │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Flow Sequence

### Step-by-Step Flow

```
User Action                  System Response
───────────────────────────────────────────────────────────────
1. Click Dropdown           → Show 428 items
                              (10 popular + separator + 417 others)

2. Select "ETH"             → on_coin_changed() triggered
                              - Check if separator? NO
                              - Allow selection

3. Click "변경" button      → change_coin() triggered
                              ├─ Validate not separator? ✓
                              ├─ Validate not already selected? ✓
                              ├─ Validate bot not running? ✓
                              ├─ Validate no position open? ✓
                              ├─ Validate symbol valid? ✓
                              └─ Show confirmation dialog

4. User clicks "예"         → Confirmation received
                              ├─ config_v2.set_symbol_in_config('ETH')
                              │   └─ TRADING_CONFIG['symbol'] = 'ETH'
                              │
                              ├─ self.config = get_version_config()
                              │   └─ Reload all config sections
                              │
                              ├─ self.bot.symbol = 'ETH'
                              │   └─ Bot will use ETH in API calls
                              │
                              ├─ Update GUI variables
                              │   ├─ coin_status_var = "현재: ETH"
                              │   ├─ current_coin_var = "ETH"
                              │   └─ window title += "- ETH"
                              │
                              └─ refresh_all_tabs()

5. refresh_all_tabs()       → Sequential tab updates:

   Tab 1:
   ├─ update_current_price()
   │   └─ get_ticker('ETH')  → Fetch ETH price
   │   └─ Display: "5,100,000 KRW"
   │
   ├─ Clear entry_score = 0
   └─ Clear entry_components = {...}

   Tab 2:
   ├─ chart_widget.coin_symbol = 'ETH'
   ├─ chart_widget.update_chart()
   │   ├─ fetch_chart_data('4h', 'ETH')
   │   ├─ calculate_indicators(ETH_df)
   │   └─ draw_chart() → Redraw with ETH data
   └─ Chart displays ETH candlesticks

   Tab 3:
   ├─ multi_chart_widget.coin_symbol = 'ETH'
   ├─ multi_chart_widget.load_all_data()
   │   ├─ Fetch 24h ETH candles
   │   ├─ Fetch 12h ETH candles
   │   ├─ Fetch 4h ETH candles
   │   ├─ Fetch 1h ETH candles
   │   └─ Redraw all 4 charts
   └─ All charts display ETH data

   Tab 4:
   ├─ score_monitoring_widget.clear_scores()
   │   ├─ score_checks.clear()
   │   ├─ update_statistics() → Show 0 checks
   │   └─ Delete JSON file
   └─ Fresh start for ETH score tracking

   Tab 5:
   ├─ signal_history_widget.clear_signals()
   │   ├─ signals.clear()
   │   ├─ Clear treeview
   │   ├─ update_statistics() → Show 0 signals
   │   └─ Delete JSON file
   └─ Fresh start for ETH signal history

6. Success notification      → messagebox.showinfo()
                              "거래 코인이 ETH(으)로 변경되었습니다."

7. Console log               → Log messages appear:
                              "⏳ 코인 변경 중: BTC → ETH"
                              "✅ Bot symbol updated to ETH"
                              "🔄 모든 탭 새로고침 중..."
                              "  - 거래 현황 새로고침"
                              "  - 실시간 차트 새로고침"
                              "  - 멀티 타임프레임 차트 새로고침"
                              "  - 점수 모니터링 초기화"
                              "  - 신호 히스토리 초기화"
                              "✅ 모든 탭 새로고침 완료"
                              "✅ 코인 변경 완료: ETH"

8. UI updates complete       → All visible elements now show ETH:
                              ✓ Dropdown: [ETH ▼]
                              ✓ Status: "현재: ETH"
                              ✓ Window title: "...v2.0 - DRY-RUN - ETH"
                              ✓ Trading status: "거래 코인: ETH"
                              ✓ Current price: "5,100,000 KRW"
                              ✓ All charts: ETH candlesticks
```

---

## Error Recovery Flow

```
Error Scenario                Recovery Action
───────────────────────────────────────────────────────────────
Separator selected          → Revert dropdown to current coin
                              No error message

Same coin selected          → Show info: "이미 {coin} 사용 중"
                              Dropdown stays same

Bot running                 → Show warning: "봇 정지 필요"
                              Revert dropdown to current coin

Position open               → Show warning: "포지션 청산 필요"
                              Revert dropdown to current coin

Invalid coin                → Show error: "Symbol not supported"
                              Revert dropdown to current coin

User cancels                → Revert dropdown to current coin
                              No changes made

Network error               → Show error: "코인 변경 실패"
                              Revert dropdown to current coin
                              Config unchanged

Tab refresh error           → Log warning in console
                              Continue with other tabs
                              Show partial success message
```

---

## State Machine Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Initial State                             │
│                                                              │
│  - Dropdown: BTC                                             │
│  - Config: symbol = 'BTC'                                    │
│  - Bot: symbol = 'BTC'                                       │
│  - All tabs: BTC data                                        │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   │ User selects ETH
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  Validation State                            │
│                                                              │
│  Checks:                                                     │
│  - Not separator?          ✓                                 │
│  - Not already selected?   ✓                                 │
│  - Bot not running?        ✓                                 │
│  - No position open?       ✓                                 │
│  - Symbol valid?           ✓                                 │
│  - User confirms?          ?                                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
         ┌─────────┴────────┐
         │                  │
    User clicks         User clicks
       "예"                "아니오"
         │                  │
         ▼                  ▼
┌─────────────────┐   ┌──────────────────┐
│  Transition     │   │   Abort State    │
│    State        │   │                  │
│                 │   │ - Revert dropdown│
│ - Update config │   │ - No changes     │
│ - Update bot    │   │ - Return to      │
│ - Update GUI    │   │   Initial State  │
│ - Refresh tabs  │   └──────────────────┘
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                     Final State                              │
│                                                              │
│  - Dropdown: ETH                                             │
│  - Config: symbol = 'ETH'                                    │
│  - Bot: symbol = 'ETH'                                       │
│  - All tabs: ETH data                                        │
│  - Score/Signal history: Cleared                             │
└──────────────────────────────────────────────────────────────┘
```

---

## Module Dependencies

```
gui_app_v2.py
    │
    ├─ Imports config_v2
    │   ├─ AVAILABLE_COINS (427 coins)
    │   ├─ POPULAR_COINS (10 coins)
    │   ├─ TRADING_CONFIG dict
    │   ├─ validate_symbol(coin) function
    │   ├─ set_symbol_in_config(coin) function
    │   └─ get_version_config() function
    │
    ├─ Uses GUITradingBotV2
    │   └─ .symbol attribute (updated on coin change)
    │
    ├─ Uses ChartWidgetV2
    │   ├─ .coin_symbol attribute
    │   └─ .update_chart() method
    │
    ├─ Uses MultiChartWidgetV2
    │   ├─ .coin_symbol attribute
    │   └─ .load_all_data() method
    │
    ├─ Uses ScoreMonitoringWidgetV2
    │   └─ .clear_scores() method
    │
    └─ Uses SignalHistoryWidgetV2
        └─ .clear_signals() method
```

---

## API Call Flow

```
Coin Change (BTC → ETH)
    │
    ├─ Immediate API Calls:
    │   └─ update_current_price()
    │       └─ get_ticker('ETH')
    │           └─ Bithumb API: /public/ticker/ETH_KRW
    │
    ├─ Chart Refresh API Calls:
    │   │
    │   ├─ Tab 2 (ChartWidgetV2):
    │   │   └─ fetch_chart_data('4h', 'ETH')
    │   │       └─ get_candlestick('ETH', '4h')
    │   │           └─ Bithumb API: /public/candlestick/ETH_KRW/4h
    │   │
    │   └─ Tab 3 (MultiChartWidgetV2):
    │       ├─ get_candlestick('ETH', '24h')
    │       │   └─ Bithumb API: /public/candlestick/ETH_KRW/24h
    │       │
    │       ├─ get_candlestick('ETH', '12h')
    │       │   └─ Bithumb API: /public/candlestick/ETH_KRW/12h
    │       │
    │       ├─ get_candlestick('ETH', '4h')
    │       │   └─ Bithumb API: /public/candlestick/ETH_KRW/4h
    │       │
    │       └─ get_candlestick('ETH', '1h')
    │           └─ Bithumb API: /public/candlestick/ETH_KRW/1h
    │
    └─ Total: 6 API calls during coin change
```

---

## Memory Management

```
Before Coin Change              After Coin Change
─────────────────────           ─────────────────
BTC candlestick data            → Released
BTC indicator calculations      → Released
BTC score check history         → Cleared
BTC signal history              → Cleared
BTC chart canvases              → Redrawn

                                ETH candlestick data      → Loaded
                                ETH indicator calculations → Calculated
                                ETH score check history    → Empty (fresh)
                                ETH signal history         → Empty (fresh)
                                ETH chart canvases         → Rendered

Net Memory Impact: Minimal (<10 MB increase)
```

---

## Performance Bottlenecks

```
Operation                        Estimated Time    Bottleneck
─────────────────────────────────────────────────────────────────
Validation checks                < 10ms            CPU (negligible)
Config update                    < 5ms             Disk I/O
GUI state update                 < 5ms             UI thread
API calls (6 total)              2-4 seconds       Network latency
Chart rendering (5 charts)       1-2 seconds       CPU (matplotlib)
Widget clearing                  < 100ms           Memory ops

Total Time: 3-6 seconds
Primary Bottleneck: Network API calls
```

---

## Thread Safety

```
Main GUI Thread (Tkinter)
    ├─ change_coin() executes here
    ├─ Dropdown events handled here
    ├─ All widget updates here
    └─ API calls here (blocking)

Bot Thread (if running)
    ├─ analyze_market() runs independently
    ├─ Uses self.bot.symbol (thread-safe read)
    └─ Blocked during coin change (bot must be stopped)

Note: No concurrent access to bot.symbol because:
- Coin change requires bot to be stopped
- Once changed, bot restarts with new symbol
- No race conditions possible
```

---

## Summary

The coin selector architecture follows a **layered validation** approach:
1. **UI Layer**: User interaction with dropdown
2. **Validation Layer**: 6-level safety checks
3. **Config Layer**: Persistent symbol update
4. **Bot Layer**: Runtime symbol update
5. **Refresh Layer**: Cascading tab updates

This ensures **safe, atomic, all-or-nothing** coin changes with complete data integrity.
