# Multi-Coin Trading: Quick Start Implementation Guide

**Target:** Ver2 Trading Bot
**Goal:** Enable simultaneous trading of 2-3 coins (BTC, ETH, XRP, SOL)
**Approach:** Portfolio Manager Pattern
**Estimated Time:** 3-5 days

---

## TL;DR - What We're Building

**Current State:**
- ❌ Single coin trading (BTC only via dropdown)
- ❌ Sequential analysis (60s loop for one coin)
- ❌ No portfolio risk management

**Target State:**
- ✅ Multi-coin trading (BTC, ETH, XRP simultaneously)
- ✅ Parallel analysis (all coins analyzed in <5s)
- ✅ Portfolio-level risk limits (max 2 positions, 6% total risk)

---

## Implementation Checklist

### Phase 1: Core Portfolio Manager (Days 1-2)

#### File 1: `ver2/portfolio_manager_v2.py`

```python
"""
Portfolio Manager V2 - Multi-Coin Trading Coordinator
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

from ver2.strategy_v2 import StrategyV2
from ver2.live_executor_v2 import LiveExecutorV2
from lib.core.logger import TradingLogger


class CoinMonitor:
    """Wrapper for monitoring a single coin using StrategyV2"""

    def __init__(self, coin: str, strategy: StrategyV2, executor: LiveExecutorV2, logger: TradingLogger):
        self.coin = coin
        self.strategy = strategy
        self.executor = executor
        self.logger = logger
        self.last_analysis = {}
        self.last_update = None

    def analyze(self) -> Dict[str, Any]:
        """Run strategy analysis for this coin"""
        try:
            result = self.strategy.analyze_market(self.coin, interval='4h')
            self.last_analysis = result
            self.last_update = datetime.now()
            return result
        except Exception as e:
            self.logger.log_error(f"Analysis failed for {self.coin}", e)
            return {
                'action': 'HOLD',
                'signal_strength': 0.0,
                'reason': f'Error: {str(e)}',
                'market_regime': 'error',
                'entry_score': 0,
            }

    def has_position(self) -> bool:
        """Check if we have an open position for this coin"""
        return self.executor.has_position(self.coin)

    def get_position_summary(self) -> Dict[str, Any]:
        """Get position details for this coin"""
        return self.executor.get_position_summary(self.coin)


class PortfolioManagerV2:
    """
    Multi-coin portfolio manager with centralized risk management.

    Features:
    - Parallel coin analysis using ThreadPoolExecutor
    - Portfolio-level position limits
    - Entry signal prioritization
    - Centralized risk management
    """

    def __init__(
        self,
        coins: List[str],
        config: Dict[str, Any],
        api,
        logger: TradingLogger
    ):
        """
        Initialize portfolio manager.

        Args:
            coins: List of coins to monitor (e.g., ['BTC', 'ETH', 'XRP'])
            config: Ver2 configuration dictionary
            api: BithumbAPI instance
            logger: TradingLogger instance
        """
        self.coins = coins
        self.config = config
        self.logger = logger

        # Shared components
        self.strategy = StrategyV2(config, logger)
        self.executor = LiveExecutorV2(api, logger, config)

        # Per-coin monitors
        self.monitors = {
            coin: CoinMonitor(coin, self.strategy, self.executor, logger)
            for coin in coins
        }

        # Portfolio state
        self.last_results = {}
        self.last_decisions = []

        self.logger.logger.info(f"Portfolio Manager initialized with coins: {coins}")

    def analyze_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Analyze all coins in parallel.

        Returns:
            Dict mapping coin symbol to analysis result
        """
        results = {}

        with ThreadPoolExecutor(max_workers=len(self.coins)) as executor:
            # Submit all analysis tasks
            futures = {
                executor.submit(monitor.analyze): coin
                for coin, monitor in self.monitors.items()
            }

            # Collect results as they complete
            for future in as_completed(futures):
                coin = futures[future]
                try:
                    results[coin] = future.result()
                    self.logger.logger.debug(f"Analysis complete for {coin}: {results[coin]['action']}")
                except Exception as e:
                    self.logger.log_error(f"Failed to get result for {coin}", e)
                    results[coin] = {
                        'action': 'HOLD',
                        'signal_strength': 0.0,
                        'reason': f'Exception: {str(e)}',
                        'market_regime': 'error',
                        'entry_score': 0,
                    }

        self.last_results = results
        return results

    def make_portfolio_decision(self, coin_results: Dict[str, Dict]) -> List[Tuple[str, str]]:
        """
        Make portfolio-level trading decisions with risk limits.

        Args:
            coin_results: Analysis results from analyze_all()

        Returns:
            List of (coin, action) tuples to execute
        """
        decisions = []

        # 1. Count current positions
        active_positions = [
            coin for coin in self.coins
            if self.executor.has_position(coin)
        ]
        total_positions = len(active_positions)

        # 2. Get portfolio limits
        portfolio_config = self.config.get('PORTFOLIO_CONFIG', {})
        max_positions = portfolio_config.get('max_positions', 2)

        self.logger.logger.info(f"Portfolio status: {total_positions}/{max_positions} positions")

        # 3. Process entry signals
        entry_candidates = [
            (coin, result)
            for coin, result in coin_results.items()
            if result['action'] == 'BUY' and not self.executor.has_position(coin)
        ]

        if entry_candidates:
            self.logger.logger.info(f"Entry candidates: {[c[0] for c in entry_candidates]}")

            # Prioritize by signal strength (entry score)
            entry_candidates.sort(
                key=lambda x: (x[1].get('entry_score', 0), x[1].get('signal_strength', 0)),
                reverse=True
            )

            # Apply portfolio position limit
            for coin, result in entry_candidates:
                if total_positions >= max_positions:
                    self.logger.logger.info(
                        f"⛔ Portfolio limit reached ({max_positions} positions), skipping {coin} entry"
                    )
                    break

                decisions.append((coin, 'BUY'))
                total_positions += 1
                self.logger.logger.info(
                    f"✅ Entry decision: {coin} (score: {result.get('entry_score')}/4, "
                    f"strength: {result.get('signal_strength'):.2f})"
                )

        # 4. Process exit signals (always allow exits)
        exit_candidates = [
            (coin, result)
            for coin, result in coin_results.items()
            if result['action'] == 'SELL' and self.executor.has_position(coin)
        ]

        for coin, result in exit_candidates:
            decisions.append((coin, 'SELL'))
            self.logger.logger.info(f"🔻 Exit decision: {coin}")

        self.last_decisions = decisions
        return decisions

    def execute_decisions(self, decisions: List[Tuple[str, str]]):
        """
        Execute trading decisions through LiveExecutorV2.

        Args:
            decisions: List of (coin, action) tuples from make_portfolio_decision()
        """
        for coin, action in decisions:
            monitor = self.monitors[coin]
            analysis = monitor.last_analysis

            if action == 'BUY':
                # Entry parameters from analysis
                price = analysis.get('current_price', 0)
                stop_loss = analysis.get('stop_loss_price', 0)

                if price <= 0:
                    self.logger.logger.error(f"Invalid price for {coin}: {price}, skipping order")
                    continue

                # Calculate position size
                trade_amount_krw = self.config['TRADING_CONFIG'].get('trade_amount_krw', 50000)
                units = trade_amount_krw / price

                # Execute buy order
                order_result = self.executor.execute_order(
                    ticker=coin,
                    action='BUY',
                    units=units,
                    price=price,
                    dry_run=self.config['EXECUTION_CONFIG'].get('dry_run', True),
                    reason=f"Entry score: {analysis.get('entry_score')}/4, regime: {analysis.get('market_regime')}"
                )

                if order_result.get('success'):
                    # Update stop-loss
                    self.executor.update_stop_loss(coin, stop_loss)
                    self.logger.logger.info(f"✅ {coin} position opened: {units:.6f} @ {price:,.0f} KRW")
                else:
                    self.logger.logger.error(f"❌ {coin} order failed: {order_result.get('message')}")

            elif action == 'SELL':
                # Exit at current price
                price = analysis.get('current_price', 0)

                if price <= 0:
                    self.logger.logger.error(f"Invalid price for {coin}: {price}, skipping order")
                    continue

                # Close entire position
                order_result = self.executor.close_position(
                    ticker=coin,
                    price=price,
                    dry_run=self.config['EXECUTION_CONFIG'].get('dry_run', True),
                    reason=analysis.get('reason', 'Exit signal')
                )

                if order_result.get('success'):
                    self.logger.logger.info(f"✅ {coin} position closed @ {price:,.0f} KRW")
                else:
                    self.logger.logger.error(f"❌ {coin} exit failed: {order_result.get('message')}")

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive portfolio summary for GUI display.

        Returns:
            Dictionary with portfolio state, individual coin states, and positions
        """
        # Count positions
        active_positions = [
            coin for coin in self.coins
            if self.executor.has_position(coin)
        ]

        # Portfolio-level stats
        total_pnl = 0.0
        for coin in active_positions:
            position = self.executor.get_position(coin)
            if position:
                # Get current price from last analysis
                current_price = self.last_results.get(coin, {}).get('current_price', position.entry_price)
                pnl = (current_price - position.entry_price) * position.size
                total_pnl += pnl

        return {
            'total_positions': len(active_positions),
            'max_positions': self.config.get('PORTFOLIO_CONFIG', {}).get('max_positions', 2),
            'total_pnl_krw': total_pnl,
            'coins': {
                coin: {
                    'analysis': self.last_results.get(coin, {}),
                    'position': self.monitors[coin].get_position_summary(),
                    'last_update': self.monitors[coin].last_update.isoformat() if self.monitors[coin].last_update else None,
                }
                for coin in self.coins
            },
            'last_decisions': self.last_decisions,
        }

    def get_monitor(self, coin: str) -> Optional[CoinMonitor]:
        """Get CoinMonitor for specific coin"""
        return self.monitors.get(coin)
```

**Key Features:**
- ✅ Parallel analysis with `ThreadPoolExecutor`
- ✅ Portfolio position limits (max 2 positions)
- ✅ Entry prioritization by score
- ✅ Centralized risk management

---

#### File 2: Update `ver2/config_v2.py`

Add this section to `config_v2.py`:

```python
# ========== PORTFOLIO CONFIGURATION (Multi-Coin) ==========

PORTFOLIO_CONFIG = {
    # Position limits
    'max_positions': 2,              # Max simultaneous open positions across all coins
    'max_positions_per_coin': 1,     # Max positions per individual coin (always 1 for this strategy)

    # Risk management
    'max_portfolio_risk_pct': 6.0,   # 6% total portfolio risk limit
    'position_size_equal': True,     # Use equal sizing (True) vs. signal-strength weighted (False)

    # Coin selection
    'default_coins': ['BTC', 'ETH', 'XRP'],  # Default active coins on startup
    'min_coins': 1,                  # Minimum coins to monitor
    'max_coins': 4,                  # Maximum coins to monitor (BTC, ETH, XRP, SOL)

    # Entry prioritization
    'entry_priority': 'score',       # Prioritize by: 'score' | 'volatility' | 'volume'
    'coin_rank': {                   # Tie-breaker if scores equal
        'BTC': 4,
        'ETH': 3,
        'XRP': 2,
        'SOL': 1
    },
}

def get_portfolio_config() -> Dict[str, Any]:
    """Get portfolio configuration"""
    return PORTFOLIO_CONFIG.copy()
```

Add `PORTFOLIO_CONFIG` to the return dict in `get_version_config()`:

```python
def get_version_config(interval: str = '4h', mode: str = None) -> Dict[str, Any]:
    # ... existing code ...

    return {
        # ... existing sections ...
        'PORTFOLIO_CONFIG': PORTFOLIO_CONFIG,  # ADD THIS LINE
    }
```

---

#### File 3: Add Thread Safety to `ver2/live_executor_v2.py`

Add lock to `LiveExecutorV2.__init__()`:

```python
class LiveExecutorV2:
    def __init__(self, api, logger, config=None, state_file=None):
        # ... existing code ...

        # Thread safety for position updates
        self._position_lock = threading.Lock()

    def _update_position_after_trade(self, ticker, action, units, price):
        """Update position state after trade execution (thread-safe)"""
        with self._position_lock:  # ADD THIS LINE
            # ... existing update logic ...
```

---

### Phase 2: GUI Integration (Days 3-4)

#### File 4: Create `ver2/widgets/coin_selector_widget.py`

```python
"""
Multi-Coin Selector Widget
Allows user to select which coins to monitor
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Callable, Optional
import json
import os


class CoinSelectorWidget:
    """Widget for selecting multiple coins to monitor"""

    def __init__(self, parent, available_coins: List[str], on_change: Optional[Callable] = None):
        """
        Initialize coin selector.

        Args:
            parent: Parent Tkinter widget
            available_coins: List of coin symbols (e.g., ['BTC', 'ETH', 'XRP', 'SOL'])
            on_change: Callback function called when selection changes (receives list of selected coins)
        """
        self.available_coins = available_coins
        self.on_change = on_change
        self.checkboxes = {}
        self.checkbox_vars = {}

        # Create frame
        self.frame = ttk.LabelFrame(parent, text="💰 코인 선택", padding="10")
        self.frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Create checkboxes for each coin
        for i, coin in enumerate(available_coins):
            var = tk.BooleanVar(value=False)
            checkbox = ttk.Checkbutton(
                self.frame,
                text=coin,
                variable=var,
                command=self._on_selection_change
            )
            checkbox.grid(row=0, column=i, padx=5)

            self.checkbox_vars[coin] = var
            self.checkboxes[coin] = checkbox

        # Buttons
        btn_frame = ttk.Frame(self.frame)
        btn_frame.grid(row=1, column=0, columnspan=len(available_coins), pady=(10, 0))

        ttk.Button(btn_frame, text="전체 선택", command=self._select_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="전체 해제", command=self._deselect_all).pack(side=tk.LEFT, padx=5)

    def _on_selection_change(self):
        """Handle selection change"""
        selected = self.get_selected_coins()
        if self.on_change:
            self.on_change(selected)

    def _select_all(self):
        """Select all coins"""
        for var in self.checkbox_vars.values():
            var.set(True)
        self._on_selection_change()

    def _deselect_all(self):
        """Deselect all coins"""
        for var in self.checkbox_vars.values():
            var.set(False)
        self._on_selection_change()

    def get_selected_coins(self) -> List[str]:
        """Get list of selected coins"""
        return [
            coin for coin, var in self.checkbox_vars.items()
            if var.get()
        ]

    def set_selected_coins(self, coins: List[str]):
        """Set selected coins"""
        for coin, var in self.checkbox_vars.items():
            var.set(coin in coins)
```

---

#### File 5: Create `ver2/widgets/portfolio_overview_widget.py`

```python
"""
Portfolio Overview Widget
Displays summary of all monitored coins in a table
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Any


class PortfolioOverviewWidget:
    """Table displaying portfolio status for all coins"""

    def __init__(self, parent):
        """Initialize portfolio overview widget"""
        self.frame = ttk.LabelFrame(parent, text="💼 포트폴리오 현황", padding="10")
        self.frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Portfolio stats
        stats_frame = ttk.Frame(self.frame)
        stats_frame.pack(fill=tk.X, pady=(0, 10))

        self.positions_var = tk.StringVar(value="0 / 2")
        self.pnl_var = tk.StringVar(value="0 KRW")
        self.risk_var = tk.StringVar(value="0.0%")

        ttk.Label(stats_frame, text="보유 포지션:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, padx=5)
        ttk.Label(stats_frame, textvariable=self.positions_var).grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(stats_frame, text="총 손익:", font=('Arial', 10, 'bold')).grid(row=0, column=2, sticky=tk.W, padx=5)
        self.pnl_label = ttk.Label(stats_frame, textvariable=self.pnl_var)
        self.pnl_label.grid(row=0, column=3, sticky=tk.W, padx=5)

        # Table
        table_frame = ttk.Frame(self.frame)
        table_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('coin', 'regime', 'score', 'position', 'entry', 'pnl')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=6)

        # Column headings
        self.tree.heading('coin', text='코인')
        self.tree.heading('regime', text='체제')
        self.tree.heading('score', text='점수')
        self.tree.heading('position', text='포지션')
        self.tree.heading('entry', text='진입가')
        self.tree.heading('pnl', text='손익')

        # Column widths
        self.tree.column('coin', width=80)
        self.tree.column('regime', width=100)
        self.tree.column('score', width=80)
        self.tree.column('position', width=100)
        self.tree.column('entry', width=120)
        self.tree.column('pnl', width=120)

        # Scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Store coin rows
        self.coin_rows = {}

    def update_portfolio(self, summary: Dict[str, Any]):
        """
        Update portfolio display with summary data.

        Args:
            summary: Dictionary from PortfolioManagerV2.get_portfolio_summary()
        """
        # Update stats
        total_pos = summary.get('total_positions', 0)
        max_pos = summary.get('max_positions', 2)
        self.positions_var.set(f"{total_pos} / {max_pos}")

        total_pnl = summary.get('total_pnl_krw', 0)
        pnl_text = f"{total_pnl:+,.0f} KRW"
        self.pnl_var.set(pnl_text)

        # Color PnL label
        if total_pnl > 0:
            self.pnl_label.config(foreground='green')
        elif total_pnl < 0:
            self.pnl_label.config(foreground='red')
        else:
            self.pnl_label.config(foreground='black')

        # Update coin rows
        coins_data = summary.get('coins', {})

        for coin, data in coins_data.items():
            analysis = data.get('analysis', {})
            position = data.get('position', {})

            # Regime display
            regime = analysis.get('market_regime', 'unknown')
            if regime == 'bullish':
                regime_text = '🟢 BULL'
            elif regime == 'bearish':
                regime_text = '🔴 BEAR'
            else:
                regime_text = '🟡 NEUT'

            # Score
            score = analysis.get('entry_score', 0)
            score_text = f"{score}/4"

            # Position
            if position.get('has_position'):
                pos_size = position.get('size', 0)
                entry_price = position.get('entry_price', 0)
                pos_text = f"{pos_size:.6f}"
                entry_text = f"{entry_price:,.0f}"

                # Calculate PnL
                current_price = analysis.get('current_price', entry_price)
                pnl = (current_price - entry_price) * pos_size
                pnl_text = f"{pnl:+,.0f}"
            else:
                pos_text = "-"
                entry_text = "-"
                pnl_text = "-"

            # Update or create row
            if coin in self.coin_rows:
                item = self.coin_rows[coin]
                self.tree.item(item, values=(coin, regime_text, score_text, pos_text, entry_text, pnl_text))
            else:
                item = self.tree.insert('', tk.END, values=(coin, regime_text, score_text, pos_text, entry_text, pnl_text))
                self.coin_rows[coin] = item
```

---

#### File 6: Update `ver2/gui_app_v2.py`

**Replace the bot initialization section:**

```python
# Around line 65-80, REPLACE single bot with portfolio manager

# OLD CODE (comment out):
# self.bot = GUITradingBotV2(log_callback=self.log, signal_callback=self.add_signal)

# NEW CODE:
from ver2.portfolio_manager_v2 import PortfolioManagerV2
from ver2.widgets.coin_selector_widget import CoinSelectorWidget
from ver2.widgets.portfolio_overview_widget import PortfolioOverviewWidget

# Load saved coin selection (or use defaults)
saved_coins = self._load_coin_preferences()
if not saved_coins:
    saved_coins = self.config['PORTFOLIO_CONFIG'].get('default_coins', ['BTC', 'ETH'])

# Initialize API client
connect_key = os.environ.get('BITHUMB_CONNECT_KEY')
secret_key = os.environ.get('BITHUMB_SECRET_KEY')

if connect_key and secret_key:
    self.api_client = BithumbAPI(connect_key=connect_key, secret_key=secret_key)
    self.logger = TradingLogger(log_dir=self.config['LOGGING_CONFIG'].get('log_dir', 'logs'))

    # Initialize portfolio manager
    self.portfolio_manager = PortfolioManagerV2(
        coins=saved_coins,
        config=self.config,
        api=self.api_client,
        logger=self.logger
    )
else:
    self.log("⚠️ API keys not found - portfolio manager disabled")
    self.portfolio_manager = None
```

**Add coin selector and portfolio overview widgets:**

```python
# In create_widgets(), after creating main_tab:

# Add coin selector (before control panel)
self.coin_selector = CoinSelectorWidget(
    parent=main_frame,
    available_coins=config_v2.AVAILABLE_COINS,
    on_change=self._on_coin_selection_change
)
self.coin_selector.set_selected_coins(saved_coins)

# Add portfolio overview tab (as Tab 0)
portfolio_tab = ttk.Frame(self.notebook)
self.notebook.insert(0, portfolio_tab, text='💼 포트폴리오')

# Create portfolio overview widget
self.portfolio_overview = PortfolioOverviewWidget(portfolio_tab)
```

**Update bot thread to use portfolio manager:**

```python
def _run_bot_thread(self):
    """Bot main loop using portfolio manager"""
    while self.is_running:
        try:
            if self.portfolio_manager:
                # 1. Analyze all coins
                results = self.portfolio_manager.analyze_all()

                # 2. Make portfolio decisions
                decisions = self.portfolio_manager.make_portfolio_decision(results)

                # 3. Execute decisions
                self.portfolio_manager.execute_decisions(decisions)

                # 4. Get summary for GUI
                summary = self.portfolio_manager.get_portfolio_summary()

                # 5. Update GUI (thread-safe)
                self.root.after(0, self._update_portfolio_gui, summary)

            time.sleep(60)  # Check every 60 seconds

        except Exception as e:
            self.log(f"❌ Error in portfolio loop: {str(e)}")
            import traceback
            self.log(traceback.format_exc())
            time.sleep(60)

def _update_portfolio_gui(self, summary: Dict[str, Any]):
    """Update GUI with portfolio summary (runs in main thread)"""
    try:
        # Update portfolio overview tab
        self.portfolio_overview.update_portfolio(summary)

        # Log portfolio status
        total_pos = summary.get('total_positions', 0)
        max_pos = summary.get('max_positions', 2)
        self.log(f"📊 Portfolio: {total_pos}/{max_pos} positions")

        # Log individual coins
        for coin, data in summary.get('coins', {}).items():
            analysis = data.get('analysis', {})
            regime = analysis.get('market_regime', 'unknown')
            score = analysis.get('entry_score', 0)
            self.log(f"  {coin}: {regime}, score {score}/4")

    except Exception as e:
        self.log(f"Error updating portfolio GUI: {str(e)}")

def _on_coin_selection_change(self, selected_coins: List[str]):
    """Handle coin selection change"""
    if not selected_coins:
        self.log("⚠️ At least one coin must be selected")
        return

    self.log(f"📝 Coin selection changed: {selected_coins}")

    # Save preferences
    self._save_coin_preferences(selected_coins)

    # Restart portfolio manager with new coins (if bot is running)
    if self.is_running:
        self.log("Restarting portfolio manager with new coin selection...")
        self.stop_bot()
        time.sleep(1)
        self.start_bot()

def _load_coin_preferences(self) -> List[str]:
    """Load saved coin preferences"""
    try:
        if os.path.exists(self.preferences_file):
            with open(self.preferences_file, 'r') as f:
                prefs = json.load(f)
                return prefs.get('selected_coins', ['BTC', 'ETH'])
    except:
        pass
    return ['BTC', 'ETH']  # Default

def _save_coin_preferences(self, coins: List[str]):
    """Save coin preferences"""
    try:
        prefs = {'selected_coins': coins}
        with open(self.preferences_file, 'w') as f:
            json.dump(prefs, f, indent=2)
    except Exception as e:
        self.log(f"Error saving preferences: {e}")
```

---

### Phase 3: Testing (Day 5)

#### Test Script: `ver2/test_portfolio_manager.py`

```python
"""
Test script for portfolio manager
Run: python -m ver2.test_portfolio_manager
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ver2.portfolio_manager_v2 import PortfolioManagerV2
from ver2 import config_v2
from lib.api.bithumb_api import BithumbAPI
from lib.core.logger import TradingLogger


def test_portfolio_manager():
    """Test portfolio manager with dry-run"""

    # Configuration
    config = config_v2.get_version_config()
    config['EXECUTION_CONFIG']['dry_run'] = True  # FORCE DRY-RUN

    # Initialize components
    api = BithumbAPI()  # No keys needed for dry-run
    logger = TradingLogger(log_dir='logs')

    # Test coins
    test_coins = ['BTC', 'ETH', 'XRP']

    # Create portfolio manager
    pm = PortfolioManagerV2(
        coins=test_coins,
        config=config,
        api=api,
        logger=logger
    )

    print("=" * 60)
    print("PORTFOLIO MANAGER TEST")
    print("=" * 60)

    # Test 1: Analyze all coins
    print("\n[TEST 1] Analyzing all coins...")
    results = pm.analyze_all()

    for coin, result in results.items():
        print(f"\n{coin}:")
        print(f"  Regime: {result.get('market_regime')}")
        print(f"  Action: {result.get('action')}")
        print(f"  Entry Score: {result.get('entry_score')}/4")
        print(f"  Signal Strength: {result.get('signal_strength', 0):.2f}")

    # Test 2: Portfolio decisions
    print("\n[TEST 2] Making portfolio decisions...")
    decisions = pm.make_portfolio_decision(results)

    print(f"\nDecisions: {decisions}")

    # Test 3: Portfolio summary
    print("\n[TEST 3] Portfolio summary...")
    summary = pm.get_portfolio_summary()

    print(f"\nTotal Positions: {summary['total_positions']}/{summary['max_positions']}")
    print(f"Total PnL: {summary['total_pnl_krw']:,.0f} KRW")

    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_portfolio_manager()
```

**Run test:**
```bash
cd /Users/seongwookjang/project/git/violet_sw/005_money
python -m ver2.test_portfolio_manager
```

---

## Configuration Checklist

**File: `ver2/config_v2.py`**

Verify these settings:

```python
# 1. Portfolio config exists
PORTFOLIO_CONFIG = {
    'max_positions': 2,  # ← Adjust based on risk tolerance
    'default_coins': ['BTC', 'ETH', 'XRP'],  # ← Your preferred coins
}

# 2. Execution config
EXECUTION_CONFIG = {
    'mode': 'live',
    'dry_run': True,  # ← Keep True for testing!
}

# 3. Trading config
TRADING_CONFIG = {
    'trade_amount_krw': 50000,  # ← Amount per coin (not total)
}
```

---

## Dry-Run Testing Protocol

**Step 1: Test with 2 coins (BTC, ETH)**
```bash
# 1. Update config
# Set: PORTFOLIO_CONFIG['default_coins'] = ['BTC', 'ETH']

# 2. Run test script
python -m ver2.test_portfolio_manager

# 3. Run GUI
python 001_python_code/ver2/gui_app_v2.py

# 4. Verify
# - Both coins analyzed in <5 seconds
# - Portfolio overview shows both coins
# - Entry signals respected portfolio limit (max 2 positions)
```

**Step 2: Test with 3 coins (BTC, ETH, XRP)**
```bash
# Same steps, but with 3 coins
# Verify: Only top 2 coins enter if all 3 signal simultaneously
```

**Step 3: Test portfolio limits**
```bash
# Scenario: All 3 coins bullish with entry signals
# Expected: Only top 2 (by score) should enter
# Verify in logs: "Portfolio limit reached (2 positions), skipping XRP entry"
```

---

## Live Trading Rollout (Days 6-7)

**Phase 1: Small Position Test**
```python
# config_v2.py
EXECUTION_CONFIG = {
    'mode': 'live',
    'dry_run': False,  # ENABLE LIVE TRADING
}

TRADING_CONFIG = {
    'trade_amount_krw': 10000,  # START SMALL (10K KRW per coin)
}

PORTFOLIO_CONFIG = {
    'max_positions': 1,  # START WITH 1 POSITION
    'default_coins': ['BTC', 'ETH'],  # 2 coins only
}
```

**Monitor for 24 hours:**
- ✅ Orders execute successfully
- ✅ Position tracking accurate
- ✅ Stop-loss updates correctly
- ✅ GUI displays correct state

**Phase 2: Increase to 2 positions**
```python
PORTFOLIO_CONFIG = {
    'max_positions': 2,  # ALLOW 2 POSITIONS
}
```

**Monitor for 48 hours:**
- ✅ Portfolio limit respected
- ✅ Entry prioritization works
- ✅ Exit signals trigger correctly

**Phase 3: Normal position sizes**
```python
TRADING_CONFIG = {
    'trade_amount_krw': 50000,  # NORMAL SIZE
}
```

---

## Troubleshooting

### Issue: "Portfolio manager is None"
**Cause:** API keys not found
**Fix:**
```bash
export BITHUMB_CONNECT_KEY="your_key"
export BITHUMB_SECRET_KEY="your_secret"
```

### Issue: "Thread deadlock detected"
**Cause:** Race condition in position updates
**Fix:** Verify `_position_lock` is added to `LiveExecutorV2`

### Issue: "All coins skipped - portfolio limit"
**Cause:** Limit set too low or positions not clearing
**Fix:**
1. Check `PORTFOLIO_CONFIG['max_positions']`
2. Verify positions closed properly (check `positions_v2.json`)
3. Reset positions: Delete `logs/positions_v2.json`

### Issue: "GUI freezes during analysis"
**Cause:** ThreadPoolExecutor blocking main thread
**Fix:** Verify `root.after(0, ...)` is used for GUI updates

---

## Performance Benchmarks

**Expected Performance (3 coins):**
- Analysis time: <5 seconds (parallel)
- API calls: 6/min (1D + 4H × 3 coins)
- Memory usage: ~150 MB
- GUI update latency: <100ms

**If performance degrades:**
1. Reduce number of candles: `regime_candles: 250 → 200`
2. Increase analysis interval: `60s → 120s`
3. Disable unused indicators in strategy

---

## Quick Reference

### Key Files Created/Modified

**Created:**
- `ver2/portfolio_manager_v2.py` - Core portfolio manager
- `ver2/widgets/coin_selector_widget.py` - Multi-coin selector GUI
- `ver2/widgets/portfolio_overview_widget.py` - Portfolio table display
- `ver2/test_portfolio_manager.py` - Test script

**Modified:**
- `ver2/config_v2.py` - Added `PORTFOLIO_CONFIG`
- `ver2/live_executor_v2.py` - Added `_position_lock`
- `ver2/gui_app_v2.py` - Integrated portfolio manager

### Important Functions

```python
# Analyze all coins
results = portfolio_manager.analyze_all()

# Make decisions with limits
decisions = portfolio_manager.make_portfolio_decision(results)

# Execute trades
portfolio_manager.execute_decisions(decisions)

# Get summary for GUI
summary = portfolio_manager.get_portfolio_summary()
```

### Configuration Settings

```python
# Max positions across all coins
PORTFOLIO_CONFIG['max_positions'] = 2

# Active coins
PORTFOLIO_CONFIG['default_coins'] = ['BTC', 'ETH', 'XRP']

# Entry prioritization
PORTFOLIO_CONFIG['entry_priority'] = 'score'  # or 'volatility' or 'volume'
```

---

## Success Criteria

**Functional:**
- ✅ All selected coins analyzed every 60s
- ✅ Portfolio limits enforced (max 2 positions)
- ✅ Entry signals prioritized by score
- ✅ GUI displays multi-coin status
- ✅ Dry-run and live modes work correctly

**Performance:**
- ✅ Analysis completes in <5s (3 coins)
- ✅ GUI responsive (<100ms updates)
- ✅ API calls within rate limits (<20/min)

**Reliability:**
- ✅ No thread deadlocks
- ✅ No position tracking errors
- ✅ Graceful error handling (1 coin fails, others continue)

---

## Next Steps After Implementation

1. **Monitor Performance:**
   - Track win rate across coins
   - Compare portfolio vs. single-coin returns
   - Analyze entry prioritization effectiveness

2. **Potential Enhancements:**
   - Correlation filtering (don't enter if coins >0.7 correlated)
   - Dynamic position sizing (larger size for higher scores)
   - Multi-exchange support (Binance, Upbit)

3. **Documentation:**
   - Update main README with multi-coin instructions
   - Create user guide for coin selection
   - Document portfolio risk settings

---

**Good luck with the implementation! For questions, refer to MULTI_COIN_ARCHITECTURE_ANALYSIS.md for detailed architectural discussions.**
