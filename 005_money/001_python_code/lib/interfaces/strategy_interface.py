"""
Strategy Interface - Protocol for trading strategy implementations

This module defines the protocol (structural typing) for strategy objects
used throughout the system.
"""

from typing import Protocol, Dict, Any, List, Optional
import pandas as pd


class StrategyProtocol(Protocol):
    """
    Protocol defining the interface for strategy objects.

    This uses structural subtyping (Protocol) rather than inheritance,
    allowing any class that implements these methods to be used as a strategy.
    """

    def analyze_market(self, symbol: str, interval: str) -> Dict[str, Any]:
        """
        Analyze market and generate trading signals.

        Args:
            symbol: Trading pair symbol
            interval: Candlestick interval

        Returns:
            Analysis results dictionary
        """
        ...

    def get_strategy_description(self) -> str:
        """Get strategy description."""
        ...

    def get_version_info(self) -> Dict[str, str]:
        """Get version metadata."""
        ...

    def get_supported_intervals(self) -> List[str]:
        """Get supported intervals."""
        ...

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate configuration."""
        ...
