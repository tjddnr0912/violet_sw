# 006_auto_bot 변경 이력

날짜순 (최신 위).

---

## 2026-05-27 PM: Grounded 호출 4곳 → Claude CLI + WebSearch 재이전

- **배경**: 오전에 끝낸 "Gemini API + 모델 fallback chain" 마이그레이션 직후 라이브 운영에서 모든 4개 모델이 429를 반환하는 현상 발생. AI Studio dashboard에서는 RPM/TPM/RPD가 거의 0%인데도 grounded call이 거부됨. **원인 진단 결과: Gemini 3.x의 `google_search` grounding은 모델 API quota와 별개의 quota bucket을 사용**하고 dashboard에 노출되지 않음. 무료 티어 한도가 매우 빡빡해 일상 사용으로 즉시 소진됨. (참고: Gemini 2.5-flash만 grounding이 살아남는데 그건 prompt당 과금 모델이라 grounding이 prompt charge에 포함되기 때문.)
- **결정**: 단일 모델(2.5-flash)에 의존하는 구조 대신, grounding이 필요한 4개 호출지점을 **Claude CLI + WebSearch**로 전면 이전. Anthropic의 web_search tool은 별도 quota bucket에서 동작하며 `claude -p` 모드에서 자동 활성화됨. 모델은 `--model haiku/sonnet/opus` + `--fallback-model`로 호출 시점에 선택 가능.
- **신규 모듈**: `shared/claude_search.py` — `claude_websearch(prompt, model, fallback_model, timeout)` wrapper. `ClaudeSearchResponse(text, sources, model_used, elapsed_seconds)` 반환. `Sources:` 푸터에서 URL 자동 추출.
- **갱신 파일 (grounding 호출 4곳)**:
  - `telegram_gemini_bot.py` (quick mode) — Sonnet + Haiku fallback
  - `shared/research_orchestrator.py` (deep mode rounds) — Sonnet + Haiku fallback. 함수명 `_run_gemini_round` + `GeminiRoundError`는 외부 호환 유지
  - `news_bot/orchestrator.py` (gap-fill) — Haiku + Sonnet fallback. JSON 출력 단순
  - `sector_bot/searcher.py` (11개 섹터 검색) — Sonnet + Opus fallback. 섹터별 깊이 요구
- **유지 (Gemini API 잔존, grounding 불필요)**:
  - `news_bot/summarizer.py` — daily/weekly/monthly 요약은 이미 수집된 RSS 처리
  - `sector_bot/analyzer.py` — searcher가 이미 grounding 수행, analyzer는 분석만
- **모델별 환경변수 외부화**: `CLAUDE_SEARCH_MODEL`, `CLAUDE_SEARCH_FALLBACK_MODEL`, `CLAUDE_SEARCH_TIMEOUT`, `CLAUDE_MODEL_SECTOR_SEARCH`, `CLAUDE_MODEL_SECTOR_SEARCH_FALLBACK`
- **테스트**: 5개 갱신 (`test_research_orchestrator` 4개 + `test_news_orchestrator` 1개), safety_blocked 테스트 1개 삭제(Claude는 해당 개념 없음). **72개 전부 pass.**
- **라이브 검증**: Haiku로 grounded 호출 → 36.4s, sources 1개, 정확한 응답("Micron Technology stock surged 19.29% ...") 확인.

---

## 2026-05-27 AM: Gemini `-p` CLI 제거 → API + 모델 fallback chain

- **배경**: Google이 2026-06에 `gemini -p` CLI 종료 예고. 코드 6곳(텔레그램 quick/deep, 뉴스봇 daily/weekly/monthly, 뉴스봇 gap-fill, 섹터봇 search/analyze)이 CLI subprocess를 직간접 호출 중이라 전수 마이그레이션.
- **새 wrapper**: `shared/gemini_cli.py` 완전 재작성. 신규 `call_gemini_with_fallback()` + 기존 `call_gemini_cli`/`is_quota_error`/`extract_urls`/`is_cli_mode_active` backward-compat alias 유지.
- **모델 fallback chain (env-configurable)**:
  - `GEMINI_MODEL` (기본 `gemini-3.1-flash-lite`) → primary
  - `GEMINI_FALLBACK_MODELS` (기본 `gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash`) → 429/503/overloaded 시 좌→우 순서로 fallthrough
  - 모든 단계에서 `google_search` grounding 설정 보존 (검색 필요 호출)
- **갱신 파일**:
  - `shared/gemini_cli.py` (재작성, +305줄)
  - `shared/research_orchestrator.py` (deep mode round 호출 → API)
  - `telegram_gemini_bot.py` (`run_gemini` quick mode → API)
  - `news_bot/summarizer.py` (`_use_cli_fallback` 플래그·`_summarize_via_cli` 메서드 제거, `_summarize()` 단일 경로)
  - `sector_bot/searcher.py` (검색 grounding 호출 wrapper로 일원화, fallback 메서드 제거)
  - `sector_bot/analyzer.py` (분석 호출 wrapper로 일원화)
  - `news_bot/orchestrator.py` (`_gap_fill_via_cli`는 함수명만 보존, 내부적으로 alias 경유로 API 호출)
- **테스트**: 4개 `test_research_orchestrator` 테스트 wrapper monkeypatch로 갱신, `test_shared_gemini_cli` `is_cli_mode_active` 영구 False 검증으로 전환, `test_sector_orchestrator` clamping 제거 검증으로 전환. 신규 2개(safety_blocked, grounding sources append) 추가. **73개 테스트 전부 pass.**
- **연계 작업**: `~/.claude/skills/research/` skill도 동일 패턴으로 마이그레이션 (`scripts/ask_gemini.sh`는 wrapper로 변환, `scripts/ask_gemini.py` 신규, `.venv` + `google-genai` 설치, `~/.zshenv`에 `GEMINI_API_KEY` 영구 export).
- **라이브 검증**: `gemini-3.1-flash-lite → 3.5-flash → 3-flash-preview → 2.5-flash` 순차 fallthrough 실측 확인 (앞 3개 quota 소진 상태에서 마지막 모델로 응답 도달).

---

## 2026-05-18: 봇 다이어그램 출력 Mermaid 전환 (SKILL.md만 변경, 코드 무변경)

- `~/.claude/skills/blogger-html/SKILL.md` 3차 패치 (483줄 → 574줄)
  - 시각화 8번 (의사결정 플로우차트) · 9번 (시스템 도식) → **Mermaid 코드블록 우선**, 인라인 SVG는 fallback으로 강등
  - 노드 수 ≤6, 분기점 ≤2, 한 줄 라벨 ≤12자 강제 (모바일 글자 가독성)
  - RSS·이메일 fallback 의무화: 다이어그램 직후 `📊 다이어그램 요약: …` 1~2문장 자연어 압축. JS 비활성 환경에서도 결론 전달
  - Blogger/Tistory 호환성 체크리스트 신설 (스킨 등록된 Mermaid는 OK 명시, 본문 `<script>` 금지)
- 운영자 직접 작업:
  - Blogger 테마 / Tistory 스킨 `</body>` 위에 Mermaid.js v11 글로벌 등록 (`mermaid.esm.min.mjs`)
  - `<pre><code class="language-mermaid">` 본문 코드블록을 `.mermaid` div로 DOM 치환하는 스킨 스크립트 추가
- 라이브 검증 (buffett_bot --once 4회 발행 in 2026-05-17~18):
  - 5/17 글: Mermaid 코드블록 2개 자동 생성 ✓ (회귀 0건)
  - 5/18 #2 · #3 글: 노드 6·분기 2 룰 정확 작동, RSS fallback 문구 자동 출현 ✓
- 결정 보류: 스킨 스크립트 v2 (fontSize 17px + `useMaxWidth: false` + 모바일 가로 스크롤). 노드 6개 제한만으로 사용자 가독성 만족 → v1 유지
- 효과: 봇 다이어그램 깨짐 해소 (이전 SVG 좌표 수동 계산 → Claude 매번 박스/화살표 어긋남 발생). 코드/봇 재시작 무변경 — SKILL.md는 `shared/claude_html_converter.py`가 *매 호출*마다 새로 로드함
- 상세 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) ("인라인 SVG 플로우차트 화살표가 박스에 안 닿음"), [CONFIGURATION.md](CONFIGURATION.md) ("Mermaid.js 글로벌 등록")

## 2026-05-16: Gemini 모델 preview → GA 전환

- 구글 공식 정책에 따라 `gemini-3.1-flash-lite-preview` (그리고 `.env`에서 임시로 사용 중이던 `gemini-3-flash-preview`) 폐기. GA 버전 `gemini-3.1-flash-lite`로 통일.
- 변경 지점:
  - `001_code/.env` / `.env.example`: `GEMINI_MODEL=gemini-3.1-flash-lite`
  - `001_code/news_bot/config.py:14`, `001_code/news_bot/summarizer.py:32`: default `gemini-3.1-flash-lite`
  - `001_code/sector_bot/config.py:269`: default `gemini-3.1-flash-lite`
  - 문서: `CLAUDE.md`, `docs/CONFIGURATION.md`, `docs/SECTOR_BOT.md`
- 영향: 뉴스봇 요약, 섹터봇 검색 grounding 모두 GA 모델로 전환. 응답 형식·쿼타 영향 없음 (free-tier 동일).

## 2026-05-10: 통합 봇 일요일 스케줄 정정 + Blogger 업로드 idle 재시도

- `investment_bot.py`: Weekly Summary `18:30 → 19:20`, Comprehensive Report `19:00 → 19:40`. 마지막 섹터 11(필수 소비재) `scheduled_time="18:40"`보다 앞서 트리거되던 문제 수정. `weekly_sector_bot.py`/CLAUDE.md 문서와 일치.
- `shared/blogger_uploader.py`: `_insert_with_retry()` 신설. `BrokenPipeError`/`ConnectionResetError`/`SSLError`/`RemoteDisconnected` 등 idle connection drop 발생 시 service 재생성 후 1회 재시도. 종합 보고서(~118KB HTML)처럼 마지막 정상 업로드 이후 30분+ 간격 호출에서 발생하던 broken pipe 자동 복구.
- 사고 기록: 2026-05-10 일요일 런 — Weekly Summary 10/11 (sector 11 미시작), 종합 보고서 broken pipe → 텔레그램 ❌ 도착.
- 상세 → [TROUBLESHOOTING.md](TROUBLESHOOTING.md) ("Sector Weekly Summary가 N-1/N 으로 나감", "Comprehensive Report 업로드 Broken pipe")

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
