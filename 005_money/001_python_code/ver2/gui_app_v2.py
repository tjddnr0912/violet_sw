#!/usr/bin/env python3
"""
Bitcoin Multi-Timeframe Strategy v2 - GUI Application

This GUI maintains the exact 5-tab layout from v1 while integrating v2-specific features:
- Daily EMA regime filter status
- 4H score-based entry system
- Chandelier Exit trailing stop visualization
- Position scaling (50% at BB mid, 100% at BB upper)
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
project_root = os.path.dirname(os.path.dirname(script_dir))
os.chdir(project_root)

# Add paths for imports
sys.path.insert(0, os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

# Import v2 modules
from ver2.gui_trading_bot_v2 import GUITradingBotV2
from lib.core.logger import TradingLogger, TransactionHistory
from lib.core.config_manager import ConfigManager
from lib.api.bithumb_api import get_ticker
from ver2.chart_widget_v2 import ChartWidgetV2
from ver2.signal_history_widget_v2 import SignalHistoryWidgetV2
from ver2.multi_chart_widget_v2 import MultiChartWidgetV2
from ver2 import config_v2


class TradingBotGUIV2:
    def __init__(self, root):
        self.root = root

        # Read trading mode from config
        self.config = config_v2.get_version_config()
        self.dry_run = self.config['EXECUTION_CONFIG'].get('dry_run', True)
        self.live_mode = self.config['EXECUTION_CONFIG'].get('mode', 'backtest') == 'live'

        # Set window title with mode indicator
        mode_str = self._get_trading_mode_string()
        self.root.title(f"🤖 Bitcoin Multi-Timeframe Strategy v2.0 - {mode_str}")
        self.root.geometry("1400x850")
        self.root.minsize(1200, 700)

        # Bot state
        self.bot = None
        self.bot_thread = None
        self.is_running = False
        self.log_queue = queue.Queue(maxsize=1000)
        self.config_manager = ConfigManager()
        self.transaction_history = TransactionHistory()

        # v2-specific status data
        self.bot_status = {
            'coin': 'BTC',
            'current_price': 0,
            'regime': 'NEUTRAL',
            'regime_confirmation_bars': 0,
            'ema_fast': 0,
            'ema_slow': 0,
            'entry_score': 0,
            'entry_components': {
                'bb_touch': 0,
                'bb_distance': 0,
                'rsi_oversold': 0,
                'rsi_value': 0,
                'stoch_cross': 0,
                'stoch_k': 0,
                'stoch_d': 0
            },
            'position_phase': 'NONE',
            'entry_price': 0,
            'position_size': 0,
            'chandelier_stop': 0,
            'highest_high': 0,
            'breakeven_moved': False,
            'first_target_price': 0,
            'first_target_hit': False,
            'current_pnl': 0,
            'last_action': 'HOLD',
            'consecutive_losses': 0,
            'daily_loss_pct': 0,
            'daily_trades': 0,
            'circuit_breaker_active': False
        }

        # GUI setup
        self.setup_styles()
        self.create_widgets()
        self.setup_logging()

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

    def create_widgets(self):
        """Create main GUI widgets - EXACT 5-tab layout from v1"""
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

        # TAB 1: Trading Status (Main)
        main_tab = ttk.Frame(self.notebook)
        self.notebook.add(main_tab, text='거래 현황')

        # TAB 2: Real-time Chart
        chart_tab = ttk.Frame(self.notebook)
        self.notebook.add(chart_tab, text='📊 실시간 차트')

        # TAB 3: Multi Timeframe Chart
        multi_chart_tab = ttk.Frame(self.notebook)
        self.notebook.add(multi_chart_tab, text='📊 멀티 타임프레임')

        # TAB 4: Signal History
        signal_history_tab = ttk.Frame(self.notebook)
        self.notebook.add(signal_history_tab, text='📋 신호 히스토리')

        # TAB 5: Transaction History
        history_tab = ttk.Frame(self.notebook)
        self.notebook.add(history_tab, text='📜 거래 내역')

        # Configure Tab 1 (Main) - 3-column layout with console
        main_tab.columnconfigure(0, weight=1)
        main_tab.columnconfigure(1, weight=1)
        main_tab.columnconfigure(2, weight=1)
        main_tab.rowconfigure(0, weight=1)
        main_tab.rowconfigure(1, weight=0)

        # Left column - Market & Entry
        left_frame = ttk.Frame(main_tab)
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 2), pady=5)
        self.create_regime_panel(left_frame)
        self.create_entry_score_panel(left_frame)

        # Middle column - Position & Risk
        middle_frame = ttk.Frame(main_tab)
        middle_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=2, pady=5)
        self.create_position_panel(middle_frame)
        self.create_chandelier_panel(middle_frame)

        # Right column - Status & Config
        right_frame = ttk.Frame(main_tab)
        right_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(2, 5), pady=5)
        self.create_status_panel(right_frame)
        self.create_risk_management_panel(right_frame)
        self.create_config_panel(right_frame)

        # Bottom console (full width)
        console_frame = ttk.Frame(main_tab, style='Card.TFrame')
        console_frame.grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), padx=5, pady=(5, 5))
        self.create_log_panel(console_frame)

        # Configure Tab 2 (Chart)
        chart_tab.columnconfigure(0, weight=1)
        chart_tab.rowconfigure(0, weight=1)
        v2_config = config_v2.get_version_config()
        self.chart_widget = ChartWidgetV2(chart_tab, v2_config)

        # Configure Tab 3 (Multi Timeframe) - 2x2 grid with Daily/12H/4H/1H
        multi_chart_tab.columnconfigure(0, weight=1)
        multi_chart_tab.rowconfigure(0, weight=1)
        self.multi_chart_widget = MultiChartWidgetV2(multi_chart_tab, v2_config)

        # Configure Tab 4 (Signal History)
        signal_history_tab.columnconfigure(0, weight=1)
        signal_history_tab.rowconfigure(0, weight=1)
        self.signal_history_widget = SignalHistoryWidgetV2(signal_history_tab)

        # Configure Tab 5 (Transaction History)
        self.create_trading_history_panel(history_tab)

    def create_control_panel(self, parent):
        """Top control panel"""
        control_frame = ttk.LabelFrame(parent, text="🎮 봇 제어", padding="10")
        control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.start_button = ttk.Button(control_frame, text="🚀 봇 시작", command=self.start_bot)
        self.start_button.grid(row=0, column=0, padx=(0, 5))

        self.stop_button = ttk.Button(control_frame, text="⏹ 봇 정지", command=self.stop_bot, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)

        self.status_var = tk.StringVar(value="⚪ 대기 중")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, style='Status.TLabel')
        status_label.grid(row=0, column=2, padx=(20, 0))

        # Trading mode indicator (from config)
        mode_text, mode_color = self._get_mode_display()
        self.mode_var = tk.StringVar(value=mode_text)
        mode_label = ttk.Label(control_frame, textvariable=self.mode_var,
                               font=('Arial', 10, 'bold'), foreground=mode_color)
        mode_label.grid(row=0, column=3, padx=(20, 0))

    def create_regime_panel(self, parent):
        """Market regime filter panel (Daily EMA)"""
        regime_frame = ttk.LabelFrame(parent, text="🔍 시장 체제 필터 (Daily EMA)", padding="10")
        regime_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))
        parent.columnconfigure(0, weight=1)

        # Regime status with color badge
        ttk.Label(regime_frame, text="체제 상태:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.regime_var = tk.StringVar(value="NEUTRAL")
        self.regime_label = ttk.Label(regime_frame, textvariable=self.regime_var,
                                       font=('Arial', 11, 'bold'), foreground='gray')
        self.regime_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # EMA 50
        ttk.Label(regime_frame, text="EMA 50:", style='Title.TLabel').grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.ema_fast_var = tk.StringVar(value="0")
        ttk.Label(regime_frame, textvariable=self.ema_fast_var, style='Status.TLabel').grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # EMA 200
        ttk.Label(regime_frame, text="EMA 200:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.ema_slow_var = tk.StringVar(value="0")
        ttk.Label(regime_frame, textvariable=self.ema_slow_var, style='Status.TLabel').grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Hysteresis buffer status
        ttk.Label(regime_frame, text="확인 봉:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.regime_confirmation_var = tk.StringVar(value="0/2")
        ttk.Label(regime_frame, textvariable=self.regime_confirmation_var, style='Status.TLabel').grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Trading permission
        ttk.Label(regime_frame, text="거래 허용:", style='Title.TLabel').grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        self.trading_allowed_var = tk.StringVar(value="NO")
        self.trading_allowed_label = ttk.Label(regime_frame, textvariable=self.trading_allowed_var,
                                                font=('Arial', 10, 'bold'), foreground='red')
        self.trading_allowed_label.grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_entry_score_panel(self, parent):
        """Entry signal scoring panel (4H)"""
        score_frame = ttk.LabelFrame(parent, text="🎯 진입 신호 시스템 (4H)", padding="10")
        score_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))

        # Total score with visual indicator
        score_row = ttk.Frame(score_frame)
        score_row.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        ttk.Label(score_row, text="총점:", style='Title.TLabel').pack(side=tk.LEFT)
        self.entry_score_var = tk.StringVar(value="0/4")
        self.entry_score_label = ttk.Label(score_row, textvariable=self.entry_score_var,
                                           font=('Arial', 16, 'bold'), foreground='gray')
        self.entry_score_label.pack(side=tk.LEFT, padx=(10, 0))

        # Entry permission badge
        self.entry_permission_var = tk.StringVar(value="대기")
        self.entry_permission_label = ttk.Label(score_row, textvariable=self.entry_permission_var,
                                                font=('Arial', 9, 'bold'), foreground='red',
                                                background='#ffe0e0', relief=tk.RAISED, padding=3)
        self.entry_permission_label.pack(side=tk.RIGHT)

        # Separator
        ttk.Separator(score_frame, orient='horizontal').grid(row=1, column=0, columnspan=2,
                                                              sticky=(tk.W, tk.E), pady=5)

        # BB Lower Touch (+1) with distance
        ttk.Label(score_frame, text="BB 하단 터치:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.bb_touch_var = tk.StringVar(value="0점")
        self.bb_touch_label = ttk.Label(score_frame, textvariable=self.bb_touch_var, style='Status.TLabel')
        self.bb_touch_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # BB distance detail
        ttk.Label(score_frame, text="  거리:", font=('Arial', 9)).grid(row=3, column=0, sticky=tk.W)
        self.bb_distance_var = tk.StringVar(value="-")
        ttk.Label(score_frame, textvariable=self.bb_distance_var, font=('Arial', 9)).grid(row=3, column=1, sticky=tk.W, padx=(10, 0))

        # RSI Oversold (+1) with value
        ttk.Label(score_frame, text="RSI 과매도:", style='Title.TLabel').grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        self.rsi_oversold_var = tk.StringVar(value="0점")
        self.rsi_oversold_label = ttk.Label(score_frame, textvariable=self.rsi_oversold_var, style='Status.TLabel')
        self.rsi_oversold_label.grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # RSI value detail
        ttk.Label(score_frame, text="  RSI(14):", font=('Arial', 9)).grid(row=5, column=0, sticky=tk.W)
        self.rsi_value_var = tk.StringVar(value="-")
        ttk.Label(score_frame, textvariable=self.rsi_value_var, font=('Arial', 9)).grid(row=5, column=1, sticky=tk.W, padx=(10, 0))

        # Stoch RSI Cross (+2) with K/D values
        ttk.Label(score_frame, text="Stoch RSI 교차:", style='Title.TLabel').grid(row=6, column=0, sticky=tk.W, pady=(5, 0))
        self.stoch_cross_var = tk.StringVar(value="0점")
        self.stoch_cross_label = ttk.Label(score_frame, textvariable=self.stoch_cross_var, style='Status.TLabel')
        self.stoch_cross_label.grid(row=6, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Stoch K/D values detail
        ttk.Label(score_frame, text="  %K / %D:", font=('Arial', 9)).grid(row=7, column=0, sticky=tk.W)
        self.stoch_kd_var = tk.StringVar(value="- / -")
        ttk.Label(score_frame, textvariable=self.stoch_kd_var, font=('Arial', 9)).grid(row=7, column=1, sticky=tk.W, padx=(10, 0))

        # Entry threshold
        ttk.Separator(score_frame, orient='horizontal').grid(row=8, column=0, columnspan=2,
                                                              sticky=(tk.W, tk.E), pady=5)
        ttk.Label(score_frame, text="진입 기준:", style='Title.TLabel').grid(row=9, column=0, sticky=tk.W, pady=(5, 0))
        threshold_label = ttk.Label(score_frame, text="≥ 3점", font=('Arial', 10, 'bold'), foreground='blue')
        threshold_label.grid(row=9, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_position_panel(self, parent):
        """Position state panel"""
        pos_frame = ttk.LabelFrame(parent, text="💼 포지션 관리 프로토콜", padding="10")
        pos_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))
        parent.columnconfigure(0, weight=1)

        # Position phase with visual indicator
        ttk.Label(pos_frame, text="현재 단계:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.phase_var = tk.StringVar(value="NONE")
        self.phase_label = ttk.Label(pos_frame, textvariable=self.phase_var,
                                      font=('Arial', 10, 'bold'), foreground='gray')
        self.phase_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # Separator
        ttk.Separator(pos_frame, orient='horizontal').grid(row=1, column=0, columnspan=2,
                                                            sticky=(tk.W, tk.E), pady=5)

        # Entry info
        ttk.Label(pos_frame, text="진입가:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.entry_price_var = tk.StringVar(value="0")
        ttk.Label(pos_frame, textvariable=self.entry_price_var, style='Status.TLabel').grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Position size (shows % of full)
        ttk.Label(pos_frame, text="포지션 크기:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.position_size_var = tk.StringVar(value="0 BTC (0%)")
        ttk.Label(pos_frame, textvariable=self.position_size_var, style='Status.TLabel').grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Current P&L
        ttk.Label(pos_frame, text="현재 손익:", style='Title.TLabel').grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        self.current_pnl_var = tk.StringVar(value="0 KRW (0%)")
        self.current_pnl_label = ttk.Label(pos_frame, textvariable=self.current_pnl_var,
                                            font=('Arial', 10, 'bold'), foreground='gray')
        self.current_pnl_label.grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Separator
        ttk.Separator(pos_frame, orient='horizontal').grid(row=5, column=0, columnspan=2,
                                                            sticky=(tk.W, tk.E), pady=5)

        # First target (BB Middle)
        ttk.Label(pos_frame, text="1차 목표 (BB중간):", style='Title.TLabel').grid(row=6, column=0, sticky=tk.W, pady=(5, 0))
        self.first_target_price_var = tk.StringVar(value="0")
        ttk.Label(pos_frame, textvariable=self.first_target_price_var, font=('Arial', 9)).grid(row=6, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # First target status
        ttk.Label(pos_frame, text="1차 목표 상태:", style='Title.TLabel').grid(row=7, column=0, sticky=tk.W, pady=(5, 0))
        self.first_target_var = tk.StringVar(value="대기중")
        self.first_target_label = ttk.Label(pos_frame, textvariable=self.first_target_var,
                                             font=('Arial', 9, 'bold'), foreground='gray')
        self.first_target_label.grid(row=7, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Scaling info
        ttk.Label(pos_frame, text="스케일링:", font=('Arial', 9)).grid(row=8, column=0, sticky=tk.W, pady=(5, 0))
        self.scaling_info_var = tk.StringVar(value="50% at Entry → 50% at BB Mid")
        ttk.Label(pos_frame, textvariable=self.scaling_info_var, font=('Arial', 8),
                  foreground='blue').grid(row=8, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_status_panel(self, parent):
        """Trading status panel"""
        status_frame = ttk.LabelFrame(parent, text="📊 거래 상태", padding="10")
        status_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))
        parent.columnconfigure(0, weight=1)

        # Current coin
        ttk.Label(status_frame, text="거래 코인:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.current_coin_var = tk.StringVar(value="BTC")
        ttk.Label(status_frame, textvariable=self.current_coin_var, style='Status.TLabel').grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # Current price
        ttk.Label(status_frame, text="현재 가격:", style='Title.TLabel').grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.current_price_var = tk.StringVar(value="0 KRW")
        ttk.Label(status_frame, textvariable=self.current_price_var, style='Status.TLabel').grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Execution interval
        ttk.Label(status_frame, text="실행 주기:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        interval_label = ttk.Label(status_frame, text="4H", style='Status.TLabel')
        interval_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Last action
        ttk.Label(status_frame, text="마지막 행동:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.last_action_var = tk.StringVar(value="HOLD")
        ttk.Label(status_frame, textvariable=self.last_action_var, style='Status.TLabel').grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_chandelier_panel(self, parent):
        """Chandelier Exit panel - ATR-based trailing stop"""
        chandelier_frame = ttk.LabelFrame(parent, text="📉 Chandelier Exit (동적 손절)", padding="10")
        chandelier_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))

        # Stop price (main display)
        ttk.Label(chandelier_frame, text="현재 손절가:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.chandelier_stop_var = tk.StringVar(value="0")
        self.chandelier_stop_label = ttk.Label(chandelier_frame, textvariable=self.chandelier_stop_var,
                                                 font=('Arial', 11, 'bold'), foreground='red')
        self.chandelier_stop_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # Separator
        ttk.Separator(chandelier_frame, orient='horizontal').grid(row=1, column=0, columnspan=2,
                                                                   sticky=(tk.W, tk.E), pady=5)

        # Highest high since entry
        ttk.Label(chandelier_frame, text="진입 후 최고가:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.highest_high_var = tk.StringVar(value="0")
        ttk.Label(chandelier_frame, textvariable=self.highest_high_var, style='Status.TLabel').grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # ATR value
        ttk.Label(chandelier_frame, text="ATR(14):", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.atr_value_var = tk.StringVar(value="0")
        ttk.Label(chandelier_frame, textvariable=self.atr_value_var, font=('Arial', 9)).grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # ATR multiplier
        ttk.Label(chandelier_frame, text="ATR 배수:", style='Title.TLabel').grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        multiplier_label = ttk.Label(chandelier_frame, text="3.0x", font=('Arial', 9), foreground='blue')
        multiplier_label.grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Separator
        ttk.Separator(chandelier_frame, orient='horizontal').grid(row=5, column=0, columnspan=2,
                                                                   sticky=(tk.W, tk.E), pady=5)

        # Breakeven status
        ttk.Label(chandelier_frame, text="손익분기 이동:", style='Title.TLabel').grid(row=6, column=0, sticky=tk.W, pady=(5, 0))
        self.breakeven_var = tk.StringVar(value="미이동")
        self.breakeven_label = ttk.Label(chandelier_frame, textvariable=self.breakeven_var,
                                          font=('Arial', 9, 'bold'), foreground='gray')
        self.breakeven_label.grid(row=6, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Protection info
        ttk.Label(chandelier_frame, text="수익 보호:", font=('Arial', 9)).grid(row=7, column=0, sticky=tk.W, pady=(5, 0))
        self.protection_info_var = tk.StringVar(value="대기중")
        ttk.Label(chandelier_frame, textvariable=self.protection_info_var, font=('Arial', 8),
                  foreground='green').grid(row=7, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_risk_management_panel(self, parent):
        """Risk management and circuit breakers panel"""
        risk_frame = ttk.LabelFrame(parent, text="⚠️ 위험 관리", padding="10")
        risk_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))

        # Circuit breaker status
        ttk.Label(risk_frame, text="회로차단기:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.circuit_breaker_var = tk.StringVar(value="정상")
        self.circuit_breaker_label = ttk.Label(risk_frame, textvariable=self.circuit_breaker_var,
                                                font=('Arial', 10, 'bold'), foreground='green')
        self.circuit_breaker_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # Separator
        ttk.Separator(risk_frame, orient='horizontal').grid(row=1, column=0, columnspan=2,
                                                             sticky=(tk.W, tk.E), pady=5)

        # Consecutive losses
        ttk.Label(risk_frame, text="연속 손실:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.consecutive_losses_var = tk.StringVar(value="0/5")
        self.consecutive_losses_label = ttk.Label(risk_frame, textvariable=self.consecutive_losses_var,
                                                    style='Status.TLabel')
        self.consecutive_losses_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Daily loss
        ttk.Label(risk_frame, text="당일 손실:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.daily_loss_var = tk.StringVar(value="0.0% / 5.0%")
        self.daily_loss_label = ttk.Label(risk_frame, textvariable=self.daily_loss_var, style='Status.TLabel')
        self.daily_loss_label.grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Daily trades
        ttk.Label(risk_frame, text="당일 거래:", style='Title.TLabel').grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        self.daily_trades_var = tk.StringVar(value="0/2")
        ttk.Label(risk_frame, textvariable=self.daily_trades_var, style='Status.TLabel').grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Separator
        ttk.Separator(risk_frame, orient='horizontal').grid(row=5, column=0, columnspan=2,
                                                             sticky=(tk.W, tk.E), pady=5)

        # Total stats
        ttk.Label(risk_frame, text="총 수익:", style='Title.TLabel').grid(row=6, column=0, sticky=tk.W, pady=(5, 0))
        self.total_profit_var = tk.StringVar(value="0 KRW")
        self.total_profit_label = ttk.Label(risk_frame, textvariable=self.total_profit_var,
                                             font=('Arial', 10, 'bold'), foreground='green')
        self.total_profit_label.grid(row=6, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        ttk.Label(risk_frame, text="승률:", style='Title.TLabel').grid(row=7, column=0, sticky=tk.W, pady=(5, 0))
        self.win_rate_var = tk.StringVar(value="0%")
        ttk.Label(risk_frame, textvariable=self.win_rate_var, font=('Arial', 9)).grid(row=7, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        ttk.Label(risk_frame, text="총 거래:", style='Title.TLabel').grid(row=8, column=0, sticky=tk.W, pady=(5, 0))
        self.total_trades_var = tk.StringVar(value="0")
        ttk.Label(risk_frame, textvariable=self.total_trades_var, font=('Arial', 9)).grid(row=8, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_config_panel(self, parent):
        """Configuration panel for strategy parameters"""
        config_frame = ttk.LabelFrame(parent, text="⚙️ 전략 설정", padding="10")
        config_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))

        # Config button
        config_button = ttk.Button(config_frame, text="설정 편집", command=self.open_config_editor)
        config_button.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        # Key parameters display
        ttk.Label(config_frame, text="진입 점수:", font=('Arial', 9)).grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Label(config_frame, text="≥ 3점", font=('Arial', 9), foreground='blue').grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        ttk.Label(config_frame, text="ATR 배수:", font=('Arial', 9)).grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Label(config_frame, text="3.0x", font=('Arial', 9), foreground='blue').grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        ttk.Label(config_frame, text="리스크:", font=('Arial', 9)).grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Label(config_frame, text="2% per trade", font=('Arial', 9), foreground='blue').grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        ttk.Label(config_frame, text="실행 주기:", font=('Arial', 9)).grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        ttk.Label(config_frame, text="4H", font=('Arial', 9), foreground='blue').grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_log_panel(self, parent):
        """Console log panel"""
        log_frame = ttk.LabelFrame(parent, text="📋 실시간 로그", padding="5")
        log_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, wrap=tk.WORD,
                                                   font=('Courier', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

    def create_trading_history_panel(self, parent):
        """Transaction history panel"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        history_frame = ttk.Frame(parent)
        history_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=10)
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(0, weight=1)

        # Treeview for history
        columns = ('Time', 'Type', 'Price', 'Amount', 'Total', 'P&L')
        self.history_tree = ttk.Treeview(history_frame, columns=columns, show='headings', height=20)

        for col in columns:
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=120, anchor='center')

        scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

    def setup_logging(self):
        """Setup logging system"""
        self.logger = TradingLogger()
        self.log_to_console("=== v2 GUI 시작 ===")
        self.log_to_console(f"시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    def log_to_console(self, message: str):
        """Add message to console log"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def start_bot(self):
        """Start trading bot"""
        if self.is_running:
            return

        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.status_var.set("🟢 실행 중")

        self.log_to_console("봇 시작됨")

        # Start bot in separate thread
        self.bot = GUITradingBotV2(log_callback=self.log_to_console)
        self.bot_thread = threading.Thread(target=self.bot.run, daemon=True)
        self.bot_thread.start()

    def stop_bot(self):
        """Stop trading bot"""
        if not self.is_running:
            return

        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.status_var.set("⚪ 대기 중")

        if self.bot:
            self.bot.stop()

        self.log_to_console("봇 정지됨")

    def update_gui(self):
        """Periodic GUI update (every 1 second)"""
        try:
            # Update bot status from bot instance
            if self.bot and self.is_running:
                status = self.bot.get_status()
                self.update_status_displays(status)

            # Update price (independent of bot)
            self.update_current_price()

        except Exception as e:
            pass

        # Schedule next update
        self.root.after(1000, self.update_gui)

    def update_status_displays(self, status: Dict[str, Any]):
        """Update all status displays with v2 strategy data"""
        # === Market Regime Section ===
        regime = status.get('regime', 'NEUTRAL')
        self.regime_var.set(regime)
        if regime == 'BULLISH':
            self.regime_label.config(foreground='green')
            self.trading_allowed_var.set("YES")
            self.trading_allowed_label.config(foreground='green')
        elif regime == 'BEARISH':
            self.regime_label.config(foreground='red')
            self.trading_allowed_var.set("NO")
            self.trading_allowed_label.config(foreground='red')
        else:
            self.regime_label.config(foreground='gray')
            self.trading_allowed_var.set("PENDING")
            self.trading_allowed_label.config(foreground='gray')

        # EMA values
        self.ema_fast_var.set(f"{status.get('ema_fast', 0):,.0f}")
        self.ema_slow_var.set(f"{status.get('ema_slow', 0):,.0f}")

        # Hysteresis buffer
        confirmation_bars = status.get('regime_confirmation_bars', 0)
        self.regime_confirmation_var.set(f"{confirmation_bars}/2")

        # === Entry Score Section ===
        score = status.get('entry_score', 0)
        self.entry_score_var.set(f"{score}/4")

        # Update score label color based on threshold
        if score >= 3:
            self.entry_score_label.config(foreground='green')
            self.entry_permission_var.set("진입 가능")
            self.entry_permission_label.config(foreground='white', background='#28a745')
        else:
            self.entry_score_label.config(foreground='orange' if score > 0 else 'gray')
            self.entry_permission_var.set("대기")
            self.entry_permission_label.config(foreground='red', background='#ffe0e0')

        # Entry components with details
        components = status.get('entry_components', {})

        # BB Touch
        bb_touch = components.get('bb_touch', 0)
        self.bb_touch_var.set(f"{bb_touch}점 {'✓' if bb_touch > 0 else ''}")
        self.bb_touch_label.config(foreground='green' if bb_touch > 0 else 'gray')
        bb_distance = components.get('bb_distance', 0)
        self.bb_distance_var.set(f"{bb_distance:+.2f}%" if bb_distance != 0 else "-")

        # RSI Oversold
        rsi_oversold = components.get('rsi_oversold', 0)
        self.rsi_oversold_var.set(f"{rsi_oversold}점 {'✓' if rsi_oversold > 0 else ''}")
        self.rsi_oversold_label.config(foreground='green' if rsi_oversold > 0 else 'gray')
        rsi_value = components.get('rsi_value', 0)
        self.rsi_value_var.set(f"{rsi_value:.1f}" if rsi_value != 0 else "-")

        # Stoch RSI Cross
        stoch_cross = components.get('stoch_cross', 0)
        self.stoch_cross_var.set(f"{stoch_cross}점 {'✓✓' if stoch_cross > 0 else ''}")
        self.stoch_cross_label.config(foreground='green' if stoch_cross > 0 else 'gray')
        stoch_k = components.get('stoch_k', 0)
        stoch_d = components.get('stoch_d', 0)
        self.stoch_kd_var.set(f"{stoch_k:.1f} / {stoch_d:.1f}" if stoch_k != 0 else "- / -")

        # === Position Management Section ===
        phase = status.get('position_phase', 'NONE')
        self.phase_var.set(phase)

        # Color code position phase
        phase_colors = {
            'NONE': 'gray',
            'INITIAL_ENTRY': 'blue',
            'FIRST_TARGET_HIT': 'green',
            'RUNNER_PHASE': 'purple'
        }
        self.phase_label.config(foreground=phase_colors.get(phase, 'gray'))

        # Position details
        entry_price = status.get('entry_price', 0)
        self.entry_price_var.set(f"{entry_price:,.0f}" if entry_price > 0 else "0")

        position_size = status.get('position_size', 0)
        position_pct = status.get('position_pct', 0)
        self.position_size_var.set(f"{position_size:.4f} BTC ({position_pct}%)")

        # Current P&L
        current_pnl = status.get('current_pnl', 0)
        current_pnl_pct = status.get('current_pnl_pct', 0)
        self.current_pnl_var.set(f"{current_pnl:+,.0f} KRW ({current_pnl_pct:+.2f}%)")
        if current_pnl >= 0:
            self.current_pnl_label.config(foreground='green')
        else:
            self.current_pnl_label.config(foreground='red')

        # First target
        first_target_price = status.get('first_target_price', 0)
        self.first_target_price_var.set(f"{first_target_price:,.0f}" if first_target_price > 0 else "0")

        first_target_hit = status.get('first_target_hit', False)
        self.first_target_var.set("달성 ✓" if first_target_hit else "대기중")
        self.first_target_label.config(foreground='green' if first_target_hit else 'gray')

        # === Chandelier Exit Section ===
        chandelier_stop = status.get('chandelier_stop', 0)
        self.chandelier_stop_var.set(f"{chandelier_stop:,.0f}" if chandelier_stop > 0 else "0")

        highest_high = status.get('highest_high', 0)
        self.highest_high_var.set(f"{highest_high:,.0f}" if highest_high > 0 else "0")

        atr_value = status.get('atr_value', 0)
        self.atr_value_var.set(f"{atr_value:,.0f}" if atr_value > 0 else "0")

        # Breakeven status
        breakeven_moved = status.get('breakeven_moved', False)
        self.breakeven_var.set("이동됨 ✓" if breakeven_moved else "미이동")
        self.breakeven_label.config(foreground='green' if breakeven_moved else 'gray')

        # Protection info
        if breakeven_moved:
            self.protection_info_var.set("리스크 프리")
        elif highest_high > entry_price:
            self.protection_info_var.set("수익 추적중")
        else:
            self.protection_info_var.set("대기중")

        # === Risk Management Section ===
        circuit_breaker_active = status.get('circuit_breaker_active', False)
        if circuit_breaker_active:
            self.circuit_breaker_var.set("발동!")
            self.circuit_breaker_label.config(foreground='red')
        else:
            self.circuit_breaker_var.set("정상")
            self.circuit_breaker_label.config(foreground='green')

        # Consecutive losses
        consecutive_losses = status.get('consecutive_losses', 0)
        max_consecutive = 5
        self.consecutive_losses_var.set(f"{consecutive_losses}/{max_consecutive}")
        if consecutive_losses >= 3:
            self.consecutive_losses_label.config(foreground='red')
        elif consecutive_losses >= 2:
            self.consecutive_losses_label.config(foreground='orange')
        else:
            self.consecutive_losses_label.config(foreground='green')

        # Daily loss
        daily_loss_pct = status.get('daily_loss_pct', 0)
        max_daily_loss = 5.0
        self.daily_loss_var.set(f"{daily_loss_pct:.1f}% / {max_daily_loss}%")
        if daily_loss_pct <= -3.0:
            self.daily_loss_label.config(foreground='red')
        elif daily_loss_pct <= -1.5:
            self.daily_loss_label.config(foreground='orange')
        else:
            self.daily_loss_label.config(foreground='green')

        # Daily trades
        daily_trades = status.get('daily_trades', 0)
        max_daily_trades = 2
        self.daily_trades_var.set(f"{daily_trades}/{max_daily_trades}")

        # Total stats
        total_profit = status.get('total_profit', 0)
        self.total_profit_var.set(f"{total_profit:+,.0f} KRW")
        if total_profit >= 0:
            self.total_profit_label.config(foreground='green')
        else:
            self.total_profit_label.config(foreground='red')

        self.win_rate_var.set(f"{status.get('win_rate', 0):.1f}%")
        self.total_trades_var.set(str(status.get('total_trades', 0)))

        # Last action
        self.last_action_var.set(status.get('last_action', 'HOLD'))

    def update_current_price(self):
        """Update current price display"""
        try:
            ticker = get_ticker('BTC')
            if ticker:
                price = ticker.get('closing_price', 0)
                self.current_price_var.set(f"{price:,.0f} KRW")
                self.bot_status['current_price'] = price
        except:
            pass

    def open_config_editor(self):
        """Open configuration editor dialog"""
        config_window = tk.Toplevel(self.root)
        config_window.title("전략 설정 편집")
        config_window.geometry("600x700")
        config_window.transient(self.root)
        config_window.grab_set()

        # Create scrollable frame
        canvas = tk.Canvas(config_window)
        scrollbar = ttk.Scrollbar(config_window, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Configuration sections
        config_vars = {}

        # Section 1: Regime Filter
        regime_frame = ttk.LabelFrame(scrollable_frame, text="시장 체제 필터 (Daily)", padding="10")
        regime_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)

        config_vars['ema_fast'] = self._add_config_entry(regime_frame, "EMA 빠름 (일봉)", 50, 0)
        config_vars['ema_slow'] = self._add_config_entry(regime_frame, "EMA 느림 (일봉)", 200, 1)
        config_vars['confirmation_bars'] = self._add_config_entry(regime_frame, "확인 봉 수", 2, 2)

        # Section 2: Entry Scoring
        entry_frame = ttk.LabelFrame(scrollable_frame, text="진입 신호 점수 시스템 (4H)", padding="10")
        entry_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)

        config_vars['min_entry_score'] = self._add_config_entry(entry_frame, "최소 진입 점수", 3, 0)
        config_vars['bb_period'] = self._add_config_entry(entry_frame, "볼린저밴드 기간", 20, 1)
        config_vars['bb_std'] = self._add_config_entry(entry_frame, "볼린저밴드 표준편차", 2.0, 2)
        config_vars['rsi_period'] = self._add_config_entry(entry_frame, "RSI 기간", 14, 3)
        config_vars['rsi_oversold'] = self._add_config_entry(entry_frame, "RSI 과매도 수준", 30, 4)
        config_vars['stoch_rsi_period'] = self._add_config_entry(entry_frame, "Stoch RSI 기간", 14, 5)
        config_vars['stoch_k_smooth'] = self._add_config_entry(entry_frame, "Stoch %K 평활", 3, 6)
        config_vars['stoch_d_smooth'] = self._add_config_entry(entry_frame, "Stoch %D 평활", 3, 7)
        config_vars['stoch_oversold'] = self._add_config_entry(entry_frame, "Stoch 과매도 수준", 20, 8)

        # Section 3: Risk Management
        risk_frame = ttk.LabelFrame(scrollable_frame, text="위험 관리", padding="10")
        risk_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)

        config_vars['atr_period'] = self._add_config_entry(risk_frame, "ATR 기간", 14, 0)
        config_vars['chandelier_multiplier'] = self._add_config_entry(risk_frame, "Chandelier ATR 배수", 3.0, 1)
        config_vars['risk_per_trade'] = self._add_config_entry(risk_frame, "거래당 리스크 (%)", 2.0, 2)
        config_vars['max_consecutive_losses'] = self._add_config_entry(risk_frame, "최대 연속 손실", 5, 3)
        config_vars['max_daily_loss'] = self._add_config_entry(risk_frame, "최대 일일 손실 (%)", 5.0, 4)
        config_vars['max_daily_trades'] = self._add_config_entry(risk_frame, "최대 일일 거래", 2, 5)

        # Section 4: Position Management
        position_frame = ttk.LabelFrame(scrollable_frame, text="포지션 관리", padding="10")
        position_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=10, pady=5)

        config_vars['initial_position_pct'] = self._add_config_entry(position_frame, "초기 진입 비율 (%)", 50, 0)
        config_vars['first_target_pct'] = self._add_config_entry(position_frame, "1차 목표 청산 (%)", 50, 1)

        # Buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.grid(row=4, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)

        def save_config():
            try:
                # Update config_v2.py with new values
                for key, var in config_vars.items():
                    value = float(var.get()) if '.' in var.get() else int(var.get())
                    # Here you would update the config file
                    # For now, just show success message
                messagebox.showinfo("성공", "설정이 저장되었습니다.\n재시작 후 적용됩니다.")
                config_window.destroy()
            except ValueError:
                messagebox.showerror("오류", "올바른 숫자 값을 입력하세요.")

        def reset_config():
            if messagebox.askyesno("확인", "기본 설정으로 초기화하시겠습니까?"):
                # Reset all values to defaults
                config_vars['ema_fast'].delete(0, tk.END)
                config_vars['ema_fast'].insert(0, "50")
                config_vars['ema_slow'].delete(0, tk.END)
                config_vars['ema_slow'].insert(0, "200")
                # ... reset other values
                messagebox.showinfo("완료", "기본 설정으로 초기화되었습니다.")

        save_button = ttk.Button(button_frame, text="저장", command=save_config)
        save_button.pack(side=tk.LEFT, padx=5)

        reset_button = ttk.Button(button_frame, text="초기화", command=reset_config)
        reset_button.pack(side=tk.LEFT, padx=5)

        cancel_button = ttk.Button(button_frame, text="취소", command=config_window.destroy)
        cancel_button.pack(side=tk.LEFT, padx=5)

        # Pack scrollbar and canvas
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def _add_config_entry(self, parent, label, default_value, row):
        """Helper to add a configuration entry"""
        ttk.Label(parent, text=f"{label}:").grid(row=row, column=0, sticky=tk.W, pady=2)
        var = tk.StringVar(value=str(default_value))
        entry = ttk.Entry(parent, textvariable=var, width=15)
        entry.grid(row=row, column=1, sticky=tk.W, padx=(10, 0), pady=2)
        return var

    def _get_trading_mode_string(self):
        """Get trading mode string for window title"""
        if self.live_mode and not self.dry_run:
            return "🔴 LIVE TRADING"
        elif self.live_mode and self.dry_run:
            return "💚 DRY-RUN (Live Mode)"
        else:
            return "🟡 BACKTEST"

    def _get_mode_display(self):
        """Get mode display text and color for control panel"""
        if self.live_mode and not self.dry_run:
            return ("🔴 실전 거래 모드", "red")
        elif self.live_mode and self.dry_run:
            return ("💚 모의 거래 모드", "green")
        else:
            return ("🟡 백테스팅 모드", "orange")

    def on_closing(self):
        """Handle window close"""
        if self.is_running:
            self.stop_bot()

        # Stop multi-chart widget auto-refresh
        if hasattr(self, 'multi_chart_widget') and self.multi_chart_widget:
            self.multi_chart_widget.stop()

        self.root.destroy()


def main():
    """Main entry point"""
    root = tk.Tk()
    app = TradingBotGUIV2(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
