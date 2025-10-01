#!/bin/bash

# 빗썸 자동매매 봇 GUI 실행 스크립트 (개선된 버전)
# 실행파일 ./gui를 사용하는 것을 추천합니다

set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}${BOLD}"
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                   🤖 빗썸 자동매매 봇 GUI                     ║"
echo "║                      Bithumb Trading Bot                         ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""

# 현재 디렉토리 확인
if [[ ! -f "001_python_code/gui_app.py" ]] || [[ ! -f "001_python_code/trading_bot.py" ]]; then
    echo -e "${RED}❌ 005_money 디렉토리에서 실행해주세요.${NC}"
    echo "   필요한 파일: 001_python_code/gui_app.py, 001_python_code/trading_bot.py"
    exit 1
fi

# Python 확인
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3가 설치되지 않았습니다.${NC}"
    exit 1
fi

# 가상환경 확인 및 활성화
if [[ -d ".venv" ]]; then
    echo -e "${GREEN}✅ 가상환경을 활성화합니다...${NC}"
    source .venv/bin/activate
else
    echo -e "${YELLOW}⚠️  가상환경이 없습니다. 먼저 run.py를 실행해주세요.${NC}"
    read -p "계속 진행하시겠습니까? [y/N]: " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

# GUI 요구사항 확인
echo -e "${BLUE}🔧 GUI 요구사항을 확인하고 있습니다...${NC}"

# tkinter 확인 (대부분의 Python 설치에 포함)
python3 -c "import tkinter" 2>/dev/null || {
    echo -e "${RED}❌ tkinter가 설치되지 않았습니다.${NC}"
    echo "   Ubuntu/Debian: sudo apt-get install python3-tk"
    echo "   CentOS/RHEL: sudo yum install tkinter"
    echo "   macOS: 기본 설치됨"
    exit 1
}

# 패키지 확인
python3 -c "
import sys
try:
    import pandas, requests, schedule, numpy
    print('✅ 필요한 패키지가 모두 설치되어 있습니다.')
except ImportError as e:
    print(f'❌ 누락된 패키지: {e}')
    print('run.py를 먼저 실행하거나 pip install -r requirements.txt를 실행해주세요.')
    sys.exit(1)
"

if [[ $? -ne 0 ]]; then
    exit 1
fi

echo ""
echo -e "${GREEN}🚀 GUI를 시작합니다...${NC}"
echo -e "${YELLOW}💡 팁: GUI에서 Ctrl+C를 눌러 안전하게 종료할 수 있습니다.${NC}"
echo -e "${BLUE}💡 추천: 더 나은 경험을 위해 ./gui 또는 python run.py --gui를 사용하세요.${NC}"
echo ""

# GUI 실행
python3 003_Execution_script/run_gui.py