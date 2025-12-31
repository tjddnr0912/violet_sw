# Stock Auto Trading System - Main Source Package
from .engine import TradingEngine, EngineConfig, EngineState
from .quant_engine import QuantTradingEngine, QuantEngineConfig

__version__ = "1.0.0"

__all__ = [
    # 기존 엔진
    "TradingEngine",
    "EngineConfig",
    "EngineState",
    # 퀀트 엔진
    "QuantTradingEngine",
    "QuantEngineConfig"
]
