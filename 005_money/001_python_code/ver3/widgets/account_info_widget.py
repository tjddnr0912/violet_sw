"""
Account Information Widget - Account Balance and Holdings Display

This widget displays comprehensive account information including:
- KRW balance
- Holdings for each traded coin (avg price, quantity, P&L)
- Real-time updates

Features:
- Clean card-based layout
- Color-coded profit/loss
- Real-time balance tracking
- Integration with position tracking
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional
from datetime import datetime


class AccountInfoWidget(ttk.LabelFrame):
    """
    Account information display widget.

    Shows:
    - KRW balance
    - Holdings per coin with avg price, quantity, P&L
    - Real-time updates
    """

    def __init__(self, parent):
        """
        Initialize account info widget.

        Args:
            parent: Parent tkinter widget
        """
        super().__init__(parent, text="💰 Account Information", padding=10)

        # State
        self.balance_krw = 0.0
        self.holdings = {}  # coin -> {avg_price, quantity, current_price, pnl_pct}
        self.last_update = None

        # Create UI
        self.create_widgets()

    def create_widgets(self):
        """Create account info display widgets"""
        # Configure grid
        self.columnconfigure(0, weight=1)

        # Balance section
        balance_frame = ttk.Frame(self)
        balance_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        ttk.Label(
            balance_frame,
            text="KRW Balance:",
            font=('Arial', 11, 'bold')
        ).pack(side=tk.LEFT)

        self.balance_label = ttk.Label(
            balance_frame,
            text="0 KRW",
            font=('Arial', 11),
            foreground='blue'
        )
        self.balance_label.pack(side=tk.LEFT, padx=10)

        # Last update time
        self.update_time_label = ttk.Label(
            balance_frame,
            text="Last update: Never",
            font=('Arial', 9),
            foreground='gray'
        )
        self.update_time_label.pack(side=tk.RIGHT)

        # Holdings section
        holdings_label = ttk.Label(
            self,
            text="🪙 Holdings:",
            font=('Arial', 11, 'bold')
        )
        holdings_label.grid(row=1, column=0, sticky=tk.W, pady=(10, 5))

        # Holdings container (scrollable if needed)
        holdings_container = ttk.Frame(self)
        holdings_container.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        holdings_container.columnconfigure(0, weight=1)

        self.holdings_frame = ttk.Frame(holdings_container)
        self.holdings_frame.pack(fill=tk.BOTH, expand=True)

        # Placeholder text
        self.placeholder_label = ttk.Label(
            self.holdings_frame,
            text="No holdings yet...",
            font=('Arial', 10),
            foreground='gray'
        )
        self.placeholder_label.pack(pady=10)

        # Holdings widgets dictionary
        self.holding_widgets = {}  # coin -> frame

    def update_balance(self, balance: float):
        """
        Update KRW balance display.

        Args:
            balance: Current KRW balance
        """
        self.balance_krw = balance
        self.last_update = datetime.now()

        # Format balance with thousand separators
        balance_text = f"{balance:,.0f} KRW"
        self.balance_label.config(text=balance_text)

        # Update timestamp
        time_str = self.last_update.strftime('%H:%M:%S')
        self.update_time_label.config(text=f"Last update: {time_str}")

    def update_holding(self, coin: str, avg_price: float, quantity: float, current_price: float):
        """
        Update single coin holding information.

        Args:
            coin: Cryptocurrency symbol (e.g., 'BTC')
            avg_price: Average purchase price in KRW
            quantity: Quantity held
            current_price: Current market price in KRW
        """
        # Calculate P&L
        pnl_pct = self.calculate_pnl(avg_price, current_price)
        current_value = quantity * current_price

        # Store holding data
        self.holdings[coin] = {
            'avg_price': avg_price,
            'quantity': quantity,
            'current_price': current_price,
            'pnl_pct': pnl_pct,
            'current_value': current_value
        }

        # Update display
        self._update_holdings_display()

    def update_holdings_batch(self, holdings_data: Dict[str, Dict[str, float]]):
        """
        Update multiple holdings at once.

        Args:
            holdings_data: Dictionary of coin -> {avg_price, quantity, current_price}
        """
        self.holdings.clear()

        for coin, data in holdings_data.items():
            avg_price = data.get('avg_price', 0)
            quantity = data.get('quantity', 0)
            current_price = data.get('current_price', 0)

            if quantity > 0:  # Only show if we actually hold this coin
                pnl_pct = self.calculate_pnl(avg_price, current_price)
                current_value = quantity * current_price

                self.holdings[coin] = {
                    'avg_price': avg_price,
                    'quantity': quantity,
                    'current_price': current_price,
                    'pnl_pct': pnl_pct,
                    'current_value': current_value
                }

        self._update_holdings_display()

    def _update_holdings_display(self):
        """Update the holdings display widgets"""
        # Hide placeholder if we have holdings
        if self.holdings:
            self.placeholder_label.pack_forget()
        else:
            self.placeholder_label.pack(pady=10)
            return

        # Remove widgets for coins we no longer hold
        for coin in list(self.holding_widgets.keys()):
            if coin not in self.holdings:
                self.holding_widgets[coin]['frame'].destroy()
                del self.holding_widgets[coin]

        # Create or update widgets for each holding
        for coin, data in self.holdings.items():
            if coin not in self.holding_widgets:
                self._create_holding_widget(coin)

            self._update_holding_widget(coin, data)

    def _create_holding_widget(self, coin: str):
        """
        Create widget for a single coin holding.

        Args:
            coin: Cryptocurrency symbol
        """
        # Create frame for this holding
        holding_frame = ttk.Frame(self.holdings_frame, relief=tk.GROOVE, borderwidth=1)
        holding_frame.pack(fill=tk.X, pady=3)

        # Inner padding frame
        inner_frame = ttk.Frame(holding_frame)
        inner_frame.pack(fill=tk.X, padx=5, pady=5)

        # Coin name (left)
        coin_label = ttk.Label(
            inner_frame,
            text=coin,
            font=('Arial', 11, 'bold')
        )
        coin_label.pack(side=tk.LEFT)

        # P&L percentage (right)
        pnl_label = ttk.Label(
            inner_frame,
            text="+0.0%",
            font=('Arial', 11, 'bold')
        )
        pnl_label.pack(side=tk.RIGHT)

        # Details frame
        details_frame = ttk.Frame(holding_frame)
        details_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        # Avg price
        avg_label = ttk.Label(
            details_frame,
            text="Avg: 0 KRW",
            font=('Arial', 9)
        )
        avg_label.pack(anchor=tk.W)

        # Quantity
        qty_label = ttk.Label(
            details_frame,
            text="Qty: 0",
            font=('Arial', 9)
        )
        qty_label.pack(anchor=tk.W)

        # Current value
        value_label = ttk.Label(
            details_frame,
            text="Value: 0 KRW",
            font=('Arial', 9)
        )
        value_label.pack(anchor=tk.W)

        # Store references
        self.holding_widgets[coin] = {
            'frame': holding_frame,
            'pnl_label': pnl_label,
            'avg_label': avg_label,
            'qty_label': qty_label,
            'value_label': value_label
        }

    def _update_holding_widget(self, coin: str, data: Dict[str, float]):
        """
        Update existing holding widget with new data.

        Args:
            coin: Cryptocurrency symbol
            data: Holding data dictionary
        """
        if coin not in self.holding_widgets:
            return

        widgets = self.holding_widgets[coin]

        # Extract data
        avg_price = data['avg_price']
        quantity = data['quantity']
        current_price = data['current_price']
        pnl_pct = data['pnl_pct']
        current_value = data['current_value']

        # Update P&L label
        pnl_sign = '+' if pnl_pct >= 0 else ''
        pnl_text = f"{pnl_sign}{pnl_pct:.2f}%"
        pnl_color = 'green' if pnl_pct >= 0 else 'red'
        widgets['pnl_label'].config(text=pnl_text, foreground=pnl_color)

        # Update avg price
        avg_text = f"Avg: {avg_price:,.0f} KRW"
        widgets['avg_label'].config(text=avg_text)

        # Update quantity
        qty_text = f"Qty: {quantity:.8f}".rstrip('0').rstrip('.')
        widgets['qty_label'].config(text=qty_text)

        # Update current value
        value_text = f"Value: {current_value:,.0f} KRW"
        widgets['value_label'].config(text=value_text)

    def calculate_pnl(self, avg_price: float, current_price: float) -> float:
        """
        Calculate profit/loss percentage.

        Args:
            avg_price: Average purchase price
            current_price: Current market price

        Returns:
            P&L percentage (e.g., 2.5 for +2.5%, -1.2 for -1.2%)
        """
        if avg_price <= 0:
            return 0.0

        pnl_pct = ((current_price - avg_price) / avg_price) * 100
        return pnl_pct

    def clear_holdings(self):
        """Clear all holdings display"""
        self.holdings.clear()

        for coin, widgets in self.holding_widgets.items():
            widgets['frame'].destroy()

        self.holding_widgets.clear()
        self.placeholder_label.pack(pady=10)

    def get_total_holdings_value(self) -> float:
        """
        Calculate total value of all holdings in KRW.

        Returns:
            Total holdings value in KRW
        """
        return sum(h['current_value'] for h in self.holdings.values())

    def get_total_account_value(self) -> float:
        """
        Calculate total account value (balance + holdings).

        Returns:
            Total account value in KRW
        """
        return self.balance_krw + self.get_total_holdings_value()
