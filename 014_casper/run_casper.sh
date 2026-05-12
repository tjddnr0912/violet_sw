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
#
# CRITICAL: use `IFS=` (no separator) + substring expansion, NOT `IFS='='
# read -r key value`. bash's `read` strips trailing IFS bytes from the last
# field, so values ending with '=' (e.g. base64-padded KIS_APP_SECRET) lose
# their final byte — yielding a corrupt secret that KIS rejects with an
# opaque HTTP 500 {"rt_cd":"1","msg_cd":"","msg1":""}. This burned an
# entire debugging session in 2026-04-14.
load_env() {
    if [ -f ".env" ]; then
        while IFS= read -r line || [ -n "$line" ]; do
            # Skip comments / blank lines
            [[ "$line" =~ ^[[:space:]]*# ]] && continue
            [[ -z "${line// }" ]] && continue
            # Split on the *first* '=' only, preserving any '=' in the value
            key="${line%%=*}"
            value="${line#*=}"
            # Trim whitespace around key
            key="${key#"${key%%[![:space:]]*}"}"
            key="${key%"${key##*[![:space:]]}"}"
            # Strip inline comments from value (space + #...)
            value="$(printf '%s' "$value" | sed 's/[[:space:]]*#.*$//')"
            # Trim whitespace around value
            value="${value#"${value%%[![:space:]]*}"}"
            value="${value%"${value##*[![:space:]]}"}"
            # Strip surrounding single/double quotes if present
            [[ "$value" == \"*\" ]] && value="${value#\"}" && value="${value%\"}"
            [[ "$value" == \'*\' ]] && value="${value#\'}" && value="${value%\'}"
            export "$key=$value"
        done < .env
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
    CONFIG_INFO=$(python3 -c "
import json, os
c = json.load(open('config/strategy_params.json'))
e = c.get('entry', {})
rr = e.get('rr_ratio', 2.0)
strict = e.get('strict_fvg', False)
dual = c.get('mode', {}).get('dual_scan', False)
# ICT effective flags = env overrides config (mirrors src/utils/config.py logic)
def _on(env, fallback):
    raw = os.getenv(env)
    if raw is None: return bool(fallback)
    return raw.strip().lower() in ('on','true','1','yes')
kz = _on('ICT_KILLZONE_ENABLED', e.get('killzone_filter_enabled', False))
disp = _on('ICT_REQUIRE_DISPLACEMENT', e.get('require_displacement', False))
sweep = _on('ICT_REQUIRE_SWEEP_CHOCH', e.get('require_sweep_choch', False))
bear = _on('ICT_BEAR_FVG_FOR_SQQQ', e.get('bear_fvg_for_sqqq', False))
bias = _on('ICT_DAILY_BIAS_SKIP_NEUTRAL', e.get('daily_bias_skip_neutral', False))
print(f'{rr}|{strict}|{dual}|{kz}|{disp}|{sweep}|{bear}|{bias}')
" 2>/dev/null || echo "?|?|?|?|?|?|?|?")
    RR=$(echo "$CONFIG_INFO" | cut -d'|' -f1)
    STRICT_FVG=$(echo "$CONFIG_INFO" | cut -d'|' -f2)
    DUAL_SCAN=$(echo "$CONFIG_INFO" | cut -d'|' -f3)
    ICT_KZ=$(echo "$CONFIG_INFO" | cut -d'|' -f4)
    ICT_DISP=$(echo "$CONFIG_INFO" | cut -d'|' -f5)
    ICT_SWEEP=$(echo "$CONFIG_INFO" | cut -d'|' -f6)
    ICT_BEAR=$(echo "$CONFIG_INFO" | cut -d'|' -f7)
    ICT_BIAS=$(echo "$CONFIG_INFO" | cut -d'|' -f8)
    SCAN_MODE="단일 (QQQ MA20 추세)"
    [ "$DUAL_SCAN" = "True" ] && SCAN_MODE="${CYAN}DUAL SCAN${NC} (TQQQ+SQQQ 동시)"
    FVG_MODE="baseline (Close>ORB)"
    [ "$STRICT_FVG" = "True" ] && FVG_MODE="${CYAN}STRICT${NC} (몸통 가로지르기 + FVG-ORB intersect)"
    echo -e "${GREEN}[INFO]${NC} 전략: ORB + FVG + Pullback (R:R 1:${RR%.*})"
    echo -e "${GREEN}[INFO]${NC} 스캔: ${SCAN_MODE}"
    echo -e "${GREEN}[INFO]${NC} FVG : ${FVG_MODE}"
    echo -e "${GREEN}[INFO]${NC} 종목: TQQQ (강세) / SQQQ (약세)"
    # ICT phase status
    ict_line=""
    [ "$ICT_KZ"    = "True" ] && ict_line="${ict_line}KZ "
    [ "$ICT_DISP"  = "True" ] && ict_line="${ict_line}Disp "
    [ "$ICT_SWEEP" = "True" ] && ict_line="${ict_line}Sweep "
    [ "$ICT_BIAS"  = "True" ] && ict_line="${ict_line}Bias "
    [ "$ICT_BEAR"  = "True" ] && ict_line="${ict_line}QQQ→SQQQ "
    if [ -n "$ict_line" ]; then
        echo -e "${GREEN}[INFO]${NC} ICT : ${CYAN}${ict_line}${NC} (전체 bot 통합 완료)"
        KST_WINDOW=$(python3 -c "
from datetime import datetime, time as dtime
import pytz
et = pytz.timezone('US/Eastern')
kst = pytz.timezone('Asia/Seoul')
today_et = datetime.now(et)
s = et.localize(datetime.combine(today_et.date(), dtime(9, 30))).astimezone(kst)
e = et.localize(datetime.combine(today_et.date(), dtime(10, 55))).astimezone(kst)
is_dst = today_et.dst().total_seconds() != 0
print(f\"{s.strftime('%H:%M')}~{e.strftime('%H:%M')}|{'서머타임' if is_dst else '표준시'}\")
" 2>/dev/null || echo "?~?|?")
        KST_TIME=$(echo "$KST_WINDOW" | cut -d'|' -f1)
        DST_TAG=$(echo "$KST_WINDOW" | cut -d'|' -f2)
        echo -e "${YELLOW}[NOTE]${NC} 매매 윈도우: ET 09:30~10:55  (KST ${KST_TIME}, ${DST_TAG})"
    else
        echo -e "${GREEN}[INFO]${NC} ICT : ${YELLOW}off${NC} (기본 ORB+FVG strict만 작동)"
    fi

    # Fine-tune reminder
    FT_INFO=$(python3 -c "
import json, os
try:
    p = 'data/trades/trades_2026.json'
    if not os.path.exists(p):
        print('0|5'); raise SystemExit
    trades = json.load(open(p))
    n_ict = sum(1 for t in trades if isinstance(t, dict) and t.get('ict'))
    print(f'{n_ict}|5')
except Exception:
    print('?|5')
" 2>/dev/null || echo "?|5")
    FT_N=$(echo "$FT_INFO" | cut -d'|' -f1)
    FT_T=$(echo "$FT_INFO" | cut -d'|' -f2)
    if [ "$FT_N" != "?" ]; then
        if [ "$FT_N" -lt "$FT_T" ] 2>/dev/null; then
            REMAINING=$((FT_T - FT_N))
            echo -e "${YELLOW}[📌 FINE-TUNE]${NC} ICT 매매 ${FT_N}/${FT_T}건 누적. ${REMAINING}건 더 후 검증 권장:"
            echo -e "${YELLOW}             ${NC} python scripts/phase1_precheck.py"
        elif [ $((FT_N % FT_T)) -eq 0 ] 2>/dev/null; then
            echo -e "${RED}[📌 FINE-TUNE NOW]${NC} ICT 매매 ${FT_N}건 — phase1_precheck.py 재실행하세요!"
        else
            NEXT=$(((FT_N / FT_T + 1) * FT_T))
            echo -e "${YELLOW}[📌 FINE-TUNE]${NC} ICT 매매 ${FT_N}건 누적 (다음 검증: ${NEXT}건)"
        fi
    fi
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

    # ICT phase summary (same logic as start_bot)
    ICT_LINE=$(python3 -c "
import json, os
c = json.load(open('config/strategy_params.json'))
e = c.get('entry', {})
def _on(env, fallback):
    raw = os.getenv(env)
    if raw is None: return bool(fallback)
    return raw.strip().lower() in ('on','true','1','yes')
flags = []
if _on('ICT_KILLZONE_ENABLED', e.get('killzone_filter_enabled', False)):
    kz = e.get('allowed_killzones', []) or []
    flags.append('KZ(' + ','.join(kz) + ')' if kz else 'KZ')
if _on('ICT_REQUIRE_DISPLACEMENT', e.get('require_displacement', False)):
    flags.append('Disp')
if _on('ICT_REQUIRE_SWEEP_CHOCH', e.get('require_sweep_choch', False)):
    flags.append('Sweep')
if _on('ICT_DAILY_BIAS_SKIP_NEUTRAL', e.get('daily_bias_skip_neutral', False)):
    flags.append('Bias')
if _on('ICT_BEAR_FVG_FOR_SQQQ', e.get('bear_fvg_for_sqqq', False)):
    flags.append('QQQ->SQQQ')
print(' + '.join(flags) if flags else 'off')
" 2>/dev/null || echo "?")
    echo -e "${GREEN}[INFO]${NC} ICT : ${CYAN}${ICT_LINE}${NC}"
    # Compute KST window (DST-aware)
    KST_WINDOW=$(python3 -c "
from datetime import datetime, time as dtime
import pytz
et = pytz.timezone('US/Eastern')
kst = pytz.timezone('Asia/Seoul')
today_et = datetime.now(et)
s = et.localize(datetime.combine(today_et.date(), dtime(9, 30))).astimezone(kst)
e = et.localize(datetime.combine(today_et.date(), dtime(10, 55))).astimezone(kst)
is_dst = today_et.dst().total_seconds() != 0
print(f\"{s.strftime('%H:%M')}~{e.strftime('%H:%M')}|{'서머타임' if is_dst else '표준시'}\")
" 2>/dev/null || echo "?~?|?")
    KST_TIME=$(echo "$KST_WINDOW" | cut -d'|' -f1)
    DST_TAG=$(echo "$KST_WINDOW" | cut -d'|' -f2)
    echo -e "${YELLOW}[NOTE]${NC} 매매 윈도우: ET 09:30~10:55  (KST ${KST_TIME}, ${DST_TAG})"

    # Fine-tune reminder — count ICT-tagged trades and remind
    FT_INFO=$(python3 -c "
import json, os
try:
    p = 'data/trades/trades_2026.json'
    if not os.path.exists(p):
        print('0|5'); raise SystemExit
    trades = json.load(open(p))
    n_ict = sum(1 for t in trades if isinstance(t, dict) and t.get('ict'))
    print(f'{n_ict}|5')
except Exception:
    print('?|5')
" 2>/dev/null || echo "?|5")
    FT_N=$(echo "$FT_INFO" | cut -d'|' -f1)
    FT_T=$(echo "$FT_INFO" | cut -d'|' -f2)
    if [ "$FT_N" != "?" ]; then
        if [ "$FT_N" -lt "$FT_T" ] 2>/dev/null; then
            REMAINING=$((FT_T - FT_N))
            echo -e "${YELLOW}[📌 FINE-TUNE]${NC} ICT 매매 ${FT_N}/${FT_T}건 누적. ${REMAINING}건 더 누적 후 검증 권장:"
            echo -e "${YELLOW}             ${NC} python scripts/phase1_precheck.py"
        elif [ $((FT_N % FT_T)) -eq 0 ] 2>/dev/null; then
            echo -e "${RED}[📌 FINE-TUNE NOW]${NC} ICT 매매 ${FT_N}건 — phase1_precheck.py 재실행하세요!"
        else
            NEXT=$(((FT_N / FT_T + 1) * FT_T))
            echo -e "${YELLOW}[📌 FINE-TUNE]${NC} ICT 매매 ${FT_N}건 누적 (다음 검증 시점: ${NEXT}건)"
        fi
    fi

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
