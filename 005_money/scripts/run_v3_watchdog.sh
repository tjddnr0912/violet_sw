#!/bin/bash
# Ver3 Trading Bot Watchdog - Auto-restart on crash or hang
#
# Usage: ./scripts/run_v3_watchdog.sh
#        ./scripts/run_v3_watchdog.sh --max-restarts 10
#        ./scripts/run_v3_watchdog.sh --restart-delay 30
#        ./scripts/run_v3_watchdog.sh --hang-timeout 600

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
HANG_TIMEOUT=600  # 10 minutes - kill bot if no log activity
HANG_CHECK_INTERVAL=60  # check every 60 seconds

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
        --hang-timeout)
            HANG_TIMEOUT="$2"
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
bot_pid=0

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

cleanup() {
    log "${RED}Watchdog stopped. Cleaning up...${NC}"
    if [[ $bot_pid -gt 0 ]]; then
        kill $bot_pid 2>/dev/null
    fi
    pkill -f "ver3/run_cli.py" 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM

# Get the latest log file
get_latest_log() {
    ls -t "$PROJECT_ROOT/logs/ver3_cli_"*.log 2>/dev/null | head -1
}

# Get log file modification time in seconds since epoch
get_log_mtime() {
    local log_file="$1"
    if [[ -f "$log_file" ]]; then
        stat -f %m "$log_file" 2>/dev/null || stat -c %Y "$log_file" 2>/dev/null
    else
        echo "0"
    fi
}

# Check if bot is hanging (no log activity)
check_hang() {
    local log_file=$(get_latest_log)
    if [[ -z "$log_file" ]]; then
        return 1  # No log file, can't determine hang
    fi

    local log_mtime=$(get_log_mtime "$log_file")
    local current_time=$(date +%s)
    local elapsed=$((current_time - log_mtime))

    if [[ $elapsed -gt $HANG_TIMEOUT ]]; then
        log "${RED}HANG DETECTED: No log activity for ${elapsed}s (threshold: ${HANG_TIMEOUT}s)${NC}"
        log "${RED}Last log file: $log_file${NC}"
        return 0  # Hang detected
    fi
    return 1  # No hang
}

log "${BLUE}========================================${NC}"
log "${BLUE}Ver3 Trading Bot Watchdog${NC}"
log "${BLUE}========================================${NC}"
log "Max restarts: ${MAX_RESTARTS:-unlimited}"
log "Restart delay: ${RESTART_DELAY}s"
log "Rapid restart threshold: ${RAPID_RESTART_THRESHOLD}s"
log "${GREEN}Hang detection: ${HANG_TIMEOUT}s timeout${NC}"
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

    # Run the bot in background
    python 001_python_code/ver3/run_cli.py &
    bot_pid=$!

    log "Bot started with PID: $bot_pid"

    # Monitor bot process and check for hangs
    while true; do
        # Check if bot process is still running
        if ! kill -0 $bot_pid 2>/dev/null; then
            wait $bot_pid
            exit_code=$?
            break
        fi

        # Check for hang
        if check_hang; then
            log "${RED}Killing hung bot (PID: $bot_pid)...${NC}"
            kill -9 $bot_pid 2>/dev/null
            wait $bot_pid 2>/dev/null
            exit_code=137  # Killed by signal
            break
        fi

        # Sleep before next check
        sleep $HANG_CHECK_INTERVAL
    done

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
