# Casper Bot - 종합 코드 리뷰 및 수정 보고서

> 초기 리뷰: 2026-04-04
> 최종 수정: 2026-04-04
> 대상: src/ 전체, tests/ 전체

---

## 1. 최종 현황

| 항목 | 수정 전 | 수정 후 |
|------|--------|--------|
| 소스 LOC | 1,853줄 | ~2,300줄 |
| 테스트 파일 | 8개 | **17개** |
| 테스트 수 | 73개 | **223개** |
| 테스트 통과율 | 73/73 | **223/223 (100%)** |
| Critical 이슈 | 5건 | **0건** |
| High 이슈 | 9건 | **0건** |
| Medium 이슈 | 8건 | **0건** |
| Low 이슈 | 5건 | **0건** |
| 미해결 | — | **0건** |

---

## 2. 전체 수정 내역

### Critical (5/5 완료)

| # | 이슈 | 수정 내용 |
|---|------|----------|
| C-1 | `_tick()` 예외 미처리 | try/except + notify_error + 30초 sleep 후 재시도 |
| C-2 | KISOrder 미연결 | `_init_kis()` → buy/sell_market 연결 |
| C-3 | 포지션 복구 없음 | `position_state.json` 영속화 + 크래시 복구 |
| C-4 | SIGTERM 미처리 | signal.SIGTERM → SystemExit + graceful shutdown |
| C-5 | `self.trend` None 접근 | `_handle_scanning()`에 None 가드 |

### High (9/9 완료)

| # | 이슈 | 수정 내용 |
|---|------|----------|
| H-1 | 비원자적 JSON 저장 | `.tmp` + `os.replace()` 패턴 |
| H-2 | 빈 토큰 독 | 빈 access_token 거부 |
| H-3 | 하드코딩 자본금 | `get_us_balance()` 조회 → 폴백 |
| H-4 | 강제청산 진입가 폴백 | 매도 후 `get_us_filled_price()` 체결가 조회 |
| H-5 | 주말 가드 누락 | `is_force_close_time/is_past_be_time`에 `is_weekday()` 추가 |
| H-6 | yfinance NaN/Inf/0 | `_valid_price()` 검증 함수 적용 |
| H-7 | 설정파일 무가드 크래시 | SystemExit + 사용자 메시지 |
| H-8 | CB capital 폴백값 1 | `capital_after` → `capital` → skip |
| H-9 | POST 재시도 중복 주문 | `retry=False` 파라미터로 주문 POST 재시도 차단 |

### Medium (8/8 완료)

| # | 이슈 | 수정 내용 |
|---|------|----------|
| M-1 | 미국 공휴일 미인식 | `config/us_holidays.json` + `is_trading_day()` 함수 |
| M-2 | yfinance 타임아웃 없음 | `ThreadPoolExecutor` 기반 30초 타임아웃 래퍼 |
| M-3 | done_today 반복 I/O | `_done_today_logged` 플래그 |
| M-4 | 토큰 파일 권한 | `os.chmod(TOKEN_FILE, 0o600)` |
| M-5 | float/int 빈 문자열 | `output.get("last") or 0` + try/except |
| M-6 | 포지션 사이즈 상한 없음 | `max_shares`, `max_position_pct` 파라미터 적용 |
| M-7 | 주간 손실률 기준 모호 | `_week_start_capital` 기반으로 변경 |
| M-8 | `max_trades_per_day` 미사용 | `trades_today` 카운터 + `_execute_entry` 가드 |

### Low (5/5 완료)

| # | 이슈 | 수정 내용 |
|---|------|----------|
| L-1 | trend 필드 버그 | `position.signal.orb.date` → `position.direction` |
| L-2 | BE price 근사치 | `entry * (1+r)/(1-r)` 정확한 라운드트립 공식 |
| L-3 | broad except 마스킹 | `FuturesTimeout` 명시 + 예외 타입 로깅 |
| L-4 | xargs 명령 주입 | `set -a; source .env; set +a` 로 변경 |
| L-5 | config 캐시 격리 | `reset_config_cache()` 함수 추가 |

---

## 3. 테스트 체크리스트 (최종)

### 전체 통과: 223/223 ✅

**core/ 모듈**
- [x] `calculate_orb()` — 정상, 데이터 부족, 빈 DataFrame, mid값
- [x] `is_orb_too_wide()` — 정상, 과대, 경계값, 제로 ADR
- [x] `detect_bullish_fvg()` — FVG 존재, 미존재, 데이터 부족, mid값
- [x] `check_breakout_with_fvg()` — 돌파, 미돌파, 음봉, 경계 인덱스
- [x] `scan_for_signal()` — 시그널 발견, 미돌파, 데이터 부족, 최소 리스크
- [x] `check_pullback()` — 풀백 발생, 미발생
- [x] `create_position()` / `check_exit()` / `move_stop_to_breakeven()` / `close_position()`
- [x] `Position` 속성 — is_open, net_pnl, r_multiple, result, breakeven_price (정확한 공식)
- [x] `check_vix_filter()` — 정상, 너무 낮음/높음, 경계
- [x] `determine_trend()` — 강세, 약세, 동일=약세
- [x] `CircuitBreaker` — record_trade, reset_if_new_week, load_from_trades (8개 시나리오)
- [x] `CircuitBreaker` — 주 시작 잔고 기준 손실률, 폴백 로직

**api/ 모듈**
- [x] `KISAuth` — init, token, headers, request_new_token (성공/빈토큰/실패/키누락), cache (로드/저장/파손)
- [x] `KISClient` — _request (성공/에러/재시도/네트워크에러/POST/retry=False), get_us_price, get_us_balance, get_us_filled_price
- [x] `KISOrder` — init (live/paper), _place_order (qty<1, 음수), buy/sell_market, buy/sell_limit, body 검증

**data/ 모듈**
- [x] `trade_store` — load/save/append/corrupt, atomic save, trade_from_position (trend 필드 포함)
- [x] `market_data` — VIX/QQQ/intraday/ADR/current_price (정상/빈/NaN), _valid_price, yf_timeout

**telegram/ 모듈**
- [x] `TelegramNotifier` — init, send (비활성/성공/에러), notify_* 6종

**utils/ 모듈**
- [x] `config` — load_strategy_params (성공/파일없음/JSON오류), load_env, get_kis_urls, reset_config_cache
- [x] `time_utils` — 시간 윈도우 7종, 공휴일, seconds_until, format_et, now_kst, today_et, get_week_number
- [x] `logger` — setup_logger (핸들러 생성, 멱등성)

**bot.py 상태 머신**
- [x] `_tick()` — 상태별 디스패치 (WAITING/PRE_MARKET/SCANNING), 일자 변경 감지
- [x] `_transition()` / `_reset_day()` — 상태 변경, 전체 초기화
- [x] `_handle_waiting()` — 주말, pre_market/orb_forming 전환
- [x] `_handle_pre_market()` — VIX 성공/실패, QQQ 성공/실패, CB 블록, 트렌드 설정
- [x] `_handle_orb_forming()` — trend=None 처리, ORB 계산 성공, 데이터 없음
- [x] `_handle_scanning()` — trend=None 가드, 스캔 윈도우 종료
- [x] `_execute_entry()` — TEST_MODE, 자본금 부족, price=0, max_trades 제한, max_shares 캡
- [x] `_handle_position_open()` — 포지션 없음, TP 종료
- [x] `_close_and_record()` — 거래 저장, 체결가 조회 (성공/실패 폴백)
- [x] `_handle_done_today()` — 1회만 로그
- [x] `run()` — tick 예외 catch + 재시도, SIGTERM/SystemExit 처리
- [x] 포지션 영속화 — 저장, 복원, 삭제, 파손 파일

**통합 테스트**
- [x] ORB→FVG→시그널→포지션→종료 전체 파이프라인
- [x] 손실/BE/승리 시나리오
- [x] 저장+통계, VIX/CB/트렌드

---

## 4. 에러 대응 흐름도 (최종)

```
yfinance 실패    → 30초 타임아웃 → except → None 반환 → NaN/Inf 검증 → ✅
KIS API 실패     → GET: 3회 재시도 / POST: 재시도 없음 → None → ✅
KIS 인증 실패    → 빈 토큰 거부 → 재시도 → ✅
JSON 파일 파손   → except → 빈 리스트 → atomic save로 방지 → ✅
설정 파일 누락   → SystemExit + 메시지 → ✅
Telegram 실패    → except → 로그만 → ✅
_tick() 내 예외  → except → 로그 + 알림 + 30초 sleep → ✅
SIGTERM 수신     → SystemExit → position state save → ✅
봇 크래시        → position_state.json → 재시작 시 복원 → ✅
강제청산 가격    → yfinance → KIS API → 체결가 조회 → entry 폴백 → ✅
공휴일           → us_holidays.json → is_trading_day() → ✅
중복 주문        → POST retry=False → 1회만 시도 → ✅
포지션 과대      → max_shares + max_position_pct 캡 → ✅
```

---

## 5. 추가된 파일

| 파일 | 용도 |
|------|------|
| `config/us_holidays.json` | 미국 시장 공휴일 (2026-2027) |
| `tests/conftest.py` | 공유 fixture |
| `tests/test_kis_order.py` | KIS 주문 모듈 테스트 (14개) |
| `tests/test_kis_auth.py` | KIS 인증 모듈 테스트 (13개) |
| `tests/test_kis_client.py` | KIS 클라이언트 테스트 (15개) |
| `tests/test_circuit_breaker_restore.py` | CB 복원 테스트 (8개) |
| `tests/test_config.py` | 설정 모듈 테스트 (8개) |
| `tests/test_notifier.py` | 텔레그램 테스트 (10개) |
| `tests/test_market_data.py` | 시장 데이터 테스트 (17개) |
| `tests/test_bot_states.py` | 봇 상태 머신 테스트 (21개) |
| `tests/test_bot_advanced.py` | 봇 고급 테스트 (15개) |
| `tests/test_trade_store_extended.py` | 거래 저장 확장 테스트 (7개) |
| `tests/test_remaining_fixes.py` | M/L 수정 검증 테스트 (15개) |
