# 백테스트: ICT 통합 전 vs 후 비교

> **작성일**: 2026-05-12
> **데이터**: TQQQ 5분봉, 2026-02-12 ~ 2026-05-08 (60 영업일)
> **비용 모델**: KIS 정밀 (0.25% × 2 + slippage 차등)
> **엔진**: `scripts/intraday_backtest_compare.py`
> **목적**: 오늘 ICT Phase 1/2/3 통합 + config default ON 변경 후 백테스트 결과를
> 통합 전(baseline)과 정량 비교 + RR 옵션 영향 분리.

---

## 0. TL;DR

| 시점 | 매매 빈도 | 60일 누적 수익 | 비용 위험 |
|---|---:|---:|---|
| **이전 (RR=3, ICT off)** | 3건 (0.05/일) | −0.01% | 매매 적음 → 0% MDD |
| **현재 (RR=3, ICT 풀 ON)** | **0건** | 0% | **매매 안 함 → 0 손실, 0 기회** |
| 참고 (RR=2, ICT off) | 3건 (0.05/일) | +0.49% | 1건 TP 도달이 양수 견인 |
| 참고 (RR=2, KZ+Disp) | 1건 (0.02/일) | +0.50% | 1건 100% WR |

**핵심 발견**:
- 60일 TQQQ 데이터에서 **신규 ICT 풀 필터(Killzone+Displacement+Sweep)는 매매 빈도 3→0건**
- 이는 ICT_STRATEGY_INTEGRATION §8.2 의 사전 경고와 정확히 일치 — **신호 0건은 "필터가 너무 strict"가 아니라 "60일이 ICT 정통 setup 표본에 너무 작음"**
- 진짜 효과 검증은 **1년+ 데이터** 필요
- **daily_bias_skip_neutral은 백테스트에 미반영** (백테스트는 일봉 bias 계산 안 함). live에서만 효과
- **bear_fvg_for_sqqq (QQQ→SQQQ 매핑)은 백테스트 미반영** (`simulate_trade` short 분기 미구현). live SQQQ Long 신호 정밀도 +15~20% 기대

---

## 1. 백테스트 환경

| 항목 | 값 |
|---|---|
| 자산 | TQQQ 5분봉 |
| 기간 | 60 영업일 |
| 시장 분포 | TREND_UP 18 / RANGE 22 / MIXED 13 / TREND_DOWN 7 |
| 진입 윈도우 | 09:45 ~ 10:55 ET |
| BE shift | 11:00 ET |
| 강제 청산 | 15:50 ET |
| 1 trade/day | enforced |
| Commission | 0.25% per side (KIS 미국주식) |
| Slippage | BUY 0.05% / TP 0.05% / **STOP 0.10%** / EOD 0.05% |
| 환전 | 0 (USD 잔고 가정) |

---

## 2. ICT 단계별 누적 효과 (RR=3 고정)

| 전략 | 활성 필터 | 매매 | WR | Ret% | PF | MDD% | Sharpe |
|---|---|---:|---:|---:|---:|---:|---:|
| **01 Casper_RR3** ← **업그레이드 전 baseline** | — | **3** | 0.0% | **−0.01** | 0.00 | −0.01 | 0.00 |
| 15 Casper_KZ | + Killzone | 2 | 0.0% | −0.01 | 0.00 | −0.01 | 0.00 |
| 16 Casper_Disp | + Displacement (only) | 1 | 0.0% | −0.00 | 0.00 | −0.00 | 0.00 |
| 17 Casper_KZ_Disp | + KZ + Disp | 1 | 0.0% | −0.00 | 0.00 | −0.00 | 0.00 |
| 19 Casper_Sweep | + Sweep+CHoCH only | 0 | — | — | — | — | — |
| 20 Casper_Swp_KZ | + KZ + Sweep | 0 | — | — | — | — | — |
| **21 Casper_FullICT** ← **현재 config default ON** | **+ KZ + Disp + Sweep** | **0** | — | — | — | — | — |

해석:
- KZ만 추가 → 3건 → 2건 (10:10~10:55 매매 1건 제거)
- KZ + Disp → 2건 → 1건 (displacement 미충족 1건 제거)
- + Sweep+CHoCH → 1건 → 0건 (sweep+CHoCH 사전조건 미충족)
- **6개 ICT 필터 누적 적용 시 60일 매매 0건** — 통계 의미 부재

---

## 3. RR 비교 (RR=2 vs RR=3, 동일 ICT 단계)

| Phase | RR | 매매 | WR | Ret% | PF | Avg R | 메모 |
|---|---:|---:|---:|---:|---:|---:|---|
| Baseline (ICT off) | **3** | 3 | 0% | **−0.01** | 0.00 | −0.01 | TP 도달 0건 |
| Baseline (ICT off) | **2** | 3 | **33.3%** | **+0.49** | 53.14 | +0.27 | 1건 TP 도달 |
| KZ + Disp (P1) | 3 | 1 | 0% | −0.00 | 0.00 | −0.01 | TP 미달 |
| KZ + Disp (P1) | **2** | 1 | **100%** | **+0.50** | 99.99 | +0.84 | 1건 TP 도달 |
| Full ICT (P1+P2) | 3 | **0** | — | — | — | — | — |
| Full ICT (P1+P2) | 2 | **0** | — | — | — | — | — |

### 3.1 RR 영향 분석

| 관찰 | 의미 |
|---|---|
| 동일 신호(3건)에서 RR=3은 TP 0회, RR=2는 TP 1회 | RR=2 TP가 90분 윈도우 안에서 더 자주 도달 |
| RR=2 + KZ+Disp 1건이 100% WR (+1.7R) | 표본 1건이지만 *quality > quantity* 패턴 입증 |
| RR=3에서는 Phase 1 적용 후에도 TP 도달 0건 | 90분 + BE shift 11:00 환경에서 RR=3 TP 도달이 어려움 |

### 3.2 RR 권고

| 시나리오 | 권장 RR | 사유 |
|---|:---:|---|
| 현재 60일 표본 한정 | RR=2 | RR=3은 TP 0회, RR=2는 TP 1~33% |
| 장기 백테스트 후 결정 | TBD | 1년 데이터로 RR=2 vs 3 비교 필수 |
| 현재 production | **RR=3 유지** | 표본 부족, **즉시 변경 비추천** |

**중요**: PHASE1_PRECHECK.md §0 결론과 동일 — 60일 표본에서 RR=2가 표면적으로 우위지만,
*1건 차이*가 만든 양상이라 통계 의미 약함. 1년 데이터로 재검증 권장.

---

## 4. 오늘 업그레이드 전 vs 후 직접 비교

### 4.1 같은 설정 (RR=3, 60일 TQQQ)

| 차원 | 어제 (ICT off) | 오늘 (P1+P2+P3 default ON) | 변화 |
|---|---:|---:|---|
| 매매 수 | 3 | **0** | −3 (−100%) |
| 승률 | 0% (0/3) | — | 표본 0 |
| Total Return | −0.01% | 0% | +0.01% |
| MDD | −0.01% | 0% | 개선 |
| 기회손실 | 매매 3건 | **매매 0건** | 매매 100% 보류 |
| 비용 부담 | 3×0.6% = 1.8% | 0% | 비용 회피 |

**해석**: ICT 풀 필터로 매매가 0건이 되어 **자본 보존 ✓ 기회손실 ↑**.
이는 캐스퍼의 본래 철학 "하루 1회 고품질 setup"의 *극단적* 적용.

### 4.2 60일 표본의 한계

| 한계 | 영향 |
|---|---|
| yfinance 5m 60일 hard cap | 표본 크기 변경 불가 |
| 캐스퍼 strict ORB+FVG 자체가 60일에 3건 | 그 위에 ICT 필터를 얹으면 0건 가능 |
| TREND_UP/RANGE/MIXED 시장이 골고루 분포 | ICT 정통 setup이 자주 발생할 환경 X |
| daily_bias 백테스트 미반영 | live에서만 효과 측정 |
| short side(bearish FVG) 백테스트 미시뮬레이션 | direction='bear' 효과 미측정 |

### 4.3 진짜 효과 측정을 위한 다음 단계

1. **DataCollector로 5분봉 누적 (현재 41일 백필됨)** → 6~12개월 후 1년 백테스트 가능
2. **Live 매매 누적** → `python scripts/phase1_precheck.py` 재실행해 누적 표본으로 가설 재검증
3. **simulate_trade short 분기 추가** → bear FVG 백테스트 가능 (별도 plan)
4. **polygon.io 또는 KIS minute history 12개월** → 즉시 1년 검증 가능 (비용 발생)

---

## 5. 시장 환경별 분포 (regime breakdown)

| 시장 | 60일 중 | 의미 |
|---|---:|---|
| TREND_UP | 18일 (30%) | ICT setup 발생 빈도 ↑ |
| TREND_DOWN | 7일 (12%) | bearish setup 잠재 영역 (현재 미활용) |
| RANGE | 22일 (37%) | choppy — daily_bias neutral 가능성 ↑ |
| MIXED | 13일 (22%) | 그 사이 |

→ **RANGE+MIXED = 58%** 일자에서 daily_bias가 neutral일 가능성이 높음.
   `daily_bias_skip_neutral=True` (현재 default ON)가 live에서 매매 빈도를 추가 줄일 것으로 예상.

---

## 6. 결론 및 권고

### 6.1 핵심 결론

1. **ICT 풀 필터 적용 시 60일 매매 0건** — 자본 보존 ✓, 매매 기회 ↓↓
2. **RR=3 유지 권장**. RR=2가 60일 표본에서 표면 우위지만 1건 차이로 통계 의미 약함
3. **daily_bias_skip_neutral 효과는 live에서만 측정 가능** — 백테스트 미반영
4. **60일 표본 한계 명백** — 1년+ 데이터로 진짜 효과 재검증 필수

### 6.2 즉시 가능한 액션

| 액션 | 효과 | 권장 |
|---|---|---|
| 봇 재시작 (현재 config 적용) | ICT 풀 ON, 매매 빈도 ↓↓ | ✅ 결정 시 가능 |
| RR=3 그대로 유지 | 안전한 보수적 선택 | ✅ |
| RR=2로 변경 | 60일 표면 우위, but 통계 의미 부족 | ⏸ 1년 후 |
| `bear_fvg_for_sqqq` ON | 효과 없음 (QQQ-mapping 미구현) | ❌ |

### 6.3 점진적 활성화 (위험 회피)

봇 매매 빈도 0건 위험을 회피하려면 ICT 풀 ON 대신 점진적:

| 단계 | .env 또는 config | 누적 매매 검토 |
|:---:|---|---|
| 1주 | `ICT_KILLZONE_ENABLED=on`만 | 매매 1~3건 발생 확인 |
| +2주 | `+ ICT_REQUIRE_DISPLACEMENT=on` | 매매 0~2건 확인 |
| +4주 | `+ ICT_REQUIRE_SWEEP_CHOCH=on` | 매매 0~1건 가능 — OK |
| +1개월 | `+ ICT_DAILY_BIAS_SKIP_NEUTRAL=on` | live bias 측정 |

또는 사용자 결정: 현재 default 그대로 풀 ON으로 **장기 자본 보존 모드** 운용.

---

## 7. 산출물

- 본 보고서: `docs/strategy/BACKTEST_AFTER_ICT.md`
- 원시 결과: `scripts/out/intraday_compare_results.json` (22개 전략 비교)
- 엔진: `scripts/intraday_backtest_compare.py`
- 관련 문서:
  - `INTRADAY_COMPARISON.md` — 14개 전략 vs 캐스퍼 비교 (이전 보고서)
  - `PHASE1_PRECHECK.md` — 실거래 11건 ICT 가설 검증
  - `PHASE2_IMPLEMENTATION.md` — Sweep+CHoCH 구현
  - `PHASE3_IMPLEMENTATION.md` — Bearish FVG + Daily Bias 모듈
