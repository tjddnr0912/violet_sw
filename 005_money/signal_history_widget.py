#!/usr/bin/env python3
"""
신호 히스토리 위젯
로그에서 거래 신호 및 액션 정보를 추출하여 테이블로 표시 (엘리트 전략 지원)
"""

import tkinter as tk
from tkinter import ttk
import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any
import re

class SignalHistoryWidget:
    """신호 히스토리 표시 위젯"""

    def __init__(self, parent_frame):
        self.parent = parent_frame
        self.log_dir = "logs"
        self.setup_ui()

    def setup_ui(self):
        """UI 구성"""
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(1, weight=1)

        control_frame = ttk.LabelFrame(self.parent, text="📊 신호 히스토리 조회", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)
        control_frame.columnconfigure(1, weight=1)

        ttk.Label(control_frame, text="조회 날짜:").grid(row=0, column=0, padx=(0, 10))
        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y%m%d"))
        date_combo = ttk.Combobox(control_frame, textvariable=self.date_var, width=15, state='readonly')
        date_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 10))
        date_combo['values'] = self.get_available_dates()
        self.date_combo = date_combo

        refresh_btn = ttk.Button(control_frame, text="🔄 새로고침", command=self.refresh_history)
        refresh_btn.grid(row=0, column=2, padx=(0, 10))

        ttk.Label(control_frame, text="필터:").grid(row=0, column=3, padx=(10, 10))
        self.filter_var = tk.StringVar(value="전체")
        filter_combo = ttk.Combobox(control_frame, textvariable=self.filter_var, width=10, state='readonly')
        filter_combo.grid(row=0, column=4, sticky=tk.W)
        filter_combo['values'] = ("전체", "HOLD", "BUY", "SELL")
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_history())

        stats_frame = ttk.Frame(control_frame)
        stats_frame.grid(row=1, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=(10, 0))
        self.stats_label = ttk.Label(stats_frame, text="통계: -", foreground='blue')
        self.stats_label.pack(side=tk.LEFT)

        table_frame = ttk.LabelFrame(self.parent, text="📈 신호 및 액션 히스토리 (최근 24시간)", padding="10")
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ('timestamp', 'action', 'overall', 'confidence', 'ma', 'rsi', 'macd', 'stoch', 'bb', 'atr', 'adx', 'reason')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=20)

        col_configs = {
            'timestamp': {'text': '시간', 'width': 140},
            'action': {'text': '액션', 'width': 70},
            'overall': {'text': '종합신호', 'width': 80},
            'confidence': {'text': '신뢰도', 'width': 70},
            'ma': {'text': 'MA', 'width': 70},
            'rsi': {'text': 'RSI', 'width': 70},
            'macd': {'text': 'MACD', 'width': 70},
            'stoch': {'text': 'Stoch', 'width': 70},
            'bb': {'text': 'BB', 'width': 70},
            'atr': {'text': 'ATR %', 'width': 70},
            'adx': {'text': 'ADX', 'width': 60},
            'reason': {'text': '사유', 'width': 250}
        }

        for col, conf in col_configs.items():
            self.tree.heading(col, text=conf['text'])
            self.tree.column(col, width=conf['width'], anchor=tk.CENTER)
        self.tree.column('reason', anchor=tk.W)

        scrollbar_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        scrollbar_x.grid(row=1, column=0, sticky=(tk.W, tk.E))

        self.tree.tag_configure('BUY', background='#e8f5e8')
        self.tree.tag_configure('SELL', background='#ffe8e8')
        self.tree.tag_configure('BUY_SIGNAL', foreground='red')
        self.tree.tag_configure('SELL_SIGNAL', foreground='blue')

        self.refresh_history()

    def get_available_dates(self) -> List[str]:
        dates = []
        if os.path.exists(self.log_dir):
            for filename in sorted(os.listdir(self.log_dir), reverse=True):
                if filename.startswith('trading_') and filename.endswith('.log'):
                    date_str = filename.replace('trading_', '').replace('.log', '')
                    dates.append(date_str)
        return dates

    def parse_log_file(self, date: str) -> List[Dict[str, Any]]:
        log_file = os.path.join(self.log_dir, f"trading_{date}.log")
        if not os.path.exists(log_file):
            return []

        signals = []
        now = datetime.now()
        cutoff_time = now - timedelta(hours=24)

        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                if '[ANALYSIS]' not in line:
                    continue

                try:
                    json_start = line.find('{')
                    if json_start == -1: continue
                    data = json.loads(line[json_start:])

                    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if not timestamp_match: continue
                    timestamp = timestamp_match.group(1)

                    log_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                    if log_time < cutoff_time: continue

                    analysis = data.get('analysis', {})
                    signals_data = data.get('signals', {})

                    signal_entry = {
                        'timestamp': timestamp,
                        'action': data.get('action', 'HOLD'),
                        'reason': data.get('reason', '-'),
                        'overall': signals_data.get('overall_signal', 0),
                        'confidence': signals_data.get('confidence', 0),
                        'ma': signals_data.get('ma_signal', 0),
                        'rsi': signals_data.get('rsi_signal', 0),
                        'bb': signals_data.get('bb_signal', 0),
                        'macd': signals_data.get('macd_signal', 0),
                        'stoch': signals_data.get('stoch_signal', 0),
                        'atr': analysis.get('atr_percent', 0),
                        'adx': analysis.get('adx', 0),
                    }
                    signals.append(signal_entry)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    print(f"로그 파싱 중 오류 발생: {e} - 라인: {line.strip()}")
                    continue
        return signals

    def format_signal_value(self, value: float) -> str:
        return f"{value:+.2f}"

    def apply_filter(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        filter_value = self.filter_var.get()
        if filter_value == "전체": return signals
        return [s for s in signals if s.get('action') == filter_value]

    def calculate_statistics(self, signals: List[Dict[str, Any]]) -> str:
        if not signals: return "통계: 데이터 없음 (최근 24시간)"
        total = len(signals)
        buy_count = sum(1 for s in signals if s['action'] == 'BUY')
        sell_count = sum(1 for s in signals if s['action'] == 'SELL')
        hold_count = total - buy_count - sell_count
        return f"📊 최근 24시간 통계 - 총 {total}건 | HOLD: {hold_count} | BUY: {buy_count} | SELL: {sell_count}"

    def refresh_history(self):
        self.date_combo['values'] = self.get_available_dates()
        for item in self.tree.get_children():
            self.tree.delete(item)

        date = self.date_var.get()
        signals = self.parse_log_file(date)
        filtered_signals = self.apply_filter(signals)
        self.stats_label.config(text=self.calculate_statistics(filtered_signals))

        for signal in reversed(filtered_signals):
            tags = [signal['action']]
            if signal['overall'] > 0.3: tags.append('BUY_SIGNAL')
            elif signal['overall'] < -0.3: tags.append('SELL_SIGNAL')

            values = (
                signal['timestamp'],
                signal['action'],
                self.format_signal_value(signal['overall']),
                f"{signal['confidence']:.1%}",
                self.format_signal_value(signal['ma']),
                self.format_signal_value(signal['rsi']),
                self.format_signal_value(signal['macd']),
                self.format_signal_value(signal['stoch']),
                self.format_signal_value(signal['bb']),
                f"{signal['atr']:.2f}%",
                f"{signal['adx']:.1f}",
                signal['reason']
            )
            self.tree.insert('', 'end', values=values, tags=tags)

        if self.tree.get_children():
            first_item = self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self.tree.see(first_item)