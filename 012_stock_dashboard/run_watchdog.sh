#!/bin/bash
# Stock Dashboard Watchdog - Health check + auto-restart
#
# Usage: ./run_watchdog.sh
#        ./run_watchdog.sh --max-restarts 10
#        ./run_watchdog.sh --restart-delay 15

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Settings
PORT=${DASHBOARD_PORT:-5002}
MAX_RESTARTS=0              # 0 = unlimited
RESTART_DELAY=10            # seconds between restarts
HEALTH_CHECK_INTERVAL=30    # health check every 30s
HEALTH_CHECK_TIMEOUT=5      # curl timeout
HEALTH_FAIL_THRESHOLD=3     # consecutive failures before restart
RAPID_RESTART_THRESHOLD=60  # crash within N seconds = rapid restart
MAX_RAPID_RESTARTS=5        # stop if too many rapid restarts
GRACE_PERIOD=30             # seconds after start before health checking

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --max-restarts) MAX_RESTARTS="$2"; shift 2 ;;
        --restart-delay) RESTART_DELAY="$2"; shift 2 ;;
        --health-interval) HEALTH_CHECK_INTERVAL="$2"; shift 2 ;;
        *) shift ;;
    esac
done

restart_count=0
rapid_restart_count=0
last_start_time=0
dashboard_pid=0

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

cleanup() {
    log "${RED}Watchdog stopped. Cleaning up...${NC}"
    if [[ $dashboard_pid -gt 0 ]] && kill -0 $dashboard_pid 2>/dev/null; then
        kill $dashboard_pid 2>/dev/null
        wait $dashboard_pid 2>/dev/null
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

health_check() {
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" \
        --connect-timeout $HEALTH_CHECK_TIMEOUT \
        --max-time $HEALTH_CHECK_TIMEOUT \
        "http://127.0.0.1:$PORT/health" 2>/dev/null)
    [[ "$http_code" == "200" ]]
}

kill_existing() {
    local existing_pid
    existing_pid=$(lsof -ti :$PORT 2>/dev/null)
    if [[ -n "$existing_pid" ]]; then
        log "${YELLOW}Killing existing process on port $PORT (PID: $existing_pid)...${NC}"
        kill $existing_pid 2>/dev/null
        sleep 2
        # Force kill if still alive
        if kill -0 $existing_pid 2>/dev/null; then
            kill -9 $existing_pid 2>/dev/null
            sleep 1
        fi
    fi
}

mkdir -p logs

# Activate venv
if [[ -d "venv" ]]; then
    source venv/bin/activate
fi

log "${BLUE}========================================${NC}"
log "${BLUE}Stock Dashboard Watchdog${NC}"
log "${BLUE}========================================${NC}"
log "Port: $PORT"
log "Max restarts: ${MAX_RESTARTS:-unlimited}"
log "Health check: every ${HEALTH_CHECK_INTERVAL}s (fail threshold: ${HEALTH_FAIL_THRESHOLD})"
log ""

# Kill existing instances
kill_existing

# Main watchdog loop
while true; do
    current_time=$(date +%s)

    # Rapid restart detection
    if [[ $last_start_time -gt 0 ]]; then
        elapsed=$((current_time - last_start_time))
        if [[ $elapsed -lt $RAPID_RESTART_THRESHOLD ]]; then
            rapid_restart_count=$((rapid_restart_count + 1))
            log "${YELLOW}Rapid restart detected (${elapsed}s). Count: $rapid_restart_count/$MAX_RAPID_RESTARTS${NC}"
            if [[ $rapid_restart_count -ge $MAX_RAPID_RESTARTS ]]; then
                log "${RED}Too many rapid restarts. Stopping watchdog.${NC}"
                log "${RED}Check logs: logs/dashboard.log${NC}"
                exit 1
            fi
        else
            rapid_restart_count=0
        fi
    fi

    # Max restarts check
    if [[ $MAX_RESTARTS -gt 0 && $restart_count -ge $MAX_RESTARTS ]]; then
        log "${RED}Max restarts ($MAX_RESTARTS) reached. Stopping.${NC}"
        exit 1
    fi

    restart_count=$((restart_count + 1))
    last_start_time=$(date +%s)

    log "${GREEN}Starting dashboard (attempt #$restart_count)...${NC}"

    # Start dashboard in background
    uvicorn app:app --host 0.0.0.0 --port $PORT --log-level info \
        >> logs/uvicorn.log 2>&1 &
    dashboard_pid=$!

    log "Dashboard started with PID: $dashboard_pid"

    # Grace period before health checking
    sleep $GRACE_PERIOD

    health_fail_count=0

    # Monitor loop
    while true; do
        # Check if process is still alive
        if ! kill -0 $dashboard_pid 2>/dev/null; then
            wait $dashboard_pid
            exit_code=$?
            log "${RED}Dashboard process died (exit code: $exit_code)${NC}"
            break
        fi

        # Health check
        if health_check; then
            health_fail_count=0
        else
            health_fail_count=$((health_fail_count + 1))
            log "${YELLOW}Health check failed ($health_fail_count/$HEALTH_FAIL_THRESHOLD)${NC}"

            if [[ $health_fail_count -ge $HEALTH_FAIL_THRESHOLD ]]; then
                log "${RED}Health check threshold reached. Killing dashboard (PID: $dashboard_pid)...${NC}"
                kill $dashboard_pid 2>/dev/null
                sleep 2
                if kill -0 $dashboard_pid 2>/dev/null; then
                    kill -9 $dashboard_pid 2>/dev/null
                fi
                wait $dashboard_pid 2>/dev/null
                break
            fi
        fi

        sleep $HEALTH_CHECK_INTERVAL
    done

    end_time=$(date +%s)
    runtime=$((end_time - last_start_time))
    log "${RED}Dashboard ran for ${runtime}s${NC}"

    log "${YELLOW}Restarting in ${RESTART_DELAY}s...${NC}"
    sleep $RESTART_DELAY

    # Kill any leftover process on the port
    kill_existing
done
