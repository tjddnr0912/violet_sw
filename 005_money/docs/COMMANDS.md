# 005_money 명령 카탈로그

## 실행 스크립트

| 명령 | 동작 | 부작용 |
|------|------|------|
| `./scripts/run_v3_watchdog.sh` | Watchdog + 봇 (자동 재시작 + hang 감지) — **권장** | 라이브 거래 시작 (config dry_run 따름) |
| `./scripts/run_v3_cli.sh` | 단순 CLI (watchdog 없음) | 라이브 거래 시작 |
| `./scripts/run_v3_gui.sh` | GUI 모드 | Tkinter 창 오픈 |
| `python ver3/run_cli.py` | venv 활성화 후 직접 실행 | watchdog 보호 없음 — 일반적으로 사용 X |

### Watchdog 옵션

```bash
./scripts/run_v3_watchdog.sh                       # 기본 (10분 hang timeout)
./scripts/run_v3_watchdog.sh --hang-timeout 300    # 5분으로 단축
./scripts/run_v3_watchdog.sh --max-restarts 10     # 재시작 횟수 제한
```

| 환경변수 | 기본값 | 설명 |
|---------|------|------|
| `HANG_TIMEOUT` | 600s | 로그 활동 없으면 hang 판단 |
| `HANG_GRACE_PERIOD` | 120s | 봇 시작 후 대기 시간 |
| `HANG_CHECK_INTERVAL` | 60s | hang 체크 주기 |

## 텔레그램 명령어

| 명령 | 동작 |
|------|------|
| `/start` | 환영 메시지 |
| `/help` | 도움말 |
| `/status` | 봇 상태 (uptime, cycle 수, 마지막 분석 시각, 포지션 현황) |
| `/positions` | 코인별 포지션 상세 (P&L, 레짐, 진입 스코어) |
| `/summary` | 일일 요약 |
| `/factors` | 동적 팩터 (볼라틸리티, ATR%, multipliers) |
| `/performance` | 7일 성과 |
| `/close <COIN>` | 특정 코인 포지션 수동 청산 (확인 버튼 포함) |
| `/stop` | 봇 종료 (Watchdog도 종료, exit 0) |
| `/reboot` | 봇 재시작 (Watchdog이 재기동, exit 1) |

`/stop` vs `/reboot`:
- `/stop`: 완전 종료 (Watchdog도 stop)
- `/reboot`: 봇만 재시작 (Watchdog 유지) — 설정 변경 적용, 메모리 정리, 빠른 복구

## 단일 분석 테스트

```python
from dotenv import load_dotenv
load_dotenv('.env')

from ver3.config_v3 import get_version_config
from ver3.trading_bot_v3 import TradingBotV3

config = get_version_config()
bot = TradingBotV3(config)

# 단일 코인 분석
result = bot.analyze_market('BTC')
print(result)

# 전체 포트폴리오 요약
summary = bot.get_portfolio_summary()
print(summary)
```

## 로그 명령

```bash
tail -f logs/ver3_cli_$(date +%Y%m%d).log         # 실시간
grep -i "error\|exception" logs/ver3_cli_*.log    # 에러만
grep -i "BUY\|SELL" logs/ver3_cli_*.log           # 거래만
grep -i "regime" logs/ver3_cli_*.log              # 레짐 변경
grep -i "timeout\|⏱" logs/ver3_cli_*.log          # timeout
```

## 디버깅 명령

```bash
# Telegram 환경변수 로드 확인
python -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); print(os.getenv('TELEGRAM_BOT_TOKEN'))"

# 빗썸 API 인증 확인
python -c "from lib.api.bithumb_api import get_ticker; print(get_ticker('BTC'))"

# 포지션 파일 확인
cat logs/positions_v3.json | python -m json.tool

# 중복 인스턴스 확인
ps aux | grep "ver3/run_cli.py"
```

## 시그널 처리

| 시그널 | 동작 |
|--------|------|
| `SIGTERM` (kill) | graceful shutdown, 포지션 자동 청산 X |
| `SIGINT` (Ctrl+C) | 동일 |
| `SIGKILL` | 즉시 종료 — 포지션 파일 일관성 깨질 수 있음 |
