# Temporary compatibility wrapper for strategy.py
# This will be removed in Phase 6
from ver1.strategy_v1 import *

# For backward compatibility, ensure TradingStrategy is available
try:
    from ver1.strategy_v1 import TradingStrategy
except ImportError:
    from ver1.strategy_v1 import StrategyV1 as TradingStrategy
