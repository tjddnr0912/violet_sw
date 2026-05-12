# ICT Phase 2 Implementation — Liquidity Sweep + CHoCH

> **작성일**: 2026-05-12  •  **선행 문서**: ICT_STRATEGY_INTEGRATION.md, PHASE1_PRECHECK.md
> **상태**: 코드 완성, 봇 default OFF로 통합. 60일 표본에서 0건 (예상됨, 1년+ 검증 필요).

---

## 1. 구현 범위 (요약)

ICT_STRATEGY_INTEGRATION.md §5 Phase 2의 핵심 3축 중 2개를 구현:

| ICT 개념 | 구현 모듈 | 테스트 |
|---|---|:---:|
| Swing point fractal (2-1-2) + EQH/EQL | `src/core/swing.py` | 10 ✅ |
| Liquidity Sweep (pin bar wick breach + close back inside) | `src/core/liquidity.py` `is_sweep_bar()`, `detect_recent_sweep()` | 10 ✅ |
| CHoCH (Change of Character — close past prior swing) | `src/core/liquidity.py` `detect_choch()` | 3 ✅ |
| Composite: Sweep → CHoCH bullish gate | `src/core/liquidity.py` `sweep_then_choch()` | 2 ✅ |
| `scan_for_signal` 통합 (`require_sweep_choch` 옵션) | `src/core/strategy.py` | 3 ✅ |

**테스트**: 신규 28개 (Phase 2 + 통합) 모두 통과. 기존 383 + 28 = **411 tests, 회귀 0**.

---

## 2. 알고리즘 정의 (코드 직역)

### 2.1 Swing Point (5-bar fractal)

```python
swing_high = bars[i].High is the maximum across [i-2..i+2]
  - strict on left: > all of [i-2, i-1]
  - non-strict on right: ≥ all of [i+1, i+2]  (plateau-safe)
```

좌우 비대칭(left strict / right non-strict)은 동일 가격이 연속될 때 *최초* 봉만 swing으로 표시 → 중복 제거.

### 2.2 Liquidity Sweep (pin bar 형태)

```python
side='up' (BSL sweep):
  bar.High - level >= level * 0.05%        # breach 0.05% 이상
  bar.Close < level                        # close back inside
  wick_ratio = (bar.High - max(open, close)) / (bar.High - bar.Low) >= 60%

side='down' (SSL sweep):
  level - bar.Low >= level * 0.05%
  bar.Close > level
  wick_ratio = (min(open, close) - bar.Low) / (bar.High - bar.Low) >= 60%
```

ICT 002 영상 timestamp 매핑:
- "0.05% 이상 breach" → ICT 표준
- "close back inside" → 단순 BOS와 sweep을 구분하는 결정적 조건
- "wick ratio ≥ 60%" → pin bar 정의

### 2.3 CHoCH (Change of Character)

```python
direction='bull' (reversal from down to up):
  bar.Close > price_of(last_swing_high_before(bar.timestamp))

direction='bear' (reversal from up to down):
  bar.Close < price_of(last_swing_low_before(bar.timestamp))
```

종가 기준 — 꼬리 돌파만으로는 CHoCH로 인정 안 함 (Casper SMC 005 timestamp 20:15).

### 2.4 Composite 트리거 (Bullish setup)

```python
sweep_then_choch(direction='bull'):
  1) recent SSL sweep        (price wicked below level, closed back above)
  2) within next N bars: CHoCH close above prior swing high

순서가 핵심 — sweep 먼저, CHoCH 나중.
```

---

## 3. `scan_for_signal` 통합 흐름

```
ORB 형성
  ↓ 09:45+ scan window
브레이크아웃 후보 봉 (close > ORB high + bullish)
  ↓
strict FVG (FVG ∩ ORB line)                  [기존]
  ↓
Killzone 필터  (Phase 1)                      [optional, default OFF]
  ↓
Displacement 필터  (Phase 1)                  [optional, default OFF]
  ↓
Sweep + CHoCH 게이트  (Phase 2, NEW)          [optional, default OFF]
  ↓
FVG mid 진입가 / 직전 봉 저점 SL / RR TP
  ↓
pullback 대기 → 진입
```

각 gate는 독립 토글이며 AND 조건. Phase 2 게이트만 켜고 Phase 1을 끄면 sweep 후 ORB+FVG strict 매매. 모두 켜면 full ICT stack.

---

## 4. Config 추가

`config/strategy_params.json` → `entry` 섹션:

| 키 | 기본값 | 의미 |
|---|---|---|
| `require_sweep_choch` | `false` | Phase 2 게이트 활성화 |
| `sweep_lookback` | 6 | sweep 검색 bar 수 (직전 ~30분) |
| `choch_lookback` | 6 | sweep 후 CHoCH 검색 bar 수 |
| `sweep_min_breach_pct` | 0.0005 | sweep wick의 최소 breach 비율 |
| `sweep_min_wick_ratio` | 0.60 | pin bar 임계값 |

**default OFF로 봇 구동 영향 0**. Phase 1과 동일 운영 모델.

---

## 5. 60일 백테스트 결과

### 5.1 결과표 (KIS 정밀 비용 모델, TQQQ 5m, 2026-02-12 ~ 2026-05-08)

| 전략 | 매매 | WR | Ret | PF | MDD |
|---|---:|---:|---:|---:|---:|
| 01 Casper_RR3 (baseline) | 3 | 0% | −0.01% | 0.00 | −0.01% |
| 02 Casper_RR2 | 3 | 33.3% | +0.49% | 53.14 | −0.01% |
| 15 Casper_KZ | 2 | 0% | −0.01% | 0.00 | −0.01% |
| 16 Casper_Disp | 1 | 0% | −0.00% | 0.00 | −0.00% |
| 17 Casper_KZ_Disp | 1 | 0% | −0.00% | 0.00 | −0.00% |
| 18 Casper_RR2_KZ_Disp | 1 | 100% | +0.50% | 99.99 | 0% |
| **19 Casper_Sweep** | **0** | — | — | — | — |
| **20 Casper_Sweep_KZ** | **0** | — | — | — | — |
| **21 Casper_FullICT (P1+P2)** | **0** | — | — | — | — |
| **22 Casper_RR2_FullICT** | **0** | — | — | — | — |

### 5.2 해석

- Phase 2 4종 모두 **60일 표본에서 매매 0건**
- 캐스퍼 baseline조차 3건뿐인 환경에서 sweep+CHoCH 사전조건이 추가되면 거의 0이 되는 것은 *예상된 결과*
- ICT_STRATEGY_INTEGRATION.md §8.2 "추가 복잡도가 가져오는 over-fitting" 경고 그대로
- 60일 표본의 통계적 의미는 약함 — Phase 2 진짜 효과는 **1년+ 데이터로 측정해야 가능**

### 5.3 표본 부족의 의미

- 기존 strict ORB+FVG 자체가 60일에 3건만 발생 → ICT 추가 게이트 = 추가 필터링
- 캐스퍼 철학 "하루 1회 고품질 setup"과 일치 — 분기 단위에서 10~20건만 발생하는 정통 ICT setup
- 사용자 호소(추세 일변도장에서 매매 못 함)의 진짜 해결책은 *추가 진입 빈도*가 아니라 *기존 매매 품질 검증* 임

---

## 6. 봇 동작 영향

- `config/strategy_params.json` Phase 2 옵션 모두 **default false**
- 봇 다음 재시작 후에도 100% 기존 동작 (회귀 테스트 411 passed로 확인)
- 활성화하려면 `require_sweep_choch: true` 토글 후 재시작
- DataCollector 패턴과 동일한 점진적 도입 모델

---

## 7. 활성화 권고 순서

PHASE1_PRECHECK §7 권고와 결합:

| 단계 | 활성화 항목 | 운용 기간 | 검증 지표 |
|:---:|---|:---:|---|
| 1 | `killzone_filter_enabled: true` | 1~2주 | WR, 매매 수 |
| 2 | `+ require_displacement: true` | 추가 2~4주 | PF, AvgR |
| 3 | `+ require_sweep_choch: true` | 추가 4~8주 | 매매 0건 가능 — 그래도 손실 안 보면 OK |

각 단계마다 매매 5건 이상 누적 후 다음 단계.
누적 매매를 `phase1_precheck.py` (Phase 2 sweep 추가는 별도 스크립트 가능)로 점검.

---

## 8. 한계 / 미해결 항목

### 8.1 현재 구현의 한계

- **sweep 검출은 ORB low / 최근 swing low만** 사용. PDH/PDL/PWH/PWL은 미포함.
  → 다음 phase에서 일봉 데이터 연결 후 확장 가능.
- **CHoCH는 단일 swing high 기준만**. ICT 정통은 *Inducement* 같은 추가 패턴 있음.
- **EQH/EQL**은 모듈에 함수만 추가, sweep 로직에 미사용. 향후 강력한 풀 식별용으로 결합 가능.

### 8.2 Phase 3 후보 (별도 plan 필요)

- QQQ를 신호 추출용으로 분리 (TQQQ/SQQQ는 실행 전용)
- Bearish FVG 활성화 → SQQQ 신호 정밀화
- Daily Bias 정밀화 (PDH/PDL sweep + midnight open premium/discount)
- yfinance NQ=F 24h 데이터로 Power of 3 (AMD) 구현

---

## 9. 산출물

| 항목 | 경로 |
|---|---|
| Swing 모듈 | `src/core/swing.py` |
| Liquidity 모듈 | `src/core/liquidity.py` |
| 통합 strategy | `src/core/strategy.py` (수정) |
| Config | `config/strategy_params.json` (5개 키 추가) |
| 백테스트 변형 | `scripts/intraday_backtest_compare.py` (#19~#22) |
| 테스트 | `tests/test_swing.py`, `test_liquidity.py`, `test_strategy_phase2.py` |
| 본 보고서 | `docs/strategy/PHASE2_IMPLEMENTATION.md` |

---

## 10. 다음 액션 (사용자 결정)

1. **Phase 1 활성화 우선** — 60일 표본은 Phase 2 직접 활성화하기에 부족.
   `killzone_filter_enabled: true`만 먼저 켜고 한 달 운용.
2. **데이터 누적** — 매주 DataCollector가 5분봉 수집 → 6개월 후 1년 백테스트 가능.
3. **Phase 2 활성화는 1년 데이터 확보 후** — 통계적 유의성 확보가 우선.
4. **Phase 3 plan 작성** — QQQ 신호 분리 + Bearish FVG는 코드 변경 비교적 가벼움. 별도 plan으로 진행 가능.
