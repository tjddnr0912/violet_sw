# 007_stock_trade 명령 카탈로그

## 실행 스크립트

| 명령 | 동작 |
|------|------|
| `./run_quant.sh daemon` | 통합 데몬 (스케줄러 + 텔레그램 봇) — **권장** |
| `./run_quant.sh screen` | 스크리닝만 1회 실행 (유니버스 + 팩터 점수) |
| `./run_quant.sh backtest` | 백테스트 |
| `./run_quant.sh stop` | daemon 종료 (PID 기반) |

## 텔레그램 명령어

### 제어

| 명령 | 동작 |
|------|------|
| `/start_trading` | 거래 시작 (STOPPED → RUNNING) |
| `/stop_trading` | 거래 종료 (RUNNING → STOPPED) |
| `/emergency_stop` | 긴급 정지 (모든 상태 → EMERGENCY_STOP) |
| `/clear_emergency` | 긴급 정지 해제 (EMERGENCY_STOP → STOPPED) |
| `/run_screening` | 즉시 스크리닝 |
| `/run_rebalance` | 즉시 리밸런싱 |
| `/reconcile` | engine_state ↔ KIS 포지션 강제 동기화 |
| `/sync_positions` | `/reconcile`과 동일 |
| `/pause` | 일시 정지 (RUNNING → PAUSED) |
| `/resume` | 재개 (PAUSED → RUNNING) |

### 조회

| 명령 | 동작 |
|------|------|
| `/status` | 봇 상태 (state, uptime, 마지막 분석/리밸런싱 시각) |
| `/positions` | 보유 종목 + P&L |
| `/orders [N]` | 최근 N건 주문 (default 10) |
| `/history [N]` | 최근 N일 거래 이력 |
| `/trades [N]` | 최근 N건 거래 상세 |
| `/capital` | 총자산·예수금·주식평가금 (T+2 반영, `nass_amt` 사용) |
| `/balance` | `/capital`과 동일 |

### 설정

| 명령 | 동작 |
|------|------|
| `/set_target N` | 목표 종목 수 변경 (default 15) |
| `/set_dryrun on\|off` | dry_run 모드 토글 |

## 일일 스케줄

| 시간 | 동작 |
|------|------|
| 08:30 | 장 전 스크리닝 (4팩터 ranking, 15종목 선정) |
| 09:00 | 주문 실행 (rebalance + new entries) |
| 5분마다 | 포지션 모니터링 (손절/익절) |
| 15:20 | 일일 리포트 + daily snapshot 저장 |
| 토요일 10:00 | 주간 장부 점검 (engine_state ↔ KIS 동기화) |

## 디버깅 명령

```bash
# KIS API 인증 확인
python -c "from src.api.kis_client import KISClient; print(KISClient().get_balance())"

# pykrx 확인
python -c "import pykrx; print(pykrx.__version__)"

# 잔고 helpers 검증
python -c "from src.utils.balance_helpers import parse_balance; print(parse_balance({...}))"

# 포지션 파일
cat data/quant/engine_state.json | python -m json.tool

# 일별 스냅샷
cat data/quant/daily_history.json | python -m json.tool
```

## 로그 명령

```bash
tail -f logs/daemon_$(date +%Y%m%d).log
grep -i "error\|exception\|EGW0" logs/daemon_*.log     # 에러
grep -i "BUY\|SELL" logs/daemon_*.log                  # 거래
grep -i "rebalance\|screening" logs/daemon_*.log       # 주요 이벤트
grep -i "EGW00201" logs/daemon_*.log                   # rate limit
```

## 시그널 처리

| 시그널 | 동작 |
|--------|------|
| `SIGTERM` | graceful shutdown — 진행 중 주문 finalize, state 저장, Telegram 종료 |
| `SIGINT` (Ctrl+C) | 동일 |
| `SIGKILL` | 즉시 종료 — `engine_state.json`이 마지막 저장 시점에 머묾 (재기동 시 reconcile 필요) |
