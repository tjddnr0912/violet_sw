#!/bin/bash
#
# Buffett Bot Runner
# ------------------
# 매일 오전 7:30 버핏/멍거 관점 투자 분석 보고서 생성
#
# 사용법:
#   ./run_buffett_bot.sh           # 스케줄 모드 (매일 07:30)
#   ./run_buffett_bot.sh --once    # 즉시 1회 실행
#   ./run_buffett_bot.sh --test    # 테스트 (업로드 스킵)
#

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/001_code"

# Python 가상환경 활성화
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

mkdir -p logs

echo "========================================"
echo "Buffett Bot - Daily Investment Analysis"
echo "========================================"
echo "Start time: $(date)"
echo "Working dir: $(pwd)"
echo ""

python buffett_bot.py "$@"

echo ""
echo "End time: $(date)"
echo "========================================"
