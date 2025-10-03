#!/usr/bin/env python3
"""
GUI Launcher for Bitcoin Multi-Timeframe Strategy v2

This script:
1. Checks dependencies
2. Sets up environment
3. Launches the v2 GUI application

Usage:
    python run_gui_v2.py
    python ver2/run_gui_v2.py  (from 001_python_code)
"""

import sys
import os
from pathlib import Path


def check_dependencies():
    """Check if all required packages are installed"""
    required_packages = {
        'tkinter': 'python3-tk (system package)',
        'pandas': 'pip install pandas',
        'numpy': 'pip install numpy',
        'matplotlib': 'pip install matplotlib',
        'requests': 'pip install requests',
        'backtrader': 'pip install backtrader',
    }

    missing = []

    for package, install_cmd in required_packages.items():
        try:
            if package == 'tkinter':
                import tkinter
            elif package == 'pandas':
                import pandas
            elif package == 'numpy':
                import numpy
            elif package == 'matplotlib':
                import matplotlib
            elif package == 'requests':
                import requests
            elif package == 'backtrader':
                import backtrader
        except ImportError:
            missing.append(f"  - {package}: {install_cmd}")

    if missing:
        print("❌ Missing dependencies:")
        print("\n".join(missing))
        print("\nQuick fix:")
        print("  cd /Users/seongwookjang/project/git/violet_sw/005_money")
        print("  source .venv/bin/activate  # if using venv")
        print("  pip install -r requirements.txt")
        print("\nPlease install missing packages and try again.")
        return False

    return True


def setup_environment():
    """Setup Python path and working directory"""
    # Get script directory and project root
    script_dir = Path(__file__).parent.resolve()
    code_dir = script_dir.parent
    project_root = code_dir.parent

    # Change to project root
    os.chdir(project_root)

    # Add to Python path
    if str(code_dir) not in sys.path:
        sys.path.insert(0, str(code_dir))
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    print(f"✅ Environment setup complete")
    print(f"   Working directory: {project_root}")
    print(f"   Python path includes: {code_dir}")


def print_welcome():
    """Print welcome message"""
    print("=" * 60)
    print("   Bitcoin Multi-Timeframe Strategy v2.0 - GUI")
    print("=" * 60)
    print()
    print("Strategy Overview:")
    print("  - Regime Filter: Daily EMA 50/200 Golden Cross")
    print("  - Entry Signals: 4H score-based system (3+ points)")
    print("    • BB Lower Touch: +1 point")
    print("    • RSI Oversold (<30): +1 point")
    print("    • Stoch RSI Cross (<20): +2 points")
    print("  - Position Management: 50% initial, scale at BB mid/upper")
    print("  - Exit: Chandelier Exit (3x ATR trailing stop)")
    print()
    print("Features:")
    print("  ✓ 5-tab interface (same layout as v1)")
    print("  ✓ Real-time regime filter monitoring")
    print("  ✓ Entry score breakdown display")
    print("  ✓ Chandelier stop visualization")
    print("  ✓ Position scaling tracking")
    print("  ✓ Signal history with detailed breakdown")
    print()
    print("=" * 60)
    print()


def launch_gui():
    """Launch the GUI application"""
    try:
        from ver2.gui_app_v2 import main
        main()
    except Exception as e:
        print(f"❌ Error launching GUI: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

    return True


def main():
    """Main entry point"""
    print_welcome()

    # Step 1: Check dependencies
    print("Checking dependencies...")
    if not check_dependencies():
        sys.exit(1)

    print("✅ All dependencies satisfied\n")

    # Step 2: Setup environment
    print("Setting up environment...")
    setup_environment()
    print()

    # Step 3: Launch GUI
    print("Launching v2 GUI...\n")
    if not launch_gui():
        sys.exit(1)


if __name__ == "__main__":
    main()
