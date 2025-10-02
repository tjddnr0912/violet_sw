#!/usr/bin/env python3
"""
빗썸 자동매매 봇 GUI 애플리케이션 - REDESIGNED VERSION
실시간 로그, 거래 상태, 수익 현황을 표시하고 설정 변경 가능

REDESIGN IMPROVEMENTS (2025-10):
1. Console-style log at bottom (150px, scrollable) - NOT filling right side
2. Compact left panel with 2-column layout - NO scrolling needed
3. Better visual hierarchy and spacing
4. Color-coded log messages (INFO=blue, WARNING=orange, ERROR=red)
5. Optimized window size (1400x850)

NEW LAYOUT STRUCTURE:
┌─────────────────────────────────────────────────────────┐
│  Top: Control Panel (Start/Stop, Status)                │
├──────────────────┬──────────────────────────────────────┤
│ Left: Compact    │  Main: Tabbed Content                │
│ Controls         │  - Chart                             │
│ (380px, visible) │  - Signals                           │
│                  │  - History                           │
├──────────────────┴──────────────────────────────────────┤
│  Bottom: Console Log (150px height, scrollable)         │
│  > [12:34:56] Trading signal detected...                │
└─────────────────────────────────────────────────────────┘
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
from typing import Dict, Any, Optional
import logging

# Ensure working directory is project root
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
os.chdir(project_root)

# Add to path
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from gui_trading_bot import GUITradingBot
from logger import TradingLogger, TransactionHistory
from config_manager import ConfigManager
import config
from bithumb_api import get_ticker
from chart_widget import ChartWidget
from signal_history_widget import SignalHistoryWidget


class TradingBotGUI:
    """
    Redesigned Trading Bot GUI with:
    - Bottom console log (compact)
    - Left panel (no scrolling)
    - Better usability
    """

    def __init__(self, root):
        self.root = root
        self.root.title("🤖 빗썸 자동매매 봇 - Redesigned UI")

        # Optimized window size for better layout
        self.root.geometry("1400x850")
        self.root.minsize(1200, 700)

        # State variables
        self.bot = None
        self.bot_thread = None
        self.is_running = False
        self.log_queue = queue.Queue(maxsize=1000)
        self.config_manager = ConfigManager()
        self.transaction_history = TransactionHistory()

        # Bot status data
        self.bot_status = {
            'coin': 'BTC',
            'current_price': 0,
            'avg_buy_price': 0,
            'holdings': 0,
            'pending_orders': [],
            'last_action': 'HOLD'
        }

        # Initialize GUI
        self.setup_styles()
        self.create_widgets()
        self.setup_logging()

        # Start periodic updates
        self.update_gui()

    def setup_styles(self):
        """GUI styles"""
        style = ttk.Style()
        style.theme_use('clam')

        # Custom styles
        style.configure('Title.TLabel', font=('Arial', 10, 'bold'))
        style.configure('Status.TLabel', font=('Arial', 9))
        style.configure('Profit.TLabel', font=('Arial', 10, 'bold'))
        style.configure('Console.TLabel', font=('Monaco', 9))

    def create_widgets(self):
        """
        Create all GUI widgets with new layout:
        ROW 0: Control panel (top)
        ROW 1: Main content (left panel + tabs)
        ROW 2: Console log (bottom)
        """
        # Configure root grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=0)  # Control panel (fixed)
        self.root.rowconfigure(1, weight=1)  # Main content (expandable)
        self.root.rowconfigure(2, weight=0)  # Console log (fixed ~150px)

        # ===== ROW 0: Control Panel =====
        self.create_control_panel(self.root)

        # ===== ROW 1: Main Content (Left + Tabs) =====
        main_frame = ttk.Frame(self.root, padding="10 5 10 5")
        main_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=0)  # Left panel (fixed width)
        main_frame.columnconfigure(1, weight=1)  # Tabs (expandable)
        main_frame.rowconfigure(0, weight=1)

        # Create left panel
        left_container = ttk.Frame(main_frame)
        left_container.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 8))
        self.create_left_panel(left_container)

        # Create tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.create_tabs()

        # ===== ROW 2: Console Log =====
        self.create_console_log(self.root)

    def create_control_panel(self, parent):
        """Top control panel with Start/Stop buttons"""
        control_frame = ttk.LabelFrame(parent, text="🎮 봇 제어", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)

        # Buttons
        self.start_button = ttk.Button(
            control_frame, text="🚀 봇 시작", command=self.start_bot, width=12
        )
        self.start_button.grid(row=0, column=0, padx=(0, 5))

        self.stop_button = ttk.Button(
            control_frame, text="⏹ 봇 정지", command=self.stop_bot,
            state=tk.DISABLED, width=12
        )
        self.stop_button.grid(row=0, column=1, padx=5)

        # Status indicators
        self.status_var = tk.StringVar(value="⚪ 대기 중")
        status_label = ttk.Label(
            control_frame, textvariable=self.status_var,
            style='Title.TLabel', foreground='gray'
        )
        status_label.grid(row=0, column=2, padx=(30, 20))

        # Mode indicator
        current_config = self.config_manager.get_config()
        mode_text = "🟡 모의 거래" if current_config['safety']['dry_run'] else "🔴 실제 거래"
        self.mode_var = tk.StringVar(value=mode_text)
        mode_label = ttk.Label(
            control_frame, textvariable=self.mode_var,
            style='Title.TLabel', foreground='orange'
        )
        mode_label.grid(row=0, column=3, padx=(0, 20))

    def create_left_panel(self, parent):
        """
        Compact left panel - all controls visible without scrolling!
        Uses efficient 2-column layout and compact spacing.
        """
        parent.columnconfigure(0, weight=1)

        row = 0

        # ===== PANEL 1: Current Status =====
        status_frame = ttk.LabelFrame(parent, text="📊 거래 상태", padding="8")
        status_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 8))
        row += 1

        # 2-column layout for status
        self.current_coin_var = tk.StringVar(value="BTC")
        self.current_price_var = tk.StringVar(value="0 KRW")
        self.holdings_var = tk.StringVar(value="0")

        ttk.Label(status_frame, text="코인:", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(status_frame, textvariable=self.current_coin_var).grid(
            row=0, column=1, sticky=tk.W, padx=(5, 20), pady=2
        )

        ttk.Label(status_frame, text="현재가:", style='Title.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(status_frame, textvariable=self.current_price_var).grid(
            row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        ttk.Label(status_frame, text="보유:", style='Title.TLabel').grid(
            row=2, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(status_frame, textvariable=self.holdings_var).grid(
            row=2, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        # ===== PANEL 2: Quick Settings =====
        settings_frame = ttk.LabelFrame(parent, text="⚙️ 설정", padding="8")
        settings_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 8))
        row += 1

        current_config = self.config_manager.get_config()

        # Coin selection
        ttk.Label(settings_frame, text="코인:", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        self.coin_var = tk.StringVar(value=current_config['trading']['target_ticker'])
        coin_combo = ttk.Combobox(
            settings_frame, textvariable=self.coin_var, width=8,
            values=('BTC', 'ETH', 'XRP', 'ADA', 'DOT'), state='readonly'
        )
        coin_combo.grid(row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        # Candle interval
        ttk.Label(settings_frame, text="캔들:", style='Title.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        self.candle_interval_var = tk.StringVar(
            value=current_config['strategy'].get('candlestick_interval', '1h')
        )
        interval_combo = ttk.Combobox(
            settings_frame, textvariable=self.candle_interval_var, width=8,
            values=('30m', '1h', '6h', '12h', '24h'), state='readonly'
        )
        interval_combo.grid(row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2)

        # Apply button
        apply_btn = ttk.Button(
            settings_frame, text="📝 적용", command=self.apply_settings, width=10
        )
        apply_btn.grid(row=2, column=0, columnspan=2, pady=(8, 0))

        # ===== PANEL 3: Market Regime =====
        regime_frame = ttk.LabelFrame(parent, text="🔵 시장 국면", padding="8")
        regime_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 8))
        row += 1

        self.regime_var = tk.StringVar(value="분석 대기 중")
        ttk.Label(regime_frame, textvariable=self.regime_var,
                 font=('Arial', 9, 'bold'), foreground='blue').pack()

        # ===== PANEL 4: Signal Status =====
        signal_frame = ttk.LabelFrame(parent, text="🎯 종합 신호", padding="8")
        signal_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 8))
        row += 1

        self.overall_signal_var = tk.StringVar(value="HOLD")
        ttk.Label(signal_frame, textvariable=self.overall_signal_var,
                 font=('Arial', 12, 'bold'), foreground='gray').pack()

        self.signal_strength_var = tk.StringVar(value="0.00")
        ttk.Label(signal_frame, textvariable=self.signal_strength_var,
                 style='Status.TLabel').pack()

        # ===== PANEL 5: Risk Management =====
        risk_frame = ttk.LabelFrame(parent, text="⚠️ 리스크", padding="8")
        risk_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 8))
        row += 1

        self.stop_loss_price_var = tk.StringVar(value="-")
        self.tp1_price_var = tk.StringVar(value="-")

        ttk.Label(risk_frame, text="손절:", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(risk_frame, textvariable=self.stop_loss_price_var,
                 foreground='red', font=('Arial', 8)).grid(
            row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        ttk.Label(risk_frame, text="익절:", style='Title.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(risk_frame, textvariable=self.tp1_price_var,
                 foreground='green', font=('Arial', 8)).grid(
            row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        # ===== PANEL 6: Profit Summary =====
        profit_frame = ttk.LabelFrame(parent, text="💰 수익", padding="8")
        profit_frame.grid(row=row, column=0, sticky=(tk.W, tk.E), pady=(0, 0))

        self.daily_profit_var = tk.StringVar(value="0 KRW")
        self.daily_trades_var = tk.StringVar(value="0회")

        ttk.Label(profit_frame, text="오늘:", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(profit_frame, textvariable=self.daily_profit_var,
                 style='Status.TLabel').grid(
            row=0, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

        ttk.Label(profit_frame, text="거래:", style='Title.TLabel').grid(
            row=1, column=0, sticky=tk.W, pady=2
        )
        ttk.Label(profit_frame, textvariable=self.daily_trades_var,
                 style='Status.TLabel').grid(
            row=1, column=1, sticky=tk.W, padx=(5, 0), pady=2
        )

    def create_tabs(self):
        """Create all content tabs"""
        # Tab 1: Trading Summary
        main_tab = ttk.Frame(self.notebook)
        self.notebook.add(main_tab, text='거래 현황')
        self.create_summary_tab(main_tab)

        # Tab 2: Chart
        chart_tab = ttk.Frame(self.notebook)
        self.notebook.add(chart_tab, text='📊 실시간 차트')
        chart_tab.columnconfigure(0, weight=1)
        chart_tab.rowconfigure(0, weight=1)
        self.chart_widget = ChartWidget(chart_tab, self.config_manager.get_config())

        # Tab 3: Signal History
        signal_tab = ttk.Frame(self.notebook)
        self.notebook.add(signal_tab, text='📋 신호 히스토리')
        signal_tab.columnconfigure(0, weight=1)
        signal_tab.rowconfigure(0, weight=1)
        self.signal_history_widget = SignalHistoryWidget(signal_tab)

        # Tab 4: Trading History
        history_tab = ttk.Frame(self.notebook)
        self.notebook.add(history_tab, text='📜 거래 내역')
        self.create_trading_history_panel(history_tab)

    def create_summary_tab(self, parent):
        """Create trading summary tab"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        info_frame = ttk.LabelFrame(parent, text="📊 종합 정보", padding="10")
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(0, weight=1)

        self.main_info_text = scrolledtext.ScrolledText(
            info_frame, height=25, wrap=tk.WORD, font=('Monaco', 10)
        )
        self.main_info_text.pack(fill=tk.BOTH, expand=True)

        # Initial content
        self.main_info_text.insert(tk.END, "=== 빗썸 자동매매 봇 ===\n\n")
        self.main_info_text.insert(tk.END, "봇을 시작하면 실시간 정보가 표시됩니다.\n")
        self.main_info_text.config(state=tk.DISABLED)

    def create_console_log(self, parent):
        """
        Console-style log at bottom - COMPACT, SCROLLABLE, MAX 150PX
        This is the KEY improvement: log doesn't dominate the interface!
        """
        log_container = ttk.Frame(parent)
        log_container.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=(5, 10))
        log_container.columnconfigure(0, weight=1)

        # Console header
        header_frame = ttk.Frame(log_container)
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))

        ttk.Label(header_frame, text="📝 Console Log",
                 style='Title.TLabel').pack(side=tk.LEFT)

        clear_btn = ttk.Button(header_frame, text="🗑 Clear",
                              command=self.clear_logs, width=8)
        clear_btn.pack(side=tk.RIGHT)

        # Log text widget - FIXED HEIGHT 150px (approx 10 lines)
        log_frame = ttk.Frame(log_container, height=150)
        log_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        log_frame.grid_propagate(False)  # DON'T expand beyond 150px!
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # ScrolledText with monospace font (console-like)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=10, wrap=tk.WORD,
            font=('Monaco', 9), bg='#f5f5f5'
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Color tags for log levels
        self.log_text.tag_configure("INFO", foreground="#0066cc")
        self.log_text.tag_configure("WARNING", foreground="#ff8800")
        self.log_text.tag_configure("ERROR", foreground="#cc0000")
        self.log_text.tag_configure("SUCCESS", foreground="#00aa00")

    # ===== Bot Control Methods =====

    def start_bot(self):
        """Start the trading bot"""
        try:
            if self.is_running:
                return

            self.is_running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_var.set("🟢 실행 중")

            # Start bot thread
            self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
            self.bot_thread.start()

            # Initialize chart
            if hasattr(self, 'chart_widget'):
                self.add_log("INFO", "차트 데이터 로딩 중...")
                self.chart_widget.refresh_chart()

            self.add_log("SUCCESS", "거래 봇이 시작되었습니다.")

        except Exception as e:
            self.add_log("ERROR", f"봇 시작 실패: {e}")
            messagebox.showerror("시작 오류", f"봇 시작 중 오류:\n{e}")

    def stop_bot(self):
        """Stop the trading bot"""
        try:
            self.is_running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_var.set("🔴 정지됨")

            if self.bot:
                self.bot.stop_price_monitoring()

            self.add_log("WARNING", "거래 봇이 정지되었습니다.")

        except Exception as e:
            self.add_log("ERROR", f"봇 정지 실패: {e}")

    def run_bot(self):
        """Bot execution in separate thread"""
        try:
            self.bot = GUITradingBot(status_callback=self.update_bot_status)

            if not self.bot.authenticate():
                self.add_log("ERROR", "봇 인증 실패")
                return

            self.add_log("INFO", "봇 인증 성공")
            self.bot.start_price_monitoring()

            # Main loop
            while self.is_running:
                try:
                    self.bot.run_trading_cycle()

                    # Wait with interrupt check
                    current_config = self.config_manager.get_config()
                    sleep_seconds = current_config['schedule'].get('check_interval_seconds', 1800)

                    for _ in range(sleep_seconds):
                        if not self.is_running:
                            break
                        time.sleep(1)

                except Exception as e:
                    self.add_log("ERROR", f"거래 사이클 오류: {e}")
                    time.sleep(60)

        except Exception as e:
            self.add_log("ERROR", f"봇 실행 오류: {e}")
        finally:
            self.is_running = False

    def apply_settings(self):
        """Apply settings changes"""
        try:
            current_config = self.config_manager.get_config()

            # Update config
            current_config['trading']['target_ticker'] = self.coin_var.get()
            current_config['strategy']['candlestick_interval'] = self.candle_interval_var.get()

            # Restart if running
            if self.is_running:
                self.stop_bot()
                self.root.after(1000, self.start_bot)

            self.add_log("SUCCESS", f"설정 적용: {self.coin_var.get()}, {self.candle_interval_var.get()}")

            # Update chart
            if hasattr(self, 'chart_widget'):
                self.chart_widget.update_config(current_config)

        except Exception as e:
            self.add_log("ERROR", f"설정 적용 실패: {e}")
            messagebox.showerror("설정 오류", f"설정 적용 중 오류:\n{e}")

    # ===== Logging Methods =====

    def setup_logging(self):
        """Setup logging handler"""
        class GUILogHandler(logging.Handler):
            def __init__(self, log_queue):
                super().__init__()
                self.log_queue = log_queue

            def emit(self, record):
                log_entry = self.format(record)
                self.log_queue.put((record.levelname, log_entry))

        gui_handler = GUILogHandler(self.log_queue)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        logger = logging.getLogger('TradingBot')
        logger.addHandler(gui_handler)
        logger.setLevel(logging.INFO)

    def add_log(self, level, message):
        """Add log message to queue"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_queue.put((level, log_entry))

    def clear_logs(self):
        """Clear log window"""
        self.log_text.delete(1.0, tk.END)

    # ===== Update Methods =====

    def update_gui(self):
        """Periodic GUI update"""
        try:
            # Process log queue (limit to 50 messages per cycle to avoid blocking)
            processed = 0
            while not self.log_queue.empty() and processed < 50:
                try:
                    level, message = self.log_queue.get_nowait()
                    self.log_text.insert(tk.END, message + "\n", level)
                    self.log_text.see(tk.END)
                    processed += 1

                    # Limit log to last 500 lines
                    line_count = int(self.log_text.index('end-1c').split('.')[0])
                    if line_count > 500:
                        self.log_text.delete('1.0', f'{line_count-500}.0')

                except queue.Empty:
                    break

            # Update trading status
            self.update_trading_status()

        except Exception as e:
            print(f"GUI update error: {e}")

        # Schedule next update
        self.root.after(1000, self.update_gui)

    def update_trading_status(self):
        """Update trading status display"""
        try:
            current_config = self.config_manager.get_config()
            current_coin = current_config['trading']['target_ticker']
            self.current_coin_var.set(current_coin)

            if not (self.bot and self.is_running):
                self.current_price_var.set("대기 중")
                self.holdings_var.set("0")

        except Exception as e:
            print(f"Trading status update error: {e}")

    def update_bot_status(self, status: Dict[str, Any]):
        """Update bot status (callback from bot)"""
        try:
            self.bot_status.update(status)

            # Update displays
            self.current_coin_var.set(status.get('coin', 'BTC'))

            current_price = status.get('current_price', 0)
            if current_price > 0:
                self.current_price_var.set(f"{current_price:,.0f} KRW")
            else:
                self.current_price_var.set("조회 중...")

            holdings = status.get('holdings', 0)
            self.holdings_var.set(f"{holdings:.6f}" if holdings > 0 else "0")

            # Update signals
            signals = status.get('signals', {})
            if signals:
                overall_signal = signals.get('overall_signal', 0)
                final_action = signals.get('final_action', 'HOLD')

                self.overall_signal_var.set(final_action)
                self.signal_strength_var.set(f"강도: {overall_signal:+.2f}")

                # Market regime
                regime = signals.get('regime', 'unknown')
                regime_map = {
                    'trending': '🔵 추세장',
                    'ranging': '🟡 횡보장',
                    'transitional': '🟠 전환기',
                    'unknown': '⚪ 분석 중'
                }
                self.regime_var.set(regime_map.get(regime, regime))

            # Log action
            last_action = status.get('last_action', '')
            if last_action and last_action != 'HOLD':
                if last_action == 'BUY':
                    self.add_log("INFO", f"🔵 매수 신호 - {status.get('coin', 'BTC')}")
                elif last_action == 'SELL':
                    self.add_log("INFO", f"🔴 매도 신호 - {status.get('coin', 'BTC')}")

        except Exception as e:
            print(f"Bot status update error: {e}")

    # ===== Trading History Tab =====

    def create_trading_history_panel(self, parent):
        """Trading history tab"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Control panel
        control_frame = ttk.LabelFrame(parent, text="📊 거래 내역 관리", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)

        refresh_btn = ttk.Button(control_frame, text="🔄 새로고침",
                                command=self.refresh_trading_history)
        refresh_btn.pack(side=tk.LEFT, padx=(0, 10))

        # History table
        table_frame = ttk.LabelFrame(parent, text="📈 거래 내역", padding="10")
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ('날짜', '시간', '코인', '거래유형', '수량', '단가', '총금액')
        self.history_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=15)

        for col in columns:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=100)

        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Initial load
        self.refresh_trading_history()

    def refresh_trading_history(self):
        """Refresh trading history"""
        try:
            # Clear existing
            for item in self.history_tree.get_children():
                self.history_tree.delete(item)

            # Add placeholder
            self.history_tree.insert('', 'end', values=(
                '거래 내역이 없습니다', '', '', '', '', '', ''
            ))

            self.add_log("INFO", "거래 내역을 새로고침했습니다.")

        except Exception as e:
            self.add_log("ERROR", f"거래 내역 새로고침 오류: {e}")


def main():
    """Run GUI application"""
    root = tk.Tk()
    app = TradingBotGUI(root)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("GUI application terminated.")


if __name__ == "__main__":
    main()
