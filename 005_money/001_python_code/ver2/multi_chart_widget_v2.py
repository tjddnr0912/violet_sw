"""
Multi-Timeframe Chart Widget for Version 2 Strategy

Displays 4 synchronized charts in 2x2 grid layout:
- Daily (24h): Regime filter with EMA 50/200
- 12H: Context chart with basic price action
- 4H: Primary execution timeframe with full indicators
- 1H: Detailed short-term context

Each chart shows relevant indicators for v2's dual-timeframe strategy.
"""

import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import sys
import os
import platform

# Add lib path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.api.bithumb_api import get_candlestick
from ver2 import indicators_v2

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


class MultiChartWidgetV2:
    """
    Multi-timeframe chart widget for v2 strategy.

    Layout (2x2 grid):
    +------------------+------------------+
    |   24H (Daily)    |    12H          |
    |  Regime Filter   |   Context       |
    +------------------+------------------+
    |   4H (Primary)   |    1H           |
    |  Execution TF    |   Context       |
    +------------------+------------------+
    """

    def __init__(self, parent, config: Dict[str, Any]):
        self.parent = parent
        self.config = config
        self.coin_symbol = 'BTC'
        self.logger = logging.getLogger(__name__)

        # Chart data cache
        self.chart_data = {
            '24h': None,
            '12h': None,
            '4h': None,
            '1h': None
        }

        # Auto-refresh state
        self.auto_refresh_enabled = True
        self.refresh_timer = None
        self.refresh_interval = 15000  # 15 seconds

        # Chart components
        self.charts = {}  # Dictionary to store individual chart objects
        self.canvas = None

        self.setup_ui()
        self.load_all_data()
        self.start_auto_refresh()

    def setup_ui(self):
        """Setup UI with control bar and 2x2 chart grid"""
        # Main container
        main_frame = ttk.Frame(self.parent)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Control bar
        self.create_control_bar(main_frame)

        # Chart grid container
        chart_container = ttk.Frame(main_frame)
        chart_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Configure grid weights (equal sizes)
        chart_container.columnconfigure(0, weight=1)
        chart_container.columnconfigure(1, weight=1)
        chart_container.rowconfigure(0, weight=1)
        chart_container.rowconfigure(1, weight=1)

        # Create matplotlib figure with 2x2 subplots
        self.fig = Figure(figsize=(14, 10), dpi=100, facecolor='white')

        # Create 2x2 grid of subplots
        self.axes = {
            '24h': self.fig.add_subplot(2, 2, 1),  # Top-left
            '12h': self.fig.add_subplot(2, 2, 2),  # Top-right
            '4h': self.fig.add_subplot(2, 2, 3),   # Bottom-left
            '1h': self.fig.add_subplot(2, 2, 4)    # Bottom-right
        }

        # Adjust subplot spacing
        self.fig.subplots_adjust(left=0.06, right=0.98, top=0.96, bottom=0.05,
                                 hspace=0.25, wspace=0.15)

        # Create canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_container)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Status bar
        self.create_status_bar(main_frame)

        self.logger.info("MultiChartWidgetV2 UI initialized")

    def create_control_bar(self, parent):
        """Create top control bar"""
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        # Title
        ttk.Label(control_frame, text=f"📊 멀티 타임프레임 차트 - {self.coin_symbol}",
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT, padx=5)

        # Manual refresh button
        ttk.Button(control_frame, text="🔄 전체 새로고침",
                  command=self.manual_refresh).pack(side=tk.RIGHT, padx=5)

        # Auto-refresh toggle
        self.auto_refresh_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="자동 새로고침 (15초)",
                       variable=self.auto_refresh_var,
                       command=self.toggle_auto_refresh).pack(side=tk.RIGHT, padx=5)

    def create_status_bar(self, parent):
        """Create bottom status bar"""
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        self.status_label = ttk.Label(status_frame, text="초기화 중...",
                                      font=('Arial', 9))
        self.status_label.pack(side=tk.LEFT)

    def load_all_data(self):
        """Load candlestick data for all timeframes"""
        try:
            self.update_status("데이터 로딩 중...")

            # Fetch data for all timeframes
            timeframes = ['24h', '12h', '4h', '1h']
            success_count = 0

            for tf in timeframes:
                try:
                    # Fetch candlestick data
                    data = get_candlestick(self.coin_symbol, tf)

                    if data is not None and len(data) > 0:
                        # Convert to DataFrame
                        df = pd.DataFrame(data)

                        # Ensure proper column names
                        if 'timestamp' in df.columns:
                            df['date'] = pd.to_datetime(df['timestamp'], unit='ms')

                        # Calculate indicators
                        self.calculate_indicators(df, tf)

                        self.chart_data[tf] = df
                        success_count += 1
                        self.logger.info(f"Loaded {len(df)} candles for {tf}")

                except Exception as e:
                    self.logger.error(f"Error loading {tf} data: {e}")

            # Draw all charts
            self.draw_all_charts()

            self.update_status(f"데이터 로드 완료 ({success_count}/4 타임프레임)")

        except Exception as e:
            self.logger.error(f"Error in load_all_data: {e}")
            self.update_status(f"오류: {str(e)}")

    def calculate_indicators(self, df: pd.DataFrame, timeframe: str):
        """Calculate indicators for a specific timeframe"""
        try:
            # Get indicator config from v2
            indicator_config = self.config.get('INDICATOR_CONFIG', {})
            regime_config = self.config.get('REGIME_FILTER_CONFIG', {})

            # For Daily (24h) - Calculate EMA 50/200
            if timeframe == '24h':
                ema_fast = regime_config.get('ema_fast', 50)
                ema_slow = regime_config.get('ema_slow', 200)

                df['ema50'] = indicators_v2.calculate_ema(df['close'], ema_fast)
                df['ema200'] = indicators_v2.calculate_ema(df['close'], ema_slow)

            # For 4H (Primary) - Calculate all entry indicators
            elif timeframe == '4h':
                # Bollinger Bands
                bb_result = indicators_v2.calculate_bollinger_bands(
                    df['close'],
                    period=indicator_config.get('bb_period', 20),
                    std_dev=indicator_config.get('bb_std', 2.0)
                )
                df['bb_upper'] = bb_result['upper']
                df['bb_middle'] = bb_result['middle']
                df['bb_lower'] = bb_result['lower']

                # RSI
                df['rsi'] = indicators_v2.calculate_rsi(
                    df['close'],
                    period=indicator_config.get('rsi_period', 14)
                )

                # Stochastic RSI
                stoch_result = indicators_v2.calculate_stochastic_rsi(
                    df['close'],
                    rsi_period=indicator_config.get('stoch_rsi_period', 14),
                    stoch_period=indicator_config.get('stoch_period', 14),
                    k_smooth=indicator_config.get('stoch_k_smooth', 3),
                    d_smooth=indicator_config.get('stoch_d_smooth', 3)
                )
                df['stoch_k'] = stoch_result['k']
                df['stoch_d'] = stoch_result['d']

                # ATR
                df['atr'] = indicators_v2.calculate_atr(
                    df['high'], df['low'], df['close'],
                    period=indicator_config.get('atr_period', 14)
                )

            # For 12H and 1H - Basic indicators
            else:
                # Simple Moving Averages for context
                df['ma20'] = df['close'].rolling(window=20).mean()
                df['ma50'] = df['close'].rolling(window=50).mean()

                # Volume average
                df['volume_ma'] = df['volume'].rolling(window=20).mean()

        except Exception as e:
            self.logger.error(f"Error calculating indicators for {timeframe}: {e}")

    def draw_all_charts(self):
        """Draw all 4 charts"""
        try:
            # Clear all axes
            for ax in self.axes.values():
                ax.clear()

            # Draw each timeframe
            self.draw_daily_chart(self.axes['24h'], self.chart_data['24h'])
            self.draw_context_chart(self.axes['12h'], self.chart_data['12h'], '12H')
            self.draw_execution_chart(self.axes['4h'], self.chart_data['4h'])
            self.draw_context_chart(self.axes['1h'], self.chart_data['1h'], '1H')

            # Redraw canvas
            self.canvas.draw()

        except Exception as e:
            self.logger.error(f"Error drawing charts: {e}")

    def draw_daily_chart(self, ax, df: Optional[pd.DataFrame]):
        """Draw Daily (24h) chart with EMA 50/200 regime filter"""
        if df is None or len(df) == 0:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center', transform=ax.transAxes)
            ax.set_title("24H (Daily) - Regime Filter", fontweight='bold', fontsize=11)
            return

        try:
            # Limit to last 100 candles for readability
            df_plot = df.tail(100).copy()

            # Draw candlesticks
            self.draw_candlesticks(ax, df_plot)

            # Draw EMA 50/200
            if 'ema50' in df_plot.columns:
                ax.plot(df_plot.index, df_plot['ema50'],
                       color='orange', linewidth=2, label='EMA 50', alpha=0.8)

            if 'ema200' in df_plot.columns:
                ax.plot(df_plot.index, df_plot['ema200'],
                       color='purple', linewidth=2, label='EMA 200', alpha=0.8)

            # Determine regime
            last_ema50 = df_plot['ema50'].iloc[-1] if 'ema50' in df_plot.columns else 0
            last_ema200 = df_plot['ema200'].iloc[-1] if 'ema200' in df_plot.columns else 0

            if last_ema50 > last_ema200:
                regime = "BULLISH ✓"
                regime_color = 'green'
            else:
                regime = "BEARISH"
                regime_color = 'red'

            # Title with regime status
            ax.set_title(f"24H (Daily) - Regime Filter | 체제: {regime}",
                        fontweight='bold', fontsize=11, color=regime_color)

            # Only show legend if there are labeled elements
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc='upper left', fontsize=8)

            ax.grid(True, alpha=0.3)
            ax.set_ylabel('Price (KRW)', fontsize=9)

        except Exception as e:
            self.logger.error(f"Error drawing daily chart: {e}")

    def draw_execution_chart(self, ax, df: Optional[pd.DataFrame]):
        """Draw 4H execution chart with full indicators"""
        if df is None or len(df) == 0:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center', transform=ax.transAxes)
            ax.set_title("4H (Primary) - Execution Timeframe", fontweight='bold', fontsize=11)
            return

        try:
            # Limit to last 100 candles
            df_plot = df.tail(100).copy()

            # Draw candlesticks
            self.draw_candlesticks(ax, df_plot)

            # Draw Bollinger Bands
            if all(col in df_plot.columns for col in ['bb_upper', 'bb_middle', 'bb_lower']):
                ax.plot(df_plot.index, df_plot['bb_upper'],
                       color='gray', linewidth=1, linestyle='--', alpha=0.5)
                ax.plot(df_plot.index, df_plot['bb_middle'],
                       color='blue', linewidth=1.5, label='BB Mid', alpha=0.7)
                ax.plot(df_plot.index, df_plot['bb_lower'],
                       color='gray', linewidth=1, linestyle='--', alpha=0.5)

                # Fill between bands
                ax.fill_between(df_plot.index, df_plot['bb_upper'], df_plot['bb_lower'],
                               alpha=0.1, color='gray')

            # Add indicator info box
            info_text = self.build_indicator_info(df_plot)
            ax.text(0.02, 0.98, info_text, transform=ax.transAxes,
                   verticalalignment='top', fontsize=8,
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

            ax.set_title("4H (Primary) - Execution Timeframe", fontweight='bold', fontsize=11)

            # Only show legend if there are labeled elements
            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(loc='upper left', fontsize=8)

            ax.grid(True, alpha=0.3)
            ax.set_ylabel('Price (KRW)', fontsize=9)

        except Exception as e:
            self.logger.error(f"Error drawing execution chart: {e}")

    def draw_context_chart(self, ax, df: Optional[pd.DataFrame], label: str):
        """Draw context chart (12H or 1H) with basic indicators"""
        if df is None or len(df) == 0:
            ax.text(0.5, 0.5, 'No Data', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f"{label} - Context", fontweight='bold', fontsize=11)
            return

        try:
            # Limit to last 100 candles
            df_plot = df.tail(100).copy()

            # Draw candlesticks
            self.draw_candlesticks(ax, df_plot)

            # Draw moving averages if available
            if 'ma20' in df_plot.columns:
                ax.plot(df_plot.index, df_plot['ma20'],
                       color='orange', linewidth=1.5, label='MA 20', alpha=0.7)

            if 'ma50' in df_plot.columns:
                ax.plot(df_plot.index, df_plot['ma50'],
                       color='purple', linewidth=1.5, label='MA 50', alpha=0.7)

            ax.set_title(f"{label} - Context", fontweight='bold', fontsize=11)
            ax.legend(loc='upper left', fontsize=8)
            ax.grid(True, alpha=0.3)
            ax.set_ylabel('Price (KRW)', fontsize=9)

        except Exception as e:
            self.logger.error(f"Error drawing {label} chart: {e}")

    def draw_candlesticks(self, ax, df: pd.DataFrame):
        """Draw candlestick chart on given axis"""
        try:
            # Prepare data
            opens = df['open'].values
            highs = df['high'].values
            lows = df['low'].values
            closes = df['close'].values

            # Draw candlesticks
            for i in range(len(df)):
                # Determine color
                color = 'red' if closes[i] >= opens[i] else 'blue'

                # Draw high-low line
                ax.plot([i, i], [lows[i], highs[i]], color=color, linewidth=0.8, alpha=0.7)

                # Draw body rectangle
                body_height = abs(closes[i] - opens[i])
                body_bottom = min(opens[i], closes[i])

                rect = Rectangle((i - 0.3, body_bottom), 0.6, body_height,
                                facecolor=color, edgecolor=color, alpha=0.6)
                ax.add_patch(rect)

            # Set x-axis limits
            ax.set_xlim(-1, len(df))

            # Format x-axis with sparse date labels
            if len(df) >= 10:
                # Show ~8 date labels
                tick_positions = np.linspace(0, len(df) - 1, 8, dtype=int)
                ax.set_xticks(tick_positions)

                # Format date labels
                if 'date' in df.columns:
                    dates = df['date'].iloc[tick_positions]
                    date_labels = [d.strftime('%m-%d %H:%M') for d in dates]
                    ax.set_xticklabels(date_labels, rotation=45, ha='right', fontsize=8)

        except Exception as e:
            self.logger.error(f"Error drawing candlesticks: {e}")

    def build_indicator_info(self, df: pd.DataFrame) -> str:
        """Build indicator info text for 4H chart"""
        try:
            info_lines = []

            # RSI
            if 'rsi' in df.columns:
                rsi_val = df['rsi'].iloc[-1]
                info_lines.append(f"RSI: {rsi_val:.1f}")

            # Stochastic RSI
            if 'stoch_k' in df.columns and 'stoch_d' in df.columns:
                k_val = df['stoch_k'].iloc[-1]
                d_val = df['stoch_d'].iloc[-1]
                info_lines.append(f"Stoch: K={k_val:.1f}, D={d_val:.1f}")

            # ATR
            if 'atr' in df.columns:
                atr_val = df['atr'].iloc[-1]
                info_lines.append(f"ATR: {atr_val:,.0f}")

            return '\n'.join(info_lines) if info_lines else "No Indicators"

        except Exception as e:
            return "Info Error"

    def manual_refresh(self):
        """Manual refresh all charts"""
        try:
            self.update_status("수동 새로고침 중...")
            self.load_all_data()

            current_time = datetime.now().strftime('%H:%M:%S')
            self.update_status(f"수동 새로고침 완료: {current_time}")

            self.logger.info("Manual refresh completed")

        except Exception as e:
            self.logger.error(f"Manual refresh error: {e}")
            self.update_status(f"새로고침 오류: {str(e)}")

    def start_auto_refresh(self):
        """Start automatic refresh timer"""
        if not self.auto_refresh_enabled:
            return

        if self.auto_refresh_var.get():
            self.refresh_timer = self.parent.after(self.refresh_interval, self.auto_refresh)
            self.logger.debug(f"Auto-refresh scheduled in {self.refresh_interval/1000}s")

    def auto_refresh(self):
        """Periodic auto-refresh callback"""
        if not self.auto_refresh_var.get():
            return

        try:
            self.logger.info("Auto-refreshing charts...")
            self.load_all_data()

            current_time = datetime.now().strftime('%H:%M:%S')
            self.update_status(f"마지막 새로고침: {current_time}")

        except Exception as e:
            self.logger.error(f"Auto-refresh error: {e}")
            self.update_status(f"새로고침 오류: {str(e)}")

        finally:
            # Schedule next refresh
            self.start_auto_refresh()

    def toggle_auto_refresh(self):
        """Toggle auto-refresh on/off"""
        if self.auto_refresh_var.get():
            self.logger.info("Auto-refresh enabled")
            self.start_auto_refresh()
        else:
            self.logger.info("Auto-refresh disabled")
            if self.refresh_timer:
                self.parent.after_cancel(self.refresh_timer)
                self.refresh_timer = None

    def update_status(self, message: str):
        """Update status bar text"""
        if self.status_label:
            self.status_label.config(text=message)

    def stop(self):
        """Stop auto-refresh and cleanup"""
        self.logger.info("Stopping MultiChartWidgetV2")
        self.auto_refresh_enabled = False

        if self.refresh_timer:
            self.parent.after_cancel(self.refresh_timer)
            self.refresh_timer = None


# Standalone test
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    # Import v2 config
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from config_v2 import get_version_config

    root = tk.Tk()
    root.title("MultiChartWidgetV2 Test")
    root.geometry("1400x900")

    config = get_version_config()
    widget = MultiChartWidgetV2(root, config)

    def on_closing():
        widget.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
