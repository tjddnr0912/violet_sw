#!/bin/bash

# ================================================================
# 퀀트 자동매매 시스템 실행 스크립트
# ================================================================

set -e

# 프로젝트 루트 디렉토리
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로고 출력
print_logo() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║       퀀트 자동매매 시스템 (Multi-Factor Strategy)       ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# 환경 변수 로드
load_env() {
    if [ -f ".env" ]; then
        echo -e "${GREEN}[INFO]${NC} .env 파일 로드 중..."
        export $(grep -v '^#' .env | xargs)
    else
        echo -e "${YELLOW}[WARN]${NC} .env 파일이 없습니다. config/sample.env를 참고하세요."
    fi
}

# Python 환경 확인
check_python() {
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}[ERROR]${NC} Python3가 설치되어 있지 않습니다."
        exit 1
    fi

    PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    echo -e "${GREEN}[INFO]${NC} Python 버전: $PYTHON_VERSION"
}

# 의존성 설치
install_deps() {
    echo -e "${GREEN}[INFO]${NC} 의존성 패키지 설치 중..."
    pip3 install -r requirements.txt --quiet --break-system-packages 2>/dev/null || \
    pip3 install -r requirements.txt --quiet

    # pykrx 설치 (KOSPI200 유니버스용)
    pip3 install pykrx setuptools --quiet --break-system-packages 2>/dev/null || \
    pip3 install pykrx setuptools --quiet

    # openpyxl 설치 (엑셀 출력용)
    pip3 install openpyxl --quiet --break-system-packages 2>/dev/null || \
    pip3 install openpyxl --quiet

    echo -e "${GREEN}[INFO]${NC} 의존성 설치 완료"
}

# API 키 확인
check_api_keys() {
    if [ -z "$KIS_APP_KEY" ] || [ -z "$KIS_APP_SECRET" ]; then
        echo -e "${YELLOW}[WARN]${NC} KIS API 키가 설정되지 않았습니다."
        echo "       .env 파일에 KIS_APP_KEY, KIS_APP_SECRET을 설정하세요."
    else
        echo -e "${GREEN}[INFO]${NC} KIS API 키 확인됨"
    fi
}

# 도움말 출력
print_help() {
    echo ""
    echo "사용법: $0 [명령어] [옵션]"
    echo ""
    echo "명령어:"
    echo "  daemon        통합 데몬 실행 (자동매매 + 자동관리 + 텔레그램)"
    echo "  start         자동매매 엔진만 시작"
    echo "  screen        수동 스크리닝 실행 (1회)"
    echo "  screen-full   200종목 전체 스크리닝 + 엑셀 저장"
    echo "  backtest      백테스트 실행"
    echo "  optimize      팩터 가중치 최적화"
    echo "  monitor       전략 성과 모니터링"
    echo "  rebalance     수동 리밸런싱 실행"
    echo "  status        현재 상태 조회"
    echo "  test          API 연결 테스트"
    echo "  telegram      텔레그램 알림 테스트"
    echo "  install       의존성 패키지 설치"
    echo ""
    echo "옵션:"
    echo "  --dry-run     모의 실행 (실제 주문 X)"
    echo "  --virtual     모의투자 계좌 사용 (기본값)"
    echo "  --real        실전투자 계좌 사용"
    echo "  --universe N  유니버스 크기 (기본: 200)"
    echo "  --target N    목표 종목 수 (기본: 20)"
    echo ""
    echo "예시:"
    echo "  $0 start --dry-run          # 모의 실행으로 엔진 시작"
    echo "  $0 screen --universe 100    # 100종목 스크리닝"
    echo "  $0 screen-full              # 200종목 전체 스크리닝"
    echo ""
}

# 엔진 시작
cmd_start() {
    echo -e "${GREEN}[INFO]${NC} 퀀트 자동매매 엔진 시작..."

    python3 -c "
import sys
sys.path.insert(0, '.')

from src.quant_engine import QuantTradingEngine, QuantEngineConfig

config = QuantEngineConfig(
    universe_size=${UNIVERSE_SIZE:-200},
    target_stock_count=${TARGET_COUNT:-20},
    dry_run=${DRY_RUN:-True}
)

engine = QuantTradingEngine(config=config, is_virtual=${IS_VIRTUAL:-True})
engine.start()
"
}

# 수동 스크리닝
cmd_screen() {
    echo -e "${GREEN}[INFO]${NC} 멀티팩터 스크리닝 실행..."

    python3 -c "
import sys
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings('ignore')

from src.api.kis_quant import KISQuantClient
from src.strategy.quant.screener import MultiFactorScreener, ScreeningConfig

config = ScreeningConfig(
    universe_size=${UNIVERSE_SIZE:-200},
    target_count=${TARGET_COUNT:-20}
)

client = KISQuantClient(is_virtual=${IS_VIRTUAL:-True})
screener = MultiFactorScreener(client, config)

def progress(cur, total, code):
    if cur % 20 == 0 or cur == total:
        print(f'진행: {cur}/{total} ({cur*100//total}%)')

result = screener.run_screening(progress)

print()
print('=' * 60)
print(f'스크리닝 완료: {result.elapsed_seconds:.1f}초')
print(f'유니버스: {result.universe_count}개')
print(f'필터 통과: {result.filtered_count}개')
print(f'최종 선정: {len(result.selected_stocks)}개')
print('=' * 60)
print()

print('TOP 10 선정 종목:')
for i, s in enumerate(result.selected_stocks[:10], 1):
    print(f'{i:2}. {s.code} {s.name:12} 점수:{s.composite_score:.1f}')
"
}

# 전체 스크리닝 + 엑셀
cmd_screen_full() {
    echo -e "${GREEN}[INFO]${NC} 200종목 전체 스크리닝 + 엑셀 저장..."

    python3 -c "
import sys
sys.path.insert(0, '.')
import warnings
warnings.filterwarnings('ignore')

from src.api.kis_quant import KISQuantClient
from src.strategy.quant.screener import MultiFactorScreener, ScreeningConfig

config = ScreeningConfig(
    universe_size=200,
    target_count=20
)

client = KISQuantClient(is_virtual=True)
screener = MultiFactorScreener(client, config)

def progress(cur, total, code):
    if cur % 20 == 0 or cur == total:
        print(f'진행: {cur}/{total} ({cur*100//total}%)')

print('스크리닝 시작...')
result = screener.run_screening(progress)

print()
print(f'스크리닝 완료: {result.elapsed_seconds:.1f}초')
print(f'유니버스: {result.universe_count}개 → 필터통과: {result.filtered_count}개 → 선정: {len(result.selected_stocks)}개')
print()

print('엑셀 파일 생성 중...')
excel_path = screener.export_to_excel(result, include_technical=True)
print(f'저장 완료: {excel_path}')
"
}

# 상태 조회
cmd_status() {
    echo -e "${GREEN}[INFO]${NC} 시스템 상태 조회..."

    python3 -c "
import sys
sys.path.insert(0, '.')
import json
from pathlib import Path

data_dir = Path('data/quant')
state_file = data_dir / 'engine_state.json'

print('=' * 50)
print('퀀트 시스템 상태')
print('=' * 50)

if state_file.exists():
    with open(state_file, 'r') as f:
        state = json.load(f)

    print(f'마지막 업데이트: {state.get(\"updated_at\", \"N/A\")}')
    print(f'마지막 스크리닝: {state.get(\"last_screening_date\", \"N/A\")}')
    print(f'보유 포지션: {len(state.get(\"positions\", []))}개')

    if state.get('positions'):
        print()
        print('보유 종목:')
        for pos in state['positions']:
            print(f'  - {pos[\"name\"]} ({pos[\"code\"]}): {pos[\"quantity\"]}주')
else:
    print('저장된 상태 없음')
print('=' * 50)
"
}

# API 테스트
cmd_test() {
    echo -e "${GREEN}[INFO]${NC} API 연결 테스트..."

    python3 -c "
import sys
sys.path.insert(0, '.')

from src.api.kis_quant import KISQuantClient

print('KIS API 클라이언트 초기화...')
client = KISQuantClient(is_virtual=True)

print('시가총액 순위 조회 테스트...')
rankings = client.get_market_cap_ranking(count=5)

print()
print('상위 5개 종목:')
for r in rankings:
    print(f'  {r.rank}. {r.code} {r.name}: {r.market_cap:,}억원')

print()
print('API 연결 테스트 성공!')
"
}

# 텔레그램 테스트
cmd_telegram() {
    echo -e "${GREEN}[INFO]${NC} 텔레그램 알림 테스트..."

    python3 -c "
import sys
sys.path.insert(0, '.')

from src.telegram import get_notifier

notifier = get_notifier()
result = notifier.send_message('퀀트 시스템 테스트 메시지입니다.')

if result:
    print('텔레그램 알림 전송 성공!')
else:
    print('텔레그램 알림 전송 실패. .env 설정을 확인하세요.')
"
}

# ================================================================
# 메인 실행
# ================================================================

print_logo

# 기본값 설정
UNIVERSE_SIZE=200
TARGET_COUNT=20
DRY_RUN=True
IS_VIRTUAL=True
COMMAND=""

# 인자 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        daemon|start|screen|screen-full|backtest|optimize|monitor|rebalance|status|test|telegram|install|help)
            COMMAND=$1
            shift
            ;;
        --dry-run)
            DRY_RUN=True
            shift
            ;;
        --no-dry-run)
            DRY_RUN=False
            shift
            ;;
        --virtual)
            IS_VIRTUAL=True
            shift
            ;;
        --real)
            IS_VIRTUAL=False
            echo -e "${RED}[WARN]${NC} 실전투자 모드입니다. 신중하게 사용하세요!"
            shift
            ;;
        --universe)
            UNIVERSE_SIZE=$2
            shift 2
            ;;
        --target)
            TARGET_COUNT=$2
            shift 2
            ;;
        -h|--help)
            print_help
            exit 0
            ;;
        *)
            echo -e "${RED}[ERROR]${NC} 알 수 없는 옵션: $1"
            print_help
            exit 1
            ;;
    esac
done

# 명령어가 없으면 도움말 출력
if [ -z "$COMMAND" ]; then
    print_help
    exit 0
fi

# 환경 설정
load_env
check_python

# 명령어 실행
case $COMMAND in
    install)
        install_deps
        ;;
    daemon)
        check_api_keys
        install_deps
        # 기존 데몬 프로세스 종료
        if pgrep -f "run_daemon.py" > /dev/null; then
            echo -e "${YELLOW}[INFO]${NC} 기존 데몬 프로세스 종료 중..."
            pkill -9 -f "run_daemon.py"
            sleep 2
            echo -e "${GREEN}[INFO]${NC} 기존 프로세스 종료 완료"
        fi
        echo -e "${GREEN}[INFO]${NC} 통합 데몬 시작 (자동매매 + 자동관리 + 텔레그램)..."
        if [ "$DRY_RUN" = "True" ]; then
            python3 scripts/run_daemon.py --dry-run
        else
            python3 scripts/run_daemon.py --no-dry-run
        fi
        ;;
    start)
        check_api_keys
        install_deps
        cmd_start
        ;;
    screen)
        install_deps
        cmd_screen
        ;;
    screen-full)
        install_deps
        cmd_screen_full
        ;;
    backtest)
        install_deps
        echo -e "${GREEN}[INFO]${NC} 백테스트 실행..."
        python3 scripts/run_backtest.py
        ;;
    optimize)
        install_deps
        echo -e "${GREEN}[INFO]${NC} 팩터 가중치 최적화..."
        python3 scripts/optimize_weights.py
        ;;
    monitor)
        install_deps
        echo -e "${GREEN}[INFO]${NC} 전략 성과 모니터링..."
        python3 scripts/monitor_strategy.py
        ;;
    status)
        cmd_status
        ;;
    test)
        install_deps
        check_api_keys
        cmd_test
        ;;
    telegram)
        install_deps
        cmd_telegram
        ;;
    help)
        print_help
        ;;
    *)
        echo -e "${RED}[ERROR]${NC} 알 수 없는 명령어: $COMMAND"
        print_help
        exit 1
        ;;
esac
