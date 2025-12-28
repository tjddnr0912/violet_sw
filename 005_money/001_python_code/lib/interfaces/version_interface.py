"""
Version Interface - Abstract Base Class for Trading Bot Versions
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
import pandas as pd


class VersionInterface(ABC):
    """Abstract base class that all trading bot versions must implement."""

    VERSION_NAME: str
    VERSION_DISPLAY_NAME: str
    VERSION_DESCRIPTION: str
    VERSION_AUTHOR: str
    VERSION_DATE: str

    @abstractmethod
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        pass

    @abstractmethod
    def get_config(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def analyze_market(self, coin_symbol: str, interval: str = "1h", limit: int = 200) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_indicator_names(self) -> List[str]:
        pass

    @abstractmethod
    def get_supported_intervals(self) -> List[str]:
        pass

    @abstractmethod
    def validate_configuration(self) -> Tuple[bool, List[str]]:
        pass

    @abstractmethod
    def get_chart_config(self) -> Dict[str, Any]:
        pass
