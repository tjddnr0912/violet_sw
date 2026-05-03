# 005_money 트러블슈팅

각 항목은 6필드(증상/원인/해결/복구절차/관련 사고/재발 감지) + Claude 진단 미스 기록 구조를 따른다.

---

## BUY 텔레그램 알림만 안 옴 — Markdown 파싱 에러

- **증상**: BUY 알림은 Telegram에 도착 안 함. SELL/CLOSE는 정상.
- **원인**: BUY의 `reason` 필드에 `strong_bearish` 등 `_` 포함 문자열이 들어감 → Telegram Markdown 파서가 `_..._`를 italic 마커로 해석 → 짝 안 맞아서 entity parsing failed. SELL/CLOSE는 `_` 없는 reason이라 통과.
- **해결**: `telegram_notifier.py`의 `send_trade_alert`에서 `reason` 내 `_`를 `\_`로 escape.
- **복구 절차**: 코드 패치 후 즉시 적용. 과거 누락된 BUY 알림은 `transaction_history.json`에서 재구성.
- **관련 사고**: 2025-12-20 (telegram-html-parsing-error)
- **재발 감지**: 일일 알림 수에서 BUY/SELL 비율 비정상 (BUY가 0건이면 의심).

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: 네트워크 문제 또는 Telegram API rate limit
- **실제 원인**: 메시지 본문 자체가 거부 — `send_message` 에러 핸들러가 `print()`만 사용해서 로그 파일에 미기록 → 진단 단서 부재
- **방향 전환 지점**: 사용자가 "SELL은 가는데 BUY만 안 와" 지적 → 메시지 내용 차이 인식
- **교훈**:
  - 첫 의심 영역: **메시지 본문의 특수문자** (Markdown/HTML 메타 문자)
  - 빨리 배제할 가설: "rate limit" — 일부 메시지만 누락이면 본문 문제
  - 핵심 진단 명령: `print` 대신 `logger.error`로 응답 본문 풀 캡처

---

## telegram.error.Conflict 409 — 같은 봇 중복 실행

- **증상**: 봇 시작 직후 `terminated by other getUpdates request`. polling 루프 비정상.
- **원인**: 같은 프로젝트 내에서 ver3 프로세스가 두 개 살아있음. 프로젝트 간 봇은 토큰이 다르므로 충돌 아님.
- **해결**:

  ```bash
  ps aux | grep "ver3/run_cli.py"
  # 중복 PID kill
  kill <PID>
  ```

- **복구 절차**: 중복 프로세스 정리 후 단일 인스턴스로 재기동. `run_v3_watchdog.sh`는 PID 파일로 자체 보호하지만 직접 `python ver3/run_cli.py` 호출 시 보호 없음.
- **관련 사고**: 2026-01-17 (telegram-409-conflict)
- **재발 감지**: 시작 후 60s 내 Conflict 에러 발생 빈도. 정상 봇은 0건.

---

## 봇이 멈추고 API 조회 안 됨 — Bithumb API hang

- **증상**: Cycle 시작 로그는 찍히는데 분석 결과 로그가 안 나옴. 봇이 살아있지만 응답 없음.
- **원인**: Bithumb API 응답 지연 또는 hang. Mac sleep 복귀 시 네트워크 재연결 지연도 동일 패턴.
- **해결**: 다층 Timeout 보호 체계로 자동 복구 (아래 "Hang 방지 시스템" 섹션).
- **복구 절차**: 일반적으로 자동 복구. 수동 복구 필요 시 `/reboot` 텔레그램 명령.
- **관련 사고**: 2026-01-07 (threadpoolexecutor-hang)
- **재발 감지**: `Analysis timeout` 또는 `⏱` 로그 빈도. 일반적으로 일일 0~2건 — 그 이상이면 네트워크 점검.

---

## 분석 cycle 동시 timeout 누적 → lockup

- **증상**: 모든 코인이 연속 timeout. 봇은 살아있지만 거래 결정 0건.
- **원인**: 네트워크 단절 또는 Bithumb API 장애 지속. 봇 자체 retry로는 못 뚫음.
- **해결**: `_max_consecutive_timeouts=3` 도달 시 봇이 `exit(1)` → Watchdog 재시작.
- **복구 절차**: 자동 복구 (Watchdog 60s 내 재시작). 수동 개입 시 `/reboot`.
- **관련 사고**: 다수 (Mac sleep 복귀 시 빈번)
- **재발 감지**: Telegram에 `🚨 연속 Timeout 감지` 알림 도착. 일일 0건이 정상.

### Claude 진단 미스 (이전 세션에서 있었음)
- **Claude 처음 가설**: 봇 코드의 lockup, threading bug
- **실제 원인**: ThreadPoolExecutor의 `shutdown(wait=True)`가 timeout 후에도 실행 중인 태스크 완료를 기다려서 다음 cycle 진입 못함
- **방향 전환 지점**: `wait=False, cancel_futures=True` 옵션으로 즉시 반환 패턴 도입 후 해결
- **교훈**:
  - 첫 의심 영역: **ThreadPool shutdown 옵션** (wait, cancel_futures)
  - 빨리 배제할 가설: "Python GIL", "threading bug" — 보통 표준 라이브러리 옵션 미설정
  - 핵심 진단 명령: timeout 발생 후 다음 cycle까지 elapsed 측정 — 60s 이상이면 shutdown 대기

---

## Hang 방지 시스템 (참고용 — 트러블 아님, 정상 설계)

다층 Timeout 보호 체계로 hang 발생 시 자동 복구:

```
Layer 1: API Timeout (5s connect + 15~30s read)
    ↓
Layer 2: ThreadPoolExecutor (60s/coin, 120s total)
    ↓ + Non-blocking shutdown (wait=False, cancel_futures=True)
Layer 3: Analysis Cycle Warning (180s)
    ↓
Layer 4: Consecutive Timeout (3회 연속 → exit(1) → Watchdog 재시작)
    ↓
Layer 5: Watchdog (600s 무활동 시 kill & restart)
```

### Timeout 설정값

| 레이어 | 위치 | 값 |
|--------|------|-----|
| API (Public) | `bithumb_api.py::API_TIMEOUT_PUBLIC` | (5, 30) |
| API (Private) | `bithumb_api.py::API_TIMEOUT_PRIVATE` | (5, 15) |
| ThreadPool (per coin) | `portfolio_manager_v3.py::ANALYSIS_TIMEOUT_PER_COIN` | 60s |
| ThreadPool (total) | `portfolio_manager_v3.py::TOTAL_ANALYSIS_TIMEOUT` | 120s |
| Consecutive Timeout | `trading_bot_v3.py::_max_consecutive_timeouts` | 3 |
| Telegram | `telegram_notifier.py::TELEGRAM_TIMEOUT` | (5, 10) |
| Watchdog | `run_v3_watchdog.sh::HANG_TIMEOUT` | 600s |

### Timeout 발생 시 동작

| 상황 | 동작 |
|------|------|
| API Timeout | 해당 요청 실패, 재시도 |
| ThreadPool Timeout | 해당 코인 HOLD 처리, 이전 유효 레짐 보존 (`REGIME (⏱)` 표시) |
| Consecutive Timeout (3회) | Telegram 알림 + 봇 종료 → Watchdog 재시작 |
| Telegram Timeout | 메시지 드롭, 봇 동작 영향 없음 |
| Watchdog Timeout | 봇 강제 종료 후 재시작 |
