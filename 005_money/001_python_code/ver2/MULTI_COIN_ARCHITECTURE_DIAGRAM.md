# Multi-Coin Architecture: Visual Diagrams

**Version:** 2.0
**Date:** 2025-10-08

---

## System Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                          GUI APPLICATION (Tkinter)                      │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  Tab 0: Portfolio Overview                                       │  │
│  │  ┌────────────────────┐  ┌──────────────────────────────────┐  │  │
│  │  │ Coin Selector      │  │ Portfolio Table                  │  │  │
│  │  │ ☑ BTC  ☑ ETH      │  │ BTC │ BULL │ 3/4 │ 0.0015 │ +50K │  │  │
│  │  │ ☑ XRP  ☐ SOL      │  │ ETH │ BULL │ 4/4 │ 0.025  │ +75K │  │  │
│  │  └────────────────────┘  └──────────────────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  Tab 1: Trading Status  │  Tab 2: Chart  │  Tab 3: Multi-TF  ...       │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ↓
┌────────────────────────────────────────────────────────────────────────┐
│                      PORTFOLIO MANAGER V2                               │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  analyze_all() → ThreadPoolExecutor                              │  │
│  │    ├── CoinMonitor(BTC).analyze()  ┐                            │  │
│  │    ├── CoinMonitor(ETH).analyze()  ├─── Parallel Execution      │  │
│  │    └── CoinMonitor(XRP).analyze()  ┘                            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  make_portfolio_decision()                                       │  │
│  │    ├── Check portfolio limits (2/2 positions?)                  │  │
│  │    ├── Prioritize entry signals (by score)                      │  │
│  │    └── Return: [(XRP, BUY), (BTC, BUY)]                         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  execute_decisions()                                             │  │
│  │    └── Delegate to LiveExecutorV2                               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ↓                               ↓
┌──────────────────────────────────┐  ┌─────────────────────────────────┐
│       STRATEGY V2                │  │    LIVE EXECUTOR V2             │
│  (Stateless, Coin-Agnostic)      │  │  (Position Tracking Per Coin)   │
│                                  │  │                                 │
│  analyze_market(coin, interval)  │  │  positions: Dict[str, Position] │
│    ├── Fetch 24h (regime)        │  │    ├── 'BTC' → Position(...)   │
│    ├── Fetch 4h  (entry)         │  │    ├── 'ETH' → Position(...)   │
│    ├── Calculate indicators      │  │    └── 'XRP' → Position(...)   │
│    ├── Score entry signals       │  │                                 │
│    └── Return analysis dict      │  │  execute_order(ticker, action)  │
│                                  │  │  close_position(ticker)         │
│                                  │  │  update_stop_loss(ticker)       │
└──────────────────────────────────┘  └─────────────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ↓
                    ┌───────────────────────────────┐
                    │      BITHUMB API              │
                    │                               │
                    │  get_candlestick(coin, int)   │
                    │  place_buy_order(coin, units) │
                    │  place_sell_order(coin, units)│
                    └───────────────────────────────┘
```

---

## Component Interaction Flow

### 1. Bot Startup & Initialization

```
User Starts Bot
      │
      ↓
Load Config (config_v2.py)
  ├── PORTFOLIO_CONFIG: max_positions=2, default_coins=['BTC','ETH','XRP']
  ├── TRADING_CONFIG: trade_amount_krw=50000
  └── EXECUTION_CONFIG: dry_run=True/False
      │
      ↓
Load Saved Preferences (user_preferences_v2.json)
  └── selected_coins: ['BTC', 'ETH']  (user's last selection)
      │
      ↓
Initialize Components
  ├── BithumbAPI (with API keys from env vars)
  ├── TradingLogger (logs to logs/trading_YYYYMMDD.log)
  ├── StrategyV2 (shared instance, stateless)
  ├── LiveExecutorV2 (shared executor, multi-coin positions)
  └── PortfolioManagerV2
        ├── Creates CoinMonitor for each selected coin
        └── Ready for analysis
      │
      ↓
Start Bot Thread
  └── Run portfolio_loop() every 60 seconds
```

---

### 2. Analysis Loop (Every 60 Seconds)

```
Timer Tick (60s)
      │
      ↓
portfolio_manager.analyze_all()
      │
      ├─────────────────────────────────────────┐
      │ ThreadPoolExecutor (max_workers=3)      │
      │                                         │
      ├── Submit: monitor_BTC.analyze()        │
      ├── Submit: monitor_ETH.analyze()        │
      └── Submit: monitor_XRP.analyze()        │
      │                                         │
      │  ┌─────── Parallel Execution ────────┐ │
      │  │                                    │ │
      │  │  BTC: strategy.analyze_market()   │ │
      │  │    ├── Fetch 24h candles          │ │
      │  │    ├── Calc EMA 50/200            │ │
      │  │    ├── Regime: BULLISH ✓          │ │
      │  │    ├── Fetch 4h candles           │ │
      │  │    ├── Calc BB, RSI, Stoch        │ │
      │  │    ├── Score: 3/4 (BB✓ RSI✓ St✓)  │ │
      │  │    └── Return: {action: BUY}      │ │
      │  │                                    │ │
      │  │  ETH: strategy.analyze_market()   │ │
      │  │    ├── ... (same process)         │ │
      │  │    ├── Regime: BULLISH ✓          │ │
      │  │    ├── Score: 4/4 (all signals)   │ │
      │  │    └── Return: {action: BUY}      │ │
      │  │                                    │ │
      │  │  XRP: strategy.analyze_market()   │ │
      │  │    ├── ... (same process)         │ │
      │  │    ├── Regime: BEARISH ✗          │ │
      │  │    └── Return: {action: HOLD}     │ │
      │  │                                    │ │
      │  └────────────────────────────────────┘ │
      │                                         │
      └─────────────────────────────────────────┘
      │
      ↓ (results collected)
{
  'BTC': {action: 'BUY', score: 3, strength: 0.75, regime: 'bullish'},
  'ETH': {action: 'BUY', score: 4, strength: 1.00, regime: 'bullish'},
  'XRP': {action: 'HOLD', score: 1, regime: 'bearish'}
}
```

---

### 3. Portfolio Decision Making

```
Results from analyze_all()
      │
      ↓
portfolio_manager.make_portfolio_decision(results)
      │
      ├─ Step 1: Count Current Positions
      │    └─ Check executor.positions: {'SOL': Position(...)}
      │    └─ total_positions = 1
      │
      ├─ Step 2: Get Portfolio Limits
      │    └─ max_positions = 2 (from config)
      │    └─ Available slots = 2 - 1 = 1
      │
      ├─ Step 3: Filter Entry Candidates
      │    └─ BTC: action=BUY, no position ✓
      │    └─ ETH: action=BUY, no position ✓
      │    └─ XRP: action=HOLD ✗ (skip)
      │    └─ Candidates: [(BTC, 3/4), (ETH, 4/4)]
      │
      ├─ Step 4: Prioritize by Score
      │    └─ Sort by (entry_score, signal_strength)
      │    └─ Priority: [ETH (4/4), BTC (3/4)]
      │
      ├─ Step 5: Apply Portfolio Limit
      │    └─ Slot 1: ETH (score 4/4) ✓
      │    └─ Slot 2: Would be BTC, but limit reached!
      │    └─ Log: "Portfolio limit (2 positions), skipping BTC"
      │
      └─ Return: [(ETH, BUY)]  ← Only 1 decision (limit enforced)
```

**Key Decision Logic:**

```python
if total_positions >= max_positions:
    break  # Stop adding entries

# Prioritization
candidates.sort(key=lambda x: (x[1]['entry_score'], x[1]['signal_strength']), reverse=True)
```

---

### 4. Order Execution

```
Decisions: [(ETH, BUY)]
      │
      ↓
portfolio_manager.execute_decisions(decisions)
      │
      └── For each (coin, action):
            │
            ├── Get Analysis Data
            │     ├── price = 3,800,000 KRW
            │     ├── stop_loss = 3,700,000 KRW (from analysis)
            │     └── score = 4/4
            │
            ├── Calculate Position Size
            │     ├── trade_amount = 50,000 KRW (from config)
            │     └── units = 50,000 / 3,800,000 = 0.01315 ETH
            │
            ├── Execute via LiveExecutorV2
            │     │
            │     ├── executor.execute_order(
            │     │     ticker='ETH',
            │     │     action='BUY',
            │     │     units=0.01315,
            │     │     price=3,800,000,
            │     │     dry_run=False  # LIVE MODE
            │     │   )
            │     │
            │     ├─── If LIVE MODE:
            │     │     ├── Call Bithumb API: place_buy_order()
            │     │     ├── Response: {status: '0000', order_id: 'ABC123'}
            │     │     └── Log: "✅ LIVE ORDER: ABC123"
            │     │
            │     └─── If DRY-RUN:
            │           ├── Simulate order
            │           └── Log: "💚 DRY-RUN: Simulated buy"
            │
            ├── Update Position State (Thread-Safe)
            │     │
            │     └── executor._update_position_after_trade()
            │           │
            │           ├── Acquire lock: with self._position_lock:
            │           ├── Create Position object:
            │           │     Position(
            │           │       ticker='ETH',
            │           │       size=0.01315,
            │           │       entry_price=3,800,000,
            │           │       entry_time=datetime.now(),
            │           │       stop_loss=3,700,000
            │           │     )
            │           ├── Save: self.positions['ETH'] = position
            │           ├── Persist to JSON: positions_v2.json
            │           └── Release lock
            │
            └── Update Stop-Loss
                  └── executor.update_stop_loss('ETH', 3,700,000)
                        └── positions['ETH'].stop_loss = 3,700,000
```

---

### 5. Position Tracking (LiveExecutorV2)

**positions_v2.json Structure:**

```json
{
  "SOL": {
    "ticker": "SOL",
    "size": 0.05,
    "entry_price": 200000,
    "entry_time": "2025-10-08T10:15:32",
    "stop_loss": 194000,
    "highest_high": 205000,
    "position_pct": 100.0,
    "first_target_hit": false,
    "second_target_hit": false
  },
  "ETH": {
    "ticker": "ETH",
    "size": 0.01315,
    "entry_price": 3800000,
    "entry_time": "2025-10-08T10:32:18",
    "stop_loss": 3700000,
    "highest_high": 3800000,
    "position_pct": 100.0,
    "first_target_hit": false,
    "second_target_hit": false
  }
}
```

**Position Operations:**

```
executor.has_position('BTC')
  └── Check: 'BTC' in self.positions
  └── Return: False

executor.get_position('ETH')
  └── Return: Position(ticker='ETH', size=0.01315, ...)

executor.get_position_summary('ETH')
  └── Return: {
        'has_position': True,
        'ticker': 'ETH',
        'size': 0.01315,
        'entry_price': 3800000,
        'stop_loss': 3700000,
        ...
      }
```

---

### 6. GUI Update Flow

```
Portfolio Manager: get_portfolio_summary()
      │
      ↓
{
  'total_positions': 2,
  'max_positions': 2,
  'total_pnl_krw': 125000,
  'coins': {
    'BTC': {
      'analysis': {regime: 'bullish', score: 3, ...},
      'position': {has_position: False, ...}
    },
    'ETH': {
      'analysis': {regime: 'bullish', score: 4, ...},
      'position': {has_position: True, size: 0.01315, entry: 3800000, ...}
    },
    'XRP': {
      'analysis': {regime: 'bearish', score: 1, ...},
      'position': {has_position: False, ...}
    }
  }
}
      │
      ↓ (Thread-Safe GUI Update)
root.after(0, update_portfolio_gui, summary)
      │
      ↓
Update Portfolio Overview Widget
  ├── Stats Panel:
  │     ├── Positions: "2 / 2"
  │     ├── Total P&L: "+125,000 KRW" (green)
  │     └── Risk: "4.2% / 6.0%"
  │
  └── Coin Table:
        ┌──────┬─────────┬───────┬──────────┬──────────┬─────────┐
        │ Coin │ Regime  │ Score │ Position │ Entry    │ P&L     │
        ├──────┼─────────┼───────┼──────────┼──────────┼─────────┤
        │ BTC  │ 🟢 BULL │ 3/4   │ -        │ -        │ -       │
        │ ETH  │ 🟢 BULL │ 4/4   │ 0.01315  │ 3,800,000│ +75,000 │
        │ XRP  │ 🔴 BEAR │ 1/4   │ -        │ -        │ -       │
        └──────┴─────────┴───────┴──────────┴──────────┴─────────┘
```

---

## Thread Safety Architecture

### Critical Sections (Require Locking)

```
┌─────────────────────────────────────────────────────────────┐
│              THREAD SAFETY MAP                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Position Updates (LiveExecutorV2)                       │
│     ┌──────────────────────────────────────────────────┐   │
│     │  _update_position_after_trade()                  │   │
│     │    with self._position_lock:  ← LOCK ACQUIRED    │   │
│     │      self.positions[ticker] = ...                │   │
│     │      self._save_positions()   ← Atomic write     │   │
│     └──────────────────────────────────────────────────┘   │
│                                                             │
│  2. Parallel Analysis (Portfolio Manager)                   │
│     ┌──────────────────────────────────────────────────┐   │
│     │  ThreadPoolExecutor (max_workers=3)              │   │
│     │    - Each CoinMonitor operates on SEPARATE data │   │
│     │    - No shared state during analysis            │   │
│     │    - Results collected in thread-safe manner    │   │
│     └──────────────────────────────────────────────────┘   │
│                                                             │
│  3. GUI Updates (Main Thread Only)                          │
│     ┌──────────────────────────────────────────────────┐   │
│     │  root.after(0, callback, data)  ← Thread-safe    │   │
│     │    - All Tkinter ops in main thread             │   │
│     │    - No direct widget updates from bot thread   │   │
│     └──────────────────────────────────────────────────┘   │
│                                                             │
│  4. Log Queue (Thread-Safe by Design)                       │
│     ┌──────────────────────────────────────────────────┐   │
│     │  queue.Queue(maxsize=5000)                       │   │
│     │    - put_nowait() from any thread               │   │
│     │    - get() from GUI thread                       │   │
│     └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Race Condition Prevention

**Scenario 1: Simultaneous Position Updates**

```
Thread 1 (BTC Monitor)          Thread 2 (ETH Monitor)
       │                                │
       ├── execute_order(BTC)           ├── execute_order(ETH)
       │                                │
       ├── _update_position_after_trade(BTC)
       │    │                           ├── _update_position_after_trade(ETH)
       │    ├── LOCK ACQUIRED            │    ├── WAITING FOR LOCK... ⏳
       │    ├── positions['BTC'] = ...   │    │
       │    ├── _save_positions()        │    │
       │    └── LOCK RELEASED            │    │
       │                                │    ├── LOCK ACQUIRED
       │                                │    ├── positions['ETH'] = ...
       │                                │    ├── _save_positions()
       │                                │    └── LOCK RELEASED
       ↓                                ↓
    ✅ BTC position saved           ✅ ETH position saved
```

**Without lock:**
```
positions['BTC'] = ...
                                  positions['ETH'] = ...  ← Overwrites!
_save_positions()  ← Only ETH saved, BTC lost! ❌
```

---

## Data Flow: Entry Signal to Execution

```
┌─────────────────────────────────────────────────────────────────┐
│                  ENTRY SIGNAL FLOW (ETH Example)                │
└─────────────────────────────────────────────────────────────────┘

1. Market Analysis
   ├── Fetch 24h: ETH candlestick data (250 candles)
   ├── Calculate: EMA(50) = 3,900,000, EMA(200) = 3,500,000
   └── Regime: EMA50 > EMA200 → BULLISH ✓

2. Entry Signal Detection (4H Timeframe)
   ├── Fetch 4h: ETH candlestick data (200 candles)
   ├── Calculate Indicators:
   │     ├── BB: upper=3,850K, mid=3,800K, lower=3,750K
   │     ├── RSI: 28 (oversold ✓)
   │     ├── Stoch RSI: K=15, D=18 (cross + oversold ✓)
   │     └── ATR: 50,000 (volatility measure)
   │
   └── Score Entry Conditions:
         ├── BB Touch: low (3,745K) <= lower (3,750K) → +1 point ✓
         ├── RSI < 30: 28 < 30 → +1 point ✓
         ├── Stoch Cross: K(15) crossed D(18) below 20 → +2 points ✓
         └── Total Score: 4/4 ← STRONG ENTRY SIGNAL

3. Portfolio Decision
   ├── Check Positions: 1/2 (SOL already held)
   ├── Available Slots: 1 ← Can enter 1 more
   ├── Candidates: [ETH (4/4), BTC (3/4)]
   ├── Prioritize: ETH (higher score)
   └── Decision: (ETH, BUY) ✓

4. Position Sizing
   ├── Trade Amount: 50,000 KRW (from config)
   ├── Current Price: 3,800,000 KRW
   └── Units: 50,000 / 3,800,000 = 0.01315 ETH

5. Risk Management
   ├── ATR: 50,000 KRW
   ├── Chandelier Stop: Highest High - (ATR × 3)
   │     = 3,800,000 - (50,000 × 3)
   │     = 3,650,000 KRW
   └── Stop-Loss: 3,650,000 KRW

6. Order Execution (LIVE MODE)
   ├── API Call: POST /trade/market_buy
   │     ├── Payload: {
   │     │     order_currency: 'ETH',
   │     │     payment_currency: 'KRW',
   │     │     units: 0.01315,
   │     │     type: 'market'
   │     │   }
   │     └── Response: {
   │           status: '0000',  ← Success
   │           order_id: 'ETH_20251008103218_ABC123'
   │         }
   │
   ├── Create Position:
   │     Position(
   │       ticker='ETH',
   │       size=0.01315,
   │       entry_price=3,800,000,
   │       entry_time='2025-10-08 10:32:18',
   │       stop_loss=3,650,000,
   │       highest_high=3,800,000
   │     )
   │
   └── Save State: positions_v2.json updated ✓

7. GUI Notification
   ├── Log: "✅ ETH position opened: 0.01315 @ 3,800,000 KRW"
   ├── Update Portfolio Table:
   │     ETH │ 🟢 BULL │ 4/4 │ 0.01315 │ 3,800,000 │ 0
   └── Signal History: "Entry: ETH, Score 4/4, Price 3,800,000"
```

---

## Configuration Hierarchy

```
┌─────────────────────────────────────────────────────────────────┐
│                    CONFIGURATION LAYERS                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Layer 1: Common Config (lib/core/config_common.py)            │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  LOGGING_CONFIG, API_CONFIG (shared across versions)      │ │
│  └───────────────────────────────────────────────────────────┘ │
│                           ↓ (merged)                           │
│                                                                 │
│  Layer 2: Version Config (ver2/config_v2.py)                   │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  TIMEFRAME_CONFIG: {execution: '4h', regime: '24h'}       │ │
│  │  REGIME_FILTER_CONFIG: {ema_fast: 50, ema_slow: 200}      │ │
│  │  ENTRY_SCORING_CONFIG: {min_score: 2, rules: {...}}       │ │
│  │  INDICATOR_CONFIG: {bb_period: 20, rsi: 14, ...}          │ │
│  │  PORTFOLIO_CONFIG: {max_positions: 2, default_coins: [...]}│ │
│  │  TRADING_CONFIG: {trade_amount_krw: 50000}                │ │
│  │  EXECUTION_CONFIG: {mode: 'live', dry_run: True}          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                           ↓ (merged)                           │
│                                                                 │
│  Layer 3: Runtime Override (optional, via args)                │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  --interval 1h  → Overrides TIMEFRAME_CONFIG              │ │
│  │  --mode live    → Overrides EXECUTION_CONFIG              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                           ↓ (final config)                     │
│                                                                 │
│  Layer 4: User Preferences (persisted, GUI-driven)             │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  user_preferences_v2.json:                                │ │
│  │    {                                                       │ │
│  │      "selected_coins": ["BTC", "ETH", "XRP"],             │ │
│  │      "last_tab": 1,                                       │ │
│  │      "window_size": [1400, 850]                           │ │
│  │    }                                                       │ │
│  └───────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘

Usage in Code:
config = config_v2.get_version_config(interval='4h', mode='live')
  → Returns merged config with all layers applied
```

---

## Error Handling & Resilience

```
┌─────────────────────────────────────────────────────────────────┐
│                   ERROR HANDLING STRATEGY                       │
└─────────────────────────────────────────────────────────────────┘

1. API Failures (Network/Rate Limit)
   ┌─────────────────────────────────────────────────────────────┐
   │  try:                                                       │
   │    df = get_candlestick(coin, '4h')                        │
   │  except RequestException as e:                             │
   │    logger.error(f"API failed for {coin}: {e}")             │
   │    return {action: 'HOLD', reason: f'API error: {e}'}      │
   │                                                             │
   │  Result: Coin skipped for this cycle, others continue ✓    │
   └─────────────────────────────────────────────────────────────┘

2. Analysis Failures (Insufficient Data)
   ┌─────────────────────────────────────────────────────────────┐
   │  if df is None or len(df) < 200:                           │
   │    return {action: 'HOLD', reason: 'Insufficient data'}    │
   │                                                             │
   │  Result: Safe fallback to HOLD, no crash ✓                 │
   └─────────────────────────────────────────────────────────────┘

3. Order Execution Failures
   ┌─────────────────────────────────────────────────────────────┐
   │  order_result = executor.execute_order(...)                │
   │  if not order_result.get('success'):                       │
   │    logger.error(f"Order failed: {order_result['message']}") │
   │    return  # Don't create position                         │
   │                                                             │
   │  Result: Position only created if order succeeds ✓         │
   └─────────────────────────────────────────────────────────────┘

4. Thread Execution Failures
   ┌─────────────────────────────────────────────────────────────┐
   │  with ThreadPoolExecutor() as executor:                    │
   │    futures = {executor.submit(analyze, coin): coin}        │
   │    for future in as_completed(futures):                    │
   │      try:                                                  │
   │        result = future.result()                            │
   │      except Exception as e:                                │
   │        logger.error(f"Thread failed: {e}")                 │
   │        results[coin] = {action: 'HOLD', reason: 'Error'}   │
   │                                                             │
   │  Result: One coin's failure doesn't crash others ✓         │
   └─────────────────────────────────────────────────────────────┘

5. GUI Update Failures
   ┌─────────────────────────────────────────────────────────────┐
   │  try:                                                       │
   │    root.after(0, update_gui, data)                         │
   │  except Exception as e:                                     │
   │    logger.error(f"GUI update failed: {e}")                 │
   │    # Bot continues, GUI just not updated                   │
   │                                                             │
   │  Result: Trading continues even if GUI breaks ✓            │
   └─────────────────────────────────────────────────────────────┘
```

---

## Performance Metrics

```
┌─────────────────────────────────────────────────────────────────┐
│                  EXPECTED PERFORMANCE (3 Coins)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Analysis Time:                                                │
│    ├── Single coin (sequential):  ~3-4 seconds                │
│    ├── 3 coins (sequential):      ~9-12 seconds               │
│    └── 3 coins (parallel):        ~4-5 seconds   ← 60% faster │
│                                                                 │
│  API Calls (per 60s cycle):                                    │
│    ├── Regime (24h):  3 calls (BTC, ETH, XRP)                 │
│    ├── Entry (4h):    3 calls (BTC, ETH, XRP)                 │
│    └── Total:         6 calls/min  (Limit: 20/min) ✓          │
│                                                                 │
│  Memory Usage:                                                 │
│    ├── Single coin:   ~50 MB                                  │
│    └── 3 coins:       ~150 MB  (linear scaling) ✓             │
│                                                                 │
│  GUI Responsiveness:                                           │
│    ├── Update latency:  <100ms  (main thread)                 │
│    ├── Chart rendering: ~200ms  (matplotlib)                  │
│    └── User input lag:  <50ms   (Tkinter event loop) ✓        │
│                                                                 │
│  Position Tracking:                                            │
│    ├── JSON write time:  <10ms  (positions_v2.json)           │
│    └── Lock contention:  <1ms   (rare simultaneous updates)   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Deployment Checklist

```
┌─────────────────────────────────────────────────────────────────┐
│                     PRE-DEPLOYMENT CHECKLIST                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [ ] Code Implementation                                        │
│      [✓] portfolio_manager_v2.py created                       │
│      [✓] CoinMonitor class implemented                         │
│      [✓] Thread safety locks added to LiveExecutorV2           │
│      [✓] PORTFOLIO_CONFIG added to config_v2.py                │
│      [✓] GUI widgets created (coin selector, portfolio table)  │
│      [✓] gui_app_v2.py integrated with portfolio manager       │
│                                                                 │
│  [ ] Testing                                                    │
│      [✓] Unit tests: test_portfolio_manager.py                 │
│      [✓] Dry-run: 2 coins (BTC, ETH) × 24 hours               │
│      [✓] Dry-run: 3 coins (BTC, ETH, XRP) × 24 hours          │
│      [✓] Portfolio limits tested (max 2 positions)             │
│      [✓] Thread safety validated (no deadlocks)                │
│                                                                 │
│  [ ] Configuration                                              │
│      [✓] PORTFOLIO_CONFIG.max_positions set correctly          │
│      [✓] EXECUTION_CONFIG.dry_run = True for testing           │
│      [✓] API keys in environment variables                     │
│      [✓] User preferences file created                         │
│                                                                 │
│  [ ] Documentation                                              │
│      [✓] MULTI_COIN_ARCHITECTURE_ANALYSIS.md reviewed          │
│      [✓] MULTI_COIN_QUICK_START.md followed                    │
│      [✓] Code comments added                                   │
│      [✓] User guide updated                                    │
│                                                                 │
│  [ ] Rollout Plan                                               │
│      [ ] Phase 1: Small positions (10K KRW × 2 coins)          │
│      [ ] Phase 2: Increase to 3 coins                          │
│      [ ] Phase 3: Normal position sizes (50K KRW)              │
│      [ ] Monitoring: 48-hour intensive observation             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Comparison: Before vs. After

```
┌─────────────────────────────────────────────────────────────────┐
│                 SINGLE-COIN vs. MULTI-COIN                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  BEFORE (Single Coin):                                          │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  • Monitor: 1 coin (BTC)                                  │ │
│  │  • Analysis: Sequential (60s)                             │ │
│  │  • Positions: 1 max                                       │ │
│  │  • Risk: 2% per trade                                     │ │
│  │  • Opportunities: Limited (1 coin × 4H = ~6 signals/day)  │ │
│  │  • Diversification: None                                  │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  AFTER (Multi-Coin):                                            │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  • Monitor: 3 coins (BTC, ETH, XRP)                       │ │
│  │  • Analysis: Parallel (<5s)                               │ │
│  │  • Positions: 2 max (portfolio limit)                     │ │
│  │  • Risk: 6% portfolio (3× 2% per coin)                    │ │
│  │  • Opportunities: 3× more (3 coins × 4H = ~18 signals/day)│ │
│  │  • Diversification: Yes (uncorrelated coins)              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  Benefits:                                                      │
│    ✅ 3× more entry opportunities                              │
│    ✅ Portfolio-level risk management                          │
│    ✅ Better capital utilization                               │
│    ✅ Diversification reduces volatility                       │
│    ✅ Entry prioritization (best signals first)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Dependency Graph

```
ver2/gui_app_v2.py
    ├── imports: portfolio_manager_v2.py
    │     ├── imports: strategy_v2.py
    │     │     ├── imports: lib/api/bithumb_api.py
    │     │     └── imports: lib/core/logger.py
    │     ├── imports: live_executor_v2.py
    │     │     ├── imports: lib/api/bithumb_api.py
    │     │     └── imports: lib/core/logger.py
    │     └── imports: config_v2.py
    │           └── imports: lib/core/config_common.py
    │
    ├── imports: widgets/coin_selector_widget.py
    ├── imports: widgets/portfolio_overview_widget.py
    ├── imports: chart_widget_v2.py
    ├── imports: signal_history_widget_v2.py
    └── imports: score_monitoring_widget_v2.py

Key Dependencies:
  • PortfolioManagerV2 depends on: StrategyV2, LiveExecutorV2, config_v2
  • StrategyV2 is stateless (no dependencies on executor)
  • LiveExecutorV2 is multi-coin ready (already supports Dict[str, Position])
  • GUI widgets depend on PortfolioManagerV2 for data
```

---

**End of Architecture Diagrams**

For implementation details, see:
- **MULTI_COIN_ARCHITECTURE_ANALYSIS.md** - Comprehensive analysis
- **MULTI_COIN_QUICK_START.md** - Step-by-step implementation guide
