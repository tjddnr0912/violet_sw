"""
Version 2 - Bitcoin Multi-Timeframe Trading Strategy

Complete Backtrader-based implementation with:
- Multi-timeframe analysis (Daily regime + 4H execution)
- Score-based entry system (3+ points required)
- ATR-based Chandelier Exit
- Position scaling protocol
- Comprehensive risk management

Usage:
    # For backtesting
    from ver2.main_v2 import main
    main()

    # For strategy access
    from ver2.backtrader_strategy_v2 import BitcoinMultiTimeframeStrategy

    # For configuration
    from ver2.config_v2 import get_version_config

Author: Trading Bot Team
Date: 2025-10-03
Framework: Backtrader
"""

VERSION_METADATA = {
    "name": "ver2",
    "display_name": "Multi-Timeframe Trend-Following Strategy",
    "description": "Professional-grade strategy using Daily regime filter + 4H entry signals with Chandelier Exit",
    "author": "Trading Bot Team",
    "date": "2025-10",
    "framework": "Backtrader",
    "status": "Production Ready"
}

# Module imports for convenience
from .config_v2 import get_version_config, validate_version_config

# Backtrader-dependent imports (graceful degradation if backtrader not installed)
try:
    from .backtrader_strategy_v2 import BitcoinMultiTimeframeStrategy
    from .regime_filter_v2 import RegimeFilter
    from .entry_signals_v2 import EntrySignalScorer
    from .position_manager_v2 import PositionManager
    from .risk_manager_v2 import RiskManager
    from .indicators_v2 import IndicatorCalculator
    BACKTRADER_AVAILABLE = True
except ImportError as e:
    BACKTRADER_AVAILABLE = False
    _backtrader_import_error = str(e)

# GUI imports (optional - won't fail if tkinter not available)
try:
    from .gui_app_v2 import TradingBotGUIV2
    from .gui_trading_bot_v2 import GUITradingBotV2
    from .chart_widget_v2 import ChartWidgetV2
    from .signal_history_widget_v2 import SignalHistoryWidgetV2
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False

__all__ = [
    'VERSION_METADATA',
    'get_version_config',
    'validate_version_config',
]

# Add backtrader exports if available
if BACKTRADER_AVAILABLE:
    __all__.extend([
        'BitcoinMultiTimeframeStrategy',
        'RegimeFilter',
        'EntrySignalScorer',
        'PositionManager',
        'RiskManager',
        'IndicatorCalculator',
    ])

# Add GUI exports if available
if GUI_AVAILABLE:
    __all__.extend([
        'TradingBotGUIV2',
        'GUITradingBotV2',
        'ChartWidgetV2',
        'SignalHistoryWidgetV2',
    ])

__version__ = '2.0.0'
