# CLAUDE.md - Casper Trading Bot

TQQQ/SQQQ Long-Only 자동매매 봇. ORB + FVG + Pullback 전략, R:R 1:3.

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
| 전략 | ORB(15분) + FVG + Pullback |
| 종목 | TQQQ (강세) / SQQQ (약세), QQQ MA20 기준 |
| R:R | 1:3 고정 (commission 0.25% 환경 최적) |
| 매매시간 | 09:45~10:55 ET (스캔), 15:50 강제청산 |
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

## 상세 문서

| 주제 | 파일 |
|------|------|
| 아키텍처·상태머신·텔레그램 컴포넌트 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 명령 카탈로그 | [docs/COMMANDS.md](docs/COMMANDS.md) |
| 트러블슈팅 + Claude 진단 미스 기록 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 환경변수·튜닝 분석 (R:R 1:3, commission 0.25%) | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| 변경 이력 | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| 코드 리뷰 (보존) | [docs/CODE_REVIEW.md](docs/CODE_REVIEW.md) |
| 코드 감사 2026-04-11 (보존) | [docs/CODE_AUDIT_2026-04-11.md](docs/CODE_AUDIT_2026-04-11.md) |
| 프로젝트 구조 (보존) | [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) |
| Gemini 리뷰 (보존) | [docs/gemini_review.md](docs/gemini_review.md) |
| 전략 리뷰 | [docs/strategy/STRATEGY_REVIEW.md](docs/strategy/STRATEGY_REVIEW.md) |
| 실행 계획 | [docs/strategy/EXECUTION_PLAN.md](docs/strategy/EXECUTION_PLAN.md) |
| Freqtrade 갭 리뷰 | [docs/strategy/FREQTRADE_GAP_REVIEW.md](docs/strategy/FREQTRADE_GAP_REVIEW.md) |
