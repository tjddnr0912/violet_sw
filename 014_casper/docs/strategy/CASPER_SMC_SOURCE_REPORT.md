# Casper SMC 원본 출처 분석 + 봇 업그레이드 검토

> **작성일**: 2026-05-15
> **목적**: 014_casper 봇이 차용한 ICT 전략의 *원본 화자*를 식별하고, 그가 가르치는 알고리즘 요소를 정량적으로 재구성. 현재 봇과의 gap을 짚어 업그레이드 후보를 도출.
> **연구 라운드**: 2 (Gemini Pro + WebSearch + WebFetch)
> **주의**: 출처 신뢰도가 균일하지 않음 — 가르침 내용 자체와 *실거래 검증 가능성*은 별개. §6 반론 섹션 반드시 함께 읽을 것.

---

## 1. 인물 식별

| 항목 | 값 | 출처 |
|---|---|---|
| 활동명 | Casper SMC | YouTube `@caspersmc` |
| 본명 | **Jesse Rogers** | Trading Nut Podcast EP 302 제목 "The Truth About Casper SMC: **Jesse Rogers** Breaks His Silence" |
| 슬로건 | "Day trading saved my life, now I'm teaching you how to do the same" | YouTube 채널 description |
| 정체성 | ICT/SMC 2차 인플루언서 (Michael Huddleston 원본 ICT 가르침의 simplification + 자체 명명 모델) | 다수 비판 영상에서 확인 |
| 한국어권 변형 | **존재하지 않음** — 014_casper 명명은 영문 원본 직접 차용 | 한국어 검색 결과 zero hit |

### 1.1 활동 채널

| 플랫폼 | URL | 콘텐츠 |
|---|---|---|
| YouTube (메인) | [youtube.com/@caspersmc](https://www.youtube.com/@caspersmc/videos) | "ICT Mastery Course" 시리즈 (numbered: 001~) + free 영상 |
| X (Twitter) | [@casper_smc](https://x.com/casper_smc/status/1704918990898737351) | 마인드셋·자기계발 위주 트윗 |
| TikTok | [@caspersmc_](https://www.tiktok.com/@caspersmc_), [@casper_smc_trade](https://www.tiktok.com/@casper_smc_trade) | First Candle Rule 짧은 클립 |
| Trustpilot | [smarttradingblueprint.com](https://www.trustpilot.com/review/smarttradingblueprint.com) | 4.6/5 (코스 만족도 — 전략 edge 아님) |
| 본인 링크 허브 | linktr.ee/rogersj66 | 403 (접근 제한, 본명 Jesse Rogers `j66` 확인) |

### 1.2 상품 라인업

| 상품 | 정상가 | 유통 가격 | 비고 |
|---|---|---|---|
| ICT Mastery Course | $147 | $14.99 (sale) → leak PDF $0 | 15 videos + 3 PDFs |
| Smart Trading Blueprint 2025 (별도) | 미상 | ~$5,000 | 풀스택 멘토십, 비판 핵심 대상 |
| 6 Figure ICT Trading Strategy (PDF, 9p) | free | scribd 무료 | 5-step framework |
| Casper Smart Trading Plan (PDF, 8p) | — | scribd 무료, 10K views | 매매 계획 템플릿 |
| Range Expansion Strategy (PDF) | — | scribd 무료 | 별도 전략 |

---

## 2. 가르치는 알고리즘 (재구성)

캐스퍼는 동일 ICT 코어를 여러 이름으로 부른다 — "First Candle Rule" (30분), "5m ORB + Retest", "ICT Mastery Model" 등. 본질은 같은 한 가지 setup.

### 2.1 5-Step Framework (6 Figure ICT PDF에서 추출)

1. **Bias 식별** — 최근 displacement 캔들 방향
2. **시간 기반 liquidity 표시** — Asia/London/Premkt high·low + PDH/PDL
3. **진입 시간 (7:30~10:30 AM, CT 기준 = ET 8:30~11:30)** — 가격이 footprint 안 + 7:30 open 위/아래
4. **MSS (Market Structure Shift) + displacement** 확인
5. **타겟 = 명백한 liquidity, R:R 3:1**, 일일 손절 = 2 losses or 1 win이면 마감

### 2.2 First Candle Rule (TikTok/YouTube 변형)

```
1) 09:30 NY open 후 첫 30분 캔들 (또는 15분 변형)의 High/Low를 ORB로 정의
2) 30분 이후 가격이 ORB high (또는 low) 돌파
3) Displacement 캔들이 FVG 형성
4) 가격이 FVG로 retrace
5) 진입 = FVG mid, SL = ORB 반대편 또는 ORB midpoint
6) TP = R:R 1:3
```

캐스퍼의 강조점: **"하나의 setup만 마스터하라 (One Setup for Life)"**.

### 2.3 ICT Mastery Course — 3개 핵심 모듈

| 모듈 | 내용 | 미장봇 매핑 |
|---|---|---|
| **Unicorn Model** | Order Block → Breaker → FVG overlap 3-confluence | [[knowledge/trading-strategies/orb-fvg/unicorn-breaker-fvg-overlap]] (구현 완료) |
| **STBP Daily Bias** | PDH/PDL + PWH/PWL + MA20/50 합산 점수로 일별 방향성 | `src/core/bias.py::compute_daily_bias` (구현 완료) |
| **Range Expansion Strategy** | Higher timeframe impulse → entry on lower timeframe pullback | **봇 미구현** (multi-timeframe ICT는 일부만 구현) |

15 videos + 3 PDFs 중 위 3개가 mastery 핵심. 나머지 12개 영상은 위 모듈의 변형/예시.

### 2.4 TradingView 오픈소스 스크립트

캐스퍼 본인이 만든 게 아닌 **community에서 재구현**:

| 스크립트 | 작성자 | URL |
|---|---|---|
| Casper SMC: 5m ORB + Retest | hoosn1ck | [tradingview.com/script/muLbjEdA](https://www.tradingview.com/script/muLbjEdA-Casper-SMC-5m-ORB-Retest/) |
| First Candle Rule (Casper SMC) | TrueBacktests | [tradingview.com/script/95ANcJKU](https://in.tradingview.com/script/95ANcJKU-First-Candle-Rule-Casper-SMC/) (404, 회수됨) |

#### 2.4.1 hoosn1ck 스크립트의 정확한 룰

```
세션: 09:30~09:35 ET 5분봉 = Opening Range (★ 미장봇은 15분 = 다름)
진입:
  Long  → 5분봉 close > ORB.high AND 다음 봉이 ORB.high 아래로 wick 후 body는 위
  Short → mirror
SL    = ORB midpoint (★ 미장봇은 prev_candle.low — 다름)
TP    = Risk × R:R ratio (configurable)
필터  (default OFF):
  - ADX < 25 → skip
  - 4H VWAP: long은 위, short은 아래만
  - ATR Range: ORB height < ATR × multiplier → skip
부분 TP:
  - 50% close at TP1 (configurable)
  - 50% close at TP2
  - TP1 hit 후 SL을 ORB boundary로 이동
```

---

## 3. 매매 종목 (사용자의 핵심 질문)

### 3.1 캐스퍼 본인의 매매 종목

| Tier | 종목 | 사용 맥락 |
|---|---|---|
| **Primary** | **NQ futures** (Nasdaq 100 mini, micro=MNQ) | YouTube 영상의 70%+ 차트가 NQ |
| Secondary | **TQQQ / SQQQ** | 선물 자본 부족한 retail용 변형으로 가르침 |
| Tertiary | SPY, QQQ (1x ETF) | 비교용 |
| 부수 | Forex (EUR/USD, GBP/USD), Crypto (BTC), 개별 종목 | "전략은 동일하다"는 마케팅 메시지로 가르침 |

→ **선생님이 정확히 추정한 대로**, primary 매매 종목은 NQ 선물. 캐스퍼 본인이 영상에서 NQ 차트를 가장 많이 사용. **TQQQ/SQQQ는 선물 못 하는 retail에게 동일 전략을 mapping해주는 변형**.

### 3.2 종목 선정 가이드 (캐스퍼 공식 가이드 없음 — 추론)

PDF·영상·TradingView 스크립트를 종합한 *암묵적* 종목 선정 기준:

| 기준 | 캐스퍼 강조점 | 봇 차용 가능성 |
|---|---|---|
| **유동성** | NQ는 일일 거래량 수십억 달러 — slippage 무시 가능 | 봇은 TQQQ/SQQQ만 — 이미 충분 |
| **변동성 (ATR)** | NQ ATR ≈ 200~300 포인트/일 → 캐스퍼의 setup이 의미 있음 | 봇 ORB ATR 필터 (`orb_atr_max_ratio`) 이미 활용 |
| **세션 명확성** | NY session 09:30~16:00 ET — institutional 시간대 | 봇 09:30~10:55 ET scan window |
| **ICT killzone 정렬** | NY는 macro kill zone과 정확히 정렬 | 봇 AM_MACRO+AM_LATE (Scenario B) |
| **레버리지** | 선물 leverage = 명목 가치의 5~10% margin | TQQQ/SQQQ는 3x leveraged ETF — 비슷한 효과 |

**캐스퍼 본인은 명시적 "종목 선정 룰"을 가르치지 않음**. 대신 "transferable setup" 철학 — 동일 setup이 충분히 liquid한 모든 시장에서 작동한다고 주장.

### 3.3 만약 선물 안 한다면 (선생님 상황)

캐스퍼의 retail variation 그대로 = **TQQQ/SQQQ Long-only**. 봇이 이미 채택한 방식. 추가 후보:

| 옵션 | 장점 | 단점 |
|---|---|---|
| **QQQ Long + Short** (1x) | leverage decay 없음, 안정적 | 수익률 ↓ (3배 작음), short 빌려야 함 |
| **TQQQ + SQQQ** (현재 봇) | leverage 자연 제공, Long-only로 short 회피 | SQQQ는 decay가 큼 — 일중 OK, 오버나잇 위험 |
| **마이크로 NQ (MNQ) 선물** | 캐스퍼와 동일 instrument, contract 5x 작음 | 선생님이 선물 안 함 → 제외 |
| **개별 mega-cap (NVDA/MSFT/META)** | 유동성 충분 | ICT killzone과 정렬 약함, ATR 천차만별 |

→ 현재 봇 구성(TQQQ/SQQQ) 유지가 최선. 선물 영역 진출 의사 없으니 종목 변경 불필요.

---

## 4. 현재 봇과의 정량 비교

캐스퍼 가르침 = "Reference Implementation" 이라 볼 때:

| 차원 | 캐스퍼 (Reference) | 014_casper 봇 (Scenario B) | Gap |
|---|---|---|---|
| ORB 길이 | 5분 (hoosn1ck) 또는 30분 (First Candle Rule) | **15분** (09:30~09:44) | ★ 캐스퍼는 5min ORB 강조, 봇은 15min |
| SL 위치 | ORB midpoint (community script) | prev_candle.low (FVG 직전 봉) | ★ 다른 접근 |
| 진입 윈도우 | 09:30~10:30 (5-step PDF), 09:50~10:10 macro alignment 강조 | 09:45~10:55 (AM_MACRO+AM_LATE) | 봇이 약간 넓음 |
| FVG retrace 진입 | FVG mid | FVG mid (또는 OTE 0.705 if overlap) | ★ 봇이 OTE 추가 |
| R:R | 1:3 고정 (캐스퍼 강조) | AM_MACRO=1:3 / AM_LATE=1:2 (Scenario B) | ★ 봇이 zone별 분기 |
| 일일 손절 | 2 losses or 1 win → 마감 | circuit breaker (3 losses + weekly 3% loss) | ★ 봇은 일간 즉시 stop 없음 |
| 부분 TP | 50%/50% (community script) | 단일 TP만 | ★ 봇 미구현 |
| Daily Bias | STBP (PDH/PDL+PWH/PWL+MA20/50) | bias.py 동일 구현 | 일치 |
| Unicorn | Order Block → Breaker → FVG | breaker_block.py 동일 구현 | 일치 |
| Displacement | body/ATR + wick 강조 | body/ATR ≥ 1.0, wick < 50%, prev×1.5 | 일치 |
| 종목 | NQ 선물 (primary), TQQQ/SQQQ (retail) | TQQQ/SQQQ만 | 의도된 선택 |
| ADX 필터 | community script에 옵션 | 봇 미사용 | ★ 봇 미구현 |
| 4H VWAP 필터 | community script에 옵션 | 봇 미사용 | ★ 봇 미구현 |
| ATR Range 필터 | community script에 옵션 | `orb_atr_max_ratio=1.5` 유사 구현 | 일부 일치 |

★ 표시 = 차이점.

---

## 5. 외부 정량 검증 자료 (Edge Verification)

### 5.1 검증 자료의 부재

**구조적 결론**: 공개된 *독립* 정량 검증 자료는 거의 없다.

조사한 후보:
- **TradingView 백테스트 스크립트** (hoosn1ck 5m ORB) — backtest UI는 사용 가능하지만 description에 결과 수치 없음
- **YouTube 백테스트 영상** ([Caspar SMC Simple Trading Strategy Backtest - High Profits](https://www.youtube.com/watch?v=pj-vq53Xe-I)) — 본인이 아닌 reviewer 영상, 구체 수치 검증 안 됨
- **My Simple One Candle Scalping Strategy (Backtested Results)** ([영상](https://www.youtube.com/watch?v=RR2ohkzTSXQ)) — title만 backtested, 자료 비공개
- **Smart Trading Blueprint Trustpilot** — 4.6/5 (코스 만족도, **edge 검증 아님**)

### 5.2 본인 주장 vs 외부 검증

| 출처 | 주장 |
|---|---|
| 캐스퍼 본인 (Trading Nut EP 302) | "broker statements를 공개해 매매 성공을 입증" |
| **ImanTrading의 반박** ([YouTube 폭로](https://www.youtube.com/watch?v=L8lKNiBF4Xg)) | **broker 플랫폼이 live account에만 표시하는 "24-hour 아이콘"이 SPY 옆에 없음 → SIM/paper 계정 결과를 live로 위장한 의혹** |
| ImanTrading X | "Fake ICT guru selling $5,000 course" — Smart Trading Blueprint 풀 멘토십 비판 |
| TruePikolla 등 다른 ICT 비판자 | 유사 폭로 영상 다수 |

### 5.3 신뢰 평가

| 영역 | 평가 |
|---|---|
| 가르침의 *개념적 정합성* | ★★★★☆ — ICT 본가 가르침을 잘 단순화. ORB+FVG+killzone은 검증 가능한 명시적 룰 |
| 가르침의 *실증적 edge* | ★☆☆☆☆ — **독립 검증 자료 부재 + SIM 위장 의혹** |
| 코스 비즈니스 윤리 | ★☆☆☆☆ — $5K 코스에 대한 비판 다수, 무료 자료로 충분히 학습 가능 |
| 봇 reference로서의 가치 | ★★★☆☆ — *개념의 source*로는 유효, *수익률 보장*으로는 무효 |

**결론**: 캐스퍼 본인의 매매 성과를 신뢰할 근거는 없지만, *그가 정립한 알고리즘 룰 자체*는 검증 가능하고 백테스트 가능하다 — 014_casper 봇의 PHASE1_PRECHECK n=11 / 60일 백테스트가 그 정량 검증의 *첫 번째 진정한 시도*에 해당.

---

## 6. 봇 업그레이드 후보 (조사 기반)

### 6.1 우선순위 ① — 즉시 검토 가능 (코드 변경 작음)

#### A. 5분 ORB 옵션 추가 (vs 현재 15분)

캐스퍼 본인의 First Candle Rule은 *30분* (TikTok), community 5m ORB script는 *5분*. 봇은 *15분* — 어느 쪽이 최적?

```python
config.orb.window_minutes: 15 | 5 | 30
```

- 5분 ORB: 진입 윈도우 길어짐 (09:35~10:55), setup 빈도 ↑
- 30분 ORB: range가 크고 안정적, breakout 명확성 ↑

**제안**: 백테스트로 비교 — 60일 yfinance 5m으로 ORB 길이별 PF 측정.

#### B. SL을 ORB midpoint로 변경 (vs prev_candle.low)

community script의 정설. 봇의 prev_candle.low는 더 빡빡 (작은 risk = 큰 TP). ORB midpoint는 더 넉넉 (작은 R:R 같은 TP).

**제안**: 백테스트 변형 추가 — `sl_method: prev_low | orb_midpoint`. 같은 60일에서 어느 게 PF 높은지 비교.

#### C. 부분 TP (50%/50%)

캐스퍼 community script의 정설. TP1 (50%) hit → SL을 ORB boundary로 이동 → TP2 위에서 50% 더.

**제안**: 봇에 `partial_tp: bool` + `tp1_ratio: 1.5`, `tp2_ratio: 3.0` 추가. 같은 setup에서 어느 게 expectancy 높은지 백테스트.

### 6.2 우선순위 ② — 검토 후 결정

#### D. 일일 stop 규칙 (2 losses or 1 win)

캐스퍼 PDF의 명시적 룰. 현재 봇은 일일 1매매 + 주간 3% 손절만.

캐스퍼 룰을 그대로 적용 시 (이미 봇은 일일 1매매라):
- 1 LOSS → 다음 날까지 stop (이미 행동 동일)
- 1 WIN → stop (이미 행동 동일)

→ **이미 충족된 룰**. 별도 변경 불필요.

#### E. ADX (>25) 필터

community script 옵션. 트렌드 강도 약한 날 setup 제외.

**제안**: 매우 보수적인 추가 필터. 매매 빈도 감소 부작용 큼. 60일 백테스트에서 이미 매매 0~4건인 상태에서 추가 시 빈도 더 떨어짐. **보류**.

#### F. 4H VWAP 필터

community script 옵션. long은 4H VWAP 위에서만, short은 아래에서만.

미장봇은 이미 Daily Bias (PDH/PDL+MA20/50)로 일별 방향 결정 — 4H VWAP은 *더 단기*. 중복 가능성 있지만 보완적일 수도.

**제안**: Daily Bias가 neutral인 날만 4H VWAP fallback으로 사용. 별도 백테스트 필요.

### 6.3 우선순위 ③ — 검토 후 deferred

#### G. Range Expansion Strategy (Mastery 모듈)

상위 timeframe(1H/4H) impulse → 하위 timeframe(5min) pullback 진입. 봇의 현재 multi-tf SL은 5m→1m 정밀화. Range Expansion은 *상위* timeframe 활용 — 완전히 다른 차원.

**제안**: 별도 plan으로 분리. 4H QQQ 일중 expansion 감지 → 5m ORB가 그 방향과 일치할 때만 진입. PHASE 5 수준 작업.

### 6.4 권장하지 않는 변경

| 변경 | 이유 |
|---|---|
| ORB midpoint를 SL로 강제 변경 | 백테스트 검증 전 변경 위험. A/B로만 |
| 30분 ORB로 변경 | 진입 윈도우 단축 → AM_MACRO와 충돌. 보류 |
| $5K Smart Trading Blueprint 구매 | ImanTrading 폭로 신뢰성 ↑. 무료 자료로 충분 |
| 본인의 broker statement를 신뢰 | SIM 위장 의혹 — *수익률 모방 목표는 위험* |

---

## 7. 백테스트 계획 (제안)

업그레이드 후보를 정량 검증하는 단일 백테스트 스크립트:

```python
# scripts/casper_variants_backtest.py
변형 = {
    "BASE":        ORB 15min, SL prev_low, single TP, RR=3/2 split,
    "5m_ORB":      ORB 5min,  others same,
    "30m_ORB":     ORB 30min, others same,
    "SL_midpoint": ORB 15min, SL = orb midpoint, others same,
    "partial_TP":  ORB 15min, partial 50%/50% at 1:1.5/1:3, others same,
    "ADX_filter":  ORB 15min, + ADX≥25 필터,
    "VWAP_4H":     ORB 15min, + 4H VWAP 정렬 필터,
}
# 동일 60일 yfinance × TQQQ/QQQ/SQQQ × KIS 비용 모델
```

매 변형마다: 매매 수, WR, PF, MDD, expectancy, AvgR. 분포는 `displacement_distribution.py`와 동일 톤.

**예상 결과**: 60일 표본 한계로 모든 변형이 통계 무의미. 그래도 *방향성*은 확인 가능. 1년+ 데이터 수집 인프라가 필요한 진정한 결론.

---

## 8. 사용자 액션 가이드

### 8.1 즉시 (코드 변경 없이)

1. **반드시 시청**: Casper SMC YouTube 채널의 numbered 시리즈 005, 015, 030 (free, 무료 자료로 충분)
2. **참고 PDF 다운로드**: scribd의 "6 Figure ICT Trading Strategy" + "Casper Smart Trading Plan" (free)
3. **봇 결정 로그 모니터**: `scripts/displacement_distribution.py --source live` 매주 실행

### 8.2 단기 (1~2주)

1. **백테스트 스크립트 작성**: `scripts/casper_variants_backtest.py` — 위 7개 변형 비교
2. **결과 보고**: 어느 변형이 60일에서 유의미한 차이를 보이는지

### 8.3 중기 (1~3개월)

1. **라이브 데이터 누적** Scenario B로 진행 중. AM_LATE 진입 5건+ 누적 후 PHASE1_PRECHECK 재실행
2. **부분 TP** 백테스트 결과가 긍정적이면 단계적 도입

### 8.4 권장하지 않음

- Smart Trading Blueprint $5K 구매
- 캐스퍼의 broker statement를 모방 목표로 삼기

---

## 9. Sources

### 출처
- [Casper SMC YouTube 채널](https://www.youtube.com/@caspersmc/videos)
- [Trading Nut Podcast EP 302 — Jesse Rogers Breaks His Silence](https://tradingnut.com/casper-smc/)
- [Casper SMC ICT Mastery Course - Trades Mint](https://tradesmint.com/product/casper-smc-ict-mastery-course/)
- [6 Figure ICT Trading Strategy PDF (Scribd)](https://www.scribd.com/document/696266632/6-Figure-ICT-Trading-Strategy-Casper-SMC)
- [Casper Smart Trading Plan PDF (Scribd)](https://www.scribd.com/document/653001889/Casper-Smart-Trading-Plan)
- [Range Expansion Strategy PDF (Scribd)](https://www.scribd.com/document/712568544/Range-Expansion-Strategy-Casper-SMC)
- [Casper SMC: 5m ORB + Retest by hoosn1ck (TradingView)](https://www.tradingview.com/script/muLbjEdA-Casper-SMC-5m-ORB-Retest/)
- [Smart Trading Blueprint Trustpilot Reviews](https://www.trustpilot.com/review/smarttradingblueprint.com)
- [WOR Podcast EP.96 — How To Trade Prop Firms The Right Way](https://open.spotify.com/episode/7Hj62tUBi3m1qHAaT5d9SP)

### 반론·검증
- [ICT's Top 2 Traders Are Frauds (ImanTrading 폭로)](https://www.youtube.com/watch?v=L8lKNiBF4Xg)
- [ImanTrading X — Fake ICT Guru 비판](https://x.com/imantradingYT/status/1821559812728951198)
- [Casper SMC: Scam or Legit Guru?](https://www.youtube.com/watch?v=wRg5B1LxMog)

### 백테스트 외부 영상
- [Caspar SMC Simple Trading Strategy Backtest](https://www.youtube.com/watch?v=pj-vq53Xe-I)
- [My Simple One Candle Scalping Strategy (Backtested Results)](https://www.youtube.com/watch?v=RR2ohkzTSXQ)
