#!/bin/bash
# ==============================================
# News Bot - Scheduled Mode (스케줄러)
# ==============================================
# 매일 지정된 시간에 자동 실행
# Ctrl+C로 중지
#
# Usage:
#   ./run_scheduled.sh           # v3 (기본값)
#   ./run_scheduled.sh v1        # 글로벌 뉴스
#   ./run_scheduled.sh v2        # 국내 뉴스 (카테고리별)
#   ./run_scheduled.sh v3        # 전체 카테고리
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/001_code"

# 버전 선택 (기본값: v3)
VERSION="${1:-v3}"

echo "=============================================="
echo "  News Bot - Scheduled Mode"
echo "=============================================="
echo "  Version: $VERSION"
echo "  Started: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  Press Ctrl+C to stop"
echo "=============================================="

# 가상환경 활성화
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "../.venv" ]; then
    source ../.venv/bin/activate
fi

# 실행
python main.py --version "$VERSION" --mode scheduled
