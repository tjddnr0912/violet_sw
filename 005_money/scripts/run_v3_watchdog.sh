#!/bin/bash
# Ver3 Trading Bot Watchdog - Auto-restart on crash
#
# Usage: ./scripts/run_v3_watchdog.sh
#        ./scripts/run_v3_watchdog.sh --max-restarts 10
#        ./scripts/run_v3_watchdog.sh --restart-delay 30

GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Default settings
MAX_RESTARTS=0  # 0 = unlimited
RESTART_DELAY=10  # seconds between restarts
RAPID_RESTART_THRESHOLD=60  # if crash within N seconds, count as rapid restart
MAX_RAPID_RESTARTS=5  # stop if too many rapid restarts

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --max-restarts)
            MAX_RESTARTS="$2"
            shift 2
            ;;
        --restart-delay)
            RESTART_DELAY="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

restart_count=0
rapid_restart_count=0
last_start_time=0

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

cleanup() {
    log "${RED}Watchdog stopped. Cleaning up...${NC}"
    pkill -f "ver3/run_cli.py" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

log "${BLUE}========================================${NC}"
log "${BLUE}Ver3 Trading Bot Watchdog${NC}"
log "${BLUE}========================================${NC}"
log "Max restarts: ${MAX_RESTARTS:-unlimited}"
log "Restart delay: ${RESTART_DELAY}s"
log "Rapid restart threshold: ${RAPID_RESTART_THRESHOLD}s"
log ""

# Kill existing instances
if pgrep -f "ver3/run_cli.py\|ver3/gui_app_v3.py" > /dev/null 2>&1; then
    log "${YELLOW}Killing existing bot instance...${NC}"
    pkill -f "ver3/run_cli.py" 2>/dev/null
    pkill -f "ver3/gui_app_v3.py" 2>/dev/null
    sleep 2
fi

# Activate venv and load env
if [[ -d ".venv" ]]; then
    source .venv/bin/activate
fi

if [[ -f ".env" ]]; then
    set -a
    source .env
    set +a
fi

# Main watchdog loop
while true; do
    current_time=$(date +%s)

    # Check for rapid restarts
    if [[ $last_start_time -gt 0 ]]; then
        elapsed=$((current_time - last_start_time))
        if [[ $elapsed -lt $RAPID_RESTART_THRESHOLD ]]; then
            rapid_restart_count=$((rapid_restart_count + 1))
            log "${YELLOW}Rapid restart detected ($elapsed seconds). Count: $rapid_restart_count/$MAX_RAPID_RESTARTS${NC}"

            if [[ $rapid_restart_count -ge $MAX_RAPID_RESTARTS ]]; then
                log "${RED}Too many rapid restarts. Stopping watchdog.${NC}"
                log "${RED}Check logs for errors: logs/ver3_cli_*.log${NC}"
                exit 1
            fi
        else
            rapid_restart_count=0  # Reset if bot ran for a while
        fi
    fi

    # Check max restarts
    if [[ $MAX_RESTARTS -gt 0 && $restart_count -ge $MAX_RESTARTS ]]; then
        log "${RED}Max restarts ($MAX_RESTARTS) reached. Stopping watchdog.${NC}"
        exit 1
    fi

    restart_count=$((restart_count + 1))
    last_start_time=$(date +%s)

    log "${GREEN}Starting bot (attempt #$restart_count)...${NC}"

    # Run the bot
    python 001_python_code/ver3/run_cli.py
    exit_code=$?

    end_time=$(date +%s)
    runtime=$((end_time - last_start_time))

    log "${RED}Bot exited with code $exit_code after ${runtime}s${NC}"

    # If clean exit (exit code 0), stop watchdog
    if [[ $exit_code -eq 0 ]]; then
        log "${GREEN}Bot exited cleanly. Stopping watchdog.${NC}"
        exit 0
    fi

    log "${YELLOW}Restarting in ${RESTART_DELAY}s...${NC}"
    sleep $RESTART_DELAY
done
