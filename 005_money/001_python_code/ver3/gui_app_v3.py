#!/usr/bin/env python3
"""
Portfolio Multi-Coin Strategy v3 - GUI Application

This GUI implements a multi-coin portfolio management interface with:
- Portfolio overview table showing all monitored coins
- Coin selection panel for dynamic coin management
- Individual coin detail tabs
- Real-time updates and logging
- Bot control panel

Architecture:
- Uses PortfolioManagerV3 for multi-coin coordination
- Thread-safe GUI updates via queue
- Parallel coin analysis visualization
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
import json
import sys
import os
from datetime import datetime
from typing import Dict, Any, Optional, List
import logging
import logging.handlers

# Ensure working directory is project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)

# Add paths for imports
sys.path.insert(0, os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

# Import v3 modules
from ver3.gui_trading_bot_v3 import GUITradingBotV3
from ver3.widgets.portfolio_overview_widget import PortfolioOverviewWidget
from ver3.widgets.coin_selector_widget import CoinSelectorWidget
from ver3.widgets.account_info_widget import AccountInfoWidget
from ver3.widgets.settings_panel_widget import SettingsPanelWidget
from ver3.preference_manager_v3 import PreferenceManagerV3
from lib.core.logger import TradingLogger, TransactionHistory
from lib.core.config_manager import ConfigManager
from lib.api.bithumb_api import get_ticker, BithumbAPI
from ver3 import config_v3


class TradingBotGUIV3:
    """
    Ver3 Multi-Coin Portfolio GUI Application.

    Features:
    - Portfolio overview dashboard
    - Multi-coin selection and management
    - Real-time updates every 5 seconds
    - Bot start/stop controls
    - Comprehensive logging
    """

    def __init__(self, root):
        self.root = root

        # Initialize preference manager
        self.pref_manager = PreferenceManagerV3()

        # Load saved preferences
        saved_prefs = self.pref_manager.load_preferences()

        # Read trading mode from config
        self.config = config_v3.get_version_config()

        # Update active coins in config module FIRST (before preference merge)
        active_coins_from_prefs = saved_prefs.get('portfolio_config', {}).get('default_coins', ['BTC', 'ETH', 'XRP'])
        try:
            config_v3.update_active_coins(active_coins_from_prefs)
            self.config = config_v3.get_version_config()
        except (ValueError, KeyError):
            # Invalid saved coins, use default from config
            pass

        # Apply saved preferences to config (AFTER updating active coins)
        self.config = self.pref_manager.merge_with_config(saved_prefs, self.config)

        self.dry_run = self.config['EXECUTION_CONFIG'].get('dry_run', True)
        self.live_mode = self.config['EXECUTION_CONFIG'].get('mode', 'backtest') == 'live'

        # Get active coins from config
        self.active_coins = self.config['PORTFOLIO_CONFIG'].get('default_coins', ['BTC', 'ETH', 'XRP'])

        # Set window title
        mode_str = self._get_trading_mode_string()
        coins_str = ', '.join(self.active_coins)
        self.root.title(f"🤖 Portfolio Multi-Coin Strategy v3.0 - {mode_str} - [{coins_str}]")
        self.root.geometry("1500x900")
        self.root.minsize(1300, 750)

        # Bot state
        self.bot = None
        self.bot_thread = None
        self.is_running = False
        self.log_queue = queue.Queue(maxsize=1000)
        self.config_manager = ConfigManager()
        self.transaction_history = TransactionHistory(history_file='logs/transaction_history.json')

        # Track coins that have already been warned about missing position data
        self.warned_missing_positions = set()

        # API client
        self.api_client = None

        # v3-specific status data
        self.bot_status = {
            'coins': self.active_coins,
            'total_positions': 0,
            'max_positions': self.config['PORTFOLIO_CONFIG'].get('max_positions', 2),
            'total_pnl': 0,
            'portfolio_risk': 0,
            'last_analysis_time': None,
            'cycle_count': 0,
        }

        # Per-coin status
        self.coin_status = {coin: {} for coin in self.active_coins}

        # GUI setup
        self.setup_styles()
        self.create_widgets()
        self.setup_logging()

        # Initialize API client
        self._initialize_api_client()

        # Start periodic updates
        self.update_gui()

    def setup_styles(self):
        """Configure GUI styles"""
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('Title.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Status.TLabel', font=('Arial', 10))
        style.configure('Bullish.TLabel', font=('Arial', 11, 'bold'), foreground='green')
        style.configure('Bearish.TLabel', font=('Arial', 11, 'bold'), foreground='red')
        style.configure('Card.TFrame', background='#f5f5f5')
        style.configure('Big.TButton', font=('Arial', 11, 'bold'))

    def create_widgets(self):
        """Create main GUI widgets"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Top control panel
        self.create_control_panel(main_frame)

        # Main tabbed interface
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))

        # TAB 1: Portfolio Overview (Primary)
        portfolio_tab = ttk.Frame(self.notebook)
        self.notebook.add(portfolio_tab, text='📊 Portfolio Overview')

        # TAB 2: Coin Selection
        coin_selector_tab = ttk.Frame(self.notebook)
        self.notebook.add(coin_selector_tab, text='⚙️ Coin Selection')

        # TAB 3: Logs
        logs_tab = ttk.Frame(self.notebook)
        self.notebook.add(logs_tab, text='📜 Logs')

        # TAB 4: Transaction History
        history_tab = ttk.Frame(self.notebook)
        self.notebook.add(history_tab, text='📋 Transaction History')

        # Configure Portfolio Tab
        portfolio_tab.columnconfigure(0, weight=1)
        portfolio_tab.rowconfigure(1, weight=1)

        # Portfolio overview widget
        self.portfolio_widget = PortfolioOverviewWidget(portfolio_tab)
        self.portfolio_widget.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # Portfolio details panel
        self.create_portfolio_details_panel(portfolio_tab)

        # Configure Coin Selector Tab
        self.create_coin_selector_tab(coin_selector_tab)

        # Configure Logs Tab
        self.create_logs_tab(logs_tab)

        # Configure Transaction History Tab
        self.create_transaction_history_tab(history_tab)

    def create_control_panel(self, parent):
        """Create top control panel"""
        control_frame = ttk.Frame(parent, style='Card.TFrame', padding=10)
        control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # Left side - Bot controls
        left_frame = ttk.Frame(control_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Start/Stop buttons
        self.start_button = ttk.Button(
            left_frame,
            text="▶️ Start Bot",
            command=self.start_bot,
            style='Big.TButton'
        )
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(
            left_frame,
            text="⏹️ Stop Bot",
            command=self.stop_bot,
            state='disabled',
            style='Big.TButton'
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)

        # Emergency stop
        emergency_button = ttk.Button(
            left_frame,
            text="🚨 Emergency Stop",
            command=self.emergency_stop
        )
        emergency_button.pack(side=tk.LEFT, padx=20)

        # Status indicator
        self.status_label = ttk.Label(
            left_frame,
            text="⚪ Bot Stopped",
            font=('Arial', 11, 'bold')
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

        # Right side - Mode indicators
        right_frame = ttk.Frame(control_frame)
        right_frame.pack(side=tk.RIGHT)

        # Dry-run mode checkbox
        self.dry_run_var = tk.BooleanVar(value=self.dry_run)
        dry_run_cb = ttk.Checkbutton(
            right_frame,
            text="🔒 Dry-run Mode (Safe)",
            variable=self.dry_run_var,
            command=self._toggle_dry_run
        )
        dry_run_cb.pack(side=tk.LEFT, padx=10)

        # Trading mode label
        mode_label = ttk.Label(
            right_frame,
            text=self._get_trading_mode_string(),
            font=('Arial', 10, 'bold'),
            foreground='red' if self.live_mode else 'blue'
        )
        mode_label.pack(side=tk.LEFT, padx=10)

    def create_portfolio_details_panel(self, parent):
        """Create portfolio details panel below overview table"""
        details_frame = ttk.LabelFrame(parent, text="Portfolio Details", padding=10)
        details_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # Create 2-row layout
        details_frame.columnconfigure(0, weight=1)
        details_frame.columnconfigure(1, weight=1)
        details_frame.rowconfigure(0, weight=1)
        details_frame.rowconfigure(1, weight=1)

        # ROW 1 - Left: Account Info Widget
        self.account_info_widget = AccountInfoWidget(details_frame)
        self.account_info_widget.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # ROW 1 - Right: Settings Panel Widget
        self.settings_panel = SettingsPanelWidget(
            details_frame,
            config=self.config,
            on_apply_callback=self._on_settings_applied
        )
        self.settings_panel.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # ROW 2 - Full width: Portfolio Stats (3 columns)
        stats_container = ttk.Frame(details_frame)
        stats_container.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        stats_container.columnconfigure(0, weight=1)
        stats_container.columnconfigure(1, weight=1)
        stats_container.columnconfigure(2, weight=1)

        # Column 1: Portfolio Stats
        stats_frame = ttk.Frame(stats_container)
        stats_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        ttk.Label(stats_frame, text="Portfolio Statistics", style='Title.TLabel').pack(anchor=tk.W)

        self.stats_text = tk.Text(stats_frame, height=8, width=35, font=('Courier', 9))
        self.stats_text.pack(fill=tk.BOTH, expand=True)
        self.stats_text.insert('1.0', "Waiting for bot to start...")
        self.stats_text.config(state='disabled')

        # Column 2: Recent Decisions
        decisions_frame = ttk.Frame(stats_container)
        decisions_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        ttk.Label(decisions_frame, text="Recent Decisions", style='Title.TLabel').pack(anchor=tk.W)

        self.decisions_text = tk.Text(decisions_frame, height=8, width=35, font=('Courier', 9))
        self.decisions_text.pack(fill=tk.BOTH, expand=True)
        self.decisions_text.insert('1.0', "No decisions yet...")
        self.decisions_text.config(state='disabled')

        # Column 3: Active Positions
        positions_frame = ttk.Frame(stats_container)
        positions_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        ttk.Label(positions_frame, text="Active Positions", style='Title.TLabel').pack(anchor=tk.W)

        self.positions_text = tk.Text(positions_frame, height=8, width=35, font=('Courier', 9))
        self.positions_text.pack(fill=tk.BOTH, expand=True)
        self.positions_text.insert('1.0', "No positions open...")
        self.positions_text.config(state='disabled')

    def create_coin_selector_tab(self, parent):
        """Create coin selection tab"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)

        # Coin selector widget
        available_coins = config_v3.list_available_coins()
        default_coins = self.config['PORTFOLIO_CONFIG'].get('default_coins', ['BTC', 'ETH', 'XRP'])
        min_coins = self.config['PORTFOLIO_CONFIG'].get('min_coins', 1)
        max_coins = self.config['PORTFOLIO_CONFIG'].get('max_coins', 4)

        self.coin_selector = CoinSelectorWidget(
            parent,
            available_coins=available_coins,
            default_coins=default_coins,
            min_coins=min_coins,
            max_coins=max_coins,
            on_change_callback=self._on_coins_changed
        )
        self.coin_selector.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), padx=10, pady=10)

        # Info panel
        info_frame = ttk.LabelFrame(parent, text="Multi-Coin Portfolio Info", padding=10)
        info_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)

        info_text = """
Portfolio Multi-Coin Strategy (Ver3):

🎯 Strategy Overview:
  • Monitors 2-3 coins simultaneously
  • Maximum 2 positions at any time
  • Entry prioritized by signal score (highest first)
  • Each coin analyzed using Ver2 strategy

📊 Per-Coin Analysis:
  • Daily EMA(50/200) regime filter
  • 4H entry scoring system (0-4 points)
  • Chandelier Exit trailing stops
  • Partial position management (50%/50%)

⚙️ Portfolio Risk Management:
  • Max portfolio risk: 6%
  • Position limit enforcement
  • Parallel coin analysis
  • Thread-safe execution

🔄 How It Works:
  1. Bot analyzes all selected coins every 15 minutes
  2. Calculates entry/exit scores for each coin
  3. Makes portfolio-level decisions:
     - If positions < 2, enter highest-scoring coin
     - Always exit when exit signals trigger
  4. Executes trades through thread-safe executor

💡 Tips:
  • Start with 2-3 liquid coins (BTC, ETH, XRP)
  • Monitor correlation (future feature)
  • Dry-run mode recommended for testing
        """

        info_display = scrolledtext.ScrolledText(
            info_frame,
            wrap=tk.WORD,
            font=('Arial', 10),
            height=20
        )
        info_display.pack(fill=tk.BOTH, expand=True)
        info_display.insert('1.0', info_text)
        info_display.config(state='disabled')

    def create_logs_tab(self, parent):
        """Create logs tab"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=0)
        parent.rowconfigure(1, weight=1)

        # Filter controls
        filter_frame = ttk.Frame(parent)
        filter_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        ttk.Label(filter_frame, text="Filter by coin:").pack(side=tk.LEFT, padx=5)

        self.log_filter_var = tk.StringVar(value="ALL")
        filter_options = ["ALL"] + self.active_coins

        filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.log_filter_var,
            values=filter_options,
            state='readonly',
            width=10
        )
        filter_combo.pack(side=tk.LEFT, padx=5)
        filter_combo.bind('<<ComboboxSelected>>', self._on_log_filter_changed)

        # Clear button
        clear_button = ttk.Button(
            filter_frame,
            text="Clear Logs",
            command=self._clear_logs
        )
        clear_button.pack(side=tk.RIGHT, padx=5)

        # Log display
        self.log_text = scrolledtext.ScrolledText(
            parent,
            wrap=tk.WORD,
            font=('Courier', 9),
            state='disabled'
        )
        self.log_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # Configure log text tags for coin colors
        self.log_text.tag_configure('BTC', foreground='#FFC107')
        self.log_text.tag_configure('ETH', foreground='#2196F3')
        self.log_text.tag_configure('XRP', foreground='#4CAF50')
        self.log_text.tag_configure('SOL', foreground='#9C27B0')
        self.log_text.tag_configure('ERROR', foreground='red')
        self.log_text.tag_configure('WARNING', foreground='orange')
        self.log_text.tag_configure('INFO', foreground='blue')

    def create_transaction_history_tab(self, parent):
        """Create transaction history tab"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        # Transaction list
        self.transaction_tree = ttk.Treeview(
            parent,
            columns=('timestamp', 'coin', 'action', 'price', 'amount', 'pnl'),
            show='headings',
            height=20
        )

        self.transaction_tree.heading('timestamp', text='Timestamp')
        self.transaction_tree.heading('coin', text='Coin')
        self.transaction_tree.heading('action', text='Action')
        self.transaction_tree.heading('price', text='Price (KRW)')
        self.transaction_tree.heading('amount', text='Amount')
        self.transaction_tree.heading('pnl', text='P&L (KRW)')

        self.transaction_tree.column('timestamp', width=150)
        self.transaction_tree.column('coin', width=80)
        self.transaction_tree.column('action', width=80)
        self.transaction_tree.column('price', width=120)
        self.transaction_tree.column('amount', width=120)
        self.transaction_tree.column('pnl', width=120)

        self.transaction_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)

        # Scrollbar
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.transaction_tree.yview)
        self.transaction_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

    # ========================================
    # Bot Control Methods
    # ========================================

    def start_bot(self):
        """Start the trading bot"""
        if self.is_running:
            messagebox.showwarning("Bot Running", "Bot is already running!")
            return

        # Confirm start
        mode = "DRY-RUN" if self.dry_run_var.get() else "LIVE"
        coins = ', '.join(self.active_coins)
        message = f"Start bot in {mode} mode?\n\nMonitoring: {coins}\n\nThis will begin analyzing markets every 15 minutes."

        if not messagebox.askyesno("Start Bot", message):
            return

        try:
            # Update config with current dry-run setting
            self.config['EXECUTION_CONFIG']['dry_run'] = self.dry_run_var.get()

            # Create bot instance
            self.bot = GUITradingBotV3(
                config=self.config,
                gui_app=self,
                log_queue=self.log_queue
            )

            # Start bot in background thread
            self.bot_thread = threading.Thread(target=self.bot.run, daemon=True)
            self.bot_thread.start()

            self.is_running = True
            self.start_button.config(state='disabled')
            self.stop_button.config(state='normal')
            self.status_label.config(text="🟢 Bot Running", foreground='green')

            self._log_to_gui("INFO", "Bot started successfully")

        except Exception as e:
            messagebox.showerror("Start Failed", f"Failed to start bot: {str(e)}")
            self._log_to_gui("ERROR", f"Bot start failed: {str(e)}")

    def stop_bot(self):
        """Stop the trading bot"""
        if not self.is_running:
            return

        if messagebox.askyesno("Stop Bot", "Stop the trading bot?"):
            try:
                if self.bot:
                    self.bot.stop()

                self.is_running = False
                self.start_button.config(state='normal')
                self.stop_button.config(state='disabled')
                self.status_label.config(text="⚪ Bot Stopped", foreground='gray')

                self._log_to_gui("INFO", "Bot stopped by user")

            except Exception as e:
                messagebox.showerror("Stop Failed", f"Failed to stop bot: {str(e)}")

    def emergency_stop(self):
        """Emergency stop - immediately halt all operations"""
        if messagebox.askyesno(
            "Emergency Stop",
            "🚨 EMERGENCY STOP - Immediately halt all operations?\n\nThis will not close open positions."
        ):
            self.is_running = False
            if self.bot:
                self.bot.stop()

            self.start_button.config(state='normal')
            self.stop_button.config(state='disabled')
            self.status_label.config(text="🔴 Emergency Stop", foreground='red')

            self._log_to_gui("ERROR", "EMERGENCY STOP activated!")

    # ========================================
    # GUI Update Methods
    # ========================================

    def update_gui(self):
        """Periodic GUI update (every 5 seconds)"""
        try:
            # Process log queue
            self._process_log_queue()

            # Update portfolio overview
            if self.is_running and self.bot:
                summary = self.bot.get_portfolio_summary()
                if summary:
                    self._update_portfolio_display(summary)

            # Update transaction history
            self._update_transaction_history()

        except Exception as e:
            print(f"GUI update error: {e}")

        # Schedule next update
        self.root.after(5000, self.update_gui)

    def _update_portfolio_display(self, summary: Dict[str, Any]):
        """
        Update portfolio overview display.

        Args:
            summary: Portfolio summary from bot.get_portfolio_summary()
        """
        # Update portfolio overview widget
        self.portfolio_widget.update_data(summary)

        # Update bot status
        self.bot_status.update({
            'total_positions': summary.get('total_positions', 0),
            'total_pnl': summary.get('total_pnl_krw', 0),
            'last_analysis_time': summary.get('last_update', None),
        })

        # Update account info widget
        self._update_account_info(summary)

        # Update stats panel
        self._update_stats_panel(summary)

        # Update decisions panel
        self._update_decisions_panel(summary)

        # Update positions panel
        self._update_positions_panel(summary)

    def _update_stats_panel(self, summary: Dict[str, Any]):
        """Update portfolio statistics panel"""
        stats_lines = []
        stats_lines.append("PORTFOLIO STATISTICS")
        stats_lines.append("=" * 30)
        stats_lines.append(f"Total Positions: {summary.get('total_positions', 0)}/{summary.get('max_positions', 2)}")
        stats_lines.append(f"Total P&L: {summary.get('total_pnl_krw', 0):+,.0f} KRW")
        stats_lines.append(f"Last Update: {datetime.now().strftime('%H:%M:%S')}")
        stats_lines.append("")
        stats_lines.append("PER-COIN STATUS:")
        stats_lines.append("-" * 30)

        coins_data = summary.get('coins', {})
        for coin, data in coins_data.items():
            analysis = data.get('analysis', {})
            regime = analysis.get('market_regime', '?')
            score = analysis.get('entry_score', 0)
            score_details = analysis.get('score_details', '')
            if score_details:
                stats_lines.append(f"{coin}: {regime.upper()} | {score}/4 ({score_details})")
            else:
                stats_lines.append(f"{coin}: {regime.upper()} | Score: {score}/4")

        self.stats_text.config(state='normal')
        self.stats_text.delete('1.0', tk.END)
        self.stats_text.insert('1.0', '\n'.join(stats_lines))
        self.stats_text.config(state='disabled')

    def _update_decisions_panel(self, summary: Dict[str, Any]):
        """Update recent decisions panel"""
        decisions = summary.get('last_decisions', [])

        decision_lines = []
        decision_lines.append("RECENT DECISIONS")
        decision_lines.append("=" * 30)

        if decisions:
            for coin, action, entry_number in decisions:
                timestamp = datetime.now().strftime('%H:%M:%S')
                # Show pyramid info if entry_number > 1
                if entry_number > 1:
                    decision_lines.append(f"[{timestamp}] {coin}: {action} (Pyramid #{entry_number})")
                else:
                    decision_lines.append(f"[{timestamp}] {coin}: {action}")
        else:
            decision_lines.append("No decisions yet...")

        self.decisions_text.config(state='normal')
        self.decisions_text.delete('1.0', tk.END)
        self.decisions_text.insert('1.0', '\n'.join(decision_lines))
        self.decisions_text.config(state='disabled')

    def _update_positions_panel(self, summary: Dict[str, Any]):
        """Update active positions panel"""
        position_lines = []
        position_lines.append("ACTIVE POSITIONS")
        position_lines.append("=" * 30)

        coins_data = summary.get('coins', {})
        has_positions = False

        for coin, data in coins_data.items():
            position = data.get('position', {})
            if position.get('has_position', False):
                has_positions = True
                entry_price = position.get('entry_price', 0)
                size = position.get('size', 0)
                pnl = position.get('pnl', 0)
                position_lines.append(f"{coin}:")
                position_lines.append(f"  Entry: {entry_price:,.0f} KRW")
                position_lines.append(f"  Size: {size:.6f}")
                position_lines.append(f"  P&L: {pnl:+,.0f} KRW")
                position_lines.append("")

        if not has_positions:
            position_lines.append("No positions open...")

        self.positions_text.config(state='normal')
        self.positions_text.delete('1.0', tk.END)
        self.positions_text.insert('1.0', '\n'.join(position_lines))
        self.positions_text.config(state='disabled')

    def _update_account_info(self, summary: Dict[str, Any]):
        """
        Update account information widget.

        Args:
            summary: Portfolio summary from bot.get_portfolio_summary()
        """
        if self.dry_run:
            # DRY-RUN MODE: Use simulated balances
            total_capital = 1000000  # 1M KRW default
            positions_value = 0

            # Build holdings data from portfolio summary
            holdings_data = {}
            coins_data = summary.get('coins', {})

            for coin, data in coins_data.items():
                position = data.get('position', {})
                if position.get('has_position', False):
                    entry_price = position.get('entry_price', 0)
                    size = position.get('size', 0)
                    stop_loss = position.get('stop_loss', 0)

                    # Fetch actual current market price
                    ticker_data = get_ticker(coin)
                    current_price = entry_price  # Fallback to entry price
                    if ticker_data:
                        current_price = float(ticker_data.get('closing_price', entry_price))

                    # Calculate profit target prices based on current config
                    exit_config = self.config.get('EXIT_CONFIG', {})
                    profit_mode = exit_config.get('profit_target_mode', 'bb_based')

                    if profit_mode == 'percentage_based':
                        # Use percentage-based targets from entry price
                        tp1_pct = exit_config.get('tp1_percentage', 1.5)
                        tp2_pct = exit_config.get('tp2_percentage', 2.5)
                        tp1_price = entry_price * (1 + tp1_pct / 100.0)
                        tp2_price = entry_price * (1 + tp2_pct / 100.0)
                    else:
                        # Use BB-based targets from analysis (if available)
                        analysis = data.get('analysis', {})
                        target_prices = analysis.get('target_prices', {})
                        tp1_price = target_prices.get('first_target', 0)
                        tp2_price = target_prices.get('second_target', 0)

                    positions_value += size * entry_price

                    holdings_data[coin] = {
                        'avg_price': entry_price,
                        'quantity': size,
                        'current_price': current_price,
                        'stop_loss': stop_loss,
                        'tp1_price': tp1_price,
                        'tp2_price': tp2_price
                    }

            # Update balance (capital - invested)
            krw_balance = total_capital - positions_value
            self.account_info_widget.update_balance(krw_balance)

            # Update holdings
            if holdings_data:
                self.account_info_widget.update_holdings_batch(holdings_data)
            else:
                self.account_info_widget.clear_holdings()

        else:
            # LIVE MODE: Query real balance from Bithumb API
            try:
                # Check if API client is initialized
                if not self.api_client:
                    self._log_to_gui("WARNING", "API client not initialized - cannot query balance")
                    self.account_info_widget.update_balance(0)
                    self.account_info_widget.clear_holdings()
                    return

                # Query balance from Bithumb
                balance_response = self.api_client.get_balance(currency='ALL')

                if balance_response and balance_response.get('status') == '0000':
                    data = balance_response.get('data', {})

                    # Update KRW balance
                    krw_total = float(data.get('total_krw', '0'))
                    self.account_info_widget.update_balance(krw_total)

                    # Build holdings data for active coins
                    holdings_data = {}
                    coins_data = summary.get('coins', {})

                    for coin in self.active_coins:
                        total_key = f'total_{coin.lower()}'
                        quantity = float(data.get(total_key, '0'))

                        if quantity > 0:
                            # Get current price
                            ticker_data = get_ticker(coin)
                            if ticker_data:
                                current_price = float(ticker_data.get('closing_price', '0'))

                                # Try to get avg_price from portfolio summary first
                                avg_price = current_price  # Default fallback
                                stop_loss = 0
                                tp1_price = 0
                                tp2_price = 0

                                if coin in coins_data:
                                    position = coins_data[coin].get('position', {})
                                    if position.get('has_position', False):
                                        # Use entry_price from portfolio summary
                                        avg_price = position.get('entry_price', current_price)
                                        stop_loss = position.get('stop_loss', 0)

                                        # Calculate profit target prices based on current config
                                        exit_config = self.config.get('EXIT_CONFIG', {})
                                        profit_mode = exit_config.get('profit_target_mode', 'bb_based')

                                        if profit_mode == 'percentage_based':
                                            # Use percentage-based targets from entry price
                                            tp1_pct = exit_config.get('tp1_percentage', 1.5)
                                            tp2_pct = exit_config.get('tp2_percentage', 2.5)
                                            tp1_price = avg_price * (1 + tp1_pct / 100.0)
                                            tp2_price = avg_price * (1 + tp2_pct / 100.0)
                                        else:
                                            # Use BB-based targets from analysis (if available)
                                            analysis = coins_data[coin].get('analysis', {})
                                            target_prices = analysis.get('target_prices', {})
                                            tp1_price = target_prices.get('first_target', 0)
                                            tp2_price = target_prices.get('second_target', 0)
                                    else:
                                        # No position in summary, try positions file
                                        avg_price = self._get_avg_price_from_positions(coin, current_price)
                                else:
                                    # Coin not in summary, try positions file
                                    avg_price = self._get_avg_price_from_positions(coin, current_price)

                                holdings_data[coin] = {
                                    'avg_price': avg_price,
                                    'quantity': quantity,
                                    'current_price': current_price,
                                    'stop_loss': stop_loss,
                                    'tp1_price': tp1_price,
                                    'tp2_price': tp2_price
                                }

                    # Update holdings
                    if holdings_data:
                        self.account_info_widget.update_holdings_batch(holdings_data)
                    else:
                        self.account_info_widget.clear_holdings()
                else:
                    # API query failed
                    error_msg = balance_response.get('message', 'Unknown error') if balance_response else 'No response'
                    self._log_to_gui("ERROR", f"Balance query failed: {error_msg}")

                    # Show zero to indicate error
                    self.account_info_widget.update_balance(0)
                    self.account_info_widget.clear_holdings()

            except Exception as e:
                self._log_to_gui("ERROR", f"Failed to query balance: {str(e)}")
                self.account_info_widget.update_balance(0)
                self.account_info_widget.clear_holdings()

    def _update_transaction_history(self):
        """Update transaction history table"""
        # Load transactions from history
        transactions = self.transaction_history.load_history()

        # Clear existing items
        for item in self.transaction_tree.get_children():
            self.transaction_tree.delete(item)

        # Add transactions (most recent first)
        for tx in reversed(transactions[-50:]):  # Last 50 transactions
            timestamp = tx.get('timestamp', '')
            coin = tx.get('ticker', tx.get('coin', ''))  # Try 'ticker' first, fallback to 'coin'
            action = tx.get('action', '')
            price = tx.get('price', 0)
            amount = tx.get('amount', 0)
            pnl = tx.get('pnl', 0)

            # Format P&L: show "-" if zero/missing, otherwise format with sign
            pnl_display = "-" if pnl == 0 else f"{pnl:+,.0f}"

            self.transaction_tree.insert(
                '',
                tk.END,
                values=(timestamp, coin, action, f"{price:,.0f}", f"{amount:.6f}", pnl_display)
            )

    def _get_avg_price_from_positions(self, coin: str, fallback_price: float) -> float:
        """
        Get average purchase price from positions file.

        Args:
            coin: Coin symbol (e.g., 'SOL')
            fallback_price: Fallback to current price if no position data

        Returns:
            Average purchase price
        """
        try:
            # Try to read from positions file
            positions_file = os.path.join('logs', 'positions_v3.json')
            if os.path.exists(positions_file):
                with open(positions_file, 'r') as f:
                    positions = json.load(f)

                    if coin in positions:
                        entry_price = positions[coin].get('entry_price', fallback_price)
                        # Remove from warned set if position exists now
                        self.warned_missing_positions.discard(coin)
                        return entry_price
                    else:
                        # Coin has balance but no position entry - log warning once
                        if coin not in self.warned_missing_positions:
                            self._log_to_gui("INFO", f"{coin}: No position data found - P&L will show 0%")
                            self.warned_missing_positions.add(coin)
        except Exception as e:
            self._log_to_gui("WARNING", f"Could not read position data for {coin}: {str(e)}")

        # Fallback to current price (will show 0% P&L)
        return fallback_price

    # ========================================
    # Helper Methods
    # ========================================

    def _get_trading_mode_string(self) -> str:
        """Get trading mode display string"""
        if self.dry_run:
            return "DRY-RUN MODE (SAFE)"
        elif self.live_mode:
            return "LIVE TRADING"
        else:
            return "BACKTEST MODE"

    def _toggle_dry_run(self):
        """Toggle dry-run mode"""
        self.dry_run = self.dry_run_var.get()
        if self.config:
            self.config['EXECUTION_CONFIG']['dry_run'] = self.dry_run

        mode = "enabled" if self.dry_run else "disabled"
        self._log_to_gui("INFO", f"Dry-run mode {mode}")

    def _on_settings_applied(self, updated_config: Dict[str, Any]):
        """
        Handle settings panel apply button.

        Args:
            updated_config: Updated configuration dictionary from settings panel
        """
        if self.is_running:
            messagebox.showwarning(
                "Bot Running",
                "Please stop the bot before changing settings."
            )
            return

        try:
            # Update config
            self.config = updated_config

            # Save preferences - preserve default_coins from current selection
            # Load existing preferences first to avoid overwriting coin selection
            existing_prefs = self.pref_manager.load_preferences()
            new_prefs = self.pref_manager.extract_preferences_from_config(updated_config)

            # Preserve default_coins from existing preferences (user's coin selection)
            new_prefs['portfolio_config']['default_coins'] = existing_prefs['portfolio_config']['default_coins']

            self.pref_manager.save_preferences(new_prefs)

            # Update bot config if it exists
            if self.bot:
                self.bot.update_config(updated_config)

            self._log_to_gui("INFO", "Settings applied and saved successfully")

        except Exception as e:
            messagebox.showerror("Settings Error", f"Failed to apply settings:\n{str(e)}")
            self._log_to_gui("ERROR", f"Failed to apply settings: {str(e)}")

    def _on_coins_changed(self, new_coins: List[str]):
        """
        Handle coin selection change.

        Args:
            new_coins: New list of selected coins
        """
        if self.is_running:
            messagebox.showwarning(
                "Bot Running",
                "Please stop the bot before changing coin selection."
            )
            return

        try:
            # Update config
            config_v3.update_active_coins(new_coins)
            self.config = config_v3.get_version_config()
            self.active_coins = new_coins

            # Update window title
            coins_str = ', '.join(self.active_coins)
            mode_str = self._get_trading_mode_string()
            self.root.title(f"🤖 Portfolio Multi-Coin Strategy v3.0 - {mode_str} - [{coins_str}]")

            # Save preferences - update only coins, preserve all other settings
            # Load existing preferences first to avoid overwriting user settings
            existing_prefs = self.pref_manager.load_preferences()
            existing_prefs['portfolio_config']['default_coins'] = new_coins
            self.pref_manager.save_preferences(existing_prefs)

            # Update portfolio widget
            self.portfolio_widget.clear()

            # Update coin status
            self.coin_status = {coin: {} for coin in new_coins}

            self._log_to_gui("INFO", f"Coins updated to: {', '.join(new_coins)}")

        except Exception as e:
            messagebox.showerror("Update Failed", f"Failed to update coins: {str(e)}")
            raise

    def _on_log_filter_changed(self, event=None):
        """Handle log filter change"""
        # Re-display logs with new filter
        # This is a placeholder - actual implementation would filter log history
        pass

    def _clear_logs(self):
        """Clear log display"""
        self.log_text.config(state='normal')
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state='disabled')

    def _process_log_queue(self):
        """Process messages from log queue"""
        try:
            while True:
                record = self.log_queue.get_nowait()

                # Handle both tuple format and LogRecord format
                if isinstance(record, tuple):
                    # Tuple format: (level, message)
                    log_level, message = record
                else:
                    # LogRecord format (from QueueHandler)
                    log_level = record.levelname
                    message = record.getMessage()

                self._log_to_gui(log_level, message)
        except queue.Empty:
            pass

    def _setup_gui_file_logger(self):
        """Setup file logger for GUI logs with daily rotation"""
        # Ensure logs directory exists
        if not os.path.exists('logs'):
            os.makedirs('logs')

        # Create log file path with current date
        current_date = datetime.now().strftime('%Y%m%d')
        self.gui_log_file = os.path.join('logs', f'ver3_gui_{current_date}.log')
        self.gui_log_date = current_date

        # Write initial header to log file
        try:
            with open(self.gui_log_file, 'a', encoding='utf-8') as f:
                if os.path.getsize(self.gui_log_file) == 0:
                    # File is new, write header
                    f.write(f"=== Ver3 GUI Log Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        except Exception as e:
            print(f"Failed to initialize GUI log file: {e}")

    def _write_log_to_file(self, level: str, message: str, timestamp: str):
        """
        Write log message to file with daily rotation.

        Args:
            level: Log level (INFO, WARNING, ERROR)
            message: Log message
            timestamp: Timestamp string (HH:MM:SS format)
        """
        try:
            # Check if date has changed (daily rotation)
            current_date = datetime.now().strftime('%Y%m%d')
            if current_date != self.gui_log_date:
                # Date changed, rotate to new log file
                self.gui_log_file = os.path.join('logs', f'ver3_gui_{current_date}.log')
                self.gui_log_date = current_date

                # Write header to new log file
                with open(self.gui_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n=== Ver3 GUI Log Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")

            # Write log entry with full timestamp
            full_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_entry = f"[{full_timestamp}] [{level}] {message}\n"

            with open(self.gui_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)

        except Exception as e:
            # Don't crash GUI if file logging fails
            print(f"Failed to write to GUI log file: {e}")

    def _log_to_gui(self, level: str, message: str):
        """
        Add log message to GUI and write to file.

        Args:
            level: Log level (INFO, WARNING, ERROR)
            message: Log message
        """
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}\n"

        # Display in GUI text widget
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, log_line, level)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

        # Write to log file
        self._write_log_to_file(level, message, timestamp)


    def _initialize_api_client(self):
        """Initialize Bithumb API client for balance/holdings queries"""
        try:
            import os
            # Try to get API keys from environment variables (same as Ver2)
            connect_key = os.getenv('BITHUMB_CONNECT_KEY')
            secret_key = os.getenv('BITHUMB_SECRET_KEY')

            if connect_key and secret_key:
                self.api_client = BithumbAPI(connect_key, secret_key)
                self._log_to_gui("INFO", "API client initialized successfully")
            else:
                self._log_to_gui("WARNING", "API keys not set - balance query unavailable")
        except Exception as e:
            self._log_to_gui("WARNING", f"API client initialization failed: {str(e)}")
            self.api_client = None

    def setup_logging(self):
        """Setup logging configuration"""
        # Configure Python logging to send to queue
        queue_handler = logging.handlers.QueueHandler(self.log_queue)
        queue_handler.setLevel(logging.INFO)

        root_logger = logging.getLogger()
        root_logger.addHandler(queue_handler)

        # Setup file logging for GUI logs
        self._setup_gui_file_logger()


# Main entry point
if __name__ == "__main__":
    root = tk.Tk()
    app = TradingBotGUIV3(root)
    root.mainloop()
