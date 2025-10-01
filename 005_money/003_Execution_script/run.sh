#!/bin/bash

# 빗썸 자동매매 봇 실행 스크립트 (최종 개선 버전)
# 새로운 명령행 인수와 동적 설정 지원
# GUI 지원 및 실행파일 형태로 개선

set -e  # 에러 발생 시 스크립트 중단

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# 함수들
show_logo() {
    echo -e "${BLUE}${BOLD}"
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║                🤖 빗썸 자동매매 봇 (CLI 모드)                   ║"
    echo "║                    Bithumb Trading Bot                          ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

show_help() {
    show_logo
    echo -e "${YELLOW}사용법:${NC} ./run.sh [run.sh 옵션] [봇 옵션]"
    echo ""
    echo -e "${YELLOW}run.sh 전용 옵션:${NC}"
    echo "  --setup-only     환경 설정만 하고 봇은 실행하지 않음"
    echo "  --skip-setup     환경 설정을 건너뛰고 봇만 실행"
    echo "  --examples       사용 예시 표시"
    echo "  --force-install  패키지 강제 재설치"
    echo "  --gui            GUI 모드로 실행"
    echo "  --help           이 도움말 표시"
    echo ""
    echo -e "${YELLOW}봇 옵션 (main.py로 전달):${NC}"
    echo "  --interval TIME  체크 간격 (30s, 5m, 1h 등)"
    echo "  --coin COIN      거래할 코인 (BTC, ETH, XRP 등)"
    echo "  --amount NUM     거래 금액 (원)"
    echo "  --dry-run        모의 거래 모드 (기본값)"
    echo "  --live           실제 거래 모드 (주의!)"
    echo "  --interactive    대화형 설정 모드"
    echo "  --show-config    현재 설정 표시"
    echo ""
    echo -e "${CYAN}사용 예시:${NC}"
    echo "  ./run.sh                              # 기본 실행"
    echo "  ./run.sh --gui                       # GUI 모드"
    echo "  ./run.sh --interval 30s              # 30초 간격"
    echo "  ./run.sh --coin ETH --amount 50000   # 이더리움 5만원"
    echo "  ./run.sh --interactive               # 대화형 설정"
    echo "  ./run.sh --examples                  # 사용 예시"
    echo ""
    echo -e "${PURPLE}💡 팁:${NC}"
    echo "  • GUI 모드를 원한다면: ${BOLD}./gui${NC} 명령을 사용하세요"
    echo "  • 빠른 GUI 실행: ${BOLD}./run.sh --gui${NC}"
    echo ""
}

show_examples() {
    show_logo
    echo -e "${BLUE}🚀 빗썸 자동매매 봇 사용 예시${NC}"
    echo ""
    echo -e "${YELLOW}⏰ 시간 간격 설정:${NC}"
    echo "  ./run.sh --interval 30s          # 30초마다"
    echo "  ./run.sh --interval 5m           # 5분마다"
    echo "  ./run.sh --interval 1h           # 1시간마다"
    echo ""
    echo -e "${YELLOW}💰 거래 설정:${NC}"
    echo "  ./run.sh --coin ETH              # 이더리움 거래"
    echo "  ./run.sh --amount 50000          # 5만원씩 거래"
    echo "  ./run.sh --coin ETH --amount 30000 --interval 1m"
    echo ""
    echo -e "${YELLOW}🛠️ 설정 관리:${NC}"
    echo "  ./run.sh --show-config           # 현재 설정 확인"
    echo "  ./run.sh --interactive           # 대화형 설정"
    echo "  ./run.sh --save-config my.json   # 설정 저장"
    echo "  ./run.sh --config-file my.json   # 저장된 설정 사용"
    echo ""
    echo -e "${YELLOW}🔧 전략 조정:${NC}"
    echo "  ./run.sh --short-ma 3 --long-ma 15"
    echo "  ./run.sh --rsi-period 7"
    echo ""
    echo -e "${YELLOW}⚠️ 안전 모드:${NC}"
    echo "  ./run.sh --dry-run               # 모의 거래 (기본값)"
    echo "  ./run.sh --live                  # 실제 거래 (주의!)"
    echo ""
    echo -e "${YELLOW}🔧 환경 설정:${NC}"
    echo "  ./run.sh --setup-only            # 환경만 설정"
    echo "  ./run.sh --skip-setup --interval 1m  # 설정 건너뛰고 바로 실행"
    echo ""
    echo -e "${YELLOW}🎮 GUI 모드:${NC}"
    echo "  ./run.sh --gui                   # GUI로 실행"
    echo "  ./gui                            # 직접 GUI 실행"
    echo ""
    echo -e "${PURPLE}📚 추가 정보:${NC}"
    echo "  • 상세한 사용법: USAGE_EXAMPLES.md"
    echo "  • GUI 설정 가이드: GUI_SETUP_GUIDE.md"
    echo ""
}

parse_arguments() {
    # 기본값 설정
    SETUP_ONLY=false
    SKIP_SETUP=false
    SHOW_EXAMPLES=false
    FORCE_INSTALL=false
    SHOW_HELP=false
    RUN_GUI=false

    # run.sh 전용 인수와 main.py로 전달할 인수 분리
    BOT_ARGS=()

    while [[ $# -gt 0 ]]; do
        case $1 in
            --setup-only)
                SETUP_ONLY=true
                shift
                ;;
            --skip-setup)
                SKIP_SETUP=true
                shift
                ;;
            --examples)
                SHOW_EXAMPLES=true
                shift
                ;;
            --force-install)
                FORCE_INSTALL=true
                shift
                ;;
            --gui)
                RUN_GUI=true
                shift
                ;;
            --help)
                SHOW_HELP=true
                shift
                ;;
            *)
                # 다른 모든 인수는 봇으로 전달
                BOT_ARGS+=("$1")
                shift
                ;;
        esac
    done
}

check_directory() {
    if [[ ! -f "001_python_code/main.py" ]] || [[ ! -f "001_python_code/trading_bot.py" ]]; then
        echo -e "${RED}❌ 005_money 디렉토리에서 실행해주세요.${NC}"
        echo "   필요한 파일: 001_python_code/main.py, 001_python_code/trading_bot.py"
        exit 1
    fi
    echo -e "${GREEN}✅ 디렉토리 확인 완료${NC}"
}

check_python() {
    echo -e "${CYAN}🐍 Python 버전을 확인하고 있습니다...${NC}"
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Python3가 설치되지 않았습니다.${NC}"
        echo "   Python 3.7 이상을 설치해주세요."
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo -e "${GREEN}✅ Python 버전: $PYTHON_VERSION${NC}"
}

setup_venv() {
    echo ""
    echo -e "${CYAN}📦 가상환경을 설정하고 있습니다...${NC}"

    if [[ ! -d ".venv" ]]; then
        echo "가상환경을 생성하고 있습니다..."
        python3 -m venv .venv
        echo -e "${GREEN}✅ 가상환경 생성 완료${NC}"
    else
        echo -e "${GREEN}✅ 가상환경이 이미 존재합니다${NC}"
    fi

    # 가상환경 활성화
    echo "가상환경을 활성화하고 있습니다..."
    source .venv/bin/activate
    echo -e "${GREEN}✅ 가상환경 활성화 완료${NC}"
}

install_dependencies() {
    echo ""
    echo -e "${CYAN}📦 의존성 패키지를 확인하고 있습니다...${NC}"

    # pip 업그레이드
    if [[ "$FORCE_INSTALL" == true ]]; then
        echo "pip을 업그레이드하고 있습니다..."
        pip install --upgrade pip --quiet
    fi

    # 의존성 설치
    if [[ -f "requirements.txt" ]]; then
        if [[ "$FORCE_INSTALL" == true ]]; then
            pip install -r requirements.txt --force-reinstall --quiet
        else
            pip install -r requirements.txt --quiet
        fi
    else
        if [[ "$FORCE_INSTALL" == true ]]; then
            pip install pandas requests schedule numpy --force-reinstall --quiet
        else
            pip install pandas requests schedule numpy --quiet
        fi
    fi
    echo -e "${GREEN}✅ 의존성 패키지 설치 완료${NC}"
}

check_config() {
    echo ""
    echo -e "${CYAN}🔧 설정을 확인하고 있습니다...${NC}"
    python -c "import sys; sys.path.insert(0, '001_python_code'); import config; print('✅ 설정 파일 로드 성공')" || {
        echo -e "${RED}❌ 설정 파일 로드 실패${NC}"
        exit 1
    }

    # API 키 확인
    API_CONFIGURED=$(python -c "import sys; sys.path.insert(0, '001_python_code'); import config; print(config.BITHUMB_CONNECT_KEY != 'YOUR_CONNECT_KEY')" 2>/dev/null)
    if [[ "$API_CONFIGURED" == "True" ]]; then
        echo -e "${GREEN}✅ API 키가 설정되어 있습니다${NC}"
    else
        echo -e "${YELLOW}⚠️  API 키가 설정되지 않았습니다${NC}"
        echo "   환경변수 또는 config.py에서 API 키를 설정해주세요"
        echo "   모의 거래 모드로 실행됩니다"
    fi
}

display_startup_info() {
    echo ""
    show_logo

    # 전달될 인수가 있으면 표시
    if [[ ${#BOT_ARGS[@]} -gt 0 ]]; then
        echo -e "${YELLOW}📋 설정된 옵션:${NC}"
        ARGS_STR="${BOT_ARGS[*]}"

        # 주요 옵션 하이라이트
        if [[ "$ARGS_STR" == *"--interval"* ]]; then
            for i in "${!BOT_ARGS[@]}"; do
                if [[ "${BOT_ARGS[i]}" == "--interval" ]] && [[ $((i+1)) -lt ${#BOT_ARGS[@]} ]]; then
                    echo "  ⏰ 체크 간격: ${BOT_ARGS[$((i+1))]}"
                    break
                fi
            done
        fi

        if [[ "$ARGS_STR" == *"--coin"* ]]; then
            for i in "${!BOT_ARGS[@]}"; do
                if [[ "${BOT_ARGS[i]}" == "--coin" ]] && [[ $((i+1)) -lt ${#BOT_ARGS[@]} ]]; then
                    echo "  💰 거래 코인: ${BOT_ARGS[$((i+1))]}"
                    break
                fi
            done
        fi

        if [[ "$ARGS_STR" == *"--amount"* ]]; then
            for i in "${!BOT_ARGS[@]}"; do
                if [[ "${BOT_ARGS[i]}" == "--amount" ]] && [[ $((i+1)) -lt ${#BOT_ARGS[@]} ]]; then
                    echo "  💵 거래 금액: ${BOT_ARGS[$((i+1))]}원"
                    break
                fi
            done
        fi

        if [[ "$ARGS_STR" == *"--live"* ]]; then
            echo -e "  ${RED}🔴 실제 거래 모드 (주의!)${NC}"
        else
            echo -e "  ${YELLOW}⚠️  모의 거래 모드${NC}"
        fi

        if [[ "$ARGS_STR" == *"--interactive"* ]]; then
            echo "  🛠️ 대화형 설정 모드"
        fi

        echo "  📝 전체 옵션: $ARGS_STR"
    fi

    echo ""
    echo -e "${CYAN}📈 주요 기능:${NC}"
    echo "  • 빗썸 API 연동 (인증, 거래, 잔고조회)"
    echo "  • 고도화된 거래 전략 (MA, RSI, 볼린저밴드)"
    echo "  • 포괄적 로깅 시스템"
    echo "  • 거래 내역 추적 및 리포트"
    echo "  • 안전 장치 (모의거래, 거래한도)"
    echo "  • 유연한 시간 간격 설정 (초/분/시간)"
    echo ""
    echo -e "${YELLOW}⚠️  주의사항:${NC}"
    echo "  • 기본적으로 모의 거래 모드로 실행됩니다"
    echo "  • 실제 거래 시 자금 손실 위험이 있습니다"
    echo "  • 설정을 신중히 검토하세요"
    echo "============================================================"
    echo ""
}

need_user_confirmation() {
    # 자동 실행이 필요하지 않은 조건들 확인
    ARGS_STR="${BOT_ARGS[*]}"

    if [[ "$ARGS_STR" == *"--help"* ]] || \
       [[ "$ARGS_STR" == *"--show-config"* ]] || \
       [[ "$ARGS_STR" == *"--save-config"* ]] || \
       [[ "$ARGS_STR" == *"--reset-config"* ]] || \
       [[ "$ARGS_STR" == *"--interactive"* ]]; then
        return 1  # 확인 불필요
    fi

    return 0  # 확인 필요
}

run_bot() {
    echo -e "${BLUE}🤖 거래 봇을 시작합니다...${NC}"

    # 명령어 구성
    CMD="python 001_python_code/main.py"
    if [[ ${#BOT_ARGS[@]} -gt 0 ]]; then
        CMD="$CMD ${BOT_ARGS[*]}"
    fi

    echo "실행 명령: $CMD"
    echo ""

    # 봇 실행
    python 001_python_code/main.py "${BOT_ARGS[@]}"
}

main() {
    # 인수 파싱
    parse_arguments "$@"

    # 도움말 표시
    if [[ "$SHOW_HELP" == true ]]; then
        show_help
        return
    fi

    # 사용 예시 표시
    if [[ "$SHOW_EXAMPLES" == true ]]; then
        show_examples
        return
    fi

    # GUI 모드로 실행
    if [[ "$RUN_GUI" == true ]]; then
        echo -e "${CYAN}🎮 GUI 모드로 전환합니다...${NC}"
        if [[ -x "./gui" ]]; then
            ./gui
        else
            echo -e "${YELLOW}⚠️  GUI 실행파일이 없습니다. run_gui.py로 실행합니다...${NC}"
            python3 003_Execution_script/run_gui.py
        fi
        return
    fi

    echo -e "${CYAN}🔄 빗썸 자동매매 봇 설정을 시작합니다...${NC}"
    echo ""

    # 1. 디렉토리 확인
    check_directory

    # 2. Python 버전 확인
    check_python

    # 3. 가상환경 설정 (건너뛰기 옵션 확인)
    if [[ "$SKIP_SETUP" != true ]]; then
        setup_venv
    fi

    # 4. 의존성 설치 (건너뛰기 옵션 확인)
    if [[ "$SKIP_SETUP" != true ]]; then
        install_dependencies
    fi

    # 가상환경 활성화 (설정을 건너뛴 경우에도 필요)
    if [[ "$SKIP_SETUP" == true ]] && [[ -d ".venv" ]]; then
        source .venv/bin/activate
    fi

    # 5. 설정 확인
    check_config

    # 설정만 하고 종료하는 옵션
    if [[ "$SETUP_ONLY" == true ]]; then
        echo ""
        echo -e "${GREEN}✅ 환경 설정이 완료되었습니다.${NC}"
        echo "봇을 실행하려면: python 001_python_code/main.py"
        return
    fi

    # 6. 시작 정보 표시
    display_startup_info

    # 7. 사용자 확인 (필요한 경우에만)
    if need_user_confirmation; then
        read -p "계속 진행하시겠습니까? [y/N]: " -n 1 -r
        echo ""

        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "프로그램을 종료합니다."
            return
        fi
        echo ""
    fi

    # 8. 거래 봇 실행
    run_bot
}

# 스크립트 실행
main "$@"