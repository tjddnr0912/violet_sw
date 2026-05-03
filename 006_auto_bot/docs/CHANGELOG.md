# 006_auto_bot 변경 이력

날짜순 (최신 위).

---

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
