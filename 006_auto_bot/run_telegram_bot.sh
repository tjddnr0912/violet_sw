#!/bin/bash
#
# Telegram Gemini Blogger Bot 실행 스크립트
# -----------------------------------------
# 텔레그램 메시지 → Gemini 응답 → Blogger 업로드
#
# Usage:
#   ./run_telegram_bot.sh           # 일반 실행
#   ./run_telegram_bot.sh --test    # 테스트 모드 (블로그 업로드 스킵)
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CODE_DIR="$SCRIPT_DIR/001_code"

cd "$CODE_DIR" || exit 1

# 가상환경 활성화 (있으면)
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# .env 파일 확인
if [ ! -f ".env" ]; then
    echo "오류: .env 파일이 없습니다."
    echo "필요한 환경변수:"
    echo "  TELEGRAM_BOT_TOKEN"
    echo "  TELEGRAM_CHAT_ID"
    echo "  BLOGGER_BLOG_ID"
    exit 1
fi

echo "=========================================="
echo " Telegram Gemini Blogger Bot"
echo "=========================================="
echo ""

# 실행
python telegram_gemini_bot.py "$@"
