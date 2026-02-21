# CLAUDE.md - 퀀트 자동매매 시스템

KIS Open API 기반 한국 주식 멀티팩터 퀀트 자동매매.

## 실행

```bash
./run_quant.sh daemon          # 통합 데몬 (권장)
./run_quant.sh screen          # 스크리닝만
./run_quant.sh backtest        # 백테스트
```

## 핵심 정보

| 항목 | 값 |
|------|-----|
| 전략 | 모멘텀(20%) + 단기모멘텀(10%) + 저변동성(50%) |
| 유니버스 | KOSPI200 |
| 목표 종목 | 15개 |
| 손절/익절 | -7% / +10% |

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

## 상세 문서

- [아키텍처](docs/ARCHITECTURE.md) - 프로젝트 구조, 개발 가이드, 유틸리티 사용법
- [트러블슈팅](docs/TROUBLESHOOTING.md) - API Rate Limit, Telegram 에러, pykrx, 리밸런싱 버그
- [변경 이력](docs/CHANGELOG.md) - 2026-01~02 변경사항 전체
- [KIS API 정보](docs/get_api_information.md) - KIS Open API 레퍼런스
- [멀티팩터 전략](docs/strategy/multi_factor_strategy.md) - 팩터 설계 상세
- [퀀트 트레이딩 가이드](docs/strategy/quant_trading_guide.md) - 전략 운영 가이드
