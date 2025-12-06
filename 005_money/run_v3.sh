#!/bin/bash
# Ver3 Trading Bot CLI 실행 스크립트

set -e

# 색상 정의
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}🤖 Ver3 Trading Bot (CLI Mode)${NC}"
echo ""

# 디렉토리 확인
if [[ ! -f "001_python_code/main.py" ]]; then
    echo -e "${RED}❌ 005_money 디렉토리에서 실행해주세요.${NC}"
    exit 1
fi

# 가상환경 활성화
if [[ -d ".venv" ]]; then
    echo -e "${GREEN}✅ 가상환경 활성화 중...${NC}"
    source .venv/bin/activate
else
    echo -e "${YELLOW}⚠️  가상환경이 없습니다. 전역 Python을 사용합니다.${NC}"
fi

# Ver3 실행
echo -e "${BLUE}🚀 Ver3 Trading Bot 시작...${NC}"
echo ""

python 001_python_code/ver3/run_cli.py "$@"
