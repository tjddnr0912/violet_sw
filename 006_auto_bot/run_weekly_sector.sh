#!/bin/bash
#
# Weekly Sector Investment Bot Runner
# -----------------------------------
# 매주 일요일 9개 섹터별 투자정보를 자동 수집/분석
#
# 사용법:
#   ./run_weekly_sector.sh           # 스케줄 모드 (일요일 자동)
#   ./run_weekly_sector.sh --once    # 즉시 전체 실행
#   ./run_weekly_sector.sh --resume  # 중단 후 재개
#   ./run_weekly_sector.sh --test    # 테스트 모드
#

# 스크립트 디렉토리로 이동
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/001_code"

# Python 가상환경 활성화
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "venv" ]; then
    source venv/bin/activate
fi

# 로그 디렉토리 생성
mkdir -p logs

echo "========================================"
echo "Weekly Sector Investment Bot"
echo "========================================"
echo "Start time: $(date)"
echo "Working dir: $(pwd)"
echo ""

# 인자 전달하여 실행
python weekly_sector_bot.py "$@"

echo ""
echo "End time: $(date)"
echo "========================================"
