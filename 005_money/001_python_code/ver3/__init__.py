"""
Version 3: Portfolio Multi-Coin Trading Strategy

This version implements a sophisticated multi-coin portfolio management system
that simultaneously monitors and trades 2-3 cryptocurrencies (BTC, ETH, XRP, SOL)
with portfolio-level risk management and parallel market analysis.

Key Features:
- Multi-coin simultaneous trading (2-3 coins)
- Portfolio-level risk management (max 2 positions, 6% total risk)
- Parallel market analysis using ThreadPoolExecutor
- Thread-safe execution with position locks
- Smart entry prioritization (highest-scoring signals first)
- Reuses ver2 strategy for individual coin analysis

Architecture:
- CoinMonitor: Wraps ver2 strategy for single coin analysis
- PortfolioManagerV3: Coordinates multi-coin trading decisions
- Thread-safe LiveExecutorV3: Concurrent order execution
- Multi-coin GUI: Portfolio overview and per-coin tabs

Usage:
    from ver3 import get_version_instance

    config = get_version_config()
    bot = get_version_instance(config)
    bot.run()
"""

from typing import Dict, Any

# Version metadata
VERSION_METADATA = {
    'name': 'ver3',
    'display_name': 'Portfolio Multi-Coin Strategy',
    'description': 'Advanced multi-coin trading with portfolio management, parallel analysis, and coordinated risk controls',
    'author': 'Claude AI Assistant',
    'date': '2025-10-08',
    'features': [
        'Multi-coin simultaneous trading (2-3 coins)',
        'Portfolio-level risk management',
        'Parallel market analysis with ThreadPoolExecutor',
        'Thread-safe execution',
        'Smart entry prioritization by score',
        'Reuses ver2 strategy for proven signals',
        'Multi-coin GUI dashboard',
        'Independent from ver1/ver2',
    ],
    'strategy': 'Portfolio Manager Pattern',
    'base_strategy': 'ver2 (Multi-Timeframe Stability)',
}


def get_version_instance(config: Dict[str, Any]):
    """
    Factory function to create Ver3 trading bot instance.

    Args:
        config: Configuration dictionary from config_v3.py

    Returns:
        TradingBotV3 instance ready to run

    Example:
        >>> from ver3 import get_version_instance
        >>> from ver3.config_v3 import get_version_config
        >>> config = get_version_config()
        >>> bot = get_version_instance(config)
        >>> bot.run()
    """
    from ver3.trading_bot_v3 import TradingBotV3
    return TradingBotV3(config)


def get_version_metadata() -> Dict[str, Any]:
    """
    Get version metadata.

    Returns:
        Dictionary with version information
    """
    return VERSION_METADATA.copy()


# Export main classes
__all__ = [
    'VERSION_METADATA',
    'get_version_instance',
    'get_version_metadata',
]
