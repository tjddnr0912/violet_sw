#!/bin/bash
# Manual Close Position Wrapper Script
# Activates virtual environment and runs manual_close_position.py
#
# Usage:
#   ./close_positions.sh                    # Interactive mode (DRY-RUN)
#   ./close_positions.sh SOL                # Close SOL (DRY-RUN)
#   ./close_positions.sh --all              # Close all (DRY-RUN)
#   ./close_positions.sh --live SOL         # Close SOL (LIVE)
#   ./close_positions.sh --live --all       # Close all (LIVE)

cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found (.venv)"
    echo "Please run: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate

# Check if requests module is installed
python -c "import requests" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "❌ Required modules not installed"
    echo "Installing dependencies..."
    pip install -r requirements.txt
fi

# Convert --LIVE to --live (case insensitive handling)
args=()
for arg in "$@"; do
    if [ "$arg" == "--LIVE" ]; then
        args+=("--live")
    else
        args+=("$arg")
    fi
done

# Run manual close position script with converted arguments
python 001_python_code/ver3/manual_close_position.py "${args[@]}"
