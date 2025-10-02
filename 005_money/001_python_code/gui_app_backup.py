#!/usr/bin/env python3
"""
빗썸 자동매매 봇 GUI 애플리케이션
실시간 로그, 거래 상태, 수익 현황을 표시하고 설정 변경 가능
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
import json
import sys
import os
from datetime import datetime  # FIX: Removed unused timedelta import
from typing import Dict, Any, Optional
import logging

# Ensure working directory is project root (parent of 001_python_code)
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
os.chdir(project_root)

# Add 001_python_code to Python path for imports
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
    def __init__(self, root):
        self.root = root
        self.root.title("🤖 빗썸 자동매매 봇")
        # Optimized window size for better layout
        self.root.geometry("1400x850")
        self.root.minsize(1200, 700)

        # 상태 변수
        self.bot = None
        self.bot_thread = None
        self.is_running = False
        # FIX: Limit queue size to prevent unbounded memory growth (max 1000 messages)
        self.log_queue = queue.Queue(maxsize=1000)
        self.config_manager = ConfigManager()
        self.transaction_history = TransactionHistory()

        # 실시간 상태 데이터
        self.bot_status = {
            'coin': 'BTC',
            'current_price': 0,
            'avg_buy_price': 0,
            'holdings': 0,
            'pending_orders': [],
            'last_action': 'HOLD'
        }

        # GUI 컴포넌트 초기화
        self.setup_styles()
        self.create_widgets()
        self.setup_logging()

        # 주기적 업데이트 시작
        self.update_gui()

    def setup_styles(self):
        """GUI 스타일 설정"""
        style = ttk.Style()
        style.theme_use('clam')

        # 커스텀 스타일 정의
        style.configure('Title.TLabel', font=('Arial', 12, 'bold'))
        style.configure('Status.TLabel', font=('Arial', 10))
        style.configure('Profit.TLabel', font=('Arial', 11, 'bold'))
        style.configure('Loss.TLabel', font=('Arial', 11, 'bold'), foreground='red')

    def create_widgets(self):
        """GUI 위젯 생성"""
        # 메인 프레임
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # 그리드 가중치 설정
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # 상단 제어 패널
        self.create_control_panel(main_frame)

        # 중앙 메인 영역을 노트북(탭)으로 구성
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))

        # 메인 탭 (기존 거래 화면)
        main_tab = ttk.Frame(self.notebook)
        self.notebook.add(main_tab, text='거래 현황')

        # 실시간 차트 탭 (NEW!)
        chart_tab = ttk.Frame(self.notebook)
        self.notebook.add(chart_tab, text='📊 실시간 차트')

        # 신호 히스토리 탭 (NEW!)
        signal_history_tab = ttk.Frame(self.notebook)
        self.notebook.add(signal_history_tab, text='📋 신호 히스토리')

        # 거래 내역 탭
        history_tab = ttk.Frame(self.notebook)
        self.notebook.add(history_tab, text='거래 내역')

        # 메인 탭 내용 (좌우 분할)
        main_paned = ttk.PanedWindow(main_tab, orient=tk.HORIZONTAL)
        main_paned.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        main_tab.columnconfigure(0, weight=1)
        main_tab.rowconfigure(0, weight=1)

        # 왼쪽 패널 (스크롤 가능한 영역으로 변경)
        # 1. 스크롤바와 캔버스를 담을 컨테이너 프레임 생성
        left_scroll_container = ttk.Frame(main_paned)
        main_paned.add(left_scroll_container, weight=1)
        left_scroll_container.grid_rowconfigure(0, weight=1)
        left_scroll_container.grid_columnconfigure(0, weight=1)

        # 2. 캔버스 생성
        canvas = tk.Canvas(left_scroll_container)
        canvas.grid(row=0, column=0, sticky='nsew')

        # 3. 스크롤바 생성 및 캔버스와 연결
        scrollbar = ttk.Scrollbar(left_scroll_container, orient='vertical', command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=scrollbar.set)

        # 4. 캔버스 내부에 실제 위젯들이 들어갈 프레임 생성
        scrollable_frame = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')

        # 5. 스크롤 영역이 변경될 때 캔버스 업데이트
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox('all'))
        scrollable_frame.bind('<Configure>', on_frame_configure)

        # 오른쪽 패널 (로그)
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)

        # 왼쪽 패널 구성 (엘리트 전략 패널들 추가!)
        # 이제 scrollable_frame에 위젯들을 추가합니다.
        self.create_status_panel(scrollable_frame)
        self.create_settings_panel(scrollable_frame)
        self.create_weight_adjustment_panel(scrollable_frame)  # NEW! Weight Adjustment Panel
        self.create_market_regime_panel(scrollable_frame)  # NEW!
        self.create_signal_panel(scrollable_frame)          # NEW!
        self.create_risk_panel(scrollable_frame)            # NEW!
        self.create_profit_panel(scrollable_frame)

        # 오른쪽 패널 구성 (로그)
        self.create_log_panel(right_frame)

        # 실시간 차트 탭 구성 (NEW!)
        chart_tab.columnconfigure(0, weight=1)
        chart_tab.rowconfigure(0, weight=1)
        self.chart_widget = ChartWidget(chart_tab, self.config_manager.get_config())

        # 신호 히스토리 탭 구성 (NEW!)
        signal_history_tab.columnconfigure(0, weight=1)
        signal_history_tab.rowconfigure(0, weight=1)
        self.signal_history_widget = SignalHistoryWidget(signal_history_tab)

        # 거래 내역 탭 구성
        self.create_trading_history_panel(history_tab)

    def create_control_panel(self, parent):
        """상단 제어 패널"""
        control_frame = ttk.LabelFrame(parent, text="🎮 봇 제어", padding="10")
        control_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # 시작/정지 버튼
        self.start_button = ttk.Button(control_frame, text="🚀 봇 시작", command=self.start_bot)
        self.start_button.grid(row=0, column=0, padx=(0, 5))

        self.stop_button = ttk.Button(control_frame, text="⏹ 봇 정지", command=self.stop_bot, state=tk.DISABLED)
        self.stop_button.grid(row=0, column=1, padx=5)

        # 상태 표시
        self.status_var = tk.StringVar(value="⚪ 대기 중")
        status_label = ttk.Label(control_frame, textvariable=self.status_var, style='Status.TLabel')
        status_label.grid(row=0, column=2, padx=(20, 0))

        # 모드 표시
        current_config = self.config_manager.get_config()
        mode_text = "🟡 모의 거래" if current_config['safety']['dry_run'] else "🔴 실제 거래"
        self.mode_var = tk.StringVar(value=mode_text)
        mode_label = ttk.Label(control_frame, textvariable=self.mode_var, style='Status.TLabel')
        mode_label.grid(row=0, column=3, padx=(20, 0))

    def create_status_panel(self, parent):
        """거래 상태 패널"""
        status_frame = ttk.LabelFrame(parent, text="📊 거래 상태", padding="10")
        status_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))
        parent.columnconfigure(0, weight=1)

        # 현재 거래 코인
        ttk.Label(status_frame, text="거래 코인:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.current_coin_var = tk.StringVar(value="BTC")
        ttk.Label(status_frame, textvariable=self.current_coin_var, style='Status.TLabel').grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # 현재 가격
        ttk.Label(status_frame, text="현재 가격:", style='Title.TLabel').grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.current_price_var = tk.StringVar(value="0 KRW")
        ttk.Label(status_frame, textvariable=self.current_price_var, style='Status.TLabel').grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 평균 매수가
        ttk.Label(status_frame, text="평균 매수가:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.avg_buy_price_var = tk.StringVar(value="0 KRW")
        ttk.Label(status_frame, textvariable=self.avg_buy_price_var, style='Status.TLabel').grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 보유 수량
        ttk.Label(status_frame, text="보유 수량:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.holdings_var = tk.StringVar(value="0")
        ttk.Label(status_frame, textvariable=self.holdings_var, style='Status.TLabel').grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 체결 대기 주문
        ttk.Label(status_frame, text="대기 주문:", style='Title.TLabel').grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        self.pending_orders_var = tk.StringVar(value="없음")
        ttk.Label(status_frame, textvariable=self.pending_orders_var, style='Status.TLabel').grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_settings_panel(self, parent):
        """설정 패널"""
        settings_frame = ttk.LabelFrame(parent, text="⚙️ 엘리트 전략 설정", padding="10")
        settings_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))
        current_config = self.config_manager.get_config()

        # 전략 프리셋 선택 (NEW!)
        preset_frame = ttk.LabelFrame(settings_frame, text="🎯 전략 프리셋", padding="10")
        preset_frame.grid(row=0, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(preset_frame, text="전략:", style='Title.TLabel').pack(side=tk.LEFT, padx=(0, 10))

        self.strategy_preset_var = tk.StringVar(value="Balanced Elite")
        strategy_combo = ttk.Combobox(preset_frame, textvariable=self.strategy_preset_var, width=20, state='readonly')
        strategy_combo['values'] = (
            'Balanced Elite',
            'MACD + RSI Filter',
            'Trend Following',
            'Mean Reversion',
            'Custom'
        )
        strategy_combo.pack(side=tk.LEFT, padx=(0, 10))
        strategy_combo.bind('<<ComboboxSelected>>', self.on_strategy_preset_changed)

        # 프리셋 설명 레이블
        self.preset_desc_var = tk.StringVar(value="균형잡힌 올라운드 전략")
        ttk.Label(preset_frame, textvariable=self.preset_desc_var,
                 foreground='blue', font=('Arial', 9, 'italic')).pack(side=tk.LEFT, padx=(10, 0))

        # 기술 지표 선택 패널 (8개 지표로 확장!)
        indicator_frame = ttk.LabelFrame(settings_frame, text="📊 엘리트 기술 지표 (8개)", padding="10")
        indicator_frame.grid(row=1, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(0, 10))

        # 지표 체크박스 및 LED 변수 초기화 (8개 지표)
        self.indicator_vars = {
            'ma': tk.BooleanVar(value=True), 'rsi': tk.BooleanVar(value=True),
            'bb': tk.BooleanVar(value=True), 'volume': tk.BooleanVar(value=True),
            'macd': tk.BooleanVar(value=True), 'atr': tk.BooleanVar(value=True),
            'stochastic': tk.BooleanVar(value=True), 'adx': tk.BooleanVar(value=True)
        }
        self.indicator_leds = {}
        self.led_states = { 'ma': 0, 'rsi': 0, 'bb': 0, 'volume': 0, 'macd': 0, 'atr': 0, 'stochastic': 0, 'adx': 0 }
        self.led_blink_state = False
        self.indicator_value_labels = {}

        indicators = [
            ('ma', '이동평균선 (MA)', 0, 0), ('macd', 'MACD (NEW)', 0, 1),
            ('rsi', 'RSI', 1, 0), ('stochastic', 'Stochastic (NEW)', 1, 1),
            ('bb', '볼린저 밴드 (BB)', 2, 0), ('atr', 'ATR (NEW)', 2, 1),
            ('volume', '거래량', 3, 0), ('adx', 'ADX (NEW)', 3, 1)
        ]

        for key, label, row, col in indicators:
            indicator_item_frame = ttk.Frame(indicator_frame)
            indicator_item_frame.grid(row=row, column=col, sticky=tk.W, padx=10, pady=5)
            led_check_frame = ttk.Frame(indicator_item_frame)
            led_check_frame.pack(side=tk.TOP, anchor=tk.W)
            led_canvas = tk.Canvas(led_check_frame, width=20, height=20, bg='white', highlightthickness=0)
            led_canvas.pack(side=tk.LEFT, padx=(0, 5))
            led_circle = led_canvas.create_oval(5, 5, 15, 15, fill='gray', outline='darkgray')
            self.indicator_leds[key] = {'canvas': led_canvas, 'circle': led_circle}
            check = ttk.Checkbutton(led_check_frame, text=label, variable=self.indicator_vars[key], command=self.validate_indicator_selection)
            check.pack(side=tk.LEFT)
            value_label = ttk.Label(indicator_item_frame, text="값: -", font=('Arial', 8), foreground='gray')
            value_label.pack(side=tk.TOP, anchor=tk.W, padx=(25, 0))
            self.indicator_value_labels[key] = value_label

        # 리스크 및 상세 전략 설정
        risk_rsi_frame = ttk.LabelFrame(settings_frame, text="⚙️ 리스크 및 상세 전략", padding="10")
        risk_rsi_frame.grid(row=2, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 0))

        ttk.Label(risk_rsi_frame, text="손절(%):").grid(row=0, column=0, sticky=tk.W)
        self.stop_loss_var = tk.StringVar(value=str(current_config['trading']['stop_loss_percent']))
        ttk.Entry(risk_rsi_frame, textvariable=self.stop_loss_var, width=8).grid(row=0, column=1, sticky=tk.W, padx=(5, 15))

        ttk.Label(risk_rsi_frame, text="익절(%):").grid(row=0, column=2, sticky=tk.W)
        self.take_profit_var = tk.StringVar(value=str(current_config['trading']['take_profit_percent']))
        ttk.Entry(risk_rsi_frame, textvariable=self.take_profit_var, width=8).grid(row=0, column=3, sticky=tk.W, padx=5)

        ttk.Label(risk_rsi_frame, text="RSI 매수(≤):").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        self.rsi_buy_var = tk.StringVar(value=str(current_config['strategy']['rsi_buy_threshold']))
        ttk.Entry(risk_rsi_frame, textvariable=self.rsi_buy_var, width=8).grid(row=1, column=1, sticky=tk.W, padx=(5, 15), pady=(5,0))

        ttk.Label(risk_rsi_frame, text="RSI 매도(≥):").grid(row=1, column=2, sticky=tk.W, pady=(5,0))
        self.rsi_sell_var = tk.StringVar(value=str(current_config['strategy']['rsi_sell_threshold']))
        ttk.Entry(risk_rsi_frame, textvariable=self.rsi_sell_var, width=8).grid(row=1, column=3, sticky=tk.W, padx=5, pady=(5,0))

        ttk.Label(risk_rsi_frame, text="분석 기간(봉):").grid(row=2, column=0, sticky=tk.W, pady=(5,0))
        self.period_var = tk.StringVar(value=str(current_config['strategy']['analysis_period']))
        ttk.Entry(risk_rsi_frame, textvariable=self.period_var, width=8).grid(row=2, column=1, sticky=tk.W, padx=(5, 15), pady=(5,0))

        # 기본 거래 설정
        base_trade_frame = ttk.LabelFrame(settings_frame, text="🔩 기본 거래 설정", padding="10")
        base_trade_frame.grid(row=3, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 0))

        ttk.Label(base_trade_frame, text="거래 코인:").grid(row=0, column=0, sticky=tk.W)
        self.coin_var = tk.StringVar()
        self.coin_combo = ttk.Combobox(base_trade_frame, textvariable=self.coin_var, width=10, values=('BTC', 'ETH', 'XRP', 'ADA', 'DOT', 'LINK', 'LTC', 'BCH', 'EOS', 'TRX'))
        self.coin_combo.grid(row=0, column=1, sticky=tk.W, padx=(10, 20))
        self.coin_combo.set(current_config['trading']['target_ticker'])

        ttk.Label(base_trade_frame, text="캔들 간격:").grid(row=0, column=2, sticky=tk.W)
        self.candle_interval_var = tk.StringVar()
        candle_interval_combo = ttk.Combobox(base_trade_frame, textvariable=self.candle_interval_var, width=10, state='readonly', values=('30m', '1h', '6h', '12h', '24h'))
        candle_interval_combo.grid(row=0, column=3, sticky=tk.W, padx=10)
        default_interval = current_config['strategy'].get('candlestick_interval', '1h')
        candle_interval_combo.set(default_interval if default_interval else '1h')
        candle_interval_combo.bind('<<ComboboxSelected>>', self.on_candle_interval_changed)

        ttk.Label(base_trade_frame, text="체크 간격:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        self.interval_var = tk.StringVar()
        self.interval_combo = ttk.Combobox(base_trade_frame, textvariable=self.interval_var, width=10, values=('10s', '30s', '1m', '5m', '10m', '30m', '1h', '2h', '4h'))
        self.interval_combo.grid(row=1, column=1, sticky=tk.W, padx=(10, 20), pady=(5,0))
        self.interval_combo.set('15m')

        ttk.Label(base_trade_frame, text="거래 금액(원):").grid(row=1, column=2, sticky=tk.W, pady=(5,0))
        self.amount_var = tk.StringVar()
        self.amount_entry = ttk.Entry(base_trade_frame, textvariable=self.amount_var, width=12)
        self.amount_entry.grid(row=1, column=3, sticky=tk.W, padx=10, pady=(5,0))
        self.amount_entry.insert(0, str(current_config['trading']['trade_amount_krw']))

        # 설정 적용 버튼
        apply_button = ttk.Button(settings_frame, text="📝 모든 설정 적용", command=self.apply_settings)
        apply_button.grid(row=4, column=0, columnspan=4, pady=(15, 0))

    def create_market_regime_panel(self, parent):
        """시장 국면 패널 (NEW!)"""
        regime_frame = ttk.LabelFrame(parent, text="🔵 시장 국면 분석", padding="10")
        regime_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))

        # 시장 국면 표시
        ttk.Label(regime_frame, text="시장 국면:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.regime_var = tk.StringVar(value="분석 대기 중")
        self.regime_label = ttk.Label(regime_frame, textvariable=self.regime_var,
                                      font=('Arial', 10, 'bold'), foreground='blue')
        self.regime_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # 변동성 수준
        ttk.Label(regime_frame, text="변동성:", style='Title.TLabel').grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.volatility_var = tk.StringVar(value="-")
        ttk.Label(regime_frame, textvariable=self.volatility_var, style='Status.TLabel').grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 추세 강도 (ADX)
        ttk.Label(regime_frame, text="추세 강도:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.trend_strength_var = tk.StringVar(value="-")
        ttk.Label(regime_frame, textvariable=self.trend_strength_var, style='Status.TLabel').grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 권장 전략
        ttk.Label(regime_frame, text="권장 전략:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.recommendation_var = tk.StringVar(value="-")
        self.recommendation_label = ttk.Label(regime_frame, textvariable=self.recommendation_var,
                                             font=('Arial', 9), foreground='green')
        self.recommendation_label.grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_signal_panel(self, parent):
        """종합 신호 패널 (NEW!)"""
        signal_frame = ttk.LabelFrame(parent, text="🎯 종합 신호", padding="10")
        signal_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))

        # 종합 신호
        ttk.Label(signal_frame, text="신호:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.overall_signal_var = tk.StringVar(value="HOLD")
        self.overall_signal_label = ttk.Label(signal_frame, textvariable=self.overall_signal_var,
                                             font=('Arial', 14, 'bold'), foreground='gray')
        self.overall_signal_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # 신호 강도 (Progress bar)
        ttk.Label(signal_frame, text="신호 강도:", style='Title.TLabel').grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.signal_strength_var = tk.StringVar(value="0.00")
        strength_frame = ttk.Frame(signal_frame)
        strength_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=(5, 0))

        self.signal_strength_bar = ttk.Progressbar(strength_frame, length=150, mode='determinate')
        self.signal_strength_bar.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(strength_frame, textvariable=self.signal_strength_var, style='Status.TLabel').pack(side=tk.LEFT)

        # 신뢰도 (Progress bar)
        ttk.Label(signal_frame, text="신뢰도:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.confidence_var = tk.StringVar(value="0.00")
        confidence_frame = ttk.Frame(signal_frame)
        confidence_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(10, 0), pady=(5, 0))

        self.confidence_bar = ttk.Progressbar(confidence_frame, length=150, mode='determinate')
        self.confidence_bar.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Label(confidence_frame, textvariable=self.confidence_var, style='Status.TLabel').pack(side=tk.LEFT)

    def create_risk_panel(self, parent):
        """리스크 관리 패널 (ATR 기반, NEW!)"""
        risk_frame = ttk.LabelFrame(parent, text="⚠️ ATR 기반 리스크 관리", padding="10")
        risk_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))

        # 진입가
        ttk.Label(risk_frame, text="진입가:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.entry_price_var = tk.StringVar(value="-")
        ttk.Label(risk_frame, textvariable=self.entry_price_var, style='Status.TLabel').grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # 손절가
        ttk.Label(risk_frame, text="손절가:", style='Title.TLabel').grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.stop_loss_price_var = tk.StringVar(value="-")
        self.stop_loss_price_label = ttk.Label(risk_frame, textvariable=self.stop_loss_price_var,
                                               foreground='red', font=('Arial', 9))
        self.stop_loss_price_label.grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 1차 익절가
        ttk.Label(risk_frame, text="익절1:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.tp1_price_var = tk.StringVar(value="-")
        self.tp1_price_label = ttk.Label(risk_frame, textvariable=self.tp1_price_var,
                                        foreground='green', font=('Arial', 9))
        self.tp1_price_label.grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 2차 익절가
        ttk.Label(risk_frame, text="익절2:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.tp2_price_var = tk.StringVar(value="-")
        self.tp2_price_label = ttk.Label(risk_frame, textvariable=self.tp2_price_var,
                                        foreground='darkgreen', font=('Arial', 9))
        self.tp2_price_label.grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # Risk:Reward 비율
        ttk.Label(risk_frame, text="R:R 비율:", style='Title.TLabel').grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        self.rr_ratio_var = tk.StringVar(value="-")
        ttk.Label(risk_frame, textvariable=self.rr_ratio_var, style='Status.TLabel').grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

    def create_profit_panel(self, parent):
        """수익 현황 패널"""
        profit_frame = ttk.LabelFrame(parent, text="💰 수익 현황", padding="10")
        profit_frame.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        parent.rowconfigure(5, weight=1)

        # 일일 수익
        ttk.Label(profit_frame, text="오늘 수익:", style='Title.TLabel').grid(row=0, column=0, sticky=tk.W)
        self.daily_profit_var = tk.StringVar(value="0 KRW")
        self.daily_profit_label = ttk.Label(profit_frame, textvariable=self.daily_profit_var, style='Status.TLabel')
        self.daily_profit_label.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))

        # 총 수익
        ttk.Label(profit_frame, text="총 수익:", style='Title.TLabel').grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        self.total_profit_var = tk.StringVar(value="0 KRW")
        self.total_profit_label = ttk.Label(profit_frame, textvariable=self.total_profit_var, style='Status.TLabel')
        self.total_profit_label.grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 거래 횟수
        ttk.Label(profit_frame, text="오늘 거래:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.daily_trades_var = tk.StringVar(value="0회")
        ttk.Label(profit_frame, textvariable=self.daily_trades_var, style='Status.TLabel').grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 성공률
        ttk.Label(profit_frame, text="성공률:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.success_rate_var = tk.StringVar(value="0%")
        ttk.Label(profit_frame, textvariable=self.success_rate_var, style='Status.TLabel').grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))

        # 수익 차트 (간단한 텍스트 기반)
        chart_frame = ttk.Frame(profit_frame)
        chart_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))
        profit_frame.rowconfigure(4, weight=1)

        self.profit_chart = scrolledtext.ScrolledText(chart_frame, height=8, width=30, wrap=tk.WORD)
        self.profit_chart.pack(fill=tk.BOTH, expand=True)

    def create_log_panel(self, parent):
        """로그 패널"""
        log_frame = ttk.LabelFrame(parent, text="📝 실시간 로그", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True)

        # 로그 텍스트 위젯
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 로그 레벨별 색상 태그 설정
        self.log_text.tag_configure("INFO", foreground="blue")
        self.log_text.tag_configure("WARNING", foreground="orange")
        self.log_text.tag_configure("ERROR", foreground="red")
        self.log_text.tag_configure("SUCCESS", foreground="green")

        # 로그 클리어 버튼
        clear_button = ttk.Button(log_frame, text="🗑 로그 지우기", command=self.clear_logs)
        clear_button.pack(pady=(10, 0))

    def on_candle_interval_changed(self, event=None):
        """캔들 간격 변경 시 호출"""
        interval = self.candle_interval_var.get()

        # 설정 업데이트
        config = self.config_manager.get_config()
        config['strategy']['candlestick_interval'] = interval

        # 권장 체크 주기 제안
        recommended_periods = config['schedule'].get('interval_check_periods', {})
        if interval in recommended_periods:
            recommended_minutes = recommended_periods[interval]
            # 분을 문자열로 변환 (1h = 60분, 2h = 120분 등)
            if recommended_minutes >= 60:
                hours = recommended_minutes // 60
                recommended_str = f"{hours}h"
            else:
                recommended_str = f"{recommended_minutes}m"

            # 체크 간격 자동 설정 제안
            result = messagebox.askyesno(
                "체크 주기 변경 제안",
                f"캔들 간격을 {interval}로 변경했습니다.\n\n"
                f"권장 체크 주기: {recommended_str}\n"
                f"체크 주기를 자동으로 변경하시겠습니까?"
            )
            if result:
                self.interval_var.set(recommended_str)

        self.log_message(f"캔들 간격이 {interval}로 변경되었습니다.")

    def on_strategy_preset_changed(self, event=None):
        """전략 프리셋 변경 시 호출"""
        preset = self.strategy_preset_var.get()

        # 프리셋별 설명 및 가중치
        preset_info = {
            'Balanced Elite': {
                'desc': '균형잡힌 올라운드 전략',
                'weights': {'macd': 0.35, 'ma': 0.25, 'rsi': 0.20, 'bb': 0.10, 'volume': 0.10}
            },
            'MACD + RSI Filter': {
                'desc': '추세 추종 + 모멘텀 필터',
                'weights': {'macd': 0.40, 'rsi': 0.30, 'ma': 0.20, 'bb': 0.10, 'volume': 0.00}
            },
            'Trend Following': {
                'desc': '추세장 전용 (ADX > 25)',
                'weights': {'macd': 0.40, 'ma': 0.30, 'rsi': 0.15, 'bb': 0.05, 'volume': 0.10}
            },
            'Mean Reversion': {
                'desc': '횡보장 전용 (ADX < 20)',
                'weights': {'rsi': 0.35, 'bb': 0.25, 'macd': 0.15, 'ma': 0.15, 'volume': 0.10}
            },
            'Custom': {
                'desc': '사용자 정의 (수동 조정)',
                'weights': None
            }
        }

        if preset in preset_info:
            info = preset_info[preset]
            self.preset_desc_var.set(info['desc'])

            # 가중치를 config에 저장 (apply_settings에서 사용)
            if info['weights'] is not None:
                config = self.config_manager.get_config()
                config['strategy']['signal_weights'] = info['weights']
                config['strategy']['current_preset'] = preset
                self.add_log("INFO", f"전략 프리셋 변경: {preset} - {info['desc']}")
            else:
                self.add_log("INFO", f"커스텀 전략 선택됨 - 수동으로 가중치를 조정하세요")

    def validate_indicator_selection(self):
        """지표 선택 검증 - 최소 2개 이상 선택 필요"""
        selected_count = sum(1 for var in self.indicator_vars.values() if var.get())

        if selected_count < 2:
            # 최소 2개 미만인 경우 경고 메시지
            messagebox.showwarning(
                "지표 선택 오류",
                "최소 2개 이상의 기술 지표를 선택해야 합니다.\n\n"
                "안전한 거래 결정을 위해 여러 지표를 조합하는 것이 중요합니다."
            )
            # 선택 해제 되돌리기 (마지막 체크박스 다시 활성화)
            for var in self.indicator_vars.values():
                if not var.get():
                    var.set(True)
                    break
            return False
        return True

    def update_indicator_leds(self, signals: Dict[str, Any], analysis: Dict[str, Any] = None):
        """지표별 LED 상태 및 값 업데이트 (8개 지표 지원)"""
        try:
            # 가중치 기반 신호 (연속값 -1.0 ~ +1.0)를 3단계로 변환
            def signal_to_led_state(signal_value: float) -> int:
                """신호 강도를 LED 상태로 변환"""
                if signal_value >= 0.3:
                    return 1  # 매수 (빨강)
                elif signal_value <= -0.3:
                    return -1  # 매도 (파랑)
                else:
                    return 0  # 중립 (회색)

            # 신호 매핑 (8개 지표)
            signal_mapping = {
                'ma': signal_to_led_state(signals.get('ma_signal', 0)),
                'rsi': signal_to_led_state(signals.get('rsi_signal', 0)),
                'bb': signal_to_led_state(signals.get('bb_signal', 0)),
                'volume': signal_to_led_state(signals.get('volume_signal', 0)),
                'macd': signal_to_led_state(signals.get('macd_signal', 0)),
                'stochastic': signal_to_led_state(signals.get('stoch_signal', 0)),
                'atr': 0,  # ATR은 신호가 아니므로 항상 중립
                'adx': 0   # ADX도 신호가 아니므로 항상 중립
            }

            # 각 지표의 LED 상태 업데이트
            for key, signal_value in signal_mapping.items():
                self.led_states[key] = signal_value

            # 지표 값 표시 레이블 업데이트 (analysis가 있을 때만)
            if analysis is not None:
                value_texts = {
                    'ma': f"차이: {((analysis.get('short_ma', 0) - analysis.get('long_ma', 1)) / analysis.get('long_ma', 1) * 100):.2f}%",
                    'rsi': f"RSI: {analysis.get('rsi', 0):.1f}",
                    'bb': f"위치: {(analysis.get('bb_position', 0.5) * 100):.0f}%",
                    'volume': f"배율: {analysis.get('volume_ratio', 1.0):.2f}x",
                    'macd': f"히스토그램: {analysis.get('macd_histogram', 0):.2f}",
                    'stochastic': f"K: {analysis.get('stoch_k', 50):.1f}, D: {analysis.get('stoch_d', 50):.1f}",
                    'atr': f"ATR: {analysis.get('atr_percent', 0):.2f}%",
                    'adx': f"ADX: {analysis.get('adx', 0):.1f}"
                }

                for key, value_text in value_texts.items():
                    if key in self.indicator_value_labels:
                        self.indicator_value_labels[key].config(text=value_text)

            # LED 색상 즉시 업데이트
            self.update_led_colors()

        except Exception as e:
            print(f"LED 업데이트 오류: {e}")

    def update_led_colors(self):
        """LED 색상 업데이트 (깜빡임 효과 포함)"""
        try:
            for key, led_info in self.indicator_leds.items():
                signal = self.led_states[key]

                # 깜빡임 상태에 따라 색상 결정
                if self.led_blink_state:
                    # 깜빡임 ON 상태 - 밝은 색상
                    if signal == 1:  # 매수
                        color = 'red'
                        outline = 'darkred'
                    elif signal == -1:  # 매도
                        color = 'blue'
                        outline = 'darkblue'
                    else:  # 중립
                        color = 'gray'
                        outline = 'darkgray'
                else:
                    # 깜빡임 OFF 상태 - 어두운 색상
                    if signal == 1:  # 매수
                        color = '#CC0000'  # 어두운 빨강
                        outline = 'darkred'
                    elif signal == -1:  # 매도
                        color = '#0000CC'  # 어두운 파랑
                        outline = 'darkblue'
                    else:  # 중립
                        color = '#666666'  # 어두운 회색
                        outline = 'darkgray'

                # LED 색상 적용
                led_info['canvas'].itemconfig(led_info['circle'], fill=color, outline=outline)

        except Exception as e:
            print(f"LED 색상 업데이트 오류: {e}")

    def blink_leds(self):
        """LED 깜빡임 애니메이션"""
        try:
            # 깜빡임 상태 토글
            self.led_blink_state = not self.led_blink_state

            # LED 색상 업데이트
            self.update_led_colors()

            # 500ms 후 다시 호출 (깜빡임 주기)
            self.root.after(500, self.blink_leds)

        except Exception as e:
            print(f"LED 깜빡임 오류: {e}")

    def setup_logging(self):
        """로깅 핸들러 설정"""
        class GUILogHandler(logging.Handler):
            def __init__(self, log_queue):
                super().__init__()
                self.log_queue = log_queue

            def emit(self, record):
                log_entry = self.format(record)
                self.log_queue.put((record.levelname, log_entry))

        # GUI 로그 핸들러 추가
        gui_handler = GUILogHandler(self.log_queue)
        gui_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

        # 기존 로거에 핸들러 추가
        logger = logging.getLogger('TradingBot')
        logger.addHandler(gui_handler)
        logger.setLevel(logging.INFO)

        # LED 깜빡임 시작
        self.blink_leds()

    def apply_settings(self):
        """설정 적용"""
        try:
            # 지표 선택 검증
            if not self.validate_indicator_selection():
                return

            # 현재 설정 가져오기
            current_config = self.config_manager.get_config()

            # 기본 거래 설정
            current_config['trading']['target_ticker'] = self.coin_var.get()
            current_config['trading']['trade_amount_krw'] = int(self.amount_var.get())

            # 리스크 및 상세 전략 설정
            current_config['trading']['stop_loss_percent'] = float(self.stop_loss_var.get())
            current_config['trading']['take_profit_percent'] = float(self.take_profit_var.get())
            current_config['strategy']['rsi_buy_threshold'] = int(self.rsi_buy_var.get())
            current_config['strategy']['rsi_sell_threshold'] = int(self.rsi_sell_var.get())
            current_config['strategy']['analysis_period'] = int(self.period_var.get())

            # 8개 기술 지표 활성화 설정
            enabled_indicators = {key: var.get() for key, var in self.indicator_vars.items()}
            current_config['strategy']['enabled_indicators'] = enabled_indicators

            # 간격 파싱
            interval_info = self.config_manager.parse_interval(self.interval_var.get())
            if interval_info['type'] == 'seconds':
                current_config['schedule']['check_interval_seconds'] = interval_info['value']
            elif interval_info['type'] == 'minutes':
                current_config['schedule']['check_interval_seconds'] = interval_info['value'] * 60
            elif interval_info['type'] == 'hours':
                current_config['schedule']['check_interval_seconds'] = interval_info['value'] * 3600

            # 실행 중인 봇이 있으면 재시작
            if self.is_running:
                self.stop_bot()
                self.root.after(1000, self.start_bot)

            self.add_log("SUCCESS", f"새로운 설정이 적용되었습니다: {self.coin_var.get()}, 체크 간격:{self.interval_var.get()}, 거래 금액:{self.amount_var.get()}원")

            # 차트 업데이트
            if hasattr(self, 'chart_widget'):
                self.chart_widget.update_config(current_config)
                self.add_log("INFO", "차트가 새로운 설정으로 업데이트되었습니다.")

        except Exception as e:
            self.add_log("ERROR", f"설정 적용 실패: {e}")
            messagebox.showerror("설정 오류", f"설정 적용 중 오류가 발생했습니다:\n{e}")

    def start_bot(self):
        """봇 시작"""
        try:
            if self.is_running:
                return

            self.is_running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_var.set("🟢 실행 중")

            # 봇 실행 스레드 시작
            self.bot_thread = threading.Thread(target=self.run_bot, daemon=True)
            self.bot_thread.start()

            # 차트 초기화 및 로드
            if hasattr(self, 'chart_widget'):
                self.add_log("INFO", "차트 데이터 로딩 중...")
                self.chart_widget.refresh_chart()

            self.add_log("SUCCESS", "거래 봇이 시작되었습니다.")

        except Exception as e:
            self.add_log("ERROR", f"봇 시작 실패: {e}")
            messagebox.showerror("시작 오류", f"봇 시작 중 오류가 발생했습니다:\n{e}")

    def stop_bot(self):
        """봇 정지"""
        try:
            self.is_running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_var.set("🔴 정지됨")

            # 가격 모니터링 중지
            if self.bot:
                self.bot.stop_price_monitoring()

            self.add_log("WARNING", "거래 봇이 정지되었습니다.")

        except Exception as e:
            self.add_log("ERROR", f"봇 정지 실패: {e}")

    def run_bot(self):
        """봇 실행 (별도 스레드)"""
        try:
            # GUI 전용 봇 초기화
            self.bot = GUITradingBot(status_callback=self.update_bot_status)

            if not self.bot.authenticate():
                self.add_log("ERROR", "봇 인증 실패")
                return

            self.add_log("INFO", "봇 인증 성공")

            # 가격 모니터링 시작
            self.bot.start_price_monitoring()

            # 메인 루프
            while self.is_running:
                try:
                    # 거래 사이클 실행
                    self.bot.run_trading_cycle()

                    # 간격에 따라 대기
                    current_config = self.config_manager.get_config()
                    sleep_seconds = current_config['schedule'].get('check_interval_seconds', 1800)  # 기본 30분

                    # 중단 요청 확인하면서 대기
                    for _ in range(sleep_seconds):
                        if not self.is_running:
                            break
                        time.sleep(1)

                except Exception as e:
                    self.add_log("ERROR", f"거래 사이클 오류: {e}")
                    time.sleep(60)  # 오류 시 1분 대기

        except Exception as e:
            self.add_log("ERROR", f"봇 실행 오류: {e}")
        finally:
            self.is_running = False

    def add_log(self, level, message):
        """로그 추가"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_queue.put((level, log_entry))

    def clear_logs(self):
        """로그 지우기"""
        self.log_text.delete(1.0, tk.END)

    def update_gui(self):
        """GUI 업데이트 (주기적 호출)"""
        try:
            # 로그 큐에서 메시지 처리
            while not self.log_queue.empty():
                try:
                    level, message = self.log_queue.get_nowait()
                    self.log_text.insert(tk.END, message + "\n", level)
                    self.log_text.see(tk.END)
                except queue.Empty:
                    break

            # 거래 상태 업데이트
            self.update_trading_status()

            # 수익 현황 업데이트
            self.update_profit_status()

            # 거래 내역 자동 새로고침 (봇이 실행 중이고 60초마다)
            if self.bot and self.is_running and hasattr(self, 'history_refresh_counter'):
                self.history_refresh_counter = getattr(self, 'history_refresh_counter', 0) + 1
                if self.history_refresh_counter >= 60:  # 60초마다 (60 * 1초)
                    self.history_refresh_counter = 0
                    try:
                        if hasattr(self, 'history_tree'):
                            self.refresh_trading_history()
                    except:
                        pass  # 자동 업데이트 오류는 무시
            elif not hasattr(self, 'auto_refresh_counter'):
                self.auto_refresh_counter = 0
                self.history_refresh_counter = 0

        except Exception as e:
            print(f"GUI 업데이트 오류: {e}")

        # 다음 업데이트 예약 (1초 후)
        self.root.after(1000, self.update_gui)

    def update_trading_status(self):
        """거래 상태 업데이트"""
        try:
            current_config = self.config_manager.get_config()
            current_coin = current_config['trading']['target_ticker']

            # 현재 코인 업데이트
            self.current_coin_var.set(current_coin)

            # 현재 가격 조회 (실제 API 호출은 봇이 실행 중일 때만)
            if self.bot and self.is_running:
                # 실제 가격 정보를 가져오는 로직 추가 가능
                pass
            else:
                self.current_price_var.set("대기 중")
                self.avg_buy_price_var.set("0 KRW")
                self.holdings_var.set("0")
                self.pending_orders_var.set("없음")

        except Exception as e:
            print(f"거래 상태 업데이트 오류: {e}")

    def update_profit_status(self):
        """수익 현황 업데이트"""
        try:
            # 거래 내역에서 수익 계산
            current_coin = self.config_manager.get_config()['trading']['target_ticker']
            daily_summary = self.transaction_history.get_summary(current_coin, 1)
            total_summary = self.transaction_history.get_summary(current_coin)

            # 일일 거래 횟수
            self.daily_trades_var.set(f"{daily_summary['total_transactions']}회")

            # 성공률 계산
            if daily_summary['total_transactions'] > 0:
                success_rate = (daily_summary['successful_transactions'] / daily_summary['total_transactions']) * 100
                self.success_rate_var.set(f"{success_rate:.1f}%")
            else:
                self.success_rate_var.set("0%")

            # 간단한 수익 차트 업데이트
            self.update_profit_chart()

        except Exception as e:
            print(f"수익 현황 업데이트 오류: {e}")

    def update_profit_chart(self):
        """수익 차트 업데이트"""
        try:
            current_coin = self.config_manager.get_config()['trading']['target_ticker']

            # 최근 거래 내역 표시
            recent_transactions = self.transaction_history.transactions[-10:]  # 최근 10건

            chart_text = f"=== {current_coin} 최근 거래 ===\n\n"

            for transaction in reversed(recent_transactions):  # 최신 순으로
                if transaction['ticker'] == current_coin and transaction['success']:
                    timestamp = datetime.fromisoformat(transaction['timestamp']).strftime("%m/%d %H:%M")
                    action = "🔵 매수" if transaction['action'] == 'BUY' else "🔴 매도"
                    amount = transaction['amount']
                    price = transaction['price']
                    chart_text += f"{timestamp} {action} {amount:.6f} @ {price:,.0f}₩\n"

            if not recent_transactions:
                chart_text += "거래 내역이 없습니다."

            # 차트 업데이트
            self.profit_chart.delete(1.0, tk.END)
            self.profit_chart.insert(tk.END, chart_text)

        except Exception as e:
            print(f"수익 차트 업데이트 오류: {e}")

    def update_bot_status(self, status: Dict[str, Any]):
        """봇 상태 업데이트 (콜백 함수) - 엘리트 기능 포함"""
        try:
            # 현재 상태 업데이트
            self.bot_status.update(status)

            # GUI 변수들 업데이트
            self.current_coin_var.set(status.get('coin', 'BTC'))

            current_price = status.get('current_price', 0)
            if current_price > 0:
                self.current_price_var.set(f"{current_price:,.0f} KRW")
            else:
                self.current_price_var.set("조회 중...")

            avg_buy_price = status.get('avg_buy_price', 0)
            if avg_buy_price > 0:
                self.avg_buy_price_var.set(f"{avg_buy_price:,.0f} KRW")
            else:
                self.avg_buy_price_var.set("0 KRW")

            holdings = status.get('holdings', 0)
            self.holdings_var.set(f"{holdings:.6f}" if holdings > 0 else "0")

            pending_orders = status.get('pending_orders', [])
            if pending_orders:
                self.pending_orders_var.set(f"{len(pending_orders)}개")
            else:
                self.pending_orders_var.set("없음")

            # 엘리트 신호 업데이트 (가중치 기반)
            signals = status.get('signals', {})
            analysis = status.get('analysis', {})

            if signals:
                # LED 신호 업데이트 (8개 지표)
                self.update_indicator_leds(signals, analysis)

                # 시장 국면 업데이트
                regime = signals.get('regime', 'unknown')
                volatility_level = signals.get('volatility_level', 'normal')
                trend_strength = signals.get('trend_strength', 0.0)

                regime_text_map = {
                    'trending': '🔵 추세장',
                    'ranging': '🟡 횡보장',
                    'transitional': '🟠 전환기',
                    'unknown': '⚪ 분석 중'
                }
                self.regime_var.set(regime_text_map.get(regime, regime))

                volatility_color_map = {
                    'low': 'green',
                    'normal': 'blue',
                    'high': 'red'
                }
                volatility_text = f"{volatility_level.upper()} ({analysis.get('current_atr_pct', 0):.2f}%)"
                self.volatility_var.set(volatility_text)

                trend_strength_text = f"{trend_strength:.2f} (ADX: {analysis.get('adx', 0):.1f})"
                self.trend_strength_var.set(trend_strength_text)

                recommendation = analysis.get('regime', {}).get('recommendation', 'WAIT')
                recommendation_text_map = {
                    'TREND_FOLLOW': '✅ 추세 추종',
                    'MEAN_REVERSION': '✅ 평균회귀',
                    'REDUCE_SIZE': '⚠️ 포지션 축소',
                    'WAIT': '⏸️ 관망'
                }
                self.recommendation_var.set(recommendation_text_map.get(recommendation, recommendation))

                # 종합 신호 업데이트
                overall_signal = signals.get('overall_signal', 0)
                final_action = signals.get('final_action', 'HOLD')

                action_color_map = {
                    'BUY': 'red',
                    'SELL': 'blue',
                    'HOLD': 'gray'
                }
                self.overall_signal_var.set(final_action)
                self.overall_signal_label.config(foreground=action_color_map.get(final_action, 'gray'))

                # 신호 강도 및 신뢰도 (Progress bar)
                signal_strength_percent = (overall_signal + 1.0) / 2.0 * 100  # -1~+1을 0~100으로 변환
                confidence = signals.get('confidence', 0) * 100

                self.signal_strength_bar['value'] = signal_strength_percent
                self.signal_strength_var.set(f"{overall_signal:+.2f}")

                self.confidence_bar['value'] = confidence
                self.confidence_var.set(f"{signals.get('confidence', 0):.2f}")

                # ATR 기반 리스크 관리 업데이트
                if current_price > 0 and analysis.get('atr', 0) > 0:
                    from strategy import calculate_exit_levels

                    exit_levels = calculate_exit_levels(
                        entry_price=current_price,
                        atr=analysis.get('atr', 0),
                        direction='LONG',
                        volatility_level=volatility_level
                    )

                    self.entry_price_var.set(f"{current_price:,.0f}원")
                    self.stop_loss_price_var.set(
                        f"{exit_levels['stop_loss']:,.0f}원 "
                        f"({((exit_levels['stop_loss'] - current_price) / current_price * 100):+.2f}%)"
                    )
                    self.tp1_price_var.set(
                        f"{exit_levels['take_profit_1']:,.0f}원 "
                        f"({((exit_levels['take_profit_1'] - current_price) / current_price * 100):+.2f}%)"
                    )
                    self.tp2_price_var.set(
                        f"{exit_levels['take_profit_2']:,.0f}원 "
                        f"({((exit_levels['take_profit_2'] - current_price) / current_price * 100):+.2f}%)"
                    )
                    self.rr_ratio_var.set(
                        f"TP1: 1:{exit_levels['rr_ratio_1']:.2f}, TP2: 1:{exit_levels['rr_ratio_2']:.2f}"
                    )

            # 마지막 액션 로그 추가
            last_action = status.get('last_action', '')
            if last_action and last_action != 'HOLD':
                if last_action == 'BUY':
                    self.add_log("INFO", f"🔵 매수 신호 감지 - {status.get('coin', 'BTC')}")
                elif last_action == 'SELL':
                    self.add_log("INFO", f"🔴 매도 신호 감지 - {status.get('coin', 'BTC')}")

        except Exception as e:
            print(f"봇 상태 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()

    def create_trading_history_panel(self, parent):
        """거래 내역 탭 패널"""
        # 메인 프레임 구성
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # 상단 제어 패널
        control_frame = ttk.LabelFrame(parent, text="📊 거래 내역 관리", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)
        control_frame.columnconfigure(0, weight=1)

        # 제어 버튼들
        button_frame = ttk.Frame(control_frame)
        button_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))

        refresh_btn = ttk.Button(button_frame, text="🔄 새로고침", command=self.refresh_trading_history)
        refresh_btn.grid(row=0, column=0, padx=(0, 10))

        export_btn = ttk.Button(button_frame, text="📤 내보내기", command=self.export_trading_history)
        export_btn.grid(row=0, column=1, padx=(0, 10))

        # 파일 경로 표시
        self.history_file_var = tk.StringVar(value="마크다운 파일을 로드 중...")
        file_label = ttk.Label(control_frame, textvariable=self.history_file_var, style='Status.TLabel')
        file_label.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(10, 0))

        # 거래 내역 테이블
        table_frame = ttk.LabelFrame(parent, text="📈 거래 내역", padding="10")
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        # Treeview 생성 (거래 내역 테이블)
        columns = ('날짜', '시간', '코인', '거래유형', '수량', '단가', '총금액', '수수료', '수익금액', '수익률', '메모')
        self.history_tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=15)

        # 컬럼 헤더 설정
        self.history_tree.heading('날짜', text='날짜')
        self.history_tree.heading('시간', text='시간')
        self.history_tree.heading('코인', text='코인')
        self.history_tree.heading('거래유형', text='거래유형')
        self.history_tree.heading('수량', text='수량')
        self.history_tree.heading('단가', text='단가')
        self.history_tree.heading('총금액', text='총금액')
        self.history_tree.heading('수수료', text='수수료')
        self.history_tree.heading('수익금액', text='수익금액')
        self.history_tree.heading('수익률', text='수익률')
        self.history_tree.heading('메모', text='메모')

        # 컬럼 너비 설정
        self.history_tree.column('날짜', width=100)
        self.history_tree.column('시간', width=80)
        self.history_tree.column('코인', width=60)
        self.history_tree.column('거래유형', width=80)
        self.history_tree.column('수량', width=100)
        self.history_tree.column('단가', width=120)
        self.history_tree.column('총금액', width=100)
        self.history_tree.column('수수료', width=80)
        self.history_tree.column('수익금액', width=100)
        self.history_tree.column('수익률', width=80)
        self.history_tree.column('메모', width=100)

        # 스크롤바 추가
        history_scrollbar_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        history_scrollbar_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=history_scrollbar_y.set, xscrollcommand=history_scrollbar_x.set)

        # 테이블과 스크롤바 배치
        self.history_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        history_scrollbar_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        history_scrollbar_x.grid(row=1, column=0, sticky=(tk.W, tk.E))

        # 초기 데이터 로드
        self.refresh_trading_history()

    def parse_markdown_trading_history(self, file_path):
        """마크다운 파일에서 거래 내역 파싱"""
        try:
            import os
            if not os.path.exists(file_path):
                return []

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            transactions = []
            lines = content.split('\n')

            # 테이블 행들 찾기 (|로 시작하고 헤더나 구분선이 아닌 것)
            for line in lines:
                line = line.strip()
                if (line.startswith('|') and
                    not line.startswith('|---') and
                    '날짜' not in line and
                    '|' in line[1:]):  # 실제 데이터 행

                    # 파이프(|)로 분할하여 컬럼 데이터 추출
                    columns = [col.strip() for col in line.split('|')[1:-1]]  # 첫 번째와 마지막 빈 요소 제거

                    if len(columns) >= 11:  # 최소 11개 컬럼 필요
                        transactions.append(columns)

            return transactions

        except Exception as e:
            self.add_log("ERROR", f"마크다운 파싱 오류: {str(e)}")
            return []

    def refresh_trading_history(self):
        """거래 내역 새로고침"""
        try:
            # 기존 데이터 삭제
            for item in self.history_tree.get_children():
                self.history_tree.delete(item)

            # 마크다운 파일 경로 가져오기
            if self.bot:
                markdown_path = self.bot.get_markdown_log_path()
            else:
                # 봇이 없을 때는 기본 경로 사용
                markdown_path = "logs/trading_history.md"

            self.history_file_var.set(f"📄 파일: {markdown_path}")

            # 마크다운 파일에서 거래 내역 로드
            transactions = self.parse_markdown_trading_history(markdown_path)

            if not transactions:
                # 데이터가 없을 때 안내 메시지
                self.history_tree.insert('', 'end', values=(
                    '거래 내역이 없습니다', '', '', '', '', '', '', '', '', '', ''
                ))
                return

            # 데이터를 역순으로 정렬 (최신 거래가 위에 오도록)
            transactions.reverse()

            # 테이블에 데이터 추가
            for transaction in transactions:
                self.history_tree.insert('', 'end', values=transaction)

            self.add_log("SUCCESS", f"거래 내역 {len(transactions)}건을 로드했습니다.")

        except Exception as e:
            self.add_log("ERROR", f"거래 내역 새로고침 오류: {str(e)}")

    def export_trading_history(self):
        """거래 내역 내보내기"""
        try:
            from tkinter import filedialog
            import csv

            # 파일 저장 대화상자
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[
                    ("CSV files", "*.csv"),
                    ("Markdown files", "*.md"),
                    ("All files", "*.*")
                ],
                title="거래 내역 저장"
            )

            if not filename:
                return

            # 현재 테이블의 모든 데이터 가져오기
            data = []
            for item in self.history_tree.get_children():
                values = self.history_tree.item(item)['values']
                data.append(values)

            if filename.endswith('.csv'):
                # CSV 형태로 저장
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    # 헤더 작성
                    headers = ['날짜', '시간', '코인', '거래유형', '수량', '단가', '총금액', '수수료', '수익금액', '수익률', '메모']
                    writer.writerow(headers)
                    # 데이터 작성
                    writer.writerows(data)
            else:
                # 마크다운 형태로 저장
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("# 거래 내역 내보내기\n\n")
                    f.write(f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    f.write("| 날짜 | 시간 | 코인 | 거래유형 | 수량 | 단가 | 총금액 | 수수료 | 수익금액 | 수익률 | 메모 |\n")
                    f.write("|------|------|------|----------|------|------|--------|--------|----------|--------|------|\n")
                    for row in data:
                        f.write("| " + " | ".join(str(cell) for cell in row) + " |\n")

            self.add_log("SUCCESS", f"거래 내역이 {filename}에 저장되었습니다.")

        except Exception as e:
            self.add_log("ERROR", f"거래 내역 내보내기 오류: {str(e)}")

def main():
    """GUI 애플리케이션 실행"""
    root = tk.Tk()
    app = TradingBotGUI(root)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("GUI 애플리케이션이 종료되었습니다.")

if __name__ == "__main__":
    main()