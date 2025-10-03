"""
Signal History Widget for Version 2

Tracks and displays:
- Entry signal score breakdown (BB touch, RSI oversold, Stoch RSI cross)
- Regime filter status at signal time
- Position phase transitions
- Exit reasons (stop loss, first target, final target)
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime
from typing import Dict, Any, List, Optional
import json


class SignalHistoryWidgetV2:
    """
    Signal history tracking widget for v2 strategy.

    Displays historical entry/exit signals with v2-specific details:
    - Entry score components
    - Regime filter status
    - Position scaling events
    - Chandelier stop movements
    """

    def __init__(self, parent):
        self.parent = parent
        self.signals = []
        self.max_signals = 100

        self.setup_ui()

    def setup_ui(self):
        """Setup signal history UI"""
        # Main container
        main_frame = ttk.Frame(self.parent, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.parent.columnconfigure(0, weight=1)
        self.parent.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Header with stats
        header_frame = ttk.LabelFrame(main_frame, text="📊 신호 통계", padding="10")
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Statistics
        ttk.Label(header_frame, text="총 신호:").grid(row=0, column=0, padx=(0, 5))
        self.total_signals_var = tk.StringVar(value="0")
        ttk.Label(header_frame, textvariable=self.total_signals_var).grid(row=0, column=1, padx=(0, 20))

        ttk.Label(header_frame, text="평균 점수:").grid(row=0, column=2, padx=(0, 5))
        self.avg_score_var = tk.StringVar(value="0.0")
        ttk.Label(header_frame, textvariable=self.avg_score_var).grid(row=0, column=3, padx=(0, 20))

        ttk.Label(header_frame, text="Bullish Regime:").grid(row=0, column=4, padx=(0, 5))
        self.bullish_count_var = tk.StringVar(value="0")
        ttk.Label(header_frame, textvariable=self.bullish_count_var).grid(row=0, column=5, padx=(0, 20))

        ttk.Label(header_frame, text="성공률:").grid(row=0, column=6, padx=(0, 5))
        self.success_rate_var = tk.StringVar(value="0%")
        ttk.Label(header_frame, textvariable=self.success_rate_var).grid(row=0, column=7)

        # Signal list
        list_frame = ttk.LabelFrame(main_frame, text="📋 신호 내역", padding="5")
        list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        # Treeview for signals
        columns = ('Time', 'Type', 'Regime', 'Score', 'Components', 'Price', 'Result')
        self.signal_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=20)

        # Column configuration
        self.signal_tree.heading('Time', text='시간')
        self.signal_tree.heading('Type', text='유형')
        self.signal_tree.heading('Regime', text='Regime')
        self.signal_tree.heading('Score', text='점수')
        self.signal_tree.heading('Components', text='구성요소')
        self.signal_tree.heading('Price', text='가격')
        self.signal_tree.heading('Result', text='결과')

        self.signal_tree.column('Time', width=120, anchor='center')
        self.signal_tree.column('Type', width=80, anchor='center')
        self.signal_tree.column('Regime', width=80, anchor='center')
        self.signal_tree.column('Score', width=60, anchor='center')
        self.signal_tree.column('Components', width=200, anchor='w')
        self.signal_tree.column('Price', width=100, anchor='e')
        self.signal_tree.column('Result', width=100, anchor='center')

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.signal_tree.yview)
        self.signal_tree.configure(yscrollcommand=scrollbar.set)

        self.signal_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Detail view (double-click handler)
        self.signal_tree.bind('<Double-1>', self.on_signal_double_click)

        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(10, 0))

        ttk.Button(button_frame, text="🔄 새로고침", command=self.refresh_signals).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="🗑️ 기록 삭제", command=self.clear_signals).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="💾 내보내기", command=self.export_signals).pack(side=tk.LEFT, padx=5)

    def add_entry_signal(self, signal_data: Dict[str, Any]):
        """
        Add entry signal to history.

        Args:
            signal_data: Dictionary with entry signal details
                - timestamp: Signal time
                - regime: Market regime (BULLISH/BEARISH/NEUTRAL)
                - score: Entry score (0-4)
                - components: Dict with bb_touch, rsi_oversold, stoch_cross scores
                - price: Entry price
        """
        timestamp = signal_data.get('timestamp', datetime.now())
        regime = signal_data.get('regime', 'UNKNOWN')
        score = signal_data.get('score', 0)
        components = signal_data.get('components', {})
        price = signal_data.get('price', 0)

        # Format components string
        comp_list = []
        if components.get('bb_touch', 0) > 0:
            comp_list.append(f"BB(+{components['bb_touch']})")
        if components.get('rsi_oversold', 0) > 0:
            comp_list.append(f"RSI(+{components['rsi_oversold']})")
        if components.get('stoch_cross', 0) > 0:
            comp_list.append(f"Stoch(+{components['stoch_cross']})")

        components_str = ", ".join(comp_list) if comp_list else "None"

        # Add to tree
        values = (
            timestamp.strftime('%Y-%m-%d %H:%M'),
            'ENTRY',
            regime,
            f'{score}/4',
            components_str,
            f'{price:,.0f}',
            'Pending'
        )

        item_id = self.signal_tree.insert('', 0, values=values)

        # Store full signal data
        signal_record = {
            'id': item_id,
            'timestamp': timestamp,
            'type': 'ENTRY',
            'regime': regime,
            'score': score,
            'components': components,
            'price': price,
            'result': None
        }
        self.signals.insert(0, signal_record)

        # Limit history size
        if len(self.signals) > self.max_signals:
            removed = self.signals.pop()
            self.signal_tree.delete(removed['id'])

        self.update_statistics()

    def add_exit_signal(self, signal_data: Dict[str, Any]):
        """
        Add exit signal to history.

        Args:
            signal_data: Dictionary with exit signal details
                - timestamp: Exit time
                - exit_type: Exit reason (STOP_LOSS, FIRST_TARGET, FINAL_TARGET, BREAKEVEN)
                - price: Exit price
                - pnl: Profit/loss
                - pnl_pct: P&L percentage
        """
        timestamp = signal_data.get('timestamp', datetime.now())
        exit_type = signal_data.get('exit_type', 'UNKNOWN')
        price = signal_data.get('price', 0)
        pnl = signal_data.get('pnl', 0)
        pnl_pct = signal_data.get('pnl_pct', 0)

        # Determine result display
        if pnl >= 0:
            result_str = f'+{pnl_pct:.1f}%'
            result_color = 'green'
        else:
            result_str = f'{pnl_pct:.1f}%'
            result_color = 'red'

        # Add to tree
        values = (
            timestamp.strftime('%Y-%m-%d %H:%M'),
            exit_type,
            '-',
            '-',
            '-',
            f'{price:,.0f}',
            result_str
        )

        item_id = self.signal_tree.insert('', 0, values=values, tags=(result_color,))

        # Configure tag colors
        self.signal_tree.tag_configure('green', foreground='green')
        self.signal_tree.tag_configure('red', foreground='red')

        # Update corresponding entry signal result
        if len(self.signals) > 0:
            for signal in self.signals:
                if signal['type'] == 'ENTRY' and signal.get('result') is None:
                    signal['result'] = {
                        'exit_type': exit_type,
                        'pnl': pnl,
                        'pnl_pct': pnl_pct
                    }
                    # Update tree item
                    self.signal_tree.set(signal['id'], 'Result', result_str)
                    self.signal_tree.item(signal['id'], tags=(result_color,))
                    break

        # Store exit record
        exit_record = {
            'id': item_id,
            'timestamp': timestamp,
            'type': 'EXIT',
            'exit_type': exit_type,
            'price': price,
            'pnl': pnl,
            'pnl_pct': pnl_pct
        }
        self.signals.insert(0, exit_record)

        self.update_statistics()

    def add_position_event(self, event_data: Dict[str, Any]):
        """
        Add position management event (scaling, stop movement, etc).

        Args:
            event_data: Dictionary with event details
                - timestamp: Event time
                - event_type: Event type (SCALE_OUT, STOP_TRAIL, BREAKEVEN)
                - description: Event description
                - price: Current price
        """
        timestamp = event_data.get('timestamp', datetime.now())
        event_type = event_data.get('event_type', 'EVENT')
        description = event_data.get('description', '')
        price = event_data.get('price', 0)

        values = (
            timestamp.strftime('%Y-%m-%d %H:%M'),
            event_type,
            '-',
            '-',
            description,
            f'{price:,.0f}',
            '-'
        )

        item_id = self.signal_tree.insert('', 0, values=values, tags=('event',))
        self.signal_tree.tag_configure('event', foreground='blue')

        # Store event record
        event_record = {
            'id': item_id,
            'timestamp': timestamp,
            'type': 'EVENT',
            'event_type': event_type,
            'description': description,
            'price': price
        }
        self.signals.insert(0, event_record)

    def update_statistics(self):
        """Update statistics display"""
        if not self.signals:
            return

        # Count signals by type
        entry_signals = [s for s in self.signals if s['type'] == 'ENTRY']
        exit_signals = [s for s in self.signals if s['type'] == 'EXIT']

        # Total signals
        self.total_signals_var.set(str(len(entry_signals)))

        # Average score
        if entry_signals:
            avg_score = sum(s.get('score', 0) for s in entry_signals) / len(entry_signals)
            self.avg_score_var.set(f"{avg_score:.1f}")

        # Bullish regime count
        bullish_count = sum(1 for s in entry_signals if s.get('regime') == 'BULLISH')
        self.bullish_count_var.set(str(bullish_count))

        # Success rate (profitable exits)
        if exit_signals:
            profitable = sum(1 for s in exit_signals if s.get('pnl', 0) > 0)
            success_rate = (profitable / len(exit_signals)) * 100
            self.success_rate_var.set(f"{success_rate:.1f}%")

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
        """Refresh signal display"""
        # Clear tree
        for item in self.signal_tree.get_children():
            self.signal_tree.delete(item)

        # Rebuild from signals list
        for signal in reversed(self.signals):
            if signal['type'] == 'ENTRY':
                values = (
                    signal['timestamp'].strftime('%Y-%m-%d %H:%M'),
                    'ENTRY',
                    signal.get('regime', '-'),
                    f"{signal.get('score', 0)}/4",
                    self._format_components(signal.get('components', {})),
                    f"{signal.get('price', 0):,.0f}",
                    self._format_result(signal.get('result'))
                )
                signal['id'] = self.signal_tree.insert('', 0, values=values)
            elif signal['type'] == 'EXIT':
                pnl_pct = signal.get('pnl_pct', 0)
                result_str = f'+{pnl_pct:.1f}%' if pnl_pct >= 0 else f'{pnl_pct:.1f}%'
                tag = 'green' if pnl_pct >= 0 else 'red'

                values = (
                    signal['timestamp'].strftime('%Y-%m-%d %H:%M'),
                    signal.get('exit_type', 'EXIT'),
                    '-',
                    '-',
                    '-',
                    f"{signal.get('price', 0):,.0f}",
                    result_str
                )
                signal['id'] = self.signal_tree.insert('', 0, values=values, tags=(tag,))

        self.update_statistics()

    def _format_components(self, components: Dict[str, int]) -> str:
        """Format components dictionary to string"""
        comp_list = []
        if components.get('bb_touch', 0) > 0:
            comp_list.append(f"BB(+{components['bb_touch']})")
        if components.get('rsi_oversold', 0) > 0:
            comp_list.append(f"RSI(+{components['rsi_oversold']})")
        if components.get('stoch_cross', 0) > 0:
            comp_list.append(f"Stoch(+{components['stoch_cross']})")
        return ", ".join(comp_list) if comp_list else "None"

    def _format_result(self, result: Optional[Dict[str, Any]]) -> str:
        """Format result dictionary to string"""
        if not result:
            return 'Pending'

        pnl_pct = result.get('pnl_pct', 0)
        return f'+{pnl_pct:.1f}%' if pnl_pct >= 0 else f'{pnl_pct:.1f}%'

    def clear_signals(self):
        """Clear all signals"""
        if tk.messagebox.askyesno("확인", "모든 신호 기록을 삭제하시겠습니까?"):
            self.signals = []
            for item in self.signal_tree.get_children():
                self.signal_tree.delete(item)
            self.update_statistics()

    def export_signals(self):
        """Export signals to JSON file"""
        from tkinter import filedialog

        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )

        if file_path:
            try:
                with open(file_path, 'w') as f:
                    json.dump(self.signals, f, indent=2, default=str)
                tk.messagebox.showinfo("성공", f"신호 기록을 {file_path}에 저장했습니다.")
            except Exception as e:
                tk.messagebox.showerror("오류", f"저장 실패: {str(e)}")

    def load_signals(self, signals: List[Dict[str, Any]]):
        """Load signals from external source"""
        self.signals = signals
        self.refresh_signals()
