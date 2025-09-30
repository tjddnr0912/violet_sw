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
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import logging

from gui_trading_bot import GUITradingBot
from logger import TradingLogger, TransactionHistory
from config_manager import ConfigManager
import config
from bithumb_api import get_ticker

class TradingBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("🤖 빗썸 자동매매 봇")
        self.root.geometry("1200x800")
        self.root.minsize(1000, 600)

        # 상태 변수
        self.bot = None
        self.bot_thread = None
        self.is_running = False
        self.log_queue = queue.Queue()
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
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))

        # 메인 탭 (기존 거래 화면)
        main_tab = ttk.Frame(notebook)
        notebook.add(main_tab, text='거래 현황')

        # 계정 정보 탭 (제거됨 - 잔고 조회 기능 비활성화)
        account_tab = ttk.Frame(notebook)
        notebook.add(account_tab, text='계정 정보')

        # 거래 내역 탭
        history_tab = ttk.Frame(notebook)
        notebook.add(history_tab, text='거래 내역')

        # 메인 탭 내용 (좌우 분할)
        main_paned = ttk.PanedWindow(main_tab, orient=tk.HORIZONTAL)
        main_paned.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        main_tab.columnconfigure(0, weight=1)
        main_tab.rowconfigure(0, weight=1)

        # 왼쪽 패널 (상태 및 설정)
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)

        # 오른쪽 패널 (로그)
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=2)

        # 왼쪽 패널 구성
        self.create_status_panel(left_frame)
        self.create_settings_panel(left_frame)
        self.create_profit_panel(left_frame)

        # 오른쪽 패널 구성 (로그)
        self.create_log_panel(right_frame)

        # 계정 정보 탭 구성 (제거됨 - 잔고 조회 기능 비활성화)
        self.create_account_info_panel(account_tab)

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
        settings_frame = ttk.LabelFrame(parent, text="⚙️ 실시간 설정", padding="10")
        settings_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), pady=(0, 10))

        # 기술 지표 선택 패널 (새로 추가)
        indicator_frame = ttk.LabelFrame(settings_frame, text="📊 기술 지표 선택 (최소 2개)", padding="10")
        indicator_frame.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 10))

        # 지표 체크박스 및 LED 변수 초기화
        self.indicator_vars = {
            'ma': tk.BooleanVar(value=True),
            'rsi': tk.BooleanVar(value=True),
            'bb': tk.BooleanVar(value=True),
            'volume': tk.BooleanVar(value=True)
        }

        self.indicator_leds = {}
        self.led_states = {
            'ma': 0,    # -1: 매도(파랑), 0: 중립(회색), 1: 매수(빨강)
            'rsi': 0,
            'bb': 0,
            'volume': 0
        }
        self.led_blink_state = False

        # 각 지표별 행 생성
        indicators = [
            ('ma', '이동평균선 (MA)'),
            ('rsi', '상대강도지수 (RSI)'),
            ('bb', '볼린저 밴드 (BB)'),
            ('volume', '거래량 (Volume)')
        ]

        for idx, (key, label) in enumerate(indicators):
            row_frame = ttk.Frame(indicator_frame)
            row_frame.grid(row=idx, column=0, sticky=tk.W, pady=2)

            # LED 캔버스 (깜빡이는 원형)
            led_canvas = tk.Canvas(row_frame, width=20, height=20, bg='white', highlightthickness=0)
            led_canvas.pack(side=tk.LEFT, padx=(0, 5))
            led_circle = led_canvas.create_oval(5, 5, 15, 15, fill='gray', outline='darkgray')
            self.indicator_leds[key] = {'canvas': led_canvas, 'circle': led_circle}

            # 체크박스
            check = ttk.Checkbutton(
                row_frame,
                text=label,
                variable=self.indicator_vars[key],
                command=self.validate_indicator_selection
            )
            check.pack(side=tk.LEFT)

        # 거래 코인 선택
        ttk.Label(settings_frame, text="거래 코인:", style='Title.TLabel').grid(row=1, column=0, sticky=tk.W, pady=(10, 0))
        self.coin_var = tk.StringVar()
        coin_combo = ttk.Combobox(settings_frame, textvariable=self.coin_var, width=10)
        coin_combo['values'] = ('BTC', 'ETH', 'XRP', 'ADA', 'DOT', 'LINK', 'LTC', 'BCH', 'EOS', 'TRX')
        coin_combo.grid(row=1, column=1, sticky=tk.W, padx=(10, 0), pady=(10, 0))
        coin_combo.set(self.config_manager.get_config()['trading']['target_ticker'])

        # 캔들 간격 선택 (새로 추가)
        ttk.Label(settings_frame, text="캔들 간격:", style='Title.TLabel').grid(row=2, column=0, sticky=tk.W, pady=(5, 0))
        self.candle_interval_var = tk.StringVar()
        candle_interval_combo = ttk.Combobox(settings_frame, textvariable=self.candle_interval_var, width=10, state='readonly')
        candle_interval_combo['values'] = ('1h', '6h', '12h', '24h')
        candle_interval_combo.grid(row=2, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        candle_interval_combo.set(self.config_manager.get_config()['strategy'].get('candlestick_interval', '24h'))
        candle_interval_combo.bind('<<ComboboxSelected>>', self.on_candle_interval_changed)

        # 체크 간격 선택
        ttk.Label(settings_frame, text="체크 간격:", style='Title.TLabel').grid(row=3, column=0, sticky=tk.W, pady=(5, 0))
        self.interval_var = tk.StringVar()
        interval_combo = ttk.Combobox(settings_frame, textvariable=self.interval_var, width=10)
        interval_combo['values'] = ('10s', '30s', '1m', '5m', '10m', '30m', '1h', '2h', '4h')
        interval_combo.grid(row=3, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        interval_combo.set('30m')  # 기본값

        # 거래 금액
        ttk.Label(settings_frame, text="거래 금액:", style='Title.TLabel').grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        self.amount_var = tk.StringVar()
        amount_entry = ttk.Entry(settings_frame, textvariable=self.amount_var, width=12)
        amount_entry.grid(row=4, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        amount_entry.insert(0, str(self.config_manager.get_config()['trading']['trade_amount_krw']))

        # 손절 비율 (%)
        ttk.Label(settings_frame, text="손절 비율:", style='Title.TLabel').grid(row=5, column=0, sticky=tk.W, pady=(5, 0))
        self.stop_loss_var = tk.StringVar()
        stop_loss_entry = ttk.Entry(settings_frame, textvariable=self.stop_loss_var, width=8)
        stop_loss_entry.grid(row=5, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        stop_loss_entry.insert(0, "5.0")  # 기본 5% 손절
        ttk.Label(settings_frame, text="%", style='Status.TLabel').grid(row=5, column=2, sticky=tk.W, padx=(5, 0), pady=(5, 0))

        # 익절 비율 (%)
        ttk.Label(settings_frame, text="익절 비율:", style='Title.TLabel').grid(row=6, column=0, sticky=tk.W, pady=(5, 0))
        self.take_profit_var = tk.StringVar()
        take_profit_entry = ttk.Entry(settings_frame, textvariable=self.take_profit_var, width=8)
        take_profit_entry.grid(row=6, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        take_profit_entry.insert(0, "3.0")  # 기본 3% 익절
        ttk.Label(settings_frame, text="%", style='Status.TLabel').grid(row=5, column=2, sticky=tk.W, padx=(5, 0), pady=(5, 0))

        # RSI 매수 임계값
        ttk.Label(settings_frame, text="RSI 매수:", style='Title.TLabel').grid(row=6, column=0, sticky=tk.W, pady=(5, 0))
        self.rsi_buy_var = tk.StringVar()
        rsi_buy_entry = ttk.Entry(settings_frame, textvariable=self.rsi_buy_var, width=8)
        rsi_buy_entry.grid(row=6, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        rsi_buy_entry.insert(0, "30")  # 기본 RSI 30 이하 매수
        ttk.Label(settings_frame, text="이하", style='Status.TLabel').grid(row=6, column=2, sticky=tk.W, padx=(5, 0), pady=(5, 0))

        # RSI 매도 임계값
        ttk.Label(settings_frame, text="RSI 매도:", style='Title.TLabel').grid(row=7, column=0, sticky=tk.W, pady=(5, 0))
        self.rsi_sell_var = tk.StringVar()
        rsi_sell_entry = ttk.Entry(settings_frame, textvariable=self.rsi_sell_var, width=8)
        rsi_sell_entry.grid(row=7, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        rsi_sell_entry.insert(0, "70")  # 기본 RSI 70 이상 매도
        ttk.Label(settings_frame, text="이상", style='Status.TLabel').grid(row=7, column=2, sticky=tk.W, padx=(5, 0), pady=(5, 0))

        # 단위 기간 (캔들 수)
        ttk.Label(settings_frame, text="분석 기간:", style='Title.TLabel').grid(row=8, column=0, sticky=tk.W, pady=(5, 0))
        self.period_var = tk.StringVar()
        period_combo = ttk.Combobox(settings_frame, textvariable=self.period_var, width=8)
        period_combo['values'] = ('10', '20', '50', '100', '200')
        period_combo.grid(row=8, column=1, sticky=tk.W, padx=(10, 0), pady=(5, 0))
        period_combo.set('20')  # 기본 20캔들
        ttk.Label(settings_frame, text="캔들", style='Status.TLabel').grid(row=8, column=2, sticky=tk.W, padx=(5, 0), pady=(5, 0))

        # 설정 적용 버튼
        apply_button = ttk.Button(settings_frame, text="📝 설정 적용", command=self.apply_settings)
        apply_button.grid(row=9, column=0, columnspan=3, pady=(15, 0))

        # 변수 저장
        self.coin_combo = coin_combo
        self.interval_combo = interval_combo
        self.amount_entry = amount_entry
        self.stop_loss_entry = stop_loss_entry
        self.take_profit_entry = take_profit_entry
        self.rsi_buy_entry = rsi_buy_entry
        self.rsi_sell_entry = rsi_sell_entry
        self.period_combo = period_combo

    def create_profit_panel(self, parent):
        """수익 현황 패널"""
        profit_frame = ttk.LabelFrame(parent, text="💰 수익 현황", padding="10")
        profit_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        parent.rowconfigure(2, weight=1)

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

    def create_account_info_panel(self, parent):
        """계정 정보 탭 생성"""
        info_frame = ttk.LabelFrame(parent, text="📋 계정 정보", padding="20")
        info_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 잔고 조회 기능 활성화 알림
        message = ttk.Label(info_frame,
                           text="✅ 잔고 조회 기능이 활성화되었습니다.\n\n" +
                                "실제 거래 모드(dry_run=False)에서는 빗썸 API를 통해 실제 계정 잔고를 조회합니다.\n" +
                                "모의 거래 모드(dry_run=True)에서는 가상 잔고를 사용합니다.\n\n" +
                                "거래 상태 탭에서 현재 잔고와 보유 수량을 확인할 수 있습니다.",
                           font=('Arial', 11),
                           foreground='green',
                           justify='center')
        message.pack(expand=True)

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

    def update_indicator_leds(self, signals: Dict[str, int]):
        """지표별 LED 상태 업데이트"""
        try:
            # 신호 매핑: ma_signal, rsi_signal, bb_signal, volume_signal
            signal_mapping = {
                'ma': signals.get('ma_signal', 0),
                'rsi': signals.get('rsi_signal', 0),
                'bb': signals.get('bb_signal', 0),
                'volume': signals.get('volume_signal', 0)
            }

            # 각 지표의 LED 상태 업데이트
            for key, signal_value in signal_mapping.items():
                self.led_states[key] = signal_value

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

            # 수익률 관련 설정
            current_config['trading']['stop_loss_percent'] = float(self.stop_loss_var.get())
            current_config['trading']['take_profit_percent'] = float(self.take_profit_var.get())

            # RSI 설정
            current_config['strategy']['rsi_buy_threshold'] = int(self.rsi_buy_var.get())
            current_config['strategy']['rsi_sell_threshold'] = int(self.rsi_sell_var.get())
            current_config['strategy']['analysis_period'] = int(self.period_var.get())

            # 기술 지표 활성화 설정 추가
            current_config['strategy']['enabled_indicators'] = {
                'ma': self.indicator_vars['ma'].get(),
                'rsi': self.indicator_vars['rsi'].get(),
                'bb': self.indicator_vars['bb'].get(),
                'volume': self.indicator_vars['volume'].get()
            }

            # 간격 파싱
            interval_info = self.config_manager.parse_interval(self.interval_var.get())
            if interval_info['type'] == 'seconds':
                current_config['schedule']['check_interval_seconds'] = interval_info['value']
                current_config['schedule']['check_interval_minutes'] = max(1, interval_info['value'] // 60)
            elif interval_info['type'] == 'minutes':
                current_config['schedule']['check_interval_minutes'] = interval_info['value']
                current_config['schedule']['check_interval_seconds'] = interval_info['value'] * 60
            elif interval_info['type'] == 'hours':
                current_config['schedule']['check_interval_minutes'] = interval_info['value'] * 60
                current_config['schedule']['check_interval_seconds'] = interval_info['value'] * 3600

            # 실행 중인 봇이 있으면 재시작
            if self.is_running:
                self.stop_bot()
                self.root.after(1000, self.start_bot)  # 1초 후 재시작

            self.add_log("SUCCESS", f"설정 적용됨: {self.coin_var.get()}, {self.interval_var.get()}, {self.amount_var.get()}원, 손절:{self.stop_loss_var.get()}%, 익절:{self.take_profit_var.get()}%, RSI:{self.rsi_buy_var.get()}-{self.rsi_sell_var.get()}")

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

            # 계정 정보 자동 업데이트 제거됨 (잔고 조회 기능 비활성화)
            # if self.bot and self.is_running and hasattr(self, 'auto_refresh_counter'):
            #     self.auto_refresh_counter = getattr(self, 'auto_refresh_counter', 0) + 1
            #     if self.auto_refresh_counter >= 30:  # 30초마다 (30 * 1초)
            #         self.auto_refresh_counter = 0
            #         try:
            #             detailed_info = self.bot.get_detailed_balance_info()
            #             if not detailed_info.get('error') and hasattr(self, 'krw_total_var'):
            #                 self.update_account_display(detailed_info)
            #         except:
            #             pass  # 자동 업데이트 오류는 무시

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
        """봇 상태 업데이트 (콜백 함수)"""
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

            # LED 신호 업데이트 (기술 지표 상태)
            signals = status.get('signals', {})
            if signals:
                self.update_indicator_leds(signals)

            # 마지막 액션 로그 추가
            last_action = status.get('last_action', '')
            if last_action and last_action != 'HOLD':
                if last_action == 'BUY':
                    self.add_log("INFO", f"🔵 매수 신호 감지 - {status.get('coin', 'BTC')}")
                elif last_action == 'SELL':
                    self.add_log("INFO", f"🔴 매도 신호 감지 - {status.get('coin', 'BTC')}")

        except Exception as e:
            print(f"봇 상태 업데이트 오류: {e}")

    # 계정 정보 새로고침 제거됨 (잔고 조회 기능 비활성화)
    def refresh_account_info(self):
        """계정 정보 새로고침 - 비활성화됨"""
        self.add_log("WARNING", "계정 정보 조회 기능이 비활성화되어 있습니다.")

    # 계정 정보 화면 업데이트 제거됨 (잔고 조회 기능 비활성화)
    def update_account_display(self, detailed_info):
        """계정 정보 화면 업데이트 - 비활성화됨"""
        pass

    # 포트폴리오 데이터 내보내기 제거됨 (잔고 조회 기능 비활성화)
    def export_portfolio_data(self):
        """포트폴리오 데이터 내보내기 - 비활성화됨"""
        self.add_log("WARNING", "포트폴리오 내보내기 기능이 비활성화되어 있습니다.")

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
                # 거래 유형에 따라 행 색상 구분을 위한 태그 설정
                if '매수' in transaction[3]:
                    tags = ('buy',)
                elif '매도' in transaction[3]:
                    tags = ('sell',)
                else:
                    tags = ()

                self.history_tree.insert('', 'end', values=transaction, tags=tags)

            # 태그별 색상 설정
            self.history_tree.tag_configure('buy', background='#e8f5e8')  # 연한 녹색
            self.history_tree.tag_configure('sell', background='#ffe8e8')  # 연한 빨간색

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