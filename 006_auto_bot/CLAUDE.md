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
| `telegram_gemini_bot.py` | Telegram Q&A 봇 — 평문=Deep research(default), `/quick`=단발 |
| `news_bot/` | RSS 파싱, Gemini 요약, 마크다운 I/O |
| `sector_bot/` | 11개 섹터 Google Search Grounding, 분석, 상태 관리 |
| `shared/` | HTML 변환, Telegram API, Blogger 업로드, Claude HTML 변환, **research_orchestrator** (다라운드 Gemini × Claude 5차원 검증) |

## 핵심 참조

| 항목 | 값 |
|------|-----|
| AI | Gemini + Claude (분석, HTML 변환, 스킬 파일 참조) |
| 출력 | Blogger (OgusInvest 등 7개 블로그) |
| 뉴스봇 | Daily 06:00 (orchestrator + 5차원 게이트), Weekly 일요일 07:00, Monthly 1일 07:30. `news_bot/orchestrator.py`가 균형/신선도/다양성/출처신뢰/글로벌균형 검증 + Gemini CLI 갭필 |
| 버핏봇 | 월~금 06:30 (뉴스 기반, Claude CLI 분석) |
| 섹터봇 | 일요일 12:00~18:40 (11개 섹터, 40분 간격), 19:20 텔레그램 알림, 19:40 종합 보고서. `sector_bot/orchestrator.py`가 5차원 검증 게이트 + 갭필 + 종합 게이트 수행 |

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
SECTOR_GEMINI_MODEL=gemini-3.1-flash-lite-preview
RESEARCH_QUICK_COMMAND=/quick    # Telegram Q&A 단발 모드 트리거 (default `/quick`)
RESEARCH_MAX_ROUNDS=3            # Deep research 라운드 상한 (1~4, default 3)
```

## 스킬 파일 (프롬프트 외부화)

모든 AI 프롬프트(Claude + Gemini)는 `~/.claude/skills/`에서 로드. 스킬 파일 수정만으로 코드 변경 없이 품질 개선 가능.

| 봇 | 스킬 파일 |
|----|----------|
| 뉴스봇 (일간/주간/월간) | `news-summarizer/SKILL.md` |
| 섹터봇 검색 | `sector-search/SKILL.md` |
| 섹터봇 분석 | `sector-analysis/SKILL.md` |
| 섹터 종합 보고서 | `sector-comprehensive/SKILL.md` |
| 버핏봇 분석 | `buffett/SKILL.md` |
| 텔레그램 Q&A | `telegram-qa/SKILL.md` |
| HTML 변환 (공유) | `blogger-html/SKILL.md` |

## 트러블슈팅 핵심

Gemini 429/503 / Claude CLI empty / Blogger OAuth / Telegram HTML parse / Sector resume·state 손상 — 각 항목은 6필드 + Claude 진단 미스 기록 → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## 상세 문서

| 주제 | 파일 |
|------|------|
| 아키텍처·모듈·데이터 흐름 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 명령 카탈로그 (통합·개별·디버깅) | [docs/COMMANDS.md](docs/COMMANDS.md) |
| 트러블슈팅 + Claude 진단 미스 기록 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 환경변수·블로그·스킬 외부화·Deep research | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| 변경 이력 | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| 섹터봇 상세 (보존) | [docs/SECTOR_BOT.md](docs/SECTOR_BOT.md) |
| 뉴스봇 상세 (orchestrator + 5차원 게이트) | [docs/NEWS_BOT.md](docs/NEWS_BOT.md) |
| 텔레그램 봇 상세 (보존) | [docs/TELEGRAM_BOT.md](docs/TELEGRAM_BOT.md) |
