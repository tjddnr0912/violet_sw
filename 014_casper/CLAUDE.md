# CLAUDE.md — 미장봇 (US Stock Bot)

**제품명**: 미장봇 (US Stock Bot). 멀티 bucket 자동매매 봇.
**구성 ($3k 기준)**: SPMO 매수보유 50% + GEM (Antonacci Dual Momentum) 30% + **20% 추세 sleeve** 20%. 자본 $5k 도달 시 MTUM/QUAL, $10k 도달 시 Clenow/TQQQ_SMA 자동 활성화.
**20% sleeve 엔진 (`sleeve_engine`)**: 기본 `trend` = 저빈도 **TQQQ Vol-Target 추세** (QQQ>200d SMA 게이트, 노출=min(1, 0.40/실현변동성), 월 1회 리밸런스, 나머지 BIL). `intraday` = 레거시 ORB+FVG 데이트레이딩(보존됨, 비활성). 근거: [docs/strategy/STRATEGY_ZOO_1000USD.md](docs/strategy/STRATEGY_ZOO_1000USD.md) — 0.25%/side에서 고빈도 일일매매는 구조적 적자, 저빈도 추세만 엣지 보존.
**전략 카테고리 명칭**: ‘Casper’ = Jesse Rogers SMC 기반 ORB+FVG 데이트레이딩 전략 이름. **봇 제품명이 아니라 한 전략의 카테고리명으로만 사용된다.** 클래스명·logger·파일명·script 이름에는 호환성을 위해 `casper` 식별자가 남아 있다.
**Casper 전략 R:R**: Scenario B — AM_MACRO=1:3 / AM_LATE=1:2.

## 실행

```bash
./run_casper.sh start --yes   # 포그라운드, 확인 없이 시작
./run_casper.sh daemon --yes  # 백그라운드 데몬
./run_casper.sh stop          # 종료 (graceful)
./run_casper.sh status        # 누적 매매 통계
./run_casper.sh test          # 유닛 테스트
```

전체 옵션·시그널·워크플로 → [docs/COMMANDS.md](docs/COMMANDS.md).

## 핵심 정보

| 항목 | 값 |
|------|-----|
| 전략 (기본) | **`sleeve_engine=trend`**: TQQQ Vol-Target 추세 (QQQ>200d SMA, 노출=min(1, 0.40/실현변동성), 월 1회). 인트라데이 스캔 없음 — 데일리 멀티버킷 틱에서 처리 |
| 전략 (레거시) | **`sleeve_engine=intraday`**: ORB(15분) + FVG + Pullback. 아래 R:R·매매시간 행은 이 모드에만 적용 |
| 종목 | trend: TQQQ/BIL (QQQ 200d 기준) · intraday: TQQQ (강세) / SQQQ (약세), QQQ MA20 기준 |
| R:R | **Scenario B**: AM_MACRO breakout = 1:3, AM_LATE breakout = 1:2. **Partial TP 활성**: 1.5R에서 50% 청산 + SL→ORB.high (free trade) + 잔여 50%는 TP2 또는 SL=ORB.high |
| 매매시간 | 09:45~10:55 ET (스캔, AM_MACRO+AM_LATE), 15:50 강제청산 |
| 필터 | VIX(12~30), ORB 폭, 서킷브레이커(3연패/주간3%손실), 공휴일 |
| 안전장치 | 크래시 복구, SIGTERM, 포지션 상한, 오버나잇 방지, 잔고 동기화, 부분체결 감지 |
| 알림 | 텔레그램 (env-driven, 큐 기반 critical 지연 재전송, 네트워크 에러 silent drop) |
| 테스트모드 | `TEST_MODE=on` → live지만 1주 고정 |

## 상태머신 (요약)

```
WAITING → PRE_MARKET → ORB_FORMING → SCANNING → POSITION_OPEN → DONE_TODAY
```

상세 다이어그램·각 상태 동작·데이터 흐름 → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## 주요 모듈

| 파일 | 역할 |
|------|------|
| `src/bot.py` | 상태머신 + 메인 루프 |
| `src/core/orb.py` | ORB 계산 |
| `src/core/fvg.py` | FVG 감지 |
| `src/core/strategy.py` | 시그널 엔진 |
| `src/core/position.py` | 포지션 관리 (SL/TP/BE) |
| `src/core/risk.py` | VIX 필터, 트렌드, 서킷브레이커 |
| `src/api/kis_order.py` | KIS 주문 실행 |
| `src/api/kis_client.py` | KIS 시세·잔고·체결내역 |
| `src/api/kis_auth.py` | OAuth + exponential backoff |
| `src/data/market_data.py` | KIS 우선 → yfinance 폴백 |
| `src/telegram/notifier.py` | 텔레그램 알림 (큐+필터, send-only) |

## 환경변수 (요약)

```
KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO   # KIS 인증 (필수)
TRADING_MODE=live | paper                      # 거래 모드
TEST_MODE=on | off                             # 1주 고정 검증 모드
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID          # 008과 동일 (모든 프로젝트 통합)
```

각 변수의 범위·기본값·시크릿 마스킹 정책 → [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## 트러블슈팅 핵심

KIS 토큰 lockout (EGW00103) / cold-start HTTP 500 / .env IFS trailing-byte / 잔고 API 분기 / 포지션 사이징 vs limit price mismatch / 매도 fill buffer / orphan 포지션 / 더블 매도 / 테스트 prod 데이터 누수 — 각 항목은 6필드 + Claude 진단 미스 기록 구조로 → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

**가장 흔한 함정 1줄 가이드**:
- `EGW00103` 보면 → 키 의심 X, **토큰 retry 빈도 의심 O**
- KIS HTTP 500 + 빈 body → 서버 장애 X, **secret 길이 비교 O** (`echo "SEC_LEN=${#KIS_APP_SECRET}"`)
- **신규 고빈도 sleeve 추가 금지** → 0.25%/side에서 일일 매매는 비용=최종자산의 25~260%로 구조적 적자(증거: [docs/strategy/STRATEGY_ZOO_1000USD.md](docs/strategy/STRATEGY_ZOO_1000USD.md)). `sleeve_engine=trend`(저빈도) 기본, `intraday`(구 Casper)는 보존됐으나 비활성
- **수수료 인하가 진짜 레버** → `commission.rate_per_side` 0.25%. KIS 우대 0.07~0.09% 적용 시 고빈도 net 약 2배, 저빈도 trend sleeve엔 영향 미미

## 상세 문서

| 주제 | 파일 |
|------|------|
| 아키텍처·상태머신·텔레그램 컴포넌트 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 명령 카탈로그 | [docs/COMMANDS.md](docs/COMMANDS.md) |
| 트러블슈팅 + Claude 진단 미스 기록 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 환경변수·튜닝 분석 (R:R 1:3, commission 0.25%) | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| 변경 이력 | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| 검증 체크리스트 (16항목, function/scenario/system 3계층) | [docs/CHECKLIST.md](docs/CHECKLIST.md) |
| **$1000 최고수익 30+매매법 백테스트 (비용-빈도 법칙)** | [docs/strategy/STRATEGY_ZOO_1000USD.md](docs/strategy/STRATEGY_ZOO_1000USD.md) |
| **저빈도 trend sleeve 설계 스펙** | [docs/superpowers/specs/2026-05-30-casper-lowfreq-trend-design.md](docs/superpowers/specs/2026-05-30-casper-lowfreq-trend-design.md) |
| **저빈도 trend sleeve 구현 계획** | [docs/superpowers/plans/2026-05-30-casper-lowfreq-trend.md](docs/superpowers/plans/2026-05-30-casper-lowfreq-trend.md) |
| Casper 신호 ablation (느슨↔AND↔필터별 빈도·승률·수익) | scripts/casper_ablation_backtest.py |
| **Casper SMC 원본 출처 분석 + 봇 매핑** | [docs/strategy/CASPER_SMC_SOURCE_REPORT.md](docs/strategy/CASPER_SMC_SOURCE_REPORT.md) |
| **업그레이드 후보 검토 (Partial TP / 5m ORB / Phase 5)** | [docs/strategy/UPGRADE_REVIEW.md](docs/strategy/UPGRADE_REVIEW.md) |
| Phase 5.0 Range Expansion 데이터 분석 (보류 결정) | [docs/strategy/PHASE5_DATA_ANALYSIS.md](docs/strategy/PHASE5_DATA_ANALYSIS.md) |
| 보류 후보 백로그 (5m ORB 등) | [docs/strategy/BACKLOG.md](docs/strategy/BACKLOG.md) |
| 코드 리뷰 (보존) | [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md) |
| 코드 감사 2026-04-11 (보존) | [docs/CODE_AUDIT_2026-04-11.md](docs/CODE_AUDIT_2026-04-11.md) |
| 프로젝트 구조 (보존) | [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) |
| Gemini 리뷰 (보존) | [docs/gemini_review.md](docs/gemini_review.md) |
| **알고리즘 흐름 해설 (차트로 따라가기)** | **[docs/strategy/ALGORITHM_WALKTHROUGH.md](docs/strategy/ALGORITHM_WALKTHROUGH.md)** |
| 전략 리뷰 | [docs/strategy/STRATEGY_REVIEW.md](docs/strategy/STRATEGY_REVIEW.md) |
| 실행 계획 | [docs/strategy/EXECUTION_PLAN.md](docs/strategy/EXECUTION_PLAN.md) |
| Freqtrade 갭 리뷰 | [docs/strategy/FREQTRADE_GAP_REVIEW.md](docs/strategy/FREQTRADE_GAP_REVIEW.md) |
| 인트라데이 전략 비교 (KIS 비용 백테스트) | [docs/strategy/INTRADAY_COMPARISON.md](docs/strategy/INTRADAY_COMPARISON.md) |
| ICT 통합 가이드 | [docs/strategy/ICT_STRATEGY_INTEGRATION.md](docs/strategy/ICT_STRATEGY_INTEGRATION.md) |
| ICT Phase 1 사전 검증 (11건 실거래) | [docs/strategy/PHASE1_PRECHECK.md](docs/strategy/PHASE1_PRECHECK.md) |
| ICT Phase 2 (Sweep+CHoCH) 구현 | [docs/strategy/PHASE2_IMPLEMENTATION.md](docs/strategy/PHASE2_IMPLEMENTATION.md) |
| ICT Phase 3 (Bearish FVG + Daily Bias) | [docs/strategy/PHASE3_IMPLEMENTATION.md](docs/strategy/PHASE3_IMPLEMENTATION.md) |
| ICT Phase 3 — QQQ→SQQQ 매핑 | [docs/strategy/PHASE3_QQQ_MAPPING.md](docs/strategy/PHASE3_QQQ_MAPPING.md) |
| ICT Phase 4 — OTE/Breaker/NQ + Multi-TF + Daily Store | [docs/strategy/PHASE4_IMPLEMENTATION.md](docs/strategy/PHASE4_IMPLEMENTATION.md) |
| ICT 통합 후 백테스트 비교 | [docs/strategy/BACKTEST_AFTER_ICT.md](docs/strategy/BACKTEST_AFTER_ICT.md) |
| 데이터 수집 plan | [docs/strategy/DATA_COLLECTOR_PLAN.md](docs/strategy/DATA_COLLECTOR_PLAN.md) |
