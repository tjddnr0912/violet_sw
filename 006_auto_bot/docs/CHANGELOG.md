# 006_auto_bot 변경 이력

날짜순 (최신 위).

---

## 2026-05-04: 뉴스봇 5차원 검증 게이트 + Gemini CLI 갭필

- `news_bot/orchestrator.py` 도입: RSS 수집 → 5차원 게이트 → Gemini CLI 갭필 → 요약 시퀀스
- `news_bot/dimensions.py`: 균형/신선도/다양성/출처신뢰/글로벌균형 5차원 정의 + Claude judge (fail-open)
- `news_bot/config.py`: `HOURS_LIMIT_BY_CATEGORY` 추가 (정치/주식/암호화폐 6h, 경제/사회/국제/IT 12h, 문화 24h)
- `news_bot/aggregator.py`: `fetch_news` / `get_daily_news`에 `hours_by_category` 매개변수 추가
- `news_bot/summarizer.py`: Gemini API 429 → CLI fallback 자동 전환 (`_use_cli_fallback` 플래그)
- `main.py`: `run_daily_task` Step 1을 `aggregator.get_daily_news` → `run_news_research` 호출로 교체
- `~/.claude/skills/news-summarizer/SKILL.md`: 모순 명시 제약 추가 → `## 📌 매체 간 시각 차이` 자동 생성
- Hard cap: 12분 (RSS 자체 3-5분 + 갭필 최대 4회)
- 라이브 검증: 2026-05-04 14:18 — 균형/글로벌균형 fail → 정치·주식·암호화폐 갭필 → 보고서에 특검법·프로젝트 프리덤 매체 간 시각 차이 자동 추출 ✓
- 상세 → [NEWS_BOT.md](NEWS_BOT.md)

## 2026-05-03 ~ 2026-05-04: 섹터봇 5차원 검증 게이트

- `sector_bot/orchestrator.py` 도입: 검색 → 5차원 게이트 (정의/현황/근거/반론/적용) → 갭필 → 분석
- `sector_bot/dimensions.py`: 5차원 정량 체크 + Claude judge (fail-open) + 종합 변형 (`claude_judge_comprehensive`)
- `sector_bot/comprehensive_report.py`: 1차 합성 → 5차원 게이트 → 미달 시 1회 재합성
- `weekly_sector_bot.py` 스케줄: 12:00 시작, 40분 간격 (구 13:00/30분), 텔레그램 19:20, 종합 19:40
- `--deep` CLI 플래그: max_rounds=3 (기본 2)
- `~/.claude/skills/sector-analysis/SKILL.md` + `sector-comprehensive/SKILL.md`: 모순 명시 제약 추가
- Hard cap: 8분/섹터, CLI fallback 활성 시 갭필 스킵
- 라이브 검증: 2026-05-04 06:43 (섹터 1) / 06:51 (종합) ✓
- 상세 → [SECTOR_BOT.md](SECTOR_BOT.md)

## 2026-05-04: shared/gemini_cli.py로 이동

- `sector_bot/gemini_cli.py` → `shared/gemini_cli.py` (`git mv`로 이력 보존)
- sector_bot 3개 모듈 + 뉴스봇 신규 모듈이 모두 import — cross-bot 재사용 깔끔하게

## 2026-04-26 ~ 2026-04-30: Deep research 통합

- `shared/research_orchestrator.py` 도입: Gemini × Claude 다라운드 5차원 검증 루프
- `RESEARCH_QUICK_COMMAND`, `RESEARCH_MAX_ROUNDS` env vars 추가
- Telegram Q&A 봇: 평문=Deep research(default), `/quick`=단발 (opt-out 패턴)
- Round-1 broad sweep + Round-N targeted gap-fill 구조
- Early-stop: `verdict=pass`면 즉시 synth 점프
- `_run_gemini_round`, `_evaluate_round`, `_synthesize` 분리 — 한 모델 자기평가 방지
- Live integration smoke test (env-gated `RUN_LIVE_RESEARCH_TEST=1`)
- 상세 → [CONFIGURATION.md#deep-research-동작](CONFIGURATION.md)

## 2026-04-23: blogger-html 스킬 시각화 지원

- `blogger-html/SKILL.md`에 차트·테이블 시각화 패턴 추가
- 섹터봇 종합 보고서에서 활용

## 2026-04: sector_bot CLI fallback

- Gemini API 장애 시 CLI 호출로 retry exhaustion 후에도 한 번 더 fallback
- 일요일 오후 섹터봇 빈 결과 사고 방지

## 2026-03: Buffett persona bot 도입

- `buffett_bot.py` — 워런 버핏 / 찰리 멍거 페르소나 일일 투자 분석
- Claude CLI 기반 (Gemini와 분리)

## 2026-03: Prompt externalization

- 모든 AI 프롬프트를 `~/.claude/skills/<bot>/SKILL.md`로 외부화
- 코드 수정 없이 스킬 파일만 수정으로 품질 개선 가능
- 7개 스킬 정리: news-summarizer, sector-search, sector-analysis, sector-comprehensive, buffett, telegram-qa, blogger-html

## 2026-03: 섹터봇 11개 분리

- `weekly_sector_bot.py` — 11개 섹터 (Tech / Healthcare / Financials / Energy / Industrials / Consumer / Real Estate / Materials / Utilities / Communication / Crypto)
- 일요일 13:00~18:00 분산 실행 (Gemini API quota 분산)
- 19:00 종합 투자 평가 보고서

## 2026-02: 다중 블로그 지원

- `BLOG_LIST` env var로 다중 블로그 등록
- Telegram에서 발행 시 블로그 선택 prompt
- `BLOG_SELECTION_TIMEOUT` (기본 180s) 후 `DEFAULT_BLOG` 사용
