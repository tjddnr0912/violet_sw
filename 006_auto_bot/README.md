# 006_auto_bot

뉴스 자동 수집/요약/블로그 포스팅 봇

## Structure

```
000_proposal/   # 기획 문서 (legacy)
001_code/       # 소스 코드 (main)
002_doc/        # 문서 (deprecated)
003_test_code/  # 테스트 코드
004_News_paper/ # 생성된 뉴스 요약 파일
```

## Quick Start

```bash
cd 001_code
source .venv/bin/activate
python main.py --version v3 --mode once
```

자세한 내용은 `CLAUDE.md` 참조
