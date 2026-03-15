#!/bin/bash
#
# Investment Bot Runner (Orchestrator)
# -------------------------------------
# 섹터봇(일요일) + 버핏봇(월~금)을 하나의 프로세스로 관리
#
# 사용법:
#   ./run_investment_bot.sh           # 스케줄 모드
#   ./run_investment_bot.sh --test    # 테스트 모드
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/001_code"

if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

mkdir -p logs

echo "========================================"
echo "Investment Bot (Sector + Buffett)"
echo "========================================"
echo "Start time: $(date)"
echo "Working dir: $(pwd)"
echo ""

python investment_bot.py "$@"

echo ""
echo "End time: $(date)"
echo "========================================"
