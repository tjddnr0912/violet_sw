#!/bin/bash
# Ver2 Trading Bot CLI

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo -e "${BLUE}Ver2 Trading Bot (CLI Mode)${NC}"
echo ""

if [[ ! -f "001_python_code/ver2/main_v2.py" ]]; then
    echo -e "${RED}Error: Run from 005_money directory${NC}"
    exit 1
fi

if [[ -d ".venv" ]]; then
    echo -e "${GREEN}Activating virtual environment...${NC}"
    source .venv/bin/activate
fi

python 001_python_code/ver2/main_v2.py "$@"
