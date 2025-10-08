#!/usr/bin/env python3
"""
Test script for enhanced V2 Signal History Widget

This script demonstrates the new features:
- Color-coded entry scores (0-4)
- Regime-aware statistics
- Score distribution analysis
- Filter capabilities
- CSV/JSON export
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
import random
from signal_history_widget_v2 import SignalHistoryWidgetV2


def generate_sample_data(widget):
    """Generate sample signals to test the widget"""

    regimes = ['BULLISH', 'BEARISH', 'NEUTRAL']
    scores = [0, 1, 2, 3, 4]

    # Generate 20 entry signals with varying scores and regimes
    for i in range(20):
        timestamp = datetime.now() - timedelta(hours=20-i)
        regime = random.choice(regimes)
        score = random.choice(scores)

        # Generate components based on score
        components = {'bb_touch': 0, 'rsi_oversold': 0, 'stoch_cross': 0}

        if score >= 1:
            if random.random() > 0.5:
                components['bb_touch'] = 1
            else:
                components['rsi_oversold'] = 1

        if score >= 2:
            if components['bb_touch'] == 0:
                components['bb_touch'] = 1
            elif components['rsi_oversold'] == 0:
                components['rsi_oversold'] = 1

        if score >= 3:
            components['stoch_cross'] = 2

        # Add entry signal
        entry_data = {
            'timestamp': timestamp,
            'regime': regime,
            'score': score,
            'components': components,
            'price': 50000000 + random.randint(-5000000, 5000000),
            'coin': 'BTC'
        }

        widget.add_entry_signal(entry_data)

        # Simulate exit for some trades (70% completion rate)
        if random.random() < 0.7:
            exit_timestamp = timestamp + timedelta(hours=random.randint(2, 8))

            # Higher scores tend to have better outcomes
            if score >= 3:
                pnl_pct = random.uniform(-2, 8)  # Better odds
            elif score >= 2:
                pnl_pct = random.uniform(-3, 5)  # Moderate odds
            else:
                pnl_pct = random.uniform(-5, 3)  # Worse odds

            pnl = entry_data['price'] * (pnl_pct / 100)

            exit_types = ['STOP_LOSS', 'FIRST_TARGET', 'FINAL_TARGET', 'BREAKEVEN']
            if pnl_pct > 0:
                exit_type = random.choice(['FIRST_TARGET', 'FINAL_TARGET'])
            else:
                exit_type = random.choice(['STOP_LOSS', 'BREAKEVEN'])

            exit_data = {
                'timestamp': exit_timestamp,
                'exit_type': exit_type,
                'price': entry_data['price'] + pnl,
                'pnl': pnl,
                'pnl_pct': pnl_pct,
                'coin': 'BTC'
            }

            widget.add_exit_signal(exit_data)

            # Add some position events for variety
            if random.random() < 0.3:
                event_timestamp = timestamp + timedelta(hours=1)
                event_data = {
                    'timestamp': event_timestamp,
                    'event_type': 'STOP_TRAIL',
                    'description': 'Stop trailed upward',
                    'price': entry_data['price'] + 100000,
                    'coin': 'BTC'
                }
                widget.add_position_event(event_data)


def main():
    """Main test application"""
    root = tk.Tk()
    root.title("V2 Signal History Widget - Test Demo")
    root.geometry("1200x800")

    # Create main frame
    main_frame = ttk.Frame(root, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # Title
    title_label = ttk.Label(
        main_frame,
        text="Enhanced V2 Signal History Widget Demo",
        font=('Arial', 14, 'bold')
    )
    title_label.pack(pady=(0, 10))

    # Info label
    info_label = ttk.Label(
        main_frame,
        text="This demo showcases v2's unique 0-4 point scoring system with color coding and advanced statistics",
        font=('Arial', 10)
    )
    info_label.pack(pady=(0, 10))

    # Create signal history widget
    widget_frame = ttk.Frame(main_frame)
    widget_frame.pack(fill=tk.BOTH, expand=True)

    signal_widget = SignalHistoryWidgetV2(widget_frame)

    # Generate sample data
    generate_sample_data(signal_widget)

    # Instructions
    instructions = ttk.Label(
        main_frame,
        text="Try: Filters (minimum score, regime, result) | Detailed Stats button | Export CSV/JSON | Double-click rows for details",
        font=('Arial', 9),
        foreground='gray'
    )
    instructions.pack(pady=(10, 0))

    root.mainloop()


if __name__ == "__main__":
    main()
