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

from ver1.strategy_v1 import StrategyV1 as TradingStrategy

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
        """Step 2: 기술적 지표 체크박스 생성 (엘리트 기능 포함)"""
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

        # Separator
        ttk.Separator(indicator_frame, orient=tk.HORIZONTAL).grid(
            row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 5)
        )

        # NEW: 엘리트 기능 체크박스
        elite_indicators = [
            ('candlestick_patterns', '캔들 패턴'),
            ('rsi_divergence', 'RSI 다이버전스'),
            ('macd_divergence', 'MACD 다이버전스'),
            ('chandelier_stop', 'Chandelier Stop'),
            ('bb_squeeze', 'BB Squeeze')
        ]

        for i, (key, label) in enumerate(elite_indicators):
            var = tk.BooleanVar(value=False)
            self.indicator_checkboxes[key] = var

            row = 5 + (i // 2)
            col = i % 2

            checkbox = ttk.Checkbutton(
                indicator_frame,
                text=label,
                variable=var,
                command=self.on_indicator_toggle
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
            # Explicitly close old figure to prevent memory leaks
            if hasattr(self, 'fig') and self.fig is not None:
                plt.close(self.fig)

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

            # NEW: 엘리트 기능 - BB Squeeze 영역 표시 (BB보다 먼저 그려서 배경에 위치)
            if self.indicator_checkboxes.get('bb_squeeze', tk.BooleanVar()).get():
                self.plot_bb_squeeze_zones(ax_main)

            # NEW: 엘리트 기능 - Chandelier Exit 트레일링 스톱
            if self.indicator_checkboxes.get('chandelier_stop', tk.BooleanVar()).get():
                self.plot_chandelier_stop(ax_main)

            # NEW: 엘리트 기능 - 캔들스틱 패턴 마커
            if self.indicator_checkboxes.get('candlestick_patterns', tk.BooleanVar()).get():
                self.plot_candlestick_patterns(ax_main)

            # Stochastic, ATR, ADX는 텍스트 정보로 표시 (엘리트 기능 추가)
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
                # NEW: RSI 다이버전스 표시
                if self.indicator_checkboxes.get('rsi_divergence', tk.BooleanVar()).get():
                    self.plot_rsi_divergence(ax_rsi)
                plt.setp(ax_rsi.get_xticklabels(), visible=False)

            if has_macd and ax_macd:
                self.plot_macd(ax_macd)
                # NEW: MACD 다이버전스 표시
                if self.indicator_checkboxes.get('macd_divergence', tk.BooleanVar()).get():
                    self.plot_macd_divergence(ax_macd)
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
        """Step 3: Stochastic, ATR, ADX 지표 정보를 텍스트로 생성 (엘리트 기능 포함)"""
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

        # NEW: 캔들스틱 패턴
        if self.indicator_checkboxes.get('candlestick_patterns', tk.BooleanVar()).get():
            if self.analysis and 'candlestick_pattern' in self.analysis:
                pattern = self.analysis['candlestick_pattern']
                pattern_type = pattern.get('pattern_type', 'None')
                pattern_score = pattern.get('pattern_score', 0.0)
                if pattern_type != 'None':
                    info_lines.append(f"Pattern: {pattern_type} ({pattern_score:+.2f})")

        # NEW: RSI 다이버전스
        if self.indicator_checkboxes.get('rsi_divergence', tk.BooleanVar()).get():
            if self.analysis and 'rsi_divergence' in self.analysis:
                div = self.analysis['rsi_divergence']
                div_type = div.get('divergence_type', 'None')
                if div_type != 'None':
                    info_lines.append(f"RSI Div: {div_type}")

        # NEW: MACD 다이버전스
        if self.indicator_checkboxes.get('macd_divergence', tk.BooleanVar()).get():
            if self.analysis and 'macd_divergence' in self.analysis:
                div = self.analysis['macd_divergence']
                div_type = div.get('divergence_type', 'None')
                if div_type != 'None':
                    info_lines.append(f"MACD Div: {div_type}")

        # NEW: Chandelier Stop
        if self.indicator_checkboxes.get('chandelier_stop', tk.BooleanVar()).get():
            if self.analysis and 'chandelier_exit' in self.analysis:
                stop = self.analysis['chandelier_exit']
                stop_price = stop.get('stop_price', 0)
                if stop_price > 0:
                    info_lines.append(f"Chandelier: {stop_price:,.0f}")

        # NEW: BB Squeeze
        if self.indicator_checkboxes.get('bb_squeeze', tk.BooleanVar()).get():
            if self.analysis and 'bb_squeeze' in self.analysis:
                squeeze = self.analysis['bb_squeeze']
                if squeeze.get('is_squeezing', False):
                    duration = squeeze.get('squeeze_duration', 0)
                    info_lines.append(f"BB Squeeze: {duration} candles")

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

    # ==================== NEW: 엘리트 기능 플로팅 함수 ====================

    def plot_candlestick_patterns(self, ax):
        """캔들스틱 패턴 마커 표시"""
        if not self.analysis or 'candlestick_pattern' not in self.analysis:
            return

        pattern = self.analysis['candlestick_pattern']
        pattern_type = pattern.get('pattern_type', 'None')
        pattern_score = pattern.get('pattern_score', 0.0)

        if pattern_type == 'None' or pattern_score == 0:
            return

        # 마지막 캔들 위치에 패턴 마커 표시
        last_idx = len(self.df) - 1
        last_price = self.df['high'].iloc[-1]

        # 패턴 타입에 따른 마커 및 색상 결정
        if pattern_score > 0:  # Bullish
            marker = '^'
            color = 'green'
            y_offset = -self.df['low'].iloc[-1] * 0.02  # 아래쪽에 표시
            va = 'top'
        else:  # Bearish
            marker = 'v'
            color = 'red'
            y_offset = self.df['high'].iloc[-1] * 0.02  # 위쪽에 표시
            va = 'bottom'

        # 마커 그리기
        ax.scatter([last_idx], [last_price + y_offset], marker=marker, s=200,
                  color=color, alpha=0.8, zorder=10, edgecolors='black', linewidths=1.5)

        # 패턴 이름 표시
        ax.text(last_idx, last_price + y_offset * 1.5, pattern_type,
               fontsize=8, color=color, fontweight='bold',
               ha='center', va=va, zorder=11,
               bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7, edgecolor=color))

    def plot_rsi_divergence(self, ax):
        """RSI 다이버전스 라인 표시"""
        if not self.analysis or 'rsi_divergence' not in self.analysis:
            return

        divergence = self.analysis['rsi_divergence']
        div_type = divergence.get('divergence_type', 'None')

        if div_type == 'None':
            return

        # 다이버전스 타입에 따른 색상 설정
        if div_type == 'Bullish':
            color = 'green'
            label_text = 'Bullish Div'
        else:  # Bearish
            color = 'red'
            label_text = 'Bearish Div'

        # 최근 데이터에서 다이버전스 포인트 찾기 (간략화된 표시)
        # 실제로는 strategy.py에서 계산된 정확한 포인트를 사용해야 하지만,
        # 여기서는 최근 30개 캔들에서 극값을 찾아 표시
        lookback = min(30, len(self.df))
        recent_data = self.df.tail(lookback)

        if 'rsi' not in recent_data.columns:
            return

        # RSI 극값 찾기
        rsi_values = recent_data['rsi'].values
        if div_type == 'Bullish':
            # 저점 찾기
            local_mins = []
            for i in range(1, len(rsi_values) - 1):
                if rsi_values[i] < rsi_values[i-1] and rsi_values[i] < rsi_values[i+1]:
                    local_mins.append(i)
            if len(local_mins) >= 2:
                # 마지막 두 저점 연결
                idx1 = len(self.df) - lookback + local_mins[-2]
                idx2 = len(self.df) - lookback + local_mins[-1]
                ax.plot([idx1, idx2], [rsi_values[local_mins[-2]], rsi_values[local_mins[-1]]],
                       linestyle='--', color=color, linewidth=2, alpha=0.7, label=label_text)
        else:  # Bearish
            # 고점 찾기
            local_maxs = []
            for i in range(1, len(rsi_values) - 1):
                if rsi_values[i] > rsi_values[i-1] and rsi_values[i] > rsi_values[i+1]:
                    local_maxs.append(i)
            if len(local_maxs) >= 2:
                # 마지막 두 고점 연결
                idx1 = len(self.df) - lookback + local_maxs[-2]
                idx2 = len(self.df) - lookback + local_maxs[-1]
                ax.plot([idx1, idx2], [rsi_values[local_maxs[-2]], rsi_values[local_maxs[-1]]],
                       linestyle='--', color=color, linewidth=2, alpha=0.7, label=label_text)

    def plot_macd_divergence(self, ax):
        """MACD 다이버전스 라인 표시"""
        if not self.analysis or 'macd_divergence' not in self.analysis:
            return

        divergence = self.analysis['macd_divergence']
        div_type = divergence.get('divergence_type', 'None')

        if div_type == 'None':
            return

        # 다이버전스 타입에 따른 색상 설정
        if div_type == 'Bullish':
            color = 'green'
            label_text = 'Bullish Div'
        else:  # Bearish
            color = 'red'
            label_text = 'Bearish Div'

        # RSI와 동일한 로직으로 MACD 히스토그램에서 극값 찾기
        lookback = min(30, len(self.df))
        recent_data = self.df.tail(lookback)

        if 'macd_histogram' not in recent_data.columns:
            return

        macd_hist = recent_data['macd_histogram'].values
        if div_type == 'Bullish':
            local_mins = []
            for i in range(1, len(macd_hist) - 1):
                if macd_hist[i] < macd_hist[i-1] and macd_hist[i] < macd_hist[i+1]:
                    local_mins.append(i)
            if len(local_mins) >= 2:
                idx1 = len(self.df) - lookback + local_mins[-2]
                idx2 = len(self.df) - lookback + local_mins[-1]
                ax.plot([idx1, idx2], [macd_hist[local_mins[-2]], macd_hist[local_mins[-1]]],
                       linestyle='--', color=color, linewidth=2, alpha=0.7, label=label_text)
        else:  # Bearish
            local_maxs = []
            for i in range(1, len(macd_hist) - 1):
                if macd_hist[i] > macd_hist[i-1] and macd_hist[i] > macd_hist[i+1]:
                    local_maxs.append(i)
            if len(local_maxs) >= 2:
                idx1 = len(self.df) - lookback + local_maxs[-2]
                idx2 = len(self.df) - lookback + local_maxs[-1]
                ax.plot([idx1, idx2], [macd_hist[local_maxs[-2]], macd_hist[local_maxs[-1]]],
                       linestyle='--', color=color, linewidth=2, alpha=0.7, label=label_text)

    def plot_chandelier_stop(self, ax):
        """Chandelier Exit 트레일링 스톱 라인 표시"""
        if not self.analysis or 'chandelier_exit' not in self.analysis:
            return

        chandelier = self.analysis['chandelier_exit']
        stop_price = chandelier.get('stop_price', 0)
        trailing_status = chandelier.get('trailing_status', 'initial')

        if stop_price <= 0:
            return

        # 상태에 따른 색상 설정
        if trailing_status == 'triggered':
            color = 'red'
            linestyle = '-'
            alpha = 0.9
        elif trailing_status == 'active':
            color = 'orange'
            linestyle = '--'
            alpha = 0.7
        else:  # initial
            color = 'gold'
            linestyle = ':'
            alpha = 0.6

        # 전체 차트에 수평선 그리기
        x = list(range(len(self.df)))
        ax.axhline(y=stop_price, color=color, linestyle=linestyle,
                  linewidth=2, alpha=alpha, label=f'Chandelier Stop ({stop_price:,.0f})')

        # 마지막 지점에 레이블 표시
        ax.text(len(self.df) - 1, stop_price, f' {stop_price:,.0f}',
               fontsize=8, color=color, fontweight='bold',
               ha='left', va='center',
               bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.7, edgecolor=color))

    def plot_bb_squeeze_zones(self, ax):
        """BB Squeeze 영역 표시 (배경 음영)"""
        if not self.analysis or 'bb_squeeze' not in self.analysis:
            return

        squeeze = self.analysis['bb_squeeze']
        is_squeezing = squeeze.get('is_squeezing', False)
        squeeze_duration = squeeze.get('squeeze_duration', 0)
        breakout_direction = squeeze.get('breakout_direction', 'neutral')

        if not is_squeezing or squeeze_duration <= 0:
            return

        # 스퀴즈 영역 계산 (최근 squeeze_duration 개 캔들)
        start_idx = max(0, len(self.df) - squeeze_duration)
        end_idx = len(self.df) - 1

        # 방향에 따른 색상 설정
        if breakout_direction == 'up':
            color = 'green'
            alpha = 0.1
        elif breakout_direction == 'down':
            color = 'red'
            alpha = 0.1
        else:  # neutral
            color = 'gray'
            alpha = 0.08

        # 배경 음영 그리기
        y_min, y_max = ax.get_ylim()
        ax.axvspan(start_idx, end_idx, facecolor=color, alpha=alpha, zorder=0)

        # 스퀴즈 표시 텍스트
        mid_idx = (start_idx + end_idx) / 2
        mid_price = (self.df['high'].iloc[start_idx:end_idx+1].max() +
                    self.df['low'].iloc[start_idx:end_idx+1].min()) / 2

        ax.text(mid_idx, mid_price, 'BB SQUEEZE',
               fontsize=9, color=color, fontweight='bold',
               ha='center', va='center', alpha=0.6,
               bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.5, edgecolor=color))