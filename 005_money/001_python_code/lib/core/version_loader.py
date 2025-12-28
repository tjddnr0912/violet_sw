"""Version Loader - Dynamic loading system for trading bot versions"""

import sys
import importlib
from typing import Optional, Dict, Any, List
from pathlib import Path

from lib.interfaces.version_interface import VersionInterface


class VersionLoader:
    def __init__(self, base_path: Optional[str] = None):
        if base_path is None:
            self.base_path = Path(__file__).parent.parent.parent
        else:
            self.base_path = Path(base_path)
        self._version_cache: Dict[str, VersionInterface] = {}

    def discover_versions(self) -> List[str]:
        versions = []
        for item in self.base_path.iterdir():
            if item.is_dir() and item.name.startswith("ver"):
                if (item / "__init__.py").exists():
                    versions.append(item.name)
        return sorted(versions)

    def version_exists(self, version_name: str) -> bool:
        version_path = self.base_path / version_name
        return (version_path.exists() and version_path.is_dir() and 
                (version_path / "__init__.py").exists())

    def load_version(self, version_name: str, config_override: Optional[Dict[str, Any]] = None) -> VersionInterface:
        cache_key = f"{version_name}:{id(config_override)}"
        if cache_key in self._version_cache:
            return self._version_cache[cache_key]

        if not self.version_exists(version_name):
            available = self.discover_versions()
            raise ValueError(f"Version '{version_name}' not found. Available: {', '.join(available) if available else 'None'}")

        if str(self.base_path) not in sys.path:
            sys.path.insert(0, str(self.base_path))

        version_module = importlib.import_module(version_name)

        if not hasattr(version_module, "get_version_instance"):
            raise ImportError(f"Version '{version_name}' must define 'get_version_instance()' function")

        version_instance = version_module.get_version_instance(config_override)

        if not isinstance(version_instance, VersionInterface):
            raise TypeError(f"Version '{version_name}' must implement VersionInterface")

        is_valid, errors = version_instance.validate_configuration()
        if not is_valid:
            raise ValueError(f"Version '{version_name}' config invalid:\n" + "\n".join(f"  - {err}" for err in errors))

        self._version_cache[cache_key] = version_instance
        return version_instance

    def get_version_metadata(self, version_name: str) -> Dict[str, str]:
        if not self.version_exists(version_name):
            raise ValueError(f"Version '{version_name}' not found")
        
        try:
            version_module = importlib.import_module(version_name)
            if hasattr(version_module, "VERSION_METADATA"):
                return version_module.VERSION_METADATA
            
            instance = self.load_version(version_name)
            return {
                "name": instance.VERSION_NAME,
                "display_name": instance.VERSION_DISPLAY_NAME,
                "description": instance.VERSION_DESCRIPTION,
                "author": instance.VERSION_AUTHOR,
                "date": instance.VERSION_DATE,
            }
        except Exception as e:
            return {"name": version_name, "display_name": version_name.upper(), 
                   "description": f"Error: {e}", "author": "Unknown", "date": "Unknown"}

    def clear_cache(self):
        self._version_cache.clear()


_loader_instance: Optional[VersionLoader] = None

def get_version_loader() -> VersionLoader:
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = VersionLoader()
    return _loader_instance
