#!/bin/bash
# ==============================================
# News Bot - Scheduled Mode
# ==============================================
# Runs daily at configured time automatically
# Ctrl+C to stop
#
# Usage:
#   ./run_scheduled.sh
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/001_code"

echo "=============================================="
echo "  News Bot - Scheduled Mode"
echo "=============================================="
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Press Ctrl+C to stop"
echo "=============================================="

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "../.venv" ]; then
    source ../.venv/bin/activate
fi

# Run
python main.py --mode scheduled
