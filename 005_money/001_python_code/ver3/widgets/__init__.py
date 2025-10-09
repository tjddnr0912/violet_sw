"""
Ver3 GUI Widgets Module

This module contains custom widgets for the Ver3 multi-coin portfolio GUI.
"""

from .portfolio_overview_widget import PortfolioOverviewWidget
from .coin_selector_widget import CoinSelectorWidget
from .account_info_widget import AccountInfoWidget
from .settings_panel_widget import SettingsPanelWidget

__all__ = [
    'PortfolioOverviewWidget',
    'CoinSelectorWidget',
    'AccountInfoWidget',
    'SettingsPanelWidget',
]
