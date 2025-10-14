#!/bin/bash

# News Bot Runner Script
# Usage: ./run.sh [once|scheduled|test]

# Color codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  📰 Automated News Bot${NC}"
echo -e "${BLUE}========================================${NC}"

# Change to script directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv .venv
fi

# Activate virtual environment
echo -e "${GREEN}Activating virtual environment...${NC}"
source .venv/bin/activate

# Install dependencies if needed
if [ ! -f ".venv/installed" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -r requirements.txt
    touch .venv/installed
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}❌ .env file not found!${NC}"
    echo -e "${YELLOW}Please create .env file from .env.example and add your API keys${NC}"
    echo -e "${YELLOW}Run: cp .env.example .env${NC}"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Determine mode
MODE=${1:-once}

echo -e "${GREEN}Running in ${MODE} mode...${NC}"
echo ""

# Run the bot
case $MODE in
    "once")
        python main.py --mode once
        ;;
    "scheduled")
        python main.py --mode scheduled
        ;;
    "test")
        python main.py --test
        ;;
    *)
        echo -e "${RED}Invalid mode: $MODE${NC}"
        echo -e "${YELLOW}Usage: ./run.sh [once|scheduled|test]${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✅ Done!${NC}"
echo -e "${BLUE}========================================${NC}"
