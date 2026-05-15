# Casper 명령 카탈로그

`run_casper.sh`는 봇 lifecycle 관리 entry point. 모든 서브커맨드는 `.env` 자동 로드 + Python venv activation 후 실행.

## 서브커맨드

| 명령 | 동작 | 부작용 |
|------|------|------|
| `./run_casper.sh start` | 포그라운드 실행 (live 모드 시 확인 프롬프트) | 라이브 거래 시작 |
| `./run_casper.sh start --yes` | 포그라운드, 확인 없이 시작 | 라이브 거래 시작 (CI/cmux용) |
| `./run_casper.sh daemon --yes` | 백그라운드 데몬, nohup + PID 파일 | 라이브 거래 시작, 종료까지 지속 |
| `./run_casper.sh stop` | PID 파일로 SIGTERM | 진행 중 거래 finalize 후 종료 |
| `./run_casper.sh status` | 누적 매매 통계 출력 | 읽기 전용 |
| `./run_casper.sh test` | 유닛 테스트 (270+개) | 읽기 전용 (격리 fixture autouse) |

## 옵션 영향

### `--yes`

- **목적**: live 모드 시작 시 사용자 확인 프롬프트 스킵
- **사용 시점**: cmux running_machine 자동 기동, CI 통합 테스트
- **주의**: paper 모드에서는 효과 없음 (애초에 프롬프트 없음)

## 환경변수 영향

| 환경변수 | 영향 |
|---------|------|
| `TRADING_MODE=paper` | 시뮬레이션, 주문 mock |
| `TRADING_MODE=live` | 실제 KIS 주문 실행 (확인 프롬프트 동반) |
| `TEST_MODE=on` | live지만 1주 고정 (실거래 최소화 검증용) |
| `TEST_MODE=off` | 정상 사이징 (capital 기반) |

상세는 [CONFIGURATION.md](CONFIGURATION.md).

## 시그널 처리

| 시그널 | 동작 |
|--------|------|
| `SIGTERM` (kill) | graceful shutdown — 진행 중 거래 finalize, state 저장, exit |
| `SIGINT` (Ctrl+C) | 동일 |
| `SIGKILL` | 즉시 종료 — `position_state.json`이 마지막 저장 시점에 머물 수 있음 (재기동 시 reconcile 필요) |

## 보조 스크립트

| 스크립트 | 용도 |
|---------|------|
| `scripts/test_telegram_messages.py` | 텔레그램 알림 14단계 스모크 테스트 |
| `scripts/backtest_compare_dual_scan.py` | 백테스트 비교 (commission/RR 토글, env var `BT_BUY_RATE`/`BT_SELL_RATE`/`BT_RR_RATIO`) |

## 일반 워크플로

### 일일 시작

```bash
./run_casper.sh daemon --yes
```

cmux의 `start_all_bots_cmux.sh`가 자동으로 실행. 단독 사용 시 nohup 적용됨.

### 진행 상황 확인

```bash
./run_casper.sh status            # 누적 통계
tail -f logs/app/casper_$(date +%F).log   # 실시간 로그
```

### 종료

```bash
./run_casper.sh stop
```

진행 중 거래가 있으면 finalize 후 종료. 강제 종료가 필요하면 `kill -9 $(cat data/casper.pid)` 후 다음 기동에서 reconcile.

### 테스트

```bash
./run_casper.sh test                              # 전체
./run_casper.sh test tests/core/test_strategy.py  # 특정 파일 (pytest 인자 패스스루)
```

## cmux 통합

- cmux running_machine 워크스페이스의 `미장봇` surface에서 `daemon --yes` 자동 실행
- 재시작: `/restart` 스킬 또는 사용자가 `./start_all_bots_cmux.sh` 호출
