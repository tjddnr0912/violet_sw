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
│   ├── claude_html_converter.py # Claude CLI로 MD→HTML (timeout 15분)
│   └── research_orchestrator.py # 다라운드 Gemini × Claude 5차원 검증 (Deep research 엔진)
├── prompts/                     # AI 프롬프트 템플릿 (fallback용)
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
├── shared.claude_html_converter
└── shared.research_orchestrator   # 평문 메시지 → run_research (Deep, default)
                                    # /quick 메시지 → run_gemini (Quick opt-out)
```

### Research Modes (telegram_gemini_bot.py)

평문 메시지는 `mode="deep"`으로 분류되어 `run_research`(Round 1 Gemini → Claude 5차원 평가 → 필요 시 Round N → Claude 종합)를 거친다. `/quick <질문>`은 `mode="quick"`으로 분류되어 기존 단발 `run_gemini` 흐름을 그대로 사용한다. 두 모드 모두 동일한 Claude HTML 변환 + Blogger 업로드 파이프라인을 통과한다. 상세는 [TELEGRAM_BOT.md](TELEGRAM_BOT.md#research-modes-deep-default-quick-opt-out) 참고.

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

## 스킬 파일 (프롬프트 외부화)

모든 AI 프롬프트(Claude `claude -p` + Gemini API/CLI)는 외부 스킬 파일에서 로드한다. 코드 수정 없이 스킬 파일만 편집하여 분석/변환 품질을 개선할 수 있다.

| 호출 위치 | AI | 용도 | 스킬 파일 |
|-----------|-----|------|----------|
| `news_bot/summarizer.py` | Gemini API | 뉴스 요약 (일간/주간/월간) | `~/.claude/skills/news-summarizer/SKILL.md` |
| `sector_bot/searcher.py` | Gemini API | 섹터 뉴스 검색 | `~/.claude/skills/sector-search/SKILL.md` |
| `sector_bot/analyzer.py` | Gemini API | 섹터별 투자 분석 (11개 페르소나) | `~/.claude/skills/sector-analysis/SKILL.md` |
| `sector_bot/comprehensive_report.py` | Claude CLI | 11개 섹터 종합 보고서 | `~/.claude/skills/sector-comprehensive/SKILL.md` |
| `buffett_bot.py` | Claude CLI | 버핏/멍거 투자 분석 | `~/.claude/skills/buffett/SKILL.md` |
| `telegram_gemini_bot.py` | Gemini CLI | 종합 리서치 Q&A | `~/.claude/skills/telegram-qa/SKILL.md` |
| `shared/claude_html_converter.py` | Claude CLI | MD→HTML 변환 (공유) | `~/.claude/skills/blogger-html/SKILL.md` (fallback: `prompts/`) |

로딩 방식: YAML frontmatter(`--- ... ---`) 자동 제거 후 프롬프트에 삽입. 동적 데이터(날짜, 뉴스, 섹터 데이터)는 코드에서 추가.

아키텍처 원칙: **콘텐츠 레이어**(분석/데이터 수집 스킬) → **프레젠테이션 레이어**(`blogger-html` 스킬이 HTML 변환 시 블로그 스타일/SEO 처리).

`blogger-html` 스킬의 프레젠테이션 기능:
- **시각화 자동 삽입**: 본문에 수치 비교·비중·추세·순위 데이터가 있으면 수평 막대 차트, 진행률 바, 도넛 차트(SVG), 히트맵 표, 스파크라인(SVG) 중 적절한 형식을 자동 선택해 인라인 삽입
- **Blogger 호환성**: 외부 JS 라이브러리/`<style>` 블록/`::before` 가상요소 사용 금지, 순수 HTML/CSS + 인라인 SVG만 사용
- **색상 팔레트 일관성**: 카테고리별·시그널별 고정 팔레트를 차트에도 재사용

## Dependencies

| 패키지 | 버전 | 용도 |
|--------|------|------|
| `google-genai` | 1.0.0+ | Gemini API (뉴스봇 + 섹터봇 통합) |

2026-03 전체 SDK 통합 마이그레이션 완료: `google-generativeai` (구) → `google-genai` (신)
