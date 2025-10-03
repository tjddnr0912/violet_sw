"""
Version 1: Elite 8-Indicator Trading Strategy

This module provides the factory function for creating Version 1 strategy instances.
"""

from typing import Dict, Any, Optional, TYPE_CHECKING
from .config_v1 import get_version_config, VERSION_METADATA
from lib.core.config_common import get_common_config, merge_configs

# Lazy import to avoid pandas dependency during config loading
if TYPE_CHECKING:
    from .strategy_v1 import StrategyV1


def get_version_instance(config_override: Optional[Dict[str, Any]] = None):
    """
    Factory function to create a Version 1 strategy instance.

    Args:
        config_override: Optional configuration overrides

    Returns:
        Configured StrategyV1 instance
    """
    # Lazy import only when actually creating instance
    from .strategy_v1 import StrategyV1

    # Get common and version configs
    common = get_common_config()
    version = get_version_config()

    # Merge configurations: common + version + override
    configs = [common, version]
    if config_override:
        configs.append(config_override)

    merged = merge_configs(*configs)

    # Create strategy instance
    return StrategyV1(config=merged)


# Export version metadata for version loader
VERSION_METADATA = VERSION_METADATA

# Note: StrategyV1 is imported lazily in get_version_instance() to avoid pandas dependency during config loading
# Export main functions for direct import
__all__ = ['get_version_instance', 'VERSION_METADATA']
