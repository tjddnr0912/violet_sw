"""
Portfolio Overview Widget - Multi-Coin Portfolio Summary Table

This widget displays a comprehensive overview of all coins in the portfolio
with real-time status updates.

Features:
- Treeview table showing all monitored coins
- Columns: Coin, Status, Entry Score, Position, P&L, Action
- Color-coded status indicators
- Real-time data updates
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, List, Optional


# Coin color scheme for visual distinction
COIN_COLORS = {
    'BTC': '#FFC107',  # Yellow
    'ETH': '#2196F3',  # Blue
    'XRP': '#4CAF50',  # Green
    'SOL': '#9C27B0',  # Purple
}


class PortfolioOverviewWidget(ttk.Frame):
    """
    Portfolio summary table widget.

    Displays real-time portfolio overview with:
    - Per-coin analysis status
    - Position information
    - P&L tracking
    - Entry/exit scores
    """

    def __init__(self, parent):
        """
        Initialize portfolio overview widget.

        Args:
            parent: Parent tkinter widget
        """
        super().__init__(parent)

        # Widget state
        self.coin_items = {}  # coin -> treeview item ID

        # Create UI
        self.create_widgets()

    def create_widgets(self):
        """Create portfolio overview table"""
        # Title
        title_frame = ttk.Frame(self)
        title_frame.pack(fill=tk.X, padx=5, pady=(5, 0))

        title_label = ttk.Label(
            title_frame,
            text="Portfolio Overview",
            font=('Arial', 14, 'bold')
        )
        title_label.pack(side=tk.LEFT)

        # Summary stats
        self.summary_label = ttk.Label(
            title_frame,
            text="Positions: 0/2 | Total P&L: +0 KRW | Risk: 0%",
            font=('Arial', 10)
        )
        self.summary_label.pack(side=tk.RIGHT, padx=10)

        # Table frame with scrollbar
        table_frame = ttk.Frame(self)
        table_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Configure table columns
        columns = ('coin', 'status', 'score', 'position', 'pnl', 'action')

        self.tree = ttk.Treeview(table_frame, columns=columns, show='headings', height=8)

        # Define headings
        self.tree.heading('coin', text='Coin')
        self.tree.heading('status', text='Status')
        self.tree.heading('score', text='Entry Score')
        self.tree.heading('position', text='Position')
        self.tree.heading('pnl', text='P&L (KRW)')
        self.tree.heading('action', text='Last Action')

        # Configure column widths
        self.tree.column('coin', width=80, anchor='center')
        self.tree.column('status', width=100, anchor='center')
        self.tree.column('score', width=100, anchor='center')
        self.tree.column('position', width=150, anchor='center')
        self.tree.column('pnl', width=120, anchor='center')
        self.tree.column('action', width=100, anchor='center')

        # Add scrollbar
        scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Pack table and scrollbar
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Configure row colors
        self.tree.tag_configure('bullish', foreground='green')
        self.tree.tag_configure('bearish', foreground='red')
        self.tree.tag_configure('neutral', foreground='gray')
        self.tree.tag_configure('position_open', background='#ffffcc')

    def update_data(self, portfolio_summary: Dict[str, Any]):
        """
        Update table with latest portfolio data.

        Args:
            portfolio_summary: Portfolio summary from PortfolioManagerV3.get_portfolio_summary()
                Expected format:
                {
                    'total_positions': int,
                    'max_positions': int,
                    'total_pnl_krw': float,
                    'coins': {
                        'BTC': {
                            'analysis': {...},
                            'position': {...},
                            'last_update': str
                        },
                        ...
                    },
                    'last_decisions': List[Tuple[str, str]]
                }
        """
        # Update summary stats
        total_pos = portfolio_summary.get('total_positions', 0)
        max_pos = portfolio_summary.get('max_positions', 2)
        total_pnl = portfolio_summary.get('total_pnl_krw', 0)

        # Calculate portfolio risk percentage (simplified)
        portfolio_risk = (total_pos / max_pos * 100) if max_pos > 0 else 0

        # Update summary label
        pnl_sign = '+' if total_pnl >= 0 else ''
        self.summary_label.config(
            text=f"Positions: {total_pos}/{max_pos} | Total P&L: {pnl_sign}{total_pnl:,.0f} KRW | Risk: {portfolio_risk:.1f}%"
        )

        # Update per-coin rows
        coins_data = portfolio_summary.get('coins', {})

        for coin, data in coins_data.items():
            self._update_coin_row(coin, data)

    def _update_coin_row(self, coin: str, data: Dict[str, Any]):
        """
        Update single coin row in table.

        Args:
            coin: Cryptocurrency symbol (e.g., 'BTC')
            data: Coin data dictionary with 'analysis' and 'position' keys
        """
        analysis = data.get('analysis', {})
        position = data.get('position', {})

        # Extract data
        regime = analysis.get('market_regime', 'neutral')
        entry_score = analysis.get('entry_score', 0)
        action = analysis.get('action', 'HOLD')

        has_position = position.get('has_position', False)
        position_text = '-'
        pnl = 0

        if has_position:
            entry_price = position.get('entry_price', 0)
            size = position.get('size', 0)
            pnl = position.get('pnl', 0)
            position_text = f"{size:.6f} @ {entry_price:,.0f}"

        # Status indicator
        if has_position:
            status = f"OPEN ({regime.upper()})"
        else:
            status = regime.upper()

        # Format entry score
        score_text = f"{entry_score}/4"

        # Format P&L
        if has_position:
            pnl_sign = '+' if pnl >= 0 else ''
            pnl_text = f"{pnl_sign}{pnl:,.0f}"
        else:
            pnl_text = '-'

        # Row values
        values = (coin, status, score_text, position_text, pnl_text, action)

        # Determine row tags for coloring
        tags = []
        if regime == 'bullish':
            tags.append('bullish')
        elif regime == 'bearish':
            tags.append('bearish')
        else:
            tags.append('neutral')

        if has_position:
            tags.append('position_open')

        # Update or insert row
        if coin in self.coin_items:
            # Update existing row
            item_id = self.coin_items[coin]
            self.tree.item(item_id, values=values, tags=tags)
        else:
            # Insert new row
            item_id = self.tree.insert('', tk.END, values=values, tags=tags)
            self.coin_items[coin] = item_id

    def clear(self):
        """Clear all rows from table"""
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.coin_items.clear()

    def get_selected_coin(self) -> Optional[str]:
        """
        Get currently selected coin in table.

        Returns:
            Coin symbol or None if no selection
        """
        selection = self.tree.selection()
        if selection:
            item = selection[0]
            values = self.tree.item(item, 'values')
            if values:
                return values[0]  # First column is coin symbol
        return None
