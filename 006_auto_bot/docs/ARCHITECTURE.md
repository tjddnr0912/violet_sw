# Architecture

## 디렉토리 구조

```
001_code/
├── investment_bot.py            # 통합 오케스트레이터 (뉴스+버핏+섹터)
├── main.py                      # 뉴스봇 (daily/weekly/monthly)
├── buffett_bot.py               # 버핏봇 (월~금, Claude CLI 분석)
├── weekly_sector_bot.py         # 섹터봇 (일요일)
├── telegram_gemini_bot.py       # Telegram Q&A → Gemini → Blogger
├── news_bot/                    # 뉴스봇 전용 모듈
│   ├── config.py                # RSS sources, schedule, labels
│   ├── aggregator.py            # RSS 파싱
│   ├── summarizer.py            # Gemini AI 요약
│   └── writer.py                # 마크다운 I/O, cleanup
├── sector_bot/                  # 섹터봇 전용 모듈
│   ├── config.py                # 11개 섹터 정의, 스케줄, 설정
│   ├── searcher.py              # Gemini Google Search Grounding
│   ├── analyzer.py              # 섹터별 분석 프롬프트
│   ├── gemini_cli.py            # Gemini CLI fallback (API 429 시 gemini -p 전환)
│   ├── comprehensive_report.py  # 종합 투자 평가 보고서 (Claude CLI 분석)
│   ├── writer.py                # 마크다운 I/O
│   └── state_manager.py         # 상태 저장/복구
├── shared/                      # 공유 모듈
│   ├── html_utils.py            # HTML 태그 처리, 마크다운 변환
│   ├── telegram_api.py          # Telegram Bot API (Inline Keyboard)
│   ├── telegram_notifier.py     # 알림 발송
│   ├── blogger_uploader.py      # Google Blogger API OAuth2
│   └── claude_html_converter.py # Claude CLI로 MD→HTML (timeout 15분)
├── prompts/                     # AI 프롬프트 템플릿
├── credentials/                 # OAuth tokens
└── logs/                        # 로그 파일
```

## 모듈 의존성

```
investment_bot.py (오케스트레이터)
├── main.NewsBot         (뉴스봇: 07:00 daily, 09:00 weekly, 10:00 monthly)
├── buffett_bot.BuffettBot   (버핏봇: 07:30 월~금)
└── weekly_sector_bot.WeeklySectorBot  (섹터봇: 일요일 13:00~19:00)

main.py (뉴스봇)
├── news_bot.config / aggregator / summarizer / writer
├── shared.blogger_uploader
└── shared.telegram_notifier

buffett_bot.py (버핏봇)
├── shared.blogger_uploader
├── shared.telegram_notifier
└── shared.claude_html_converter

weekly_sector_bot.py (섹터봇)
├── sector_bot.config / searcher / analyzer / writer / state_manager
├── sector_bot.comprehensive_report
├── shared.blogger_uploader
├── shared.telegram_notifier
└── shared.claude_html_converter

telegram_gemini_bot.py
├── shared.telegram_api (Inline Keyboard)
├── shared.html_utils
├── shared.blogger_uploader
└── shared.claude_html_converter
```

## 데이터 흐름

### News Bot
1. **Daily** (07:00): RSS → Gemini 요약 → `004_News_paper/YYYYMMDD/*.md` → Blogger → Telegram
2. **Weekly** (일요일 09:00): 월~토 일간요약 → Gemini 주간요약 → Blogger
3. **Monthly** (1일 10:00): 전월 일간요약 → Gemini 월간요약 → Blogger → 2개월 전 데이터 정리

### Buffett Bot
1. **Daily** (월~금 07:30): 뉴스봇 `blog_summary_*.md` → Claude CLI (버핏/멍거 관점 분석) → `005_Buffett_Daily/YYYYMMDD/*.md` → Blogger → Telegram

### Cleanup Logic
월간 요약 완료 후 2개월 전 데이터 자동 삭제:
- 일간 폴더 (`shutil.rmtree`), 주간 파일
- 연도 전환 처리: 1월→11월(전년), 2월→12월(전년)

## 설정 (news_bot/config.py)

| Setting | Value | Description |
|---------|-------|-------------|
| `POSTING_TIME` | "07:00" | 일간 요약 |
| `WEEKLY_POSTING_TIME` | "09:00" | 주간 요약 (일요일) |
| `MONTHLY_POSTING_TIME` | "10:00" | 월간 요약 (1일) |
| `MAX_NEWS_COUNT` | 50 | 수집 뉴스 수 |

## Dependencies

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `google-genai` | 1.0.0+ | Gemini API (뉴스봇 + 섹터봇 통합) |

2026-03 전체 SDK 통합 마이그레이션 완료: `google-generativeai` (구) → `google-genai` (신)
