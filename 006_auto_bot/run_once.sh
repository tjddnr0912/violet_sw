#!/bin/bash
# ==============================================
# News Bot - Once Mode (1회 실행)
# ==============================================
# 뉴스 수집 → AI 요약 → 블로그 업로드를 1회 실행
#
# Usage:
#   ./run_once.sh           # v3 (기본값)
#   ./run_once.sh v1        # 글로벌 뉴스
#   ./run_once.sh v2        # 국내 뉴스 (카테고리별)
#   ./run_once.sh v3        # 전체 카테고리
# ==============================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/001_code"

# 버전 선택 (기본값: v3)
VERSION="${1:-v3}"

echo "=============================================="
echo "  News Bot - Once Mode"
echo "=============================================="
echo "  Version: $VERSION"
echo "  Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="

# 가상환경 활성화
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "../.venv" ]; then
    source ../.venv/bin/activate
fi

# 실행
python main.py --version "$VERSION" --mode once

echo ""
echo "=============================================="
echo "  Completed at $(date '+%Y-%m-%d %H:%M:%S')"
echo "=============================================="
