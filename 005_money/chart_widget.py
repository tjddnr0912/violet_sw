#!/usr/bin/env python3
"""
실시간 캔들스틱 차트 위젯
기술적 지표와 매수/매도 시그널을 시각화
"""

import tkinter as tk
from tkinter import ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import mplfinance as mpf

from bithumb_api import get_candlestick
from strategy import calculate_moving_average, calculate_rsi, calculate_bollinger_bands


class ChartWidget:
    """실시간 차트 위젯"""

    def __init__(self, parent_frame, config: Dict):
        self.parent = parent_frame
        self.config = config

        # 차트 데이터
        self.df = None
        self.indicators = {}
        self.signals = []

        # UI 설정
        self.setup_ui()

    def setup_ui(self):
        """UI 구성"""
        # 메인 프레임
        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 상단 컨트롤 패널
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        # 차트 설정 컨트롤
        ttk.Label(control_frame, text="표시 지표:").pack(side=tk.LEFT, padx=5)

        self.show_ma = tk.BooleanVar(value=True)
        self.show_rsi = tk.BooleanVar(value=True)
        self.show_bollinger = tk.BooleanVar(value=False)

        ttk.Checkbutton(control_frame, text="이동평균선(MA)", variable=self.show_ma,
                       command=self.update_chart).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(control_frame, text="RSI", variable=self.show_rsi,
                       command=self.update_chart).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(control_frame, text="볼린저밴드", variable=self.show_bollinger,
                       command=self.update_chart).pack(side=tk.LEFT, padx=5)

        ttk.Button(control_frame, text="새로고침",
                  command=self.refresh_chart).pack(side=tk.LEFT, padx=20)

        # 차트 영역
        self.chart_frame = ttk.Frame(self.main_frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # matplotlib 차트 생성
        self.create_chart()

    def create_chart(self):
        """matplotlib 차트 생성"""
        # Figure 생성 (2개의 서브플롯: 가격차트, RSI)
        self.fig = Figure(figsize=(12, 8), dpi=100)

        # 캔버스 생성
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # 툴바 추가
        toolbar = NavigationToolbar2Tk(self.canvas, self.chart_frame)
        toolbar.update()

    def load_data(self, ticker: str, interval: str) -> bool:
        """캔들스틱 데이터 로드"""
        try:
            # 빗썸 API로 데이터 가져오기
            df = get_candlestick(ticker, interval)

            if df is None or df.empty:
                print(f"데이터 로드 실패: {ticker}")
                return False

            # 최근 100개 데이터만 사용
            self.df = df.tail(100).copy()

            # 기술적 지표 계산
            self.calculate_indicators()

            # 매수/매도 시그널 계산
            self.calculate_signals()

            return True

        except Exception as e:
            print(f"데이터 로드 오류: {e}")
            return False

    def calculate_indicators(self):
        """기술적 지표 계산"""
        if self.df is None or self.df.empty:
            return

        try:
            # 이동평균선 계산
            short_window = self.config.get('strategy', {}).get('short_ma_window', 5)
            long_window = self.config.get('strategy', {}).get('long_ma_window', 20)

            self.df['MA_short'] = self.df['close'].rolling(window=short_window).mean()
            self.df['MA_long'] = self.df['close'].rolling(window=long_window).mean()

            # RSI 계산
            rsi_period = self.config.get('strategy', {}).get('rsi_period', 14)
            delta = self.df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()

            rs = gain / loss
            self.df['RSI'] = 100 - (100 / (1 + rs))

            # 볼린저 밴드 계산
            bb_period = 20
            bb_std = 2
            self.df['BB_middle'] = self.df['close'].rolling(window=bb_period).mean()
            rolling_std = self.df['close'].rolling(window=bb_period).std()
            self.df['BB_upper'] = self.df['BB_middle'] + (rolling_std * bb_std)
            self.df['BB_lower'] = self.df['BB_middle'] - (rolling_std * bb_std)

            self.indicators = {
                'MA_short': short_window,
                'MA_long': long_window,
                'RSI': rsi_period,
                'BB': bb_period
            }

        except Exception as e:
            print(f"지표 계산 오류: {e}")

    def calculate_signals(self):
        """매수/매도 시그널 계산"""
        if self.df is None or self.df.empty:
            return

        self.signals = []

        try:
            rsi_buy = self.config.get('strategy', {}).get('rsi_oversold', 30)
            rsi_sell = self.config.get('strategy', {}).get('rsi_overbought', 70)

            for i in range(1, len(self.df)):
                idx = self.df.index[i]

                # 골든크로스 (MA 기반 매수 시그널)
                if (self.df['MA_short'].iloc[i] > self.df['MA_long'].iloc[i] and
                    self.df['MA_short'].iloc[i-1] <= self.df['MA_long'].iloc[i-1] and
                    self.df['RSI'].iloc[i] < rsi_sell):
                    self.signals.append({
                        'time': idx,
                        'type': 'BUY',
                        'price': self.df['close'].iloc[i],
                        'reason': 'Golden Cross + RSI'
                    })

                # 데드크로스 (MA 기반 매도 시그널)
                elif (self.df['MA_short'].iloc[i] < self.df['MA_long'].iloc[i] and
                      self.df['MA_short'].iloc[i-1] >= self.df['MA_long'].iloc[i-1] and
                      self.df['RSI'].iloc[i] > rsi_buy):
                    self.signals.append({
                        'time': idx,
                        'type': 'SELL',
                        'price': self.df['close'].iloc[i],
                        'reason': 'Dead Cross + RSI'
                    })

                # RSI 과매수 (매도 시그널)
                elif self.df['RSI'].iloc[i] > rsi_sell and self.df['RSI'].iloc[i-1] <= rsi_sell:
                    self.signals.append({
                        'time': idx,
                        'type': 'SELL',
                        'price': self.df['close'].iloc[i],
                        'reason': f'RSI Overbought ({self.df["RSI"].iloc[i]:.1f})'
                    })

                # RSI 과매도 (매수 시그널)
                elif self.df['RSI'].iloc[i] < rsi_buy and self.df['RSI'].iloc[i-1] >= rsi_buy:
                    self.signals.append({
                        'time': idx,
                        'type': 'BUY',
                        'price': self.df['close'].iloc[i],
                        'reason': f'RSI Oversold ({self.df["RSI"].iloc[i]:.1f})'
                    })

        except Exception as e:
            print(f"시그널 계산 오류: {e}")

    def update_chart(self):
        """차트 업데이트"""
        if self.df is None or self.df.empty:
            return

        try:
            # 기존 차트 지우기
            self.fig.clear()

            # RSI 표시 여부에 따라 서브플롯 개수 결정
            if self.show_rsi.get():
                gs = self.fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.1)
                ax1 = self.fig.add_subplot(gs[0])
                ax2 = self.fig.add_subplot(gs[1], sharex=ax1)
            else:
                ax1 = self.fig.add_subplot(111)
                ax2 = None

            # 1. 캔들스틱 차트
            self.plot_candlestick(ax1)

            # 2. 이동평균선
            if self.show_ma.get():
                self.plot_moving_averages(ax1)

            # 3. 볼린저 밴드
            if self.show_bollinger.get():
                self.plot_bollinger_bands(ax1)

            # 4. 매수/매도 시그널 배경
            self.plot_signal_backgrounds(ax1)

            # 5. RSI
            if self.show_rsi.get() and ax2 is not None:
                self.plot_rsi(ax2)

            # 차트 스타일 설정
            ax1.set_title(f"실시간 차트 - {self.config.get('trading', {}).get('target_ticker', 'BTC')}",
                         fontsize=14, fontweight='bold')
            ax1.set_ylabel('가격 (KRW)', fontsize=10)
            ax1.grid(True, alpha=0.3)
            ax1.legend(loc='upper left')

            # x축 레이블 회전
            if ax2 is not None:
                plt.setp(ax1.get_xticklabels(), visible=False)
                ax2.set_xlabel('시간', fontsize=10)
            else:
                ax1.set_xlabel('시간', fontsize=10)

            self.fig.autofmt_xdate()

            # 캔버스 업데이트
            self.canvas.draw()

        except Exception as e:
            print(f"차트 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()

    def plot_candlestick(self, ax):
        """캔들스틱 플롯"""
        try:
            # 상승/하락 구분
            up = self.df[self.df['close'] >= self.df['open']]
            down = self.df[self.df['close'] < self.df['open']]

            # 상승 캔들 (빨강)
            ax.bar(up.index, up['close'] - up['open'],
                  bottom=up['open'], color='red', alpha=0.8, width=0.6)
            ax.bar(up.index, up['high'] - up['close'],
                  bottom=up['close'], color='red', alpha=0.3, width=0.1)
            ax.bar(up.index, up['open'] - up['low'],
                  bottom=up['low'], color='red', alpha=0.3, width=0.1)

            # 하락 캔들 (파랑)
            ax.bar(down.index, down['open'] - down['close'],
                  bottom=down['close'], color='blue', alpha=0.8, width=0.6)
            ax.bar(down.index, down['high'] - down['open'],
                  bottom=down['open'], color='blue', alpha=0.3, width=0.1)
            ax.bar(down.index, down['close'] - down['low'],
                  bottom=down['low'], color='blue', alpha=0.3, width=0.1)

        except Exception as e:
            print(f"캔들스틱 플롯 오류: {e}")

    def plot_moving_averages(self, ax):
        """이동평균선 플롯"""
        try:
            if 'MA_short' in self.df.columns:
                ax.plot(self.df.index, self.df['MA_short'],
                       label=f"MA({self.indicators['MA_short']})",
                       color='orange', linewidth=1.5, alpha=0.8)

            if 'MA_long' in self.df.columns:
                ax.plot(self.df.index, self.df['MA_long'],
                       label=f"MA({self.indicators['MA_long']})",
                       color='purple', linewidth=1.5, alpha=0.8)

        except Exception as e:
            print(f"이동평균선 플롯 오류: {e}")

    def plot_bollinger_bands(self, ax):
        """볼린저 밴드 플롯"""
        try:
            if all(col in self.df.columns for col in ['BB_upper', 'BB_middle', 'BB_lower']):
                ax.plot(self.df.index, self.df['BB_upper'],
                       label='BB Upper', color='gray', linewidth=1, alpha=0.5, linestyle='--')
                ax.plot(self.df.index, self.df['BB_middle'],
                       label='BB Middle', color='gray', linewidth=1, alpha=0.5)
                ax.plot(self.df.index, self.df['BB_lower'],
                       label='BB Lower', color='gray', linewidth=1, alpha=0.5, linestyle='--')

                # 밴드 사이 영역 채우기
                ax.fill_between(self.df.index, self.df['BB_upper'], self.df['BB_lower'],
                               alpha=0.1, color='gray')

        except Exception as e:
            print(f"볼린저 밴드 플롯 오류: {e}")

    def plot_signal_backgrounds(self, ax):
        """매수/매도 시그널 배경색 표시"""
        try:
            if not self.signals:
                return

            # y축 범위 가져오기
            ymin, ymax = ax.get_ylim()

            for signal in self.signals:
                signal_time = signal['time']
                signal_type = signal['type']

                # 시그널 위치의 인덱스 찾기
                try:
                    idx = self.df.index.get_loc(signal_time)
                except:
                    continue

                # 배경색 설정
                if signal_type == 'BUY':
                    color = 'red'
                    alpha = 0.15
                else:  # SELL
                    color = 'blue'
                    alpha = 0.15

                # 캔들 하나의 너비만큼 배경색 표시
                ax.axvspan(signal_time, signal_time,
                          alpha=alpha, color=color, zorder=0)

                # 마커 표시
                marker = '^' if signal_type == 'BUY' else 'v'
                marker_color = 'red' if signal_type == 'BUY' else 'blue'
                y_pos = signal['price'] * 0.98 if signal_type == 'BUY' else signal['price'] * 1.02

                ax.plot(signal_time, y_pos, marker=marker,
                       markersize=12, color=marker_color,
                       markeredgecolor='black', markeredgewidth=1, zorder=5)

        except Exception as e:
            print(f"시그널 배경 플롯 오류: {e}")
            import traceback
            traceback.print_exc()

    def plot_rsi(self, ax):
        """RSI 플롯"""
        try:
            if 'RSI' not in self.df.columns:
                return

            rsi_overbought = self.config.get('strategy', {}).get('rsi_overbought', 70)
            rsi_oversold = self.config.get('strategy', {}).get('rsi_oversold', 30)

            # RSI 선
            ax.plot(self.df.index, self.df['RSI'],
                   label='RSI', color='purple', linewidth=1.5)

            # 과매수/과매도 라인
            ax.axhline(y=rsi_overbought, color='red', linestyle='--',
                      alpha=0.5, linewidth=1, label=f'Overbought ({rsi_overbought})')
            ax.axhline(y=rsi_oversold, color='blue', linestyle='--',
                      alpha=0.5, linewidth=1, label=f'Oversold ({rsi_oversold})')
            ax.axhline(y=50, color='gray', linestyle='-',
                      alpha=0.3, linewidth=0.5)

            # 과매수 영역 색칠
            ax.fill_between(self.df.index, rsi_overbought, 100,
                           alpha=0.1, color='red')
            ax.fill_between(self.df.index, 0, rsi_oversold,
                           alpha=0.1, color='blue')

            ax.set_ylabel('RSI', fontsize=10)
            ax.set_ylim(0, 100)
            ax.grid(True, alpha=0.3)
            ax.legend(loc='upper left', fontsize=8)

        except Exception as e:
            print(f"RSI 플롯 오류: {e}")

    def refresh_chart(self):
        """차트 새로고침"""
        ticker = self.config.get('trading', {}).get('target_ticker', 'BTC')
        interval = self.config.get('strategy', {}).get('candlestick_interval', '24h')

        if self.load_data(ticker, interval):
            self.update_chart()
            print(f"차트 업데이트 완료: {ticker} ({interval})")
        else:
            print(f"차트 업데이트 실패")

    def update_config(self, new_config: Dict):
        """설정 업데이트"""
        self.config = new_config
        self.refresh_chart()