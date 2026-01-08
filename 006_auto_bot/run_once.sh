#!/bin/bash
# ==============================================
# News Bot - Once Mode
# ==============================================
# News collection -> AI summary -> Blog upload (one-time)
#
# Usage:
#   ./run_once.sh
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/001_code"

echo "=============================================="
echo "  News Bot - Once Mode"
echo "=============================================="
echo "  Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# Activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "../.venv" ]; then
    source ../.venv/bin/activate
fi

# Run
python main.py --mode once

echo ""
echo "=============================================="
echo "  Completed at $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
