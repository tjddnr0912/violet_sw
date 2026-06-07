# Weekly Sector Bot

매주 일요일 11개 섹터별 투자정보를 자동 수집/분석하여 OgusInvest 블로그에 업로드.

## 실행

```bash
python weekly_sector_bot.py           # 스케줄 모드 (일요일 자동)
python weekly_sector_bot.py --once    # 즉시 전체 실행
python weekly_sector_bot.py --resume  # 중단 후 재개
python weekly_sector_bot.py --sector 1  # 특정 섹터만 (1-11)
python weekly_sector_bot.py --test    # 테스트 (업로드 스킵)
python weekly_sector_bot.py --comprehensive  # 종합 투자 평가 보고서
python weekly_sector_bot.py --status  # 상태 확인
python weekly_sector_bot.py --reset   # 상태 초기화
```

## 11개 섹터

| ID | 섹터 | 영문명 | 시간 |
|----|------|--------|------|
| 1 | AI/양자컴퓨터 | ai_quantum | 12:00 |
| 2 | 금융 | finance | 12:40 |
| 3 | 조선/항공/우주 | shipbuilding_aerospace | 13:20 |
| 4 | 에너지 | energy | 14:00 |
| 5 | 바이오 | bio | 14:40 |
| 6 | IT/통신/Cloud/DC | it_cloud | 15:20 |
| 7 | 주식시장 | stock_market | 16:00 |
| 8 | 반도체 | semiconductor | 16:40 |
| 9 | 자동차/배터리/로봇 | auto_battery_robot | 17:20 |
| 10 | 리츠(REITs) | reits | 18:00 |
| 11 | 필수 소비재 | consumer_staples | 18:40 |

## 섹터별 분석 초점

| ID | 분석 초점 |
|----|-----------|
| 1 | AI 기술발표/벤치마크, MCP/Skills 에이전트, 양자컴퓨팅, AI 반도체 |
| 2 | 기준금리/통화정책, 월가 전망, CPI/인플레이션, 고용지표, 귀금속 |
| 3 | 조선 수주, Boeing/Airbus, SpaceX/위성, 방산 수출 |
| 4 | 신재생에너지, 원유 WTI/Brent, 천연가스, 원자력/SMR, ESS |
| 5 | FDA 승인, 임상시험, 유전자치료/CRISPR, 바이오텍 M&A/IPO |
| 6 | AWS/Azure/GCP, 데이터센터, 5G/통신, 사이버보안, SaaS |
| 7 | S&P500/Nasdaq 전망, 지정학 리스크, 무역분쟁, VIX |
| 8 | 파운드리 (TSMC, 삼성), 장비 (ASML), Fabless (NVIDIA, AMD), 메모리 |
| 9 | EV (Tesla, BYD), 배터리 (LG, 삼성SDI, CATL), 자율주행, 휴머노이드 |
| 10 | 리츠 ETF 수급, FTSE NAREIT, 배당/자산매매, 경기 사이클 |
| 11 | 종목/ETF 추천 (P&G, Coca-Cola, XLP), 경기 사이클, 주가 전망 |

## 파일 저장 구조

```
004_Sector_Weekly/YYYYMMDD/
├── sector_01_ai_quantum.md
├── sector_02_finance.md
├── ...
├── sector_11_consumer_staples.md
└── comprehensive_report.md       # 종합 투자 평가 보고서 (19:40)
```

## 종합 투자 평가 보고서

- **스케줄**: 일요일 19:40 (11개 섹터 완료 후)
- **입력**: 당일 생성된 11개 섹터 MD 파일 전체 취합
- **분석 엔진**: Claude CLI (`claude -p`) — 월스트리트 30년+ 마스터 애널리스트 역할
- **HTML 변환**: 장문 보고서는 h2 기준 청크 분할 후 개별 변환·합침
- **라벨**: `[종합분석, 주간, 투자정보]`
- **최소 섹터**: 8개 이상 존재해야 보고서 생성 (미달 시 스킵)

## 블로그 업로드

- **블로그**: OgusInvest (Blog ID: `9115231004981625966`)
- **제목**: `{날짜} {N}주차 {섹터명} 투자정보`
- **라벨**: `[섹터명, 주간, 투자정보]`

## State Management

- **상태 파일**: `sector_bot/state.json`
- **주차 키**: YYYY-WW 형식 (같은 주 내에서만 재개 가능)
- **저장 정보**: 완료 섹터, 실패 섹터, 블로그 URL

## 분석 프롬프트 (PTCC 프레임워크)

`analyzer.py`의 각 섹터 프롬프트는 6개 섹션으로 구성:

| 섹션 | 위치 | 내용 |
|------|------|------|
| **Persona** | `SECTOR_PROMPTS[id]` (섹터별) | 전문가 역할 + 필수 분석 항목 + 형식 특수사항 |
| **Task** | `_build_analysis_prompt()` (공용) | 해석/판단/행동 3관점 분석 |
| **Context** | 공용 | 데이터 소스, 독자, 발행 채널 |
| **Blogger Style** | 공용 | 이모지, 짧은 문단, 표, Hook, h1 미사용 |
| **SEO** | 공용 | 키워드 전략, Heading 계층, snippet 최적화 |
| **Constraints** | 공용 | 언어/분량/객관성/정직성/AI 언급 금지 등 9항목 |

## 오케스트레이터 (5차원 검증)

`sector_bot/orchestrator.py`가 검색 → 5차원 게이트 → 1회 갭필 → 분석을 시퀀싱한다. 기존 `searcher`/`analyzer`는 변경 없이 재사용.

### 5차원 체크리스트

| 차원 | 통과 기준 (정량 1차) | Claude 2차 |
|------|------------------|----------|
| 정의 | 동인 키워드 ≥2 또는 head bullet ≥2 | 항상 실행 (Q4=a) |
| 현황 | (수치, 날짜) 페어 ≥3 | ↑ |
| 근거 | Tier 1 도메인 출처 ≥2 (Bloomberg/Reuters/FT/WSJ/SEC/CNBC/MarketWatch) | ↑ |
| 반론 | 강세/약세 어휘 양쪽 출현 | ↑ |
| 적용 | 액션 동사 + 티커 패턴 | ↑ (갭필 없음 — analyzer 책임) |

OR-semantics: 한 차원이 정량 OR Claude 중 하나라도 통과하면 그 차원은 통과 처리. Claude는 정량의 false-negative만 구제 가능 (정량 통과를 거부하지는 못함).

### 라운드 예산

- 정상: 2 라운드 (검색 + 갭필 1회)
- `--deep`: 3 라운드
- CLI fallback 활성: 강제 1 라운드 (갭필 스킵)
- 섹터당 hard cap: 8분 — 초과 시 갭필 중단하고 분석으로 진행 (분석 자체는 중단되지 않음)

### 갭필 카운터 분리

- `gap_fills_attempted`: 루프 종료 조건 (실패한 갭필도 카운트해서 무한 루프 방지)
- `rounds_completed`: 콘텐츠 생산에 성공한 라운드만 카운트 (caller에 보고)

### 모순 명시

분석 결과에 `## 📌 자료 간 차이` 섹션이 있으면 orchestrator가 bullet 항목을 파싱하여 `OrchestrationResult.contradictions`에 적재. 종합 보고서는 `## 📌 섹터 간 시각 차이` 변형 사용.

## 종합 보고서 게이트

`comprehensive_report.generate_report`도 동일한 5차원 게이트 적용 (변형판: "현황"=8 섹터 이상 인용, "적용"=3 포트폴리오 비중 100%). 미달 시 1회 재합성.

게이트 결과는 반환 dict의 `gate_results`(차원별 bool) + `failed_dimensions`(실패한 차원명 리스트) 필드로 노출.

## 설정 (sector_bot/config.py)

| Setting | Value | Description |
|---------|-------|-------------|
| `GEMINI_MODEL` | gemini-3.5-flash | 분석 primary 모델 (env `SECTOR_GEMINI_MODEL`, 2026-06-07 flash-lite→3.5-flash 승격) |
| `MAX_RETRIES` | 3 | API 호출 최대 재시도 |
| `RETRY_DELAY` | 60초 | 재시도 대기 (지수 백오프) |
| `CLAUDE_TIMEOUT` | 900초 (15분) | Claude CLI 타임아웃 |
| `SCHEDULE_DAY` | 6 (Sunday) | 스케줄 실행 요일 |

## 에러 처리

| 에러 | 처리 |
|------|------|
| Gemini API 429 할당량 초과 | wrapper가 섹터 fallback chain으로 자동 전환 (3.5-flash → 3.1-flash-lite → 3-flash-preview → 2.5-flash) |
| Gemini Search 실패 (503 등) | 동일하게 chain 내 다음 모델로 fallthrough. 모든 모델 소진 시 `MAX_RETRIES` 지수 백오프 재시도 (60초→120초→240초) |
| Gemini Safety Filter | BLOCK_NONE 설정으로 비활성화. SAFETY 차단 시 fallback chain 단축(verdict는 모델 무관) |
| Claude CLI 타임아웃 | 15분 후 마크다운 폴백 |
| 네트워크 에러 | 지수 백오프 재시도 |

### Gemini Model Fallback Chain (`shared/gemini_cli.py`)

옛 `gemini -p` CLI fallback은 2026-06 CLI 종료 대응으로 **2026-05 제거**됨. 현재는 in-process 모델 chain 사용:

1. **Primary**: `GEMINI_MODEL` 환경변수 (기본 `gemini-3.1-flash-lite`). **단 섹터 분석은 별도 `SECTOR_GEMINI_MODEL`=`gemini-3.5-flash`(2026-06-07)**
2. **Fallbacks**: `GEMINI_FALLBACK_MODELS` (기본 `gemini-3.5-flash,gemini-3-flash-preview,gemini-2.5-flash`). **섹터 분석은 격리된 `SECTOR_GEMINI_FALLBACK_MODELS`(기본 flash-lite 우선)** 사용
3. **트리거**: 429 `RESOURCE_EXHAUSTED`, 503 `UNAVAILABLE`, `overloaded` 메시지 → 다음 모델로 fallthrough
4. **Grounding**: chain의 모든 단계가 동일한 `google_search` Tool 설정을 유지 (검색이 필요한 호출의 경우)

- `searcher.py`(grounding 필요), `analyzer.py`(grounding 불필요) 모두 wrapper의 `call_gemini_with_fallback()`을 사용 — 별도 CLI 경로 없음
- `_use_cli_fallback` 속성은 backward-compat 위해 False로 박제, `is_cli_mode_active()`는 no-op 항상 False
