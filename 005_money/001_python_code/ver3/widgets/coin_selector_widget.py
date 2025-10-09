"""
Coin Selector Widget - Multi-Coin Selection Panel

This widget allows users to select which coins to monitor in the portfolio
with dynamic checkbox controls and validation.

Features:
- Checkboxes for each available coin (BTC, ETH, XRP, SOL)
- Default selections from config
- Apply Changes button with validation
- Real-time coin count display
- Min/max coin limit enforcement
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import List, Dict, Callable, Optional


class CoinSelectorWidget(ttk.LabelFrame):
    """
    Multi-coin selection panel.

    Allows users to:
    - Select which coins to monitor
    - Apply changes with validation
    - See current monitoring count
    """

    def __init__(
        self,
        parent,
        available_coins: List[str],
        default_coins: List[str],
        min_coins: int = 1,
        max_coins: int = 4,
        on_change_callback: Optional[Callable[[List[str]], None]] = None
    ):
        """
        Initialize coin selector widget.

        Args:
            parent: Parent tkinter widget
            available_coins: List of all available coins
            default_coins: List of initially selected coins
            min_coins: Minimum coins that must be selected (default: 1)
            max_coins: Maximum coins that can be selected (default: 4)
            on_change_callback: Callback function called when coins are changed
                               Function signature: callback(new_coins: List[str])
        """
        super().__init__(parent, text="Select Coins to Monitor", padding=10)

        self.available_coins = available_coins
        self.default_coins = default_coins
        self.min_coins = min_coins
        self.max_coins = max_coins
        self.on_change_callback = on_change_callback

        # Checkbox variables
        self.coin_vars = {}  # coin -> BooleanVar

        # Create UI
        self.create_widgets()

    def create_widgets(self):
        """Create coin selector UI"""
        # Info label
        info_frame = ttk.Frame(self)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        info_label = ttk.Label(
            info_frame,
            text=f"Select {self.min_coins}-{self.max_coins} coins to monitor:",
            font=('Arial', 10)
        )
        info_label.pack(side=tk.LEFT)

        # Current count label
        self.count_label = ttk.Label(
            info_frame,
            text=f"Currently monitoring: {len(self.default_coins)} coins",
            font=('Arial', 10, 'bold'),
            foreground='blue'
        )
        self.count_label.pack(side=tk.RIGHT)

        # Checkboxes frame
        checkboxes_frame = ttk.Frame(self)
        checkboxes_frame.pack(fill=tk.X, pady=(0, 10))

        # Create checkbox for each coin
        for i, coin in enumerate(self.available_coins):
            # Create BooleanVar
            var = tk.BooleanVar(value=(coin in self.default_coins))
            self.coin_vars[coin] = var

            # Create checkbox with coin-specific color
            cb = ttk.Checkbutton(
                checkboxes_frame,
                text=f"{coin} ({self._get_coin_description(coin)})",
                variable=var,
                command=self._on_checkbox_changed
            )
            cb.grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)

        # Button frame
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X)

        # Apply button
        self.apply_button = ttk.Button(
            button_frame,
            text="Apply Changes",
            command=self._apply_changes
        )
        self.apply_button.pack(side=tk.LEFT, padx=5)

        # Reset button
        reset_button = ttk.Button(
            button_frame,
            text="Reset to Default",
            command=self._reset_to_default
        )
        reset_button.pack(side=tk.LEFT, padx=5)

        # Status label
        self.status_label = ttk.Label(
            button_frame,
            text="",
            foreground='gray'
        )
        self.status_label.pack(side=tk.LEFT, padx=10)

    def _get_coin_description(self, coin: str) -> str:
        """
        Get human-readable description for coin.

        Args:
            coin: Cryptocurrency symbol

        Returns:
            Description string
        """
        descriptions = {
            'BTC': 'Bitcoin',
            'ETH': 'Ethereum',
            'XRP': 'Ripple',
            'SOL': 'Solana',
        }
        return descriptions.get(coin, coin)

    def _on_checkbox_changed(self):
        """Handle checkbox state change"""
        selected = self.get_selected_coins()
        count = len(selected)

        # Update count label
        self.count_label.config(text=f"Currently monitoring: {count} coins")

        # Update count label color based on validity
        if count < self.min_coins:
            self.count_label.config(foreground='red')
            self.status_label.config(
                text=f"⚠️ Select at least {self.min_coins} coins",
                foreground='red'
            )
        elif count > self.max_coins:
            self.count_label.config(foreground='red')
            self.status_label.config(
                text=f"⚠️ Select at most {self.max_coins} coins",
                foreground='red'
            )
        else:
            self.count_label.config(foreground='green')
            self.status_label.config(text="✅ Valid selection", foreground='green')

    def _apply_changes(self):
        """Apply selected coins"""
        selected = self.get_selected_coins()

        # Validate selection
        if len(selected) < self.min_coins:
            messagebox.showwarning(
                "Invalid Selection",
                f"Please select at least {self.min_coins} coin(s)."
            )
            return

        if len(selected) > self.max_coins:
            messagebox.showwarning(
                "Invalid Selection",
                f"Please select at most {self.max_coins} coin(s)."
            )
            return

        # Confirm change
        if selected != self.default_coins:
            message = f"Update monitored coins to: {', '.join(selected)}?\n\n"
            message += "This will restart the portfolio analysis with the new coins."

            if messagebox.askyesno("Confirm Change", message):
                # Update default coins
                self.default_coins = selected

                # Call callback
                if self.on_change_callback:
                    try:
                        self.on_change_callback(selected)
                        self.status_label.config(
                            text="✅ Coins updated successfully",
                            foreground='green'
                        )
                    except Exception as e:
                        messagebox.showerror(
                            "Update Failed",
                            f"Failed to update coins: {str(e)}"
                        )
                        self.status_label.config(
                            text=f"❌ Update failed: {str(e)}",
                            foreground='red'
                        )
            else:
                self.status_label.config(text="Change cancelled", foreground='gray')
        else:
            self.status_label.config(text="No changes to apply", foreground='gray')

    def _reset_to_default(self):
        """Reset checkboxes to default selection"""
        for coin, var in self.coin_vars.items():
            var.set(coin in self.default_coins)

        self._on_checkbox_changed()
        self.status_label.config(text="Reset to default", foreground='gray')

    def get_selected_coins(self) -> List[str]:
        """
        Get list of currently selected coins.

        Returns:
            List of coin symbols that are checked
        """
        return [coin for coin, var in self.coin_vars.items() if var.get()]

    def set_enabled(self, enabled: bool):
        """
        Enable/disable all checkboxes and buttons.

        Args:
            enabled: True to enable, False to disable
        """
        state = 'normal' if enabled else 'disabled'

        # Disable checkboxes (need to access children)
        for child in self.winfo_children():
            if isinstance(child, ttk.Frame):
                for widget in child.winfo_children():
                    if isinstance(widget, ttk.Checkbutton) or isinstance(widget, ttk.Button):
                        widget.config(state=state)

    def update_coin_status(self, coin_statuses: Dict[str, str]):
        """
        Update visual status of coins (e.g., add badge for active positions).

        Args:
            coin_statuses: Dict mapping coin -> status string
                          e.g., {'BTC': 'POSITION_OPEN', 'ETH': 'MONITORING'}
        """
        # This is a placeholder for future enhancement
        # Could add visual indicators next to checkboxes
        pass
