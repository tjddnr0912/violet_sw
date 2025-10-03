#!/usr/bin/env python3
"""
ChartColumn - Individual chart widget with independent controls
Features:
- 8 independent indicator checkboxes
- Optional interval dropdown (for column 1)
- Dynamic subplot layout based on enabled indicators
- Pure matplotlib candlestick plotting
- Isolated redraw logic (only updates when state changes)
"""

import tkinter as tk
from tkinter import ttk
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd
import numpy as np
from typing import Dict, Optional
import logging
import platform

# Font setup for Korean text
try:
    if platform.system() == 'Windows':
        plt.rc('font', family='Malgun Gothic')
    elif platform.system() == 'Darwin':  # macOS
        plt.rc('font', family='AppleGothic')
    else:  # Linux
        plt.rc('font', family='NanumGothic')
except OSError:
    print("Warning: Korean font not available, text may not display correctly")

plt.rcParams['axes.unicode_minus'] = False


class ChartColumn:
    """
    Individual chart column widget for multi-timeframe display
    Each column can display candlesticks with selectable indicators
    """

    def __init__(self, parent, interval: str, data_manager, indicator_calculator,
                 has_dropdown: bool = False, column_label: str = "차트"):
        """
        Initialize ChartColumn

        Args:
            parent: Parent tkinter widget
            interval: Initial candlestick interval (e.g., '1h', '4h', '24h')
            data_manager: DataManager instance for fetching data
            indicator_calculator: IndicatorCalculator instance for calculations
            has_dropdown: Whether to show interval dropdown (True for column 1 only)
            column_label: Label text for this column
        """
        self.parent = parent
        self.interval = interval
        self.data_manager = data_manager
        self.indicator_calculator = indicator_calculator
        self.has_dropdown = has_dropdown
        self.column_label = column_label
        self.logger = logging.getLogger(__name__)

        # Data storage
        self.df: Optional[pd.DataFrame] = None
        self.indicators: Dict = {}

        # Indicator checkbox states (all start UNCHECKED)
        self.indicator_vars = {
            'ma': tk.BooleanVar(value=False),
            'rsi': tk.BooleanVar(value=False),
            'bb': tk.BooleanVar(value=False),
            'volume': tk.BooleanVar(value=False),
            'macd': tk.BooleanVar(value=False),
            'stochastic': tk.BooleanVar(value=False),
            'atr': tk.BooleanVar(value=False),
            'adx': tk.BooleanVar(value=False)
        }

        # Debouncing for checkbox toggles
        self.redraw_timer = None
        self.debounce_delay = 200  # milliseconds

        # Chart objects
        self.fig = None
        self.canvas = None

        # Build UI
        self.setup_ui()

        # Initial data load
        self.refresh_data()

    def setup_ui(self):
        """Build the column UI layout"""
        # Main container frame
        # Note: parent will handle placement (grid/pack), so we don't pack here
        self.main_frame = ttk.Frame(self.parent, relief=tk.RIDGE, borderwidth=2)

        # 1. Column label
        label = ttk.Label(self.main_frame, text=self.column_label,
                         font=('Arial', 11, 'bold'))
        label.pack(pady=(5, 2))

        # 2. Interval dropdown (only if has_dropdown=True)
        if self.has_dropdown:
            self.create_interval_dropdown()

        # 3. Indicator checkbox panel
        self.create_indicator_checkboxes()

        # 4. Chart canvas
        self.create_chart_canvas()

    def create_interval_dropdown(self):
        """Create interval selection dropdown (Column 1 only)"""
        dropdown_frame = ttk.Frame(self.main_frame)
        dropdown_frame.pack(pady=5)

        ttk.Label(dropdown_frame, text="간격:").pack(side=tk.LEFT, padx=(5, 2))

        self.interval_var = tk.StringVar(value=self.interval)
        intervals = ['30m', '1h', '6h', '12h', '24h']

        dropdown = ttk.Combobox(dropdown_frame, textvariable=self.interval_var,
                               values=intervals, state='readonly', width=8)
        dropdown.pack(side=tk.LEFT)
        dropdown.bind('<<ComboboxSelected>>', self.on_interval_change)

    def create_indicator_checkboxes(self):
        """Create 8 indicator checkboxes in 2 rows x 4 columns"""
        checkbox_frame = ttk.LabelFrame(self.main_frame, text="지표 선택", padding="5")
        checkbox_frame.pack(pady=5, padx=5, fill=tk.X)

        # Indicator definitions (Korean labels)
        indicators = [
            ('ma', 'MA'),
            ('rsi', 'RSI'),
            ('bb', 'BB'),
            ('volume', 'Volume'),
            ('macd', 'MACD'),
            ('stochastic', 'Stoch'),
            ('atr', 'ATR'),
            ('adx', 'ADX')
        ]

        # Create 2 rows x 4 columns
        for i, (key, label) in enumerate(indicators):
            row = i // 4
            col = i % 4

            checkbox = ttk.Checkbutton(
                checkbox_frame,
                text=label,
                variable=self.indicator_vars[key],
                command=lambda k=key: self.on_indicator_toggle(k)
            )
            checkbox.grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)

    def create_chart_canvas(self):
        """Create matplotlib chart canvas"""
        chart_frame = ttk.Frame(self.main_frame)
        chart_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create figure with appropriate size
        self.fig = Figure(figsize=(6, 7), dpi=80)
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def on_interval_change(self, event=None):
        """Handle interval dropdown change (Column 1 only)"""
        new_interval = self.interval_var.get()
        if new_interval != self.interval:
            self.logger.info(f"Interval changed from {self.interval} to {new_interval}")
            self.interval = new_interval
            self.refresh_data()

    def on_indicator_toggle(self, indicator_name: str):
        """Handle indicator checkbox toggle with debouncing"""
        # Cancel previous timer if exists
        if self.redraw_timer:
            self.parent.after_cancel(self.redraw_timer)

        # Schedule redraw after debounce delay
        self.redraw_timer = self.parent.after(self.debounce_delay, self._redraw_chart)

    def refresh_data(self):
        """Fetch new data and redraw chart"""
        try:
            self.logger.info(f"Refreshing data for {self.interval}")

            # Fetch data from DataManager
            self.df = self.data_manager.fetch_data(self.interval)

            if self.df is None or self.df.empty:
                self.logger.warning(f"No data available for {self.interval}")
                self.show_error_message("데이터 없음")
                return False

            # Calculate enabled indicators
            self._calculate_indicators()

            # Redraw chart
            self._redraw_chart()

            return True

        except Exception as e:
            self.logger.error(f"Error refreshing data: {e}")
            import traceback
            traceback.print_exc()
            self.show_error_message(f"오류: {str(e)}")
            return False

    def _calculate_indicators(self):
        """Calculate all enabled indicators"""
        if self.df is None or self.df.empty:
            return

        # Get config for this interval from strategy config
        from config import STRATEGY_CONFIG
        interval_key = self.interval
        interval_config = STRATEGY_CONFIG.get('interval_presets', {}).get(interval_key, {})

        # Use default config as fallback
        config = {**STRATEGY_CONFIG, **interval_config}

        # Calculate indicators lazily (only enabled ones will be used)
        self.indicators = {}

        # MA
        if self.indicator_vars['ma'].get():
            ma_result = self.indicator_calculator.calculate_ma(self.df, config)
            if ma_result:
                self.indicators['ma'] = ma_result

        # RSI
        if self.indicator_vars['rsi'].get():
            rsi_result = self.indicator_calculator.calculate_rsi_indicator(self.df, config)
            if rsi_result is not None:
                self.indicators['rsi'] = rsi_result

        # BB
        if self.indicator_vars['bb'].get():
            bb_result = self.indicator_calculator.calculate_bb(self.df, config)
            if bb_result:
                self.indicators['bb'] = bb_result

        # MACD
        if self.indicator_vars['macd'].get():
            macd_result = self.indicator_calculator.calculate_macd_indicator(self.df, config)
            if macd_result:
                self.indicators['macd'] = macd_result

        # Stochastic
        if self.indicator_vars['stochastic'].get():
            stoch_result = self.indicator_calculator.calculate_stoch(self.df, config)
            if stoch_result:
                self.indicators['stochastic'] = stoch_result

        # ATR
        if self.indicator_vars['atr'].get():
            atr_result = self.indicator_calculator.calculate_atr_indicator(self.df, config)
            if atr_result is not None:
                self.indicators['atr'] = atr_result

        # ADX
        if self.indicator_vars['adx'].get():
            adx_result = self.indicator_calculator.calculate_adx_indicator(self.df, config)
            if adx_result is not None:
                self.indicators['adx'] = adx_result

        # Volume (no calculation needed)
        if self.indicator_vars['volume'].get():
            volume_result = self.indicator_calculator.get_volume_data(self.df)
            if volume_result is not None:
                self.indicators['volume'] = volume_result

    def _redraw_chart(self):
        """Redraw the entire chart with enabled indicators"""
        if self.df is None or self.df.empty:
            return

        try:
            # Clear previous chart
            self.fig.clear()

            # Recalculate indicators (only enabled ones)
            self._calculate_indicators()

            # Determine subplot layout
            has_rsi = 'rsi' in self.indicators
            has_macd = 'macd' in self.indicators
            has_volume = 'volume' in self.indicators

            num_subplots = 1 + sum([has_rsi, has_macd, has_volume])

            # Create subplot layout
            if num_subplots == 1:
                ax_main = self.fig.add_subplot(111)
                ax_rsi = None
                ax_macd = None
                ax_volume = None
            elif num_subplots == 2:
                gs = self.fig.add_gridspec(2, 1, height_ratios=[3, 1], hspace=0.1)
                ax_main = self.fig.add_subplot(gs[0])

                if has_rsi:
                    ax_rsi = self.fig.add_subplot(gs[1], sharex=ax_main)
                    ax_macd = None
                    ax_volume = None
                elif has_macd:
                    ax_rsi = None
                    ax_macd = self.fig.add_subplot(gs[1], sharex=ax_main)
                    ax_volume = None
                else:
                    ax_rsi = None
                    ax_macd = None
                    ax_volume = self.fig.add_subplot(gs[1], sharex=ax_main)
            elif num_subplots == 3:
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
            else:  # 4 subplots
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

            # Plot candlesticks (always)
            self._plot_candlesticks(ax_main)

            # Plot main chart overlays
            if 'ma' in self.indicators:
                self._plot_moving_averages(ax_main)

            if 'bb' in self.indicators:
                self._plot_bollinger_bands(ax_main)

            # Plot info box for non-visual indicators
            info_text = self._get_info_text()
            if info_text:
                ax_main.text(0.99, 0.97, info_text,
                           transform=ax_main.transAxes,
                           verticalalignment='top',
                           horizontalalignment='right',
                           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.6),
                           fontsize=7)

            # Plot subplots
            if ax_rsi:
                self._plot_rsi(ax_rsi)
                plt.setp(ax_rsi.get_xticklabels(), visible=False)

            if ax_macd:
                self._plot_macd(ax_macd)
                plt.setp(ax_macd.get_xticklabels(), visible=False)

            if ax_volume:
                self._plot_volume(ax_volume)

            # Chart styling
            ax_main.set_title(f"{self.data_manager.coin_symbol} ({self.interval})",
                            fontsize=10, fontweight='bold', pad=10)
            ax_main.set_ylabel('가격 (KRW)', fontsize=8)
            ax_main.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax_main.tick_params(axis='both', labelsize=7)

            # Hide x-axis labels on main chart if subplots exist
            if num_subplots > 1:
                plt.setp(ax_main.get_xticklabels(), visible=False)
            else:
                ax_main.set_xlabel('시간', fontsize=8)

            # Show legend if any overlays
            handles, labels = ax_main.get_legend_handles_labels()
            if labels:
                ax_main.legend(loc='upper left', fontsize=7)

            # x-axis label on bottom subplot
            bottom_ax = ax_volume if ax_volume else (ax_macd if ax_macd else (ax_rsi if ax_rsi else ax_main))
            bottom_ax.set_xlabel('시간', fontsize=8)
            bottom_ax.tick_params(axis='x', rotation=45, labelsize=7)
            bottom_ax.xaxis.set_major_locator(plt.MaxNLocator(8))

            # Tight layout
            self.fig.tight_layout(pad=1.0)

            self.canvas.draw()

        except Exception as e:
            self.logger.error(f"Chart redraw error: {e}")
            import traceback
            traceback.print_exc()

    def _plot_candlesticks(self, ax):
        """Plot candlestick chart"""
        width = 0.6

        for idx, (timestamp, row) in enumerate(self.df.iterrows()):
            open_price = row['open']
            high_price = row['high']
            low_price = row['low']
            close_price = row['close']

            # Color based on direction
            if close_price >= open_price:
                color = 'red'
                body_color = 'red'
                edge_color = 'darkred'
            else:
                color = 'blue'
                body_color = 'blue'
                edge_color = 'darkblue'

            # Wick (high-low line)
            ax.plot([idx, idx], [low_price, high_price],
                   color=color, linewidth=0.8, solid_capstyle='round')

            # Body (open-close box)
            height = abs(close_price - open_price)
            bottom = min(open_price, close_price)

            rect = Rectangle((idx - width/2, bottom), width, height,
                           facecolor=body_color, edgecolor=edge_color,
                           linewidth=0.8, alpha=0.8)
            ax.add_patch(rect)

        # x-axis setup
        ax.set_xlim(-1, len(self.df))

        step = max(1, len(self.df) // 8)
        tick_positions = list(range(0, len(self.df), step))
        tick_labels = [self.df.index[i].strftime('%m/%d %H:%M')
                      for i in tick_positions if i < len(self.df)]

        ax.set_xticks(tick_positions)
        ax.set_xticklabels(tick_labels, fontsize=7)

        # y-axis setup
        price_min = self.df['low'].min()
        price_max = self.df['high'].max()
        price_range = price_max - price_min
        ax.set_ylim(price_min - price_range * 0.05,
                   price_max + price_range * 0.05)

        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))

    def _plot_moving_averages(self, ax):
        """Plot MA lines"""
        ma_data = self.indicators.get('ma')
        if not ma_data:
            return

        x = list(range(len(self.df)))
        ax.plot(x, ma_data['ma_short'], label='MA(short)',
               color='orange', linewidth=1.2, alpha=0.9)
        ax.plot(x, ma_data['ma_long'], label='MA(long)',
               color='purple', linewidth=1.2, alpha=0.9)

    def _plot_bollinger_bands(self, ax):
        """Plot Bollinger Bands"""
        bb_data = self.indicators.get('bb')
        if not bb_data:
            return

        x = list(range(len(self.df)))
        ax.plot(x, bb_data['upper'], color='gray', linewidth=0.8,
               alpha=0.6, linestyle='--', label='BB')
        ax.plot(x, bb_data['lower'], color='gray', linewidth=0.8,
               alpha=0.6, linestyle='--')
        ax.fill_between(x, bb_data['upper'], bb_data['lower'],
                        alpha=0.08, color='gray')

    def _plot_rsi(self, ax):
        """Plot RSI indicator"""
        rsi_data = self.indicators.get('rsi')
        if rsi_data is None:
            return

        x = list(range(len(self.df)))
        ax.plot(x, rsi_data, label='RSI', color='purple', linewidth=1.2)

        # Overbought/oversold lines
        ax.axhline(y=70, color='red', linestyle='--', alpha=0.5, linewidth=0.8)
        ax.axhline(y=30, color='blue', linestyle='--', alpha=0.5, linewidth=0.8)
        ax.axhline(y=50, color='gray', linestyle=':', alpha=0.3, linewidth=0.6)

        ax.fill_between(x, 70, 100, alpha=0.08, color='red')
        ax.fill_between(x, 0, 30, alpha=0.08, color='blue')

        ax.set_ylabel('RSI', fontsize=8)
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.legend(loc='upper left', fontsize=7)
        ax.tick_params(axis='both', labelsize=7)

    def _plot_macd(self, ax):
        """Plot MACD indicator"""
        macd_data = self.indicators.get('macd')
        if not macd_data:
            return

        x = list(range(len(self.df)))

        ax.plot(x, macd_data['macd_line'], label='MACD', color='blue', linewidth=1.0)
        ax.plot(x, macd_data['signal_line'], label='Signal', color='red',
               linestyle='--', linewidth=1.0)

        # Histogram
        colors = ['green' if v >= 0 else 'red' for v in macd_data['histogram']]
        ax.bar(x, macd_data['histogram'], label='Histogram',
              color=colors, alpha=0.35, width=0.7)

        ax.axhline(y=0, color='gray', linestyle='-', alpha=0.5, linewidth=0.8)

        ax.set_ylabel('MACD', fontsize=8)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.legend(loc='upper left', fontsize=7)
        ax.tick_params(axis='both', labelsize=7)

    def _plot_volume(self, ax):
        """Plot volume bars"""
        volume_data = self.indicators.get('volume')
        if volume_data is None:
            return

        x = list(range(len(self.df)))

        colors = []
        for _, row in self.df.iterrows():
            if row['close'] >= row['open']:
                colors.append('red')
            else:
                colors.append('blue')

        ax.bar(x, volume_data, color=colors, alpha=0.5, width=0.7)

        ax.set_ylabel('거래량', fontsize=8)
        ax.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x:,.0f}'))
        ax.tick_params(axis='both', labelsize=7)

    def _get_info_text(self) -> str:
        """Get info text for non-visual indicators"""
        lines = []

        # Stochastic
        if 'stochastic' in self.indicators:
            stoch = self.indicators['stochastic']
            k = stoch['k'].iloc[-1]
            d = stoch['d'].iloc[-1]
            lines.append(f"Stoch: K={k:.1f}, D={d:.1f}")

        # ATR
        if 'atr' in self.indicators:
            atr = self.indicators['atr'].iloc[-1]
            atr_pct = (atr / self.df['close'].iloc[-1]) * 100
            lines.append(f"ATR: {atr:,.0f} ({atr_pct:.2f}%)")

        # ADX
        if 'adx' in self.indicators:
            adx = self.indicators['adx'].iloc[-1]
            trend = "강함" if adx > 25 else "약함"
            lines.append(f"ADX: {adx:.1f} ({trend})")

        return '\n'.join(lines) if lines else ""

    def show_error_message(self, message: str):
        """Display error message on chart"""
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.text(0.5, 0.5, message,
               ha='center', va='center', fontsize=12, color='red')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        self.canvas.draw()

    def cleanup(self):
        """Cleanup resources"""
        if self.fig:
            plt.close(self.fig)


# Example usage
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    from data_manager import DataManager
    from indicator_calculator import IndicatorCalculator

    root = tk.Tk()
    root.title("ChartColumn Test")
    root.geometry("600x800")

    # Create managers
    data_mgr = DataManager('BTC', cache_ttl_seconds=15)
    indicator_calc = IndicatorCalculator()

    # Create chart column
    column = ChartColumn(
        parent=root,
        interval='1h',
        data_manager=data_mgr,
        indicator_calculator=indicator_calc,
        has_dropdown=True,
        column_label="테스트 차트"
    )

    column.main_frame.pack(fill=tk.BOTH, expand=True)

    root.mainloop()
