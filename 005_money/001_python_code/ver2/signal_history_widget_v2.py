"""
Signal History Widget for Version 2 - Enhanced Design

Tracks and displays v2-specific scoring system:
- Entry signal score breakdown (0-4 points: BB touch, RSI oversold, Stoch RSI cross)
- Regime filter status at signal time (BULLISH/BEARISH/NEUTRAL)
- Position phase transitions with visual indicators
- Exit reasons with P&L tracking (stop loss, first target, final target)
- Advanced statistics: score distribution, win rate by score/regime
- Filter capabilities and CSV/JSON export
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from typing import Dict, Any, List, Optional
import json
import os


class SignalHistoryWidgetV2:
    """
    Enhanced signal history tracking widget for v2 strategy.

    Key Features:
    - Color-coded entry scores (0-4 points)
    - Regime-aware filtering and statistics
    - Score distribution analysis
    - Win rate tracking by score and regime
    - Export to CSV/JSON
    - Sortable columns
    """

    def __init__(self, parent):
        self.parent = parent
        self.signals = []
        self.max_signals = 200  # Increased for better analysis

        # Color scheme for scores
        self.score_colors = {
            4: '#006400',  # Dark green (excellent)
            3: '#32CD32',  # Light green (good)
            2: '#FFA500',  # Orange (marginal)
            1: '#FF6347',  # Tomato red (poor)
            0: '#DC143C'   # Crimson red (very poor)
        }

        self.setup_ui()
        self.load_from_file()  # Auto-load previous session

    def setup_ui(self):
        """Setup enhanced signal history UI with modern design"""
        # Main container
        main_frame = ttk.Frame(self.parent, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # === Statistics Panel ===
        stats_frame = ttk.LabelFrame(main_frame, text="📊 V2 전략 통계 (Entry Score System)", padding="10")
        stats_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Row 1: Overall statistics
        stats_row1 = ttk.Frame(stats_frame)
        stats_row1.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Label(stats_row1, text="총 신호:").pack(side=tk.LEFT, padx=(0, 5))
        self.total_signals_var = tk.StringVar(value="0")
        ttk.Label(stats_row1, textvariable=self.total_signals_var, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(stats_row1, text="평균 점수:").pack(side=tk.LEFT, padx=(0, 5))
        self.avg_score_var = tk.StringVar(value="0.0/4")
        ttk.Label(stats_row1, textvariable=self.avg_score_var, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(stats_row1, text="총 거래:").pack(side=tk.LEFT, padx=(0, 5))
        self.total_trades_var = tk.StringVar(value="0")
        ttk.Label(stats_row1, textvariable=self.total_trades_var, font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Label(stats_row1, text="전체 성공률:").pack(side=tk.LEFT, padx=(0, 5))
        self.success_rate_var = tk.StringVar(value="0%")
        self.success_rate_label = ttk.Label(stats_row1, textvariable=self.success_rate_var, font=('Arial', 10, 'bold'))
        self.success_rate_label.pack(side=tk.LEFT)

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

        # Row 3: Regime statistics
        stats_row3 = ttk.Frame(stats_frame)
        stats_row3.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        ttk.Label(stats_row3, text="Regime 분포:", font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 10))

        # Bullish
        bull_frame = ttk.Frame(stats_row3)
        bull_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(bull_frame, text="BULLISH:", foreground='green', font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 3))
        self.bullish_count_var = tk.StringVar(value="0")
        ttk.Label(bull_frame, textvariable=self.bullish_count_var).pack(side=tk.LEFT, padx=(0, 5))
        self.bullish_win_rate_var = tk.StringVar(value="(0%)")
        ttk.Label(bull_frame, textvariable=self.bullish_win_rate_var, foreground='gray').pack(side=tk.LEFT)

        # Bearish
        bear_frame = ttk.Frame(stats_row3)
        bear_frame.pack(side=tk.LEFT, padx=(0, 15))
        ttk.Label(bear_frame, text="BEARISH:", foreground='red', font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 3))
        self.bearish_count_var = tk.StringVar(value="0")
        ttk.Label(bear_frame, textvariable=self.bearish_count_var).pack(side=tk.LEFT, padx=(0, 5))
        self.bearish_win_rate_var = tk.StringVar(value="(0%)")
        ttk.Label(bear_frame, textvariable=self.bearish_win_rate_var, foreground='gray').pack(side=tk.LEFT)

        # Neutral
        neut_frame = ttk.Frame(stats_row3)
        neut_frame.pack(side=tk.LEFT)
        ttk.Label(neut_frame, text="NEUTRAL:", foreground='gray', font=('Arial', 9, 'bold')).pack(side=tk.LEFT, padx=(0, 3))
        self.neutral_count_var = tk.StringVar(value="0")
        ttk.Label(neut_frame, textvariable=self.neutral_count_var).pack(side=tk.LEFT)

        # === Filter Panel ===
        filter_frame = ttk.LabelFrame(main_frame, text="🔍 필터", padding="5")
        filter_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Filter controls
        ttk.Label(filter_frame, text="최소 점수:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_score_var = tk.StringVar(value="0")
        score_combo = ttk.Combobox(filter_frame, textvariable=self.filter_score_var,
                                   values=['0', '2', '3', '4'], width=5, state='readonly')
        score_combo.pack(side=tk.LEFT, padx=(0, 15))
        score_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Label(filter_frame, text="Regime:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_regime_var = tk.StringVar(value="ALL")
        regime_combo = ttk.Combobox(filter_frame, textvariable=self.filter_regime_var,
                                    values=['ALL', 'BULLISH', 'BEARISH', 'NEUTRAL'], width=10, state='readonly')
        regime_combo.pack(side=tk.LEFT, padx=(0, 15))
        regime_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Label(filter_frame, text="결과:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_result_var = tk.StringVar(value="ALL")
        result_combo = ttk.Combobox(filter_frame, textvariable=self.filter_result_var,
                                   values=['ALL', 'PROFIT', 'LOSS', 'PENDING'], width=10, state='readonly')
        result_combo.pack(side=tk.LEFT, padx=(0, 15))
        result_combo.bind('<<ComboboxSelected>>', lambda e: self.apply_filter())

        ttk.Button(filter_frame, text="필터 초기화", command=self.reset_filter).pack(side=tk.LEFT)

        # === Signal List ===
        list_frame = ttk.LabelFrame(main_frame, text="📋 신호 내역 (최신순)", padding="5")
        list_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # Treeview for signals (redesigned columns)
        columns = ('Time', 'Score', 'Breakdown', 'Regime', 'Coin', 'Price', 'Type', 'Result')
        self.signal_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)

        # Column configuration with sorting capability
        self.signal_tree.heading('Time', text='시간', command=lambda: self.sort_column('Time'))
        self.signal_tree.heading('Score', text='점수', command=lambda: self.sort_column('Score'))
        self.signal_tree.heading('Breakdown', text='구성요소 (Score Breakdown)', command=lambda: self.sort_column('Breakdown'))
        self.signal_tree.heading('Regime', text='Regime', command=lambda: self.sort_column('Regime'))
        self.signal_tree.heading('Coin', text='코인', command=lambda: self.sort_column('Coin'))
        self.signal_tree.heading('Price', text='가격', command=lambda: self.sort_column('Price'))
        self.signal_tree.heading('Type', text='유형', command=lambda: self.sort_column('Type'))
        self.signal_tree.heading('Result', text='결과 (P&L)', command=lambda: self.sort_column('Result'))

        self.signal_tree.column('Time', width=140, anchor='center')
        self.signal_tree.column('Score', width=70, anchor='center')
        self.signal_tree.column('Breakdown', width=220, anchor='w')
        self.signal_tree.column('Regime', width=90, anchor='center')
        self.signal_tree.column('Coin', width=60, anchor='center')
        self.signal_tree.column('Price', width=100, anchor='e')
        self.signal_tree.column('Type', width=100, anchor='center')
        self.signal_tree.column('Result', width=100, anchor='center')

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.signal_tree.yview)
        self.signal_tree.configure(yscrollcommand=scrollbar.set)

        self.signal_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Configure tags for color coding
        self.signal_tree.tag_configure('score_4', background='#E6FFE6')  # Light green
        self.signal_tree.tag_configure('score_3', background='#F0FFF0')  # Very light green
        self.signal_tree.tag_configure('score_2', background='#FFF8DC')  # Cornsilk (yellow)
        self.signal_tree.tag_configure('score_1', background='#FFE4E1')  # Misty rose (light red)
        self.signal_tree.tag_configure('score_0', background='#FFCCCC')  # Light red
        self.signal_tree.tag_configure('profit', foreground='#006400')  # Dark green
        self.signal_tree.tag_configure('loss', foreground='#DC143C')    # Crimson
        self.signal_tree.tag_configure('event', foreground='#4169E1')   # Royal blue
        self.signal_tree.tag_configure('regime_bullish', foreground='#008000')  # Green
        self.signal_tree.tag_configure('regime_bearish', foreground='#FF0000')  # Red
        self.signal_tree.tag_configure('regime_neutral', foreground='#808080')  # Gray

        # Detail view (double-click handler)
        self.signal_tree.bind('<Double-1>', self.on_signal_double_click)

        # === Control Buttons ===
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(10, 0))

        ttk.Button(button_frame, text="🔄 새로고침", command=self.refresh_signals).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="📊 상세 통계", command=self.show_detailed_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 CSV 내보내기", command=self.export_to_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 JSON 내보내기", command=self.export_signals).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="🗑️ 기록 삭제", command=self.clear_signals).pack(side=tk.LEFT, padx=5)

    def add_entry_signal(self, signal_data: Dict[str, Any]):
        """
        Add entry signal to history with enhanced v2 display.

        Args:
            signal_data: Dictionary with entry signal details
                - timestamp: Signal time
                - regime: Market regime (BULLISH/BEARISH/NEUTRAL)
                - score: Entry score (0-4)
                - components: Dict with bb_touch, rsi_oversold, stoch_cross scores
                - price: Entry price
                - coin: Trading pair (default: 'BTC')
        """
        timestamp = signal_data.get('timestamp', datetime.now())
        regime = signal_data.get('regime', 'NEUTRAL')
        score = signal_data.get('score', 0)
        components = signal_data.get('components', {})
        price = signal_data.get('price', 0)
        coin = signal_data.get('coin', 'BTC')

        # Format components string with visual indicators
        comp_list = []
        if components.get('bb_touch', 0) > 0:
            comp_list.append(f"BB Lower Touch(+{components['bb_touch']})")
        if components.get('rsi_oversold', 0) > 0:
            comp_list.append(f"RSI<30(+{components['rsi_oversold']})")
        if components.get('stoch_cross', 0) > 0:
            comp_list.append(f"Stoch Cross(+{components['stoch_cross']})")

        components_str = ", ".join(comp_list) if comp_list else "None"

        # Determine tags for color coding
        tags = [f'score_{score}']
        if regime == 'BULLISH':
            tags.append('regime_bullish')
        elif regime == 'BEARISH':
            tags.append('regime_bearish')
        else:
            tags.append('regime_neutral')

        # Add to tree with new column order
        values = (
            timestamp.strftime('%Y-%m-%d %H:%M'),  # Time
            f'{score}/4',                           # Score
            components_str,                         # Breakdown
            regime,                                 # Regime
            coin,                                   # Coin
            f'{price:,.0f}',                       # Price
            'ENTRY',                               # Type
            'Pending'                              # Result
        )

        item_id = self.signal_tree.insert('', 0, values=values, tags=tuple(tags))

        # Store full signal data
        signal_record = {
            'id': item_id,
            'timestamp': timestamp,
            'type': 'ENTRY',
            'regime': regime,
            'score': score,
            'components': components,
            'price': price,
            'coin': coin,
            'result': None
        }
        self.signals.insert(0, signal_record)

        # Limit history size
        if len(self.signals) > self.max_signals:
            removed = self.signals.pop()
            try:
                self.signal_tree.delete(removed['id'])
            except:
                pass  # Item may have been filtered out

        self.update_statistics()
        self.save_to_file()  # Auto-save to persistent storage

    def add_exit_signal(self, signal_data: Dict[str, Any]):
        """
        Add exit signal to history with enhanced v2 display.

        Args:
            signal_data: Dictionary with exit signal details
                - timestamp: Exit time
                - exit_type: Exit reason (STOP_LOSS, FIRST_TARGET, FINAL_TARGET, BREAKEVEN)
                - price: Exit price
                - pnl: Profit/loss (absolute)
                - pnl_pct: P&L percentage
                - coin: Trading pair (default: 'BTC')
        """
        timestamp = signal_data.get('timestamp', datetime.now())
        exit_type = signal_data.get('exit_type', 'EXIT')
        price = signal_data.get('price', 0)
        pnl = signal_data.get('pnl', 0)
        pnl_pct = signal_data.get('pnl_pct', 0)
        coin = signal_data.get('coin', 'BTC')

        # Determine result display and color
        if pnl >= 0:
            result_str = f'+{pnl_pct:.2f}% (${pnl:+.0f})'
            tags = ['profit']
        else:
            result_str = f'{pnl_pct:.2f}% (${pnl:.0f})'
            tags = ['loss']

        # Add to tree with new column order
        values = (
            timestamp.strftime('%Y-%m-%d %H:%M'),  # Time
            '-',                                    # Score (N/A for exits)
            '-',                                    # Breakdown (N/A)
            '-',                                    # Regime (N/A)
            coin,                                   # Coin
            f'{price:,.0f}',                       # Price
            exit_type,                             # Type
            result_str                             # Result
        )

        item_id = self.signal_tree.insert('', 0, values=values, tags=tuple(tags))

        # Update corresponding entry signal result
        if len(self.signals) > 0:
            for signal in self.signals:
                if signal['type'] == 'ENTRY' and signal.get('result') is None:
                    signal['result'] = {
                        'exit_type': exit_type,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct
                    }
                    # Update tree item with profit/loss tag
                    try:
                        current_tags = list(self.signal_tree.item(signal['id'], 'tags'))
                        if pnl >= 0:
                            current_tags.append('profit')
                        else:
                            current_tags.append('loss')
                        self.signal_tree.item(signal['id'], tags=tuple(current_tags))
                        self.signal_tree.set(signal['id'], 'Result', result_str)
                    except:
                        pass  # Item may have been filtered out
                    break

        # Store exit record
        exit_record = {
            'id': item_id,
            'timestamp': timestamp,
            'type': 'EXIT',
            'exit_type': exit_type,
            'price': price,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'coin': coin
        }
        self.signals.insert(0, exit_record)

        self.update_statistics()
        self.save_to_file()  # Auto-save to persistent storage

    def add_position_event(self, event_data: Dict[str, Any]):
        """
        Add position management event (scaling, stop movement, etc) with enhanced v2 display.

        Args:
            event_data: Dictionary with event details
                - timestamp: Event time
                - event_type: Event type (SCALE_OUT, STOP_TRAIL, FIRST_TARGET_HIT, BREAKEVEN)
                - description: Event description
                - price: Current price
                - coin: Trading pair (default: 'BTC')
        """
        timestamp = event_data.get('timestamp', datetime.now())
        event_type = event_data.get('event_type', 'EVENT')
        description = event_data.get('description', '')
        price = event_data.get('price', 0)
        coin = event_data.get('coin', 'BTC')

        # Add to tree with new column order
        values = (
            timestamp.strftime('%Y-%m-%d %H:%M'),  # Time
            '-',                                    # Score (N/A)
            description,                           # Breakdown (use for description)
            '-',                                    # Regime (N/A)
            coin,                                   # Coin
            f'{price:,.0f}',                       # Price
            event_type,                            # Type
            '-'                                     # Result (N/A)
        )

        item_id = self.signal_tree.insert('', 0, values=values, tags=('event',))

        # Store event record
        event_record = {
            'id': item_id,
            'timestamp': timestamp,
            'type': 'EVENT',
            'event_type': event_type,
            'description': description,
            'price': price,
            'coin': coin
        }
        self.signals.insert(0, event_record)
        self.save_to_file()  # Auto-save to persistent storage

    def update_statistics(self):
        """Update enhanced statistics display with v2 scoring insights"""
        if not self.signals:
            # Reset all stats to zero
            self.total_signals_var.set("0")
            self.avg_score_var.set("0.0/4")
            self.total_trades_var.set("0")
            self.success_rate_var.set("0%")
            for score in [4, 3, 2, 1, 0]:
                self.score_dist_vars[score].set("0")
            self.bullish_count_var.set("0")
            self.bearish_count_var.set("0")
            self.neutral_count_var.set("0")
            self.bullish_win_rate_var.set("(0%)")
            self.bearish_win_rate_var.set("(0%)")
            return

        # Separate signals by type
        entry_signals = [s for s in self.signals if s['type'] == 'ENTRY']
        exit_signals = [s for s in self.signals if s['type'] == 'EXIT']

        # Total entry signals
        self.total_signals_var.set(str(len(entry_signals)))

        # Average score
        if entry_signals:
            avg_score = sum(s.get('score', 0) for s in entry_signals) / len(entry_signals)
            self.avg_score_var.set(f"{avg_score:.2f}/4")
        else:
            self.avg_score_var.set("0.0/4")

        # Score distribution
        score_counts = {4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
        for signal in entry_signals:
            score = signal.get('score', 0)
            if score in score_counts:
                score_counts[score] += 1

        for score, count in score_counts.items():
            self.score_dist_vars[score].set(str(count))

        # Regime distribution
        bullish_entries = [s for s in entry_signals if s.get('regime') == 'BULLISH']
        bearish_entries = [s for s in entry_signals if s.get('regime') == 'BEARISH']
        neutral_entries = [s for s in entry_signals if s.get('regime') == 'NEUTRAL']

        self.bullish_count_var.set(str(len(bullish_entries)))
        self.bearish_count_var.set(str(bearish_entries))
        self.neutral_count_var.set(str(len(neutral_entries)))

        # Total completed trades (entries with results)
        completed_trades = [s for s in entry_signals if s.get('result') is not None]
        self.total_trades_var.set(str(len(completed_trades)))

        # Overall success rate
        if completed_trades:
            profitable = sum(1 for s in completed_trades if s['result'].get('pnl', 0) > 0)
            success_rate = (profitable / len(completed_trades)) * 100
            self.success_rate_var.set(f"{success_rate:.1f}%")

            # Color code success rate
            if success_rate >= 60:
                self.success_rate_label.config(foreground='green')
            elif success_rate >= 40:
                self.success_rate_label.config(foreground='orange')
            else:
                self.success_rate_label.config(foreground='red')
        else:
            self.success_rate_var.set("0%")

        # Regime-specific win rates
        bullish_completed = [s for s in bullish_entries if s.get('result') is not None]
        if bullish_completed:
            bullish_wins = sum(1 for s in bullish_completed if s['result'].get('pnl', 0) > 0)
            bullish_wr = (bullish_wins / len(bullish_completed)) * 100
            self.bullish_win_rate_var.set(f"({bullish_wr:.0f}% win)")
        else:
            self.bullish_win_rate_var.set("(0%)")

        bearish_completed = [s for s in bearish_entries if s.get('result') is not None]
        if bearish_completed:
            bearish_wins = sum(1 for s in bearish_completed if s['result'].get('pnl', 0) > 0)
            bearish_wr = (bearish_wins / len(bearish_completed)) * 100
            self.bearish_win_rate_var.set(f"({bearish_wr:.0f}% win)")
        else:
            self.bearish_win_rate_var.set("(0%)")

    def on_signal_double_click(self, event):
        """Handle double-click on signal for detail view"""
        selection = self.signal_tree.selection()
        if not selection:
            return

        item_id = selection[0]
        values = self.signal_tree.item(item_id)['values']

        # Find signal in records
        signal = None
        for s in self.signals:
            if s['id'] == item_id:
                signal = s
                break

        if not signal:
            return

        # Show detail dialog
        self.show_signal_detail(signal)

    def show_signal_detail(self, signal: Dict[str, Any]):
        """Show detailed signal information in popup"""
        detail_window = tk.Toplevel(self.parent)
        detail_window.title("신호 상세 정보")
        detail_window.geometry("500x400")

        # Detail text
        detail_frame = ttk.Frame(detail_window, padding="10")
        detail_frame.pack(fill=tk.BOTH, expand=True)

        text = tk.Text(detail_frame, wrap=tk.WORD, font=('Courier', 10))
        text.pack(fill=tk.BOTH, expand=True)

        # Format signal details
        detail_str = json.dumps(signal, indent=2, default=str)
        text.insert('1.0', detail_str)
        text.config(state=tk.DISABLED)

        # Close button
        ttk.Button(detail_window, text="닫기", command=detail_window.destroy).pack(pady=10)

    def refresh_signals(self):
        """Refresh signal display with current filter settings"""
        # Clear tree
        for item in self.signal_tree.get_children():
            self.signal_tree.delete(item)

        # Rebuild from signals list (apply filters if active)
        filtered_signals = self._get_filtered_signals()

        for signal in reversed(filtered_signals):
            if signal['type'] == 'ENTRY':
                # Format components
                components_str = self._format_components(signal.get('components', {}))
                result_str = self._format_result(signal.get('result'))
                score = signal.get('score', 0)
                regime = signal.get('regime', 'NEUTRAL')

                # Determine tags
                tags = [f'score_{score}']
                if regime == 'BULLISH':
                    tags.append('regime_bullish')
                elif regime == 'BEARISH':
                    tags.append('regime_bearish')
                else:
                    tags.append('regime_neutral')

                # Add profit/loss tag if result exists
                result = signal.get('result')
                if result and result.get('pnl', 0) >= 0:
                    tags.append('profit')
                elif result:
                    tags.append('loss')

                values = (
                    signal['timestamp'].strftime('%Y-%m-%d %H:%M'),
                    f"{score}/4",
                    components_str,
                    regime,
                    signal.get('coin', 'BTC'),
                    f"{signal.get('price', 0):,.0f}",
                    'ENTRY',
                    result_str
                )
                signal['id'] = self.signal_tree.insert('', 0, values=values, tags=tuple(tags))

            elif signal['type'] == 'EXIT':
                pnl = signal.get('pnl', 0)
                pnl_pct = signal.get('pnl_pct', 0)
                result_str = f'+{pnl_pct:.2f}% (${pnl:+.0f})' if pnl >= 0 else f'{pnl_pct:.2f}% (${pnl:.0f})'
                tags = ['profit'] if pnl >= 0 else ['loss']

                values = (
                    signal['timestamp'].strftime('%Y-%m-%d %H:%M'),
                    '-',
                    '-',
                    '-',
                    signal.get('coin', 'BTC'),
                    f"{signal.get('price', 0):,.0f}",
                    signal.get('exit_type', 'EXIT'),
                    result_str
                )
                signal['id'] = self.signal_tree.insert('', 0, values=values, tags=tuple(tags))

            elif signal['type'] == 'EVENT':
                values = (
                    signal['timestamp'].strftime('%Y-%m-%d %H:%M'),
                    '-',
                    signal.get('description', ''),
                    '-',
                    signal.get('coin', 'BTC'),
                    f"{signal.get('price', 0):,.0f}",
                    signal.get('event_type', 'EVENT'),
                    '-'
                )
                signal['id'] = self.signal_tree.insert('', 0, values=values, tags=('event',))

        self.update_statistics()

    def _get_filtered_signals(self) -> List[Dict[str, Any]]:
        """Get signals filtered by current filter settings"""
        filtered = self.signals

        # Filter by minimum score
        min_score = int(self.filter_score_var.get())
        if min_score > 0:
            filtered = [s for s in filtered if
                       s['type'] != 'ENTRY' or s.get('score', 0) >= min_score]

        # Filter by regime
        regime_filter = self.filter_regime_var.get()
        if regime_filter != 'ALL':
            filtered = [s for s in filtered if
                       s['type'] != 'ENTRY' or s.get('regime') == regime_filter]

        # Filter by result
        result_filter = self.filter_result_var.get()
        if result_filter == 'PROFIT':
            filtered = [s for s in filtered if
                       s['type'] != 'ENTRY' or (s.get('result') and s['result'].get('pnl', 0) > 0)]
        elif result_filter == 'LOSS':
            filtered = [s for s in filtered if
                       s['type'] != 'ENTRY' or (s.get('result') and s['result'].get('pnl', 0) < 0)]
        elif result_filter == 'PENDING':
            filtered = [s for s in filtered if
                       s['type'] != 'ENTRY' or s.get('result') is None]

        return filtered

    def _format_components(self, components: Dict[str, int]) -> str:
        """Format components dictionary to string"""
        comp_list = []
        if components.get('bb_touch', 0) > 0:
            comp_list.append(f"BB Lower Touch(+{components['bb_touch']})")
        if components.get('rsi_oversold', 0) > 0:
            comp_list.append(f"RSI<30(+{components['rsi_oversold']})")
        if components.get('stoch_cross', 0) > 0:
            comp_list.append(f"Stoch Cross(+{components['stoch_cross']})")
        return ", ".join(comp_list) if comp_list else "None"

    def _format_result(self, result: Optional[Dict[str, Any]]) -> str:
        """Format result dictionary to string"""
        if not result:
            return 'Pending'

        pnl = result.get('pnl', 0)
        pnl_pct = result.get('pnl_pct', 0)
        return f'+{pnl_pct:.2f}% (${pnl:+.0f})' if pnl >= 0 else f'{pnl_pct:.2f}% (${pnl:.0f})'

    def apply_filter(self):
        """Apply current filter settings to signal display"""
        self.refresh_signals()

    def reset_filter(self):
        """Reset all filters to default values"""
        self.filter_score_var.set("0")
        self.filter_regime_var.set("ALL")
        self.filter_result_var.set("ALL")
        self.refresh_signals()

    def sort_column(self, column_name: str):
        """Sort signals by column (placeholder - can be enhanced)"""
        # For now, just refresh - can implement actual sorting logic later
        messagebox.showinfo("정렬", f"{column_name} 컬럼 정렬 기능은 향후 구현 예정입니다.")

    def clear_signals(self):
        """Clear all signals with confirmation"""
        if messagebox.askyesno("확인", "모든 신호 기록을 삭제하시겠습니까?"):
            self.signals = []
            for item in self.signal_tree.get_children():
                self.signal_tree.delete(item)
            self.update_statistics()
            self.save_to_file()  # Save empty list

    def export_signals(self):
        """Export signals to JSON file"""
        from tkinter import filedialog

        if not self.signals:
            messagebox.showwarning("경고", "내보낼 신호가 없습니다.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"signals_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        if file_path:
            try:
                # Export with metadata
                export_data = {
                    'export_time': datetime.now().isoformat(),
                    'version': 'v2',
                    'total_signals': len(self.signals),
                    'signals': self.signals
                }
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, default=str, ensure_ascii=False)
                messagebox.showinfo("성공", f"신호 기록을 {file_path}에 저장했습니다.\n총 {len(self.signals)}개 신호")
            except Exception as e:
                messagebox.showerror("오류", f"저장 실패: {str(e)}")

    def export_to_csv(self):
        """Export signals to CSV file for spreadsheet analysis"""
        from tkinter import filedialog
        import csv

        if not self.signals:
            messagebox.showwarning("경고", "내보낼 신호가 없습니다.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"signals_v2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        if file_path:
            try:
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)

                    # Header row
                    writer.writerow([
                        'Timestamp', 'Type', 'Score', 'BB Touch', 'RSI Oversold', 'Stoch Cross',
                        'Regime', 'Coin', 'Price', 'Exit Type', 'PnL', 'PnL %', 'Description'
                    ])

                    # Data rows
                    for signal in reversed(self.signals):  # Chronological order
                        if signal['type'] == 'ENTRY':
                            components = signal.get('components', {})
                            result = signal.get('result')
                            writer.writerow([
                                signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                                'ENTRY',
                                signal.get('score', 0),
                                components.get('bb_touch', 0),
                                components.get('rsi_oversold', 0),
                                components.get('stoch_cross', 0),
                                signal.get('regime', ''),
                                signal.get('coin', 'BTC'),
                                signal.get('price', 0),
                                result.get('exit_type', '') if result else '',
                                result.get('pnl', '') if result else '',
                                result.get('pnl_pct', '') if result else '',
                                ''
                            ])
                        elif signal['type'] == 'EXIT':
                            writer.writerow([
                                signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                                'EXIT',
                                '',
                                '',
                                '',
                                '',
                                '',
                                signal.get('coin', 'BTC'),
                                signal.get('price', 0),
                                signal.get('exit_type', ''),
                                signal.get('pnl', 0),
                                signal.get('pnl_pct', 0),
                                ''
                            ])
                        elif signal['type'] == 'EVENT':
                            writer.writerow([
                                signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                                'EVENT',
                                '',
                                '',
                                '',
                                '',
                                '',
                                signal.get('coin', 'BTC'),
                                signal.get('price', 0),
                                signal.get('event_type', ''),
                                '',
                                '',
                                signal.get('description', '')
                            ])

                messagebox.showinfo("성공", f"CSV 파일을 {file_path}에 저장했습니다.\n총 {len(self.signals)}개 신호")
            except Exception as e:
                messagebox.showerror("오류", f"CSV 저장 실패: {str(e)}")

    def show_detailed_stats(self):
        """Show detailed statistics window with score-based analysis"""
        stats_window = tk.Toplevel(self.parent)
        stats_window.title("V2 전략 상세 통계")
        stats_window.geometry("700x600")

        # Main frame with scrollbar
        main_frame = ttk.Frame(stats_window, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Create text widget for stats
        text = tk.Text(main_frame, wrap=tk.WORD, font=('Courier', 10), bg='#F5F5F5')
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)

        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Generate statistics
        stats_text = self._generate_detailed_stats()
        text.insert('1.0', stats_text)
        text.config(state=tk.DISABLED)

        # Close button
        ttk.Button(stats_window, text="닫기", command=stats_window.destroy).pack(pady=10)

    def _generate_detailed_stats(self) -> str:
        """Generate detailed statistics text for v2 strategy"""
        if not self.signals:
            return "통계를 생성할 신호가 없습니다."

        entry_signals = [s for s in self.signals if s['type'] == 'ENTRY']
        completed_trades = [s for s in entry_signals if s.get('result') is not None]

        stats = []
        stats.append("=" * 70)
        stats.append("V2 전략 상세 통계 - Entry Score System (0-4 Points)")
        stats.append("=" * 70)
        stats.append("")

        # Overall summary
        stats.append("📊 전체 요약")
        stats.append("-" * 70)
        stats.append(f"총 진입 신호: {len(entry_signals)}개")
        stats.append(f"완료된 거래: {len(completed_trades)}개")
        stats.append(f"대기 중인 거래: {len(entry_signals) - len(completed_trades)}개")
        stats.append("")

        # Score distribution and performance
        stats.append("🎯 점수별 분석 (Entry Score Performance)")
        stats.append("-" * 70)

        for score in [4, 3, 2, 1, 0]:
            score_signals = [s for s in entry_signals if s.get('score', 0) == score]
            score_completed = [s for s in score_signals if s.get('result') is not None]

            stats.append(f"\n점수 {score}/4:")
            stats.append(f"  총 신호: {len(score_signals)}개")

            if score_completed:
                wins = sum(1 for s in score_completed if s['result'].get('pnl', 0) > 0)
                win_rate = (wins / len(score_completed)) * 100
                avg_pnl = sum(s['result'].get('pnl_pct', 0) for s in score_completed) / len(score_completed)

                stats.append(f"  완료 거래: {len(score_completed)}개")
                stats.append(f"  승률: {win_rate:.1f}% ({wins}승 {len(score_completed)-wins}패)")
                stats.append(f"  평균 수익률: {avg_pnl:+.2f}%")
            else:
                stats.append(f"  완료 거래: 0개 (데이터 없음)")

        stats.append("")

        # Regime-based analysis
        stats.append("🌐 Regime별 분석")
        stats.append("-" * 70)

        for regime in ['BULLISH', 'BEARISH', 'NEUTRAL']:
            regime_signals = [s for s in entry_signals if s.get('regime') == regime]
            regime_completed = [s for s in regime_signals if s.get('result') is not None]

            stats.append(f"\n{regime}:")
            stats.append(f"  총 신호: {len(regime_signals)}개")

            if regime_completed:
                wins = sum(1 for s in regime_completed if s['result'].get('pnl', 0) > 0)
                win_rate = (wins / len(regime_completed)) * 100
                avg_pnl = sum(s['result'].get('pnl_pct', 0) for s in regime_completed) / len(regime_completed)
                avg_score = sum(s.get('score', 0) for s in regime_signals) / len(regime_signals)

                stats.append(f"  완료 거래: {len(regime_completed)}개")
                stats.append(f"  승률: {win_rate:.1f}% ({wins}승 {len(regime_completed)-wins}패)")
                stats.append(f"  평균 수익률: {avg_pnl:+.2f}%")
                stats.append(f"  평균 진입 점수: {avg_score:.2f}/4")
            else:
                stats.append(f"  완료 거래: 0개 (데이터 없음)")

        stats.append("")

        # Component contribution analysis
        stats.append("🔧 구성요소 기여도 분석")
        stats.append("-" * 70)

        components_list = ['bb_touch', 'rsi_oversold', 'stoch_cross']
        component_names = {
            'bb_touch': 'BB Lower Touch (+1)',
            'rsi_oversold': 'RSI Oversold (+1)',
            'stoch_cross': 'Stochastic Cross (+2)'
        }

        for comp in components_list:
            comp_signals = [s for s in entry_signals if s.get('components', {}).get(comp, 0) > 0]
            comp_completed = [s for s in comp_signals if s.get('result') is not None]

            stats.append(f"\n{component_names[comp]}:")
            stats.append(f"  발생 횟수: {len(comp_signals)}개")

            if comp_completed:
                wins = sum(1 for s in comp_completed if s['result'].get('pnl', 0) > 0)
                win_rate = (wins / len(comp_completed)) * 100
                stats.append(f"  완료 거래: {len(comp_completed)}개")
                stats.append(f"  승률: {win_rate:.1f}%")
            else:
                stats.append(f"  완료 거래: 0개")

        stats.append("")

        # Best combination analysis
        stats.append("⭐ 최적 조합 분석")
        stats.append("-" * 70)

        # 4/4 signals (all three components)
        perfect_signals = [s for s in entry_signals if s.get('score', 0) == 4]
        perfect_completed = [s for s in perfect_signals if s.get('result') is not None]

        if perfect_completed:
            wins = sum(1 for s in perfect_completed if s['result'].get('pnl', 0) > 0)
            win_rate = (wins / len(perfect_completed)) * 100
            avg_pnl = sum(s['result'].get('pnl_pct', 0) for s in perfect_completed) / len(perfect_completed)

            stats.append(f"4/4 Perfect Score (모든 조건 만족):")
            stats.append(f"  총 {len(perfect_signals)}개 신호, {len(perfect_completed)}개 완료")
            stats.append(f"  승률: {win_rate:.1f}%")
            stats.append(f"  평균 수익률: {avg_pnl:+.2f}%")
            stats.append("")

        # Regime + Score combination
        bullish_high_score = [s for s in entry_signals
                             if s.get('regime') == 'BULLISH' and s.get('score', 0) >= 3]
        bullish_high_completed = [s for s in bullish_high_score if s.get('result') is not None]

        if bullish_high_completed:
            wins = sum(1 for s in bullish_high_completed if s['result'].get('pnl', 0) > 0)
            win_rate = (wins / len(bullish_high_completed)) * 100
            avg_pnl = sum(s['result'].get('pnl_pct', 0) for s in bullish_high_completed) / len(bullish_high_completed)

            stats.append(f"BULLISH + 3-4점 (최적 조합):")
            stats.append(f"  총 {len(bullish_high_score)}개 신호, {len(bullish_high_completed)}개 완료")
            stats.append(f"  승률: {win_rate:.1f}%")
            stats.append(f"  평균 수익률: {avg_pnl:+.2f}%")
            stats.append("")

        stats.append("=" * 70)
        stats.append(f"통계 생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        stats.append("=" * 70)

        return "\n".join(stats)

    def load_signals(self, signals: List[Dict[str, Any]]):
        """Load signals from external source"""
        self.signals = signals
        self.refresh_signals()

    def save_to_file(self, file_path: str = None):
        """Save signals to JSON file (persistent storage)"""
        if file_path is None:
            file_path = os.path.join('logs', 'signals_v2.json')

        try:
            # Create logs directory if not exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w') as f:
                json.dump(self.signals, f, indent=2, default=str)
        except Exception as e:
            print(f"Error saving signals to {file_path}: {str(e)}")

    def load_from_file(self, file_path: str = None):
        """Load signals from JSON file"""
        if file_path is None:
            file_path = os.path.join('logs', 'signals_v2.json')

        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    self.signals = json.load(f)
                self.refresh_signals()
                return True
        except Exception as e:
            print(f"Error loading signals from {file_path}: {str(e)}")

        return False
