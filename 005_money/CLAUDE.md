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
| 분석 주기 | 15분 |
| 최대 포지션 | 2 |
| 코인 | BTC, ETH, XRP |

## 주요 컴포넌트 (ver3/)

| 파일 | 역할 |
|------|------|
| `trading_bot_v3.py` | 메인 봇 오케스트레이터 |
| `strategy_v3.py` | 매매 전략 (진입/청산) |
| `portfolio_manager_v3.py` | 멀티코인 포트폴리오 관리 |
| `live_executor_v3.py` | 실제 주문 실행 |
| `regime_detector.py` | 6단계 시장 레짐 분류 |
| `dynamic_factor_manager.py` | 동적 파라미터 관리 |

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

## 상세 문서

- [아키텍처](docs/ARCHITECTURE.md) - 디렉토리 구조, 레짐 분류, 진입/청산 전략, 설정값
- [트러블슈팅](docs/TROUBLESHOOTING.md) - Hang 방지 시스템, Timeout 레이어, 에러 대응
- [변경 이력](docs/CHANGELOG.md) - 수익성 개선 내역 (2026-01)
