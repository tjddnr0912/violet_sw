# US 퀀트 트레이딩 종합 가이드 — KIS 수수료 0.25% 환경

> **작성일**: 2026-05-15
> **저자**: Claude (research skill, Gemini Round 1 + WebSearch 5 라운드)
> **대상**: 한국투자증권(KIS) 미국주식 계좌, 왕복 수수료 0.50%(매수 0.25% + 매도 0.25%) 환경
> **목적**: Casper(데이트레이딩 봇) 외에 **장기·저빈도 퀀트 전략**을 검토하여 자본의 어느 부분을 어떻게 분할 운용할지 결정하는 근거 자료
> **선행 문서**: [INTRADAY_COMPARISON.md](INTRADAY_COMPARISON.md) (Casper 데이트레이딩 13개 대안 비교, KIS 정밀비용 모델)

---

## 0. TL;DR (한 문단 요약)

KIS 미국주식 0.25% × 2 = **왕복 0.50% 수수료** + 한국 양도소득세 22% (기본공제 250만 원/년) + 환전 스프레드 (전신환매도/매수 약 0.2%) 환경에서 **현실적으로 살아남는 퀀트 전략은 회전율(Turnover) 300% 이하**이다. 데이트레이딩(Casper) 같은 1,000%+ 회전 전략은 비용 5%/년이 알파를 잠식하므로, 자본의 일부를 **월간·분기간 리밸런스 저빈도 전략**(Antonacci GEM, Clenow Stocks-on-the-Move, Faber GTAA, SPMO/MTUM 매수보유, AQR 멀티팩터 복제)으로 옮기면 비용 0.2~1.5%/년에 CAGR 10~20%·MaxDD −20%~−30%를 기대할 수 있다. Casper(데이트레이딩)는 ‘추세장에서 ORB+FVG strict 필터가 매매를 90% 보류 → 비용 회피 자체가 알파’라는 본질을 갖고 있어, **저빈도 퀀트가 Casper의 ‘기회손실(매매 보류 일자)’을 메우는 보완재**가 된다. 결론은 **대체가 아닌 하이브리드**: 자본의 70%는 GEM/Clenow/SPMO 같은 저회전 시스템에, 30%는 Casper 데이트레이딩에 배분하는 것이 KIS 0.25% × 2 환경의 합리적 기본형이다.

---

## 1. 起 — 왜 저빈도 퀀트를 다시 보는가

### 1.1 Casper 60일 백테스트가 던진 질문

[INTRADAY_COMPARISON.md](INTRADAY_COMPARISON.md) §3 에 정리된 60일(2026-02-12 ~ 2026-05-08) TQQQ 5분봉 백테스트 결과는 다음을 확인시켰다.

| 발견 | 의미 |
|---|---|
| Casper RR3 60일 동안 **단 3건 매매**(일평균 0.05회) | 캐스퍼의 strict filter가 90% 매매를 차단함 |
| KIS 정밀비용 반영 시 13개 대안 중 **11개가 적자** | 0.25% × 2 + slippage 0.10~0.15%/trade는 RR 1:2 단순 전략에서 회복 불가 |
| Holy Grail (Linda Raschke) 비용 미반영 +2.51% → 비용 반영 −2.46% | 매매 36건 × −0.14%/trade ≈ −5% 비용 잠식 |
| Casper만 유일하게 +0.49% (RR2) 또는 −0.01% (RR3) 흑자/break-even | strict filter = **비용 회피 자체가 알파(α)** |

이 60일 실험은 “**고빈도(High-Frequency) 인트라데이 전략 대부분이 KIS 비용 환경에서 의미가 없다**”는 강한 시그널이었다. 그러나 동시에 **하루 평균 0.05회 매매란 사실상 자본이 놀고 있다는 의미**이기도 하다. Casper RR3는 “자본 보존 ✓ 기회손실 ↑↑”의 극단을 보여줬다.

### 1.2 그렇다면 어디서 알파를 얻을 것인가

위 질문에 대해 학계와 산업계는 60년에 걸친 답변을 누적해 왔다. 답은 한 줄로 요약된다.

> **회전율을 낮추고, 잘 검증된 팩터(factor)에 분산 노출하라.**

이 문서는 그 ‘잘 검증된 팩터’와 ‘저회전 알고리즘’을 KIS 0.25% × 2 환경에서 어떻게 활용할지를 다룬다.

---

## 2. 핵심 용어 풀이 (Glossary)

문서 본문에서 처음 등장할 때 다시 한 번 설명하지만, 빠르게 참조할 수 있게 한 곳에 모았다.

### 2.1 성과 지표

| 용어 | 영문 | 정의 | 직관 |
|---|---|---|---|
| **CAGR** | Compound Annual Growth Rate | 연복리 수익률. $1 → $X 가 N년 동안 일어났다면 `CAGR = X^(1/N) − 1` | 매년 평균 몇 % 복리로 불었나 |
| **Sharpe 비율** | Sharpe Ratio | 초과수익(평균수익 − 무위험금리)을 변동성(표준편차)으로 나눈 값 | 변동성 1% 당 몇 % 수익을 얻나. >1 좋음, >2 매우 좋음, >3 의심 |
| **Sortino 비율** | Sortino Ratio | Sharpe와 같지만 **하방 변동성**만 사용 | 상방 변동성은 좋은 변동성이므로 패널티 안 주겠다는 변형 |
| **MaxDD** | Maximum Drawdown | 고점 대비 최대 손실폭(%). 시계열 안에서 가장 큰 잠재 미실현 손실 | −50% MaxDD = 자본이 절반으로 줄어든 적이 있다 |
| **Calmar 비율** | Calmar Ratio | CAGR / |MaxDD| | 큰 손실 한 번을 견딜 만큼 평소에 벌었나 |
| **PF** | Profit Factor | (이긴 거래 총 수익) / (진 거래 총 손실). >1 흑자, >2 우수 | 수익 1원 얻기 위해 손실 얼마 감수했나 |
| **WR** | Win Rate | 이긴 거래 수 / 전체 거래 수 | 단독으로는 의미 약함 (R:R과 함께 봐야 함) |
| **R:R** | Risk-Reward Ratio | 손절폭 1 단위 대비 익절폭 단위. 1:2 = 손절 1원·익절 2원 | WR과 함께 손익분기 승률을 결정 |
| **Beta(β)** | Beta | 시장(S&P 500 등) 1% 움직임에 자산이 평균 몇 % 움직이나 | β=1 시장 동조, β=0 무상관, β>1 시장보다 큰 변동 |
| **Alpha(α)** | Alpha | 시장 베타로 설명되지 않는 초과수익 | "독자적 실력"으로 번 부분 |
| **Turnover** | Turnover | 1년 동안 포지션이 몇 번 교체되었나(%). 100% = 1년에 자산 전체를 한 번 갈아탐 | 회전율이 높을수록 비용 부담 큼 |

### 2.2 전략 분류

| 용어 | 영문 | 정의 | 한 줄 예시 |
|---|---|---|---|
| **모멘텀** | Momentum | 최근 잘 오른 자산이 계속 오른다는 가설 | "지난 12개월 수익률 상위 10%를 매수" |
| **크로스섹셔널 모멘텀** | Cross-sectional Momentum (CS-MOM) | 같은 시점 여러 자산을 비교해 상대적 강자를 매수 | "S&P 500 종목 중 상위 50주" |
| **타임시리즈 모멘텀** | Time-series Momentum (TS-MOM) | 한 자산의 자체 시계열만 보고 상승 추세면 매수/하락 추세면 매도 | "S&P 12개월 수익률 >0이면 보유, <0이면 현금" |
| **평균회귀** | Mean Reversion | 가격이 평균에서 벗어나면 다시 돌아온다는 가설 | "RSI(2) < 10이면 매수, 5일 SMA 도달 시 매도" |
| **추세추종** | Trend Following / CTA | 장기 추세를 따라 다양한 자산군(주식·채권·원자재·통화·금리)에 분산 | CTA(Commodity Trading Advisor) 펀드들 |
| **통계적 차익거래** | Statistical Arbitrage (StatArb) | 통계 모형으로 일시적 가격 괴리를 잡아 무위험에 가까운 수익 추구 | "Coca-Cola vs Pepsi 페어 z-score > 2면 short Coke/long Pepsi" |
| **페어 트레이딩** | Pairs Trading | StatArb의 가장 단순한 형태. 두 자산 스프레드만 트레이드 | 위 예시 |
| **멀티팩터** | Multi-Factor | 가치(Value)·우량(Quality)·소형(Size)·저변동(Low-Vol)·모멘텀(Momentum) 등 학술적으로 검증된 팩터에 분산 노출 | iShares MTUM, QUAL, VLUE, SIZE 동시 보유 |
| **리스크 패리티** | Risk Parity | 각 자산이 포트폴리오 리스크에 **같은** 양 기여하도록 비중 결정. 보통 변동성이 낮은 채권/원자재에 레버리지 적용 | Bridgewater All Weather |
| **변동성 타깃팅** | Volatility Targeting | 목표 변동성(예: 연 15%)을 정해놓고, 자산 변동성이 높으면 포지션 축소, 낮으면 확대 | "20일 실현변동성 기준 사이즈 조정" |
| **이중 모멘텀** | Dual Momentum | 절대 모멘텀(자기 시계열) + 상대 모멘텀(자산 간 비교)을 결합 | Antonacci GEM: SPY vs VEU 12개월 수익률 비교 후 둘 다 T-Bill보다 약하면 채권으로 |
| **택티컬 자산배분** | Tactical Asset Allocation (TAA) | 단기 시장 신호(예: SMA, 모멘텀)에 따라 자산군 비중을 동적으로 조정 | Faber GTAA: 5/10/13 자산을 10개월 SMA로 ON/OFF |
| **전략적 자산배분** | Strategic Asset Allocation (SAA) | 장기 기대수익·상관관계에 따라 비중 고정. 리밸런스 외 거의 안 움직임 | "60% SPY / 40% AGG 매년 1회 리밸런스" |

### 2.3 팩터 / 인자

| 용어 | 영문 | 정의 | 대표 ETF |
|---|---|---|---|
| **가치** | Value | 저PER·저PBR·고배당 등 ‘싸 보이는’ 주식이 장기적으로 비싸 보이는 주식을 이긴다 | VLUE, IVE, VBR |
| **우량** | Quality | 자기자본이익률(ROE) 높고 부채 적고 이익 안정적인 주식 | QUAL, JQUA, COWZ |
| **소형주** | Size | 시가총액 작은 주식이 큰 주식을 장기 이긴다 (1980년 이후 약화) | IWM, SLY |
| **저변동** | Low-Volatility | 변동성이 낮은 주식이 위험 대비 수익이 더 좋다 (CAPM 반대) | USMV, SPLV |
| **모멘텀** | Momentum (factor) | 위에서 정의됨 | MTUM, SPMO, VFMO |
| **QMJ** | Quality minus Junk | Quality 롱·Junk 숏의 학술 팩터. Buffett의 알파 일부를 설명 | (학술용) |
| **BAB** | Betting Against Beta | 저베타 롱·고베타 숏 + 레버리지. Buffett 알파의 또 다른 일부 | (학술용) |

### 2.4 시장 도구

| 용어 | 영문 | 정의 |
|---|---|---|
| **ETF** | Exchange-Traded Fund | 거래소 상장 인덱스 펀드. 주식처럼 매매 가능 |
| **AUM** | Assets Under Management | 운용자산 규모 |
| **SMA / EMA** | Simple / Exponential Moving Average | 단순/지수 이동평균 |
| **ATR** | Average True Range | N일 평균 변동 폭. 변동성 측정 표준 |
| **RSI** | Relative Strength Index | 0~100 모멘텀 오실레이터. 14일 표준 |
| **Slippage** | Slippage | 주문가와 체결가 차이. KIS 미국주식 시장가 SL 시 약 0.10% |
| **Bid-Ask Spread** | Bid-Ask Spread | 매수 호가 vs 매도 호가 차이. TQQQ 약 $0.01/주 (~0.025%) |
| **PDT 규칙** | Pattern Day Trader rule | 미국 FINRA의 5일 내 4회+ 데이트레이드 시 $25,000 최소 자본 요구. **한국 증권사는 미적용** |
| **양도소득세** | Capital Gains Tax | 한국 해외주식 매매 차익에 대해 22%(지방세 포함), 기본공제 250만 원/년 |

---

## 3. 承 — 8대 퀀트 전략 family 상세

각 family에 대해 다음 6요소를 채운다: **(1) 정의 (2) 원리 (3) 알고리즘 (4) 학술 출처 (5) 운용사·ETF (6) 공개 수익률**.

> **공통 주의 1: 회전율과 KIS 비용.**
> 왕복 0.50% 비용은 회전율이 100%면 0.50% 비용 발생, 1,000%면 5.0% 비용 발생. CAGR 10% 전략이라도 회전율이 1,000%면 순익 5%로 반토막.

> **공통 주의 2: Sharpe 비율이 3 이상이면 의심하라.**
> Renaissance Medallion(공개 안 됨)을 제외하고 retail 가능 전략의 검증된 Sharpe는 대부분 0.4~1.5 범위.

### 3.1 모멘텀 (Momentum) — 가장 검증되고 가장 ‘배신’도 잦은 팩터

#### 정의
**모멘텀(Momentum)** = 최근 가격이 잘 오른 자산이 앞으로도 평균적으로 더 오른다는 통계적 경향. 크게 두 종류로 나뉜다.
- **크로스섹셔널(CS) 모멘텀**: 같은 시점 여러 자산을 비교해 상위(예: 상위 10%) 매수, 하위 매도(또는 무시).
- **타임시리즈(TS) 모멘텀**: 한 자산의 자체 과거 수익률 부호만 보고 양수면 보유, 음수면 현금/매도.

#### 원리
1979년 Jegadeesh & Titman이 처음 학술적으로 보고. 행동재무학적 설명: 투자자가 새 정보에 ‘**천천히 반응**’(underreaction)하기 때문에 추세가 일정 기간 지속됨. 한편 너무 길게 지속되면 ‘**과잉반응(overreaction)**’이 누적되어 **모멘텀 크래시(Momentum Crash)**가 일어남(2009년 3월 미국 모멘텀 −40%).

#### 알고리즘 (CS-MOM, 학술 표준)
```
매월 마지막 거래일:
  1. universe = 미국 보통주, 시총 상위 1,000개
  2. score[i] = ret[i, -12개월 ~ -1개월]   # 최근 1개월 제외 (단기 평균회귀 회피)
  3. rank by score, 상위 10% 매수, 하위 10% 매도 (또는 무시)
  4. equal-weight, 다음 달 첫 거래일에 리밸런스
```

#### 학술 출처
- Jegadeesh, N. & Titman, S. (1993) "Returns to Buying Winners and Selling Losers", *J. Finance*. 1965~1989 미국주식에서 12-1 momentum이 연 1% 초과수익을 냈다고 보고.
- Asness, C., Moskowitz, T., Pedersen, L.H. (2013) "Value and Momentum Everywhere", *J. Finance*. 8개 자산군에서 모멘텀이 보편적임을 입증.
- Frazzini, A., Israel, R., Moskowitz, T. (2020) "Trading Costs of Asset Pricing Anomalies". AQR이 실거래 비용을 측정해 모멘텀이 비용 후에도 살아남는다고 보고.

#### 운용사·ETF
| 티커 | 운용사 | 자산규모(AUM) | 리밸런스 | 보유 종목 수 | 비용비율 |
|---|---|---:|---|---:|---:|
| **MTUM** | iShares (BlackRock) | ~$14B | 반기 | ~125개 | 0.15% |
| **SPMO** | Invesco | ~$2B | 분기 | ~100개 | 0.13% |
| **VFMO** | Vanguard | ~$1B | 월간 | ~580개 | 0.13% |
| **QMOM** | Alpha Architect | ~$200M | 분기 | ~50개 | 0.39% |

#### 공개 수익률 (2026-05 기준)
| ETF | 2024 | 2025 | 2026 YTD | 5년 CAGR | 10년 CAGR | Sharpe |
|---|---:|---:|---:|---:|---:|---:|
| **SPMO** | **+45.8%** | **+26.6%** | +23.0% | 22.31% | 19.41% | 2.32 |
| **MTUM** | +32.9% | +22.2% | +20.7%(13.68 YTD per 일부 소스) | – | 15.87% | 1.82 |
| **VFMO** | – | +13.44%(5yr) | +19.95% | 13.44% | – | 2.24 |
| **QMOM** | – | +2.4% | +18.6% | – | – | – |

→ SPMO는 ‘대형 AI 모멘텀(NVDA·MSFT·AAPL)’에 집중되어 2024~2025 압도적. QMOM은 “순수 모멘텀 + 변동성 낮은 종목 우선” 규칙으로 2025년에는 underperform 했지만 2026 회복 중. **이는 모멘텀이 ‘rules 차이로 결과가 매우 달라지는’ 팩터임을 보여줌**.

#### 반론 (Counter)
- 2010~2019 ‘**잃어버린 10년**’: MTUM이 SPY를 거의 못 이김. 학계는 “모멘텀이 죽었나” 토론.
- 2024~2025 부활은 ‘대형주 모멘텀 = AI 모멘텀’이라는 점에서 산업 특이 요인 가능.
- **모멘텀 크래시 위험**: 시장이 급반전할 때 가장 큰 손실. 2009년 3월 미국 −40%, 2020년 3월 −20%.

---

### 3.2 멀티팩터 (Multi-Factor) — 가장 ‘기관다운’ 안정 전략

#### 정의
**멀티팩터(Multi-Factor)** = 학술적으로 검증된 여러 팩터(가치·우량·소형·저변동·모멘텀)에 동시에 노출. 한 팩터가 부진해도 다른 팩터가 만회.

#### 원리
- 각 팩터는 **장기 평균적으로 양의 프리미엄**을 보이나, **단기에는 서로 다른 시점에 부진**함.
- 예: 2020 Value −20%, 같은 해 Momentum +30%. 둘 다 들고 있으면 +5%.
- 학술적 기반: **Fama-French 3-factor (1993)** → **5-factor (2015)** → Carhart momentum 추가 6-factor. 가장 많이 인용되는 자산가격결정모형.

#### 알고리즘 (예: 6-factor equal-weight 복제)
```
quarterly:
  1. 각 팩터 ETF 비중 1/6:
     Value     → VLUE 16.7%
     Momentum  → MTUM 16.7%
     Quality   → QUAL 16.7%
     Size      → IWM  16.7%
     Low-Vol   → USMV 16.7%
     Min-Vol   → SPLV 16.7%
  2. 분기 말 각 자산 비중을 1/6로 재조정
  3. (선택) 200일 SMA 아래로 SPY 깨지면 50% 현금(BIL)
```

#### 학술 출처
- Fama, E. & French, K. (1993) "Common risk factors in the returns on stocks and bonds", *J. Financial Economics*. 3-factor model (Market, SMB, HML).
- Fama, E. & French, K. (2015) "A five-factor asset pricing model", *J. Financial Economics*. Profitability·Investment 추가.
- Carhart, M. (1997) "On Persistence in Mutual Fund Performance", *J. Finance*. Momentum 추가.
- Asness, C., Frazzini, A., Pedersen, L.H. (2019) "Quality Minus Junk", *Review of Accounting Studies*. QMJ 팩터.

#### 운용사
- **AQR Capital Management**: Cliff Asness 창업. 2025년 Apex Strategy +19.6%. QSPIX (Style Premia Alternative Fund) 5년 CAGR 21.09%, 10년 6.27%, MaxDD −41.37% (2018-2020 누적). 학술 → 실거래의 가장 직접적 가교.
- **Dimensional Fund Advisors (DFA)**: Eugene Fama 자문. 패시브 가치/소형주 중심.
- **Research Affiliates (Rob Arnott)**: Fundamental Indexing.

#### 공개 수익률
| 펀드/ETF | 기간 | 수익률 | 비고 |
|---|---|---:|---|
| **AQR QSPIX (Style Premia)** | 최근 1년 | **+17.75%** | Long/short 멀티에셋 multi-style |
| AQR QSPIX | 5년 CAGR | **+21.09%** | 2020~2025 |
| AQR QSPIX | 10년 CAGR | +6.27% | 2014~2018 부진 포함 |
| AQR QSPIX MaxDD | 2018-2020 | **−41.37%** | 2018 −12.3%, 2019 −8.1%, 2020 −21.9% |
| AQR Apex Strategy | 2025 | +19.6% | flagship 멀티팩터 |
| QUAL (iShares Quality) | 10년 CAGR | ~12% | S&P 500 대비 약간 우위 |

→ **멀티팩터 = 안정성·용량 최대, 단기 underperform 위험 동반**.

#### 반론
- 2018-2020 QSPIX −41% MaxDD는 ‘분산된 멀티팩터’조차 큰 손실을 볼 수 있음을 보여줌 (Value 부진 + 코로나).
- 일부 팩터(Size)는 1980년대 이후 사실상 사라짐 (Banz 1981 발견 후 차익거래 소멸).
- Robeco (2024) 5-factor model 비판: profitability/investment 팩터가 모든 시장에서 재현되지 않음.

---

### 3.3 추세추종 (Trend Following / CTA) — 모든 자산군에 적용되는 형 모멘텀

#### 정의
**추세추종(Trend Following)** = 한 자산이 ‘위로 추세’이면 매수, ‘아래로 추세’이면 매도(또는 숏). 주식·채권·통화·원자재·금리 **5대 자산군 50~100개 시장**에 동시 적용하는 게 ‘CTA(Commodity Trading Advisor)’ 표준.

#### 원리
- TS-MOM(타임시리즈 모멘텀)의 다자산 확장.
- 행동재무학: 추세 정보가 시장에 천천히 반영됨 + 위험관리(헤지) 수요가 추세를 더 강화.
- 핵심 가치: **위기 시 양의 수익**(crisis alpha). 2008, 2022 인플레 충격에서 강함.

#### 알고리즘 (단순 12-1 multi-asset)
```
매월 말:
  for asset in [SPY, EFA, EEM, AGG, IEF, TLT, DBC, GLD, USO, FXE, FXY, UUP]:
    if total_return(asset, lookback=12개월) > 0:
      target_weight[asset] = 1/N
    else:
      target_weight[asset] = 0   # 현금(BIL)
  vol_target = 10%
  scale = vol_target / portfolio_realized_vol
  positions = target_weight * scale
```

#### 학술 출처
- Moskowitz, T., Ooi, Y.H., Pedersen, L.H. (2012) "Time series momentum", *J. Financial Economics*. 1965-2009 다자산 TS-MOM이 모든 자산군에서 유의한 알파를 냄.
- Hurst, B., Ooi, Y.H., Pedersen, L.H. (2017) "A century of evidence on trend-following investing", *J. Portfolio Management*. 1880-2016 137년 데이터로 trend following이 시대 불변임을 보임.

#### 운용사
- **AQR Managed Futures Strategy Fund (AQMNX/AQMRX)**: AQR의 retail CTA.
- **Man AHL, Winton, Aspect Capital, Lynx Asset Management, Transtrend**: 전통 CTA 강자.
- **Société Générale SG CTA Index, SG Trend Index**: CTA 산업 벤치마크.
- **Simplify Managed Futures Strategy ETF (CTA)**: retail ETF.

#### 공개 수익률 (SG CTA Index)
| 연도 | 수익률 | 비고 |
|---|---:|---|
| 2019 | +10%대 | |
| 2020 | +5% 내외 | 코로나 |
| 2021 | +8% 내외 | |
| 2022 | **+20.1%** | 사상 최고 (인플레·금리 인상 추세) |
| 2023 | **−1.3% (YTD Aug) ≈ flat** | 추세 부재 |
| 2024 | **+2.4%** | flat |

→ CTA는 **‘평소엔 5~10%, 위기엔 +20%’**의 보험형 수익. 다만 2023~2024 같은 ‘추세 없는 횡보장’에서는 부진.

#### 반론
- CTA는 **레버리지(보통 2~5x)와 선물거래** 기반. KIS 미국주식 계좌에서는 직접 구현 어려움 → DBMF, KMLM, CTA(Simplify) 같은 ETF로만 접근.
- 위기 alpha를 위해 평소 부진 시기를 견뎌야 함. 심리적으로 어려움.

---

### 3.4 평균회귀 (Mean Reversion) — KIS 환경에서는 가장 위험

#### 정의
**평균회귀(Mean Reversion)** = 가격이 일시적으로 평균(20일 SMA, VWAP 등)에서 벗어나면 결국 돌아온다는 가설. RSI(2) < 10, BB(20,2) 하단 이탈, z-score < −2 등으로 진입 시그널.

#### 원리
- 단기에는 **유동성 수급**과 **공포-탐욕 cycle**이 비합리적으로 작동.
- 다만 추세장에서는 ‘**band walking**(밴드 위를 계속 걸음)’이 일어나 평균회귀 신호가 연속 손절 유발.

#### 알고리즘 (Connors RSI-2, retail 표준)
```
일봉:
  1. SPY 종가 > 200일 SMA   # 상승장만 trade
  2. RSI(2) < 10            # 단기 oversold
  진입 = 다음 시가 매수
  청산 = 종가가 5일 SMA 위로 올라오면 매도 (또는 5거래일 후 무조건 청산)
```

#### 학술 출처
- Poterba, J. & Summers, L. (1988) "Mean reversion in stock prices", *J. Financial Economics*.
- Connors, L. & Alvarez, C. (2009) "Short Term Trading Strategies That Work". Retail-oriented 책.
- Da, Z., Liu, Q., Schaumburg, E. (2014) "A closer look at the short-term return reversal", *Management Science*.

#### 운용사·ETF
- **Mean reversion 전용 ETF는 거의 없음**. AQR DELIX (Risk Parity), AQRIX (Risk Parity) 등은 평균회귀 일부 포함.
- 헤지펀드: **Two Sigma, Citadel** 등의 statistical arbitrage desk가 사용.

#### 공개 수익률
- **공개된 retail mean reversion ETF 부재** → 검증 어려움.
- 학술 backtest (1990-2010): 연 10~15% CAGR, **단 거래비용 차감 전**. Frazzini et al. (2020) AQR 보고서에 따르면 거래비용이 mean reversion 수익의 **50~80%를 잠식**.

#### 반론 / KIS 환경에서의 한계
**KIS 0.25% × 2 환경에서 평균회귀는 거의 무조건 적자.** 회전율 1,000~2,000%/년이라 비용 5~10%/년. 보통 학술 CAGR 10~15%가 거의 다 사라짐. **이는 INTRADAY_COMPARISON.md §3.2의 RSI-2 결과(WR 14%, Ret −3.6%)와 정확히 일치**.

---

### 3.5 통계적 차익거래 (Statistical Arbitrage) — retail 불가능

#### 정의
**통계적 차익거래(StatArb)** = 통계 모형(코인티그레이션, PCA 등)으로 가격 괴리를 잡아 high-frequency·high-leverage로 수익 추구. 페어 트레이딩이 가장 단순한 형태.

#### 원리
- 두 비슷한 자산(KO vs PEP, GOOG vs GOOGL, ETF vs underlying basket)이 통계적으로 균형 관계를 가져야 함.
- 일시적 괴리 → 두 자산을 long/short으로 잡으면 시장 방향 무관하게 수익.

#### 알고리즘 (페어 z-score)
```
1. universe = 같은 섹터 종목 쌍 (예: KO-PEP)
2. spread = log(KO) - log(PEP)
3. z = (spread - rolling_mean(spread, 60d)) / rolling_std(spread, 60d)
4. if z > 2:   short KO, long PEP
   if z < -2:  long KO, short PEP
   if |z| < 0.5: 청산
```

#### 학술 출처
- Gatev, E., Goetzmann, W., Rouwenhorst, K.G. (2006) "Pairs trading: Performance of a relative-value arbitrage rule", *RFS*.
- Avellaneda, M. & Lee, J.H. (2010) "Statistical arbitrage in the US equities market", *Quantitative Finance*.

#### 운용사
- **Renaissance Medallion (Jim Simons)**: 1988-2018 연 39% gross / 26% net (after fees), 자체 폐쇄(직원만). Sharpe 추정 ~3.0~4.0.
- **Two Sigma, DE Shaw, Citadel, Millennium**: HFT/StatArb 데스크.

#### 공개 수익률
| 펀드 | 기간 | 수익률 |
|---|---|---|
| **Renaissance Medallion** | 1988-2018 (30년) | 평균 +39%/년 (수수료 전), +26%/년(수수료 후), Sharpe ~3 추정 |
| Renaissance RIEF (public) | 2024 | ~9% (Medallion 대비 큰 차이) |
| Two Sigma Spectrum | 2024 | **+10.9%** |
| Two Sigma Absolute Return Enhanced | 2024 | **+14.3%** |
| Citadel Wellington | 2024 | **+15.1%** |
| Citadel Wellington | 2025 | +10.2% |
| DE Shaw Composite | 최근 10년 평균 | ~13%/년 (추정) |

#### 반론 / Retail 불가능 이유
1. **인프라**: 마이크로초 단위 latency, colocated server.
2. **자본**: 작은 알파를 큰 자본으로 곱해야 의미.
3. **수수료**: 0.25% × 2면 매 trade당 50bp 손실. StatArb 알파는 trade당 5~20bp.

→ **개인 투자자는 그 ETF나 펀드를 매수 보유로 ‘노출’만 가능**. 알고리즘 자체는 모방 불가.

---

### 3.6 리스크 패리티 (Risk Parity) — 안정성의 정점

#### 정의
**리스크 패리티(Risk Parity)** = 각 자산이 포트폴리오 총 리스크(변동성)에 같은 양 기여하도록 비중 결정. 통상 변동성 낮은 채권/원자재에 레버리지를 적용.

#### 원리
- 전통 60/40(주식/채권)은 자본 비중은 6:4지만 **리스크 비중은 90:10**. 사실상 주식 베팅.
- Risk Parity는 채권에 레버리지를 걸어 리스크 50:50으로 맞춤 → 단일 자산군 충격에 강함.

#### 알고리즘 (Bridgewater All Weather 단순화)
```
연 1회 (또는 분기):
  1. 4개 경제 환경에 25%씩 리스크 배분
     - 성장 ↑ 인플레 ↓: 주식 (SPY)
     - 성장 ↑ 인플레 ↑: 원자재 (DBC), 신흥국 채권
     - 성장 ↓ 인플레 ↓: 국채 (TLT) 레버리지
     - 성장 ↓ 인플레 ↑: 인플레연동채(TIPS), 금(GLD)
  2. 자산별 변동성 역수로 비중 조정 → 변동성 1%당 같은 risk
  3. 1.5~2.0x 레버리지로 목표 변동성 ~10% 맞춤
```

#### 학술 출처
- Asness, C., Frazzini, A., Pedersen, L.H. (2012) "Leverage aversion and risk parity", *Financial Analysts Journal*.
- Qian, E. (2005) "Risk Parity Portfolios", PanAgora.

#### 운용사
- **Bridgewater Associates (Ray Dalio)**: All Weather, Pure Alpha.
- **AQR Risk Parity Fund (AQRIX)**.
- **PanAgora, Putnam Risk Parity**.
- **SPDR Bridgewater All Weather ETF (ALLW)** — 2025-03 출시. 1.8x 레버리지. **개인 직접 매수 가능**.

#### 공개 수익률
| 펀드 | 기간 | 수익률 |
|---|---|---:|
| **Bridgewater All Weather (institutional)** | 1996-2024 평균 | ~7~9%/년, MaxDD 약 −20% |
| Bridgewater Pure Alpha Wellington | 2024 | **+15.1%** |
| Bridgewater Tactical Trading | 2024 | +22.3% |
| Bridgewater Equities | 2024 | +18% |
| Bridgewater Global Fixed Income | 2024 | +9.7% |
| **ALLW (SPDR All Weather ETF)** | 2025-03 ~ 2025-09 (6개월) | **+6.6%** (vs VOO +10.5%, AOR +7.7%) |

→ 2025년 ALLW는 SPY 대비 underperform — risk parity는 ‘bull market에서 따라가지 못함’이 정상.

#### 반론
- 채권 레버리지 사용 → 금리 상승기에 큰 손실. 2022년 다수 risk parity 펀드 −20% 이상.
- ALLW는 ETF로 출시되었으나 실거래 1년 미만 표본 부족.

---

### 3.7 변동성 타깃팅 (Volatility Targeting) — overlay 형태

#### 정의
**변동성 타깃팅(Vol Targeting)** = 자산의 실현 변동성을 목표 변동성(예: 연 10~15%)에 맞추기 위해 포지션 크기를 동적으로 조절. 다른 전략 위에 ‘overlay’로 얹는 게 일반적.

#### 원리
- 변동성 자체가 **변동성에 관성**(volatility clustering)을 보임 (GARCH).
- 변동성 높을 때 사이즈 줄이면 평균 손실 폭 감소 → Sharpe 개선.

#### 알고리즘
```
매 거래일:
  sigma_realized = std(daily_returns, lookback=20d) * sqrt(252)
  scale = vol_target / sigma_realized   # 예: 0.10 / 0.20 = 0.5
  position_size = base_position * scale
  # cap at 1.5x leverage
```

#### 학술 출처
- Moreira, A. & Muir, T. (2017) "Volatility-Managed Portfolios", *J. Finance*.
- Harvey, C. (2018) "Vol Timing".

#### 효과
- Moreira-Muir 2017: 모멘텀에 vol targeting overlay 시 Sharpe 0.5 → 0.9. 약 **+0.10~+0.20 Sharpe** 개선 (단, look-ahead bias 논쟁).
- Casper 봇에 적용: VIX 12~30 구간만 매매 = ad-hoc vol targeting의 일종.

---

### 3.8 이중 모멘텀 (Dual Momentum, Antonacci GEM) — retail 황금률

#### 정의
**이중 모멘텀(Dual Momentum)** = Gary Antonacci(2014) 제안. **절대 모멘텀**(자기 12개월 수익률이 T-Bill보다 높은가) + **상대 모멘텀**(미국 vs 비미국 어느 쪽이 강한가)을 결합.

#### 원리
- 모멘텀 단독: bull/bear 구분 못함.
- T-Bill 비교: 시장이 약하면 자동으로 현금으로 이동 → drawdown 방어.
- 미국 vs 비미국: 글로벌 자산 회전 → 더 좋은 모멘텀 자산 보유.

#### 알고리즘 (GEM 정확한 규칙)
```
매월 마지막 거래일:
  US_ret    = 12개월 총수익률 (SPY)
  ExUS_ret  = 12개월 총수익률 (VEU 또는 VXUS, ACWI ex-US)
  Bill_ret  = 12개월 총수익률 (BIL 또는 SHY)

  if max(US_ret, ExUS_ret) > Bill_ret:
      if US_ret > ExUS_ret:
          target = 100% SPY
      else:
          target = 100% VEU
  else:
      target = 100% AGG   # 미국 종합채권 (또는 BIL)

  # 매월 한 자산에 100% — 분산 없음
  # 매월 turnover 최대 200% (자산 갈아탈 때만)
```

#### 학술 출처
- Antonacci, G. (2014) *Dual Momentum Investing*, McGraw-Hill.
- Antonacci, G. (2017) "Risk premia harvesting through dual momentum", *J. Management & Sustainability*.

#### 공개 수익률 (Antonacci 발표 + 독립 검증)
| 백테스트 | 기간 | CAGR | MaxDD | 비고 |
|---|---|---:|---:|---|
| Antonacci 원본 (1974-2013) | 40년 | **~17%** | ~−20% | 책 출판 시 |
| SVRN 독립 검증 (1974-2015) | 41년 | ~16% | ~−22% | robust 확인 |
| 확장 (SPY/VXUS/IEF/BIL, 1974-2023) | 50년 | **+14.8%** | **−20.5%** | vs B&H 11.2%/−50.1% |
| Antonacci optimalmomentum.com 라이브 (2014-2024) | 11년 라이브 | 약 ~9% | 약 −20% | 백테스트 대비 ‘**out-of-sample 부진**’ |

#### 회전율·KIS 비용
- **연간 트랜잭션 평균 2~3회** (모멘텀 자산 변경 시).
- 회전율 ~100~200%/년 → KIS 비용 0.5~1.0%/년.
- **이게 retail 환경에서 거의 최적의 비용 효율**.

#### 반론
- Newfound Research (2019) "Fragility Case Study: Dual Momentum GEM" — **선택 자산이 단 2개**(SPY vs VEU)라 ‘fragile’. 추가 변종(GEM-multi, dual momentum sector rotation)이 더 안정적.
- 라이브 11년(2014-2024) 성과가 백테스트(40년)보다 낮음 → 모멘텀 decay 가능성.
- T-Bill 비교 기준만 사용해 ‘bear market 진입 직전’은 잡지 못함 (12개월 lag).

---

## 4. 그 외 retail-friendly 구체 알고리즘

### 4.1 Andreas Clenow — Stocks on the Move

#### 정의
Clenow(2015) *Stocks on the Move: Beating the Market with Hedge Fund Momentum Strategies*. **CS-MOM의 책 한 권짜리 retail 완성판**.

#### 알고리즘 (정확한 규칙)
```
매주 수요일:
  market_filter:
    SPY 종가 > 200일 SMA → ON
    아니면 신규 매수 금지 (기존 포지션 유지)

  for stock in S&P 500 universe:
    skip if 최근 90일 내 일중 갭 |Δ| >= 15%   # 점프 회피
    skip if 현재가 < 100일 SMA              # 추세 외 종목 제거
    score[stock] = exp_regression_slope(90일 로그수익률) * R_squared(90일 적합도)
    # = 모멘텀 강도 × 신뢰도

  ranked = sort(score, desc)
  target_count = top N (보통 20~30)
  position_size[stock] = (총자산 × 0.001) / ATR(20)
  # ATR-based: 모든 종목이 같은 risk 단위로 sized

  if (현재 포지션이 ranked top 20% 밖으로 빠짐) or (stock < 100SMA): sell

리밸런스: 매주 수요일 1회. 평소 2~5건 매매.
```

#### 백테스트 (Clenow 원본 + 독립 재현)
| 출처 | 기간 | CAGR | MaxDD | beta | 비고 |
|---|---|---:|---:|---:|---|
| Clenow 원본 (1999-2014) | 16년 | ~20%/년 | −24% | – | 책에 보고됨 |
| QuantConnect (1999-2020) | 21년 | **14.81%** | **−27.3%** | 0.516 | WR 59%, vs SPY 8.86% |
| TuringTrader (확장) | 2000-2024 | ~12% | ~−30% | – | – |

#### 회전율
- 매주 수요일 리밸런스, 매주 평균 2~5건 매매 → 연간 100~250 trades.
- **20~30 종목 × 100~200% turnover** ≈ KIS 비용 0.5~1.0%/년.

#### KIS 환경 적합성
- **OK**: 회전율 합리적, MaxDD −27%로 견딜 만함, ATR 사이징으로 risk balance.
- **주의**: 종목 20~30개를 동시 보유 → 미국주식 계좌 자본 최소 $10,000+ 권장 (각 종목 $300~500).

---

### 4.2 Meb Faber — GTAA (Global Tactical Asset Allocation)

#### 정의
Faber, M. (2007) "A Quantitative Approach to Tactical Asset Allocation", SSRN. **세상에서 가장 단순한 모멘텀 TAA**.

#### 알고리즘 (GTAA-5)
```
universe = [SPY (미국주식), EFA (선진국주식), DBC (원자재), IEF (미국채), VNQ (REIT)]
weight = 20% each   # 동일 비중

매월 말:
  for each asset:
    if 자산 종가 > 10개월 SMA:
      hold (20%)
    else:
      cash (BIL 20%)

# 5자산 × 200% turnover 한도 = 연 50~100% turnover (계산 단순화)
```

#### GTAA-13 (확장판)
13개 자산: SPY, IWM, EFA, EEM, VNQ, RWX, DBC, GLD, TIP, IEF, TLT, BIL, AGG. 각 1/13. 동일 SMA 규칙.

#### 백테스트
| 버전 | 기간 | CAGR | MaxDD | Buy&Hold 60/40 |
|---|---|---:|---:|---|
| GTAA-5 (Faber 1973-2012) | 39년 | **~10%** | **<−10%** | B&H 60/40 ~9% / −46% |
| GTAA-13 (1973-2012) | 39년 | ~10% | <−10% | – |

→ **MaxDD −10% 미만 = 거의 모든 ‘투자 책’ 전략 중 가장 낮은 drawdown**. CAGR은 평범하지만 Calmar 비율(=CAGR/|MaxDD|)이 1.0 수준 (60/40은 0.2).

#### KIS 환경 적합성
- **최적**: 5자산 × 월 1회 ON/OFF = 회전율 50~100%/년 = 비용 0.25~0.50%/년.
- 자본 최소 $2,000+ (각 자산 $400 이상).

---

### 4.3 Wesley Gray — QMOM (Quantitative Momentum)

#### 정의
Gray, W. & Vogel, J. (2016) *Quantitative Momentum*. **CS-MOM의 학술적 정밀화**: 모멘텀 + ‘smooth momentum’(연속성) 필터.

#### 알고리즘
```
분기 (3개월) 마지막 거래일:
  universe = 미국 mid-large cap (S&P 1500 또는 IWB 보유 종목)

  step 1: 12-1 momentum 상위 20% 선별
  step 2: 그 중 'FIP score' = 양봉일 비율 - 음봉일 비율   # smooth momentum
         smooth 상위 50% 선택   # 점프식 상승 vs 꾸준한 상승 우선
  step 3: top 50개를 동일가중 매수

다음 분기말 같은 절차로 갈아끼움.
```

#### 출처
- Gray & Vogel (2016) Wiley.
- 운용: Alpha Architect (QMOM ETF, AUM ~$200M).

#### 공개 수익률
- QMOM 2024: +(데이터 부족, 모멘텀 비교적 약함).
- QMOM 2025: **+2.4%** (대형 모멘텀에 underperform — 의도적으로 ‘smooth’만 잡아 NVDA 같은 점프 모멘텀 회피).
- QMOM 2026 YTD: **+18.6%** (회복).

#### 회전율
- 분기 리밸런스 50개 종목 100% 교체 가정 시 turnover ~400%/년 → KIS 비용 2.0%/년 (높음).
- 실제 리밸런스 시 중복 종목 많으므로 200~300% (1.0~1.5% 비용).

---

### 4.4 TQQQ + 200-day SMA (단일자산 추세추종)

#### 정의
가장 단순한 ‘TQQQ 보유/현금 ON-OFF’ 규칙. **레버리지 ETF + 추세 필터**의 retail favorite.

#### 알고리즘
```
일봉 (또는 주봉):
  if QQQ 종가 > 200일 SMA (1% 버퍼):
      target = 100% TQQQ
  else:
      target = 100% BIL (현금)
  # 매매는 신호 변화 시에만 1회
```

#### 백테스트 (2011-2025)
| 항목 | 매수보유 | 200MA 시스템 |
|---|---|---|
| 누적수익 | **+10,806%** | **+4,067%** |
| MaxDD | **−81.7%** | **−69.9%** |
| 자본 곡선 | 변동성 폭발 | 변동성 완화 |

→ **누적수익은 매수보유가 우위지만 MaxDD가 −81% → 사람이 못 견디고 손절**. 200MA 시스템은 수익 절반 + MaxDD 12%p 개선.

#### QQQ 24년 (2000-2024)
| 항목 | 매수보유 | 200MA 시스템 |
|---|---|---|
| 누적수익 | **+428%** | **+791%** |
| MaxDD | **−83%** | **−28.6%** |

→ 24년 기간 (닷컴 버블 포함)에선 시스템이 **누적도 크게 압도** + MaxDD 1/3.

#### KIS 환경 적합성
- 매매 횟수 연 2~4회 → 회전율 200~400%/년 → KIS 비용 1.0~2.0%/년.
- TQQQ 3x 레버리지 + 200MA 추세필터 = ‘월간 추세장’에서 극단적 수익.

#### 주의
- **변동성 감쇠(Volatility Decay)**: TQQQ는 매일 리밸런스되어 횡보장에서 손실 누적. 200MA로 횡보 회피해도 짧은 whipsaw 위험.
- 2020-03 코로나, 2022 약세장에서 200MA가 **늦게** 신호를 줘 −30% 발생.

---

## 5. 轉 — KIS 0.25% × 2 환경의 비용·세금·환차 현실

### 5.1 비용 분해 (다시)

이미 INTRADAY_COMPARISON.md §0에서 정리한 비용을 보강·확장한다.

| 항목 | 값 | 적용 |
|---|---|---|
| 매수 수수료 | **0.25%** | 매수 시 (KIS 미국주식 기본) |
| 매도 수수료 | **0.25%** | 매도 시 |
| 매수 슬리피지 | ~0.05% | limit 가정 |
| 매도 슬리피지 (limit/TP) | ~0.05% | |
| 매도 슬리피지 (시장가/SL) | ~0.10% | stop trigger 후 market |
| SEC fee (매도만) | $0.0000278/$ ≈ 0.003% | |
| FINRA TAF (매도만) | $0.000166/share ≈ 0.001% | |
| **환전 스프레드** (전신환매도/매수) | **~0.20%** (왕복) | USD ↔ KRW 환전 시. 기본 환율 우대 0% 가정. 우대 50% 시 0.10%. 우대 95% 시 0.02% |

> **이벤트 수수료**: KIS는 신규/휴면 고객 최초 3개월 무료, 이후 9개월 0.09%로 적용되는 이벤트가 종종 있음. STRATEGY_REVIEW.md §4.3에 정리. **그러나 본 문서는 ‘이벤트 종료 후 기본 0.25%’ 가정**으로 진행 (보수적).

### 5.2 회전율 × 비용 매트릭스

자본 대비 연간 비용 = `Turnover × Round-trip cost`

| 전략 | Turnover | Round-trip cost | 연 비용 | 살아남나? |
|---|---:|---:|---:|---|
| Casper 데이트레이딩 RR3 (60일 3건) | 18회/년 × 600% pos = **~150%/년** | 0.60% | **0.9%** | 매매 자체가 너무 적어 비용 미미 |
| **저빈도 GEM 월간** | 2-3 transaction/년 = ~200% | 0.60% | **1.2%** | ✓ |
| **Faber GTAA-5 월간** | 100%/년 (5자산 ON/OFF) | 0.60% | **0.6%** | ✓✓ |
| **Clenow Stocks-on-the-Move 주간** | 200~300%/년 | 0.60% | **1.5%** | ✓ (CAGR 14%로 흡수 가능) |
| **SPMO/MTUM 매수보유** | 0~10%/년 (리밸런스 자동) | 0% (보유) | **0%** | ✓✓✓ (ETF 내부 비용비율 0.13~0.15%만) |
| **TQQQ + 200MA** | 200~400%/년 | 0.60% | **1.2~2.4%** | △ (CAGR 강하면 OK) |
| **QMOM 분기** | 200~400%/년 | 0.60% | **1.2~2.4%** | △ |
| **모멘텀 monthly CS-MOM** | 500~800%/년 | 0.60% | **3.0~4.8%** | ✗ |
| **Mean Reversion RSI-2** | 1,000~2,000%/년 | 0.60% | **6~12%** | ✗ (불가) |
| **Statistical Arbitrage** | 10,000%+ | 0.60% | **60%+** | ✗✗ (불가) |

### 5.3 한국 양도소득세 22% 영향

- **세율**: 양도차익 × 22% (지방세 2% 포함)
- **기본공제**: 연 250만 원 (약 $1,800 at 1,400 KRW/USD)
- **세금 신고**: 매년 5월 (전년도 1/1~12/31 매매 차익)
- **손익통산**: 같은 해 내 미국주식 손익 합산 가능. **이월 불가**.
- **환율 평가**: 매매 시점 환율로 계산 (USD 차익이 아닌 KRW 차익 기준)

#### 효과
- **확정 수익 → 세후 78%만 남음** (250만 원 초과분).
- 같은 해 손실은 같은 해 이익과 상계 가능. **연말 손실 종목 매도(tax loss harvesting)**가 유효 전략.
- 미실현 이익은 세금 없음 → **buy-and-hold가 세금상 가장 유리**.

#### 회전율과 세금 상호작용
| 전략 | 미실현 vs 실현 비율 | 세금 부담 |
|---|---|---|
| 매수보유 (SPMO 등) | 거의 100% 미실현 | 매도 시점에만 부과 |
| 월간 리밸런스 (GEM) | 100% 실현/년 | 매년 22% 세금 |
| 데이트레이딩 (Casper) | 100% 실현/년 | 매년 22% 세금 |

→ **세금 효율성에서 매수보유가 압도적**. GEM/Clenow도 매수보유 대비 매년 22% × (실현분) 누수.

#### 예시
$10,000 자본, 연 +15% 수익 ($1,500) 가정:
- **매수보유**: 22% × max(0, $1,500-$1,800) = $0 세금. 순익 $1,500.
- **GEM 월간 리밸런스**: 매년 실현. 22% × ($1,500 - $1,800) = $0 세금 (이 해는 공제 한도 내). 다음 해도 비슷 가정.
- **자본 증가 후 ($20,000, 연 +15% = $3,000)**: 22% × ($3,000 - $1,800) = $264 세금. 순익 $2,736.

### 5.4 환차익·환전 스프레드

KIS USD ↔ KRW 환전: 기본 스프레드 약 1% (왕복 2%). **환율 우대 95%** (모바일 신청) 시 약 0.05% (왕복 0.10%).

#### 두 가지 가정 시나리오
**A) 환전 없음 (USD 잔고 내 매매)**: 이미 USD를 보유 중. 매매는 0% 환전 비용.
**B) 매번 환전**: KRW로 입금하고 매매 시 환전, 매도 후 KRW로 환전. 왕복 0.10%~2% 추가.

**권장**: KRW → USD 한 번 환전 후 USD 잔고 내 매매. 익절·손절 후에도 USD로 보유. 1년에 한 번 KRW로 인출 시에만 환차 발생.

---

## 6. 종목 선정 방법 (Universe Selection)

각 전략별 universe + 필터링 규칙.

### 6.1 단일 자산 (ETF, 가장 단순)
| ETF | 추적 자산 | 일평균 거래량 | 사용처 |
|---|---|---|---|
| **SPY / VOO / IVV** | S&P 500 | $20~30B | 코어 보유 |
| **QQQ / QQQM** | Nasdaq-100 | $15B | 기술주 베타 |
| **TQQQ / SQQQ** | Nasdaq-100 3x bull/bear | $5B | 단일자산 추세추종 (Casper) |
| **MTUM / SPMO / VFMO** | 모멘텀 팩터 | $0.5~2B | 모멘텀 노출 |
| **QUAL / SPHQ** | 우량 팩터 | $1~2B | 안정 코어 |
| **VLUE / IVE** | 가치 팩터 | $0.5~1B | 다각화 |
| **USMV / SPLV** | 저변동 팩터 | $1~3B | 변동성 보호 |
| **VEU / VXUS / IEFA** | 미국 외 선진국 | $2~5B | GEM ex-US |
| **EEM / VWO** | 신흥국 | $3~5B | 위험자산 분산 |
| **AGG / BND / TLT / IEF** | 미국채 | $2~10B | GEM 안전자산 |
| **BIL / SHV** | 단기 T-Bill | $5~10B | 현금 등가 |
| **DBC / GSG** | 원자재 | $0.3~1B | 인플레 헤지 |
| **GLD / IAU** | 금 | $5~10B | 인플레/위기 헤지 |
| **VNQ / IYR** | REIT | $1~3B | 인플레/금리 |

### 6.2 개별 주식 (CS-MOM, Clenow, QMOM)
| 기준 | 권장값 | 이유 |
|---|---|---|
| 시가총액 | $1B+ (S&P 1500 또는 Russell 1000) | 유동성 |
| 일평균 달러 거래량 | $20M+ | 30주 매매에 충분 |
| 가격 | $5+ (penny stock 제외) | 거래소 상장 표준 |
| 점프 필터 (Clenow) | 최근 90일 단일일 |수익률| < 15% | M&A·실적 surprise 회피 |
| 추세 필터 (Clenow) | 종가 > 100일 SMA | 하락 종목 제외 |

### 6.3 종목 ranking 점수 — 4가지 표준 방법

| 방법 | 수식 | 강점 | 약점 |
|---|---|---|---|
| **12-1 momentum (Jegadeesh-Titman)** | ret(−12 ~ −1m) | 학술 표준, 단순 | 점프성 모멘텀에 취약 |
| **6-1 momentum** | ret(−6 ~ −1m) | 빠른 회전, 강한 시그널 | 단기 노이즈 |
| **Volatility-adjusted slope (Clenow)** | slope_90d × R²_90d | 신뢰도 가중 | 계산 복잡 |
| **FIP smooth momentum (Gray)** | 양봉일 비율 − 음봉일 비율 | 점프 회피, 안정성 | 강한 단기 모멘텀 놓침 |

---

## 7. SL / TP / 청산 규칙 핸들링

### 7.1 저빈도 퀀트의 청산은 ‘리밸런스’

데이트레이딩(Casper)의 명시적 SL/TP와 달리, **저빈도 퀀트는 정기 리밸런스가 곧 청산**이다.

| 전략 | 청산 트리거 | 명시적 SL? | 명시적 TP? |
|---|---|---|---|
| **GEM (월간)** | 매월 말 자산 비교 후 갈아탐 | 없음 (다음 month 비교에서 자동 처분) | 없음 |
| **Faber GTAA (월간)** | 종가 < 10개월 SMA | 자산별 SMA 이탈 | 없음 (계속 보유) |
| **Clenow (주간)** | top 20% 밖 또는 100SMA 이탈 | 100SMA | 없음 |
| **QMOM (분기)** | 분기 말 새 top 50으로 갈아탐 | 분기 단위만 | 없음 |
| **SPMO 매수보유** | 절대 청산 안 함 (또는 은퇴 시점) | 없음 | 없음 |
| **Casper 데이트레이딩** | **명시적 SL/TP, BE shift, EOD 강제** | FVG 캔들 저점 | R:R 1:3 |

### 7.2 옵션 1 — pure 리밸런스 (학술 표준)

- 매월/매분기 정해진 날에 점수 재계산 → 새 universe 매매
- **장점**: 단순, 감정 개입 없음, 학술 검증
- **단점**: 큰 drawdown을 ‘다음 리밸런스까지 견뎌야’

### 7.3 옵션 2 — 리밸런스 + 트레일링 스톱

- 리밸런스 후 보유 종목별로 **−10% trailing stop** (또는 ATR × 3) 설정
- 손절 발동 시 그 자리만 cash로 두고 다음 리밸런스 대기
- **장점**: 큰 사고 방어
- **단점**: whipsaw 손절 증가 (잔잔한 약세장에서)

### 7.4 옵션 3 — regime filter (Clenow 방식)

- SPY 200일 SMA 위에서만 신규 매수
- 200SMA 깨지면 신규 매수 정지, 기존 포지션은 개별 100SMA 이탈 시 청산
- **장점**: 시장 전체 약세 시 자동 cash
- **단점**: 200SMA 신호가 늦어 −10~−20% 손실 후 청산

### 7.5 옵션 4 — vol targeting overlay

- 보유 중 포지션 사이즈를 daily realized vol에 따라 매일 스케일
- vol_target=15%, sigma_realized=30% 면 사이즈 50%
- **장점**: 변동성 폭발 시 자동 사이즈 축소
- **단점**: 매일 미세 조정 → 회전율 200~500%/년 추가

### 7.6 권장 조합

| 전략 | 권장 청산 방식 |
|---|---|
| **GEM** | pure 월간 리밸런스 (옵션 1). Antonacci 원본 그대로. |
| **Faber GTAA** | SMA 이탈 시 cash (옵션 1 + 2 자체 포함). |
| **Clenow** | regime filter + 100SMA stop (옵션 3). 원본대로. |
| **QMOM** | pure 분기 리밸런스 (옵션 1). |
| **SPMO 매수보유** | regime filter (옵션 3) — SPY 200SMA 깨지면 50% 현금화. |
| **TQQQ + 200MA** | 단일 SMA 신호 (옵션 1 + 3 결합). |

---

## 8. 리스크 관리 (Risk Management)

### 8.1 포지션 사이징

**개별 종목 매매 시 (Clenow, QMOM)**:
- ATR(20)-based: `shares = (총자산 × 0.001) / ATR_20`
  - 의미: 종목별로 ‘하루 일평균 변동폭이 총자산의 0.1%’가 되도록 사이즈
  - 모든 종목이 같은 risk 단위 (변동성 낮은 우량주 더 많이, 변동성 큰 종목 적게)
- Equal-weight 대안: `shares = (총자산 / N) / 현재가`. 단순하지만 변동성 큰 종목이 위험 비중 과다.

**자산배분 시 (GEM, Faber, Risk Parity)**:
- 비중 = 학술 표준 (균등 또는 vol-weighted)
- Risk Parity: 자산별 var 역수 가중
- vol target overlay: 매일 σ_realized 측정 후 scale

### 8.2 Kelly Criterion (참고)

**Kelly Criterion** = ‘이론적으로 자본 성장 최대화’ 베팅 사이즈.

- Kelly f = (WR × R:R - (1-WR)) / R:R
- 예: WR 0.43, R:R 2 → Kelly f = (0.43×2 - 0.57)/2 = 0.145 = **자본의 14.5%/trade**

> **실무에서는 Half-Kelly (7.25%) 또는 Quarter-Kelly (3.6%) 사용** — 백테스트 수치가 과대 추정인 경우 Full Kelly는 50%+ drawdown 유발.
> **Casper의 “잔액 전부 매수” 규칙은 Full Kelly의 1주 단위 근사**이다. RR 1:3, WR ~38%면 Kelly ~17% — 잔액 전부 매수는 over-bet이지만 1개 종목 1회/일 매매라 분산 부족을 자본 풀 사용으로 보상하는 디자인.

### 8.3 서킷브레이커 (Circuit Breaker)

데이트레이딩에서만 쓰는 게 아님. 저빈도 퀀트에도 다음 규칙이 유효:

| 트리거 | 액션 |
|---|---|
| MaxDD < −20% | 신규 매수 정지, 회복까지 대기 |
| 3개월 누적 −10% | 사이즈 50% 축소 |
| 6개월 누적 −15% | 전략 재검토 |
| 연 누적 −25% | **전략 폐기 검토** (mean reversion 강제, 또는 잠시 cash) |

### 8.4 Diversification

| 차원 | 분산 방법 |
|---|---|
| 자산군 | 주식 + 채권 + 원자재 + 금 + REIT (GEM-multi, Faber GTAA-13) |
| 지역 | 미국 + 비미국 (VEU) + 신흥국 (EEM) |
| 팩터 | Momentum + Value + Quality + Low-Vol (멀티팩터) |
| 시간 | 다른 회전율 전략 결합 (저빈도 + 고빈도) |

### 8.5 ‘Tail Risk’ 보호

**Tail Risk** = 정상 분포 가정으로는 극히 드물지만 실제로는 자주 일어나는 극단 손실.

| 도구 | 비용 | 효과 |
|---|---|---|
| **VIX call ETF (VIXY)** | 매년 ~10%+ decay | 위기 시 +100~300% |
| **장기국채 TLT** | 캐리 비용 ~0 | 위기 시 +10~30% (단, 2022 같은 인플레 위기엔 실패) |
| **Gold (GLD)** | 캐리 비용 ~0 | 위기 시 +10~20% |
| **현금 (BIL)** | 기회비용 만 | 손실 0 |
| **Put options on SPY** | 매년 1~3% premium | 위기 시 +50~300% |

→ **GEM은 자동 현금 회피로 tail 일부 방어. Faber GTAA는 다자산 SMA로 자동 tail 방어. 둘 다 ‘저렴한 보호’**.

---

## 9. 예상 수익률 (시나리오 분석)

KIS 0.25% × 2 + 양도소득세 22% + 환차 0.10% 모두 반영한 **세후·비용후 기대 CAGR**.

> 가정: 자본 $10,000 + 환율 우대 95% + USD 잔고 매매 (1회만 환전).
> 양도세는 매매 차익 250만 원 초과분에만 22% 적용 가정.

### 9.1 ETF 매수보유

| 전략 | 보유 자산 | 비용/년 | 세전 CAGR | 세후 CAGR (자본 $10k 가정) | MaxDD |
|---|---|---:|---:|---:|---:|
| **SPY 매수보유** | SPY | 0.03% | ~10% | ~9% (세금 약간) | −34% (2020) / −56% (2008) |
| **SPMO 매수보유** | SPMO | 0.13% | **+19% 10yr** | ~15% 세후 | ~−25% |
| **MTUM 매수보유** | MTUM | 0.15% | +15% 10yr | ~12% 세후 | ~−25% |
| **QUAL 매수보유** | QUAL | 0.15% | +12% 10yr | ~10% 세후 | ~−30% |
| **TQQQ 매수보유** | TQQQ | 0.84% | +20%~+100%/년 | 세후 후 +15~70% | **−81.7%** ← 사람이 못 견딤 |

### 9.2 정해진 알고리즘

| 전략 | 회전율 | 비용/년 | CAGR (이론) | CAGR (KIS 후) | CAGR (세후) | MaxDD |
|---|---:|---:|---:|---:|---:|---:|
| **GEM (Antonacci)** | ~150% | 0.9% | 14.8% | **13.9%** | **~12%** (250만 공제 후) | −20.5% |
| **Faber GTAA-5** | ~100% | 0.6% | 10% | **9.4%** | ~8% | <−10% |
| **Faber GTAA-13** | ~120% | 0.7% | 10% | **9.3%** | ~8% | <−10% |
| **Clenow Stocks-on-the-Move** | ~250% | 1.5% | 14.8% | **13.3%** | ~11% | −27.3% |
| **QMOM** | ~300% | 1.8% | 12%(추정) | **10.2%** | ~9% | ~−35% |
| **TQQQ + 200MA** | ~300% | 1.8% | 25%(매우 가변) | **23%** | ~19% | −70% (2020·2022) |
| **AQR QSPIX 복제** | ~500% | 3.0% | 7%(10yr) | **4%** | ~3% | −41.4% |
| **CS-MOM monthly (학술)** | ~700% | 4.2% | 12% | **7.8%** | ~6% | ~−40% |

### 9.3 Casper 데이트레이딩 (이미 측정됨)

| 전략 | 회전율 | 비용/년 | CAGR (이론) | CAGR (실제 60일 표본) |
|---|---:|---:|---:|---:|
| **Casper RR3 (production)** | ~18 trades/년 = ~5% | 0.03% | ?% | **−0.06%** (60일) → 연환산 −0.36% |
| **Casper RR2 (옵션)** | 같음 | 0.03% | ?% | **+0.49%** (60일) → 연환산 +3.0% |
| STRATEGY_REVIEW.md 백테스트 (Casper 23회/60일) | ~70 trades/년 | 0.42% | +11.21%/60일 → **+67%/년** | **+5.6%/월** (백테스트, 표본 23건) |

→ **Casper는 백테스트 23건일 때 매우 강하나 (60일 +11%), 실거래 production 60일 표본은 3건뿐**. 표본 크기가 적어 ‘진짜 CAGR’ 추정 폭이 매우 넓다 (−5% ~ +50%).

### 9.4 종합 비교 (수익적 측면, KIS 0.25% × 2 환경)

| 전략 | 기대 CAGR | MaxDD | 회전율 | 매매 일수/년 | 노동 강도 | KIS 비용/년 | 세후 추정 CAGR |
|---|---:|---:|---:|---:|---|---:|---:|
| **SPMO 매수보유** | 18% | −25% | 0% | 0 | 매우 낮음 | 0% | ~15% |
| **GEM** | 14.8% | −20.5% | 150% | 12 | 낮음 | 0.9% | ~12% |
| **Clenow** | 14.8% | −27% | 250% | 52 | 중간 | 1.5% | ~11% |
| **Faber GTAA** | 10% | <−10% | 100% | 12 | 낮음 | 0.6% | ~8% |
| **TQQQ+200MA** | 23% | −70% | 300% | 4 | 낮음 | 1.8% | ~19% (변동성 매우 큼) |
| **Casper RR3 (production)** | 5~30%(매우 가변) | −2% | ~150% (포지션 기준) | ~18 일 | **매우 높음** (스캔·체결 모니터링) | 0.9% | ~3~20% |
| **AQR QSPIX 복제** | 7% | −41% | 500% | 50+ | 매우 높음 | 3.0% | ~3% |

### 9.5 결합 포트폴리오 시나리오

#### 시나리오 A: 보수 (코어 ETF 70% + 위성 30%)
- 70% SPMO 매수보유 → 세후 ~15% × 0.70 = 10.5%
- 20% GEM → ~12% × 0.20 = 2.4%
- 10% Casper RR3 → ~5% × 0.10 = 0.5%
- **합계 13.4% / MaxDD 약 −25%**

#### 시나리오 B: 균형 (다각화 50/50)
- 30% SPMO → 4.5%
- 30% GEM → 3.6%
- 20% Clenow → 2.2%
- 20% Casper → 1.0%
- **합계 11.3% / MaxDD 약 −22%**

#### 시나리오 C: 공격 (모멘텀 집중)
- 50% TQQQ+200MA → ~9.5%
- 30% Clenow → 3.3%
- 20% Casper → 1.0%
- **합계 13.8% / MaxDD 약 −45%** (TQQQ 비중 큼)

#### 시나리오 D: 데이트레이딩 전부
- 100% Casper RR3 → ~5%/년
- **합계 5% / MaxDD −2%** (현재 측정)

→ **시나리오 A·B가 ‘리스크 조정 수익’ 면에서 우세**. Casper 단독은 위험 회피적이나 자본 효율이 낮음.

---

## 10. Casper 데이트레이딩 vs 저빈도 퀀트 — 직접 비교

### 10.1 정량 비교

| 차원 | **Casper (데이트레이딩)** | **GEM (저빈도)** | **Clenow** | **SPMO 매수보유** |
|---|---|---|---|---|
| **연 매매 빈도** | ~18회 진입(60일 3건) | 2-3회 자산 갈아탐 | ~250 trades | 0~1회 |
| **포지션 보유 기간** | 평균 22분 | 1~12개월 | 4~26주 | 영구 |
| **연 회전율 (자본 기준)** | ~150% | ~150% | ~250% | ~0% |
| **연 비용 (KIS 0.25%×2)** | ~0.9% | ~0.9% | ~1.5% | ~0% |
| **연 세금 (실현분 22%)** | 22% × 실현차익 | 22% × 실현차익 | 22% × 실현차익 | **0** (미실현) |
| **이론 CAGR (세전·비용전)** | +11.2%(백테)·또는 +5%(실거래) | +14.8% | +14.8% | +19% |
| **세후·비용후 CAGR (10k 가정)** | ~3~10% | ~12% | ~11% | ~15% |
| **MaxDD** | −2~−5% (90분 한정·BE shift) | −20.5% | −27% | −25% |
| **Sharpe (추정)** | ~1.5(불확실) | 0.7 | 0.6 | 1.0 |
| **노동 강도 (사람이 직접 봐야 하는 시간)** | 매일 90분(스캔) + 대기 | 월 1회 5분 | 주 1회 30분 | 없음 |
| **알고리즘 복잡도** | 상태머신 6단계 + FVG + ORB + ICT | 단순 ranking | 중간 | 없음 |
| **운용 인프라** | 봇 24/7 운영 + KIS 토큰 + 텔레그램 | 매월 수동 가능 | 매주 수동 가능 | 없음 |
| **장점** | 오버나잇 0, MDD 작음, FOMC 회피 | 자동 cash 회피, drawdown 보호 | 분산, ATR sizing | 세금 효율, 0 노동 |
| **단점** | 표본 적음, 60일 3건 = 자본 놀이 | 단일 자산만 보유 (Antonacci fragile) | 종목 20+ 필요 | bear market 풀로 맞음 |

### 10.2 ‘수익적 측면’의 정성 비교 — 사용자가 가장 궁금해할 부분

#### Casper가 우세한 측면
1. **MaxDD가 압도적으로 작다 (−2~5% vs 저빈도 −20~30%)**.
   - 오버나잇 보유 안 함 + EOD 강제 청산 + BE shift → 큰 사고 차단.
   - 심리적 안정. 시장 큰 폭락 (2020-03, 2022-09) 무관.
2. **Casper의 strict filter는 ‘비용 회피라는 알파’**.
   - 60일 3건만 매매 = 비용 0.9%만 발생.
   - 같은 60일 Holy Grail 36건 = 비용 5%.
3. **세금 측면에서 손익통산이 즉시**.
   - 같은 해 손실/이익이 매일 발생 → 같은 해 안에서 통산.
   - 저빈도는 ‘이번 해는 +30%, 다음 해는 −20%’ 식 변동 → 첫 해에 22% 세금 후 다음 해 보전 불가.

#### Casper가 약세인 측면
1. **자본 효율성 매우 낮음**.
   - 60일 3건 = 자본의 95% 일자가 ‘유휴 상태’.
   - $10,000 × 95% × 365일 = 9,490일 어치 무이자 현금.
   - 만약 그 95%를 GEM에 두면 12% × 0.95 = 11.4%/년 추가.
2. **표본 부족 → 진짜 CAGR 추정 불가**.
   - 60일 3건은 통계적으로 ‘0건과 같은 정보 가치’.
   - STRATEGY_REVIEW.md §7의 23건 백테스트(+11.21%)는 promising하지만 23건 ≪ 200건 (학술 권장).
3. **노동 강도가 높음**.
   - 매일 ET 09:30 ~ 11:00 (KST 23:30~01:00) 모니터링.
   - 텔레그램 알람·체결 확인·시그널 검토.
   - 봇이 자동이라도 운영자가 매일 신경 써야 함.
4. **시장 ‘추세 일변도’ 환경에서 매매 없음**.
   - INTRADAY_COMPARISON.md §3.1: 60일 중 25일(42%) TREND_UP/DOWN, 그 중 Casper 진입 1건뿐.
   - “시장이 ORB 깨고 FVG 없이 추세 지속” = Casper의 사각지대.
   - **저빈도 모멘텀 전략은 정확히 이 추세장에서 활약** → 보완재 관계.

#### 저빈도 퀀트가 우세한 측면
1. **자본 효율성 최대**.
   - 365일 × 100% 시장 노출.
   - SPMO/MTUM/GEM은 ‘bear가 아니면 항상 시장 안’에 있음.
2. **세금 효율 (특히 매수보유)**.
   - 미실현 = 세금 무한 연기.
   - 매수보유 + 은퇴 시 거주국 변경 = 사실상 무세금 가능.
3. **노동 강도 거의 0**.
   - 매월 1회 5분 ~ 매주 1회 30분.
   - 자동화 안 해도 운영 가능.
4. **추세장에서 강력**.
   - SPMO 2024 +45.8%, 2025 +26.6%, 2026 YTD +23%.
   - 같은 기간 Casper 60일 +0.49% (실거래) 또는 +11.21% (백테스트 23건).

#### 저빈도 퀀트가 약세인 측면
1. **MaxDD가 크다 (−20~30%)**.
   - 2020-03, 2022-09 같은 폭락 시 자본 1/4 손실.
   - 저빈도 시그널이 늦게 cash로 회피 (200SMA 등).
2. **양도세 부담**.
   - 매년 실현 차익에 22% 누수.
   - 250만 원 공제 한 번만, 이월 불가.
3. **모멘텀 크래시 위험**.
   - 2009-03 모멘텀 −40%, 2020-03 모멘텀 −20%.
   - SPMO 단독 보유 시 노출.
4. **단일 자산 fragile (GEM 특히)**.
   - Newfound 2019 비판: SPY vs VEU 2개 자산 비교가 미세한 차이로 결정 → 12월 1일 매수 vs 12월 31일 매수가 결과 다름.

### 10.3 ‘대체 vs 보완’ 판단

| 비교 | 대체관계? | 보완관계? | 평가 |
|---|---|---|---|
| Casper(데이트레이딩) vs GEM(저빈도) | △ | **✓ 강함** | 매매 빈도, 보유기간, drawdown, 세금 효율 모두 정반대 |
| Casper vs Clenow | △ | ✓ | Casper 1자산(TQQQ), Clenow 20+ 종목 분산 |
| Casper vs SPMO 매수보유 | ✗ | ✓ | 매수보유는 매도 시점 컨트롤 안 됨, Casper 매도 컨트롤 강함 |
| GEM vs Clenow | ✓ 약간 | △ | 둘 다 모멘텀, 다만 자산군 vs 종목 |
| SPMO 매수보유 vs GEM | ✗ | ✓ | 매수보유는 항상 시장, GEM은 자동 cash |

→ **Casper는 저빈도 퀀트의 ‘완벽한 보완재’**. 둘이 같은 자본을 차지하기보다, 다른 자본 풀에 들어가는 게 합리적.

### 10.4 ‘얼마를 어디에 배분할 것인가’ — 권고

#### 자본 $1,000 (소형) — 단순화 권장
| 비중 | 전략 |
|---|---|
| 100% | **GEM 또는 Faber GTAA-5** (월 1회 리밸런스, 노동 거의 0) |
| 0% | Casper (자본 너무 적어 매매당 비용 비율 과대) |

#### 자본 $5,000~$15,000 (중형) — 균형
| 비중 | 전략 |
|---|---|
| 40~50% | **SPMO 매수보유** (코어, 모멘텀 노출) |
| 30~40% | **GEM 또는 Faber GTAA** (TAA, 자동 cash 회피) |
| 10~20% | **Casper RR3** (데이트레이딩, alpha 추구) |

#### 자본 $30,000+ (대형) — 다각화
| 비중 | 전략 |
|---|---|
| 30% | **SPMO + MTUM + QUAL** (멀티팩터 코어) |
| 25% | **GEM** |
| 20% | **Clenow Stocks-on-the-Move** (개별주 모멘텀, 종목 20+) |
| 15% | **TQQQ + 200MA** (레버리지 베타) |
| 10% | **Casper** (데이트레이딩) |

---

## 11. 結 — 종합 권고

### 11.1 핵심 메시지

1. **KIS 0.25% × 2 환경의 ‘가장 큰 변수는 회전율’**.
   - 회전율 0%(매수보유) → 비용 0%, 세금 거의 0%
   - 회전율 150%(GEM) → 비용 0.9%, 세금 22% × 실현
   - 회전율 1,000%+ (mean reversion) → 비용 5%+ → 알파 잠식

2. **Casper는 ‘비용 회피 → 자본 보존’의 극단**.
   - 60일 3건 매매 = 자본 95% 유휴 → 효율 낮음
   - MaxDD −2% = 사고 방어력 최대
   - **단독으로는 ‘안전한 저수익’, 저빈도 퀀트와 결합 시 자본 100% 활용**

3. **저빈도 퀀트는 ‘자본 효율 → 시장 노출’의 극단**.
   - 365일 100% 시장 안
   - MaxDD −20~30% = 시장 폭락 시 정상 손실
   - 노동 강도 거의 0 → ‘백그라운드 자산 증식’

4. **사용자의 자본 규모에 따라 단순 → 복잡 진화**.
   - $1,000: GEM 단독
   - $5,000~$15,000: SPMO + GEM + Casper 균형
   - $30,000+: 5종 자산 분산

### 11.2 즉시 가능한 다음 액션

| 우선순위 | 액션 | 소요 시간 |
|---|---|---|
| **1 (최고)** | Antonacci GEM 월간 리밸런스 paper trading 시작 (KIS 모의계좌 또는 Excel 추적) | 월 5분 |
| 2 | SPMO 또는 MTUM 일부 매수 (시작 비중 10~20%) | 1회 5분 |
| 3 | Faber GTAA-5 백테스트 (Portfolio Visualizer 무료) → 본인 자본 시뮬레이션 | 30분 |
| 4 | Clenow 알고리즘 코드 작성 (Python + yfinance, S&P 500 universe) → 1년 백테스트 | 1~2일 |
| 5 | Casper의 ‘자본 비중 30% 제한’ 도입 (잔액 전부 매수 → 30%만 매수, 70% USD 현금 또는 ETF) | 코드 수정 1시간 |
| 6 | 자본 $5,000 도달 시 SPMO/MTUM 50% + Casper 20% + GEM 30% 시범 운용 1년 | – |

### 11.3 본 문서 작성 시 발견한 한계 (transparency)

1. **Gemini Round 2 capacity 부족으로 실패** — Round 1 결과 + WebSearch 7회로 보강. 따라서 ‘retail tools (Composer, Portfolio Visualizer)’ 사례는 깊이 부족.
2. **AQR QSPIX 5년 CAGR 21% 데이터의 ‘best period bias’ 가능성** — 같은 펀드 10년 6.27%, MaxDD −41%. 일반적 retail이 5년만 보고 들어가면 실망 가능.
3. **2024~2025 SPMO·MTUM 성과는 ‘AI 거품 모멘텀’과 강하게 연결** — 2026 후반 또는 2027 조정 시 backtest와 lived experience가 크게 갈라질 수 있음.
4. **세금 시뮬레이션은 단순화**. 실제로는 실현 시점 환율, 손익 통산 디테일, 종합과세 vs 분리과세 선택 등이 있음. **회계사 자문 권장**.

---

## 부록 A. 알고리즘 의사코드 모음

### A.1 Antonacci GEM (Python)
```python
import yfinance as yf, pandas as pd, numpy as np

def gem_signal(date: pd.Timestamp) -> str:
    """매월 말 호출. 반환: 'SPY' | 'VEU' | 'AGG'"""
    end = date
    start = end - pd.Timedelta(days=400)
    px = yf.download(["SPY","VEU","BIL","AGG"], start=start, end=end,
                     auto_adjust=True)["Close"]
    # 12개월 총수익률
    ret_12m = px.iloc[-1] / px.iloc[-252] - 1
    us, exus, bill = ret_12m["SPY"], ret_12m["VEU"], ret_12m["BIL"]
    if max(us, exus) > bill:
        return "SPY" if us > exus else "VEU"
    else:
        return "AGG"

# 매월 마지막 거래일 호출
target = gem_signal(pd.Timestamp.today())
# KIS: 현재 보유 ETF를 매도 후 target을 매수
```

### A.2 Faber GTAA-5 (Python)
```python
ASSETS = ["SPY","EFA","DBC","IEF","VNQ"]

def gtaa5_weights(date):
    px = yf.download(ASSETS + ["BIL"], start=date - pd.Timedelta(days=400),
                     end=date, interval="1mo", auto_adjust=True)["Close"]
    w = {a: 0.0 for a in ASSETS + ["BIL"]}
    for a in ASSETS:
        if px[a].iloc[-1] > px[a].iloc[-10:].mean():  # 10개월 SMA
            w[a] = 0.20
        else:
            w["BIL"] += 0.20
    return w
```

### A.3 Clenow Stocks-on-the-Move (Python 골격)
```python
import numpy as np
from scipy import stats

def momentum_score(close: pd.Series, window: int = 90) -> float:
    """log price regression slope × R²"""
    y = np.log(close[-window:])
    x = np.arange(window)
    slope, intercept, r, *_ = stats.linregress(x, y)
    annualized = (np.exp(slope) ** 252 - 1)
    return annualized * (r ** 2)

def clenow_select(prices: pd.DataFrame, total_capital: float, atr_days=20):
    spy = prices["SPY"]
    if spy.iloc[-1] < spy.rolling(200).mean().iloc[-1]:
        return {}  # market filter OFF
    scores = {}
    for sym in prices.columns:
        if sym == "SPY": continue
        c = prices[sym]
        # 점프 필터
        ret = c.pct_change()
        if ret[-90:].abs().max() >= 0.15:
            continue
        # 추세 필터
        if c.iloc[-1] < c.rolling(100).mean().iloc[-1]:
            continue
        scores[sym] = momentum_score(c)
    top = sorted(scores, key=scores.get, reverse=True)[:30]
    # ATR sizing
    atr = {s: prices[s].rolling(atr_days).apply(true_range_mean) for s in top}
    shares = {s: int((total_capital * 0.001) / atr[s].iloc[-1]) for s in top}
    return shares
```

### A.4 TQQQ + 200MA (Python)
```python
def tqqq_sma_signal(date):
    qqq = yf.download("QQQ", end=date, period="1y")["Close"]
    sma200 = qqq.rolling(200).mean().iloc[-1]
    current = qqq.iloc[-1]
    if current > sma200 * 1.01:  # 1% buffer
        return "TQQQ"
    elif current < sma200 * 0.99:
        return "BIL"
    else:
        return "HOLD"  # 변동 영역, 기존 포지션 유지
```

---

## 부록 B. 참고문헌·출처 URL

### 학술 논문
- Jegadeesh, N. & Titman, S. (1993) "Returns to Buying Winners and Selling Losers"
- Fama, E. & French, K. (1993, 2015) 3-factor / 5-factor models — https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/Data_Library/f-f_5_factors_2x3.html
- Carhart, M. (1997) "On Persistence in Mutual Fund Performance"
- Antonacci, G. (2014) *Dual Momentum Investing*, McGraw-Hill — https://www.optimalmomentum.com/
- Asness, C., Moskowitz, T., Pedersen, L.H. (2013) "Value and Momentum Everywhere"
- Asness, C., Frazzini, A., Pedersen, L.H. (2012) "Leverage Aversion and Risk Parity"
- Asness, C., Frazzini, A., Pedersen, L.H. (2019) "Quality Minus Junk"
- Frazzini, A., Kabiller, D., Pedersen, L.H. (2018) "Buffett's Alpha", *Financial Analysts Journal* — https://www.aqr.com/Insights/Research/Journal-Article/Buffetts-Alpha
- Moskowitz, T., Ooi, Y.H., Pedersen, L.H. (2012) "Time series momentum"
- Hurst, B., Ooi, Y.H., Pedersen, L.H. (2017) "A century of evidence on trend-following investing"
- Moreira, A. & Muir, T. (2017) "Volatility-Managed Portfolios"
- Poterba, J. & Summers, L. (1988) "Mean reversion in stock prices"
- Avellaneda, M. & Lee, J.H. (2010) "Statistical arbitrage in the US equities market"
- Faber, M. (2007) "A Quantitative Approach to Tactical Asset Allocation" — https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf
- Gray, W. & Vogel, J. (2016) *Quantitative Momentum* — https://alphaarchitect.com/wp-content/uploads/compliance/etf/education/Investment_Case_QMOM.pdf
- Clenow, A. (2015) *Stocks on the Move* — https://www.followingthetrend.com/stocks-on-the-move/
- Newfound Research (2019) "Fragility Case Study: Dual Momentum GEM" — https://blog.thinknewfound.com/2019/01/fragility-case-study-dual-momentum-gem/

### ETF 운용사 페이지
- iShares MTUM — https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf
- Invesco SPMO — https://www.financecharts.com/etfs/SPMO/performance
- Vanguard VFMO — https://investor.vanguard.com/investment-products/etfs/profile/vfmo
- Alpha Architect QMOM — https://funds.alphaarchitect.com/QMOM/
- SPDR Bridgewater All Weather ETF (ALLW) — https://www.ssga.com/us/en/intermediary/capabilities/alternatives/all-weather-etf
- AQR Fund Finder — https://funds.aqr.com/fund-finder
- AQR QSPIX — https://funds.aqr.com/funds/alternatives/aqr-style-premia-alternative-fund/qspix

### 운용사·헤지펀드 공개 자료
- Bridgewater "The All Weather Story" — https://www.bridgewater.com/research-and-insights/the-all-weather-story
- Hedgeweek (2024 quant returns) — https://www.hedgeweek.com/renaissance-tech-and-two-sigma-lead-2024-quant-gains/
- Institutional Investor "Renaissance's 2024 Rebirth" — https://www.institutionalinvestor.com/article/2e0uykr3vn5booz0smrcw/hedge-funds/renaissances-2024-rebirth
- Quantified Strategies Medallion analysis — https://www.quantifiedstrategies.com/decoding-the-medallion-fund-what-we-know-about-its-annual-returns/

### Retail tools / 백테스트 출처
- Composer.trade Symphony Database — https://www.composer.trade/trading-strategies
- QuantConnect Clenow community port — https://www.quantconnect.com/forum/discussion/10493
- TuringTrader Clenow port — https://www.turingtrader.com/portfolios/clenow-stocks-on-the-move/
- Portfolio Visualizer — https://www.portfoliovisualizer.com/
- SG CTA Index — https://wholesale.banking.societegenerale.com/en/prime-services-indices/
- Antonacci 확장 backtest — https://www.optimalmomentum.com/extended-backtest-of-global-equities-momentum/
- Allocate Smartly GTAA — https://allocatesmartly.com/aggressive-global-tactical-asset-allocation/

### 한국 세금·KIS
- EY Korea 2025 tax reform — https://www.ey.com/en_gl/technical/tax-alerts/korea-announces-2025-tax-reform-proposals
- PwC Korea Individual Income — https://taxsummaries.pwc.com/republic-of-korea/individual/income-determination
- 한국투자증권 미국주식 수수료 — https://www.truefriend.com/main/customer/guide/_static/TF04ae010000.shtm

### 그 외 관련
- TQQQ 200MA backtest (financialwisdomtv) — https://www.financialwisdomtv.com/post/qqq-trading-strategy-that-beats-the-market-proven-backtest-results
- TQQQ 200MA Bogleheads forum — https://www.bogleheads.org/forum/viewtopic.php?t=339329

---

## 12. 운영 매뉴얼 — Casper 봇이 옵션 D를 자동 운영하도록 활성화하기

### 12.1 구현 완료 항목 (2026-05-15 PM)

| Phase | 무엇이 자동화되었나 | 코드 위치 |
|---|---|---|
| **P0** | Casper의 자본 잠식 차단 — `CASPER_MAX_POSITION_USD` env로 1회 매매 최대 사이즈를 buckets's 할당분으로 제한 | `src/bot.py::_execute_entry` |
| **P1** | GEM 신호 매월 자동 계산 + 텔레그램 알림 (`GEM_MODE=alert`). 매매는 사람이 KIS 앱에서 직접 | `src/core/gem.py` + `_maybe_run_gem` |
| **P2** | `GEM_MODE=auto`로 두면 봇이 매월 마지막 거래일에 자동 매도/매수 (Antonacci 원본대로 다음 거래일 시가 매매) | `_execute_gem_rotation` |
| **P3** | 매일 1회 portfolio bucket 평가 + 분기말(3/6/9/12 마지막 거래일)에 SPMO/MTUM/QUAL drift 자동 리밸런스 | `_daily_portfolio_tick`, `_execute_bucket_drift_rebalance` |
| **P4 자동 활성화** | 자본이 $5,000 도달 시 MTUM + QUAL 자동 추가, $10,000 도달 시 Clenow + TQQQ_SMA 자동 추가. 별도 작업 없음 | `tier_for_capital(usd)` |
| **공휴일 안전망** | 매월 마지막 거래일 + 3거래일 grace window. 봇이 크래시·휴가로 놓쳐도 자동 복구. 동시에 GemState로 중복 방지 | `time_utils.py`, `should_run_gem` |

### 12.2 자본 $3,000 옵션 D 활성화 절차 — **수동 매수 0회**

`.env` 파일에 2줄 추가:

```bash
# Casper bucket: $3,000 × 20% = $600
CASPER_MAX_POSITION_USD=600

# 100% 자동 운영 (initial seed 포함). 처음 1개월 paper 테스트 후 적용 권장
GEM_MODE=auto
```

봇 재시작만 하면 끝:
```bash
./run_casper.sh daemon --yes
```

**처음 봇이 동작하는 거래일**:
1. KIS 잔고 조회 → $3,000 현금 + 0 보유 감지
2. `needs_initial_seed()` 호출 → cash 비율 100% > 90% → **True**
3. tier_for_capital($3,000) → SPMO 50% / GEM 30% / Casper 20%
4. 봇이 자동으로:
   - **SPMO ~12주 매수** ($1,500) — 시장가 limit
   - **GEM 신호 자산 매수** — `compute_gem_signal()` 즉시 호출 (월말 안 기다림), 오늘 기준 SPY 또는 VEU ~$900어치
   - **Casper bucket ($600)는 현금 보유** — Casper는 ORB+FVG 신호 발생 시에만 매수
   - **Clenow bucket ($10k+ tier)도 현금 보유** — 종목 스크리닝 모듈 도착 시 자동 매수
5. `portfolio_state.seeded_at` 영속화 → 다음 재시작에서도 절대 중복 매수 X

텔레그램 알림 흐름:
```
🎬 Initial seed $3,000.00 → 자동 매수 시작
🟢 SPMO BUY SPMO x12 @ $120.50  ─ Initial seed (50% of $3,000)
🟢 GEM  BUY VEU  x13 @ $67.20   ─ Initial seed (30% of $3,000)
✅ Initial seed complete
  spmo: SPMO x12 @ $120.50
  gem:  VEU  x13 @ $67.20
```

**안전장치**: 사용자가 이미 다른 ETF (예: AAPL 2주, value $500)를 들고 있으면 cash 비율이 $2,500/$3,000 = 83% < 90% → seed 건너뜀 + `seeded_at` 기록. 봇이 사용자 기존 포지션 위로 over-buy 하지 않음.

**alert 모드 옵션**: 자동 매수가 불안하면 먼저 `GEM_MODE=alert`로 1개월 paper 운영. seed는 alert 모드에서 fire 안 함 (`if gem_mode == "auto" and needs_initial_seed(...)`). 알람만 받으며 검증 후 `auto`로 전환.

봇 로그에서 다음 줄이 찍히면 활성화 성공:
```
GEM scheduler active (mode=auto, last=never, holding=-)
🎬 Initial seed starting: total=$3,000.00 cash-mostly, no prior positions
```

### 12.3 운영 일정 (실제 봇이 매일 하는 일)

매일 KST 13:00 (ET 00:00) 새 거래일 진입 시:
1. **자본 동기화** — KIS 잔고 조회
2. **공휴일 체크** — NYSE 휴장일이면 P0~P4 모두 skip
3. **portfolio snapshot** — 모든 ETF + 현금 평가
4. **tier 체크** — 자본이 $5k/$10k 경계를 넘었는지 확인. 넘으면 텔레그램 `🎯 Portfolio tier changed`
5. **GEM 스케줄러** — 오늘이 월말 거래일 또는 grace window 안인가?
   - YES + 첫 실행 → 신호 계산, 텔레그램 `🌐 GEM SIGNAL`
   - alert 모드 → 매매 안 함, 사람이 수동 매매
   - auto 모드 → 09:30 ET 이후 자동 매도/매수, `🟢 GEM BUY VEU x13 @ $67.50` 텔레그램
6. **분기말 drift 체크** — 오늘이 3/6/9/12월 마지막 거래일이고 SPMO 5%+ drift면 자동 trim/add
7. **portfolio summary** — `💼 Portfolio $3,012.45` 일일 텔레그램

ET 09:30~11:00 (KST 23:30~01:00) Casper 데이트레이딩:
- 기존 ORB+FVG+ICT 로직 그대로
- 단 매수 사이즈는 `CASPER_MAX_POSITION_USD=600` 이내로 제한
- TQQQ $80 기준 7주, SQQQ $25 기준 24주

### 12.4 모니터링 (사용자 노동 강도 = 월 5분)

매일 자동 텔레그램:
- `💼 Portfolio $3,xxx` — 1줄 + bucket별 drift
- (Casper 매매 시) `📍 ENTRY TQQQ x7 @ $80.50` 같은 기존 알림

매월 1회 자동 텔레그램 (월말):
- `🌐 GEM SIGNAL 2026-05-29 Target: VEU` — 신호 알람
- (auto 모드) `🟢 GEM BUY VEU x13` — 자동 매매 결과

분기 1회 자동 텔레그램 (3/6/9/12 말일):
- `⚖️ Bucket drift detected` — SPMO drift 5% 이상이면

자본 tier 전환 시 1회 자동 텔레그램:
- `🎯 Portfolio tier changed $4,980 → $5,150 (MTUM/QUAL 활성화)`

### 12.5 검증·트러블슈팅

체크리스트 일괄 검증:
```bash
python -m pytest tests/test_multi_bucket.py -v
# 27 passed
```

GEM 신호 즉시 확인 (수동 dry-run):
```bash
python -c "from src.core.gem import compute_gem_signal; s = compute_gem_signal(); print(s.target, s.reason)"
```

상태 파일 위치:
- `data/gem_state.json` — GEM 마지막 신호 + 현재 보유 자산
- `data/portfolio_state.json` — Portfolio 마지막 평가 + tier key

상태 리셋 (테스트용):
```bash
rm data/gem_state.json data/portfolio_state.json
```

### 12.6 안전 기본값 (역호환)

`GEM_MODE`를 설정하지 않으면 (`off`가 default) **기존 Casper 동작이 100% 그대로**다. 새 코드는 `_daily_portfolio_tick` 한 호출이 추가되었지만 `gem_mode=='off' and CASPER_MAX_POSITION_USD==0`이면 즉시 return 한다. 기존 테스트 551개 모두 회귀 없이 통과.

### 12.7 P4 자본 $5,000 도달 시 자동 동작 확인

코드는 매일 `tier_for_capital(total_usd)`를 호출한다. 자본이 다음 임계값을 처음 넘는 날:
- **$3,000 → $5,000**: 텔레그램 `🎯 tier changed`. 다음 분기말 (예: 6/30)에 자동으로 SPMO 50% → 40%, MTUM 0% → 10%, QUAL 0% → 10%로 리밸런스
- **$5,000 → $10,000**: Clenow + TQQQ_SMA가 활성화. Clenow는 별도 종목 스크리닝 모듈이 필요해서 P4 본 구현에서는 ‘drift 대상’으로만 등록되어 있고 매수는 사람이 1회 종목 선정 후 봇이 분기 drift만 관리하는 형태로 시작 (향후 자동 종목 스크리닝 모듈 추가 예정)

---

## 변경 이력

| 날짜 | 작성자 | 변경 |
|---|---|---|
| 2026-05-15 | Claude (research skill) | 초기 작성: 8대 전략 + Casper 비교 + KIS 비용·세금 분석 |
| 2026-05-15 PM | Claude | §12 운영 매뉴얼 추가: P0~P4 구현 완료, GEM_MODE / CASPER_MAX_POSITION_USD env, 공휴일 grace, 27개 unit test |
