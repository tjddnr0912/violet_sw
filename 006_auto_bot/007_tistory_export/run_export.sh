#!/bin/bash
# Tistory Blog Export Tool - Run Script
# ======================================
# 티스토리 블로그 게시글을 Markdown + Image로 로컬에 다운로드

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 가상환경 확인 및 활성화
if [ -d ".venv" ]; then
    source .venv/bin/activate
elif [ -d "../.venv" ]; then
    source ../.venv/bin/activate
elif [ -d "../001_code/.venv" ]; then
    source ../001_code/.venv/bin/activate
fi

# 의존성 설치 확인
check_dependencies() {
    python3 -c "import selenium" 2>/dev/null
    if [ $? -ne 0 ]; then
        echo "Installing dependencies..."
        pip3 install -r requirements.txt
    fi
}

# 도움말
show_help() {
    echo "Tistory Blog Export Tool"
    echo "========================"
    echo ""
    echo "Usage:"
    echo "  ./run_export.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --blog-url URL     블로그 URL (필수, 또는 .env 설정)"
    echo "  --max-posts N      최대 N개 게시글만 내보내기"
    echo "  --category CAT     특정 카테고리만 필터링"
    echo "  --single-post ID   단일 게시글만 내보내기"
    echo "  --list-only        게시글 목록만 표시 (다운로드 안 함)"
    echo "  --no-headless      브라우저 표시 모드"
    echo "  --help             이 도움말 표시"
    echo ""
    echo "Examples:"
    echo "  # 모든 게시글 내보내기"
    echo "  ./run_export.sh --blog-url https://gong-mil-le.tistory.com"
    echo ""
    echo "  # 최근 10개만"
    echo "  ./run_export.sh --blog-url https://gong-mil-le.tistory.com --max-posts 10"
    echo ""
    echo "  # 목록만 확인"
    echo "  ./run_export.sh --blog-url https://gong-mil-le.tistory.com --list-only"
    echo ""
}

# 메인
main() {
    if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
        show_help
        exit 0
    fi

    check_dependencies
    python3 export.py "$@"
}

main "$@"
