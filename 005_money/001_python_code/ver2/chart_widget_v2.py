"""
Chart Widget for Version 2 - Multi-Timeframe Strategy

Displays:
- Daily EMA 50/200 (regime filter)
- 4H Bollinger Bands (entry/exit zones)
- 4H RSI
- 4H Stochastic RSI
- ATR values
- Entry score components visualization
"""

import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from datetime import datetime
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
import sys
import os

# Add lib path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.api.bithumb_api import get_candlestick


class ChartWidgetV2:
    """
    Chart widget for v2 strategy visualization.

    Features:
    - Dual timeframe display (Daily + 4H)
    - Regime filter visualization (EMA 50/200)
    - Entry signal components (BB, RSI, Stoch RSI)
    - Chandelier Exit trailing stop
    - Position entry/exit markers
    """

    def __init__(self, parent, config: Dict[str, Any]):
        self.parent = parent
        self.config = config
        self.coin_symbol = 'BTC'

        # Chart state
        self.current_timeframe = '4h'
        self.indicators_enabled = {
            'ema': True,
            'bb': True,
            'rsi': True,
            'stoch_rsi': True,
            'atr': True,
        }

        self.setup_ui()

    def setup_ui(self):
        """Setup chart UI with controls and canvas"""
        # Main container
        main_frame = ttk.Frame(self.parent)
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Control panel
        control_frame = ttk.LabelFrame(main_frame, text="차트 설정", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=5, pady=5)

        # Timeframe selector
        ttk.Label(control_frame, text="타임프레임:").grid(row=0, column=0, padx=(0, 5))
        self.timeframe_var = tk.StringVar(value='4h')
        timeframe_combo = ttk.Combobox(control_frame, textvariable=self.timeframe_var,
                                        values=['1h', '4h', '24h'], width=10, state='readonly')  # Bithumb uses '24h' not '1d'
        timeframe_combo.grid(row=0, column=1, padx=5)
        timeframe_combo.bind('<<ComboboxSelected>>', self.on_timeframe_changed)

        # Indicator checkboxes
        ttk.Label(control_frame, text="지표:").grid(row=0, column=2, padx=(20, 5))

        self.ema_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="EMA", variable=self.ema_var,
                       command=self.on_indicator_toggle).grid(row=0, column=3, padx=5)

        self.bb_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="BB", variable=self.bb_var,
                       command=self.on_indicator_toggle).grid(row=0, column=4, padx=5)

        self.rsi_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="RSI", variable=self.rsi_var,
                       command=self.on_indicator_toggle).grid(row=0, column=5, padx=5)

        self.stoch_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="Stoch RSI", variable=self.stoch_var,
                       command=self.on_indicator_toggle).grid(row=0, column=6, padx=5)

        self.atr_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="ATR", variable=self.atr_var,
                       command=self.on_indicator_toggle).grid(row=0, column=7, padx=5)

        # Refresh button
        ttk.Button(control_frame, text="🔄 새로고침",
                  command=self.refresh_chart).grid(row=0, column=8, padx=(20, 0))

        # Chart canvas
        chart_frame = ttk.Frame(main_frame)
        chart_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=5, pady=5)
        chart_frame.columnconfigure(0, weight=1)
        chart_frame.rowconfigure(0, weight=1)

        # Initialize matplotlib figure
        self.create_chart(chart_frame)

    def create_chart(self, parent):
        """Create matplotlib chart"""
        # Determine number of subplots based on enabled indicators
        num_subplots = 1  # Main price chart
        if self.rsi_var.get():
            num_subplots += 1
        if self.stoch_var.get():
            num_subplots += 1
        if self.atr_var.get():
            num_subplots += 1

        # Create figure
        self.fig = Figure(figsize=(12, 8), dpi=100, facecolor='white')

        # Height ratios (main chart larger)
        height_ratios = [3] + [1] * (num_subplots - 1)

        # Create subplots
        self.axes = []
        gs = self.fig.add_gridspec(num_subplots, 1, height_ratios=height_ratios, hspace=0.3)

        for i in range(num_subplots):
            ax = self.fig.add_subplot(gs[i])
            self.axes.append(ax)

        # Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Draw initial chart
        self.draw_chart()

    def draw_chart(self):
        """Draw chart with data"""
        # Fetch data
        interval = self.timeframe_var.get()
        df = self.fetch_chart_data(interval)

        if df is None or len(df) == 0:
            self.draw_no_data()
            return

        # Calculate indicators
        df = self.calculate_indicators(df)

        # Clear all axes
        for ax in self.axes:
            ax.clear()

        ax_idx = 0

        # Main price chart with BB and EMA
        self.draw_main_chart(self.axes[ax_idx], df)
        ax_idx += 1

        # RSI
        if self.rsi_var.get() and ax_idx < len(self.axes):
            self.draw_rsi(self.axes[ax_idx], df)
            ax_idx += 1

        # Stochastic RSI
        if self.stoch_var.get() and ax_idx < len(self.axes):
            self.draw_stoch_rsi(self.axes[ax_idx], df)
            ax_idx += 1

        # ATR
        if self.atr_var.get() and ax_idx < len(self.axes):
            self.draw_atr(self.axes[ax_idx], df)
            ax_idx += 1

        self.canvas.draw()

    def draw_main_chart(self, ax, df):
        """Draw main price chart with candlesticks, BB, and EMA"""
        # Candlestick colors
        colors = ['red' if c >= o else 'blue' for c, o in zip(df['close'], df['open'])]

        # Candlestick bodies
        for i, (idx, row) in enumerate(df.iterrows()):
            ax.plot([i, i], [row['low'], row['high']], color=colors[i], linewidth=1)
            body_height = abs(row['close'] - row['open'])
            body_bottom = min(row['close'], row['open'])
            ax.add_patch(plt.Rectangle((i-0.3, body_bottom), 0.6, body_height,
                                       facecolor=colors[i], edgecolor=colors[i]))

        # Bollinger Bands
        if self.bb_var.get() and 'bb_upper' in df.columns:
            x = range(len(df))
            ax.plot(x, df['bb_upper'], 'gray', linestyle='--', linewidth=1, label='BB Upper', alpha=0.7)
            ax.plot(x, df['bb_mid'], 'gray', linestyle='-', linewidth=1, label='BB Mid', alpha=0.7)
            ax.plot(x, df['bb_lower'], 'gray', linestyle='--', linewidth=1, label='BB Lower', alpha=0.7)
            ax.fill_between(x, df['bb_upper'], df['bb_lower'], alpha=0.1, color='gray')

        # EMA (if daily or enabled)
        if self.ema_var.get() and 'ema_fast' in df.columns:
            x = range(len(df))
            ax.plot(x, df['ema_fast'], 'orange', linewidth=2, label='EMA 50', alpha=0.8)
            ax.plot(x, df['ema_slow'], 'purple', linewidth=2, label='EMA 200', alpha=0.8)

        ax.set_title(f'{self.coin_symbol} Price Chart ({self.timeframe_var.get().upper()})', fontsize=14, fontweight='bold')
        ax.set_ylabel('Price (KRW)', fontsize=10)
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)

        # X-axis labels
        step = max(1, len(df) // 10)
        xticks = range(0, len(df), step)
        xticklabels = [df.index[i].strftime('%m-%d %H:%M') for i in xticks]
        ax.set_xticks(xticks)
        ax.set_xticklabels(xticklabels, rotation=45, ha='right')

    def draw_rsi(self, ax, df):
        """Draw RSI indicator"""
        if 'rsi' not in df.columns:
            return

        x = range(len(df))
        ax.plot(x, df['rsi'], 'purple', linewidth=2, label='RSI')
        ax.axhline(y=70, color='red', linestyle='--', linewidth=1, alpha=0.5)
        ax.axhline(y=30, color='blue', linestyle='--', linewidth=1, alpha=0.5)
        ax.fill_between(x, 30, 70, alpha=0.1, color='gray')

        ax.set_title('RSI (14)', fontsize=10, fontweight='bold')
        ax.set_ylabel('RSI', fontsize=9)
        ax.set_ylim(0, 100)
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)

    def draw_stoch_rsi(self, ax, df):
        """Draw Stochastic RSI"""
        if 'stoch_k' not in df.columns:
            return

        x = range(len(df))
        ax.plot(x, df['stoch_k'], 'blue', linewidth=2, label='%K')
        ax.plot(x, df['stoch_d'], 'orange', linewidth=2, label='%D')
        ax.axhline(y=80, color='red', linestyle='--', linewidth=1, alpha=0.5)
        ax.axhline(y=20, color='blue', linestyle='--', linewidth=1, alpha=0.5)
        ax.fill_between(x, 20, 80, alpha=0.1, color='gray')

        ax.set_title('Stochastic RSI (14,3,3)', fontsize=10, fontweight='bold')
        ax.set_ylabel('Stoch RSI', fontsize=9)
        ax.set_ylim(0, 100)
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)

    def draw_atr(self, ax, df):
        """Draw ATR indicator"""
        if 'atr' not in df.columns:
            return

        x = range(len(df))
        ax.plot(x, df['atr'], 'green', linewidth=2, label='ATR')

        ax.set_title('ATR (14)', fontsize=10, fontweight='bold')
        ax.set_ylabel('ATR', fontsize=9)
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)

    def draw_no_data(self):
        """Draw no data message"""
        for ax in self.axes:
            ax.clear()

        self.axes[0].text(0.5, 0.5, 'No Data Available',
                         ha='center', va='center', fontsize=16, transform=self.axes[0].transAxes)
        self.canvas.draw()

    def fetch_chart_data(self, interval: str) -> Optional[pd.DataFrame]:
        """Fetch chart data from API"""
        try:
            # get_candlestick already returns a DataFrame with 'time' as index
            df = get_candlestick(self.coin_symbol, interval)
            if df is None or len(df) == 0:
                return None

            # The DataFrame is already indexed by time and sorted
            # Just ensure we have the right column names
            df = df.sort_index()

            return df
        except Exception as e:
            print(f"Error fetching chart data: {e}")
            return None

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        # Bollinger Bands
        if self.bb_var.get():
            period = 20
            std = 2.0
            df['bb_mid'] = df['close'].rolling(window=period).mean()
            df['bb_std'] = df['close'].rolling(window=period).std()
            df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * std)
            df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * std)

        # EMA
        if self.ema_var.get():
            df['ema_fast'] = df['close'].ewm(span=50, adjust=False).mean()
            df['ema_slow'] = df['close'].ewm(span=200, adjust=False).mean()

        # RSI
        if self.rsi_var.get():
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))

        # Stochastic RSI
        if self.stoch_var.get() and 'rsi' in df.columns:
            rsi = df['rsi']
            stoch_period = 14
            k_smooth = 3
            d_smooth = 3

            rsi_min = rsi.rolling(window=stoch_period).min()
            rsi_max = rsi.rolling(window=stoch_period).max()
            stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min) * 100

            df['stoch_k'] = stoch_rsi.rolling(window=k_smooth).mean()
            df['stoch_d'] = df['stoch_k'].rolling(window=d_smooth).mean()

        # ATR
        if self.atr_var.get():
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            df['atr'] = true_range.rolling(window=14).mean()

        return df

    def on_timeframe_changed(self, event=None):
        """Handle timeframe change"""
        self.current_timeframe = self.timeframe_var.get()
        self.refresh_chart()

    def on_indicator_toggle(self):
        """Handle indicator checkbox toggle"""
        # Recreate chart with new subplot layout
        for widget in self.canvas.get_tk_widget().master.winfo_children():
            widget.destroy()

        self.create_chart(self.canvas.get_tk_widget().master)

    def refresh_chart(self):
        """Refresh chart data"""
        self.draw_chart()

    def update_chart(self, data: Optional[Dict[str, Any]] = None):
        """Update chart with new data (called from bot)"""
        self.refresh_chart()
