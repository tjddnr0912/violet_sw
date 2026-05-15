# Intraday Strategy Comparison — Casper vs 12 Alternatives

**작성일**: 2026-05-09 (KIS 정밀 비용 모델 반영)
**백테스트 기간**: 2026-02-12 ~ 2026-05-08 (60 trading days)
**자산**: TQQQ 5분봉 (yfinance, period=60d)  •  **베이스라인**: Casper ORB+FVG strict, RR=3
**원시 데이터**: `scripts/out/intraday_compare_results.json`
**엔진**: `scripts/intraday_backtest_compare.py`

---

## 0. KIS 미국주식 거래비용 모델 (정밀)

이번 백테스트는 **모든 전략에 동일한 KIS 실비용 모델**을 적용했다.
초기 분석에서 사용한 단순 0.02% slippage 가정은 **너무 낙관적**이라
재계산 결과 결과가 크게 달라졌다.

### 0.1 비용 항목 (per trade)

| 항목 | 값 | 적용 시점 | 출처 |
|------|----|----------|------|
| **거래수수료 (Brokerage)** | **0.25%** per side | 매수·매도 모두 | KIS 온라인 미국주식 ([truefriend.com 2026-05](https://www.truefriend.com/main/customer/guide/_static/TF04ae010000.shtm)) |
| 매수 슬리피지 | 0.05% | 진입 fill | TQQQ 평균 1bp~10bp |
| 매도 슬리피지 (TP / limit) | 0.05% | 익절 | limit 우호적 fill |
| **매도 슬리피지 (SL / 시장가)** | **0.10%** | 손절 | stop trigger → market |
| 매도 슬리피지 (15:50 강제청산) | 0.05% | EOD | limit 가정 |
| SEC fee (매도) | $0.0000278 / $ of sale | 매도 | SEC 2026 fee schedule |
| FINRA TAF (매도) | $0.000166 / share | 매도 | FINRA 2025 update |
| 환전 수수료 | 0 | 미적용 | USD 잔고 내 매매 가정 |

### 0.2 트레이드 1건당 실효 비용 (round-trip)

```
TQQQ $80, 18주 매매(=$1,440 자본 투입) 가정:

매수:  brokerage 80 × 18 × 0.25% = $3.60
매수:  slippage  80 × 18 × 0.05% = $0.72
매도:  brokerage 80 × 18 × 0.25% = $3.60
매도:  slippage  80 × 18 × 0.05~0.10% = $0.72~$1.44
SEC:   80 × 18 × 0.0000278 = $0.04
TAF:   18 × 0.000166 = $0.003
─────────────────────────────────
TP 청산 합계:  $8.66 (= 0.60% of position)
SL 청산 합계:  $9.38 (= 0.65% of position)
EOD 청산 합계: $8.66 (= 0.60% of position)
```

→ **R:R 1:2 전략은 win 시 +2R, lose 시 -1R로 가정하지만,
실제로는 win=+2R−0.6%·win_rate, lose=−1R−0.65%·lose_rate**.
WR 50% 가정 시 비용만으로 자본 대비 **0.625% 잠식 per trade**.
30 trades/2개월이면 **자본의 18%가 비용으로 사라짐**.

### 0.3 BE shift 시 손익분기 가격

```python
be_price = entry × (1 + brokerage_round_trip + slip_buy + slip_tp)
        = entry × (1 + 0.005 + 0.0005 + 0.0005)
        = entry × 1.006   # 0.6% above entry
```

11:00 BE shift 후 stop을 entry*1.006로 올림. 0.6% 미만 수익 시점에서는
"BE stop"이 발동되지 않고 일반 손절가 그대로.

---

## 1. Why this study (起)

미장봇은 09:30~10:55 ET에만 진입 신호를 찾는 90분 데이트레이딩 봇이다.
시그널 조건이 **strict**: ORB(15m) 상단 돌파 + FVG가 ORB 라인을 가로질러야 함 + 되돌림 진입.
최근 시장이 **추세 일변도** 장세로 흐르면서 ORB 상단을 깬 뒤 FVG 형성 없이 그대로 상승,
미장봇이 진입 자체를 못하는 일이 잦았다.

이 보고서는 다음을 검증한다.
1. 정말로 미장봇이 신호를 못 잡고 있는가? (정량 측정)
2. quant·기관·개인 트레이더가 쓰는 13개 대안 일중 기법은 어떤 결과를 내는가?
3. **KIS 0.25% per side 비용을 반영했을 때** 어느 기법이 살아남는가?

---

## 2. Strategies surveyed (承)

각 카테고리별 5차원(정의·현황·근거·반론·적용)을 채운 핵심 정리는 아래 표 참고.
각 기법의 진입/청산/리스크 규칙은 `scripts/intraday_backtest_compare.py`의 `strat_*` 함수에 그대로 코딩되어 있어 재현 가능하다.

### 2.1 Trend-following

| 기법 | 진입 핵심 | 청산 | 시장 적합 | 근거 |
|------|-----------|------|-----------|------|
| **VWAP Pullback** | 09:45 이후 VWAP 상회 후 첫 pullback에서 종가가 다시 VWAP 상단 회복 | SL = VWAP×0.997, RR 1:2 | Strong trend | Brian Shannon AVWAP, QuantConnect 2025 |
| **EMA 9/21 Cross** | post-ORB EMA9 상향돌파 EMA21, RSI(14)≥50 | SL = EMA21 / 최근 3봉 저, RR 1:2 | Trend only, 횡보 약함 | TradingView Public Backtest 2024 |
| **MACD-Fast (5/34/5)** | MACD>0 + Signal 상향 + 히스토그램 3봉 확장 | SL = 최근 4봉 저, RR 1:2 | Volatile trend | Bill Williams 응용, MQTSJ 2025 |
| **Holy Grail (Linda Raschke)** | ADX(14)≥25 + EMA20 pullback bounce + 직전봉 고가 돌파 | SL = 최근 4봉 저, RR 1:2 | **Strongly trending only** | Raschke "Street Smarts", LBR Group 2024 |

### 2.2 Mean-reversion

| 기법 | 진입 핵심 | 청산 | 시장 적합 | 근거 |
|------|-----------|------|-----------|------|
| **Connors RSI-2** | post-ORB Close > EMA200 + RSI(2) < 10 | SL = -1.5×ATR, RR 1:1.5 | 추세 내 일시 조정 | Connors&Alvarez 2009, QuantPedia 2025 |
| **BB Reentry** | BB(20,2) 하단 종가 이탈 후 다시 하단 위 회복 | TP = MB(20-MA), RR ~1:1 | **Range only** | Bollinger Bands 표준 |
| **ORB Fade (false-breakdown)** | ORB low 하향 이탈 후 다시 ORB low 상회 | TP = ORB middle, RR 1:1.5 | "Stop hunt" 회수 | John Carter "Mastering the Trade" |
| **Z-Score Reversion** | 5분 종가 기준 rolling 20-bar z-score < -2 | TP = 평균(20-MA), 1.2% hard stop | Range, 정규분포 가정 | Statistical arbitrage 표준 |

### 2.3 Breakout 변형

| 기법 | 진입 핵심 | 청산 | 시장 적합 | 근거 |
|------|-----------|------|-----------|------|
| **NR7 (Crabel)** | 직전일이 지난 7거래일 중 일봉 range 최소 → 당일 시가 + 0.30·ATR 돌파 | SL = 시가 - 0.30·ATR, RR 1:2 | 변동성 압축 직후 | Crabel 1990, Quantified Strategies 2025 |
| **IB-60 Breakout** | 09:30~10:30 IB high를 10:30~10:55 사이에 종가 돌파 | SL = IB middle, TP = IB×100% extension | 갭 채우고 강세 | tradingstats.net (ES/NQ 2015~2025): IB 단일 break 67.97%, IB high 76.8%(YM), C-period(10:30~11:00) 60% 첫 돌파 |
| **Vol-Targeted EMA20** | EMA20 종가 돌파 + ATR(14) sized stop (1.5×ATR) | RR 1:2 | 변동성 expansion | Crabel acceleration concept |
| **Intraday Momentum** | 09:30~09:44 ret > +0.5% → 09:45 시가 진입 | SL = 09:30~09:44 최저, RR 1:2 | Gap-and-go | Carver SST · SSRN intraday momentum |

### 2.4 Quant 통계 (filter / sizing 결합)

- TQQQ/SQQQ pair: 인버스 ETF는 long-leg 둘 다 양수 → pair는 오히려 decay 누적, 일중 무의미. 단독 시그널 X.
- Vol-targeted sizing: ATR 기반 (위 EMA20에 결합)
- GARCH(1,1) intraday vol gating: VIX·realized vol gate
- Stat-arb on TQQQ vs 3×QQQ implied: 일중 dislocation 1bp → retail 거래비용에 못 이김

→ **Quant 카테고리는 단독 시그널이 아니라 filter/sizing으로 결합**. 본 백테스트 `14_VT_EMA20`이 vol-targeting + EMA cross.

### 2.5 레버리지 ETF 적용 시 공통 주의사항

- **Volatility decay**: TQQQ는 인트라데이 한정에서 거의 정확히 3×QQQ 추종. EOD 강제청산이 들어간 캐스퍼는 decay 안전.
- **Mean-reversion은 추세장에서 walking-the-bands**: ADX/EMA200 추세 필터 없으면 손절 누적.
- **NR7 fakeout**: 변동성 압축 후 돌파는 한 방향만 진짜. ATR 폭 작은 NR7일수록 fakeout 비율 ~40%.

---

## 3. Backtest results (轉)

### 3.1 시장 환경 분포 (60일 분류)

| 상태 | 정의 | 일수 |
|------|------|------|
| TREND_UP | body/range > 0.6 + 양봉 / 또는 range>4% | **18일 (30%)** |
| RANGE | body/range < 0.30 | **22일 (37%)** |
| MIXED | 그 사이 | 13일 (22%) |
| TREND_DOWN | body/range > 0.6 + 음봉 | 7일 (12%) |

→ 추세 일변도일이 25일(42%), 박스권 22일(37%). 사용자 호소대로 캐스퍼가 신호를 못 잡는 환경.

### 3.2 통합 비교표 (KIS 정밀 비용 모델)

| 전략 | 매매 | Tr/d | WR% | Ret% | PF | AvgR | MDD% | Sharpe | Sortino | Hold(분) |
|------|----:|----:|----:|----:|----:|----:|----:|----:|----:|----:|
| **01 Casper-RR3 (production)** | **3** | 0.05 | 0.0 | **−0.01** | 0.00 | −0.01 | −0.01 | 0.00 | 0.00 | 21.7 |
| **02 Casper-RR2** | **3** | 0.05 | **33.3** | **+0.49** | 53.14 | +0.27 | −0.01 | 10.83 | 0.00 | 11.7 |
| 03 VWAP Pullback | 22 | 0.37 | 27.3 | **−12.71** | 0.08 | −1.04 | −13.36 | −13.48 | −20.51 | 14.1 |
| 04 EMA 9/21 | 7 | 0.12 | 14.3 | −3.98 | 0.08 | −0.65 | −3.98 | −10.57 | −11.99 | 30.0 |
| 05 MACD Fast | 9 | 0.15 | 0.0 | −0.04 | 0.00 | −0.01 | −0.04 | −29.70 | 0.00 | 28.3 |
| **06 Holy Grail** | **36** | **0.60** | 13.9 | **−2.46** | 0.80 | −0.20 | −4.99 | −3.45 | −3.73 | 75.1 |
| 07 RSI-2 | 7 | 0.12 | 14.3 | −3.60 | 0.22 | −0.59 | −3.60 | −9.42 | −11.32 | 28.6 |
| 08 BB Reentry | 0 | — | — | — | — | — | — | — | — | — |
| 09 ORB Fade | 17 | 0.28 | 35.3 | **−16.30** | 0.00 | −1.25 | −16.30 | −25.58 | −25.58 | 6.8 |
| 10 Z-Score | 0 | — | — | — | — | — | — | — | — | — |
| 11 NR7 Breakout | 4 | 0.07 | 0.0 | −6.02 | 0.00 | −0.62 | −6.02 | −15.84 | −165.36 | 70.0 |
| 12 IB-60 Breakout | 20 | 0.33 | 0.0 | −2.87 | 0.00 | −0.06 | −2.87 | −3.70 | −1.72 | 24.2 |
| 13 Momentum | 16 | 0.27 | 12.5 | −5.97 | 0.33 | −0.36 | −7.84 | −6.47 | −38.29 | 92.2 |
| 14 Vol-Targeted EMA20 | 16 | 0.27 | 0.0 | −0.07 | 0.00 | −0.00 | −0.07 | −15.87 | 0.00 | 15.9 |

### 3.3 비용 모델 차이가 결과에 미친 영향

| 전략 | Ret% (낙관 0.02% slip) | Ret% (KIS 정밀) | 차이 | 거래 수 | 비용/거래 효과 |
|------|----:|----:|----:|----:|----:|
| 01 Casper-RR3 | +0.05 | −0.01 | -0.06 | 3 | -0.02%/trade |
| 02 Casper-RR2 | +0.59 | +0.49 | -0.10 | 3 | -0.03%/trade |
| 03 VWAP Pullback | −11.06 | **−12.71** | -1.65 | 22 | -0.075%/trade |
| 06 **Holy Grail** | **+2.51** | **−2.46** | **-4.97** | 36 | -0.14%/trade |
| 09 ORB Fade | −14.97 | −16.30 | -1.33 | 17 | -0.078%/trade |
| 14 VT-EMA20 | +1.53 | −0.07 | -1.60 | 16 | -0.10%/trade |

→ **거래 수가 많을수록 비용 잠식이 누적**. Holy Grail은 36건 × 약 -0.14% = -5%의 비용 부담.
이는 **자본의 5%를 비용으로 갈아넣는 셈**.

### 3.4 시장 상태별 승률 (regime breakdown)

| 전략 | TREND_UP WR | RANGE WR | 메모 |
|------|----:|----:|------|
| 01 Casper-RR3 | 0.0% (1건) | 0.0% (1건) | 표본 부족 |
| 02 Casper-RR2 | 0.0% (1건) | 0.0% (1건) | 표본 부족, 1건이 MIXED에서 WIN |
| 03 VWAP Pullback | 30.0% | 25.0% | 양쪽 다 비용 못 이김 |
| 06 Holy Grail | **30.8%** (13건) | 0.0% (17건) | TREND_UP 30% 승률도 비용 못 이김 |
| 09 ORB Fade | 0.0% | **50.0%** (8건) | RANGE 강하지만 큰 손실 1건이 모든 win 잠식 |
| 13 Momentum | 22.2% | 0.0% | 갭업 후 sustain 안 됨 |

### 3.5 핵심 관찰 (KIS 정밀 모델 반영)

1. **캐스퍼 RR3는 60일 동안 단 3건, 일평균 0.05회**. 사용자 호소대로다.
   기회손실은 거대하지만 **비용 손실도 거의 0** (Ret -0.01%, MDD -0.01%).
   "거래 안 하는 것" 자체가 최고의 자본 보존 효과.

2. **캐스퍼 RR2는 60일 동안 +0.49% 흑자** (3건 중 1건 WIN, RR 1:2 도달).
   현재 production이 RR=3인데, **이 표본에서는 RR=2가 더 좋았다** (TP 도달이 한 건 더).
   단, 표본 3건 — 통계적 유의성 부족.

3. **Holy Grail은 비용 반영 후 폭락**. 일평균 0.6회로 매매 빈도는 12배 늘었지만,
   **0.25% × 2 round-trip 비용을 견디기에 WR 13.9%·R 평균 -0.2가 부족**.
   표면상 매력적이던 +2.51%가 실제로는 -2.46%.

4. **단순 R:R 1:2 전략은 KIS 비용을 거의 못 이긴다.** 특히 BE shift가 11:00에 들어가면
   초기 진입 후 1시간 내 큰 추세가 안 잡히면 BE 손절 자주 발동 → 비용만 누적.

5. **PF 0.0인 전략 6개** (05, 09, 11, 12, 14): 비용 반영 후 win이 단 1건도 비용을 이기지 못함.
   특히 IB60-Breakout과 VT-EMA20은 WR 0% — 모든 진입이 손실.

6. **유일하게 흑자**: Casper-RR2 (+0.49%). Casper-RR3는 거의 break-even (-0.01%).
   다른 12개 전략 모두 적자. **즉 비용 시대에 캐스퍼의 strict 필터는 그 자체로 알파**.

### 3.6 백테스트 한계 및 caveat

| 한계 | 영향 | 보완 방향 |
|------|------|-----------|
| yfinance 5m → 60일 한정 | 통계적 유의성 부족, NR7/BB/Z-Score 표본 거의 0 | KIS minute history 또는 polygon.io 12~24개월 |
| Sharpe = trade-level | 표본 3건일 때 비현실적 (Casper-RR2 10.83) | 일별 P&L Sharpe 보완 |
| 슬리피지 차등 모델 | 09:30~10:00 실제 슬리피지는 더 클 수 있음 | volume-weighted slip 모델 |
| 1 trade/day 고정 | BB/RSI-2 다회 신호 불허 | 전략별 고유 규칙 옵션 |
| TQQQ-only (SQQQ dual-scan 미시뮬레이션) | 캐스퍼 dual_scan 효과 일부 누락 | SQQQ 5m 추가 |
| 환전 수수료 미적용 | USD 잔고 가정 — 매번 환전이면 +0.2% | KRW→USD 환전 빈도 모델링 |

---

## 4. Recommendation (結) — KIS 비용 반영

### 4.1 종합 판정 (수정)

| 카테고리 | 권장 | 비고 |
|----------|------|------|
| **현재 캐스퍼 유지 (RR3 또는 RR2 옵션)** | ✅ | 60일 표본에서 **유일하게 흑자(또는 break-even)**. strict 필터가 비용을 회피. |
| **Holy Grail 단순 추가** | ❌ **금지** | 36회 매매 × -0.14%/trade = -5% 비용 잠식. 단독으로는 적자. |
| **Holy Grail + RR ≥ 1:3 + ATR-trailing** | ⚠️ 후보 | RR을 1:3 이상으로 강화하고 ATR 트레일링 적용 시 재검증 가치. 본 보고서는 1:2 결과만 측정. |
| **VWAP / ORB Fade / Momentum** | ❌ | 60일에서 명확히 적자. 추가 필터 필수. |
| **NR7 / BB / Z-Score** | ⏸ | 표본 부족. 12~24개월 데이터 필요. |
| **MACD-Fast / VT-EMA20** | ❌ | WR 0% / Avg R 0 — TP 도달 불가능한 노이즈 거래. R:R 재설계 필수. |

### 4.2 다음 액션 (우선순위 순, KIS 비용 반영 후)

1. **데이터 확장 (HIGHEST)**: 60일은 표본 부족. KIS minute history / polygon.io 1~2년 5분봉 확보.
   특히 NR7 / BB / Z-Score는 표본 자체가 0건이라 평가 불가.

2. **RR=2 vs RR=3 결정 검토**: 60일 표본에서 RR=2가 RR=3보다 +0.50% 우위.
   하지만 표본 3건 — 1년 데이터로 재검증 필요. 현재 production RR=3 즉시 변경하지는 말 것.

3. **Holy Grail 재설계 후 재검증**:
   - RR 1:2 → **1:3 또는 ATR-trailing**으로 변경
   - ADX 25 → **ADX 30** (더 strong trend만)
   - 매매 빈도 36 → 15~20회 수준 (필터 강화)
   - 캐스퍼 ORB+FVG가 실패한 날에만 fallback (1 trade/day 유지)
   → 이 조건으로 재백테스트 후 채택 결정

4. **백테스트 엔진 개선**:
   - 일별 P&L Sharpe (trade-level 한계 회피)
   - regime-conditional sizing (RANGE에서 size 절반)
   - 환전 수수료 모델 (USD 잔고 부족 시 0.1% per round-trip 추가)

5. **A/B 운용 모드** (재설계 Holy Grail 채택 후):
   `entry.fallback = "holy_grail_strict"` 옵션 + paper trading 1개월 후 production 결정

### 4.3 사용자 호소에 대한 직접 답 (수정)

> "장이 아예 오르거나 아예 내리거나 하는 형태로 이루어지다보니 ORB를 돌파하는 FVG도 형성되지 않고, 그대로 상승하면서 매매를 못하게 되는 경향"

→ **정량 확인됨**:
- 60일 중 47일(78%)이 추세 일변도/박스권
- 캐스퍼 RR3는 60일 동안 단 3건 (skip rate 92%)
- 추세 일변도 25일 중 캐스퍼 진입 1건뿐

→ **하지만 KIS 비용 반영 후 핵심 메시지가 바뀜**:
- 캐스퍼의 "거래 빈도 낮음"이 사실은 **비용 회피라는 알파**
- Holy Grail로 매매 빈도를 12배 올리면 표면상 +2.51%였지만, **실제로는 -2.46%**
- 거래수수료 0.25% × 2 + 슬리피지 0.10~0.15%는 R:R 1:2 전략에서 **회복 불가능한 부담**

→ **올바른 해법** (수정):
1. **캐스퍼 strict 필터는 그대로 유지** — 비용 시대에 가장 합리적
2. **fallback 추가는 매우 보수적으로**:
   (a) RR 최소 1:3 보장
   (b) ADX 30 이상 강한 추세 + EMA20 pullback + 거래량 spike
   (c) 매매 빈도 0.3회/일 이하로 제한
3. **단순히 매매 늘리는 방향은 자본 잠식 위험** — Holy Grail 단순 도입 ❌

→ **답의 형태가 "보강"에서 "조심스러운 추가" 또는 "현 상태 유지"로 이동**.
60일 표본은 작지만 비용 압박이 명확히 가시화된 것이 가장 큰 발견.

---

## 출처 (References)

### KIS 비용 정책
- [한국투자증권 수수료안내 (truefriend.com)](https://www.truefriend.com/main/customer/guide/_static/TF04ae010000.shtm) — KIS 온라인 미국주식 0.25% per side
- [SEC Fee Rate Advisory (SEC.gov 2026)](https://www.sec.gov/) — Section 31 transaction fees
- [FINRA TAF rate](https://www.finra.org/) — Trading Activity Fee 2025

### 전략 출처
1. Brian Shannon — *Anchored VWAP for Intraday Analysis* (updated 2024)
2. Linda Raschke — *Street Smarts: High Probability Short-Term Trading Strategies* (1996)
3. LBR Group — *Holy Grail Historical Performance* (2024 update)
4. Larry Connors & Cesar Alvarez — *Short Term Trading Strategies That Work* (2009)
5. John F. Carter — *Mastering the Trade* (2nd ed., 2012)
6. Toby Crabel — *Day Trading with Short Term Price Patterns and Opening Range Breakout* (1990)
7. Carlo Zarattini & Andrew Aziz — *A Profitable Day Trading Strategy For The U.S. Equity Market* (SSRN 4729284, 2024). https://www.wealth-lab.com/api/discussion/download/pdf/8007-ssrn-4729284-1-pdf
8. Concretum Group — *Can Day Trading Really Be Profitable? ORB Strategy Research*. https://concretumgroup.com/can-day-trading-really-be-profitable/
9. tradingstats.net — *Initial Balance Breakout Statistics: ES & NQ Futures 2015–2025*. https://tradingstats.net/initial-balance-breakout-statistics/
10. Quantified Strategies — *NR7 Trading Strategy*. https://www.quantifiedstrategies.com/nr7-trading-strategy-toby-crabel/
11. Alvarez Quant Trading — *UPRO/TQQQ Leveraged ETF Strategy*. https://alvarezquanttrading.com/blog/upro-tqqq-leveraged-etf-strategy/
12. Trade Risk — *TQQQ Trading: Two Risks Every Leveraged ETF Trader Needs to Know*. https://www.thetraderisk.com/tqqq-trading-two-risks-every-leveraged-etf-trader-needs-to-know-about/
13. NinjaTrader Blog — *Statistical Analysis of Trading Patterns*. https://ninjatrader.com/futures/blogs/the-statistical-analysis-of-trading-patterns/
14. QuantPedia Database — *RSI-2 Mean Reversion Strategy* (2025 update)
15. SSRN — *The Impact of Volatility Drag on Leveraged ETF Trading Strategies* (2024)

(라이브 백테스트 데이터: `scripts/out/intraday_compare_results.json`, 60-day TQQQ 5m via yfinance, 2026-02-12 ~ 2026-05-08. KIS 정밀 비용 모델 적용)
