#!/usr/bin/env python3
"""
MultiTimeframeChartTab - Container for 3-column chart display
Manages 3 ChartColumn instances with synchronized refresh
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional
import logging
from datetime import datetime

from lib.gui.data_manager import DataManager
from lib.gui.indicator_calculator import IndicatorCalculator
from lib.gui.components.chart_column import ChartColumn


class MultiTimeframeChartTab:
    """
    Multi-timeframe chart tab with 3 columns:
    - Column 1: User-selectable interval (dropdown)
    - Column 2: Fixed 4-hour interval
    - Column 3: Fixed 24-hour (daily) interval
    """

    def __init__(self, parent, coin_symbol: str, api_instance=None, config: dict = None):
        """
        Initialize MultiTimeframeChartTab

        Args:
            parent: Parent notebook widget
            coin_symbol: Cryptocurrency symbol (e.g., 'BTC')
            api_instance: API instance (not used, kept for compatibility)
            config: Configuration dictionary (optional)
        """
        self.parent = parent
        self.coin_symbol = coin_symbol
        self.config = config or {}
        self.logger = logging.getLogger(__name__)

        # Load multi-chart config
        from config import STRATEGY_CONFIG
        self.multi_config = STRATEGY_CONFIG.get('multi_chart_config', {})

        # Timing settings
        self.refresh_interval = self.multi_config.get('refresh_interval_seconds', 15) * 1000  # ms
        self.cache_ttl = self.multi_config.get('cache_ttl_seconds', 15)
        self.rate_limit = self.multi_config.get('api_rate_limit_seconds', 1.0)

        # Create shared managers
        self.data_manager = DataManager(
            coin_symbol=coin_symbol,
            cache_ttl_seconds=self.cache_ttl,
            rate_limit_seconds=self.rate_limit
        )
        self.indicator_calculator = IndicatorCalculator()

        # Chart columns
        self.column1: Optional[ChartColumn] = None
        self.column2: Optional[ChartColumn] = None
        self.column3: Optional[ChartColumn] = None

        # Refresh timer
        self.refresh_timer = None
        self.is_running = True

        # Status label
        self.status_label = None

        # Build UI
        self.setup_ui()

        # Initial data load
        self.load_initial_data()

        # Start auto-refresh
        self.start_auto_refresh()

    def setup_ui(self):
        """Build the tab UI with 3-column layout"""
        # Main container frame
        self.main_frame = ttk.Frame(self.parent)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Top control bar
        self.create_control_bar()

        # 3-column grid container
        chart_container = ttk.Frame(self.main_frame)
        chart_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Configure grid weights (equal widths)
        chart_container.columnconfigure(0, weight=1)
        chart_container.columnconfigure(1, weight=1)
        chart_container.columnconfigure(2, weight=1)
        chart_container.rowconfigure(0, weight=1)

        # Get default interval for column 1
        default_interval = self.multi_config.get('default_column1_interval', '1h')

        # Create 3 chart columns
        self.column1 = ChartColumn(
            parent=chart_container,
            interval=default_interval,
            data_manager=self.data_manager,
            indicator_calculator=self.indicator_calculator,
            has_dropdown=True,
            column_label="가변 타임프레임"
        )
        self.column1.main_frame.grid(row=0, column=0, sticky='nsew')

        self.column2 = ChartColumn(
            parent=chart_container,
            interval='4h',
            data_manager=self.data_manager,
            indicator_calculator=self.indicator_calculator,
            has_dropdown=False,
            column_label="4시간봉"
        )
        self.column2.main_frame.grid(row=0, column=1, sticky='nsew')

        self.column3 = ChartColumn(
            parent=chart_container,
            interval='24h',
            data_manager=self.data_manager,
            indicator_calculator=self.indicator_calculator,
            has_dropdown=False,
            column_label="일봉 (24시간)"
        )
        self.column3.main_frame.grid(row=0, column=2, sticky='nsew')

        # Bottom status bar
        self.create_status_bar()

        self.logger.info(f"MultiTimeframeChartTab initialized for {self.coin_symbol}")

    def create_control_bar(self):
        """Create top control bar with manual refresh button"""
        control_frame = ttk.Frame(self.main_frame)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        # Title
        ttk.Label(control_frame, text=f"📊 멀티 타임프레임 차트 - {self.coin_symbol}",
                 font=('Arial', 12, 'bold')).pack(side=tk.LEFT, padx=5)

        # Manual refresh button
        ttk.Button(control_frame, text="🔄 전체 새로고침",
                  command=self.manual_refresh).pack(side=tk.RIGHT, padx=5)

        # Auto-refresh toggle
        self.auto_refresh_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(control_frame, text="자동 새로고침",
                       variable=self.auto_refresh_var,
                       command=self.toggle_auto_refresh).pack(side=tk.RIGHT, padx=5)

    def create_status_bar(self):
        """Create bottom status bar"""
        status_frame = ttk.Frame(self.main_frame)
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        self.status_label = ttk.Label(status_frame, text="초기화 중...",
                                      font=('Arial', 9))
        self.status_label.pack(side=tk.LEFT)

    def load_initial_data(self):
        """Load initial data for all 3 charts"""
        try:
            self.update_status("데이터 로딩 중...")

            # Get intervals from all columns
            intervals = [
                self.column1.interval,
                self.column2.interval,
                self.column3.interval
            ]

            # Fetch all data (with rate limiting handled by DataManager)
            self.logger.info(f"Loading initial data for intervals: {intervals}")
            data = self.data_manager.fetch_multiple_intervals(intervals)

            # Check results
            success_count = len(data)
            if success_count > 0:
                self.update_status(f"초기 데이터 로드 완료 ({success_count}/3)")
            else:
                self.update_status("데이터 로드 실패")

        except Exception as e:
            self.logger.error(f"Initial data load error: {e}")
            self.update_status(f"오류: {str(e)}")

    def start_auto_refresh(self):
        """Start automatic refresh timer"""
        if not self.is_running:
            return

        if self.auto_refresh_var.get():
            self.refresh_timer = self.main_frame.after(self.refresh_interval, self.auto_refresh)
            self.logger.debug(f"Auto-refresh scheduled in {self.refresh_interval/1000}s")

    def auto_refresh(self):
        """Periodic auto-refresh callback"""
        if not self.is_running or not self.auto_refresh_var.get():
            return

        try:
            self.logger.info("Auto-refreshing charts...")
            self.update_status("자동 새로고침 중...")

            # Get active intervals
            intervals = [
                self.column1.interval,
                self.column2.interval,
                self.column3.interval
            ]

            # Check which intervals need refresh
            refreshed = self.data_manager.refresh_intervals(intervals)

            if refreshed:
                # Update only refreshed columns
                if self.column1.interval in refreshed:
                    self.column1.refresh_data()

                if self.column2.interval in refreshed:
                    self.column2.refresh_data()

                if self.column3.interval in refreshed:
                    self.column3.refresh_data()

                current_time = datetime.now().strftime('%H:%M:%S')
                self.update_status(f"마지막 새로고침: {current_time} ({len(refreshed)}개 업데이트)")
            else:
                current_time = datetime.now().strftime('%H:%M:%S')
                self.update_status(f"캐시 유효 (확인: {current_time})")

        except Exception as e:
            self.logger.error(f"Auto-refresh error: {e}")
            self.update_status(f"새로고침 오류: {str(e)}")

        finally:
            # Schedule next refresh
            self.start_auto_refresh()

    def manual_refresh(self):
        """Manual refresh all charts (force refresh)"""
        try:
            self.update_status("수동 새로고침 중...")

            # Force refresh all columns
            self.column1.refresh_data()
            self.column2.refresh_data()
            self.column3.refresh_data()

            current_time = datetime.now().strftime('%H:%M:%S')
            self.update_status(f"수동 새로고침 완료: {current_time}")

            self.logger.info("Manual refresh completed")

        except Exception as e:
            self.logger.error(f"Manual refresh error: {e}")
            self.update_status(f"새로고침 오류: {str(e)}")

    def toggle_auto_refresh(self):
        """Toggle auto-refresh on/off"""
        if self.auto_refresh_var.get():
            self.logger.info("Auto-refresh enabled")
            self.start_auto_refresh()
        else:
            self.logger.info("Auto-refresh disabled")
            if self.refresh_timer:
                self.main_frame.after_cancel(self.refresh_timer)
                self.refresh_timer = None

    def update_status(self, message: str):
        """Update status bar text"""
        if self.status_label:
            self.status_label.config(text=message)

    def stop(self):
        """Stop auto-refresh and cleanup"""
        self.logger.info("Stopping MultiTimeframeChartTab")
        self.is_running = False

        if self.refresh_timer:
            self.main_frame.after_cancel(self.refresh_timer)
            self.refresh_timer = None

        # Cleanup columns
        if self.column1:
            self.column1.cleanup()
        if self.column2:
            self.column2.cleanup()
        if self.column3:
            self.column3.cleanup()

    def get_cache_info(self) -> str:
        """Get cache status information for debugging"""
        info = self.data_manager.get_cache_info()
        lines = ["Cache Status:"]
        for interval, stats in info.items():
            lines.append(f"  {interval}: {stats['candle_count']} candles, "
                        f"age={stats['age_seconds']:.1f}s, "
                        f"fresh={stats['is_fresh']}")
        return '\n'.join(lines)


# Example usage and testing
if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)

    root = tk.Tk()
    root.title("MultiTimeframeChartTab Test")
    root.geometry("1600x900")

    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True)

    # Create multi-chart tab
    multi_tab = MultiTimeframeChartTab(
        parent=notebook,
        coin_symbol='BTC'
    )

    notebook.add(multi_tab.main_frame, text="📊 멀티 타임프레임")

    def on_closing():
        multi_tab.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
