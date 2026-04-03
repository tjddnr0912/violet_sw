# Casper Trading Strategy - 실행 계획서

> 목표: 캐스퍼 매매법의 누락 요소를 보완하고, 백테스팅으로 유효성을 검증한 후,
> 실전 적용 가능한 완전한 트레이딩 시스템을 구축한다.
>
> 작성일: 2026-03-27

---

## Phase 0: 사전 준비 (1주)

### 0.1 개발 환경 구축

```
014_casper/
├── STRATEGY_REVIEW.md      # 전략 검토 (완료)
├── EXECUTION_PLAN.md       # 이 문서
├── docs/
│   ├── THEORY.md           # 이론 정립 (Phase 1 산출물)
│   ├── STOCK_SELECTION.md  # 종목 선택 기준 (Phase 1 산출물)
│   └── BACKTEST_RESULTS.md # 백테스트 결과 (Phase 3 산출물)
├── data/
│   ├── raw/                # 원시 OHLCV 데이터
│   └── processed/          # 전처리된 데이터
├── src/
│   ├── data_loader.py      # 데이터 수집/전처리
│   ├── strategy.py         # 전략 로직 (ORB + FVG + Entry)
│   ├── backtester.py       # 백테스팅 엔진
│   ├── scanner.py          # 종목 스캐너 (Pre-market)
│   ├── indicators.py       # FVG, ORB 계산 모듈
│   └── analysis.py         # 성과 분석/시각화
├── notebooks/
│   └── exploration.ipynb   # 데이터 탐색/시각화
├── config/
│   └── strategy_params.json # 전략 파라미터
├── requirements.txt
└── .env                    # API 키 (Alpaca 등)
```

### 0.2 데이터 소스 선정 및 API 키 확보

| 우선순위 | 데이터 소스 | 비용 | 용도 |
|---------|-----------|------|------|
| 1 | **Alpaca Markets** | 무료 | 1분봉 10년치, 백테스트 메인 |
| 2 | **yfinance** | 무료 | 빠른 프로토타이핑 (60일 5분봉) |
| 3 | **Polygon.io** | $79/월 | 검증용 교차 확인 (필요 시) |

**Action Items:**
- [ ] Alpaca 계좌 개설 및 API 키 확보
- [ ] Python 환경 설정 (venv, requirements.txt)
- [ ] 데이터 다운로드 파이프라인 구축

### 0.3 백테스팅 프레임워크 선정

| 프레임워크 | 장점 | 단점 | 선택 |
|-----------|------|------|------|
| **VectorBT** | 최고 속도, 대규모 데이터 최적 | 학습 곡선 높음 | **메인** |
| Backtrader | 실거래 연동, 복잡한 주문 | 속도 느림 | 실거래 단계 |
| Backtesting.py | 가장 쉬움 | 기능 제한 | 프로토타이핑 |

---

## Phase 1: 이론 정립 및 자료 수집 (2주)

### 1.1 ORB 이론 심화 연구

**목표:** 15분 ORB의 최적 조건과 한계를 명확히 파악

**조사 항목:**
- [ ] Crabel 원저 핵심 내용 정리 (NR4, NR7 패턴 포함)
- [ ] ORB 시간대별 비교 (5분/15분/30분/60분) 기존 백테스트 수집
- [ ] Narrow Range Day가 ORB 성공률에 미치는 영향 정량화
- [ ] ORB가 실패하는 시장 조건 패턴 분류

**참고 자료:**
- Toby Crabel "Day Trading with Short Term Price Patterns and ORB" (1990)
- Linda Raschke & Larry Connors "Street Smarts" (1995)
- QuantifiedStrategies.com ORB 시리즈
- Unger Academy ORB 백테스트

### 1.2 ICT FVG 이론 체계화

**목표:** FVG의 작동 원리를 학술적/통계적으로 정리

**조사 항목:**
- [ ] FVG 정확한 정의 및 식별 알고리즘 코드화
- [ ] FVG 유형별 분류 (Bullish/Bearish/Inverse)
- [ ] FVG 충족(Mitigation) 확률에 대한 기존 통계 수집
- [ ] FVG와 기존 Price Action 갭 이론의 비교
- [ ] FVG가 ORB 레벨과 겹칠 때의 추가 엣지 검증 설계

**참고 자료:**
- ICT Mentorship YouTube 시리즈
- Edgeful FVG 통계 (YM 30분 차트)
- smart-money-concepts Python 패키지 (GitHub: joshyattridge)

### 1.3 종목 선택 기준 수립

**목표:** 이 전략에 최적화된 종목 스캐너 기준 확립

**단계별 접근:**

```
Step 1 (검증 단계): ETF만 사용
  → SPY, QQQ, IWM
  → 변수 최소화로 전략 자체 엣지 측정

Step 2 (확장 단계): 개별주 추가
  → 유동성 필터: 일평균 거래량 500만주+
  → 변동성 필터: ATR 2%+
  → 모멘텀 필터: RVOL 1.5x+, Gap 3%+
  → 카탈리스트: 뉴스/실적 존재

Step 3 (최적화 단계): 스캐너 자동화
  → Pre-market 스캐너 구현
  → 매일 9:00 AM까지 후보 종목 리스트 생성
```

**조사 항목:**
- [ ] 데이트레이딩 종목 선택 기준 비교 분석
- [ ] ORB 전략에 특화된 종목 특성 식별
- [ ] Pre-market 갭 종목 필터링 로직 설계
- [ ] Float, Market Cap, Sector별 ORB 성공률 차이 조사

**참고 자료:**
- Warrior Trading Scanner 기준
- CenterPoint Securities Pre-Market Gappers
- ORBSetups.com 스캐너 로직
- LuxAlgo Momentum Scans

### 1.4 시장 방향성 필터 설계

**목표:** 당일 매수/매도 편향을 판단하는 필터 구축

**조사 항목:**
- [ ] SPY/QQQ 일봉 추세 필터 (20일/50일 MA)
- [ ] VIX 구간별 전략 성과 차이 (15~25 vs 25+ vs 12 이하)
- [ ] Pre-market 선물 방향과 ORB 성공률 상관관계
- [ ] FOMC/CPI 등 매크로 이벤트 당일 ORB 성과 분석
- [ ] 요일별 ORB 성과 차이 (월/금 특이성)

**산출물:** `docs/THEORY.md`, `docs/STOCK_SELECTION.md`

---

## Phase 2: 전략 코드화 (2주)

### 2.1 데이터 수집 모듈

```python
# src/data_loader.py
# - Alpaca API로 1분봉/5분봉 OHLCV 다운로드
# - 기간: 최소 2년, 권장 5년
# - 대상: SPY, QQQ, IWM + 개별주 (Phase 1.3 기준)
# - 데이터 검증: 갭/누락/분할 확인
```

**Action Items:**
- [ ] Alpaca API 연동 및 데이터 다운로드 구현
- [ ] 데이터 품질 검증 로직 (갭, 누락, 분할 보정)
- [ ] Pre-market vs Regular Hours 분리 저장
- [ ] data/raw/ → data/processed/ 파이프라인

### 2.2 지표 계산 모듈

```python
# src/indicators.py
# - Opening Range 계산 (9:30~9:45 고가/저가)
# - FVG 식별 알고리즘 (3캔들 패턴)
# - FVG 위치와 ORB 레벨 겹침 판정
# - Market Bias 필터 (MA, VIX, Pre-market 방향)
```

**FVG 식별 알고리즘 (핵심):**
```
Bullish FVG:
  조건: candle[i-1].high < candle[i+1].low
  영역: candle[i-1].high ~ candle[i+1].low

Bearish FVG:
  조건: candle[i-1].low > candle[i+1].high
  영역: candle[i+1].high ~ candle[i-1].low
```

**Action Items:**
- [ ] ORB 고가/저가 계산 로직
- [ ] FVG 식별 알고리즘 구현
- [ ] ORB-FVG 겹침 판정 로직
- [ ] Market Bias 필터 구현 (MA, VIX)

### 2.3 전략 로직 모듈

```python
# src/strategy.py
# 진입 규칙:
#   1. 9:30~9:45 Opening Range 설정
#   2. 5분봉 전환, 캔들 몸통이 ORB 상단/하단 돌파
#   3. 돌파 캔들에서 FVG 형성 확인
#   4. FVG 구간으로 되돌림 시 진입
#   5. Market Bias 필터 통과 확인
#
# 청산 규칙:
#   - 손절: FVG 캔들 이전 캔들 저점/고점
#   - 익절: R:R 1:2 (기본), 1:3 (공격적)
#   - 시간 제한: 11:00 AM 자동 청산
#
# 필터:
#   - VIX 12~30 범위 내
#   - RVOL 1.5x+
#   - SPY MA(20) 방향과 일치
#   - Circuit Breaker: 연속 3회 손절 → 당일 중단
```

**Action Items:**
- [ ] 진입/청산 로직 구현
- [ ] 포지션 사이징 모듈 (1% 리스크 룰)
- [ ] Circuit Breaker 로직
- [ ] 시간 제한 청산 로직

### 2.4 백테스팅 엔진

```python
# src/backtester.py
# - VectorBT 기반
# - 수수료/슬리피지 모델 포함
# - Walk-Forward Analysis 지원
# - Out-of-Sample 테스트 분리
```

**Action Items:**
- [ ] VectorBT 기반 백테스터 구현
- [ ] 커미션 모델: 거래당 $0.005/주
- [ ] 슬리피지 모델: 0.01~0.05%
- [ ] In-Sample / Out-of-Sample 데이터 분리 (70:30)

---

## Phase 3: 백테스팅 및 검증 (3주)

### 3.1 기본 백테스트 (Step 1: ETF Only)

**대상:** SPY, QQQ, IWM
**기간:** 최근 5년 (다양한 시장 사이클 포함)
**데이터:** 5분봉

**측정 지표:**

| 지표 | 목표 기준 | 의미 |
|------|----------|------|
| Win Rate | 40~55% | 승률 |
| Profit Factor | 1.5+ | 총수익/총손실 |
| Expectancy | 양수 | 거래당 기대 수익 |
| Max Drawdown | 15% 이하 | 최대 낙폭 |
| Sharpe Ratio | 1.0+ | 위험 대비 수익 |
| 실제 평균 R:R | 1.8+ | 설정 대비 달성치 |

**통계적 유의성 기준:**
- 최소 200회 거래: 기본 방향성 확인
- **권장 400회+: 95% 신뢰구간에서 ±5% 정밀도**
- 하루 1~2회 세팅 기준 → 6개월~1년 데이터 필요

**Action Items:**
- [ ] SPY 5년 백테스트 실행
- [ ] QQQ 5년 백테스트 실행
- [ ] IWM 5년 백테스트 실행
- [ ] 거래 횟수 400회 이상 확인
- [ ] 결과 시각화 (수익 곡선, 드로다운, 월별 성과)

### 3.2 조건별 세분화 분석

**분석 차원:**

| 차원 | 세부 항목 |
|------|----------|
| 요일별 | 월~금 각각의 승률/기대값 |
| VIX 구간별 | <15, 15~25, 25~35, 35+ |
| 시장 추세별 | 상승장(MA20 위) / 하락장 / 횡보 |
| FVG 위치별 | ORB 근접 vs ORB 원거리 |
| ORB 범위별 | Narrow Range vs Wide Range |
| 갭 방향별 | Gap Up + Long vs Gap Down + Short |

**Action Items:**
- [ ] 요일별 성과 분석
- [ ] VIX 구간별 성과 분석
- [ ] 시장 추세별 성과 분석
- [ ] FVG-ORB 거리별 성과 분석
- [ ] ORB 범위별 성과 분석

### 3.3 견고성 검증

**Robustness Tests:**

| 테스트 | 방법 |
|--------|------|
| Walk-Forward Analysis | 롤링 1년 In-Sample → 3개월 Out-of-Sample |
| Parameter Sensitivity | ORB 시간(10/15/20/30분), R:R(1:1.5/1:2/1:2.5/1:3) 변화 |
| Monte Carlo Simulation | 거래 순서 1,000회 셔플 → 최악 드로다운 분포 |
| Regime Analysis | 2020 코로나, 2022 금리인상, 2024~2025 강세장 분리 |

**Action Items:**
- [ ] Walk-Forward Analysis 구현 및 실행
- [ ] 파라미터 민감도 분석
- [ ] Monte Carlo 시뮬레이션
- [ ] 시장 국면별 분리 분석

### 3.4 비교 벤치마크

**비교 대상:**
- 순수 ORB (FVG 없이 돌파 즉시 진입)
- FVG만 사용 (ORB 없이)
- Buy & Hold SPY
- Random Entry (동일 R:R, 동일 시간대)

**산출물:** `docs/BACKTEST_RESULTS.md`

---

## Phase 4: 최적화 및 보완 (2주)

### 4.1 파라미터 최적화

**최적화 대상 (과최적화 주의):**
- ORB 시간: 10분 / 15분 / 20분 / 30분
- FVG 필터: ORB 레벨과의 최대 허용 거리
- R:R 비율: 1:1.5 / 1:2 / 1:2.5 / 1:3
- 시간 제한: 90분 / 120분 / 장 마감까지
- VIX 필터 임계값

**과최적화 방지:**
- Out-of-Sample에서 In-Sample 대비 70%+ 성과 유지 확인
- 파라미터 변화에 따른 성과 곡면(Surface)이 매끄러운지 확인
- "파라미터 절벽"이 있으면 해당 설정 회피

### 4.2 종목 스캐너 구현

```python
# src/scanner.py
# Pre-market 스캐너 (매일 9:00 AM 실행)
# 필터:
#   - Gap% > 3% (대형주) 또는 Gap% > 10% (소형주)
#   - Pre-market 거래량 > 100,000주
#   - RVOL > 1.5x
#   - ATR > $0.50
#   - Float 확인
#   - 카탈리스트 존재 여부 (뉴스 API 연동)
```

### 4.3 완전한 트레이딩 시스템 통합

```
매일 루틴:
  8:30 AM - Pre-market 스캐너 실행 → 후보 종목 3~5개
  9:00 AM - Market Bias 확인 (SPY MA, VIX, 선물 방향)
  9:30 AM - Opening Range 시작, 15분봉 관찰
  9:45 AM - 기준선 확정, 5분봉 전환, 대기
  9:45~11:00 AM - 세팅 발생 시 진입 (최대 2포지션)
  11:00 AM - 미청산 포지션 정리, 당일 기록
```

---

## Phase 5: 페이퍼 트레이딩 (3개월)

### 5.1 실행 환경

- **플랫폼:** Alpaca Paper Trading 또는 TradingView Paper
- **기간:** 최소 3개월 (60+ 거래일)
- **목표 거래 수:** 100회+ (통계적 유의성 최소선)

### 5.2 기록 항목

| 항목 | 내용 |
|------|------|
| 날짜/시간 | 진입/청산 시각 |
| 종목 | 티커, 선택 이유 |
| ORB Range | 고가/저가, 범위 (ATR 대비) |
| FVG | 위치, ORB 레벨과의 거리 |
| Market Bias | SPY 방향, VIX, 뉴스 |
| 진입/손절/익절 가격 | 계획 vs 실제 |
| R:R | 계획 vs 실제 |
| 결과 | Win/Loss, P&L |
| 스크린샷 | 진입/청산 시점 차트 |
| 메모 | 감정, 실수, 개선점 |

### 5.3 중간 리뷰 (4주마다)

- 백테스트 결과 대비 실제 성과 비교
- 승률, Profit Factor, Max Drawdown 추적
- 슬리피지/체결 차이 측정
- 전략 규칙 위반 횟수 기록
- **Go/No-Go 판단:** 50회 거래 후 Profit Factor < 1.0 → Phase 1로 복귀

---

## Phase 6: 실전 전환 (조건부)

### 6.1 전환 조건 (모두 충족 시)

- [ ] 백테스트 Profit Factor > 1.5
- [ ] 페이퍼 트레이딩 Profit Factor > 1.2
- [ ] 페이퍼 트레이딩 100회+ 거래 완료
- [ ] Max Drawdown < 15%
- [ ] 백테스트 대비 페이퍼 성과 70%+

### 6.2 점진적 자금 투입

```
Month 1: 계좌의 25% 규모로 시작 (리스크 0.5%/거래)
Month 2: 50% 규모 (리스크 0.75%/거래) - 성과 유지 시
Month 3: 100% 규모 (리스크 1.0%/거래) - 성과 유지 시
```

### 6.3 지속적 모니터링

- 주간 성과 리뷰
- 월간 백테스트 대비 실제 성과 비교
- **중단 기준:** 실전 Max Drawdown > 20% → 즉시 중단, 재검토

---

## 타임라인 요약

| Phase | 기간 | 핵심 산출물 |
|-------|------|-----------|
| 0. 사전 준비 | 1주 | 환경 구축, API 확보, 데이터 파이프라인 |
| 1. 이론 정립 | 2주 | THEORY.md, STOCK_SELECTION.md |
| 2. 전략 코드화 | 2주 | strategy.py, indicators.py, backtester.py |
| 3. 백테스팅 | 3주 | BACKTEST_RESULTS.md, 성과 지표 |
| 4. 최적화 | 2주 | scanner.py, 파라미터 최적화 |
| 5. 페이퍼 트레이딩 | 3개월 | 실전 검증 데이터 |
| 6. 실전 전환 | 조건부 | Go/No-Go 판단 |

**총 소요: 약 10주 (개발) + 3개월 (페이퍼) = ~6개월**

---

## 핵심 참고 자료

### 서적
- Toby Crabel - "Day Trading with Short Term Price Patterns and ORB" (1990)
- Linda Raschke & Larry Connors - "Street Smarts" (1995)
- Mark Douglas - "Trading in the Zone" (심리적 규율)
- David Aronson - "Evidence-Based Technical Analysis" (통계적 검증)
- Robert Carver - "Systematic Trading" (포지션 사이징)

### 온라인 자료
- QuantifiedStrategies.com - ORB 백테스트 시리즈
- Edgeful.com - FVG 통계 데이터
- BlackArbs.com - 인트라데이 고/저 형성 확률 연구
- ICT YouTube Mentorship - FVG 원본 강의

### 도구
- Alpaca Markets - 무료 데이터 + 페이퍼 트레이딩
- VectorBT - 백테스팅 엔진
- smart-money-concepts (GitHub) - FVG 알고리즘 참조
- ORBSetups.com - ORB 전용 스캐너

### 데이터 소스
- Alpaca: 1분봉 10년치 (무료, 메인)
- Polygon.io: 교차 검증용 ($79/월)
- Databento: 기관급 데이터 (신규 $125 크레딧)
