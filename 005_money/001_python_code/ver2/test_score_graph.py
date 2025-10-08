#!/usr/bin/env python3
"""
Quick test to demonstrate the Score Trend Graph feature
Creates sample data and opens the graph window
"""

import tkinter as tk
from datetime import datetime, timedelta
from score_monitoring_widget_v2 import ScoreMonitoringWidgetV2

# Create root window
root = tk.Tk()
root.title("Score Trend Graph Test")
root.geometry("1100x750")

# Create widget
widget = ScoreMonitoringWidgetV2(root)

# Generate realistic sample data (2 hours worth)
print("Generating sample data...")
base_time = datetime.now() - timedelta(hours=2)

# Simulate various market conditions
for i in range(120):  # 120 minutes = 2 hours
    # Create varying scores to show different patterns
    if i < 20:
        # Low activity period
        score = i % 2
        components = {
            'bb_touch': 0,
            'rsi_oversold': 0,
            'stoch_cross': 0
        }
    elif i < 40:
        # Building momentum
        score = min(2, (i - 20) // 5)
        components = {
            'bb_touch': 1 if score >= 1 else 0,
            'rsi_oversold': 1 if score >= 2 else 0,
            'stoch_cross': 0
        }
    elif i < 50:
        # Strong entry signals (3-4 points)
        score = 3 + (i % 2)
        components = {
            'bb_touch': 1,
            'rsi_oversold': 1,
            'stoch_cross': 2 if score >= 4 else 1
        }
    elif i < 70:
        # Declining signals
        score = max(0, 4 - ((i - 50) // 4))
        components = {
            'bb_touch': 1 if score >= 2 else 0,
            'rsi_oversold': 1 if score >= 3 else 0,
            'stoch_cross': 2 if score >= 4 else 0
        }
    else:
        # Random fluctuation
        score = (i + (i % 7)) % 5
        components = {
            'bb_touch': 1 if score >= 1 else 0,
            'rsi_oversold': 1 if score >= 2 else 0,
            'stoch_cross': 2 if score >= 4 else (1 if score >= 3 else 0)
        }

    regime_idx = i % 4
    regimes = ['BULLISH', 'BULLISH', 'NEUTRAL', 'BEARISH']
    regime = regimes[regime_idx]

    widget.add_score_check({
        'timestamp': base_time + timedelta(minutes=i),
        'score': score,
        'components': components,
        'regime': regime,
        'price': 170000000 + (i * 15000) + ((i % 10) * 5000)
    })

print(f"Added {len(widget.score_checks)} score checks")

# Automatically open the graph window after a short delay
def open_graph():
    print("Opening score trend graph...")
    widget.show_score_trend()

root.after(500, open_graph)

print("\nTest GUI is running!")
print("- Main window shows the score monitoring table")
print("- Graph window will open automatically")
print("- Try the 'Component Breakdown' checkbox in the graph")
print("- Use the matplotlib toolbar to zoom/pan/save")
print("\nClose the windows to exit.")

root.mainloop()
