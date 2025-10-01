#!/usr/bin/env python3
"""
신호 히스토리 위젯
로그에서 거래 신호 및 액션 정보를 추출하여 테이블로 표시
"""

import tkinter as tk
from tkinter import ttk
import json
import os
from datetime import datetime
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
        # 메인 프레임
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(1, weight=1)

        # 상단 제어 패널
        control_frame = ttk.LabelFrame(self.parent, text="📊 신호 히스토리 조회", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=10, pady=10)
        control_frame.columnconfigure(1, weight=1)

        # 날짜 선택
        ttk.Label(control_frame, text="조회 날짜:").grid(row=0, column=0, padx=(0, 10))

        self.date_var = tk.StringVar(value=datetime.now().strftime("%Y%m%d"))
        date_combo = ttk.Combobox(control_frame, textvariable=self.date_var, width=15)
        date_combo.grid(row=0, column=1, sticky=(tk.W,), padx=(0, 10))
        date_combo['values'] = self.get_available_dates()

        # 새로고침 버튼
        refresh_btn = ttk.Button(control_frame, text="🔄 새로고침", command=self.refresh_history)
        refresh_btn.grid(row=0, column=2, padx=(0, 10))

        # 필터 옵션
        ttk.Label(control_frame, text="필터:").grid(row=0, column=3, padx=(10, 10))

        self.filter_var = tk.StringVar(value="전체")
        filter_combo = ttk.Combobox(control_frame, textvariable=self.filter_var, width=10)
        filter_combo.grid(row=0, column=4, sticky=(tk.W,))
        filter_combo['values'] = ("전체", "HOLD", "BUY", "SELL", "매수신호", "매도신호")
        filter_combo.bind('<<ComboboxSelected>>', lambda e: self.refresh_history())

        # 통계 표시 프레임
        stats_frame = ttk.Frame(control_frame)
        stats_frame.grid(row=1, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=(10, 0))

        self.stats_label = ttk.Label(stats_frame, text="통계: -", foreground='blue')
        self.stats_label.pack(side=tk.LEFT)

        # 테이블 프레임
        table_frame = ttk.LabelFrame(self.parent, text="📈 신호 및 액션 히스토리 (최근 24시간)", padding="10")
        table_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=(0, 10))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        # 테이블 생성
        columns = ('timestamp', 'action', 'ma', 'rsi', 'bb', 'volume', 'overall', 'confidence', 'reason')
        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=20)

        # 컬럼 헤더 설정
        self.tree.heading('timestamp', text='시간')
        self.tree.heading('action', text='액션')
        self.tree.heading('ma', text='MA신호')
        self.tree.heading('rsi', text='RSI신호')
        self.tree.heading('bb', text='BB신호')
        self.tree.heading('volume', text='거래량신호')
        self.tree.heading('overall', text='종합신호')
        self.tree.heading('confidence', text='신뢰도')
        self.tree.heading('reason', text='사유')

        # 컬럼 너비 설정
        self.tree.column('timestamp', width=150, anchor=tk.CENTER)
        self.tree.column('action', width=80, anchor=tk.CENTER)
        self.tree.column('ma', width=80, anchor=tk.CENTER)
        self.tree.column('rsi', width=80, anchor=tk.CENTER)
        self.tree.column('bb', width=80, anchor=tk.CENTER)
        self.tree.column('volume', width=90, anchor=tk.CENTER)
        self.tree.column('overall', width=90, anchor=tk.CENTER)
        self.tree.column('confidence', width=80, anchor=tk.CENTER)
        self.tree.column('reason', width=200, anchor=tk.W)

        # 스크롤바
        scrollbar_y = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        # 배치
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        scrollbar_x.grid(row=1, column=0, sticky=(tk.W, tk.E))

        # 태그 색상 설정
        self.tree.tag_configure('BUY', background='#ffcccc')  # 연한 빨강
        self.tree.tag_configure('SELL', background='#ccccff')  # 연한 파랑
        self.tree.tag_configure('HOLD', background='white')
        self.tree.tag_configure('BUY_SIGNAL', foreground='red', font=('Arial', 9, 'bold'))
        self.tree.tag_configure('SELL_SIGNAL', foreground='blue', font=('Arial', 9, 'bold'))

        # 초기 데이터 로드
        self.refresh_history()

    def get_available_dates(self) -> List[str]:
        """사용 가능한 로그 날짜 목록 반환"""
        dates = []
        if os.path.exists(self.log_dir):
            for filename in os.listdir(self.log_dir):
                if filename.startswith('trading_') and filename.endswith('.log'):
                    # trading_20250930.log -> 20250930
                    date_str = filename.replace('trading_', '').replace('.log', '')
                    dates.append(date_str)
        return sorted(dates, reverse=True)

    def parse_log_file(self, date: str) -> List[Dict[str, Any]]:
        """로그 파일에서 신호 정보 파싱 (최근 24시간만)"""
        log_file = os.path.join(self.log_dir, f"trading_{date}.log")

        if not os.path.exists(log_file):
            return []

        signals = []

        # 현재 시간으로부터 24시간 전 계산
        from datetime import datetime, timedelta
        now = datetime.now()
        cutoff_time = now - timedelta(hours=24)

        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                # [ANALYSIS] 라인만 처리
                if '[ANALYSIS]' not in line:
                    continue

                try:
                    # JSON 부분 추출
                    json_start = line.find('{')
                    if json_start == -1:
                        continue

                    json_str = line[json_start:]
                    data = json.loads(json_str)

                    # 타임스탬프 추출 (로그 라인 앞부분에서)
                    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if timestamp_match:
                        timestamp = timestamp_match.group(1)
                    else:
                        timestamp = data.get('analysis', {}).get('timestamp', '')

                    # 24시간 필터링
                    if timestamp:
                        try:
                            log_time = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                            # 24시간 이전 로그는 스킵
                            if log_time < cutoff_time:
                                continue
                        except ValueError:
                            # 타임스탬프 파싱 실패 시 포함 (안전장치)
                            pass

                    # 신호 정보 추출
                    signals_data = data.get('signals', {})
                    action = data.get('action', 'HOLD')
                    reason = data.get('reason', '-')

                    signal_entry = {
                        'timestamp': timestamp,
                        'action': action,
                        'ma_signal': signals_data.get('ma_signal', 0),
                        'rsi_signal': signals_data.get('rsi_signal', 0),
                        'bb_signal': signals_data.get('bb_signal', 0),
                        'volume_signal': signals_data.get('volume_signal', 0),
                        'overall_signal': signals_data.get('overall_signal', 0),
                        'confidence': signals_data.get('confidence', 0),
                        'reason': reason
                    }

                    signals.append(signal_entry)

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"로그 파싱 오류: {e}")
                    continue

        return signals

    def signal_to_text(self, signal_value: int) -> str:
        """신호 값을 텍스트로 변환"""
        if signal_value == 1:
            return "매수 ↑"
        elif signal_value == -1:
            return "매도 ↓"
        else:
            return "중립 -"

    def apply_filter(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """필터 적용"""
        filter_value = self.filter_var.get()

        if filter_value == "전체":
            return signals
        elif filter_value == "HOLD":
            return [s for s in signals if s['action'] == 'HOLD']
        elif filter_value == "BUY":
            return [s for s in signals if s['action'] == 'BUY']
        elif filter_value == "SELL":
            return [s for s in signals if s['action'] == 'SELL']
        elif filter_value == "매수신호":
            return [s for s in signals if s['overall_signal'] == 1]
        elif filter_value == "매도신호":
            return [s for s in signals if s['overall_signal'] == -1]

        return signals

    def calculate_statistics(self, signals: List[Dict[str, Any]]) -> str:
        """통계 계산"""
        if not signals:
            return "통계: 데이터 없음 (최근 24시간)"

        total = len(signals)
        hold_count = sum(1 for s in signals if s['action'] == 'HOLD')
        buy_count = sum(1 for s in signals if s['action'] == 'BUY')
        sell_count = sum(1 for s in signals if s['action'] == 'SELL')

        buy_signal_count = sum(1 for s in signals if s['overall_signal'] == 1)
        sell_signal_count = sum(1 for s in signals if s['overall_signal'] == -1)

        stats_text = (
            f"📊 최근 24시간 통계 - 총 {total}건 | "
            f"HOLD: {hold_count} | BUY: {buy_count} | SELL: {sell_count} | "
            f"매수신호: {buy_signal_count} | 매도신호: {sell_signal_count}"
        )

        return stats_text

    def refresh_history(self):
        """히스토리 새로고침"""
        # 기존 데이터 삭제
        for item in self.tree.get_children():
            self.tree.delete(item)

        # 날짜 가져오기
        date = self.date_var.get()

        # 로그 파싱
        signals = self.parse_log_file(date)

        # 필터 적용
        filtered_signals = self.apply_filter(signals)

        # 통계 업데이트
        stats_text = self.calculate_statistics(filtered_signals)
        self.stats_label.config(text=stats_text)

        # 테이블에 데이터 추가 (최신순)
        for signal in reversed(filtered_signals):
            ma_text = self.signal_to_text(signal['ma_signal'])
            rsi_text = self.signal_to_text(signal['rsi_signal'])
            bb_text = self.signal_to_text(signal['bb_signal'])
            volume_text = self.signal_to_text(signal['volume_signal'])
            overall_text = self.signal_to_text(signal['overall_signal'])
            confidence_text = f"{signal['confidence']:.1%}"

            # 액션에 따라 태그 결정
            tags = [signal['action']]
            if signal['overall_signal'] == 1:
                tags.append('BUY_SIGNAL')
            elif signal['overall_signal'] == -1:
                tags.append('SELL_SIGNAL')

            values = (
                signal['timestamp'],
                signal['action'],
                ma_text,
                rsi_text,
                bb_text,
                volume_text,
                overall_text,
                confidence_text,
                signal['reason']
            )

            self.tree.insert('', 'end', values=values, tags=tags)

        # 첫 번째 항목 선택
        if self.tree.get_children():
            first_item = self.tree.get_children()[0]
            self.tree.selection_set(first_item)
            self.tree.see(first_item)
