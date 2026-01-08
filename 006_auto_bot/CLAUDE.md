# CLAUDE.md - News Bot

뉴스 수집 → Gemini AI 요약 → Blogger 업로드 → Telegram 알림 자동화 봇

## Commands

```bash
cd 006_auto_bot/001_code
source .venv/bin/activate

# Daily (즉시 1회)
python main.py --mode once

# Weekly (주간 요약)
python main.py --mode weekly

# Monthly (월간 요약, --no-cleanup으로 정리 스킵 가능)
python main.py --mode monthly

# Scheduled (일간 07:00, 주간 일요일 09:00, 월간 1일 10:00)
python main.py --mode scheduled

# Test (저장/업로드 없이)
python main.py --test

# Telegram Gemini Bot
python telegram_gemini_bot.py
python telegram_gemini_bot.py --test  # Blog 업로드 스킵
```

## Architecture

```
001_code/
├── main.py                   # 뉴스봇 진입점 (daily/weekly/monthly)
├── telegram_gemini_bot.py    # Telegram Q&A → Gemini → Blogger
│
├── news_bot/                 # 뉴스봇 전용 모듈
│   ├── __init__.py
│   ├── config.py             # RSS sources, schedule times, labels
│   ├── aggregator.py         # RSS 파싱
│   ├── summarizer.py         # Gemini AI 요약 (daily/weekly/monthly)
│   └── writer.py             # 마크다운 파일 I/O, cleanup
│
├── shared/                   # 공유 모듈
│   ├── __init__.py
│   ├── html_utils.py         # HTML 태그 처리, 마크다운 변환
│   ├── telegram_api.py       # Telegram Bot API 기본 클라이언트
│   ├── telegram_notifier.py  # Telegram 알림 발송
│   └── blogger_uploader.py   # Google Blogger API
│
├── credentials/              # OAuth tokens
└── logs/                     # 로그 파일
```

## Module Dependencies

```
main.py
├── news_bot.config
├── news_bot.aggregator
├── news_bot.summarizer
├── news_bot.writer
├── shared.blogger_uploader
└── shared.telegram_notifier

telegram_gemini_bot.py
├── shared.telegram_api (상속)
├── shared.html_utils
└── shared.blogger_uploader
```

## Data Flow

1. **Daily** (07:00): RSS → Gemini 요약 → `004_News_paper/YYYYMMDD/blog_summary_*.md` → Blogger → Telegram
2. **Weekly** (일요일 09:00): 월~토 일간요약 수집 → Gemini 주간요약 → `weekly/weekly_summary_*.md` → Blogger
3. **Monthly** (1일 10:00): 전월 일간요약 수집 → Gemini 월간요약 → `monthly/monthly_summary_*.md` → Blogger → **2개월 전 데이터 정리**

## Config (.env)

```
GEMINI_API_KEY=required
GEMINI_MODEL=gemini-2.5-flash

BLOGGER_ENABLED=true
BLOGGER_BLOG_ID=your_id
BLOGGER_CREDENTIALS_PATH=./credentials/blogger_credentials.json

TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_id
```

## Key Settings (news_bot/config.py)

| Setting | Value | Description |
|---------|-------|-------------|
| `POSTING_TIME` | "07:00" | 일간 요약 시간 |
| `WEEKLY_POSTING_TIME` | "09:00" | 주간 요약 (일요일) |
| `MONTHLY_POSTING_TIME` | "10:00" | 월간 요약 (1일) |
| `BLOGGER_WEEKLY_LABELS` | ['뉴스', '주간'] | 주간 포스트 라벨 |
| `BLOGGER_MONTHLY_LABELS` | ['뉴스', '월간'] | 월간 포스트 라벨 |
| `MAX_NEWS_COUNT` | 50 | 수집 뉴스 수 |

## Blogs

- **NewsBot** → Korea News Room (krnewsfeed.blogspot.com)
- **TelegramBot** → Brave Ogu (bravebabyogu.blogspot.com)

## Cleanup Logic

월간 요약 완료 후 **2개월 전** 데이터 자동 삭제:
- `YYYYMM*` 일간 폴더들 (`shutil.rmtree`)
- `weekly/weekly_summary_YYYYMM*.md` 주간 파일들

연도 전환 처리: 1월→11월(전년), 2월→12월(전년)

## Shared Modules

| Module | Class | Description |
|--------|-------|-------------|
| `html_utils.py` | `HtmlUtils` | HTML 태그 수정, Telegram HTML 변환 |
| `telegram_api.py` | `TelegramClient` | Telegram Bot API 기본 클라이언트 |
| `telegram_notifier.py` | `TelegramNotifier` | 블로그 알림 발송 (TelegramClient 상속) |
| `blogger_uploader.py` | `BloggerUploader` | Google Blogger API OAuth2 |

## Debugging

| Error | Solution |
|-------|----------|
| ModuleNotFoundError | `pip install -r requirements.txt` |
| Gemini API error | Check `GEMINI_API_KEY` |
| Blogger OAuth | Delete `credentials/blogger_token.pkl` |
| Telegram HTML parse error | Plain text fallback 자동 적용 |
