#!/usr/bin/env python3
"""
실시간 캔들스틱 차트 위젯 (v3.0 - Clean Rebuild)
Step 1: Simple, clean candlestick chart implementation
Step 2: Technical indicator checkboxes
Step 3: Dynamic on/off functionality for indicators
"""

import tkinter as tk
from tkinter import ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
import numpy as np
from typing import Dict, Any
import platform

from strategy import TradingStrategy

# OS에 맞는 한글 폰트 설정
try:
    if platform.system() == 'Windows':
        plt.rc('font', family='Malgun Gothic')
    elif platform.system() == 'Darwin':  # macOS
        plt.rc('font', family='AppleGothic')
    else:  # Linux
        plt.rc('font', family='NanumGothic')
except OSError:
    print("경고: 지정된 한글 폰트가 없습니다. 차트의 한글이 깨질 수 있습니다.")

# 마이너스 부호 깨짐 방지
import matplotlib
matplotlib.rcParams['axes.unicode_minus'] = False


class ChartWidget:
    """실시간 차트 위젯 - 단계별 구현"""

    def __init__(self, parent_frame, config: Dict):
        self.parent = parent_frame
        self.config = config
        self.strategy = TradingStrategy()
        self.df = None
        self.analysis = None
        self.signals = None

        # Step 2: 기술적 지표 체크박스 상태
        self.indicator_checkboxes = {}

        self.setup_ui()

    def setup_ui(self):
        """UI 구성"""
        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 상단 제어 패널
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill=tk.X, padx=5, pady=5)

        # 새로고침 버튼
        ttk.Button(control_frame, text="🔄 차트 새로고침",
                  command=self.refresh_chart).pack(side=tk.LEFT, padx=5)

        # Step 2: 기술적 지표 체크박스 패널
        self.create_indicator_checkboxes(control_frame)

        # 차트 영역
        self.chart_frame = ttk.Frame(self.main_frame)
        self.chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Figure 생성 (적절한 크기와 DPI)
        self.fig = Figure(figsize=(14, 8), dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def create_indicator_checkboxes(self, parent):
        """Step 2: 기술적 지표 체크박스 생성"""
        indicator_frame = ttk.LabelFrame(parent, text="📊 기술적 지표", padding="5")
        indicator_frame.pack(side=tk.LEFT, padx=10)

        # 지표 목록 (초기값: 모두 체크 해제)
        indicators = [
            ('ma', 'MA (이동평균선)'),
            ('rsi', 'RSI'),
            ('bb', 'Bollinger Bands'),
            ('macd', 'MACD'),
            ('volume', 'Volume'),
            ('stochastic', 'Stochastic'),
            ('atr', 'ATR'),
            ('adx', 'ADX')
        ]

        # 2열로 배치
        for i, (key, label) in enumerate(indicators):
            var = tk.BooleanVar(value=False)  # 초기값: 모두 비활성화
            self.indicator_checkboxes[key] = var

            row = i // 2
            col = i % 2

            checkbox = ttk.Checkbutton(
                indicator_frame,
                text=label,
                variable=var,
                command=self.on_indicator_toggle  # Step 3: 체크박스 토글 시 차트 업데이트
            )
            checkbox.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)

    def on_indicator_toggle(self):
        """Step 3: 지표 체크박스 토글 시 차트 즉시 업데이트"""
        if self.df is not None and not self.df.empty:
            self.update_chart()

    def load_and_prepare_data(self) -> bool:
        """데이터 로드 및 모든 지표 계산"""
        try:
            ticker = self.config.get('trading', {}).get('target_ticker', 'BTC')
            interval = self.config.get('strategy', {}).get('candlestick_interval', '1h')

            analysis_data = self.strategy.analyze_market_data(ticker, interval)

            if analysis_data is None or 'price_data' not in analysis_data:
                print(f"차트 데이터 분석 실패: {ticker}")
                self.df = None
                return False

            self.df = analysis_data['price_data'].tail(100).copy()
            self.analysis = analysis_data
            self.signals = self.strategy.generate_weighted_signals(self.analysis)

            return True

        except Exception as e:
            print(f"차트 데이터 준비 오류: {e}")
            import traceback
            traceback.print_exc()
            return False

    def update_chart(self):
        """Step 1 & 3: 캔들스틱 차트 + 활성화된 지표 표시"""
        if self.df is None or self.df.empty:
            return

        try:
            self.fig.clear()

            # 활성화된 서브플롯 확인
            has_rsi = self.indicator_checkboxes['rsi'].get()
            has_macd = self.indicator_checkboxes['macd'].get()
            has_volume = self.indicator_checkboxes['volume'].get()

            # 서브플롯 개수 계산
            num_subplots = 1  # 메인 캔들스틱 차트
            if has_rsi:
                num_subplots += 1
            if has_macd:
                num_subplots += 1
            if has_volume:
                num_subplots += 1

            # 서브플롯 레이아웃 생성
            if num_subplots == 1:
                # 캔들스틱만
                ax_main = self.fig.add_subplot(111)
                ax_rsi = None
                ax_macd = None
                ax_volume = None
            elif num_subplots == 2:
                # 캔들스틱 + 1개 지표
                gs = self.fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.1)
                ax_main = self.fig.add_subplot(gs[0])

                # 활성화된 지표에 두 번째 서브플롯 할당
                if has_rsi:
                    ax_rsi = self.fig.add_subplot(gs[1], sharex=ax_main)
                    ax_macd = None
                    ax_volume = None
                elif has_macd:
                    ax_rsi = None
                    ax_macd = self.fig.add_subplot(gs[1], sharex=ax_main)
                    ax_volume = None
                else:  # has_volume
                    ax_rsi = None
                    ax_macd = None
                    ax_volume = self.fig.add_subplot(gs[1], sharex=ax_main)
            elif num_subplots == 3:
                # 캔들스틱 + 2개 지표
                gs = self.fig.add_gridspec(3, 1, height_ratios=[3, 1, 1], hspace=0.1)
                ax_main = self.fig.add_subplot(gs[0])

                subplot_idx = 1
                ax_rsi = None
                ax_macd = None
                ax_volume = None

                if has_rsi:
                    ax_rsi = self.fig.add_subplot(gs[subplot_idx], sharex=ax_main)
                    subplot_idx += 1
                if has_macd:
                    ax_macd = self.fig.add_subplot(gs[subplot_idx], sharex=ax_main)
                    subplot_idx += 1
                if has_volume and subplot_idx < 3:
                    ax_volume = self.fig.add_subplot(gs[subplot_idx], sharex=ax_main)
            else:  # num_subplots >= 4
                # 캔들스틱 + 3개 지표
                gs = self.fig.add_gridspec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.1)
                ax_main = self.fig.add_subplot(gs[0])

                subplot_idx = 1
                ax_rsi = None
                ax_macd = None
                ax_volume = None

                if has_rsi:
                    ax_rsi = self.fig.add_subplot(gs[subplot_idx], sharex=ax_main)
                    subplot_idx += 1
                if has_macd:
                    ax_macd = self.fig.add_subplot(gs[subplot_idx], sharex=ax_main)
                    subplot_idx += 1
                if has_volume:
                    ax_volume = self.fig.add_subplot(gs[subplot_idx], sharex=ax_main)

            # Step 1: 캔들스틱 그리기
            self.plot_candlesticks(ax_main)

            # Step 3: 활성화된 메인 차트 지표
            if self.indicator_checkboxes['ma'].get():
                self.plot_moving_averages(ax_main)

            if self.indicator_checkboxes['bb'].get():
                self.plot_bollinger_bands(ax_main)

            # Stochastic, ATR, ADX는 텍스트 정보로 표시
            info_text = self.get_indicator_info_text()
            if info_text:
                ax_main.text(0.99, 0.97, info_text,
                           transform=ax_main.transAxes,
                           verticalalignment='top',
                           horizontalalignment='right',
                           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
                           fontsize=8)

            # Step 3: 서브플롯 지표
            if has_rsi and ax_rsi:
                self.plot_rsi(ax_rsi)
                plt.setp(ax_rsi.get_xticklabels(), visible=False)

            if has_macd and ax_macd:
                self.plot_macd(ax_macd)
                plt.setp(ax_macd.get_xticklabels(), visible=False)

            if has_volume and ax_volume:
                self.plot_volume(ax_volume)

            # 차트 스타일 설정
            ticker = self.config.get('trading', {}).get('target_ticker', 'BTC')
            ax_main.set_title(f"{ticker} 실시간 차트", fontsize=14, fontweight='bold', pad=20)
            ax_main.set_ylabel('가격 (KRW)', fontsize=11)
            ax_main.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)

            # 메인 차트 x축 레이블 숨김 (서브플롯이 있을 때)
            if num_subplots > 1:
                plt.setp(ax_main.get_xticklabels(), visible=False)
            else:
                ax_main.set_xlabel('시간', fontsize=11)

            # 범례 표시 (지표가 있을 때만)
            handles, labels = ax_main.get_legend_handles_labels()
            if labels:
                ax_main.legend(loc='upper left', fontsize=9)

            # 마지막 서브플롯에만 x축 레이블 표시
            bottom_ax = ax_volume if ax_volume else (ax_macd if ax_macd else (ax_rsi if ax_rsi else ax_main))
            bottom_ax.set_xlabel('시간', fontsize=11)
            bottom_ax.tick_params(axis='x', rotation=45, labelsize=9)

            # x축 눈금 개수 제한
            bottom_ax.xaxis.set_major_locator(plt.MaxNLocator(12))

            # 레이아웃 최적화
            self.fig.tight_layout(pad=1.5)

            self.canvas.draw()

        except Exception as e:
            print(f"차트 업데이트 오류: {e}")
            import traceback
            traceback.print_exc()

    def plot_candlesticks(self, ax):
        """Step 1: 깔끔한 캔들스틱 직접 그리기 (matplotlib만 사용)"""

        # 캔들 너비 계산 (데이터 포인트 간격의 60%)
        width = 0.6

        for idx, (timestamp, row) in enumerate(self.df.iterrows()):
            open_price = row['open']
            high_price = row['high']
            low_price = row['low']
            close_price = row['close']

            # 상승/하락 색상 결정
            if close_price >= open_price:
                color = 'red'  # 상승
                body_color = 'red'
                edge_color = 'darkred'
            else:
                color = 'blue'  # 하락
                body_color = 'blue'
                edge_color = 'darkblue'

            # 고가-저가 선 (심지)
            ax.plot([idx, idx], [low_price, high_price],
                   color=color, linewidth=1, solid_capstyle='round')

            # 시가-종가 박스 (몸통)
            height = abs(close_price - open_price)
            bottom = min(open_price, close_price)

            rect = Rectangle((idx - width/2, bottom), width, height,
                           facecolor=body_color, edgecolor=edge_color,
                           linewidth=1, alpha=0.8)
            ax.add_patch(rect)

        # x축 설정 (시간 레이블)
        ax.set_xlim(-1, len(self.df))

        # x축 눈금을 시간으로 표시
        step = max(1, len(self.df) // 10)  # 최대 10개 레이블
        tick_positions = list(range(0, len(self.df), step))
        tick_labels = [self.df.index[i].strftime('%m/%d %H:%M')
                      for i in tick_positions if i < len(self.df)]

        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, fontsize=9)

        # y축 가격 범위 설정 (여유 5%)
        price_min = self.df['low'].min()
        price_max = self.df['high'].max()
        price_range = price_max - price_min
        ax.set_ylim(price_min - price_range * 0.05,
                   price_max + price_range * 0.05)

        # 가격 포맷 (천 단위 구분)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(
            lambda x, p: f'{x:,.0f}'
        ))

    def plot_moving_averages(self, ax):
        """Step 3: 이동평균선 표시"""
        if 'short_ma' not in self.df.columns or 'long_ma' not in self.df.columns:
            return

        config = self.analysis.get('indicator_config', {})
        short_window = config.get('short_ma_window', 10)
        long_window = config.get('long_ma_window', 30)

        x = list(range(len(self.df)))
        ax.plot(x, self.df['short_ma'],
               label=f'MA({short_window})',
               color='orange', linewidth=1.5, alpha=0.9)
        ax.plot(x, self.df['long_ma'],
               label=f'MA({long_window})',
               color='purple', linewidth=1.5, alpha=0.9)

    def plot_bollinger_bands(self, ax):
        """Step 3: 볼린저 밴드 표시"""
        if 'bb_upper' not in self.df.columns or 'bb_lower' not in self.df.columns:
            return

        x = list(range(len(self.df)))
        ax.plot(x, self.df['bb_upper'],
               color='gray', linewidth=1, alpha=0.7, linestyle='--', label='BB Upper')
        ax.plot(x, self.df['bb_lower'],
               color='gray', linewidth=1, alpha=0.7, linestyle='--', label='BB Lower')
        ax.fill_between(x, self.df['bb_upper'], self.df['bb_lower'],
                        alpha=0.1, color='gray')

    def plot_rsi(self, ax):
        """Step 3: RSI 지표 표시"""
        if 'rsi' not in self.df.columns:
            return

        x = list(range(len(self.df)))

        # RSI 설정값
        overbought = 70
        oversold = 30

        # RSI 라인
        ax.plot(x, self.df['rsi'], label='RSI', color='purple', linewidth=1.5)

        # 과매수/과매도 선
        ax.axhline(y=overbought, color='red', linestyle='--', alpha=0.5, linewidth=1)
        ax.axhline(y=oversold, color='blue', linestyle='--', alpha=0.5, linewidth=1)
        ax.axhline(y=50, color='gray', linestyle=':', alpha=0.3, linewidth=0.8)

        # 과매수/과매도 영역 색칠
        ax.fill_between(x, overbought, 100, alpha=0.1, color='red')
        ax.fill_between(x, 0, oversold, alpha=0.1, color='blue')

        ax.set_ylabel('RSI', fontsize=10)
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.legend(loc='upper left', fontsize=8)

    def plot_macd(self, ax):
        """Step 3: MACD 지표 표시"""
        if 'macd_line' not in self.df.columns:
            return

        x = list(range(len(self.df)))

        # MACD 라인과 시그널 라인
        ax.plot(x, self.df['macd_line'], label='MACD', color='blue', linewidth=1.3)
        ax.plot(x, self.df['macd_signal'], label='Signal', color='red',
               linestyle='--', linewidth=1.3)

        # 히스토그램 (MACD - Signal)
        if 'macd_histogram' in self.df.columns:
            colors = ['green' if v >= 0 else 'red' for v in self.df['macd_histogram']]
            ax.bar(x, self.df['macd_histogram'], label='Histogram',
                  color=colors, alpha=0.4, width=0.8)

        # 제로 라인
        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5, linewidth=1)

        ax.set_ylabel('MACD', fontsize=10)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.legend(loc='upper left', fontsize=8)

    def plot_volume(self, ax):
        """Step 3: 거래량 표시"""
        if 'volume' not in self.df.columns:
            return

        x = list(range(len(self.df)))

        # 상승/하락에 따라 색상 다르게
        colors = []
        for i, (timestamp, row) in enumerate(self.df.iterrows()):
            if row['close'] >= row['open']:
                colors.append('red')  # 상승
            else:
                colors.append('blue')  # 하락

        # 거래량 바 차트
        ax.bar(x, self.df['volume'], color=colors, alpha=0.6, width=0.8)

        ax.set_ylabel('거래량', fontsize=10)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)

        # y축 포맷 (천 단위 구분)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(
            lambda x, p: f'{x:,.0f}'
        ))

    def get_indicator_info_text(self) -> str:
        """Step 3: Stochastic, ATR, ADX 지표 정보를 텍스트로 생성"""
        info_lines = []

        # Stochastic
        if self.indicator_checkboxes['stochastic'].get():
            if 'stoch_k' in self.df.columns and 'stoch_d' in self.df.columns:
                stoch_k = self.df['stoch_k'].iloc[-1]
                stoch_d = self.df['stoch_d'].iloc[-1]
                info_lines.append(f"Stochastic: K={stoch_k:.1f}, D={stoch_d:.1f}")

        # ATR
        if self.indicator_checkboxes['atr'].get():
            if self.analysis and 'atr' in self.analysis:
                atr = self.analysis['atr']
                atr_pct = self.analysis.get('atr_percent', 0)
                info_lines.append(f"ATR: {atr:,.0f} ({atr_pct:.2f}%)")

        # ADX
        if self.indicator_checkboxes['adx'].get():
            if self.analysis and 'adx' in self.analysis:
                adx = self.analysis['adx']
                trend_text = "강한 추세" if adx > 25 else "약한 추세"
                info_lines.append(f"ADX: {adx:.1f} ({trend_text})")

        return '\n'.join(info_lines) if info_lines else ""

    def refresh_chart(self):
        """차트 새로고침"""
        if self.load_and_prepare_data():
            self.update_chart()
            print("✅ Step 1 완료: 캔들스틱 차트 업데이트 성공")
        else:
            self.fig.clear()
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "차트 데이터 로드 실패\n새로고침 버튼을 다시 클릭해주세요",
                   ha='center', va='center', fontsize=12, color='red')
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis('off')
            self.canvas.draw()
            print("❌ 차트 데이터 로드 실패")

    def update_config(self, new_config: Dict):
        """설정 업데이트"""
        self.config = new_config
        self.refresh_chart()