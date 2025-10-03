"""
Argument Parser - Command-line argument parsing utilities

This module provides argument parsing functionality for the trading bot,
including version selection and runtime configuration.
"""

import argparse
from typing import Optional, List
from .version_loader import get_version_loader


def list_available_versions() -> List[str]:
    """Get list of available versions."""
    loader = get_version_loader()
    return loader.discover_versions()


def create_base_parser(description: str = "Cryptocurrency Trading Bot") -> argparse.ArgumentParser:
    """
    Create base argument parser with common arguments.

    Args:
        description: Program description for help text

    Returns:
        ArgumentParser instance with base arguments
    """
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Version selection
    parser.add_argument(
        "--version",
        type=str,
        default="ver1",
        help="Trading strategy version to use (e.g., ver1, ver2). Default: ver1",
    )

    # List versions
    parser.add_argument(
        "--list-versions",
        action="store_true",
        help="List all available trading strategy versions and exit",
    )

    # Trading parameters
    parser.add_argument(
        "--interval",
        type=str,
        choices=["30m", "1h", "6h", "12h", "24h"],
        help="Candlestick interval (overrides config default)",
    )

    parser.add_argument(
        "--coin",
        type=str,
        help="Cryptocurrency symbol (e.g., BTC, ETH)",
    )

    parser.add_argument(
        "--amount",
        type=float,
        help="Trade amount in KRW",
    )

    # Execution mode
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live trading mode (default is dry-run)",
    )

    parser.add_argument(
        "--gui",
        action="store_true",
        help="Launch GUI mode",
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactive configuration mode",
    )

    # Debugging
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    return parser


def parse_trading_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments for trading bot.

    Args:
        args: Optional argument list (defaults to sys.argv)

    Returns:
        Parsed arguments namespace
    """
    parser = create_base_parser()
    return parser.parse_args(args)


def parse_gui_args(args: Optional[List[str]] = None) -> argparse.Namespace:
    """
    Parse command-line arguments for GUI mode.

    Args:
        args: Optional argument list (defaults to sys.argv)

    Returns:
        Parsed arguments namespace
    """
    parser = create_base_parser(description="Cryptocurrency Trading Bot - GUI Mode")
    return parser.parse_args(args)


def validate_version_arg(version_name: str) -> bool:
    """
    Validate that specified version exists.

    Args:
        version_name: Version identifier to validate

    Returns:
        True if valid, False otherwise
    """
    available = list_available_versions()
    return version_name in available


def print_available_versions() -> None:
    """
    Print formatted list of available versions.
    """
    from .version_loader import VersionLoader

    loader = VersionLoader()
    versions_info = loader.list_versions()

    print("\n=== Available Trading Strategy Versions ===\n")

    if not versions_info:
        print("No versions found.")
        return

    for version_name, metadata in versions_info.items():
        if "error" in metadata:
            print(f"[{version_name}] - Error: {metadata['error']}")
        else:
            display_name = metadata.get("display_name", version_name)
            description = metadata.get("description", "No description")
            author = metadata.get("author", "Unknown")
            date = metadata.get("date", "Unknown")

            print(f"[{version_name}] {display_name}")
            print(f"  Description: {description}")
            print(f"  Author: {author}")
            print(f"  Date: {date}")
            print()


def build_config_override(args: argparse.Namespace) -> dict:
    """
    Build configuration override dictionary from parsed arguments.

    Args:
        args: Parsed command-line arguments

    Returns:
        Dictionary with configuration overrides
    """
    config_override = {}

    # Execution mode
    if args.live:
        config_override.setdefault("SAFETY_CONFIG", {})["dry_run"] = False

    # Trading parameters
    if args.interval:
        config_override.setdefault("EXECUTION_CONFIG", {})["default_interval"] = args.interval

    if args.coin:
        config_override.setdefault("EXECUTION_CONFIG", {})["default_symbol"] = args.coin

    if args.amount:
        config_override.setdefault("EXECUTION_CONFIG", {})["trade_amount_krw"] = args.amount

    # Debugging
    if args.debug or args.verbose:
        config_override.setdefault("LOGGING_CONFIG", {})["console_level"] = "DEBUG"

    return config_override
