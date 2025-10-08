# Multi-Coin Trading Architecture Analysis & Recommendations

**Document Version:** 1.0
**Date:** 2025-10-08
**Author:** Project-Leader Agent
**Target:** Ver2 Trading Bot Multi-Coin Enhancement

---

## Executive Summary

This document provides a comprehensive architectural analysis for extending the current single-coin ver2 trading bot to support simultaneous trading of 2-3 cryptocurrencies (BTC, ETH, XRP, SOL). After evaluating multiple architectural approaches, **Option C: Portfolio Manager Pattern** is recommended as the optimal solution, balancing implementation complexity, maintainability, and functionality.

**Key Recommendation:**
- **Recommended Approach:** Portfolio Manager Pattern (Option C)
- **Estimated Effort:** Medium (3-5 days implementation)
- **Code Complexity:** Moderate increase (30-40% more code)
- **Risk Level:** Low-Medium (well-established pattern)

---

## 1. Current Architecture Overview

### 1.1 System Components Analysis

**Core Components:**

```
ver2/
├── gui_app_v2.py              # Main GUI application (single coin dropdown)
├── gui_trading_bot_v2.py      # Trading bot adapter (single coin instance)
├── strategy_v2.py             # Strategy analysis (stateless, coin-agnostic)
├── live_executor_v2.py        # Order execution & position tracking
├── config_v2.py               # Configuration (SELECTED_COIN='BTC')
└── chart_widget_v2.py         # Chart display (single coin)
```

**Key Architectural Characteristics:**

1. **Single Coin State Management**
   - `GUITradingBotV2`: Manages one active coin (`self.symbol`)
   - 60-second analysis loop for one market only
   - Single position tracking (`self.position`)

2. **Strategy Engine (Coin-Agnostic)**
   - `StrategyV2.analyze_market(coin_symbol)` - **stateless**
   - Takes coin symbol as parameter, returns analysis dict
   - No internal coin state ✅ (Good for multi-coin)

3. **Live Executor (Position-Per-Coin)**
   - `LiveExecutorV2`: Already supports multi-coin positions!
   - Uses `Dict[str, Position]` - keyed by ticker
   - State persistence in `positions_v2.json`
   - **Already multi-coin ready!** ✅

4. **GUI Structure**
   - 6-tab layout: Trading Status, Chart, Multi-TF, Score Monitor, Signals, History
   - Single coin dropdown selector
   - Status panels designed for one coin at a time

### 1.2 Current Limitations for Multi-Coin

| Component | Limitation | Impact |
|-----------|-----------|--------|
| **GUITradingBotV2** | Single `self.symbol` instance variable | Only monitors one coin |
| **Analysis Loop** | Sequential 60s loop, one coin only | No parallel monitoring |
| **GUI Layout** | Single coin dropdown, status for 1 coin | Cannot display multiple coins |
| **Configuration** | `SELECTED_COIN` global setting | Only one active coin |
| **Chart Widget** | Single coin price data | Cannot compare coins |

### 1.3 Existing Multi-Coin Support (Partial)

**Already Multi-Coin Ready:**
- ✅ `StrategyV2.analyze_market(coin_symbol)` - stateless, accepts any coin
- ✅ `LiveExecutorV2` - tracks positions per ticker in dict
- ✅ `BithumbAPI` - coin-agnostic API methods
- ✅ `AVAILABLE_COINS = ['BTC', 'ETH', 'XRP', 'SOL']` - config already defined

**Needs Extension:**
- ❌ `GUITradingBotV2` - single coin instance
- ❌ GUI display - single coin status panels
- ❌ Analysis loop - sequential, not parallel
- ❌ Configuration management - single coin selection

---

## 2. Architectural Design Options

### Option A: Multi-Instance Approach

**Concept:** Create multiple `GUITradingBotV2` instances, one per coin.

```python
class MultiCoinManager:
    def __init__(self, coins: List[str]):
        self.bots = {
            coin: GUITradingBotV2(coin=coin)
            for coin in coins
        }
        self.threads = {}

    def start_all(self):
        for coin, bot in self.bots.items():
            thread = threading.Thread(target=bot.run)
            thread.start()
            self.threads[coin] = thread
```

**Pros:**
- ✅ Minimal code changes to existing `GUITradingBotV2`
- ✅ Perfect isolation between coins (no interference)
- ✅ Easy to debug (each bot is independent)
- ✅ Can run different strategies per coin

**Cons:**
- ❌ High resource usage (3 threads × 60s loops = potential timing conflicts)
- ❌ No portfolio-level risk management
- ❌ Difficult to coordinate decisions (e.g., "don't enter BTC if ETH already at max risk")
- ❌ GUI complexity: Need to display 3 independent bot states
- ❌ Shared executor could have race conditions

**Risk Assessment:** Medium-High
- Thread safety issues with shared `LiveExecutorV2`
- Difficult to implement portfolio limits (e.g., max 2 positions total)
- No central decision-making

**Verdict:** ❌ Not recommended for 2-3 coins (better for 10+ coins with microservices)

---

### Option B: Single-Instance Multi-Coin Loop

**Concept:** Modify existing bot to handle multiple coins in one instance.

```python
class GUITradingBotV2:
    def __init__(self, coins: List[str]):
        self.coins = coins
        self.positions = {coin: None for coin in coins}
        self.coin_states = {coin: {} for coin in coins}

    def analyze_market(self):
        for coin in self.coins:
            self._analyze_coin(coin)

    def _analyze_coin(self, coin: str):
        # Existing logic, but parameterized by coin
        df = get_candlestick(coin, '4h')
        # ... rest of analysis
```

**Pros:**
- ✅ Single thread, simpler resource management
- ✅ Easy to implement portfolio-level decisions
- ✅ Can prioritize coins (e.g., analyze BTC first)
- ✅ Centralized state in one object

**Cons:**
- ❌ Sequential analysis (slow if coins increase)
- ❌ Blocking: if one coin API call hangs, all coins wait
- ❌ Hard to extend GUI (designed for single coin)
- ❌ Large refactor of `GUITradingBotV2` class (500+ lines)

**Threading Enhancement:**
```python
def analyze_market(self):
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(self._analyze_coin, coin): coin
            for coin in self.coins
        }
        for future in as_completed(futures):
            coin = futures[future]
            result = future.result()
            self._process_result(coin, result)
```

**Risk Assessment:** Medium
- GUI refactor is non-trivial
- ThreadPoolExecutor adds complexity
- Error handling tricky (one coin failure shouldn't crash all)

**Verdict:** ⚠️ Possible, but messy refactor of existing code

---

### Option C: Portfolio Manager Pattern (RECOMMENDED)

**Concept:** Create a new `PortfolioManager` class that delegates to existing components.

```python
class CoinMonitor:
    """Wrapper around strategy analysis for one coin"""
    def __init__(self, coin: str, strategy: StrategyV2, executor: LiveExecutorV2):
        self.coin = coin
        self.strategy = strategy
        self.executor = executor
        self.state = {}  # Regime, score, etc.

    def analyze(self) -> Dict[str, Any]:
        """Run strategy analysis for this coin"""
        result = self.strategy.analyze_market(self.coin, interval='4h')
        self.state = result
        return result

    def has_position(self) -> bool:
        return self.executor.has_position(self.coin)


class PortfolioManagerV2:
    """Centralized manager for multi-coin trading"""
    def __init__(self, coins: List[str], config: Dict[str, Any]):
        self.coins = coins
        self.config = config

        # Shared components
        self.strategy = StrategyV2(config)
        self.executor = LiveExecutorV2(api, logger, config)

        # Per-coin monitors
        self.monitors = {
            coin: CoinMonitor(coin, self.strategy, self.executor)
            for coin in coins
        }

        # Portfolio state
        self.portfolio_risk = 0.0
        self.total_positions = 0

    def analyze_all(self) -> Dict[str, Dict]:
        """Analyze all coins in parallel"""
        results = {}

        with ThreadPoolExecutor(max_workers=len(self.coins)) as executor:
            futures = {
                executor.submit(monitor.analyze): coin
                for coin, monitor in self.monitors.items()
            }

            for future in as_completed(futures):
                coin = futures[future]
                try:
                    results[coin] = future.result()
                except Exception as e:
                    logger.error(f"Analysis failed for {coin}: {e}")
                    results[coin] = {'action': 'HOLD', 'reason': f'Error: {e}'}

        return results

    def make_portfolio_decision(self, coin_results: Dict[str, Dict]) -> List[Tuple[str, str]]:
        """
        Portfolio-level decision making with risk limits.

        Returns:
            List of (coin, action) tuples to execute
        """
        decisions = []

        # 1. Count current positions
        self.total_positions = sum(
            1 for coin in self.coins
            if self.executor.has_position(coin)
        )

        # 2. Portfolio risk limits
        max_positions = self.config['RISK_CONFIG'].get('max_positions', 2)

        # 3. Process entry signals
        entry_candidates = [
            (coin, result)
            for coin, result in coin_results.items()
            if result['action'] == 'BUY' and not self.executor.has_position(coin)
        ]

        # Sort by signal strength (highest first)
        entry_candidates.sort(key=lambda x: x[1]['signal_strength'], reverse=True)

        # 4. Apply portfolio limits
        for coin, result in entry_candidates:
            if self.total_positions >= max_positions:
                self.logger.log(f"Portfolio limit reached ({max_positions} positions), skipping {coin}")
                break

            decisions.append((coin, 'BUY'))
            self.total_positions += 1

        # 5. Process exit signals (always allow exits)
        for coin, result in coin_results.items():
            if result['action'] == 'SELL' and self.executor.has_position(coin):
                decisions.append((coin, 'SELL'))

        return decisions

    def execute_decisions(self, decisions: List[Tuple[str, str]]):
        """Execute trading decisions through LiveExecutor"""
        for coin, action in decisions:
            if action == 'BUY':
                # Get trade details from monitor state
                monitor = self.monitors[coin]
                price = monitor.state['current_price']
                stop_loss = monitor.state['stop_loss_price']

                self.executor.execute_order(
                    ticker=coin,
                    action='BUY',
                    units=self._calculate_position_size(coin, price),
                    price=price,
                    dry_run=self.config['EXECUTION_CONFIG']['dry_run']
                )

            elif action == 'SELL':
                # Close position
                position = self.executor.get_position(coin)
                self.executor.close_position(
                    ticker=coin,
                    price=position.entry_price * 1.01,  # Approximate
                    dry_run=self.config['EXECUTION_CONFIG']['dry_run']
                )

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get summary of all coin states"""
        return {
            'coins': {
                coin: {
                    'state': monitor.state,
                    'position': self.executor.get_position_summary(coin)
                }
                for coin, monitor in self.monitors.items()
            },
            'total_positions': self.total_positions,
            'portfolio_risk': self.portfolio_risk,
        }
```

**Integration with GUI:**

```python
class TradingBotGUIV2:
    def __init__(self, root):
        # ... existing setup ...

        # Multi-coin selection
        self.selected_coins = ['BTC', 'ETH', 'XRP']  # User selectable

        # Portfolio manager (replaces single bot)
        self.portfolio_manager = PortfolioManagerV2(
            coins=self.selected_coins,
            config=config_v2.get_version_config()
        )

        # Update loop
        self.bot_thread = threading.Thread(target=self._run_portfolio_loop)

    def _run_portfolio_loop(self):
        while self.is_running:
            # 1. Analyze all coins
            results = self.portfolio_manager.analyze_all()

            # 2. Make portfolio decisions
            decisions = self.portfolio_manager.make_portfolio_decision(results)

            # 3. Execute decisions
            self.portfolio_manager.execute_decisions(decisions)

            # 4. Update GUI
            self._update_gui_with_portfolio(results)

            time.sleep(60)

    def _update_gui_with_portfolio(self, results: Dict):
        # Update multi-coin display panels
        for coin, result in results.items():
            self._update_coin_status(coin, result)
```

**Pros:**
- ✅ Minimal changes to existing `StrategyV2` and `LiveExecutorV2`
- ✅ Centralized portfolio risk management
- ✅ Easy to add portfolio-level rules (max positions, correlation checks)
- ✅ Parallel analysis with ThreadPoolExecutor
- ✅ Clean separation of concerns (Monitor = coin logic, Manager = portfolio logic)
- ✅ Easy to test (each component is independent)
- ✅ Scalable (can add more coins without refactoring)

**Cons:**
- ❌ Requires new GUI panels for multi-coin display
- ❌ Need to manage thread pool lifecycle
- ❌ Slightly more complex than single-instance approach

**Risk Assessment:** Low-Medium
- Well-established design pattern
- Existing components already support multi-coin
- Thread safety handled by ThreadPoolExecutor
- Portfolio manager can be unit-tested independently

**Verdict:** ✅ **RECOMMENDED** - Best balance of functionality and maintainability

---

### Option D: Event-Driven Async Architecture

**Concept:** Use asyncio for non-blocking concurrent coin monitoring.

```python
class AsyncPortfolioManager:
    async def analyze_coin(self, coin: str) -> Dict:
        # Non-blocking API calls
        df = await get_candlestick_async(coin, '4h')
        result = self.strategy.analyze_market_sync(df)
        return result

    async def run(self):
        while self.running:
            tasks = [
                asyncio.create_task(self.analyze_coin(coin))
                for coin in self.coins
            ]
            results = await asyncio.gather(*tasks)
            await self.process_results(results)
            await asyncio.sleep(60)
```

**Pros:**
- ✅ Highly efficient (non-blocking I/O)
- ✅ Scalable to 10+ coins
- ✅ Modern Python pattern

**Cons:**
- ❌ **Major refactor:** All API calls must be async
- ❌ Tkinter GUI is synchronous (compatibility issues)
- ❌ BithumbAPI not async (would need rewrite)
- ❌ Complexity explosion for 2-3 coins (overkill)

**Verdict:** ❌ Overkill for 2-3 coins (consider for 10+ coins)

---

## 3. Recommended Approach: Portfolio Manager Pattern (Option C)

### 3.1 Implementation Roadmap

**Phase 1: Core Portfolio Manager (2 days)**

1. **Create `portfolio_manager_v2.py`**
   - Implement `CoinMonitor` class
   - Implement `PortfolioManagerV2` class
   - Add portfolio risk management logic

2. **Add portfolio configuration to `config_v2.py`**
   ```python
   PORTFOLIO_CONFIG = {
       'max_positions': 2,           # Max simultaneous positions
       'max_portfolio_risk': 0.06,   # 6% total portfolio risk
       'position_size_equal': True,  # Equal position sizes
       'correlation_limit': 0.7,     # Don't enter if correlation > 0.7
   }
   ```

3. **Unit tests for portfolio manager**
   - Test parallel analysis
   - Test portfolio decision logic
   - Test position limits

**Phase 2: GUI Integration (1.5 days)**

1. **Create multi-coin selector panel**
   - Checkboxes for BTC, ETH, XRP, SOL
   - "Select All" / "Deselect All" buttons
   - Save selection to `user_preferences_v2.json`

2. **Create portfolio overview tab**
   - Table view: Coin | Regime | Score | Position | P&L
   - Color-coded status (green=bullish, red=bearish)
   - Total portfolio P&L

3. **Update existing tabs for multi-coin**
   - Tab 1 (Trading Status): Show selected coin (dropdown remains)
   - Tab 2 (Chart): Add coin selector, show selected coin chart
   - Tab 4 (Score Monitor): Multi-coin score comparison
   - Tab 5 (Signal History): Filter by coin

**Phase 3: Testing & Validation (1.5 days)**

1. **Dry-run testing**
   - Test with 2 coins (BTC, ETH)
   - Test with 3 coins (BTC, ETH, XRP)
   - Test portfolio limits (max 2 positions)

2. **Edge case testing**
   - All coins bullish simultaneously (respects max positions?)
   - API failure for one coin (doesn't crash others?)
   - Position scaling scenarios

3. **Live trading validation**
   - Start with small amounts (5,000 KRW per coin)
   - Monitor for 1 week in dry-run
   - Gradual rollout to live mode

**Total Estimated Effort:** 3-5 days

---

### 3.2 Detailed Code Architecture

**File Structure:**

```
ver2/
├── portfolio_manager_v2.py         # NEW: Portfolio manager & coin monitors
├── gui_app_v2.py                   # MODIFIED: Multi-coin GUI
├── gui_trading_bot_v2.py           # DEPRECATED: Replaced by portfolio manager
├── strategy_v2.py                  # NO CHANGE: Already stateless
├── live_executor_v2.py             # NO CHANGE: Already multi-coin ready
├── config_v2.py                    # MODIFIED: Add PORTFOLIO_CONFIG
└── widgets/
    ├── portfolio_overview_widget.py  # NEW: Portfolio summary table
    └── coin_selector_widget.py       # NEW: Multi-coin checkbox selector
```

**Data Flow:**

```
GUI Event Loop (60s)
  ↓
Portfolio Manager.analyze_all()
  ↓
ThreadPool: [CoinMonitor.analyze() for BTC, ETH, XRP]
  ↓
StrategyV2.analyze_market(coin) × 3 (parallel)
  ↓
Results: {BTC: {action: BUY, score: 3}, ETH: {action: HOLD}, XRP: {action: BUY, score: 4}}
  ↓
Portfolio Manager.make_portfolio_decision(results)
  ↓
Apply Limits: max_positions=2 → Select XRP (score 4) and BTC (score 3)
  ↓
Decisions: [(XRP, BUY), (BTC, BUY)]
  ↓
Portfolio Manager.execute_decisions()
  ↓
LiveExecutorV2.execute_order(XRP, BUY)
LiveExecutorV2.execute_order(BTC, BUY)
  ↓
Update GUI with portfolio state
```

---

### 3.3 Configuration Management

**New Configuration Section:**

```python
# config_v2.py

PORTFOLIO_CONFIG = {
    # Position limits
    'max_positions': 2,              # Max number of simultaneous open positions
    'max_positions_per_coin': 1,     # Max positions per individual coin

    # Risk management
    'max_portfolio_risk': 0.06,      # 6% total portfolio risk
    'position_size_equal': True,     # Equal sizing vs. signal-strength weighted
    'reserve_cash_pct': 0.20,        # Keep 20% cash reserve

    # Coin selection
    'default_coins': ['BTC', 'ETH', 'XRP'],  # Default active coins
    'min_coins': 2,                  # Minimum coins to monitor
    'max_coins': 4,                  # Maximum coins to monitor

    # Correlation filtering (future enhancement)
    'check_correlation': False,      # Enable correlation checks
    'max_correlation': 0.7,          # Don't enter if correlation > 0.7 with existing position

    # Entry prioritization
    'entry_priority': 'score',       # 'score' | 'volatility' | 'volume'
    'tie_breaker': 'coin_rank',      # If scores equal: BTC > ETH > XRP > SOL
}

def get_portfolio_config() -> Dict[str, Any]:
    """Get portfolio configuration with validation"""
    return PORTFOLIO_CONFIG.copy()
```

---

### 3.4 GUI Design Changes

**New Portfolio Overview Tab:**

```
┌─────────────────────────────────────────────────────────────────┐
│  💼 Portfolio Overview                                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─ Coin Selection ───────────────────────────────────────┐   │
│  │  ☑ BTC    ☑ ETH    ☑ XRP    ☐ SOL                      │   │
│  │  [Select All]  [Deselect All]                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Portfolio Status ──────────────────────────────────────┐   │
│  │  Total Positions: 2 / 2                                 │   │
│  │  Total P&L:       +125,000 KRW (+2.5%)                  │   │
│  │  Portfolio Risk:  4.2% / 6.0%                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Individual Coins ──────────────────────────────────────┐   │
│  │  Coin  │ Regime  │ Score │ Position │ Entry    │ P&L     │   │
│  │  ────  │ ──────  │ ───── │ ──────── │ ──────   │ ──────  │   │
│  │  BTC   │ 🟢BULL  │  3/4  │ 0.0015   │ 95.5M    │ +50K    │   │
│  │  ETH   │ 🟢BULL  │  4/4  │ 0.025    │ 3.8M     │ +75K    │   │
│  │  XRP   │ 🔴BEAR  │  1/4  │ -        │ -        │ -       │   │
│  │  SOL   │ 🟡NEUT  │  2/4  │ -        │ -        │ -       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─ Recent Actions ────────────────────────────────────────┐   │
│  │  [10:32] BUY ETH @ 3,800,000 (Score: 4/4)               │   │
│  │  [10:15] BUY BTC @ 95,500,000 (Score: 3/4)              │   │
│  │  [09:45] Portfolio limit reached (2/2 positions)        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**Modified Score Monitoring Tab:**

```
┌─────────────────────────────────────────────────────────────────┐
│  📈 Score Monitoring (Multi-Coin)                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [Coin Filter: ▼ All Coins]  [Timeframe: ▼ 4H]                │
│                                                                 │
│  Score History (Last 24 Hours)                                 │
│   4 ┤     ●                          ●                          │
│   3 ┤  ●     ●        ●●         ●●                            │
│   2 ┤●          ●  ●      ●●  ●●      ●                        │
│   1 ┤                                    ●●                    │
│   0 ┤                                        ●●●●              │
│     └──────────────────────────────────────────────────────────│
│       0h   4h   8h  12h  16h  20h  24h                         │
│                                                                 │
│  Legend:  ● BTC (blue)  ● ETH (green)  ● XRP (orange)         │
│                                                                 │
│  Current Scores:                                               │
│    BTC: 3/4  (BB:✓ RSI:✓ Stoch:✓ Vol:✗)                      │
│    ETH: 4/4  (BB:✓ RSI:✓ Stoch:✓ Vol:✓)  ← ENTRY SIGNAL!     │
│    XRP: 1/4  (BB:✗ RSI:✗ Stoch:✗ Vol:✓)                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3.5 Thread Safety Considerations

**Potential Race Conditions:**

1. **LiveExecutorV2 Position Updates**
   - **Issue:** Multiple CoinMonitors could call `executor.execute_order()` simultaneously
   - **Solution:** Add thread lock in `LiveExecutorV2._update_position_after_trade()`

   ```python
   class LiveExecutorV2:
       def __init__(self, ...):
           self._position_lock = threading.Lock()

       def _update_position_after_trade(self, ticker, action, units, price):
           with self._position_lock:
               # Existing update logic (now thread-safe)
               ...
   ```

2. **Configuration Updates**
   - **Issue:** GUI updating config while portfolio manager reading
   - **Solution:** Use `threading.RLock()` in ConfigManager

3. **Log Queue Overflow**
   - **Issue:** 3 coins logging simultaneously could overflow queue
   - **Solution:** Increase queue size to 5000, add overflow handler

   ```python
   self.log_queue = queue.Queue(maxsize=5000)

   # In log handler
   try:
       self.log_queue.put_nowait(message)
   except queue.Full:
       # Drop oldest message
       self.log_queue.get_nowait()
       self.log_queue.put_nowait(message)
   ```

**Thread Safety Checklist:**

- ✅ LiveExecutorV2: Add `_position_lock`
- ✅ Portfolio Manager: Use `ThreadPoolExecutor` context manager (auto-cleanup)
- ✅ GUI Updates: All GUI updates via `root.after()` (Tkinter thread-safe)
- ✅ State Persistence: JSON file writes use exclusive lock

---

### 3.6 Risk Management Enhancements

**Portfolio-Level Risk Controls:**

```python
class PortfolioManagerV2:
    def check_portfolio_risk(self) -> bool:
        """
        Check if portfolio risk is within limits.

        Returns:
            True if safe to enter new position, False otherwise
        """
        # 1. Count existing positions
        active_positions = [
            self.executor.get_position(coin)
            for coin in self.coins
            if self.executor.has_position(coin)
        ]

        if len(active_positions) >= self.config['PORTFOLIO_CONFIG']['max_positions']:
            self.logger.log("⛔ Portfolio limit reached: max_positions")
            return False

        # 2. Calculate total portfolio risk
        total_risk = 0.0
        for position in active_positions:
            # Risk = (Entry - StopLoss) * Size
            position_risk = (position.entry_price - position.stop_loss) * position.size
            total_risk += position_risk

        # Get account balance (approximate)
        total_capital = self.config['TRADING_CONFIG'].get('total_capital_krw', 1000000)
        portfolio_risk_pct = (total_risk / total_capital) * 100

        max_risk = self.config['PORTFOLIO_CONFIG']['max_portfolio_risk'] * 100  # Convert to %

        if portfolio_risk_pct >= max_risk:
            self.logger.log(f"⛔ Portfolio risk limit: {portfolio_risk_pct:.2f}% >= {max_risk}%")
            return False

        # 3. Check daily loss limit
        daily_loss = self._calculate_daily_loss()
        max_daily_loss = self.config['RISK_CONFIG']['max_daily_loss_pct']

        if daily_loss >= max_daily_loss:
            self.logger.log(f"⛔ Daily loss limit: {daily_loss:.2f}% >= {max_daily_loss}%")
            return False

        return True

    def prioritize_entry_signals(self, candidates: List[Tuple[str, Dict]]) -> List[str]:
        """
        Prioritize entry signals when multiple coins trigger.

        Args:
            candidates: List of (coin, analysis_result) tuples

        Returns:
            Ordered list of coins to enter (highest priority first)
        """
        priority_mode = self.config['PORTFOLIO_CONFIG']['entry_priority']

        if priority_mode == 'score':
            # Sort by entry score (highest first)
            candidates.sort(key=lambda x: x[1]['entry_score'], reverse=True)

        elif priority_mode == 'volatility':
            # Sort by ATR% (prefer higher volatility for trend following)
            candidates.sort(
                key=lambda x: x[1]['indicators'].get('atr', 0) / x[1]['current_price'],
                reverse=True
            )

        elif priority_mode == 'volume':
            # Sort by 24h volume (prefer high liquidity)
            candidates.sort(
                key=lambda x: self._get_24h_volume(x[0]),
                reverse=True
            )

        # Apply tie-breaker (coin rank: BTC > ETH > XRP > SOL)
        coin_rank = {'BTC': 4, 'ETH': 3, 'XRP': 2, 'SOL': 1}
        candidates.sort(
            key=lambda x: (x[1]['entry_score'], coin_rank.get(x[0], 0)),
            reverse=True
        )

        return [coin for coin, _ in candidates]
```

---

## 4. Migration Path

### Step 1: Create Portfolio Manager (No Breaking Changes)

1. Create `portfolio_manager_v2.py` with new classes
2. Add unit tests
3. Deploy alongside existing code (not used yet)

**Deliverables:**
- `ver2/portfolio_manager_v2.py`
- `ver2/tests/test_portfolio_manager.py`
- Updated `config_v2.py` with `PORTFOLIO_CONFIG`

### Step 2: Add Multi-Coin GUI (Feature Flag)

1. Add portfolio overview tab (Tab 0)
2. Add coin selector panel
3. Feature flag: `USE_PORTFOLIO_MANAGER = False` (default)

**Deliverables:**
- `ver2/widgets/portfolio_overview_widget.py`
- `ver2/widgets/coin_selector_widget.py`
- Updated `gui_app_v2.py` with conditional logic

### Step 3: Integration Testing (Dry-Run Only)

1. Enable feature flag: `USE_PORTFOLIO_MANAGER = True`
2. Test with dry-run mode for 1 week
3. Monitor for issues:
   - Thread safety
   - API rate limits
   - GUI responsiveness

**Acceptance Criteria:**
- All 3 coins analyzed every 60s
- Portfolio limits respected
- No crashes or deadlocks
- GUI updates smoothly

### Step 4: Live Trading Rollout (Gradual)

1. Start with 2 coins (BTC, ETH) in live mode
2. Small position sizes (10,000 KRW per coin)
3. Monitor for 3 days
4. Add 3rd coin (XRP) if stable
5. Increase to normal position sizes

**Rollback Plan:**
- If issues occur: Set `USE_PORTFOLIO_MANAGER = False`
- Falls back to single-coin mode immediately
- Existing positions remain (LiveExecutorV2 unaffected)

---

## 5. Trade-offs and Risks

### 5.1 Code Complexity

**Before (Single Coin):**
- `GUITradingBotV2`: 640 lines
- Simple linear flow
- One position state

**After (Multi-Coin):**
- `PortfolioManagerV2`: +300 lines
- `CoinMonitor`: +100 lines
- GUI updates: +200 lines
- **Total:** +600 lines (30% increase)

**Mitigation:**
- Comprehensive unit tests
- Clear documentation
- Code review before deployment

### 5.2 Performance Implications

**API Call Volume:**
- Before: 2 API calls/min (1D + 4H for 1 coin)
- After: 6 API calls/min (1D + 4H for 3 coins)
- **Impact:** Bithumb rate limit is 20 calls/min → Safe ✅

**Memory Usage:**
- Before: ~50 MB (single coin data)
- After: ~150 MB (3 coins × 200 candles each)
- **Impact:** Negligible on modern systems ✅

**GUI Responsiveness:**
- ThreadPoolExecutor: 3 parallel API calls (~1-2s total)
- GUI update: Main thread, no blocking
- **Impact:** No noticeable lag ✅

### 5.3 Testing Challenges

**Unit Testing:**
- ✅ Easy: Portfolio manager logic (decision-making)
- ✅ Easy: CoinMonitor (strategy wrapper)
- ⚠️ Medium: Threading scenarios (use `unittest.mock` for ThreadPoolExecutor)
- ❌ Hard: GUI integration (requires GUI automation)

**Integration Testing:**
- Mock BithumbAPI responses for deterministic tests
- Use dry-run mode for real API tests
- Simulate portfolio scenarios (all bullish, mixed signals, etc.)

### 5.4 Maintenance Burden

**Ongoing Maintenance:**
- Configuration management (3× coin configs to maintain)
- Portfolio limits tuning (max positions, risk thresholds)
- GUI layout adjustments (more data to display)

**Future Enhancements:**
- Correlation-based entry filtering (don't enter BTC if ETH correlated 0.9)
- Dynamic position sizing (allocate more to stronger signals)
- Multi-exchange support (Binance, Upbit)

**Mitigation:**
- Automated tests for portfolio logic
- Configuration validation on startup
- Feature flags for gradual rollout

---

## 6. Alternative Considerations

### 6.1 Why Not Single-Instance Loop? (Option B)

**Rejected because:**
- Requires major refactor of `GUITradingBotV2` (640 lines)
- Sequential analysis slow (3× API latency)
- Hard to isolate coin-specific errors

**When to reconsider:**
- If threading proves unstable
- If API rate limits become an issue

### 6.2 Why Not Multi-Instance? (Option A)

**Rejected because:**
- No portfolio-level coordination
- Thread safety nightmare (shared executor)
- Resource inefficient (3 threads × 60s loops)

**When to reconsider:**
- Scaling to 10+ coins (microservices approach)
- Different strategies per coin

### 6.3 Why Not Async? (Option D)

**Rejected because:**
- Requires async rewrite of BithumbAPI
- Tkinter GUI not async-compatible
- Overkill for 2-3 coins

**When to reconsider:**
- Scaling to 20+ coins
- Moving to async GUI framework (e.g., Toga, Kivy)

---

## 7. Recommended Implementation Plan

### Week 1: Core Development

**Day 1-2: Portfolio Manager**
- [ ] Implement `CoinMonitor` class
- [ ] Implement `PortfolioManagerV2` class
- [ ] Add `PORTFOLIO_CONFIG` to `config_v2.py`
- [ ] Write unit tests (80% coverage)

**Day 3: Threading & Risk Management**
- [ ] Add thread safety locks to `LiveExecutorV2`
- [ ] Implement portfolio risk checks
- [ ] Implement entry prioritization logic
- [ ] Integration tests with mocked API

### Week 2: GUI & Testing

**Day 4: GUI Updates**
- [ ] Create portfolio overview tab
- [ ] Create multi-coin selector widget
- [ ] Update score monitoring for multi-coin
- [ ] Update signal history filtering

**Day 5: Dry-Run Testing**
- [ ] Test with 2 coins (BTC, ETH)
- [ ] Test with 3 coins (BTC, ETH, XRP)
- [ ] Test portfolio limits (max positions)
- [ ] Test simultaneous signals

**Day 6-7: Live Trading Validation**
- [ ] Small position live test (10K KRW × 2 coins)
- [ ] Monitor for anomalies
- [ ] Performance profiling
- [ ] Final adjustments

### Rollout Checklist

**Pre-Deployment:**
- [ ] All unit tests passing
- [ ] Dry-run testing complete (1 week)
- [ ] Documentation updated
- [ ] Rollback plan confirmed

**Deployment:**
- [ ] Deploy with feature flag OFF
- [ ] Enable for dry-run testing
- [ ] Enable for live with small positions
- [ ] Gradual increase to full size

**Post-Deployment:**
- [ ] Monitor logs for 48 hours
- [ ] Check position tracking accuracy
- [ ] Validate P&L calculations
- [ ] Collect user feedback

---

## 8. Code Examples

### 8.1 Portfolio Manager Usage

```python
# Initialize portfolio manager
coins = ['BTC', 'ETH', 'XRP']
config = config_v2.get_version_config()

portfolio_manager = PortfolioManagerV2(coins, config)

# Main loop
while running:
    # 1. Analyze all coins in parallel
    results = portfolio_manager.analyze_all()
    # Results: {
    #   'BTC': {'action': 'BUY', 'score': 3, 'signal_strength': 0.75, ...},
    #   'ETH': {'action': 'HOLD', 'score': 1, ...},
    #   'XRP': {'action': 'BUY', 'score': 4, 'signal_strength': 1.0, ...}
    # }

    # 2. Make portfolio-level decisions
    decisions = portfolio_manager.make_portfolio_decision(results)
    # Decisions: [('XRP', 'BUY'), ('BTC', 'BUY')]  # XRP ranked higher (score 4 vs 3)

    # 3. Execute decisions
    portfolio_manager.execute_decisions(decisions)

    # 4. Get portfolio summary for GUI
    summary = portfolio_manager.get_portfolio_summary()
    update_gui(summary)

    time.sleep(60)
```

### 8.2 GUI Integration

```python
class TradingBotGUIV2:
    def __init__(self, root):
        # Multi-coin selection
        self.selected_coins = self._load_coin_preferences()  # ['BTC', 'ETH']

        # Portfolio manager
        self.portfolio_manager = PortfolioManagerV2(
            coins=self.selected_coins,
            config=config_v2.get_version_config()
        )

    def _run_portfolio_loop(self):
        while self.is_running:
            try:
                # Analyze & execute
                results = self.portfolio_manager.analyze_all()
                decisions = self.portfolio_manager.make_portfolio_decision(results)
                self.portfolio_manager.execute_decisions(decisions)

                # Update GUI (thread-safe)
                self.root.after(0, self._update_portfolio_display, results)

            except Exception as e:
                self.log(f"Error in portfolio loop: {e}")

            time.sleep(60)

    def _update_portfolio_display(self, results: Dict):
        # Update portfolio table
        for coin, result in results.items():
            position = self.portfolio_manager.executor.get_position(coin)

            self.portfolio_table.update_row(coin, {
                'regime': result['market_regime'],
                'score': f"{result['entry_score']}/4",
                'position': position.size if position else '-',
                'pnl': self._calculate_pnl(position, result['current_price'])
            })
```

---

## 9. Success Metrics

### 9.1 Technical Metrics

**Performance:**
- ✅ All 3 coins analyzed within 60s
- ✅ GUI remains responsive (<100ms update latency)
- ✅ API calls within rate limits (<20/min)

**Reliability:**
- ✅ Zero thread deadlocks
- ✅ Zero position tracking errors
- ✅ 99.9% uptime over 1 week

**Code Quality:**
- ✅ 80%+ unit test coverage
- ✅ All portfolio manager tests passing
- ✅ No critical code smells (SonarQube)

### 9.2 Business Metrics

**Trading Performance:**
- Monitor: Average entry score across coins
- Monitor: Portfolio Sharpe ratio (vs. single coin)
- Monitor: Max drawdown (should be lower with diversification)

**User Experience:**
- Faster signal detection (3× more opportunities)
- Better risk management (portfolio limits)
- Improved visibility (multi-coin dashboard)

---

## 10. Conclusion

### Final Recommendation: Portfolio Manager Pattern (Option C)

**Why this is the best approach:**

1. **Minimal Risk:** Leverages existing `StrategyV2` and `LiveExecutorV2` without changes
2. **Clean Architecture:** Separation of concerns (Monitor = coin, Manager = portfolio)
3. **Scalable:** Easy to add 4th coin (SOL) or more in the future
4. **Maintainable:** Clear responsibilities, easy to test and debug
5. **Portfolio Intelligence:** Centralized risk management and decision-making

**Implementation Summary:**
- **Effort:** 3-5 days (1 week with testing)
- **Code Complexity:** Moderate (+30% lines of code)
- **Risk Level:** Low-Medium (well-established pattern)
- **ROI:** High (3× trading opportunities with portfolio risk control)

### Next Steps

1. **Approval:** Review this document, approve recommended approach
2. **Development:** Implement portfolio manager (Days 1-3)
3. **Testing:** Dry-run validation (Days 4-5)
4. **Deployment:** Gradual rollout with feature flag (Days 6-7)
5. **Monitoring:** 48-hour intensive monitoring post-deployment

### Questions for Stakeholders

1. **Portfolio Limits:** Confirm `max_positions = 2` or allow 3?
2. **Entry Priority:** Use score-based or volatility-based prioritization?
3. **Correlation Filter:** Implement in v1 or defer to future enhancement?
4. **Position Sizing:** Equal size per coin or signal-strength weighted?

---

**Document End**

*For questions or clarifications, please contact the development team.*
