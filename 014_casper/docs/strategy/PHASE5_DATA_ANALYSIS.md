# Phase 5.0 — Range Expansion 데이터 분석 결과

> **작성일**: 2026-05-15
> **목적**: Phase 5 (Range Expansion 필터) 도입 결정에 필요한 데이터 검증. 기존 18건 매매(라이브 11 + 60일 백테스트 7)의 진입 시점에 1H/4H expansion 정렬 여부 측정.
> **결론**: **표본 부족** + **counter-direction 일부 발견** → **Phase 5는 보류**. 6개월+ 데이터 누적 후 재검토 권장.

---

## 1. 방법론

### 1.1 데이터

- **HTF 데이터**: QQQ 1H bars (420개 = ~60 RTH 일), QQQ 4H bars (120개 = ~30 RTH 일) — yfinance 60d
- **매매 18건**:
  - 라이브 11건 (`data/trades/trades_2026.json`, 2026-04-06 ~ 2026-05-06)
  - 60일 백테스트 5분봉 재실행 → 7건 추가 후보 (2026-02-24 ~ 2026-05-13)

### 1.2 Expansion 정의 (ICT Mastery Course 재구성)

```
candle = HTF bar (1H or 4H)
prev_window = candle 직전 range_period 개 봉의 Close 시계열

조건 (3개 동시 충족):
  body > range_size × 1.5     # range_size = max(prev.Close) - min(prev.Close)
  body > avg_body × 2.0       # avg_body = prev_window의 평균 |Close-Open|
  wick_ratio < 0.40           # wick = (H-L - body) / (H-L)

direction:
  bull if Close > Open
  bear if Close < Open
```

각 trade의 entry time에 대해 1H/4H windows를 backward scan — 가장 *최근* expansion candle을 찾음. lookback:
- 1H: 직전 40개 봉 (~6 RTH 일)
- 4H: 직전 30개 봉 (~15 RTH 일)

### 1.3 Alignment 분류

| 분류 | 의미 |
|---|---|
| **aligned** | expansion 방향 = trade 방향 (둘 다 bull 또는 둘 다 bear) |
| **misaligned** | expansion 방향 ≠ trade 방향 (counter direction) |
| **no_expansion** | 윈도우 안에 expansion 자체가 없음 |

---

## 2. 결과

```
Source     Date         Sym   Dir   Entry                  1H exp       1H aln  4H exp       4H aln
─────────────────────────────────────────────────────────────────────────────────────────────────
live       2026-04-07   SQQQ  bull  10:00 ET               —            —       —            —
live       2026-04-06   TQQQ  bull  09:50                   —            —       —            —
live       2026-04-14   TQQQ  bull  10:10                   —            —       —            —
live       2026-04-15   TQQQ  bull  10:00                   —            —       —            —
live       2026-04-17   TQQQ  bull  10:05                   —            —       —            —
live       2026-04-21   TQQQ  bull  10:00                   —            —       —            —
live       2026-04-24   TQQQ  bull  10:50                   —            —       —            —
live       2026-05-01   TQQQ  bull  10:00                   bear         ✗       —            —
live       2026-05-04   TQQQ  bull  10:45                   bear         ✗       —            —
live       2026-05-05   TQQQ  bull  10:25                   bear         ✗       —            —
live       2026-05-06   TQQQ  bull  10:35                   bear         ✗       —            —
backtest   2026-02-24   TQQQ  bull  10:20                   —            —       —            —
backtest   2026-02-27   TQQQ  bull  10:00                   —            —       —            —
backtest   2026-03-09   TQQQ  bull  10:40                   —            —       —            —
backtest   2026-04-02   TQQQ  bull  09:50                   —            —       —            —
backtest   2026-04-23   TQQQ  bull  10:50                   —            —       —            —
backtest   2026-04-29   TQQQ  bull  09:50                   —            —       —            —
backtest   2026-05-13   TQQQ  bull  10:50                   —            —       —            —
```

### 2.1 집계

| 측정 | 1H | 4H |
|---|---:|---:|
| 총 매매 | 18 | 18 |
| Expansion 발견 | **4** | **0** |
| Aligned | 0 | — |
| Misaligned | 4 | — |
| No-expansion | 14 | 18 |
| Alignment rate | **0% (0/4)** | **N/A (0/0)** |

---

## 3. 해석

### 3.1 표본 크기 문제

- **4H expansion = 0건** (60일 데이터). 4H 캔들이 *최근 8봉의 close range × 1.5*보다 큰 body를 만드는 경우가 60일 동안 발생하지 않음. 기준이 매우 빡빡하다는 신호.
- **1H expansion = 4건** (18건 중). 표본 너무 작아 통계 추론 불가.
- 14건 매매(78%)는 **expansion 자체가 prior 6일 RTH에 없는 상태에서 진입** — 즉 Range Expansion 필터를 적용했다면 매매 자체가 일어나지 않거나 무관.

### 3.2 발견된 4건의 counter-correlation

흥미로운 패턴:
- 2026-05-01, 05-04, 05-05, 05-06 — **연속 4영업일** 모두 1H bear expansion 발생
- 그 시점 모든 캐스퍼 매매는 **bull** (TQQQ Long)
- 즉 **0% alignment, 100% misaligned**

이건 두 가지로 해석 가능:

**해석 A (가설 검증 — 캐스퍼 마케팅과 반대)**:
> Range Expansion alignment가 *작동하지 않음*. 1H bear에서 bull setup이 발생했고 실제 거래됨 — counter signal.

**해석 B (정통 ICT 재해석)**:
> Bear expansion 후 reversal 진입 = ICT의 *"sweep + CHoCH"* 패턴 정확히 그것. Casper SMC는 *"expansion follow"* 가 아니라 *"expansion exhaustion → reversal"* 을 가르치는 게 옳음. 4건은 그 reversal setup의 정상 작동 사례.

**해석 B를 지지하는 정황**:
- 같은 4건의 라이브 결과: 2026-05-01 LOSS, 05-04 LOSS, 05-05 BE, 05-06 BE — *모두 reversal trade가 실패*. 즉 expansion *수반* 진입은 LOSS/BE만 발생, 정렬은 의미 없음.
- PHASE1_PRECHECK의 결과(전체 11건 WR 54.5%) vs 이 4건의 *0% WR* — counter-direction 매매가 실제로 더 약했다는 *간접적 증거*.

→ **두 해석 모두 표본 4건으로는 결정 불가**.

### 3.3 임계값 sensitivity 검토 (별도 실험 안 함, 가설만)

만약 expansion 임계값을 완화 (body > range × 1.0, avg × 1.5):
- 추가 expansion 건수 추정: 1H 10~15건, 4H 3~5건
- 그래도 18건 매매 중 절반 이상은 여전히 expansion 매칭
- 임계값을 어디까지 낮춰야 *의미 있는 신호*가 나오는지는 ad-hoc 결정 — PRECHECK과 같은 함정

---

## 4. Phase 5 진행 여부 결정

### 4.1 진행 *반대* 근거 (이번 데이터 기반)

1. **4H expansion 0건** — 60일에 단 한 번도 4H 큰 body가 발생 안 함. 4H 필터는 *항상 reject* 결과.
2. **1H expansion 4건 / 18건** — 표본 22%만 expansion 동반. 78%는 무관.
3. **4건 모두 misaligned (0% alignment)** — alignment 가설은 *반증* 또는 *재해석 필요*.
4. **표본 4건은 통계적으로 무의미** — 6개월+ 매매 데이터 누적 필요.
5. **임계값 자의성** — body × range × wick의 정확한 임계값을 PHASE1_PRECHECK처럼 작은 표본으로 정하면 *함정*.

### 4.2 진행 *찬성* 근거

1. **misaligned 4건 모두 LOSS/BE** — 해석 B(counter-direction reversal trade는 실패)가 사실이면 *Phase 5는 도움이 될 것*.
2. 캐스퍼 ICT Mastery Course의 3개 핵심 모듈 중 하나 — 원본 학습 가치는 보존.

### 4.3 결정

→ **Phase 5는 보류**. 다음 트리거 충족 시 재검토:

| 트리거 | 임계값 |
|---|---|
| 라이브 매매 누적 | **≥ 30건** (현재 11건) — 통계 신뢰성 위한 최소선 |
| 표본 기간 | **≥ 6개월** (현재 ~5주) — 다양한 시장 regime 포함 |
| 임계값 sensitivity 사전 분석 | 별도 실험 — body/range, body/avg, wick 임계값을 0.5~2.5 범위에서 ablation |
| 1년+ HTF 데이터 가능 | yfinance 4H = 730일 가용 → 진정한 1년 백테스트 가능 |

### 4.4 보류된 작업 (참조)

- `src/core/range_expansion.py` (모듈)
- `scan_for_signal::require_range_expansion` (게이트)
- HTF data fetch 통합 (`src/data/market_data.py`)
- ICT decision log `range_expansion` 이벤트
- paper 모드 검증
- 예상 코드 변경 ~150~250 lines

---

## 5. 보조 발견 — Counter-Direction 패턴

데이터에서 가장 흥미로운 결과: **2026-05-01 ~ 05-06 4영업일 연속 1H bear expansion 발생 + 미장봇이 모두 bull 매매**.

이 기간 봇의 매매 결과:
| 날짜 | result | r_mult |
|---|---|---|
| 2026-05-01 | LOSS | -1.67 |
| 2026-05-04 | LOSS | -0.00 |
| 2026-05-05 | BE | +0.01 |
| 2026-05-06 | BE | -0.00 |

→ **모두 미달성**. PHASE1_PRECHECK의 -0.49R 평균(11건 중 후반 4건)이 이 시기에 집중.

**향후 운용 시사점**:
- 1H bear expansion이 *최근 발생*했고 캐스퍼 setup이 *bull*이라면 → 매매 *경계*. 단 정량 임계값은 데이터 더 필요.
- 반대 시나리오(1H bull expansion + bear setup)도 동일 가설로 적용 가능.

이 패턴은 **Phase 5 본격 도입 전이라도** ict_decisions JSONL에 추가 정보로 적재할 가치 있음 (별도 작업).

---

## 6. 산출물

- `scripts/range_expansion_data_analysis.py` — 재실행 가능 분석 스크립트
- `scripts/out/range_expansion_analysis.csv` (18행 raw)
- `scripts/out/range_expansion_analysis.json` (summary + per-trade)

매월 1회 재실행 권장 — 라이브 매매가 누적되면 자연스럽게 표본 ↑.

---

## 7. 다음 액션

1. **Phase 5.1 (모듈 빌드) 보류** — 트리거 충족 전 미진행
2. **라이브 ict_decisions에 HTF expansion 정보 적재** (선택) — Phase 5 본격 도입 전 *암묵적 데이터 수집*. 별도 plan으로 분리
3. **6개월 후 재분석 예약** — 라이브 매매 ≥30건 + 백테스트 1년 데이터 확보 시점

Phase 5는 *기술적으로 빌드 준비됐지만 정량 정당화 부족*. 시간이 데이터를 만들기를 기다리는 게 옳음.
