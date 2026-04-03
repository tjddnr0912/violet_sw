#!/bin/bash

# ================================================================
# Casper Trading Bot - TQQQ/SQQQ ORB+FVG Strategy
# ================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 색상
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_logo() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║      👻 Casper Bot - TQQQ/SQQQ ORB+FVG Strategy        ║"
    echo "╚═══════════════════════════════════════════════════════���══╝"
    echo -e "${NC}"
}

# .env 로드
load_env() {
    if [ -f ".env" ]; then
        set -a
        source .env
        set +a
    else
        echo -e "${RED}[ERROR]${NC} .env 파일이 없습니다. .env.example을 참고하세요."
        exit 1
    fi
}

# venv 활성화
activate_venv() {
    if [ -d ".venv" ]; then
        source .venv/bin/activate
    else
        echo -e "${YELLOW}[INFO]${NC} venv 생성 중..."
        python3 -m venv .venv
        source .venv/bin/activate
        pip install -r requirements.txt --quiet
    fi
}

# 의존성 확인
check_deps() {
    python3 -c "import yfinance, pandas, numpy, requests, dotenv, pytz" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}[INFO]${NC} 의존성 설치 중..."
        pip install -r requirements.txt --quiet
    fi
}

# API 키 확인
check_api_keys() {
    if [ -z "$KIS_APP_KEY" ] || [ -z "$KIS_APP_SECRET" ]; then
        echo -e "${RED}[ERROR]${NC} KIS API 키가 설정되지 않았습니다."
        echo "       .env 파일에 KIS_APP_KEY, KIS_APP_SECRET을 설정하세요."
        exit 1
    fi
    echo -e "${GREEN}[OK]${NC} KIS API 키 확인됨"
}

# 중복 실행 방지
PID_FILE="$SCRIPT_DIR/.casper.pid"

check_running() {
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if kill -0 "$OLD_PID" 2>/dev/null; then
            echo -e "${YELLOW}[WARN]${NC} Casper Bot이 이미 실행 중입니다 (PID: $OLD_PID)"
            echo "       종료하려면: $0 stop"
            exit 1
        else
            rm -f "$PID_FILE"
        fi
    fi
}

# 상태 출력
show_status() {
    activate_venv
    python3 run_bot.py --status
}

# 봇 시작
start_bot() {
    print_logo
    load_env
    activate_venv
    check_deps
    check_api_keys
    check_running

    MODE="${TRADING_MODE:-paper}"
    TEST="${TEST_MODE:-off}"
    echo -e "${GREEN}[INFO]${NC} 모드: ${BLUE}${MODE}${NC}"
    if [ "$TEST" = "on" ]; then
        echo -e "${GREEN}[INFO]${NC} 테스트: ${YELLOW}ON (1주 고정)${NC}"
    fi
    echo -e "${GREEN}[INFO]${NC} 계좌: ${KIS_ACCOUNT_NO}"
    echo -e "${GREEN}[INFO]${NC} 전략: ORB + FVG + Pullback (R:R 1:2)"
    echo -e "${GREEN}[INFO]${NC} 종목: TQQQ (강세) / SQQQ (약세)"
    echo ""

    if [ "$MODE" = "live" ] && [ "$AUTO_CONFIRM" != "1" ]; then
        echo -e "${RED}⚠  실전투자 모드입니다! ⚠${NC}"
        echo -n "   계속하시겠습니까? (y/N): "
        read -r confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "취소되었습니다."
            exit 0
        fi
        echo ""
    fi

    echo -e "${GREEN}[START]${NC} Casper Bot 시작..."
    echo $$ > "$PID_FILE"
    exec python3 run_bot.py
}

# 데몬 모드 (백그라운드)
start_daemon() {
    print_logo
    load_env
    activate_venv
    check_deps
    check_api_keys
    check_running

    MODE="${TRADING_MODE:-paper}"
    echo -e "${GREEN}[INFO]${NC} 데몬 모드로 시작 (모드: ${BLUE}${MODE}${NC})"

    nohup python3 run_bot.py >> logs/casper.log 2>&1 &
    DAEMON_PID=$!
    echo "$DAEMON_PID" > "$PID_FILE"
    echo -e "${GREEN}[START]${NC} Casper Bot 데몬 시작 (PID: $DAEMON_PID)"
    echo -e "${GREEN}[INFO]${NC} 로그: tail -f logs/casper.log"
}

# 봇 종료
stop_bot() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            rm -f "$PID_FILE"
            echo -e "${GREEN}[STOP]${NC} Casper Bot 종료됨 (PID: $PID)"
        else
            rm -f "$PID_FILE"
            echo -e "${YELLOW}[INFO]${NC} 프로세스가 이미 종료됨"
        fi
    else
        echo -e "${YELLOW}[INFO]${NC} 실행 중인 봇이 없습니다"
    fi
}

# 도움말
print_help() {
    print_logo
    echo "사용법: $0 [명령어]"
    echo ""
    echo "  명령어:"
    echo "    start       봇 시작 (포그라운드)"
    echo "    daemon      봇 시작 (백그라운드 데몬)"
    echo "    stop        봇 종료"
    echo "    status      누적 매매 통계"
    echo "    log         실시간 로그 보기"
    echo "    test        유닛 테스트 실행"
    echo "    help        도움말"
    echo ""
    echo "  예시:"
    echo "    $0 start    # 포그라운드로 봇 실행"
    echo "    $0 daemon   # 백그라운드 데몬으로 실행"
    echo "    $0 stop     # 데몬 종료"
    echo ""
}

# --yes 플래그 처리
AUTO_CONFIRM=0
for arg in "$@"; do
    if [ "$arg" = "--yes" ] || [ "$arg" = "-y" ]; then
        AUTO_CONFIRM=1
    fi
done

# 메인
case "${1:-start}" in
    start)
        start_bot
        ;;
    daemon)
        start_daemon
        ;;
    stop)
        stop_bot
        ;;
    status)
        show_status
        ;;
    log)
        tail -f logs/casper.log
        ;;
    test)
        activate_venv
        python3 -m pytest tests/ -v
        ;;
    help|--help|-h)
        print_help
        ;;
    *)
        echo -e "${RED}[ERROR]${NC} 알 수 없는 명령어: $1"
        print_help
        exit 1
        ;;
esac
