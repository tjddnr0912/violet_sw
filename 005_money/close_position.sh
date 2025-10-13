#!/bin/bash
#
# Manual Position Closer for Ver3 Trading Bot
#
# Quick script to manually close positions when needed.
# Useful for closing positions before changing coin list or emergency exits.
#
# Usage:
#   ./close_position.sh              # Interactive mode (menu)
#   ./close_position.sh -help        # Show help
#   ./close_position.sh SOL          # Close specific coin (SOL)
#   ./close_position.sh -all         # Close all positions
#

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Help message
show_help() {
    echo ""
    echo "${BLUE}=====================================================================${NC}"
    echo "${GREEN}         Manual Position Closer - Ver3 Trading Bot${NC}"
    echo "${BLUE}=====================================================================${NC}"
    echo ""
    echo "${YELLOW}DESCRIPTION:${NC}"
    echo "  Manually close positions in your Ver3 trading bot."
    echo "  Useful for:"
    echo "    - Closing positions before changing coin list"
    echo "    - Emergency exits"
    echo "    - Portfolio cleanup"
    echo ""
    echo "${YELLOW}USAGE:${NC}"
    echo "  ${GREEN}./close_position.sh${NC}              ${BLUE}# Interactive mode (menu)${NC}"
    echo "  ${GREEN}./close_position.sh -help${NC}        ${BLUE}# Show this help message${NC}"
    echo "  ${GREEN}./close_position.sh SOL${NC}          ${BLUE}# Close specific coin (e.g., SOL)${NC}"
    echo "  ${GREEN}./close_position.sh -all${NC}         ${BLUE}# Close ALL positions${NC}"
    echo ""
    echo "${YELLOW}EXAMPLES:${NC}"
    echo "  ${GREEN}1. Interactive mode (recommended for beginners):${NC}"
    echo "     $ ./close_position.sh"
    echo "     → Shows current positions"
    echo "     → Menu: Choose specific coin or close all"
    echo ""
    echo "  ${GREEN}2. Close specific coin:${NC}"
    echo "     $ ./close_position.sh XRP"
    echo "     → Closes only XRP position"
    echo "     → Shows P&L and asks for confirmation"
    echo ""
    echo "  ${GREEN}3. Close all positions:${NC}"
    echo "     $ ./close_position.sh -all"
    echo "     → Closes ALL positions (SOL, ETH, XRP, etc.)"
    echo "     → Shows total count and asks for confirmation"
    echo ""
    echo "${YELLOW}AVAILABLE COINS:${NC}"
    echo "  BTC, ETH, XRP, SOL, ADA, DOGE, etc."
    echo "  (Any coin you're currently trading)"
    echo ""
    echo "${YELLOW}NOTES:${NC}"
    echo "  - Uses DRY-RUN mode by default (no real trades)"
    echo "  - To enable LIVE trading, edit config_v3.py"
    echo "  - Always shows P&L before closing"
    echo "  - Updates positions_v3.json automatically"
    echo "  - Logs all manual closes to trading log"
    echo ""
    echo "${YELLOW}WORKFLOW - Changing Coins Safely:${NC}"
    echo "  ${GREEN}Step 1:${NC} Check current positions"
    echo "     $ ./close_position.sh"
    echo ""
    echo "  ${GREEN}Step 2:${NC} Close all positions"
    echo "     $ ./close_position.sh -all"
    echo ""
    echo "  ${GREEN}Step 3:${NC} Verify positions = 0"
    echo "     $ cat logs/positions_v3.json"
    echo "     (Should show: {})"
    echo ""
    echo "  ${GREEN}Step 4:${NC} Change coins in GUI"
    echo "     Settings → Portfolio → Select new coins"
    echo ""
    echo "  ${GREEN}Step 5:${NC} Restart bot"
    echo "     Start trading with new coins"
    echo ""
    echo "${BLUE}=====================================================================${NC}"
    echo ""
    exit 0
}

# Check for -help flag
if [ "$1" == "-help" ] || [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
    show_help
fi

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "${RED}❌ Error: Virtual environment not found${NC}"
    echo "Please create virtual environment first:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install -r requirements.txt"
    exit 1
fi

# Activate virtual environment
echo "${BLUE}Activating virtual environment...${NC}"
source .venv/bin/activate

# Check if Python script exists
PYTHON_SCRIPT="001_python_code/ver3/manual_close_position.py"
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "${RED}❌ Error: $PYTHON_SCRIPT not found${NC}"
    exit 1
fi

# Parse arguments
LIVE_MODE=false
CLOSE_ALL=false
COIN=""

for arg in "$@"; do
    if [ "$arg" == "--live" ] || [ "$arg" == "-live" ]; then
        LIVE_MODE=true
    elif [ "$arg" == "--all" ] || [ "$arg" == "-all" ]; then
        CLOSE_ALL=true
    else
        COIN="$arg"
    fi
done

# Build Python command arguments
PYTHON_ARGS=()
if [ "$LIVE_MODE" == true ]; then
    PYTHON_ARGS+=("--live")
    echo "${YELLOW}Closing --live position...${NC}"
fi

# Run Python script with arguments
if [ $# -eq 0 ]; then
    # No arguments - interactive mode
    echo "${GREEN}Starting interactive mode...${NC}"
    python "$PYTHON_SCRIPT"
elif [ "$CLOSE_ALL" == true ]; then
    # Close all positions
    echo "${YELLOW}⚠️  Closing ALL positions...${NC}"
    python "$PYTHON_SCRIPT" "${PYTHON_ARGS[@]}" --all
else
    # Close specific coin
    COIN=$(echo "$COIN" | tr '[:lower:]' '[:upper:]')
    echo "${YELLOW}Closing $COIN position...${NC}"
    python "$PYTHON_SCRIPT" "${PYTHON_ARGS[@]}" "$COIN"
fi

# Deactivate virtual environment
deactivate

echo ""
echo "${GREEN}✓ Done${NC}"
echo ""
