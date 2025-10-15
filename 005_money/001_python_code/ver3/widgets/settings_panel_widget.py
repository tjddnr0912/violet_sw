"""
Settings Panel Widget - Configurable Trading Parameters

This widget provides a comprehensive settings panel for:
- Portfolio configuration (max positions)
- Entry scoring settings (min score, thresholds)
- Exit scoring settings (chandelier multiplier, profit targets)
- Risk management settings

Features:
- Input validation
- Apply button with callback
- Persistent settings support
- User-friendly layout with sections
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Any, Callable, Optional


class SettingsPanelWidget(ttk.LabelFrame):
    """
    Settings panel for configurable trading parameters.

    Allows users to modify:
    - Portfolio settings (max positions, default coins)
    - Entry scoring thresholds
    - Exit scoring parameters
    - Risk management limits
    """

    def __init__(self, parent, config: Dict[str, Any], on_apply_callback: Callable[[Dict], None]):
        """
        Initialize settings panel widget.

        Args:
            parent: Parent tkinter widget
            config: Current configuration dictionary
            on_apply_callback: Callback function called when settings applied
                              Receives updated config dictionary
        """
        super().__init__(parent, text="⚙️ Settings", padding=10)

        self.config = config
        self.on_apply = on_apply_callback

        # Settings variables
        self.setting_vars = {}

        # Create UI
        self.create_widgets()

        # Load current settings
        self.load_settings(config)

    def create_widgets(self):
        """Create settings input widgets"""
        # Configure grid
        self.columnconfigure(0, weight=1)

        # Create notebook for organized sections
        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # TAB 1: Portfolio Settings
        portfolio_tab = ttk.Frame(notebook, padding=10)
        notebook.add(portfolio_tab, text="Portfolio")
        self.create_portfolio_settings(portfolio_tab)

        # TAB 2: Entry Settings
        entry_tab = ttk.Frame(notebook, padding=10)
        notebook.add(entry_tab, text="Entry Scoring")
        self.create_entry_settings(entry_tab)

        # TAB 3: Exit Settings
        exit_tab = ttk.Frame(notebook, padding=10)
        notebook.add(exit_tab, text="Exit Scoring")
        self.create_exit_settings(exit_tab)

        # TAB 4: Risk Management
        risk_tab = ttk.Frame(notebook, padding=10)
        notebook.add(risk_tab, text="Risk Management")
        self.create_risk_settings(risk_tab)

        # Apply button
        button_frame = ttk.Frame(self)
        button_frame.grid(row=1, column=0, sticky=(tk.W, tk.E))

        self.apply_button = ttk.Button(
            button_frame,
            text="✅ Apply Settings",
            command=self.apply_settings,
            style='Big.TButton'
        )
        self.apply_button.pack(side=tk.RIGHT, padx=5)

        reset_button = ttk.Button(
            button_frame,
            text="↻ Reset to Defaults",
            command=self.reset_to_defaults
        )
        reset_button.pack(side=tk.RIGHT, padx=5)

    def create_portfolio_settings(self, parent):
        """Create portfolio configuration inputs"""
        parent.columnconfigure(1, weight=1)

        row = 0

        # Max positions
        ttk.Label(
            parent,
            text="Max Positions:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        max_pos_var = tk.IntVar(value=2)
        self.setting_vars['max_positions'] = max_pos_var

        max_pos_frame = ttk.Frame(parent)
        max_pos_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        max_pos_spinbox = ttk.Spinbox(
            max_pos_frame,
            from_=1,
            to=4,
            textvariable=max_pos_var,
            width=10
        )
        max_pos_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            max_pos_frame,
            text="(Max simultaneous positions)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

        row += 1

        # Position size
        ttk.Label(
            parent,
            text="Position Size (KRW):",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        position_size_var = tk.IntVar(value=50000)
        self.setting_vars['position_size_krw'] = position_size_var

        position_frame = ttk.Frame(parent)
        position_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        position_entry = ttk.Entry(
            position_frame,
            textvariable=position_size_var,
            width=12
        )
        position_entry.pack(side=tk.LEFT)

        ttk.Label(
            position_frame,
            text="(Amount per trade)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

        row += 1

        # Portfolio risk percentage
        ttk.Label(
            parent,
            text="Max Portfolio Risk %:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        portfolio_risk_var = tk.DoubleVar(value=6.0)
        self.setting_vars['max_portfolio_risk_pct'] = portfolio_risk_var

        risk_frame = ttk.Frame(parent)
        risk_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        risk_spinbox = ttk.Spinbox(
            risk_frame,
            from_=1.0,
            to=20.0,
            increment=0.5,
            textvariable=portfolio_risk_var,
            width=10
        )
        risk_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            risk_frame,
            text="(Total portfolio risk limit)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

    def create_entry_settings(self, parent):
        """Create entry scoring settings inputs"""
        parent.columnconfigure(1, weight=1)

        row = 0

        # Info label
        info_label = ttk.Label(
            parent,
            text="Entry scoring determines when to enter positions (0-4 points).",
            font=('Arial', 9),
            foreground='blue',
            wraplength=400
        )
        info_label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        row += 1

        # Min entry score
        ttk.Label(
            parent,
            text="Min Entry Score:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        min_entry_score_var = tk.IntVar(value=2)
        self.setting_vars['min_entry_score'] = min_entry_score_var

        entry_score_frame = ttk.Frame(parent)
        entry_score_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        entry_score_spinbox = ttk.Spinbox(
            entry_score_frame,
            from_=1,
            to=4,
            textvariable=min_entry_score_var,
            width=10
        )
        entry_score_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            entry_score_frame,
            text="(Higher = more selective)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

        row += 1

        # RSI oversold threshold
        ttk.Label(
            parent,
            text="RSI Oversold Threshold:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        rsi_threshold_var = tk.IntVar(value=35)
        self.setting_vars['rsi_oversold'] = rsi_threshold_var

        rsi_frame = ttk.Frame(parent)
        rsi_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        rsi_spinbox = ttk.Spinbox(
            rsi_frame,
            from_=20,
            to=40,
            textvariable=rsi_threshold_var,
            width=10
        )
        rsi_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            rsi_frame,
            text="(RSI < this = oversold)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

        row += 1

        # Stochastic oversold threshold
        ttk.Label(
            parent,
            text="Stochastic Oversold:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        stoch_threshold_var = tk.IntVar(value=20)
        self.setting_vars['stoch_oversold'] = stoch_threshold_var

        stoch_frame = ttk.Frame(parent)
        stoch_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        stoch_spinbox = ttk.Spinbox(
            stoch_frame,
            from_=10,
            to=30,
            textvariable=stoch_threshold_var,
            width=10
        )
        stoch_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            stoch_frame,
            text="(Stoch < this = oversold)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

    def create_exit_settings(self, parent):
        """Create exit scoring settings inputs"""
        parent.columnconfigure(1, weight=1)

        row = 0

        # Info label
        info_label = ttk.Label(
            parent,
            text="Exit settings control when to close positions and take profits.",
            font=('Arial', 9),
            foreground='blue',
            wraplength=400
        )
        info_label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        row += 1

        # Chandelier Exit ATR multiplier
        ttk.Label(
            parent,
            text="Chandelier ATR Multiplier:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        chandelier_var = tk.DoubleVar(value=3.0)
        self.setting_vars['chandelier_atr_multiplier'] = chandelier_var

        chandelier_frame = ttk.Frame(parent)
        chandelier_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        chandelier_spinbox = ttk.Spinbox(
            chandelier_frame,
            from_=1.5,
            to=5.0,
            increment=0.5,
            textvariable=chandelier_var,
            width=10
        )
        chandelier_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            chandelier_frame,
            text="(Higher = looser stop-loss)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

        row += 1

        # Profit target mode selection
        ttk.Label(
            parent,
            text="Profit Target Mode:",
            font=('Arial', 10, 'bold')
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        profit_mode_var = tk.StringVar(value='bb_based')
        self.setting_vars['profit_target_mode'] = profit_mode_var

        mode_frame = ttk.Frame(parent)
        mode_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        # Radio buttons for mode selection
        rb_bb = ttk.Radiobutton(
            mode_frame,
            text="BB-based (Middle/Upper)",
            variable=profit_mode_var,
            value='bb_based',
            command=self._on_profit_mode_changed
        )
        rb_bb.pack(side=tk.LEFT, padx=(0, 15))

        rb_pct = ttk.Radiobutton(
            mode_frame,
            text="Percentage-based",
            variable=profit_mode_var,
            value='percentage_based',
            command=self._on_profit_mode_changed
        )
        rb_pct.pack(side=tk.LEFT)

        row += 1

        # First profit target (TP1) - percentage mode only
        self.tp1_label = ttk.Label(
            parent,
            text="First Target (TP1) %:",
            font=('Arial', 10)
        )
        self.tp1_label.grid(row=row, column=0, sticky=tk.W, pady=5)

        tp1_var = tk.DoubleVar(value=1.5)
        self.setting_vars['tp1_target_pct'] = tp1_var

        tp1_frame = ttk.Frame(parent)
        tp1_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        self.tp1_spinbox = ttk.Spinbox(
            tp1_frame,
            from_=0.5,
            to=5.0,
            increment=0.5,
            textvariable=tp1_var,
            width=10
        )
        self.tp1_spinbox.pack(side=tk.LEFT)

        self.tp1_help_label = ttk.Label(
            tp1_frame,
            text="(Exit 50% of position)",
            font=('Arial', 9),
            foreground='gray'
        )
        self.tp1_help_label.pack(side=tk.LEFT, padx=10)

        row += 1

        # Second profit target (TP2) - percentage mode only
        self.tp2_label = ttk.Label(
            parent,
            text="Second Target (TP2) %:",
            font=('Arial', 10)
        )
        self.tp2_label.grid(row=row, column=0, sticky=tk.W, pady=5)

        tp2_var = tk.DoubleVar(value=2.5)
        self.setting_vars['tp2_target_pct'] = tp2_var

        tp2_frame = ttk.Frame(parent)
        tp2_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        self.tp2_spinbox = ttk.Spinbox(
            tp2_frame,
            from_=1.0,
            to=10.0,
            increment=0.5,
            textvariable=tp2_var,
            width=10
        )
        self.tp2_spinbox.pack(side=tk.LEFT)

        self.tp2_help_label = ttk.Label(
            tp2_frame,
            text="(Exit remaining position)",
            font=('Arial', 9),
            foreground='gray'
        )
        self.tp2_help_label.pack(side=tk.LEFT, padx=10)

        row += 1

        # Explanation label
        self.mode_explanation = ttk.Label(
            parent,
            text="BB mode: Uses Bollinger Bands (dynamic). Percentage mode: Fixed % from entry.",
            font=('Arial', 9),
            foreground='blue',
            wraplength=400
        )
        self.mode_explanation.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))

        # Store widgets for enable/disable control
        self.pct_mode_widgets = [
            self.tp1_label, self.tp1_spinbox, self.tp1_help_label,
            self.tp2_label, self.tp2_spinbox, self.tp2_help_label
        ]

        # Set initial state
        self._on_profit_mode_changed()

    def create_risk_settings(self, parent):
        """Create risk management settings inputs"""
        parent.columnconfigure(1, weight=1)

        row = 0

        # Info label
        info_label = ttk.Label(
            parent,
            text="Risk management settings protect your capital from excessive losses.",
            font=('Arial', 9),
            foreground='blue',
            wraplength=400
        )
        info_label.grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 10))

        row += 1

        # Max daily trades
        ttk.Label(
            parent,
            text="Max Daily Trades:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        max_daily_trades_var = tk.IntVar(value=10)
        self.setting_vars['max_daily_trades'] = max_daily_trades_var

        daily_trades_frame = ttk.Frame(parent)
        daily_trades_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        daily_trades_spinbox = ttk.Spinbox(
            daily_trades_frame,
            from_=1,
            to=50,
            textvariable=max_daily_trades_var,
            width=10
        )
        daily_trades_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            daily_trades_frame,
            text="(Prevents overtrading)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

        row += 1

        # Daily loss limit
        ttk.Label(
            parent,
            text="Daily Loss Limit %:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        daily_loss_var = tk.DoubleVar(value=5.0)
        self.setting_vars['daily_loss_limit_pct'] = daily_loss_var

        loss_frame = ttk.Frame(parent)
        loss_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        loss_spinbox = ttk.Spinbox(
            loss_frame,
            from_=1.0,
            to=20.0,
            increment=0.5,
            textvariable=daily_loss_var,
            width=10
        )
        loss_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            loss_frame,
            text="(Stop trading if exceeded)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

        row += 1

        # Max consecutive losses
        ttk.Label(
            parent,
            text="Max Consecutive Losses:",
            font=('Arial', 10)
        ).grid(row=row, column=0, sticky=tk.W, pady=5)

        consecutive_losses_var = tk.IntVar(value=3)
        self.setting_vars['max_consecutive_losses'] = consecutive_losses_var

        consecutive_frame = ttk.Frame(parent)
        consecutive_frame.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=5)

        consecutive_spinbox = ttk.Spinbox(
            consecutive_frame,
            from_=1,
            to=10,
            textvariable=consecutive_losses_var,
            width=10
        )
        consecutive_spinbox.pack(side=tk.LEFT)

        ttk.Label(
            consecutive_frame,
            text="(Pause after this many losses)",
            font=('Arial', 9),
            foreground='gray'
        ).pack(side=tk.LEFT, padx=10)

    def _on_profit_mode_changed(self):
        """Handle profit target mode change - enable/disable percentage inputs."""
        mode = self.setting_vars['profit_target_mode'].get()

        if mode == 'percentage_based':
            # Enable percentage inputs
            state = 'normal'
        else:
            # Disable percentage inputs (BB mode doesn't use them)
            state = 'disabled'

        # Update widget states
        self.tp1_spinbox.config(state=state)
        self.tp2_spinbox.config(state=state)

    def load_settings(self, config: Dict[str, Any]):
        """
        Load settings from configuration.

        Args:
            config: Configuration dictionary
        """
        self.config = config

        # Portfolio settings
        portfolio_config = config.get('PORTFOLIO_CONFIG', {})
        self.setting_vars['max_positions'].set(portfolio_config.get('max_positions', 2))
        self.setting_vars['max_portfolio_risk_pct'].set(portfolio_config.get('max_portfolio_risk_pct', 6.0))

        # Position sizing
        position_sizing = config.get('POSITION_SIZING_CONFIG', {})
        self.setting_vars['position_size_krw'].set(position_sizing.get('base_amount_krw', 50000))

        # Entry scoring
        entry_config = config.get('ENTRY_SCORING_CONFIG', {})
        self.setting_vars['min_entry_score'].set(entry_config.get('min_entry_score', 2))

        indicator_config = config.get('INDICATOR_CONFIG', {})
        self.setting_vars['rsi_oversold'].set(indicator_config.get('rsi_oversold', 35))
        self.setting_vars['stoch_oversold'].set(indicator_config.get('stoch_oversold', 20))

        # Exit scoring
        exit_config = config.get('EXIT_CONFIG', {})
        self.setting_vars['chandelier_atr_multiplier'].set(indicator_config.get('chandelier_multiplier', 3.0))

        # Profit target mode
        profit_mode = exit_config.get('profit_target_mode', 'bb_based')
        self.setting_vars['profit_target_mode'].set(profit_mode)

        # Profit targets (stored as percentages, displayed as percentages)
        self.setting_vars['tp1_target_pct'].set(exit_config.get('tp1_percentage', 1.5))
        self.setting_vars['tp2_target_pct'].set(exit_config.get('tp2_percentage', 2.5))

        # Update UI state based on mode
        self._on_profit_mode_changed()

        # Risk management
        risk_config = config.get('RISK_CONFIG', {})
        safety_config = config.get('SAFETY_CONFIG', {})

        self.setting_vars['max_daily_trades'].set(safety_config.get('max_daily_trades', 10))
        self.setting_vars['daily_loss_limit_pct'].set(risk_config.get('max_daily_loss_pct', 5.0))
        self.setting_vars['max_consecutive_losses'].set(risk_config.get('max_consecutive_losses', 3))

    def apply_settings(self):
        """Validate and apply settings"""
        # Validate inputs
        is_valid, errors = self.validate_settings()

        if not is_valid:
            error_msg = "Invalid settings:\n\n" + "\n".join(errors)
            messagebox.showerror("Validation Error", error_msg)
            return

        # Build updated config
        updated_config = self._build_updated_config()

        # Call callback
        try:
            self.on_apply(updated_config)
            messagebox.showinfo("Settings Applied", "Settings have been saved successfully!")
        except Exception as e:
            messagebox.showerror("Apply Failed", f"Failed to apply settings:\n{str(e)}")

    def validate_settings(self) -> tuple[bool, list[str]]:
        """
        Validate current settings.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Validate max positions
        max_pos = self.setting_vars['max_positions'].get()
        if max_pos < 1 or max_pos > 4:
            errors.append("Max positions must be between 1 and 4")

        # Validate position size
        position_size = self.setting_vars['position_size_krw'].get()
        if position_size < 10000 or position_size > 1000000:
            errors.append("Position size must be between 10,000 and 1,000,000 KRW")

        # Validate min entry score
        min_entry = self.setting_vars['min_entry_score'].get()
        if min_entry < 1 or min_entry > 4:
            errors.append("Min entry score must be between 1 and 4")

        # Validate profit targets (only if in percentage mode)
        profit_mode = self.setting_vars['profit_target_mode'].get()
        if profit_mode == 'percentage_based':
            tp1 = self.setting_vars['tp1_target_pct'].get()
            tp2 = self.setting_vars['tp2_target_pct'].get()

            if tp1 <= 0 or tp1 > 10:
                errors.append("TP1 target must be between 0.5% and 10%")

            if tp2 <= 0 or tp2 > 10:
                errors.append("TP2 target must be between 1% and 10%")

            if tp1 >= tp2:
                errors.append("TP2 target must be greater than TP1 target")

        # Validate risk limits
        daily_loss = self.setting_vars['daily_loss_limit_pct'].get()
        if daily_loss <= 0 or daily_loss > 20:
            errors.append("Daily loss limit must be between 1% and 20%")

        is_valid = len(errors) == 0
        return is_valid, errors

    def _build_updated_config(self) -> Dict[str, Any]:
        """
        Build updated configuration dictionary from current settings.

        Returns:
            Updated config dictionary
        """
        # Create deep copy of current config
        import copy
        updated_config = copy.deepcopy(self.config)

        # Update portfolio config
        updated_config['PORTFOLIO_CONFIG']['max_positions'] = self.setting_vars['max_positions'].get()
        updated_config['PORTFOLIO_CONFIG']['max_portfolio_risk_pct'] = self.setting_vars['max_portfolio_risk_pct'].get()

        # Update position sizing (sync both configs for consistency)
        position_size = self.setting_vars['position_size_krw'].get()
        updated_config['POSITION_SIZING_CONFIG']['base_amount_krw'] = position_size
        updated_config['TRADING_CONFIG']['trade_amount_krw'] = position_size

        # Update entry scoring
        updated_config['ENTRY_SCORING_CONFIG']['min_entry_score'] = self.setting_vars['min_entry_score'].get()
        updated_config['INDICATOR_CONFIG']['rsi_oversold'] = self.setting_vars['rsi_oversold'].get()
        updated_config['INDICATOR_CONFIG']['stoch_oversold'] = self.setting_vars['stoch_oversold'].get()

        # Update exit scoring
        updated_config['INDICATOR_CONFIG']['chandelier_multiplier'] = self.setting_vars['chandelier_atr_multiplier'].get()

        # Update profit target mode and percentages
        updated_config['EXIT_CONFIG']['profit_target_mode'] = self.setting_vars['profit_target_mode'].get()
        updated_config['EXIT_CONFIG']['tp1_percentage'] = self.setting_vars['tp1_target_pct'].get()
        updated_config['EXIT_CONFIG']['tp2_percentage'] = self.setting_vars['tp2_target_pct'].get()

        # Update risk management
        updated_config['RISK_CONFIG']['max_daily_loss_pct'] = self.setting_vars['daily_loss_limit_pct'].get()
        updated_config['RISK_CONFIG']['max_consecutive_losses'] = self.setting_vars['max_consecutive_losses'].get()
        updated_config['SAFETY_CONFIG']['max_daily_trades'] = self.setting_vars['max_daily_trades'].get()

        return updated_config

    def reset_to_defaults(self):
        """Reset all settings to default values"""
        if messagebox.askyesno("Reset Settings", "Reset all settings to default values?"):
            # Import default config
            from ver3 import config_v3
            default_config = config_v3.get_version_config()
            self.load_settings(default_config)
            messagebox.showinfo("Reset Complete", "Settings have been reset to defaults.")
