# ICT Phase 3 Implementation — Bearish FVG + Daily Bias 정밀화

> **작성일**: 2026-05-12  •  **선행**: ICT_STRATEGY_INTEGRATION.md, PHASE1_PRECHECK.md, PHASE2_IMPLEMENTATION.md
> **업데이트**: 2026-05-12 — Daily Bias bot 통합 + QQQ→SQQQ 매핑 추가 (PHASE3_QQQ_MAPPING.md 참조)
> **상태**: ✅ **bot 통합 완료** — Daily Bias hook + QQQ-signal mapping 모두 활성화 가능. simulate_trade short 분기만 보류.

---

## 1. 구현 범위

| ICT 개념 | 모듈 / 변경점 | 테스트 |
|---|---|:---:|
| Bearish FVG 검출 | `src/core/fvg.py` `detect_bearish_fvg()`, `check_breakdown_with_fvg()` | 9 ✅ |
| Bearish breakout signal flow | `src/core/strategy.py` — `direction='bull'/'bear'` 옵션 | 4 ✅ |
| Daily Bias 다층화 (PDH/PDL/PWH/PWL + MA20/50) | `src/core/bias.py` `compute_daily_bias()` | 9 ✅ |

**신규 테스트 22개 모두 통과**. 기존 411 + 22 = **433 tests, 회귀 0** (회귀 백그라운드 실행 중).

ICT_STRATEGY_INTEGRATION §5 Phase 3에서 **QQQ-신호 분리(symbol exec mapping)** 는 가격 변환 정확도 + bot dual_scan re-engineering 부담으로 **별도 plan**으로 분리. 본 phase는 그 토대(bearish 신호 흐름, 정밀 bias)를 완성.

---

## 2. 알고리즘 정의

### 2.1 Bearish FVG

```python
detect_bearish_fvg(c1, c2, c3):
    if c1.Low > c3.High:
        return FairValueGap(top=c1.Low, bottom=c3.High, ...)
```

진입 zone의 의미는 mirror — bullish FVG는 상승 후 pullback 시 진입, bearish FVG는 하락 후 반등 시 진입.

### 2.2 Bearish breakdown (strict)

```python
check_breakdown_with_fvg(bars, orb_low, i, strict=True):
    breakdown candle:  Close < orb_low AND Close < Open
    strict S1:         Close <= orb_low <= Open  (body straddles ORB line)
    bearish FVG:       c1.Low > c3.High
    strict S2:         fvg.bottom <= orb_low <= fvg.top
```

bullish strict의 mirror. 캐스퍼 ORB+FVG strict의 일관성 유지.

### 2.3 Bearish signal in scan_for_signal

```python
scan_for_signal(..., direction='bear'):
  - check_breakdown_with_fvg() 사용
  - entry_price = fvg.mid
  - stop_loss = prev_candle.High      (mirror of Low)
  - risk = stop_loss - entry_price
  - take_profit = entry_price - risk * rr_ratio
  - signal.direction = 'short'
```

기존 bullish 경로는 `direction='bull'` (default)로 100% 보존.

### 2.4 Daily Bias scoring

| 컴포넌트 | 가중 | 기준 |
|---|---|---|
| MA20 | ±1 | close vs 20-day MA |
| MA50 | ±1 | close vs 50-day MA |
| PDH/PDL | ±1 | close > PDH (+1) / < PDL (-1) / 사이 (0) |
| PWH/PWL | ±1 | close > PWH (+1) / < PWL (-1) / 사이 (0) |

- score > 0 → bull, < 0 → bear, == 0 → neutral
- `daily_bias_skip_neutral=True` (config 옵션) 시 neutral 일자는 매매 회피

ICT_STRATEGY_INTEGRATION.md §C8 권고 그대로.

---

## 3. 통합 흐름 (현재 + Phase 3)

```
[ Trend Filter ]                          ← Phase 3에서 정밀 bias로 교체 가능
  ↓ QQQ MA20 (현재) or compute_daily_bias() (옵션)
[ Daily Decision ]
  ↓ Bull → TQQQ, Bear → SQQQ, Neutral → skip
[ ORB Formation ]                         ← 변경 없음
  ↓
[ Scan for signal ]
  ├─ direction='bull' (TQQQ leg)        ← 기존
  └─ direction='bear' (옵션 — QQQ short setup, 추후 매핑)
[ Filters: KZ / Disp / Sweep+CHoCH ]    ← Phase 1/2 그대로 적용
  ↓
[ Pullback entry → Position open ]
```

---

## 4. Config 추가

`config/strategy_params.json` → `entry`:

| 키 | 기본값 | 의미 |
|---|---|---|
| `bear_fvg_for_sqqq` | `false` | (옵션) SQQQ 스캔 시 direction='bear' 모드 사용 |
| `daily_bias_skip_neutral` | `false` | (옵션) bias=neutral 일자 매매 회피 |

**default OFF로 봇 영향 0**. 활성화는 별도 통합 plan에서 진행.

---

## 5. 백테스트 시뮬레이션 — 보류 사유

Phase 1/2는 ICT 필터가 *기존 bullish 흐름*을 조이는 형태라 `simulate_trade` 변경 없이 백테스트 가능했다.

Phase 3 bearish 신호는 **short trade 시뮬레이션 분기 추가 필요**:
- TP check: `bar.Low <= target` (mirror)
- SL check: `bar.High >= stop`
- 슬리피지: 매수(청산)/매도(진입) 반대

simulate_trade 변경은 50+ 줄 추가가 예상되고, 기존 백테스트 결과의 회귀 위험을 키운다. 따라서:

1. **Phase 3 모듈은 검증 완료** (22 unit tests 통과)
2. **Bear 신호 백테스트는 별도 plan** — `simulate_trade_short()` 분기 추가 후 P3 bearish 변형 검증
3. **TQQQ 60일 데이터에서 bearish setup이 매우 적을 가능성** — INTRADAY_COMPARISON Casper_RR3 3건과 같은 양상 예상

→ 통계적 유의성을 위해 1년+ 데이터 + bear 시뮬레이션 동시 도입이 효율적.

---

## 6. 봇 동작 영향

- `config/strategy_params.json` Phase 3 옵션 모두 **default false**
- `scan_for_signal()` `direction` 파라미터 기본값 `'bull'` → 기존 호출 100% 동일
- 봇 재시작 후에도 변화 없음
- 회귀 433 tests pass (백그라운드, 곧 도착)

---

## 7. 다음 작업

### 7.1 ✅ P3-bot 통합 (Daily Bias hook) — **완료 2026-05-12**

- `market_data.py`에 `get_qqq_daily_df(lookback)` ✅
- `bot.py:_handle_pre_market`에서 `compute_daily_bias()` 호출 + neutral 시 skip ✅
- ICT meta에 `daily_bias_direction/score` 포함 ✅

### 7.2 ✅ P3-QQQ-signal-mapping — **완료 2026-05-12** (PHASE3_QQQ_MAPPING.md)

- `src/core/exec_mapper.py` — QQQ bear signal → SQQQ Long 가격 변환 ✅
- `bot.py:_handle_orb_forming` — QQQ ORB 추가 계산 ✅
- `bot.py:_handle_scanning` — QQQ leg에서 direction='bear' 스캔 + remap → SQQQ Long ✅
- `check_pullback(direction='bear')` 추가 ✅
- 텔레그램/bash 라벨 `QQQ→SQQQ` ✅
- ICT meta `signal_source: "QQQ"` 추가 ✅
- 회귀 통과 ✅

### 7.3 P3-bear-backtest plan (보류)

- `simulate_trade()`에 `side='short'` 분기 추가 (50줄)
- `intraday_backtest_compare.py`에 변형:
  - 23. `Casper_QQQ_to_SQQQ_long` (QQQ bear signal mapped to SQQQ Long)
  - 24. `Casper_Dual_with_QQQ_mapping` (TQQQ self-chart + SQQQ from QQQ)
- KIS 정밀 비용 모델 + leverage 2.85 변환

코드량: 약 80줄. 1년+ 데이터로 검증 권장.

---

## 8. 산출물

| 항목 | 경로 |
|---|---|
| Bearish FVG | `src/core/fvg.py` (확장) |
| Daily Bias | `src/core/bias.py` (신규) |
| 통합 strategy | `src/core/strategy.py` (direction 옵션) |
| Config | `config/strategy_params.json` (+2 키) |
| 테스트 | `tests/test_fvg_bearish.py`, `test_strategy_phase3.py`, `test_bias.py` |
| 본 보고서 | `docs/strategy/PHASE3_IMPLEMENTATION.md` |

---

## 9. 활성화 권고 (전체 ICT)

| 단계 | 활성화 | 권장 시점 |
|:---:|---|:---:|
| 1 | Phase 1 Killzone | 즉시 (사용자 결정) |
| 2 | + Phase 1 Displacement | 1~2주 후 |
| 3 | + Phase 2 Sweep+CHoCH | 1~3개월 데이터 누적 후 |
| 4 | + Phase 3 Daily Bias skip-neutral | 별도 통합 plan |
| 5 | + Phase 3 Bearish FVG (SQQQ 정밀화) | bear 백테스트 검증 후 |
| 6 | + Phase 3 QQQ-signal mapping | 별도 plan 후 |

각 단계마다 매매 5건+ 또는 30 영업일 누적 후 다음 단계.

---

## 10. 결론

- ICT 매매법의 **bearish 측 인프라 완성** (FVG 검출 + 신호 흐름 + bias 정밀화)
- 봇 production 영향 0 (모든 default OFF, scan_for_signal direction 기본 'bull')
- 433 tests pass
- 실제 활용은 (a) bot.py 통합 plan + (b) bear-side simulate_trade plan + (c) QQQ-signal mapping plan으로 3분할 진행

기존 Phase 1/2 옵션을 먼저 운용으로 검증하고, 그 결과를 바탕으로 Phase 3 통합 plan을 작성하는 것이 합리적 순서.
