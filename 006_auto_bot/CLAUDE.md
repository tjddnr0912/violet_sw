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

# Weekly Sector Bot (주간 섹터 투자정보)
python weekly_sector_bot.py           # 스케줄 모드 (일요일 자동)
python weekly_sector_bot.py --once    # 즉시 전체 실행
python weekly_sector_bot.py --resume  # 중단 후 재개
python weekly_sector_bot.py --sector 1  # 특정 섹터만 (1-9)
python weekly_sector_bot.py --test    # 테스트 (업로드 스킵)
python weekly_sector_bot.py --status  # 상태 확인
```

## Architecture

```
001_code/
├── main.py                   # 뉴스봇 진입점 (daily/weekly/monthly)
├── telegram_gemini_bot.py    # Telegram Q&A → Gemini → Blogger (블로그 선택 기능)
├── weekly_sector_bot.py      # 주간 섹터 투자정보 봇
│
├── news_bot/                 # 뉴스봇 전용 모듈
│   ├── __init__.py
│   ├── config.py             # RSS sources, schedule times, labels
│   ├── aggregator.py         # RSS 파싱
│   ├── summarizer.py         # Gemini AI 요약 (daily/weekly/monthly)
│   └── writer.py             # 마크다운 파일 I/O, cleanup
│
├── sector_bot/               # 섹터봇 전용 모듈
│   ├── __init__.py
│   ├── config.py             # 9개 섹터 정의, 스케줄, 설정
│   ├── searcher.py           # Gemini Google Search Grounding
│   ├── analyzer.py           # 섹터별 분석 프롬프트
│   ├── writer.py             # 마크다운 파일 I/O
│   └── state_manager.py      # 상태 저장/복구 (재시작용)
│
├── shared/                   # 공유 모듈
│   ├── __init__.py
│   ├── html_utils.py         # HTML 태그 처리, 마크다운 변환
│   ├── telegram_api.py       # Telegram Bot API (Inline Keyboard 지원)
│   ├── telegram_notifier.py  # Telegram 알림 발송
│   ├── blogger_uploader.py   # Google Blogger API
│   └── claude_html_converter.py  # Claude CLI로 Markdown→HTML 변환 (timeout 15분)
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

weekly_sector_bot.py
├── sector_bot.config
├── sector_bot.searcher
├── sector_bot.analyzer
├── sector_bot.writer
├── sector_bot.state_manager
├── shared.blogger_uploader
├── shared.telegram_notifier
└── shared.claude_html_converter
```

## Data Flow

### News Bot
1. **Daily** (07:00): RSS → Gemini 요약 → `004_News_paper/YYYYMMDD/blog_summary_*.md` → Blogger → Telegram
2. **Weekly** (일요일 09:00): 월~토 일간요약 수집 → Gemini 주간요약 → `weekly/weekly_summary_*.md` → Blogger
3. **Monthly** (1일 10:00): 전월 일간요약 수집 → Gemini 월간요약 → `monthly/monthly_summary_*.md` → Blogger → **2개월 전 데이터 정리**

### Weekly Sector Bot
- **일요일 13:00~17:00**: 9개 섹터 순차 처리
- 각 섹터: Gemini Google Search → 섹터별 분석 → 마크다운 저장 → Claude HTML → OgusInvest 블로그
- 저장 경로: `004_Sector_Weekly/YYYYMMDD/sector_XX_name.md`
- 재시작 기능: 같은 주 내에서 `--resume`로 중단 지점부터 재개

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

# Weekly Sector Bot
SECTOR_BLOGGER_BLOG_ID=9115231004981625966  # OgusInvest (ogusinvest.blogspot.com)
SECTOR_GEMINI_MODEL=gemini-3-flash-preview  # 섹터봇용 Gemini 모델
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
| `claude_html_converter.py` | `convert_md_to_html_via_claude()` | Claude CLI로 HTML 변환 (투자 면책조항 옵션) |

### telegram_api.py 주요 메서드

| Method | Description |
|--------|-------------|
| `send_message()` | 텍스트 메시지 전송 |
| `send_message_with_inline_keyboard()` | Inline Keyboard 버튼이 포함된 메시지 전송 |
| `answer_callback_query()` | 버튼 클릭 응답 (Telegram 필수) |
| `edit_message_text()` | 기존 메시지 텍스트 수정 |
| `get_updates()` | Long polling으로 업데이트 수신 |
| `test_connection()` | 봇 연결 테스트 |

### claude_html_converter.py 투자 면책조항

`convert_md_to_html_via_claude()` 함수는 `include_investment_disclaimer` 파라미터로 투자 면책조항 포함 여부 제어:

| Bot | include_investment_disclaimer | 면책조항 |
|-----|-------------------------------|----------|
| News Bot (main.py) | `True` | 포함 |
| Sector Bot (weekly_sector_bot.py) | `True` | 포함 |
| Telegram Gemini Bot (telegram_gemini_bot.py) | `False` (기본값) | 제외 |

**면책조항 내용**: "본 자료는 투자 권유가 아니며, 투자에 대한 결정과 책임은 전적으로 본인에게 있습니다."

**공통 금지 사항**: AI, 자동 생성, Gemini, Claude 등 AI 관련 문구 (모든 봇에 적용)

## Debugging

| Error | Solution |
|-------|----------|
| ModuleNotFoundError | `pip install -r requirements.txt` |
| Gemini API error | Check `GEMINI_API_KEY` |
| Blogger OAuth | Delete `credentials/blogger_token.pkl` |
| Telegram HTML parse error | Plain text fallback 자동 적용 |
| Claude CLI not found | `pip install claude-cli` 또는 PATH 확인 |
| Blog selection timeout | `BLOG_SELECTION_TIMEOUT` 값 조정 (기본 180초) |
| Sector bot resume 실패 | 다른 주에 시작 - `--reset` 후 `--once` 실행 |
| Gemini Search 실패 | API 키 확인, 재시도 자동 (3회, 지수 백오프) |
| Sector state 손상 | `python weekly_sector_bot.py --reset` |

---

## Weekly Sector Bot

매주 일요일 9개 섹터별 투자정보를 자동 수집/분석하여 OgusInvest 블로그에 업로드

### 실행 방법

```bash
cd 006_auto_bot/001_code
source .venv/bin/activate

python weekly_sector_bot.py           # 스케줄 모드 (일요일 자동)
python weekly_sector_bot.py --once    # 즉시 전체 실행
python weekly_sector_bot.py --resume  # 중단 후 재개
python weekly_sector_bot.py --sector 1  # 특정 섹터만 (1-9)
python weekly_sector_bot.py --test    # 테스트 (업로드 스킵)
python weekly_sector_bot.py --status  # 상태 확인
python weekly_sector_bot.py --reset   # 상태 초기화
```

### 9개 섹터 상세 정보

| ID | 섹터 | 영문명 | 시간 |
|----|------|--------|------|
| 1 | AI/양자컴퓨터 | ai_quantum | 13:00 |
| 2 | 금융 | finance | 13:30 |
| 3 | 조선/항공/우주 | shipbuilding_aerospace | 14:00 |
| 4 | 에너지 | energy | 14:30 |
| 5 | 바이오 | bio | 15:00 |
| 6 | IT/통신/Cloud/DC | it_cloud | 15:30 |
| 7 | 주식시장 | stock_market | 16:00 |
| 8 | 반도체 | semiconductor | 16:30 |
| 9 | 자동차/배터리/로봇 | auto_battery_robot | 17:00 |

### 섹터별 분석 초점

| ID | 섹터 | 분석 초점 |
|----|------|-----------|
| 1 | AI/양자컴퓨터 | AI 기술발표/벤치마크, MCP/Skills 에이전트, 양자컴퓨팅 (IBM, Google, IonQ), AI 반도체 |
| 2 | 금융 | 기준금리/통화정책 (Fed, ECB), 월가 전망, CPI/인플레이션, 고용지표, 귀금속(금/은) |
| 3 | 조선/항공/우주 | 조선 수주 (HD현대, 삼성중공업), Boeing/Airbus, SpaceX/위성, 방산 수출 |
| 4 | 에너지 | 신재생에너지, 원유 WTI/Brent, 천연가스, 원자력/SMR, ESS |
| 5 | 바이오 | FDA 승인, 임상시험, 유전자치료/CRISPR, 바이오텍 M&A/IPO |
| 6 | IT/통신/Cloud/DC | AWS/Azure/GCP, 데이터센터 Capex, 5G/통신, 사이버보안, SaaS |
| 7 | 주식시장 | S&P500/Nasdaq 전망, 지정학 리스크, 무역분쟁, 글로벌 시장, VIX |
| 8 | 반도체 | 파운드리 (TSMC, 삼성), 장비 (ASML), Fabless (NVIDIA, AMD), 메모리 가격 |
| 9 | 자동차/배터리/로봇 | EV 판매 (Tesla, BYD), 배터리 (LG, 삼성SDI, CATL), 자율주행, 휴머노이드 로봇 |

### 파일 저장 구조

```
004_Sector_Weekly/
└── YYYYMMDD/
    ├── sector_01_ai_quantum.md
    ├── sector_02_finance.md
    ├── sector_03_shipbuilding_aerospace.md
    ├── sector_04_energy.md
    ├── sector_05_bio.md
    ├── sector_06_it_cloud.md
    ├── sector_07_stock_market.md
    ├── sector_08_semiconductor.md
    └── sector_09_auto_battery_robot.md
```

### 블로그 업로드 형식

- **블로그**: OgusInvest (Blog ID: `9115231004981625966`)
- **제목**: `{날짜} {N}주차 {섹터명} 투자정보` (예: "2026-02-02 1주차 AI/양자컴퓨터 투자정보")
- **라벨**: `[섹터명, 주간, 투자정보]`

### 설정 (sector_bot/config.py)

| Setting | Value | Description |
|---------|-------|-------------|
| `GEMINI_MODEL` | gemini-3-flash-preview | Gemini 모델 |
| `BLOGGER_BLOG_ID` | 9115231004981625966 | OgusInvest 블로그 ID |
| `MAX_RETRIES` | 3 | API 호출 최대 재시도 |
| `RETRY_DELAY` | 60초 | 재시도 대기 (지수 백오프) |
| `CLAUDE_TIMEOUT` | 900초 (15분) | Claude CLI 타임아웃 |
| `SCHEDULE_DAY` | 6 (Sunday) | 스케줄 실행 요일 |

### State Management

- **상태 파일**: `sector_bot/state.json`
- **주차 키**: YYYY-WW 형식 (같은 주 내에서만 재개 가능)
- **저장 정보**: 완료 섹터, 실패 섹터, 블로그 URL

```bash
# 상태 확인
python weekly_sector_bot.py --status

# 출력 예시:
# === Sector Bot State ===
# Week: 2026-05
# Progress: 5/9 (55%)
# Completed: [1, 2, 3, 4, 5]
# Failed: []
# Last Update: 2026-02-02T15:30:00
```

### Telegram 알림

- **섹터 완료 시**: 섹터명 + 블로그 URL
- **전체 완료 시**: 요약 (완료/실패 카운트 + 모든 URL)

### 에러 처리

| 에러 | 처리 |
|------|------|
| Gemini Search 실패 | 3회 재시도 (60초→120초→240초 지수 백오프) |
| Gemini Safety Filter | BLOCK_NONE 설정으로 비활성화 |
| Claude CLI 타임아웃 | 15분 후 마크다운 폴백 |
| 네트워크 에러 | 지수 백오프 재시도 |
| SSL 인증서 | `ssl._create_unverified_context` 사용 |

### 로그 파일

섹터봇은 날짜별 로그 파일을 생성합니다:

```
logs/
├── news_bot_YYYYMMDD.log      # 뉴스봇
└── sector_bot_YYYYMMDD.log    # 섹터봇
```

### Dependencies (2026-02 업데이트)

섹터봇은 Google Search Grounding을 위해 새로운 SDK를 사용합니다:

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `google-genai` | 1.61.0+ | 섹터봇 Google Search Grounding |
| `google-generativeai` | 0.8.5+ | 뉴스봇 Gemini API |

**SDK 마이그레이션 (2026-02-01):**
- 섹터봇: `google.generativeai` → `google.genai` (새 SDK)
- 이유: `google_search_retrieval` deprecated → `types.Tool(google_search=types.GoogleSearch())` 사용
