# CLAUDE.md - Bithumb Trading Bot

빗썸 거래소 자동매매 봇. 포트폴리오 멀티코인 전략 (Ver3).

## 실행

```bash
./scripts/run_v3_watchdog.sh   # 권장 (자동 재시작 + hang 감지)
./scripts/run_v3_cli.sh        # 단순 CLI
./scripts/run_v3_gui.sh        # GUI
```

## 핵심 정보

| 항목 | 값 |
|------|-----|
| 거래소 | Bithumb |
| 언어 | Python 3.13+ |
| 전략 | Portfolio Multi-Coin (Ver3) |
| 분석 주기 | 60초 (풀) + 15초 (경량 체크) |
| 최대 포지션 | 2 |
| 코인 | BTC, ETH, XRP |

## 주요 컴포넌트 (ver3/)

| 파일 | 역할 |
|------|------|
| `trading_bot_v3.py` | 메인 봇 오케스트레이터 |
| `strategy_v3.py` | 매매 전략 (진입/청산) |
| `portfolio_manager_v3.py` | 멀티코인 포트폴리오 관리 |
| `live_executor_v3.py` | 실제 주문 실행 |
| `regime_detector.py` | 매크로(6단계)+마이크로(3단계) 레짐 분류 |
| `dynamic_factor_manager.py` | 동적 파라미터 + 적응형 가중치 관리 |

## 텔레그램 명령어

`/status`, `/positions`, `/factors`, `/performance`, `/close <COIN>`, `/stop`, `/reboot`

## 환경변수 (.env)

```bash
BITHUMB_API_KEY=
BITHUMB_SECRET_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

## 코드 수정 시 주의

1. **ver3 전용**: 프로덕션은 ver3만 사용 (ver1/ver2 삭제됨)
2. **lib/ 수정 시**: ver3 호환성 테스트 필요
3. **전략 수정 시**: `strategy_v3.py`와 `config_v3.py` 동시 수정

## 트러블슈팅 핵심

Telegram 메시지 escape / Conflict 409 / Bithumb API hang / 연속 timeout lockup — 각 항목은 6필드 + Claude 진단 미스 기록 → [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## 상세 문서

| 주제 | 파일 |
|------|------|
| 아키텍처·레짐·전략·설정값 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 명령 카탈로그 (스크립트·텔레그램·디버깅) | [docs/COMMANDS.md](docs/COMMANDS.md) |
| 트러블슈팅 + Claude 진단 미스 기록 | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| 환경변수·파라미터·시크릿 마스킹 | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| 변경 이력 | [docs/CHANGELOG.md](docs/CHANGELOG.md) |
