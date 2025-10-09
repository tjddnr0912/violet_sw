"""
Score Monitoring Widget for Version 2

Tracks ALL score checks (0-4 points) every minute for strategy analysis.
Separate from signal history which only tracks actual entries (3+ points).

Features:
- Real-time score tracking (every 60 seconds)
- Score distribution chart
- Component breakdown
- Regime correlation
- Trend visualization with interactive graph
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
from typing import Dict, Any, List
from collections import deque
import json
import os
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import numpy as np


class ScoreMonitoringWidgetV2:
    """
    Score monitoring widget for tracking ALL score checks.

    Unlike SignalHistoryWidget (which tracks only trades), this widget
    records every score calculation for analysis purposes.
    """

    def __init__(self, parent, config=None, coin_symbol: str = 'BTC'):
        self.parent = parent
        self.score_checks = deque(maxlen=1440)  # 24 hours at 1-minute intervals

        # Store coin symbol for filtering
        self.coin_symbol = coin_symbol

        # Store config reference for dynamic threshold
        if config is None:
            from ver2 import config_v2
            self.config = config_v2.get_version_config()
            self.coin_symbol = self.config['TRADING_CONFIG'].get('symbol', 'BTC')
        else:
            self.config = config

        # Color scheme for scores (same as signal history)
        self.score_colors = {
            4: '#006400',  # Dark green
            3: '#32CD32',  # Light green
            2: '#FFA500',  # Orange
            1: '#FF6347',  # Tomato red
            0: '#DC143C'   # Crimson red
        }

        # Graph window reference
        self.graph_window = None

        # Component visualization toggles (for graph)
        self.show_component_breakdown = False

        self.setup_ui()
        self.load_from_file()  # Auto-load previous session

    def setup_ui(self):
        """Setup score monitoring UI"""
        # Main container
        main_frame = ttk.Frame(self.parent, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # === Statistics Panel ===
        self.stats_frame = ttk.LabelFrame(main_frame, text=f"📊 {self.coin_symbol} 점수 체크 통계 (실시간 모니터링)", padding="10")
        self.stats_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        stats_frame = self.stats_frame  # Alias for existing code

        # Row 1: Overall stats
        stats_row1 = ttk.Frame(stats_frame)
        stats_row1.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(stats_row1, text="총 체크 횟수:").pack(side=tk.LEFT, padx=(0, 5))
        self.total_checks_var = tk.StringVar(value="0")
        ttk.Label(stats_row1, textvariable=self.total_checks_var, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(stats_row1, text="평균 점수:").pack(side=tk.LEFT, padx=(0, 5))
        self.avg_score_var = tk.StringVar(value="0.0/4")
        ttk.Label(stats_row1, textvariable=self.avg_score_var, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(stats_row1, text="진입 가능 (3+):").pack(side=tk.LEFT, padx=(0, 5))
        self.entry_ready_var = tk.StringVar(value="0회 (0%)")
        self.entry_ready_label = ttk.Label(stats_row1, textvariable=self.entry_ready_var, font=('Arial', 10, 'bold'))
        self.entry_ready_label.pack(side=tk.LEFT)

        # Row 2: Score distribution
        stats_row2 = ttk.Frame(stats_frame)
        stats_row2.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 5))

        ttk.Label(stats_row2, text="점수 분포:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        self.score_dist_vars = {}
        for score in [4, 3, 2, 1, 0]:
            frame = ttk.Frame(stats_row2)
            frame.pack(side=tk.LEFT, padx=(0, 15))

            # Score label with color background
            score_label = tk.Label(frame, text=f"{score}/4", width=4,
                                  bg=self.score_colors[score], fg='white',
                                  font=('Arial', 8, 'bold'))
            score_label.pack(side=tk.LEFT, padx=(0, 3))

            # Count
            var = tk.StringVar(value="0")
            self.score_dist_vars[score] = var
            ttk.Label(frame, textvariable=var, font=('Arial', 9)).pack(side=tk.LEFT)

        # Row 3: Component stats
        stats_row3 = ttk.Frame(stats_frame)
        stats_row3.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        ttk.Label(stats_row3, text="구성요소 발생 횟수:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        # BB Touch
        bb_frame = ttk.Frame(stats_row3)
        bb_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(bb_frame, text="BB:", foreground='blue', font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 3))
        self.bb_count_var = tk.StringVar(value="0")
        ttk.Label(bb_frame, textvariable=self.bb_count_var).pack(side=tk.LEFT)

        # RSI Oversold
        rsi_frame = ttk.Frame(stats_row3)
        rsi_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(rsi_frame, text="RSI:", foreground='purple', font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 3))
        self.rsi_count_var = tk.StringVar(value="0")
        ttk.Label(rsi_frame, textvariable=self.rsi_count_var).pack(side=tk.LEFT)

        # Stoch Cross
        stoch_frame = ttk.Frame(stats_row3)
        stoch_frame.pack(side=tk.LEFT)
        ttk.Label(stoch_frame, text="Stoch:", foreground='green', font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 3))
        self.stoch_count_var = tk.StringVar(value="0")
        ttk.Label(stoch_frame, textvariable=self.stoch_count_var).pack(side=tk.LEFT)

        # === Filter Panel ===
        filter_frame = ttk.LabelFrame(main_frame, text="🔍 필터", padding="5")
        filter_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(filter_frame, text="표시 기간:").pack(side=tk.LEFT, padx=(0, 5))
        self.time_filter_var = tk.StringVar(value="1H")
        time_combo = ttk.Combobox(filter_frame, textvariable=self.time_filter_var,
                                  values=['15M', '30M', '1H', '4H', '24H'], width=8, state='readonly')
        time_combo.pack(side=tk.LEFT, padx=(0, 15))
        time_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Label(filter_frame, text="최소 점수:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_score_var = tk.StringVar(value="0")
        score_combo = ttk.Combobox(filter_frame, textvariable=self.filter_score_var,
                                   values=['0', '1', '2', '3', '4'], width=5, state='readonly')
        score_combo.pack(side=tk.LEFT, padx=(0, 15))
        score_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Label(filter_frame, text="Regime:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_regime_var = tk.StringVar(value="ALL")
        regime_combo = ttk.Combobox(filter_frame, textvariable=self.filter_regime_var,
                                    values=['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL'], width=10, state='readonly')
        regime_combo.pack(side=tk.LEFT, padx=(0, 15))
        regime_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Button(filter_frame, text="필터 초기화", command=self.reset_filter).pack(side=tk.LEFT)

        # === Score Check List ===
        list_frame = ttk.LabelFrame(main_frame, text="📋 점수 체크 내역 (최신순)", padding="5")
        list_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # Treeview for score checks
        columns = ('Time', 'Score', 'BB', 'RSI', 'Stoch', 'Regime', 'Price', 'Note')
        self.score_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=20)

        # Column configuration
        self.score_tree.heading('Time', text='시간')
        self.score_tree.heading('Score', text='총점')
        self.score_tree.heading('BB', text='BB')
        self.score_tree.heading('RSI', text='RSI')
        self.score_tree.heading('Stoch', text='Stoch')
        self.score_tree.heading('Regime', text='Regime')
        self.score_tree.heading('Price', text='가격')
        self.score_tree.heading('Note', text='메모')

        self.score_tree.column('Time', width=140, anchor='center')
        self.score_tree.column('Score', width=60, anchor='center')
        self.score_tree.column('BB', width=50, anchor='center')
        self.score_tree.column('RSI', width=50, anchor='center')
        self.score_tree.column('Stoch', width=50, anchor='center')
        self.score_tree.column('Regime', width=90, anchor='center')
        self.score_tree.column('Price', width=100, anchor='e')
        self.score_tree.column('Note', width=200, anchor='w')

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.score_tree.yview)
        self.score_tree.configure(yscrollcommand=scrollbar.set)

        self.score_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Configure tags for color coding
        self.score_tree.tag_configure('score_4', background='#E6FFE6')
        self.score_tree.tag_configure('score_3', background='#F0FFF0')
        self.score_tree.tag_configure('score_2', background='#FFF8DC')
        self.score_tree.tag_configure('score_1', background='#FFE4E1')
        self.score_tree.tag_configure('score_0', background='#FFCCCC')
        self.score_tree.tag_configure('entry_ready', foreground='#006400', font=('Arial', 9, 'bold'))

        # === Control Buttons ===
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(10, 0))

        ttk.Button(button_frame, text="🔄 새로고침", command=self.refresh_display).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="📊 점수 추세 그래프", command=self.show_score_trend).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 CSV 내보내기", command=self.export_to_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🗑️ 기록 삭제", command=self.clear_scores).pack(side=tk.LEFT, padx=5)

    def add_score_check(self, score_data: Dict[str, Any]):
        """
        Add score check to monitoring.

        Args:
            score_data: Dictionary with score check details
                - timestamp: Check time
                - score: Total score (0-4)
                - components: Dict with bb_touch, rsi_oversold, stoch_cross
                - regime: Market regime
                - price: Current price
                - coin: Coin symbol (optional, defaults to widget's current coin)
        """
        timestamp = score_data.get('timestamp', datetime.now())
        score = score_data.get('score', 0)
        components = score_data.get('components', {})
        regime = score_data.get('regime', 'NEUTRAL')
        price = score_data.get('price', 0)
        coin = score_data.get('coin', self.coin_symbol)  # Use widget's coin if not specified

        # Filter: Only add if coin matches current widget coin
        if coin != self.coin_symbol:
            return  # Silently ignore checks from different coins

        # Get dynamic threshold from config
        min_entry_score = self.config['ENTRY_SCORING_CONFIG'].get('min_entry_score', 3)

        # Determine note (dynamic based on config threshold)
        note = ""
        if score >= min_entry_score:
            note = "✅ 진입 가능"
        elif score == min_entry_score - 1:
            note = f"⚠️ {min_entry_score - score}점 부족"
        elif score > 0:
            note = f"{min_entry_score - score}점 부족"
        else:
            note = "-"

        # Determine tags (dynamic threshold)
        tags = [f'score_{score}']
        if score >= min_entry_score:
            tags.append('entry_ready')

        # Add to tree
        values = (
            timestamp.strftime('%Y-%m-%d %H:%M'),
            f'{score}/4',
            f"+{components.get('bb_touch', 0)}" if components.get('bb_touch', 0) > 0 else "-",
            f"+{components.get('rsi_oversold', 0)}" if components.get('rsi_oversold', 0) > 0 else "-",
            f"+{components.get('stoch_cross', 0)}" if components.get('stoch_cross', 0) > 0 else "-",
            regime,
            f'{price:,.0f}',
            note
        )

        item_id = self.score_tree.insert('', 0, values=values, tags=tuple(tags))

        # Store check data
        check_record = {
            'id': item_id,
            'timestamp': timestamp,
            'score': score,
            'components': components,
            'regime': regime,
            'price': price,
            'coin': coin  # Store coin symbol
        }
        self.score_checks.append(check_record)

        self.update_statistics()
        self.save_to_file()  # Auto-save

    def update_statistics(self):
        """Update statistics display"""
        if not self.score_checks:
            self.total_checks_var.set("0")
            self.avg_score_var.set("0.0/4")
            self.entry_ready_var.set("0회 (0%)")
            for score in [4, 3, 2, 1, 0]:
                self.score_dist_vars[score].set("0")
            self.bb_count_var.set("0")
            self.rsi_count_var.set("0")
            self.stoch_count_var.set("0")
            return

        # Total checks
        total = len(self.score_checks)
        self.total_checks_var.set(str(total))

        # Average score
        avg_score = sum(c['score'] for c in self.score_checks) / total
        self.avg_score_var.set(f"{avg_score:.2f}/4")

        # Entry-ready count (dynamic threshold from config)
        min_entry_score = self.config['ENTRY_SCORING_CONFIG'].get('min_entry_score', 3)
        entry_ready = sum(1 for c in self.score_checks if c['score'] >= min_entry_score)
        entry_ready_pct = (entry_ready / total) * 100
        self.entry_ready_var.set(f"{entry_ready}회 ({entry_ready_pct:.1f}%)")

        # Color code entry ready
        if entry_ready_pct >= 10:
            self.entry_ready_label.config(foreground='green')
        elif entry_ready_pct >= 5:
            self.entry_ready_label.config(foreground='orange')
        else:
            self.entry_ready_label.config(foreground='red')

        # Score distribution
        score_counts = {4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
        for check in self.score_checks:
            score = check['score']
            if score in score_counts:
                score_counts[score] += 1

        for score, count in score_counts.items():
            self.score_dist_vars[score].set(str(count))

        # Component counts
        bb_count = sum(1 for c in self.score_checks if c['components'].get('bb_touch', 0) > 0)
        rsi_count = sum(1 for c in self.score_checks if c['components'].get('rsi_oversold', 0) > 0)
        stoch_count = sum(1 for c in self.score_checks if c['components'].get('stoch_cross', 0) > 0)

        self.bb_count_var.set(str(bb_count))
        self.rsi_count_var.set(str(rsi_count))
        self.stoch_count_var.set(str(stoch_count))

    def apply_filter(self):
        """Apply filter settings"""
        self.refresh_display()

        # Update graph if window is open
        if self.graph_window is not None and self.graph_window.winfo_exists():
            self.update_graph_display()

    def reset_filter(self):
        """Reset filters"""
        self.time_filter_var.set("1H")
        self.filter_score_var.set("0")
        self.filter_regime_var.set("ALL")
        self.refresh_display()

    def refresh_display(self):
        """Refresh display with filters"""
        # Clear tree
        for item in self.score_tree.get_children():
            self.score_tree.delete(item)

        # Get filtered checks
        filtered = self._get_filtered_checks()

        # Add to tree
        min_entry_score = self.config['ENTRY_SCORING_CONFIG'].get('min_entry_score', 3)
        for check in reversed(filtered):
            score = check['score']
            components = check['components']

            # Dynamic note based on config threshold
            note = ""
            if score >= min_entry_score:
                note = "✅ 진입 가능"
            elif score == min_entry_score - 1:
                note = f"⚠️ {min_entry_score - score}점 부족"
            elif score > 0:
                note = f"{min_entry_score - score}점 부족"

            tags = [f'score_{score}']
            if score >= min_entry_score:
                tags.append('entry_ready')

            values = (
                check['timestamp'].strftime('%Y-%m-%d %H:%M'),
                f'{score}/4',
                f"+{components.get('bb_touch', 0)}" if components.get('bb_touch', 0) > 0 else "-",
                f"+{components.get('rsi_oversold', 0)}" if components.get('rsi_oversold', 0) > 0 else "-",
                f"+{components.get('stoch_cross', 0)}" if components.get('stoch_cross', 0) > 0 else "-",
                check['regime'],
                f"{check['price']:,.0f}",
                note
            )

            check['id'] = self.score_tree.insert('', 0, values=values, tags=tuple(tags))

    def _get_filtered_checks(self) -> List[Dict[str, Any]]:
        """Get filtered score checks"""
        filtered = list(self.score_checks)

        # Time filter
        time_filter = self.time_filter_var.get()
        minutes_map = {'15M': 15, '30M': 30, '1H': 60, '4H': 240, '24H': 1440}
        minutes = minutes_map.get(time_filter, 60)

        cutoff_time = datetime.now()
        from datetime import timedelta
        cutoff_time = cutoff_time - timedelta(minutes=minutes)

        filtered = [c for c in filtered if c['timestamp'] >= cutoff_time]

        # Score filter
        min_score = int(self.filter_score_var.get())
        if min_score > 0:
            filtered = [c for c in filtered if c['score'] >= min_score]

        # Regime filter
        regime_filter = self.filter_regime_var.get()
        if regime_filter != 'ALL':
            filtered = [c for c in filtered if c['regime'] == regime_filter]

        return filtered

    def show_score_trend(self):
        """Show score trend graph in new window"""
        if not self.score_checks:
            from tkinter import messagebox
            messagebox.showwarning("경고", "표시할 점수 데이터가 없습니다.")
            return

        # Close existing window if open
        if self.graph_window is not None:
            try:
                self.graph_window.destroy()
            except:
                pass

        # Create new window
        self.graph_window = tk.Toplevel(self.parent)
        self.graph_window.title("점수 추세 그래프")
        self.graph_window.geometry("1200x700")

        # Main container
        main_frame = ttk.Frame(self.graph_window, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.graph_window.columnconfigure(0, weight=1)
        self.graph_window.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Control panel
        control_frame = ttk.LabelFrame(main_frame, text="그래프 설정", padding="10")
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Component breakdown toggle
        ttk.Label(control_frame, text="표시 옵션:").pack(side=tk.LEFT, padx=(0, 10))

        self.breakdown_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(control_frame, text="구성요소별 표시 (BB, RSI, Stoch)",
                       variable=self.breakdown_var,
                       command=lambda: self.update_graph_display()).pack(side=tk.LEFT, padx=(0, 20))

        # Filter sync info
        ttk.Label(control_frame, text="현재 필터:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 5))

        filter_info = f"{self.time_filter_var.get()} | 최소점수: {self.filter_score_var.get()} | Regime: {self.filter_regime_var.get()}"
        self.graph_filter_label = ttk.Label(control_frame, text=filter_info, foreground='blue')
        self.graph_filter_label.pack(side=tk.LEFT, padx=(0, 20))

        # Refresh button
        ttk.Button(control_frame, text="🔄 새로고침",
                  command=lambda: self.update_graph_display()).pack(side=tk.LEFT)

        # Chart frame
        chart_frame = ttk.Frame(main_frame)
        chart_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        chart_frame.columnconfigure(0, weight=1)
        chart_frame.rowconfigure(0, weight=1)

        # Create matplotlib figure
        self.create_score_trend_graph(chart_frame)

    def create_score_trend_graph(self, parent):
        """Create the score trend graph with matplotlib"""
        # Get filtered data
        filtered_checks = self._get_filtered_checks()

        if not filtered_checks:
            # Show no data message
            fig = Figure(figsize=(12, 6), dpi=100, facecolor='white')
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, '필터 조건에 맞는 데이터가 없습니다',
                   ha='center', va='center', fontsize=16, transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])

            self.graph_canvas = FigureCanvasTkAgg(fig, master=parent)
            self.graph_canvas.get_tk_widget().grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
            return

        # Prepare data
        timestamps = [check['timestamp'] for check in filtered_checks]
        scores = [check['score'] for check in filtered_checks]

        # Component data
        bb_values = [check['components'].get('bb_touch', 0) for check in filtered_checks]
        rsi_values = [check['components'].get('rsi_oversold', 0) for check in filtered_checks]
        stoch_values = [check['components'].get('stoch_cross', 0) for check in filtered_checks]

        # Determine if we show breakdown
        show_breakdown = self.breakdown_var.get() if hasattr(self, 'breakdown_var') else False

        # Create figure
        if show_breakdown:
            fig = Figure(figsize=(12, 8), dpi=100, facecolor='white')
            gs = fig.add_gridspec(2, 1, height_ratios=[2, 1], hspace=0.3)
            ax_main = fig.add_subplot(gs[0])
            ax_components = fig.add_subplot(gs[1], sharex=ax_main)
        else:
            fig = Figure(figsize=(12, 6), dpi=100, facecolor='white')
            ax_main = fig.add_subplot(111)

        # Main score trend line
        x_indices = range(len(timestamps))

        # Plot score line with color segments
        for i in range(len(scores) - 1):
            score = scores[i]
            color = self._get_line_color(score)
            ax_main.plot([i, i+1], [scores[i], scores[i+1]],
                        color=color, linewidth=2.5, alpha=0.8)

        # Add markers for each point
        for i, score in enumerate(scores):
            color = self._get_line_color(score)
            ax_main.scatter(i, score, color=color, s=50, zorder=5, edgecolors='white', linewidths=1)

        # Reference lines for score levels (dynamic threshold)
        min_entry_score = self.config['ENTRY_SCORING_CONFIG'].get('min_entry_score', 3)
        ax_main.axhline(y=4, color='#006400', linestyle=':', linewidth=1, alpha=0.4, label='만점 (4/4)')
        ax_main.axhline(y=min_entry_score, color='#32CD32', linestyle=':', linewidth=1, alpha=0.4,
                       label=f'진입가능 ({min_entry_score}/4)')
        ax_main.axhline(y=2, color='#FFA500', linestyle=':', linewidth=1, alpha=0.3)
        ax_main.axhline(y=1, color='#FF6347', linestyle=':', linewidth=1, alpha=0.3)
        ax_main.axhline(y=0, color='#DC143C', linestyle=':', linewidth=1, alpha=0.3)

        # Shaded "Entry Ready" zone (dynamic threshold)
        ax_main.fill_between(x_indices, min_entry_score, 4, alpha=0.15, color='green', label='진입 가능 구간')

        # Grid
        ax_main.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)

        # Labels and title
        ax_main.set_ylabel('Entry Score (점)', fontsize=11, fontweight='bold')
        ax_main.set_ylim(-0.5, 4.5)
        ax_main.set_yticks([0, 1, 2, 3, 4])
        ax_main.set_title('Entry Score Trend Analysis (진입 점수 추세 분석)',
                         fontsize=13, fontweight='bold', pad=15)
        ax_main.legend(loc='upper left', fontsize=9)

        # X-axis formatting
        if len(timestamps) > 0:
            step = max(1, len(timestamps) // 15)
            xtick_indices = list(range(0, len(timestamps), step))
            xtick_labels = [timestamps[i].strftime('%m-%d\n%H:%M') for i in xtick_indices]
            ax_main.set_xticks(xtick_indices)
            ax_main.set_xticklabels(xtick_labels, fontsize=8)

        # Component breakdown subplot (if enabled)
        if show_breakdown:
            # Stack area chart for components
            ax_components.fill_between(x_indices, 0, bb_values,
                                      alpha=0.6, color='blue', label='BB Touch')

            rsi_base = np.array(bb_values)
            ax_components.fill_between(x_indices, rsi_base,
                                      rsi_base + np.array(rsi_values),
                                      alpha=0.6, color='purple', label='RSI Oversold')

            stoch_base = rsi_base + np.array(rsi_values)
            ax_components.fill_between(x_indices, stoch_base,
                                      stoch_base + np.array(stoch_values),
                                      alpha=0.6, color='green', label='Stoch Cross')

            ax_components.set_ylabel('Component\nContribution', fontsize=9, fontweight='bold')
            ax_components.set_xlabel('Time (시간)', fontsize=10, fontweight='bold')
            ax_components.set_ylim(0, 4.5)
            ax_components.set_yticks([0, 1, 2, 3, 4])
            ax_components.legend(loc='upper left', fontsize=9)
            ax_components.grid(True, alpha=0.3, linestyle='--', linewidth=0.5)
            ax_components.set_title('Score Components Breakdown (구성요소 분해)',
                                   fontsize=11, fontweight='bold')
        else:
            ax_main.set_xlabel('Time (시간)', fontsize=10, fontweight='bold')

        # Add statistics text box
        avg_score = np.mean(scores)
        max_score = max(scores)
        min_score = min(scores)
        min_entry_score = self.config['ENTRY_SCORING_CONFIG'].get('min_entry_score', 3)
        entry_ready_pct = (sum(1 for s in scores if s >= min_entry_score) / len(scores)) * 100

        stats_text = f'Statistics:\n'
        stats_text += f'Avg: {avg_score:.2f}/4\n'
        stats_text += f'Max: {max_score}/4\n'
        stats_text += f'Min: {min_score}/4\n'
        stats_text += f'Entry Ready: {entry_ready_pct:.1f}%'

        ax_main.text(0.98, 0.97, stats_text,
                    transform=ax_main.transAxes,
                    fontsize=9,
                    verticalalignment='top',
                    horizontalalignment='right',
                    bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        fig.tight_layout()

        # Canvas
        self.graph_canvas = FigureCanvasTkAgg(fig, master=parent)
        self.graph_canvas.get_tk_widget().grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Toolbar for zoom/pan/save
        toolbar_frame = ttk.Frame(parent)
        toolbar_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))
        toolbar = NavigationToolbar2Tk(self.graph_canvas, toolbar_frame)
        toolbar.update()

    def _get_line_color(self, score: int) -> str:
        """Get color for score value"""
        return self.score_colors.get(score, '#808080')  # Gray as default

    def update_graph_display(self):
        """Update graph when settings change"""
        if self.graph_window is not None and self.graph_window.winfo_exists():
            # Update filter label
            filter_info = f"{self.time_filter_var.get()} | 최소점수: {self.filter_score_var.get()} | Regime: {self.filter_regime_var.get()}"
            self.graph_filter_label.config(text=filter_info)

            # Destroy old canvas
            for widget in self.graph_canvas.get_tk_widget().master.winfo_children():
                widget.destroy()

            # Recreate graph
            self.create_score_trend_graph(self.graph_canvas.get_tk_widget().master)

    def export_to_csv(self):
        """Export score checks to CSV"""
        from tkinter import filedialog, messagebox
        import csv

        if not self.score_checks:
            messagebox.showwarning("경고", "내보낼 데이터가 없습니다.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"score_checks_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)

                    # Header
                    writer.writerow([
                        'Timestamp', 'Score', 'BB Touch', 'RSI Oversold', 'Stoch Cross',
                        'Regime', 'Price', 'Entry Ready'
                    ])

                    # Data (dynamic threshold)
                    min_entry_score = self.config['ENTRY_SCORING_CONFIG'].get('min_entry_score', 3)
                    for check in reversed(list(self.score_checks)):
                        components = check['components']
                        writer.writerow([
                            check['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                            check['score'],
                            components.get('bb_touch', 0),
                            components.get('rsi_oversold', 0),
                            components.get('stoch_cross', 0),
                            check['regime'],
                            check['price'],
                            'YES' if check['score'] >= min_entry_score else 'NO'
                        ])

                messagebox.showinfo("성공", f"CSV 파일을 저장했습니다.\n{file_path}\n총 {len(self.score_checks)}개 기록")
            except Exception as e:
                messagebox.showerror("오류", f"CSV 저장 실패: {str(e)}")

    def update_coin(self, new_coin: str):
        """
        Update widget when coin changes.

        Args:
            new_coin: New coin symbol (e.g., 'SOL', 'ETH')
        """
        self.coin_symbol = new_coin

        # Update title (LabelFrame uses configure, not StringVar)
        self.stats_frame.configure(text=f"📊 {self.coin_symbol} 점수 체크 통계 (실시간 모니터링)")

        # Load data for new coin from file (will filter by coin)
        self.load_from_file()

        # Refresh display
        self.refresh_display()

    def clear_scores(self):
        """Clear all score checks"""
        from tkinter import messagebox
        if messagebox.askyesno("확인", "모든 점수 체크 기록을 삭제하시겠습니까?"):
            self.score_checks.clear()
            for item in self.score_tree.get_children():
                self.score_tree.delete(item)
            self.update_statistics()
            self.save_to_file()

    def save_to_file(self, file_path: str = None):
        """Save score checks to JSON file"""
        if file_path is None:
            file_path = os.path.join('logs', 'score_checks_v2.json')

        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            # Convert deque to list for JSON serialization
            data = list(self.score_checks)

            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving score checks to {file_path}: {str(e)}")

    def load_from_file(self, file_path: str = None):
        """Load score checks from JSON file (filtered by current coin)"""
        if file_path is None:
            file_path = os.path.join('logs', 'score_checks_v2.json')

        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    data = json.load(f)

                # Convert timestamp strings back to datetime and filter by coin
                filtered_data = []
                for check in data:
                    if isinstance(check['timestamp'], str):
                        check['timestamp'] = datetime.fromisoformat(check['timestamp'])

                    # Filter by coin symbol (backwards compatible: include if no coin field)
                    check_coin = check.get('coin', self.coin_symbol)  # Assume current coin if not specified
                    if check_coin == self.coin_symbol:
                        filtered_data.append(check)

                self.score_checks = deque(filtered_data, maxlen=1440)
                self.refresh_display()
                return True
        except Exception as e:
            print(f"Error loading score checks from {file_path}: {str(e)}")

        return False


# Test function
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Score Monitoring Widget Test")
    root.geometry("1000x700")

    widget = ScoreMonitoringWidgetV2(root)

    # Add sample data
    from datetime import timedelta
    base_time = datetime.now() - timedelta(hours=2)

    for i in range(120):  # 2 hours of data at 1-minute intervals
        score = (i % 5)  # Cycle through scores 0-4
        components = {
            'bb_touch': 1 if score >= 1 else 0,
            'rsi_oversold': 1 if score >= 2 else 0,
            'stoch_cross': 2 if score >= 4 else 0
        }
        regime = 'BULLISH' if i % 3 == 0 else ('BEARISH' if i % 3 == 1 else 'NEUTRAL')

        widget.add_score_check({
            'timestamp': base_time + timedelta(minutes=i),
            'score': score,
            'components': components,
            'regime': regime,
            'price': 170000000 + (i * 10000)
        })

    root.mainloop()
