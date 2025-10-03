#!/bin/bash
# Quick GUI Launch Script for Testing Multi-Timeframe Charts
# This script activates venv and launches GUI with proper environment

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}  Multi-Timeframe Chart GUI Launcher${NC}"
echo -e "${BLUE}==========================================${NC}"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}✓${NC} Script directory: $SCRIPT_DIR"
echo -e "${GREEN}✓${NC} Project root: $PROJECT_ROOT"
echo ""

# Change to project root
cd "$PROJECT_ROOT"

# Check if venv exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗${NC} Virtual environment not found!"
    echo "  Please create it first:"
    echo "    cd $PROJECT_ROOT"
    echo "    python3 -m venv .venv"
    echo "    source .venv/bin/activate"
    echo "    pip install -r requirements.txt"
    exit 1
fi

echo -e "${GREEN}✓${NC} Virtual environment found"

# Activate venv
echo -e "${BLUE}Activating virtual environment...${NC}"
source .venv/bin/activate

# Verify key dependencies
echo -e "${BLUE}Checking dependencies...${NC}"
python -c "import pandas, matplotlib, tkinter; print('✓ All dependencies available')" || {
    echo -e "${RED}✗${NC} Dependencies missing!"
    echo "  Install them with:"
    echo "    pip install -r requirements.txt"
    exit 1
}

# Quick import check
echo -e "${BLUE}Testing imports...${NC}"
cd "$SCRIPT_DIR"
python -c "from multi_chart_tab import MultiTimeframeChartTab; print('✓ MultiTimeframeChartTab import OK')" || {
    echo -e "${RED}✗${NC} Import failed!"
    exit 1
}

# Launch GUI
echo ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN}  Launching GUI...${NC}"
echo -e "${GREEN}==========================================${NC}"
echo ""
echo "Press Ctrl+C to stop the GUI"
echo ""

python gui_app.py

echo ""
echo -e "${BLUE}GUI closed${NC}"
