# Troubleshooting

## telegram.error.Conflict 에러

`start_all_bots.sh`로 실행 시 각 봇은 독립 토큰 사용 → 프로젝트 간 충돌 아님.
같은 프로젝트 내 중복 실행 확인:
```bash
ps aux | grep "ver3/run_cli.py"
```

## 봇이 멈추고 API 조회 안 됨

로그에서 Cycle 시작 후 분석 결과가 없으면 **Bithumb API hang** 의심:
- 네트워크 문제 또는 API 서버 응답 지연
- Mac sleep 상태에서 발생 가능

## Hang 방지 시스템

다층 Timeout 보호 체계로 hang 발생 시 자동 복구:

```
Layer 1: API Timeout (5s connect + 15~30s read)
    ↓
Layer 2: ThreadPoolExecutor (60s/coin, 120s total)
    ↓  + Non-blocking shutdown (wait=False, cancel_futures=True)
Layer 3: Analysis Cycle Warning (180s)
    ↓
Layer 4: Consecutive Timeout (3회 연속 → 자동 재시작)
    ↓
Layer 5: Watchdog (600s → kill & restart)
```

### Timeout 설정값

| 레이어 | 위치 | 값 |
|--------|------|-----|
| API (Public) | `bithumb_api.py` | connect=5s, read=30s |
| API (Private) | `bithumb_api.py` | connect=5s, read=15s |
| ThreadPool (per coin) | `portfolio_manager_v3.py` | 60s |
| ThreadPool (total) | `portfolio_manager_v3.py` | 120s |
| Consecutive Timeout | `trading_bot_v3.py` | 3회 |
| Telegram | `telegram_notifier.py` | connect=5s, read=10s |
| Watchdog | `run_v3_watchdog.sh` | 600s |

### Timeout 발생 시 동작

| 상황 | 동작 |
|------|------|
| API Timeout | 해당 요청 실패, 재시도 로직 |
| ThreadPool Timeout | 해당 코인 HOLD 처리, 이전 유효 레짐 보존 (`REGIME (⏱)` 표시) |
| Consecutive Timeout (3회) | Telegram 알림 + 봇 종료 → Watchdog 재시작 |
| Telegram Timeout | 메시지 드롭, 봇 동작 영향 없음 |
| Watchdog Timeout | 봇 강제 종료 후 재시작 |
