be brief

# CLAUDE.md - 퀀트 자동매매 시스템

KIS Open API 기반 한국 주식 멀티팩터 퀀트 자동매매.

## 실행

```bash
./run_quant.sh daemon          # 통합 데몬 (권장)
./run_quant.sh watchdog        # 데몬 수명 감시 (별도 surface, P1 재발 방지)
./run_quant.sh screen          # 스크리닝만
./run_quant.sh backtest        # 백테스트
```

상위 `start_all_bots*.sh`는 그대로 두고, watchdog가 필요하면 별도 surface에서 `./run_quant.sh watchdog`만 호출하면 됨.

## 핵심 정보

| 항목 | 값 |
|------|-----|
| 전략 | 4팩터 Percentile Ranking (V 34% + M 26% + Q 26% + Vol 15%) |
| 유니버스 | KOSPI200 |
| 목표 종목 | 15개 (Score-Weighted 비중, Buffer Rule 25위까지 유지) |
| 손절 | 변동성 기반 동적 3~15% (ATR 2σ) |
| 익절 | 손익비 3.5:1 / 6.0:1 (20%/30% 부분 익절) |
| 리스크 | 변동성 타겟팅 15%, 시장 레짐 감지 (Bull/Neutral/Bear) |

## 주요 모듈

| 파일 | 역할 |
|------|------|
| `src/quant_engine.py` | 자동매매 엔진 오케스트레이션 (~980줄) |
| `src/quant_modules/` | 상태관리, 주문실행, 포지션모니터, 스케줄, 리포트, 트래커 |
| `src/telegram/bot.py` | 텔레그램 봇 (~330줄), `commands/`에 Mixin 분리 |
| `src/api/kis_client.py` | KIS API 클라이언트 |
| `src/utils/` | balance_helpers, retry, market_calendar, error_formatter |

## 텔레그램 명령어

| 카테고리 | 명령어 |
|----------|--------|
| 제어 | `/start_trading`, `/stop_trading`, `/emergency_stop`, `/run_screening`, `/run_rebalance`, `/reconcile` |
| 조회 | `/status`, `/positions`, `/orders [N]`, `/history [N]`, `/trades [N]`, `/capital` |
| 설정 | `/set_target N`, `/set_dryrun on\|off` |

## 일일 스케줄

| 시간 | 동작 |
|------|------|
| 08:30 | 장 전 스크리닝 |
| 09:00 | 주문 실행 |
| 5분마다 | 포지션 모니터링 |
| 15:20 | 일일 리포트 + 스냅샷 저장 |
| 토요일 10:00 | 주간 장부 점검 |

## 환경변수 (.env)

```bash
KIS_APP_KEY=
KIS_APP_SECRET=
KIS_ACCOUNT_NO=12345678-01
TRADING_MODE=VIRTUAL
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## 코드 수정 시 주의

- 텔레그램 명령어 추가: `src/telegram/commands/` Mixin 파일에 추가 → `bot.py`에 핸들러 등록
- 총자산 계산: `nass_amt`(순자산) 사용 (T+2 결제 대응)
- 설정 파일: `config/system_config.json`은 Telegram 명령으로 변경됨
- 팩터 가중치: `config/optimal_weights.json`의 `factor_weights`가 Single Source of Truth

## 트레이딩 룰 가드 (P2)

매수 주문 직전 두 가드가 발화: **재진입 쿨다운**(20영업일 손절 종목 차단, 5% 추가 하락 시 해제) / **섹터 한도**(동일 섹터 3개 초과 차단). 위치: `order_executor.py:30~35` 상수, `:141`/`:150` 가드. 사고 컨텍스트: 2026-04 반복 손절, 2026-03-09 금융주 4종 동시 손절.

## 재발 방지 인프라 (P1)

월 첫 영업일 리밸런싱 누락 감지(`schedule_handler._check_missed_rebalance`, 15:20 일일 리포트 후 텔레그램 경고) / 데몬 다운·hang 자동 재시작(`scripts/run_quant_watchdog.sh`, 별도 surface). 사고 컨텍스트: 2026-05-01 5월 사일런트 실패.

## 트러블슈팅 핵심

API Rate Limit (EGW00201) / pykrx 호환성 / Telegram 409·ConnectError / T+2 결제 nass_amt / 긴급 리밸런싱 무한 반복 / 휴장일 오판단 / engine_state ↔ KIS 동기화 / 반복 손절 루프 / 단일 섹터 동시 손절 / 월 첫 영업일 사일런트 실패 / 데몬 hang 미감지 — 각 항목은 6필드 + Claude 진단 미스 기록 → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## 상세 문서

| 주제 | 파일 |
|------|------|
| 아키텍처·프로젝트 구조·유틸리티 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 명령 카탈로그 (스크립트·텔레그램·디버깅) | [docs/COMMANDS.md](docs/COMMANDS.md) |
| 트러블슈팅 + Claude 진단 미스 기록 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 환경변수·팩터 가중치·rate limit | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| 변경 이력 | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
| KIS API 레퍼런스 (보존) | [docs/get_api_information.md](docs/get_api_information.md) |
| 멀티팩터 전략 (보존) | [docs/strategy/multi_factor_strategy.md](docs/strategy/multi_factor_strategy.md) |
| 퀀트 트레이딩 가이드 (보존) | [docs/strategy/quant_trading_guide.md](docs/strategy/quant_trading_guide.md) |
