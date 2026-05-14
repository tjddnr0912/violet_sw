#!/bin/bash
# Quant Trading Bot Watchdog - Auto-restart on crash or hang
#
# Usage:
#   ./scripts/run_quant_watchdog.sh
#   ./scripts/run_quant_watchdog.sh --max-restarts 10
#   ./scripts/run_quant_watchdog.sh --hang-timeout 1800
#
# 005_money/scripts/run_v3_watchdog.sh 패턴 차용
# 데몬이 죽거나 로그가 너무 오래 멈춰있으면 자동 재시작.

set -uo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 기본값
MAX_RESTARTS=0
RESTART_DELAY=10
RAPID_RESTART_THRESHOLD=60
MAX_RAPID_RESTARTS=5
HANG_TIMEOUT=1800   # 30분 동안 로그 갱신 없으면 hang으로 간주
HANG_CHECK_INTERVAL=120
HANG_GRACE_PERIOD=180

while [[ $# -gt 0 ]]; do
    case $1 in
        --max-restarts) MAX_RESTARTS="$2"; shift 2 ;;
        --restart-delay) RESTART_DELAY="$2"; shift 2 ;;
        --hang-timeout) HANG_TIMEOUT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

restart_count=0
rapid_restart_count=0
last_start_time=0
bot_pid=0

log() { echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

cleanup() {
    log "${RED}Watchdog 정지. 정리 중...${NC}"
    if [[ $bot_pid -gt 0 ]]; then kill $bot_pid 2>/dev/null || true; fi
    pkill -f "run_quant.sh daemon" 2>/dev/null || true
    pkill -f "main.py.*daemon" 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

get_latest_log() {
    ls -t "$PROJECT_ROOT/logs/daemon_"*.log 2>/dev/null | head -1
}

get_log_mtime() {
    local f="$1"
    [[ -f "$f" ]] && (stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null) || echo 0
}

notify_telegram() {
    # .env에서 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 읽어서 알림
    local msg="$1"
    [[ -f ".env" ]] || return
    local token chat
    token=$(grep -E '^TELEGRAM_BOT_TOKEN=' .env | cut -d'=' -f2-)
    chat=$(grep -E '^TELEGRAM_CHAT_ID=' .env | cut -d'=' -f2-)
    [[ -z "$token" || -z "$chat" ]] && return
    curl -sS -m 5 -X POST "https://api.telegram.org/bot${token}/sendMessage" \
        -d "chat_id=${chat}" \
        -d "text=$(echo -e "$msg")" \
        -d "parse_mode=HTML" > /dev/null 2>&1 || true
}

log "${GREEN}=== Quant Watchdog 시작 ===${NC}"
log "max_restarts=$MAX_RESTARTS, hang_timeout=${HANG_TIMEOUT}s"

while true; do
    # 재시작 한도 체크
    if [[ $MAX_RESTARTS -gt 0 && $restart_count -ge $MAX_RESTARTS ]]; then
        log "${RED}최대 재시작 횟수($MAX_RESTARTS) 도달. 종료.${NC}"
        notify_telegram "🚨 <b>Watchdog 종료</b>\n최대 재시작 횟수 도달 ($MAX_RESTARTS)"
        exit 1
    fi

    # rapid restart 보호
    now=$(date +%s)
    if (( now - last_start_time < RAPID_RESTART_THRESHOLD )); then
        rapid_restart_count=$((rapid_restart_count + 1))
        if (( rapid_restart_count >= MAX_RAPID_RESTARTS )); then
            log "${RED}짧은 시간 내 ${MAX_RAPID_RESTARTS}회 재시작. 인적 개입 필요.${NC}"
            notify_telegram "🚨 <b>Watchdog 일시중지</b>\n${RAPID_RESTART_THRESHOLD}초 내 ${MAX_RAPID_RESTARTS}회 재시작. 봇 점검 필요."
            sleep 300  # 5분 후 다시 시도
            rapid_restart_count=0
        fi
    else
        rapid_restart_count=0
    fi

    last_start_time=$now
    restart_count=$((restart_count + 1))
    log "${GREEN}[#$restart_count] 데몬 시작...${NC}"

    # 데몬 실행 (background)
    ./run_quant.sh daemon &
    bot_pid=$!
    log "데몬 PID: $bot_pid"

    # hang 감지 루프
    start_grace=$(date +%s)
    while kill -0 $bot_pid 2>/dev/null; do
        sleep $HANG_CHECK_INTERVAL
        now=$(date +%s)
        # grace period 이내면 hang 체크 스킵
        (( now - start_grace < HANG_GRACE_PERIOD )) && continue
        latest=$(get_latest_log)
        [[ -z "$latest" ]] && continue
        mtime=$(get_log_mtime "$latest")
        diff=$((now - mtime))
        if (( diff > HANG_TIMEOUT )); then
            log "${YELLOW}Hang 감지: 로그 ${diff}초간 갱신 없음. 데몬 재시작.${NC}"
            notify_telegram "⚠️ <b>Watchdog: Hang 감지</b>\n로그 ${diff}s 무응답 → 재시작"
            kill $bot_pid 2>/dev/null || true
            sleep 5
            pkill -f "main.py" 2>/dev/null || true
            break
        fi
    done

    wait $bot_pid 2>/dev/null
    exit_code=$?
    log "${YELLOW}데몬 종료 (exit=$exit_code). ${RESTART_DELAY}초 후 재시작.${NC}"

    if (( exit_code != 0 )); then
        notify_telegram "⚠️ <b>Watchdog: 데몬 종료</b>\nexit=$exit_code → 재시작 (#$((restart_count+1)))"
    fi

    sleep $RESTART_DELAY
done
