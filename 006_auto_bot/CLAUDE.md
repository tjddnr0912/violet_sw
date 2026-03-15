# CLAUDE.md - News Bot + Buffett Bot + Sector Bot + Telegram Gemini Bot

뉴스 수집 → AI 분석 → Blogger 업로드 → Telegram 알림 자동화 봇.

## 실행

```bash
cd 006_auto_bot/001_code
source .venv/bin/activate

python investment_bot.py               # 통합 스케줄 (뉴스+버핏+섹터)
python telegram_gemini_bot.py          # Telegram Gemini Q&A 봇

# 개별 실행
python main.py --mode once             # 뉴스봇 일간 즉시 1회
python buffett_bot.py --once           # 버핏봇 즉시 1회
python weekly_sector_bot.py --once     # 섹터봇 즉시 전체
python weekly_sector_bot.py --comprehensive  # 종합 투자 평가 보고서
```

## 구조 요약

| 모듈 | 역할 |
|------|------|
| `investment_bot.py` | 통합 오케스트레이터 (뉴스+버핏+섹터 스케줄 관리) |
| `buffett_bot.py` | 버핏/멍거 관점 일일 투자 분석 (Claude CLI) |
| `news_bot/` | RSS 파싱, Gemini 요약, 마크다운 I/O |
| `sector_bot/` | 11개 섹터 Google Search Grounding, 분석, 상태 관리 |
| `shared/` | HTML 변환, Telegram API, Blogger 업로드, Claude HTML 변환 |

## 핵심 참조

| 항목 | 값 |
|------|-----|
| AI | Gemini + Claude (분석, HTML 변환) |
| 출력 | Blogger (OgusInvest 등 7개 블로그) |
| 뉴스봇 | Daily 07:00, Weekly 일요일 09:00, Monthly 1일 10:00 |
| 버핏봇 | 월~금 07:30 (뉴스 기반, Claude CLI 분석) |
| 섹터봇 | 일요일 13:00~18:00 (11개 섹터), 19:00 종합 보고서 |

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
