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

# Telegram Gemini Bot (블로그 선택 기능 포함)
python telegram_gemini_bot.py
python telegram_gemini_bot.py --test  # Blog 업로드 스킵
```

## Architecture

```
001_code/
├── main.py                   # 뉴스봇 진입점 (daily/weekly/monthly)
├── telegram_gemini_bot.py    # Telegram Q&A → Gemini → Blogger (블로그 선택 기능)
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
│   ├── telegram_api.py       # Telegram Bot API (Inline Keyboard 지원)
│   ├── telegram_notifier.py  # Telegram 알림 발송
│   ├── blogger_uploader.py   # Google Blogger API
│   └── claude_html_converter.py  # Claude CLI로 Markdown→HTML 변환
│
├── prompts/                  # AI 프롬프트 템플릿
│   └── blogger_html_prompt.md    # Claude HTML 변환 프롬프트
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
├── shared.telegram_api (상속, Inline Keyboard 포함)
├── shared.html_utils
├── shared.blogger_uploader
└── shared.claude_html_converter
```

## Data Flow

### News Bot
1. **Daily** (07:00): RSS → Gemini 요약 → `004_News_paper/YYYYMMDD/blog_summary_*.md` → Blogger → Telegram
2. **Weekly** (일요일 09:00): 월~토 일간요약 수집 → Gemini 주간요약 → `weekly/weekly_summary_*.md` → Blogger
3. **Monthly** (1일 10:00): 전월 일간요약 수집 → Gemini 월간요약 → `monthly/monthly_summary_*.md` → Blogger → **2개월 전 데이터 정리**

### Telegram Gemini Bot (블로그 선택 기능)
```
질문 수신 → 블로그 선택 UI (Inline Keyboard) → 선택/타임아웃
                    ↓
         Gemini 처리 (1500자+ 요구)
                    ↓
         Claude HTML 변환 (1000자+ 요구)
                    ↓
         블로그 업로드 (Dual 또는 Default만)
```

**업로드 방식:**
- **블로그 선택 시**: 2군데 업로드
  - Default (Brave Ogu): HTML + Raw Data (`<details>` 태그)
  - 선택한 블로그: HTML만 (Raw Data 없음)
- **Default만 클릭 / 타임아웃**: 1군데만 업로드 (Brave Ogu)

## Config (.env)

```bash
# Gemini API
GEMINI_API_KEY=required
GEMINI_MODEL=gemini-3-flash-preview

# Blogger (기본)
BLOGGER_ENABLED=true
BLOGGER_BLOG_ID=your_id
BLOGGER_CREDENTIALS_PATH=./credentials/blogger_credentials.json
BLOGGER_TOKEN_PATH=./credentials/blogger_token.pkl

# Telegram
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_id

# Blog Selection (Telegram Gemini Bot)
BLOG_LIST='[{"key":"brave_ogu","id":"...","name":"Brave Ogu"}, ...]'
DEFAULT_BLOG=brave_ogu
BLOG_SELECTION_TIMEOUT=180  # 3분 (초)
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

## Telegram Gemini Bot - 블로그 선택 기능

### 지원 블로그 (7개)

| Key | Name | URL |
|-----|------|-----|
| brave_ogu | Brave Ogu (Default) | bravebabyogu.blogspot.com |
| soc_design | SoC Design | socdesignengineer.blogspot.com |
| ogusinvest | OgusInvest | ogusinvest.blogspot.com |
| sw_develope | SW Develope | swdevelope.blogspot.com |
| booksreview | BooksReview | booksreview333.blogspot.com |
| virtual_lifes | Virtual Life's | virtuallifeininternet.blogspot.com |
| wherewego | Where we go | wherewegoinworld.blogspot.com |

### 진행 상황 메시지

질문 후 버튼 선택 시 다음 순서로 상태 표시:
1. "Processing: Asking Gemini..."
2. "Processing: Claude에서 HTML을 생성 중..."
3. "Processing: Uploading to blog..."
4. 완료 메시지 (URL 포함)

### 최소 글자 수 요구사항

| 단계 | 최소 글자 수 | 설명 |
|------|-------------|------|
| Gemini 응답 | 1500자+ | 메타데이터 제외 본문 |
| Claude HTML | 1000자+ | HTML 태그 제외 가시적 텍스트 |

## Cleanup Logic

월간 요약 완료 후 **2개월 전** 데이터 자동 삭제:
- `YYYYMM*` 일간 폴더들 (`shutil.rmtree`)
- `weekly/weekly_summary_YYYYMM*.md` 주간 파일들

연도 전환 처리: 1월→11월(전년), 2월→12월(전년)

## Shared Modules

| Module | Class/Function | Description |
|--------|----------------|-------------|
| `html_utils.py` | `HtmlUtils` | HTML 태그 수정, Telegram HTML 변환 |
| `telegram_api.py` | `TelegramClient` | Telegram Bot API (Inline Keyboard, Callback Query 지원) |
| `telegram_notifier.py` | `TelegramNotifier` | 블로그 알림 발송 (TelegramClient 상속) |
| `blogger_uploader.py` | `BloggerUploader` | Google Blogger API OAuth2 |
| `claude_html_converter.py` | `convert_md_to_html_via_claude()` | Claude CLI로 HTML 변환 |

### telegram_api.py 주요 메서드

| Method | Description |
|--------|-------------|
| `send_message()` | 텍스트 메시지 전송 |
| `send_message_with_inline_keyboard()` | Inline Keyboard 버튼이 포함된 메시지 전송 |
| `answer_callback_query()` | 버튼 클릭 응답 (Telegram 필수) |
| `edit_message_text()` | 기존 메시지 텍스트 수정 |
| `get_updates()` | Long polling으로 업데이트 수신 |
| `test_connection()` | 봇 연결 테스트 |

## Debugging

| Error | Solution |
|-------|----------|
| ModuleNotFoundError | `pip install -r requirements.txt` |
| Gemini API error | Check `GEMINI_API_KEY` |
| Blogger OAuth | Delete `credentials/blogger_token.pkl` |
| Telegram HTML parse error | Plain text fallback 자동 적용 |
| Claude CLI not found | `pip install claude-cli` 또는 PATH 확인 |
| Blog selection timeout | `BLOG_SELECTION_TIMEOUT` 값 조정 (기본 180초) |
