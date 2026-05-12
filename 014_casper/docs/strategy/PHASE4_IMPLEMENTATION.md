# ICT Phase 4 Implementation — OTE / Breaker Block / NQ Futures + Multi-TF SL + Daily Store

> **작성일**: 2026-05-12
> **선행**: PHASE3_IMPLEMENTATION.md, PHASE3_QQQ_MAPPING.md
> **상태**: 핵심 모듈 + Multi-TF SL strategy 통합 + 일봉 store + simulate_trade short 모두 완료. bot.py에 OTE/Breaker hook은 차후 단계.

---

## 1. 본 phase에서 추가된 것

| 항목 | 모듈 / 변경 | 상태 |
|---|---|:---:|
| 일봉 영구 저장 (Parquet 연도별) | `src/data/store.py` `save_daily_bars` + `load_daily_range` | ✅ |
| 일봉 store-first 액세스 | `src/data/market_data.py` `get_daily_df()` (store→KIS→yfinance) | ✅ |
| `simulate_trade` short 분기 | `scripts/intraday_backtest_compare.py` | ✅ |
| Multi-TF SL 정밀화 (1분봉 swing) | `src/core/multi_tf.py` + scan_for_signal 옵션 | ✅ |
| OTE 진입 (피보 0.618 / 0.705 / 0.79) | `src/core/ote.py` | ✅ (모듈) |
| Breaker Block + Unicorn pattern | `src/core/breaker_block.py` | ✅ (모듈) |
| NQ futures 24h + Power of 3 | `src/data/futures.py` (yfinance) | ✅ (모듈) |
| Asia / London / Midnight Open helpers | `src/data/futures.py` | ✅ |
| Judas Swing 감지 | `src/data/futures.py:detect_judas_swing` | ✅ |

### 모듈 단독 사용 가능 / bot.py 통합은 부분적

- Multi-TF SL: `entry.use_multi_tf_sl=true` config 토글 가능 (default OFF, `bars_1m` 인자 봇이 전달해야 함 — 다음 단계)
- OTE / Breaker / Futures: 단독 함수로 호출 가능, 신호 흐름 hook은 별도 plan

---

## 2. 일봉 영구 저장 (가장 큰 quick win)

### 2.1 구조

```
data/marketdata/
└── QQQ/
    ├── daily/
    │   ├── 2025.parquet      (1년치 일봉, ~250 rows, ~5KB)
    │   └── 2026.parquet
    └── 2026/                 (5분봉 일별)
        └── 2026-05-12.parquet
```

연도별 Parquet — `save_daily_bars()`가 자동으로 split + 기존 행과 merge + dedup.

### 2.2 효과

| 측면 | 이전 | 신규 |
|---|---|---|
| 봇 재시작 시 KIS 호출 | 60일 일봉 fetch (~5초) | store 우선 (~50ms) |
| 백테스트 데이터 폭 | yfinance 60일 5분봉 한도 | 일봉 1년+ + 5분봉 60일 |
| Daily Bias 계산 | 매번 fetch | 누적 데이터로 더 정확 |
| 네트워크 의존 | 일봉도 매번 의존 | store cache hit 시 의존 0 |

### 2.3 자동 백필

봇 cold-start에 `_cold_start_backfill()`이 일봉도 호출 — 첫 실행 시 KIS에서 120일치 받아서 저장. 이후엔 store-first.

---

## 3. simulate_trade short 분기

PHASE3_QQQ_MAPPING의 SQQQ Long 매핑 효과를 측정하기 위해 `simulate_trade`에 `Sig.side == "short"` 분기 추가:

```
Long  exit conditions:  bar.Low ≤ stop, bar.High ≥ target
Short exit conditions:  bar.High ≥ stop, bar.Low ≤ target
                        (geometry mirror: stop > entry > target)
```

슬리피지 / 수수료 / SEC fee도 mirror 적용. 신규 `Sig(side='short')` 변형은 backtest 엔진이 자동 인식.

### 사용 예 (백테스트에 short 전략 추가 가능)

```python
def strat_qqq_bear_to_sqqq(day_df, ctx):
    sig = scan_for_signal(... direction='bear')   # QQQ chart
    if sig is None:
        return None
    return Sig(..., side='short')   # simulate_trade가 short으로 처리
```

향후 23번 백테스트 변형: `Casper_QQQ_to_SQQQ_long` — QQQ 5분봉으로 bear 검출 → SQQQ Long 매핑 후 5분봉 시뮬레이션. 다음 plan.

---

## 4. Multi-TF SL 정밀화

`scan_for_signal()`에 새 파라미터:

```
use_multi_tf_sl: bool          → 1분봉으로 SL 다시 잡기
bars_1m: pd.DataFrame          → 1분봉 데이터 (KIS nmin=1)
mtf_lookback_min: int = 15     → 신호 시점 이전 N분 동안의 swing
```

### 동작

```
1. 5-min strict ORB+FVG signal 검출 (기존)
2. signal time 이전 15분 1-min bars 추출
3. long → min(Low), bear → max(High) 가 새 SL
4. min_risk 미만 시 5-min SL로 폴백
```

### 정량 효과 (추정)

| 시나리오 | 5-min SL | 1-min SL | 개선 |
|---|---:|---:|---|
| TQQQ 09:55 진입 | $50.20 (5분봉 prev low) | $50.27 (1분봉 swing low) | risk 0.07$ → 0.40$ (R:R 1:3 도달 ↑) |
| SQQQ 10:00 진입 | $77.46 (5분봉 prev low) | $77.55 (1분봉 swing) | risk 줄어듦 |

평균 30~60% SL 단축 → R:R 1:3 도달률 +15~20% 기대.

### Config 토글

```json
"entry": {
  ...
  "use_multi_tf_sl": false,    ← Phase 4 추가
  "mtf_lookback_min": 15
}
```

`.env`로도 override 가능: `ICT_USE_MULTI_TF_SL=on`.

---

## 5. OTE (Optimal Trade Entry) 모듈

```python
from src.core.ote import ote_entry_price, fvg_overlaps_ote

# 5-min impulse: 100 → 110
entry = ote_entry_price(100.0, 110.0, direction="bull", fib_level=0.705)
# → entry = 110 - 0.705 × 10 = 102.95

# FVG와 OTE 영역이 겹치는지 확인 (Unicorn 후보)
if fvg_overlaps_ote(fvg_top=104.0, fvg_bot=102.5, ote_price=entry):
    use_ote = True
```

ICT 표준 fib: **0.618 / 0.705 / 0.79**. 0.705 (Casper 권고)가 본 모듈 default.

### Strategy 통합 (다음 단계 plan)

`scan_for_signal()`에 `use_ote: bool`, `ote_fib_level: float` 추가 후 entry_price = ote_entry_price(...). 별도 hook plan으로 분리.

---

## 6. Breaker Block + Unicorn Pattern 모듈

### 정의

1. **Order Block**: 마지막 *opposite* 캔들 (bullish impulse 직전의 마지막 음봉)
2. **Breaker Block**: OB가 *깨진 후* 가격이 다시 돌아온 zone (역할 반전: 지지→저항 or 반대)
3. **Unicorn Pattern**: Breaker zone과 FVG zone이 *겹치는* 진입 setup (ICT 최강 reversal)

### API

```python
from src.core.breaker_block import find_order_block, to_breaker_block, is_unicorn

ob = find_order_block(bars_5m, impulse_end_index=20, direction="bull")
if ob:
    bb = to_breaker_block(ob, bars_after=bars_5m.iloc[21:])
    if bb and is_unicorn(bb, fvg_top=, fvg_bottom=):
        # Highest-probability ICT reversal entry
        ...
```

### Strategy 통합 (다음 단계 plan)

`scan_for_signal()`에 `require_unicorn: bool` 추가. 활성화 시 ORB+FVG + Unicorn 동시 검증. 매매 빈도 추가 감소 가능성 — 1년+ 데이터로 검증 필요.

---

## 7. NQ Futures 24h + Power of 3

### 데이터 소스

- yfinance `NQ=F` — 5-min, ~60일, 23h 세션 (Sun 18:00 ET ~ Fri 17:00 ET)
- KIS는 NQ futures 미제공 (해외선물 계좌 필요)

### 제공 함수

| 함수 | 반환 | 용도 |
|---|---|---|
| `fetch_nq_futures_5m(period="60d")` | DataFrame | 신선한 NQ 5분봉 |
| `asia_session_range(bars, day)` | (high, low) | Asia accumulation box |
| `london_session_range(bars, day)` | (high, low) | London Killzone |
| `midnight_open_price(bars, day)` | float | ICT True Open (00:00 ET) |
| `detect_judas_swing(bars, day)` | 'bullish_judas' / 'bearish_judas' / None | Power of 3 manipulation phase |

### Power of 3 (AMD) 검출 흐름

```
Accumulation → Asia session range (18:00 prev ~ 00:00 ET)
Manipulation → 00:00 ~ 09:30 ET 사이 Asia 한쪽 breach 후 reversal (= Judas Swing)
Distribution → 09:30 이후 실제 방향 (= 정통 ICT 추세)
```

판정:
- bearish_judas → 그날 bearish bias 확정 → SQQQ Long 우선 검토
- bullish_judas → bullish bias → TQQQ Long 우선 검토

### Strategy 통합 (다음 단계 plan)

Daily Bias score 보강: Judas Swing 결과를 ±1로 가산 → 더 정확한 신호 우선순위.

---

## 8. Config / Env 추가

`config/strategy_params.json`:

```json
"entry": {
  ...
  "use_multi_tf_sl": false,     ← Phase 4 신규
  "mtf_lookback_min": 15        ← Phase 4 신규
}
```

`.env` (`.env.example` 갱신 권장):

```bash
# Phase 4
ICT_USE_MULTI_TF_SL=on       # multi-TF SL refinement
ICT_USE_OTE=on               # (future) OTE entry override
ICT_USE_BREAKER_BLOCK=on     # (future) Unicorn pattern
ICT_USE_POWER_OF_3=on        # (future) Judas Swing bias boost
ICT_FIB_LEVEL=0.705
```

활성화 옵션은 모두 **default OFF** — 현재 봇 동작 영향 0.

---

## 9. 신규 테스트 (Phase 4 단독)

| 파일 | 테스트 수 |
|---|:---:|
| `tests/test_data_store_daily.py` | 10 |
| `tests/test_multi_tf.py` | 6 |
| `tests/test_ote.py` | 9 |
| `tests/test_breaker_block.py` | 9 |
| `tests/test_futures.py` | 6 |
| **합계** | **40** |

회귀: 이전 472 → 신규 합산 후 ~512 tests, 회귀 0 기대.

---

## 10. 남은 통합 작업 — **완료 (2026-05-12 N1~N6)**

| 작업 | 상태 | 통합 위치 |
|---|:---:|---|
| ✅ OTE entry → `scan_for_signal()` | 완료 | `entry.use_ote / ote_fib_level` |
| ✅ Breaker Block + Unicorn → strategy | 완료 | `entry.require_unicorn` |
| ✅ Power of 3 Judas Swing → Daily Bias score | 완료 | `entry.use_power_of_3` + bias.judas_signal 인자 |
| ✅ TQQQ도 QQQ-mapping (대칭) | 완료 | `entry.bull_fvg_for_tqqq` + `remap_qqq_bull_to_tqqq_long()` |
| ✅ QQQ→SQQQ 백테스트 변형 (#23/#24) | 완료 | `strat_qqq_bear_short[_full_ict]` — short simulate_trade 활용 |
| 1분봉 KIS fetch + bot 전달 | 완료 | `bot.py` use_multi_tf_sl 시 `interval="1m"` fetch |
| 동적 leverage factor (SQQQ/QQQ 실측) | 보류 | 별도 plan (운용 데이터 누적 후) |

### 신규 config / env (모두 default OFF)

| 키 | env override | 의미 |
|---|---|---|
| `entry.use_multi_tf_sl` | `ICT_USE_MULTI_TF_SL` | 1분봉 swing으로 SL 단축 |
| `entry.mtf_lookback_min` | `ICT_MTF_LOOKBACK_MIN` | 1분봉 swing 검색 윈도우 (default 15) |
| `entry.use_ote` | `ICT_USE_OTE` | FVG 중간점 대신 OTE 0.705 진입 |
| `entry.ote_fib_level` | `ICT_FIB_LEVEL` | OTE 피보 레벨 (default 0.705) |
| `entry.require_unicorn` | `ICT_REQUIRE_UNICORN` | Breaker ∩ FVG 검증 강제 |
| `entry.use_power_of_3` | `ICT_USE_POWER_OF_3` | Daily Bias에 Judas Swing 가산 (±1) |
| `entry.bull_fvg_for_tqqq` | `ICT_BULL_FVG_FOR_TQQQ` | QQQ Bull setup → TQQQ Long 매핑 |

### 봇 동작 영향 (재시작 시)

- 모든 새 옵션 default OFF → 현재 동작과 100% 동일
- 활성화 시:
  - `use_multi_tf_sl=on` → 1분봉 자동 fetch (KIS `nmin=1`, NREC 120) + tighter SL
  - `use_ote=on` → entry_price = FVG mid 대신 fib 0.705 (FVG 영역과 overlap할 때만)
  - `require_unicorn=on` → Breaker ∩ FVG 검증 추가 (매매 빈도 더 감소 가능)
  - `use_power_of_3=on` → NQ futures 5분봉 fetch + Judas Swing 감지 + bias ±1
  - `bull_fvg_for_tqqq=on` → QQQ bull setup → TQQQ Long (대칭 매핑)

---

## 11. 다음 봇 재시작 시 효과

- 일봉 store 자동 백필 (cold start backfill)
- Multi-TF SL은 토글 OFF — 옵션만 추가됨
- 봇 동작 100% 이전과 동일
- 향후 토글 ON 시 진입 SL 정밀화 효과 즉시 발생

---

## 12. 산출물

| 항목 | 경로 |
|---|---|
| 일봉 store | `src/data/store.py` (확장) |
| 일봉 액세스 | `src/data/market_data.py` `get_daily_df()` |
| Multi-TF | `src/core/multi_tf.py` |
| OTE | `src/core/ote.py` |
| Breaker Block | `src/core/breaker_block.py` |
| NQ Futures | `src/data/futures.py` |
| Backtest short 분기 | `scripts/intraday_backtest_compare.py` |
| 본 보고서 | `docs/strategy/PHASE4_IMPLEMENTATION.md` |
| 테스트 (5 파일, 40 tests) | `tests/test_*.py` |
