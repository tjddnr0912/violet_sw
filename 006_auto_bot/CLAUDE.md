# CLAUDE.md - News Bot + Sector Bot + Telegram Gemini Bot

뉴스 수집 → Gemini AI 요약 → Blogger 업로드 → Telegram 알림 자동화 봇.

## 실행

```bash
cd 006_auto_bot/001_code
source .venv/bin/activate

python main.py --mode scheduled        # 뉴스봇 스케줄 (일간/주간/월간)
python main.py --mode once             # 일간 즉시 1회
python telegram_gemini_bot.py          # Telegram Gemini Q&A 봇
python weekly_sector_bot.py            # 섹터봇 스케줄 (일요일)
python weekly_sector_bot.py --once     # 섹터봇 즉시 전체
python weekly_sector_bot.py --resume   # 섹터봇 중단 후 재개
```

## 구조 요약

| 모듈 | 역할 |
|------|------|
| `news_bot/` | RSS 파싱, Gemini 요약, 마크다운 I/O |
| `sector_bot/` | 11개 섹터 Google Search Grounding, 분석, 상태 관리 |
| `shared/` | HTML 변환, Telegram API, Blogger 업로드, Claude HTML 변환 |

## 핵심 참조

| 항목 | 값 |
|------|-----|
| AI | Gemini + Claude (HTML 변환) |
| 출력 | Blogger (7개 블로그) |
| 뉴스봇 스케줄 | Daily 07:00, Weekly 일요일, Monthly 1일 |
| 섹터봇 스케줄 | 일요일 13:00~18:00 (11개 섹터) |
| 최소 글자 수 | Gemini 1500자+, Claude HTML 1000자+ |

## 환경변수 (.env)

```bash
GEMINI_API_KEY=
BLOGGER_BLOG_ID=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
BLOG_LIST='[{"key":"...","id":"...","name":"..."}, ...]'
DEFAULT_BLOG=brave_ogu
BLOG_SELECTION_TIMEOUT=180
SECTOR_BLOGGER_BLOG_ID=9115231004981625966
SECTOR_GEMINI_MODEL=gemini-3-flash-preview
```

## 상세 문서

- [아키텍처](docs/ARCHITECTURE.md) - 디렉토리 구조, 모듈 의존성, 데이터 흐름
- [섹터봇](docs/SECTOR_BOT.md) - 11개 섹터 상세, 상태 관리, 재시작
- [텔레그램 봇](docs/TELEGRAM_BOT.md) - 블로그 선택 기능, 공유 모듈 상세
- [트러블슈팅](docs/TROUBLESHOOTING.md) - 에러 대응, 디버깅
