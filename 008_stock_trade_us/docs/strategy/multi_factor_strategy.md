# 멀티팩터 복합 전략 완벽 가이드

> 작성일: 2024-12-25
> 버전: 1.0
> 목적: 가치 + 모멘텀 + 퀄리티 복합 전략의 체계적 구현

---

## 목차

1. [전략 개요](#1-전략-개요)
2. [팩터 정의 및 계산](#2-팩터-정의-및-계산)
3. [종목 스크리닝](#3-종목-스크리닝)
4. [매수 타이밍](#4-매수-타이밍)
5. [매도 타이밍](#5-매도-타이밍)
6. [손절 전략](#6-손절-전략)
7. [익절 전략](#7-익절-전략)
8. [포지션 관리](#8-포지션-관리)
9. [리밸런싱](#9-리밸런싱)
10. [리스크 관리](#10-리스크-관리)
11. [API 구현 계획](#11-api-구현-계획)

---

## 1. 전략 개요

### 1.1 복합 전략이란?

**멀티팩터(Multi-Factor) 전략**은 단일 투자 기준이 아닌, 여러 팩터를 조합하여 종목을 선정하고 매매하는 방식입니다.

```
단일 팩터의 문제점:
├─ 가치투자: 성장주 장세에서 소외 (2020년 사례)
├─ 모멘텀: 급락장에서 큰 손실 (2022년 사례)
└─ 퀄리티: 저평가 기회 놓침

복합 전략의 해결:
└─ 서로 다른 시기에 강한 팩터가 상호 보완
   → 변동성 감소 + 꾸준한 수익
```

### 1.2 사용 팩터 구성

| 팩터 | 비중 | 역할 | 강점 시기 |
|------|------|------|-----------|
| **가치(Value)** | 40% | 저평가 종목 발굴 | 하락장 후반, 회복기 |
| **모멘텀(Momentum)** | 30% | 상승 추세 포착 | 상승장, 추세장 |
| **퀄리티(Quality)** | 30% | 우량 기업 필터 | 전 구간 안정성 |

### 1.3 기대 성과

| 지표 | 목표치 | 비고 |
|------|--------|------|
| 연평균 수익률 (CAGR) | 15~20% | 시장 대비 초과수익 5~10% |
| 최대 낙폭 (MDD) | 20% 이내 | 심리적 유지 가능 수준 |
| 샤프 비율 | 1.0 이상 | 위험 대비 수익 효율 |
| 승률 | 55~60% | 손익비와 함께 판단 |
| 손익비 | 1.5:1 이상 | 평균 이익 / 평균 손실 |

---

## 2. 팩터 정의 및 계산

### 2.1 가치 팩터 (Value Factor)

#### 핵심 지표

| 지표 | 계산식 | 저평가 기준 | 가중치 |
|------|--------|-------------|--------|
| **PER** | 주가 / 주당순이익 | < 15 | 35% |
| **PBR** | 주가 / 주당순자산 | < 1.5 | 35% |
| **PSR** | 주가 / 주당매출 | < 1.0 | 15% |
| **배당수익률** | 배당금 / 주가 | > 2% | 15% |

#### 가치 점수 계산

```python
def calculate_value_score(stock):
    """
    가치 점수 계산 (0~100)
    낮을수록 저평가 → 높은 점수 부여
    """
    # 각 지표의 백분위 계산 (전체 종목 대비)
    per_percentile = get_percentile(stock.per, ascending=True)   # 낮을수록 좋음
    pbr_percentile = get_percentile(stock.pbr, ascending=True)   # 낮을수록 좋음
    psr_percentile = get_percentile(stock.psr, ascending=True)   # 낮을수록 좋음
    div_percentile = get_percentile(stock.dividend_yield, ascending=False)  # 높을수록 좋음

    value_score = (
        per_percentile * 0.35 +
        pbr_percentile * 0.35 +
        psr_percentile * 0.15 +
        div_percentile * 0.15
    )

    return value_score
```

#### 가치 팩터 필터 조건

```
1차 필터 (필수):
├─ PER > 0 (흑자 기업만)
├─ PER < 30 (극단적 고평가 제외)
├─ PBR > 0.2 (자본잠식 제외)
└─ PBR < 5 (극단적 고평가 제외)

2차 필터 (점수화):
├─ PER 하위 30% → 고득점
├─ PBR 하위 30% → 고득점
└─ 배당수익률 상위 30% → 고득점
```

### 2.2 모멘텀 팩터 (Momentum Factor)

#### 핵심 지표

| 지표 | 계산식 | 기간 | 가중치 |
|------|--------|------|--------|
| **12개월 수익률** | (현재가 - 12개월전) / 12개월전 | 12M | 40% |
| **6개월 수익률** | (현재가 - 6개월전) / 6개월전 | 6M | 30% |
| **3개월 수익률** | (현재가 - 3개월전) / 3개월전 | 3M | 20% |
| **1개월 수익률** | (현재가 - 1개월전) / 1개월전 | 1M | 10% |

#### 모멘텀 점수 계산

```python
def calculate_momentum_score(stock, price_history):
    """
    모멘텀 점수 계산 (0~100)

    주의: 최근 1개월 수익률은 "단기 과열" 필터로 사용
          → 너무 높으면 오히려 감점 (평균회귀 고려)
    """
    # 기간별 수익률 계산
    ret_12m = (price_history[-1] - price_history[-252]) / price_history[-252] * 100
    ret_6m = (price_history[-1] - price_history[-126]) / price_history[-126] * 100
    ret_3m = (price_history[-1] - price_history[-63]) / price_history[-63] * 100
    ret_1m = (price_history[-1] - price_history[-21]) / price_history[-21] * 100

    # 12-1 모멘텀 (최근 1개월 제외) - 학술적으로 검증된 방식
    momentum_12_1 = ret_12m - ret_1m

    # 백분위 점수 계산
    mom_12m_pct = get_percentile(ret_12m, ascending=False)
    mom_6m_pct = get_percentile(ret_6m, ascending=False)
    mom_3m_pct = get_percentile(ret_3m, ascending=False)

    # 단기 과열 페널티 (1개월 수익률이 상위 10%면 감점)
    short_term_penalty = 10 if ret_1m > get_top_percentile(10) else 0

    momentum_score = (
        mom_12m_pct * 0.40 +
        mom_6m_pct * 0.30 +
        mom_3m_pct * 0.30 -
        short_term_penalty
    )

    return max(0, momentum_score)
```

#### 모멘텀 팩터 필터 조건

```
1차 필터 (필수):
├─ 12개월 수익률 > -20% (급락주 제외)
├─ 6개월 수익률 > -10% (하락 추세 제외)
└─ 거래대금 일평균 10억 이상 (유동성)

2차 필터 (점수화):
├─ 12개월 수익률 상위 30% → 고득점
├─ 6개월 수익률 상위 30% → 고득점
└─ 52주 신고가 대비 -10% 이내 → 보너스
```

### 2.3 퀄리티 팩터 (Quality Factor)

#### 핵심 지표

| 지표 | 계산식 | 우량 기준 | 가중치 |
|------|--------|-----------|--------|
| **ROE** | 순이익 / 자기자본 | > 10% | 35% |
| **영업이익률** | 영업이익 / 매출 | > 8% | 25% |
| **부채비율** | 부채 / 자기자본 | < 100% | 25% |
| **이익 성장률** | (금년 EPS - 전년 EPS) / 전년 EPS | > 0% | 15% |

#### 퀄리티 점수 계산

```python
def calculate_quality_score(stock):
    """
    퀄리티 점수 계산 (0~100)
    재무 건전성과 수익성 측정
    """
    # 백분위 계산
    roe_pct = get_percentile(stock.roe, ascending=False)           # 높을수록 좋음
    margin_pct = get_percentile(stock.operating_margin, ascending=False)  # 높을수록 좋음
    debt_pct = get_percentile(stock.debt_ratio, ascending=True)    # 낮을수록 좋음
    growth_pct = get_percentile(stock.eps_growth, ascending=False) # 높을수록 좋음

    quality_score = (
        roe_pct * 0.35 +
        margin_pct * 0.25 +
        debt_pct * 0.25 +
        growth_pct * 0.15
    )

    return quality_score
```

#### 퀄리티 팩터 필터 조건

```
1차 필터 (필수):
├─ ROE > 5% (최소 수익성)
├─ 영업이익 > 0 (본업 흑자)
├─ 부채비율 < 200% (재무 안정성)
└─ 3년 연속 흑자 (지속성)

2차 필터 (점수화):
├─ ROE 상위 30% → 고득점
├─ 영업이익률 상위 30% → 고득점
└─ 부채비율 하위 30% → 고득점
```

### 2.4 통합 점수 계산

```python
def calculate_composite_score(stock):
    """
    복합 점수 계산

    가치(40%) + 모멘텀(30%) + 퀄리티(30%) = 100%
    """
    value_score = calculate_value_score(stock)
    momentum_score = calculate_momentum_score(stock, stock.price_history)
    quality_score = calculate_quality_score(stock)

    # 가중 평균
    composite_score = (
        value_score * 0.40 +
        momentum_score * 0.30 +
        quality_score * 0.30
    )

    # 보너스/페널티
    bonus = 0

    # 모든 팩터에서 상위 50% 이상이면 보너스
    if value_score >= 50 and momentum_score >= 50 and quality_score >= 50:
        bonus += 5

    # 어떤 팩터든 하위 20%면 페널티
    if min(value_score, momentum_score, quality_score) < 20:
        bonus -= 10

    return min(100, max(0, composite_score + bonus))
```

---

## 3. 종목 스크리닝

### 3.1 유니버스 설정

```
전체 상장 종목
    │
    ▼
┌─────────────────────────────────┐
│ 1단계: 기본 필터                  │
├─────────────────────────────────┤
│ • 시가총액 > 1,000억원            │
│ • 일평균 거래대금 > 10억원         │
│ • 관리종목/투자경고 제외           │
│ • 상장 후 1년 이상 경과            │
└─────────────────────────────────┘
    │ (약 400~500종목)
    ▼
┌─────────────────────────────────┐
│ 2단계: 재무 필터                  │
├─────────────────────────────────┤
│ • 3년 연속 흑자                   │
│ • 부채비율 < 200%                │
│ • 자본잠식 없음                   │
└─────────────────────────────────┘
    │ (약 200~300종목)
    ▼
┌─────────────────────────────────┐
│ 3단계: 팩터 점수 계산              │
├─────────────────────────────────┤
│ • 가치 점수 (0~100)              │
│ • 모멘텀 점수 (0~100)             │
│ • 퀄리티 점수 (0~100)             │
│ • 복합 점수 (가중평균)             │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ 4단계: 최종 선정                  │
├─────────────────────────────────┤
│ • 복합 점수 상위 20종목 선정        │
│ • 섹터 분산 (단일 섹터 30% 이하)    │
└─────────────────────────────────┘
```

### 3.2 섹터 분산 규칙

```python
SECTOR_LIMIT = 0.30  # 단일 섹터 최대 비중 30%

def apply_sector_diversification(candidates, target_count=20):
    """
    섹터 분산을 적용한 최종 종목 선정
    """
    selected = []
    sector_count = {}
    max_per_sector = int(target_count * SECTOR_LIMIT)  # 6종목

    for stock in sorted(candidates, key=lambda x: x.composite_score, reverse=True):
        sector = stock.sector

        # 섹터별 한도 체크
        if sector_count.get(sector, 0) < max_per_sector:
            selected.append(stock)
            sector_count[sector] = sector_count.get(sector, 0) + 1

        if len(selected) >= target_count:
            break

    return selected
```

---

## 4. 매수 타이밍

### 4.1 매수 조건 체계

```
┌─────────────────────────────────────────────────────────────┐
│                      매수 신호 판단                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 종목 선정 완료 (복합 점수 상위 20)           ✓ 필수      │
│                     │                                       │
│                     ▼                                       │
│  2. 시장 환경 확인                              ✓ 필수      │
│     ├─ KOSPI > 60일 이동평균                               │
│     └─ VIX(변동성) < 25                                    │
│                     │                                       │
│                     ▼                                       │
│  3. 기술적 매수 타이밍                          ✓ 권장      │
│     ├─ RSI < 70 (과매수 아님)                              │
│     ├─ 20일 이동평균 위                                    │
│     └─ MACD 히스토그램 > 0 또는 상승 전환                   │
│                     │                                       │
│                     ▼                                       │
│  4. 매수 실행                                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 시장 환경 필터

```python
def check_market_condition():
    """
    시장 환경 체크

    Returns:
        "BULLISH": 적극 매수
        "NEUTRAL": 일반 매수
        "BEARISH": 매수 보류/비중 축소
    """
    kospi = get_kospi_index()
    kospi_ma60 = get_moving_average(kospi, 60)
    kospi_ma120 = get_moving_average(kospi, 120)

    # 상승 추세: KOSPI > 60일선 > 120일선
    if kospi > kospi_ma60 > kospi_ma120:
        return "BULLISH"

    # 하락 추세: KOSPI < 60일선 < 120일선
    elif kospi < kospi_ma60 < kospi_ma120:
        return "BEARISH"

    else:
        return "NEUTRAL"
```

### 4.3 개별 종목 매수 타이밍

#### 기술적 지표 조건

```python
def check_technical_buy_signal(stock):
    """
    기술적 매수 신호 확인

    Returns:
        score: 0~100 (높을수록 매수 적합)
    """
    score = 50  # 기본 점수

    # RSI 체크 (14일)
    rsi = calculate_rsi(stock, 14)
    if rsi < 30:
        score += 20  # 과매도 → 강한 매수 신호
    elif rsi < 50:
        score += 10  # 중립 하단 → 매수 적합
    elif rsi > 70:
        score -= 20  # 과매수 → 매수 보류

    # 이동평균 체크
    price = stock.current_price
    ma20 = calculate_ma(stock, 20)
    ma60 = calculate_ma(stock, 60)

    if price > ma20 > ma60:
        score += 15  # 정배열 → 상승 추세
    elif price < ma20 < ma60:
        score -= 15  # 역배열 → 하락 추세

    # MACD 체크
    macd, signal, histogram = calculate_macd(stock)
    if histogram > 0 and histogram > histogram_prev:
        score += 15  # 히스토그램 양수 + 상승
    elif histogram < 0 and histogram < histogram_prev:
        score -= 15  # 히스토그램 음수 + 하락

    # 볼린저밴드 체크
    upper, middle, lower = calculate_bollinger(stock, 20, 2)
    if price < lower:
        score += 10  # 하단 이탈 → 반등 기대
    elif price > upper:
        score -= 10  # 상단 이탈 → 조정 가능

    return max(0, min(100, score))
```

### 4.4 매수 실행 규칙

```
매수 타이밍 결정:

┌────────────────────────────────────────────────────────────┐
│ 시장 환경      │ 기술적 점수    │ 실행                      │
├────────────────────────────────────────────────────────────┤
│ BULLISH       │ >= 60        │ 즉시 매수 (목표 비중 100%) │
│ BULLISH       │ 40~59        │ 분할 매수 (50% 먼저)       │
│ BULLISH       │ < 40         │ 대기 (다음 리밸런싱까지)    │
├────────────────────────────────────────────────────────────┤
│ NEUTRAL       │ >= 70        │ 즉시 매수 (목표 비중 80%)  │
│ NEUTRAL       │ 50~69        │ 분할 매수 (50% 먼저)       │
│ NEUTRAL       │ < 50         │ 대기                      │
├────────────────────────────────────────────────────────────┤
│ BEARISH       │ >= 80        │ 소량 매수 (목표 비중 50%)  │
│ BEARISH       │ < 80         │ 매수 보류                 │
└────────────────────────────────────────────────────────────┘
```

### 4.5 분할 매수 전략

```python
def execute_split_buy(stock, total_amount, splits=3):
    """
    분할 매수 실행

    Args:
        stock: 종목
        total_amount: 총 매수 금액
        splits: 분할 횟수 (기본 3회)
    """
    amount_per_split = total_amount / splits

    # 1차 매수: 즉시 (40%)
    buy_order(stock, amount_per_split * 1.2)

    # 2차 매수: -3% 하락 시 (30%)
    set_limit_order(stock, stock.price * 0.97, amount_per_split * 0.9)

    # 3차 매수: -5% 하락 시 (30%)
    set_limit_order(stock, stock.price * 0.95, amount_per_split * 0.9)
```

---

## 5. 매도 타이밍

### 5.1 매도 조건 체계

```
┌─────────────────────────────────────────────────────────────┐
│                      매도 신호 유형                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 리밸런싱 매도 (정기)                                     │
│     └─ 월별/분기별 리밸런싱 시 편출 종목                       │
│                                                             │
│  2. 조건 매도 (팩터 이탈)                                    │
│     ├─ 복합 점수 하위 30% 이하로 하락                         │
│     ├─ 개별 팩터 급격히 악화                                 │
│     └─ 재무 악화 (적자 전환, 부채 급증)                       │
│                                                             │
│  3. 기술적 매도 (추세 전환)                                  │
│     ├─ 60일 이동평균 하향 돌파                               │
│     ├─ RSI 70 이상 후 하락 전환                             │
│     └─ MACD 데드크로스                                      │
│                                                             │
│  4. 손절 매도 (리스크 관리)                                  │
│     └─ 손절가 도달 시 즉시 매도                              │
│                                                             │
│  5. 익절 매도 (수익 실현)                                    │
│     └─ 목표가 도달 시 단계적 매도                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 리밸런싱 매도

```python
def rebalancing_sell_check(portfolio, new_rankings):
    """
    리밸런싱 시 매도 대상 확인

    매도 조건:
    1. 신규 순위에서 탈락 (상위 20 → 20 밖)
    2. 순위 급락 (상위 10 → 하위 50%)
    """
    sell_candidates = []

    for stock in portfolio:
        new_rank = new_rankings.get(stock.code)

        # 순위권 이탈
        if new_rank is None or new_rank > 30:
            sell_candidates.append({
                'stock': stock,
                'reason': 'RANK_OUT',
                'action': 'FULL_SELL'
            })

        # 급격한 순위 하락
        elif stock.prev_rank <= 10 and new_rank > 25:
            sell_candidates.append({
                'stock': stock,
                'reason': 'RANK_DROP',
                'action': 'PARTIAL_SELL_50%'
            })

    return sell_candidates
```

### 5.3 기술적 매도 신호

```python
def check_technical_sell_signal(stock):
    """
    기술적 매도 신호 확인

    Returns:
        signal: "STRONG_SELL", "WEAK_SELL", "HOLD"
    """
    signals = []

    # RSI 과매수 후 하락
    rsi = calculate_rsi(stock, 14)
    rsi_prev = calculate_rsi(stock, 14, offset=1)
    if rsi_prev > 70 and rsi < rsi_prev - 5:
        signals.append("RSI_REVERSAL")

    # 이동평균 하향 돌파
    price = stock.current_price
    ma60 = calculate_ma(stock, 60)
    ma60_prev = calculate_ma(stock, 60, offset=5)
    if price < ma60 and stock.price_5days_ago > ma60_prev:
        signals.append("MA60_BREAKDOWN")

    # MACD 데드크로스
    macd, signal_line, _ = calculate_macd(stock)
    macd_prev, signal_prev, _ = calculate_macd(stock, offset=1)
    if macd < signal_line and macd_prev >= signal_prev:
        signals.append("MACD_DEAD_CROSS")

    # 볼린저밴드 상단 이탈 후 복귀
    upper, _, _ = calculate_bollinger(stock, 20, 2)
    if stock.high_5days > upper and price < upper * 0.98:
        signals.append("BB_UPPER_REVERSAL")

    # 신호 개수에 따른 판단
    if len(signals) >= 3:
        return "STRONG_SELL"
    elif len(signals) >= 2:
        return "WEAK_SELL"
    else:
        return "HOLD"
```

---

## 6. 손절 전략

### 6.1 손절 원칙

```
┌─────────────────────────────────────────────────────────────┐
│                      손절의 핵심 원칙                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 사전 설정: 매수 시점에 손절가 반드시 설정                  │
│                                                             │
│  2. 기계적 실행: 감정 개입 없이 규칙대로 실행                  │
│                                                             │
│  3. 손실 제한: 개별 종목 -10%, 일일 -2%, 포트폴리오 -15%       │
│                                                             │
│  4. 재진입 규칙: 손절 후 최소 5거래일 대기                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 손절가 설정 방법

#### 방법 1: 고정 비율 손절

```python
def set_fixed_stop_loss(entry_price, loss_rate=0.07):
    """
    고정 비율 손절가 설정

    Args:
        entry_price: 진입가
        loss_rate: 손절률 (기본 7%)

    Returns:
        stop_loss_price: 손절가
    """
    return entry_price * (1 - loss_rate)

# 예시: 50,000원 진입 → 46,500원 손절
```

#### 방법 2: ATR 기반 손절 (권장)

```python
def set_atr_stop_loss(entry_price, atr, multiplier=2.0):
    """
    ATR 기반 손절가 설정
    변동성에 맞춰 자동 조절

    Args:
        entry_price: 진입가
        atr: 14일 ATR
        multiplier: ATR 배수 (기본 2.0)

    Returns:
        stop_loss_price: 손절가
    """
    return entry_price - (atr * multiplier)

# 예시: 50,000원 진입, ATR 1,500원
# → 손절가 = 50,000 - (1,500 × 2) = 47,000원
```

#### 방법 3: 지지선 기반 손절

```python
def set_support_stop_loss(stock, buffer=0.02):
    """
    기술적 지지선 기반 손절가 설정

    Args:
        stock: 종목
        buffer: 지지선 아래 버퍼 (기본 2%)

    Returns:
        stop_loss_price: 손절가
    """
    # 지지선 후보
    support_levels = [
        calculate_ma(stock, 20),           # 20일 이동평균
        calculate_ma(stock, 60),           # 60일 이동평균
        stock.low_20days,                  # 20일 최저가
        calculate_bollinger(stock)[2],     # 볼린저밴드 하단
    ]

    # 현재가 아래의 가장 가까운 지지선
    current = stock.current_price
    valid_supports = [s for s in support_levels if s < current]

    if valid_supports:
        nearest_support = max(valid_supports)
        return nearest_support * (1 - buffer)
    else:
        # 지지선이 없으면 고정 비율 사용
        return current * 0.93
```

### 6.3 트레일링 스탑

```python
def update_trailing_stop(position, trailing_pct=0.07):
    """
    트레일링 스탑 업데이트
    상승 시 손절가도 상승, 하락 시 유지

    Args:
        position: 보유 포지션
        trailing_pct: 트레일링 비율 (기본 7%)
    """
    current_price = position.stock.current_price

    # 신고가 갱신 시 손절가 상향
    if current_price > position.highest_price:
        position.highest_price = current_price
        new_stop = current_price * (1 - trailing_pct)

        # 손절가는 상향만 가능 (하향 금지)
        if new_stop > position.stop_loss:
            position.stop_loss = new_stop
            log(f"{position.stock.name}: 손절가 상향 → {new_stop:,}원")

    # 손절가 도달 시 매도
    if current_price <= position.stop_loss:
        execute_stop_loss(position)
```

### 6.4 손절 실행

```python
def execute_stop_loss(position):
    """
    손절 매도 실행
    """
    stock = position.stock

    # 시장가 매도 (빠른 체결)
    result = sell_market_order(stock, position.quantity)

    if result.success:
        loss = position.entry_price - result.price
        loss_pct = loss / position.entry_price * 100

        log(f"[손절] {stock.name}")
        log(f"  진입가: {position.entry_price:,}원")
        log(f"  손절가: {result.price:,}원")
        log(f"  손실률: {loss_pct:.2f}%")

        # 손절 기록 저장 (향후 분석용)
        save_stop_loss_record(position, result)

        # 재진입 금지 기간 설정
        set_cooldown(stock.code, days=5)
```

---

## 7. 익절 전략

### 7.1 익절 원칙

```
┌─────────────────────────────────────────────────────────────┐
│                      익절의 핵심 원칙                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 욕심 제어: "더 오를 것 같다"는 감정 배제                   │
│                                                             │
│  2. 단계적 실현: 한 번에 전량 매도 X, 분할 매도 O              │
│                                                             │
│  3. 손익비 준수: 최소 1.5:1 이상 (7% 손절 → 10.5% 익절)       │
│                                                             │
│  4. 추세 존중: 강한 상승 추세면 일부만 익절, 나머지 보유        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 익절 목표가 설정

#### 방법 1: 고정 비율 익절

```python
def set_fixed_take_profit(entry_price, stop_loss_price, risk_reward_ratio=2.0):
    """
    손익비 기반 익절가 설정

    Args:
        entry_price: 진입가
        stop_loss_price: 손절가
        risk_reward_ratio: 손익비 (기본 2.0)

    Returns:
        take_profit_price: 익절가
    """
    risk = entry_price - stop_loss_price  # 리스크 (손절 폭)
    reward = risk * risk_reward_ratio      # 리워드 (익절 폭)

    return entry_price + reward

# 예시: 진입 50,000원, 손절 46,500원 (리스크 3,500원)
# → 익절 = 50,000 + (3,500 × 2) = 57,000원
```

#### 방법 2: ATR 기반 익절

```python
def set_atr_take_profit(entry_price, atr, multiplier=3.0):
    """
    ATR 기반 익절가 설정

    Args:
        entry_price: 진입가
        atr: 14일 ATR
        multiplier: ATR 배수 (기본 3.0)

    Returns:
        take_profit_price: 익절가
    """
    return entry_price + (atr * multiplier)

# 예시: 진입 50,000원, ATR 1,500원
# → 익절 = 50,000 + (1,500 × 3) = 54,500원
```

### 7.3 단계적 익절 (권장)

```python
def execute_staged_take_profit(position):
    """
    3단계 분할 익절

    1차: +10% → 30% 물량 익절
    2차: +20% → 30% 물량 익절
    3차: 트레일링 스탑으로 나머지 관리
    """
    entry = position.entry_price
    current = position.stock.current_price
    profit_pct = (current - entry) / entry * 100

    # 1차 익절 (+10%)
    if profit_pct >= 10 and not position.tp1_executed:
        sell_quantity = int(position.quantity * 0.30)
        result = sell_limit_order(position.stock, current, sell_quantity)

        if result.success:
            position.tp1_executed = True
            position.quantity -= sell_quantity
            log(f"[1차 익절] {position.stock.name}: 30% 물량 매도, +{profit_pct:.1f}%")

            # 손절가를 본전으로 상향 (손실 방지)
            position.stop_loss = entry

    # 2차 익절 (+20%)
    if profit_pct >= 20 and position.tp1_executed and not position.tp2_executed:
        sell_quantity = int(position.quantity * 0.50)  # 남은 물량의 50%
        result = sell_limit_order(position.stock, current, sell_quantity)

        if result.success:
            position.tp2_executed = True
            position.quantity -= sell_quantity
            log(f"[2차 익절] {position.stock.name}: 추가 매도, +{profit_pct:.1f}%")

            # 손절가를 +10% 위치로 상향
            position.stop_loss = entry * 1.10

    # 3차: 나머지는 트레일링 스탑으로 관리
    if position.tp2_executed:
        update_trailing_stop(position, trailing_pct=0.10)  # 10% 트레일링
```

### 7.4 익절 판단 보조 지표

```python
def should_take_profit(position):
    """
    익절 타이밍 판단 보조

    Returns:
        action: "FULL", "PARTIAL", "HOLD"
    """
    stock = position.stock
    profit_pct = (stock.current_price - position.entry_price) / position.entry_price * 100

    # 과매수 + 수익 구간 → 익절 적극 고려
    rsi = calculate_rsi(stock, 14)
    if rsi > 75 and profit_pct > 15:
        return "FULL"

    # 볼린저 상단 돌파 + 수익 구간 → 부분 익절
    upper_band = calculate_bollinger(stock)[0]
    if stock.current_price > upper_band and profit_pct > 10:
        return "PARTIAL"

    # MACD 약화 + 수익 구간 → 부분 익절
    macd, signal, histogram = calculate_macd(stock)
    if histogram < 0 and profit_pct > 10:
        return "PARTIAL"

    return "HOLD"
```

---

## 8. 포지션 관리

### 8.1 포지션 사이징

```python
# 기본 설정
MAX_POSITION_COUNT = 20         # 최대 종목 수
MAX_SINGLE_POSITION = 0.10      # 단일 종목 최대 비중 10%
MIN_SINGLE_POSITION = 0.03      # 단일 종목 최소 비중 3%
CASH_RESERVE = 0.10             # 현금 보유 비율 10%

def calculate_position_size(stock, total_capital, risk_per_trade=0.02):
    """
    포지션 크기 계산 (ATR 기반)

    Args:
        stock: 종목
        total_capital: 총 자본금
        risk_per_trade: 거래당 리스크 (기본 2%)

    Returns:
        position_size: 매수 금액
    """
    # 최대 손실 금액
    max_loss = total_capital * risk_per_trade

    # ATR 기반 손절폭
    atr = calculate_atr(stock, 14)
    stop_distance = atr * 2  # 2 ATR 손절

    # 손절폭 대비 적정 물량
    price = stock.current_price
    stop_loss_pct = stop_distance / price

    # 포지션 크기 = 최대 손실 / 손절률
    position_size = max_loss / stop_loss_pct

    # 최대/최소 비중 제한
    max_size = total_capital * MAX_SINGLE_POSITION
    min_size = total_capital * MIN_SINGLE_POSITION

    return max(min_size, min(max_size, position_size))
```

### 8.2 동일 비중 배분

```python
def equal_weight_allocation(total_capital, target_stocks):
    """
    동일 비중 배분

    Args:
        total_capital: 총 자본금
        target_stocks: 목표 종목 리스트
    """
    investable = total_capital * (1 - CASH_RESERVE)  # 현금 제외
    weight_per_stock = 1.0 / len(target_stocks)
    amount_per_stock = investable * weight_per_stock

    allocations = []
    for stock in target_stocks:
        allocations.append({
            'stock': stock,
            'target_weight': weight_per_stock,
            'target_amount': amount_per_stock,
            'target_quantity': int(amount_per_stock / stock.current_price)
        })

    return allocations
```

### 8.3 복합 점수 기반 비중 배분

```python
def score_weighted_allocation(total_capital, target_stocks):
    """
    복합 점수 비례 비중 배분
    높은 점수 종목에 더 많은 비중
    """
    investable = total_capital * (1 - CASH_RESERVE)

    # 점수 합계
    total_score = sum(s.composite_score for s in target_stocks)

    allocations = []
    for stock in target_stocks:
        # 점수 비례 비중 (최소/최대 제한)
        raw_weight = stock.composite_score / total_score
        weight = max(MIN_SINGLE_POSITION, min(MAX_SINGLE_POSITION, raw_weight))

        allocations.append({
            'stock': stock,
            'target_weight': weight,
            'target_amount': investable * weight,
            'target_quantity': int(investable * weight / stock.current_price)
        })

    # 비중 정규화 (합계가 90%가 되도록)
    weight_sum = sum(a['target_weight'] for a in allocations)
    for a in allocations:
        a['target_weight'] = a['target_weight'] / weight_sum * 0.90
        a['target_amount'] = total_capital * a['target_weight']

    return allocations
```

---

## 9. 리밸런싱

### 9.1 리밸런싱 주기

```
┌─────────────────────────────────────────────────────────────┐
│                     리밸런싱 스케줄                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  정기 리밸런싱: 매월 첫 거래일                                │
│  ├─ 전체 종목 재스크리닝                                     │
│  ├─ 복합 점수 재계산                                        │
│  └─ 포트폴리오 재구성                                        │
│                                                             │
│  비정기 리밸런싱: 아래 조건 충족 시                           │
│  ├─ 개별 종목 비중 15% 초과                                 │
│  ├─ 개별 종목 손절가 도달                                    │
│  ├─ 시장 급변 (KOSPI 일일 -3% 이상)                         │
│  └─ 재무 이슈 발생 (적자 전환, 감사의견 거절 등)              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 리밸런싱 프로세스

```python
def execute_rebalancing(portfolio, new_rankings, total_capital):
    """
    월별 리밸런싱 실행
    """
    # 1단계: 매도 대상 확인
    sell_list = []
    for position in portfolio.positions:
        new_rank = new_rankings.get(position.stock.code)

        # 순위 탈락 → 전량 매도
        if new_rank is None or new_rank > 30:
            sell_list.append({
                'position': position,
                'action': 'FULL_SELL',
                'reason': 'RANK_OUT'
            })
        # 급격한 악화 → 부분 매도
        elif new_rank > position.prev_rank * 2:
            sell_list.append({
                'position': position,
                'action': 'HALF_SELL',
                'reason': 'RANK_DROP'
            })

    # 2단계: 매도 실행
    for item in sell_list:
        if item['action'] == 'FULL_SELL':
            sell_all(item['position'])
        else:
            sell_half(item['position'])

    # 3단계: 신규 편입 종목 확인
    current_codes = [p.stock.code for p in portfolio.positions]
    new_entries = [s for s in new_rankings if s.code not in current_codes][:5]  # 상위 5개

    # 4단계: 신규 매수
    available_cash = portfolio.cash
    for stock in new_entries:
        if available_cash > total_capital * 0.03:  # 최소 3% 이상 매수
            amount = calculate_position_size(stock, total_capital)
            buy_order(stock, min(amount, available_cash * 0.5))
            available_cash -= amount

    # 5단계: 기존 종목 비중 조정
    rebalance_existing_positions(portfolio, total_capital)
```

### 9.3 거래비용 최소화

```python
def should_rebalance_position(current_weight, target_weight, threshold=0.03):
    """
    리밸런싱 필요 여부 판단
    소규모 차이는 무시하여 거래비용 절감

    Args:
        current_weight: 현재 비중
        target_weight: 목표 비중
        threshold: 리밸런싱 임계값 (기본 3%p)

    Returns:
        bool: 리밸런싱 필요 여부
    """
    diff = abs(current_weight - target_weight)
    return diff > threshold

# 예시: 현재 6%, 목표 5% → 차이 1%p → 리밸런싱 안 함 (거래비용 절감)
# 예시: 현재 12%, 목표 5% → 차이 7%p → 리밸런싱 실행
```

---

## 10. 리스크 관리

### 10.1 리스크 한도 설정

```python
# 리스크 관리 파라미터
RISK_PARAMS = {
    # 개별 종목 리스크
    'single_position_max': 0.10,      # 단일 종목 최대 비중 10%
    'single_loss_max': 0.10,          # 단일 종목 최대 손실 10%

    # 포트폴리오 리스크
    'daily_loss_limit': 0.02,         # 일일 손실 한도 2%
    'weekly_loss_limit': 0.05,        # 주간 손실 한도 5%
    'monthly_loss_limit': 0.10,       # 월간 손실 한도 10%
    'mdd_limit': 0.20,                # MDD 한도 20%

    # 연속 손실 대응
    'consecutive_loss_pause': 3,      # 3연속 손절 시 거래 중단
    'pause_duration_days': 5,         # 중단 기간 5거래일

    # 현금 비중
    'min_cash_ratio': 0.10,           # 최소 현금 비중 10%
    'crisis_cash_ratio': 0.50,        # 위기 시 현금 비중 50%
}
```

### 10.2 일일 리스크 모니터링

```python
def daily_risk_check(portfolio):
    """
    일일 리스크 체크
    한도 초과 시 경고 또는 자동 대응
    """
    alerts = []

    # 일일 손실 체크
    daily_pnl = portfolio.daily_pnl_pct
    if daily_pnl < -RISK_PARAMS['daily_loss_limit']:
        alerts.append({
            'type': 'DAILY_LOSS_EXCEEDED',
            'value': daily_pnl,
            'action': 'HALT_NEW_ORDERS'
        })

    # MDD 체크
    current_mdd = calculate_mdd(portfolio)
    if current_mdd > RISK_PARAMS['mdd_limit']:
        alerts.append({
            'type': 'MDD_EXCEEDED',
            'value': current_mdd,
            'action': 'REDUCE_EXPOSURE_50%'
        })

    # 단일 종목 비중 체크
    for position in portfolio.positions:
        weight = position.market_value / portfolio.total_value
        if weight > RISK_PARAMS['single_position_max'] * 1.5:  # 15% 초과
            alerts.append({
                'type': 'CONCENTRATION_RISK',
                'stock': position.stock.name,
                'value': weight,
                'action': 'REDUCE_TO_10%'
            })

    # 경고 처리
    for alert in alerts:
        log_alert(alert)
        if alert.get('action'):
            execute_risk_action(alert)

    return alerts
```

### 10.3 시장 위기 대응

```python
def check_market_crisis():
    """
    시장 위기 상황 감지
    """
    kospi = get_kospi_index()
    kospi_change = get_daily_change(kospi)
    vix = get_volatility_index()  # 또는 VKOSPI

    # 위기 레벨 판단
    crisis_level = 0

    # 일일 급락
    if kospi_change < -0.03:  # -3%
        crisis_level += 1
    if kospi_change < -0.05:  # -5%
        crisis_level += 2

    # 변동성 급등
    if vix > 25:
        crisis_level += 1
    if vix > 35:
        crisis_level += 2

    # 이동평균 하회
    if kospi < get_moving_average(kospi, 60):
        crisis_level += 1
    if kospi < get_moving_average(kospi, 120):
        crisis_level += 1

    return crisis_level

def execute_crisis_response(crisis_level, portfolio):
    """
    위기 레벨에 따른 대응
    """
    if crisis_level >= 5:
        # 심각: 현금 50%로 축소
        reduce_exposure(portfolio, target_cash_ratio=0.50)
        log("🚨 심각한 위기 감지: 현금 비중 50%로 확대")

    elif crisis_level >= 3:
        # 경계: 현금 30%로 축소
        reduce_exposure(portfolio, target_cash_ratio=0.30)
        log("⚠️ 위기 경계: 현금 비중 30%로 확대")

    elif crisis_level >= 1:
        # 주의: 신규 매수 중단
        pause_new_orders()
        log("⚡ 위기 주의: 신규 매수 중단")
```

### 10.4 연속 손실 관리

```python
def check_consecutive_losses(trade_history):
    """
    연속 손실 체크 및 대응
    """
    recent_trades = trade_history[-10:]  # 최근 10거래
    consecutive_losses = 0

    for trade in reversed(recent_trades):
        if trade.pnl < 0:
            consecutive_losses += 1
        else:
            break

    if consecutive_losses >= RISK_PARAMS['consecutive_loss_pause']:
        log(f"🛑 {consecutive_losses}연속 손실 발생: {RISK_PARAMS['pause_duration_days']}일간 거래 중단")
        pause_trading(days=RISK_PARAMS['pause_duration_days'])

        # 전략 점검 알림
        notify_strategy_review()

        return True

    return False
```

---

## 11. API 구현 계획

### 11.1 필요 API 목록

#### 필수 구현 (우선순위 높음)

| 순번 | API 명 | TR ID | 용도 | 현재 상태 |
|------|--------|-------|------|-----------|
| 1 | 재무비율 조회 | `FHKST66430300` | PER, PBR, ROE, EPS | ❌ 미구현 |
| 2 | 시가총액 순위 | `FHPST01740000` | 유동성 필터, 유니버스 | ❌ 미구현 |
| 3 | 거래량 순위 | `FHPST01710000` | 유동성 확인 | ❌ 미구현 |
| 4 | 기간별 시세 | `FHKST03010100` | 모멘텀 계산 (일/주/월봉) | ⚠️ 일부 |
| 5 | 손익계산서 | `FHKST66430200` | 영업이익, 매출 | ❌ 미구현 |
| 6 | 재무상태표 | `FHKST66430100` | 부채비율, 자본 | ❌ 미구현 |

#### 권장 구현 (우선순위 중간)

| 순번 | API 명 | TR ID | 용도 | 현재 상태 |
|------|--------|-------|------|-----------|
| 7 | 52주 신고저가 | `FHPST01730000` | 모멘텀 보조 | ❌ 미구현 |
| 8 | 배당 정보 | `HHKDB669101C0` | 가치 팩터 | ❌ 미구현 |
| 9 | 투자자별 매매동향 | `FHKST01010600` | 수급 분석 | ❌ 미구현 |
| 10 | 업종 현재가 | `FHKUP03500100` | 섹터 분류 | ❌ 미구현 |

#### 선택 구현 (우선순위 낮음)

| 순번 | API 명 | TR ID | 용도 | 현재 상태 |
|------|--------|-------|------|-----------|
| 11 | 외국인 순매수 | `FHPST01760000` | 수급 분석 | ❌ 미구현 |
| 12 | 기관 순매수 | `FHPST01770000` | 수급 분석 | ❌ 미구현 |
| 13 | 종목 정보 | `CTPF1002R` | 종목 기본 정보 | ❌ 미구현 |

### 11.2 데이터 수집 설계

```
┌─────────────────────────────────────────────────────────────┐
│                    데이터 수집 파이프라인                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 일일 수집 (매일 16:00 장 마감 후)                         │
│     ├─ 전 종목 현재가/거래량                                 │
│     ├─ 시가총액 순위 TOP 500                                │
│     └─ 거래량 순위 TOP 100                                  │
│                                                             │
│  2. 주간 수집 (매주 금요일)                                  │
│     ├─ 일봉 데이터 (최근 250일)                             │
│     └─ 52주 신고저가                                        │
│                                                             │
│  3. 분기 수집 (실적 발표 후)                                 │
│     ├─ 재무비율 (PER, PBR, ROE)                            │
│     ├─ 손익계산서                                           │
│     ├─ 재무상태표                                           │
│     └─ 배당 정보                                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 11.3 구현 클래스 설계

```python
# src/api/kis_quant.py

from dataclasses import dataclass
from typing import List, Optional
from .kis_client import KISClient


@dataclass
class FinancialData:
    """재무 데이터"""
    code: str
    name: str
    per: float
    pbr: float
    roe: float
    eps: float
    bps: float
    operating_margin: float
    debt_ratio: float
    dividend_yield: float


@dataclass
class MomentumData:
    """모멘텀 데이터"""
    code: str
    return_1m: float
    return_3m: float
    return_6m: float
    return_12m: float
    high_52w: int
    low_52w: int
    distance_from_high: float  # 52주 고점 대비 (%)


@dataclass
class RankingItem:
    """순위 데이터"""
    rank: int
    code: str
    name: str
    price: int
    change_pct: float
    volume: int
    market_cap: int  # 시가총액 (억원)


class KISQuantClient(KISClient):
    """퀀트 전략용 확장 클라이언트"""

    def get_financial_data(self, stock_code: str) -> FinancialData:
        """
        재무비율 조회 (가치 팩터용)

        TR ID: FHKST66430300
        """
        tr_id = "FHKST66430300"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/finance/financial-ratio",
            tr_id=tr_id,
            params=params
        )

        output = data.get("output", {})

        return FinancialData(
            code=stock_code,
            name=output.get("hts_kor_isnm", ""),
            per=float(output.get("per", 0) or 0),
            pbr=float(output.get("pbr", 0) or 0),
            roe=float(output.get("roe", 0) or 0),
            eps=float(output.get("eps", 0) or 0),
            bps=float(output.get("bps", 0) or 0),
            operating_margin=float(output.get("bsop_prfi_inrt", 0) or 0),
            debt_ratio=float(output.get("lblt_rate", 0) or 0),
            dividend_yield=float(output.get("dvdn_rate", 0) or 0)
        )

    def get_market_cap_ranking(self, count: int = 100) -> List[RankingItem]:
        """
        시가총액 순위 조회

        TR ID: FHPST01740000
        """
        tr_id = "FHPST01740000"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20174",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0",
            "FID_INPUT_DATE_1": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/ranking/market-cap",
            tr_id=tr_id,
            params=params
        )

        result = []
        for i, item in enumerate(data.get("output", [])[:count], 1):
            result.append(RankingItem(
                rank=i,
                code=item.get("stck_shrn_iscd", ""),
                name=item.get("hts_kor_isnm", ""),
                price=int(item.get("stck_prpr", 0)),
                change_pct=float(item.get("prdy_ctrt", 0)),
                volume=int(item.get("acml_vol", 0)),
                market_cap=int(item.get("stck_avls", 0))  # 시가총액 (억원)
            ))

        return result

    def get_volume_ranking(self, count: int = 100) -> List[RankingItem]:
        """
        거래량 순위 조회

        TR ID: FHPST01710000
        """
        tr_id = "FHPST01710000"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0",
            "FID_INPUT_DATE_1": ""
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/ranking/volume",
            tr_id=tr_id,
            params=params
        )

        result = []
        for i, item in enumerate(data.get("output", [])[:count], 1):
            result.append(RankingItem(
                rank=i,
                code=item.get("stck_shrn_iscd", ""),
                name=item.get("hts_kor_isnm", ""),
                price=int(item.get("stck_prpr", 0)),
                change_pct=float(item.get("prdy_ctrt", 0)),
                volume=int(item.get("acml_vol", 0)),
                market_cap=0
            ))

        return result

    def get_52week_high_low(self, count: int = 50) -> List[dict]:
        """
        52주 신고저가 종목 조회

        TR ID: FHPST01730000
        """
        tr_id = "FHPST01730000"

        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20173",
            "FID_INPUT_ISCD": "0000",
            "FID_DIV_CLS_CODE": "0",  # 0: 52주 신고가
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "000000",
            "FID_INPUT_PRICE_1": "0",
            "FID_INPUT_PRICE_2": "0",
            "FID_VOL_CNT": "0"
        }

        data = self._request(
            method="GET",
            endpoint="/uapi/domestic-stock/v1/ranking/highlow-price",
            tr_id=tr_id,
            params=params
        )

        result = []
        for item in data.get("output", [])[:count]:
            result.append({
                "code": item.get("stck_shrn_iscd", ""),
                "name": item.get("hts_kor_isnm", ""),
                "price": int(item.get("stck_prpr", 0)),
                "high_52w": int(item.get("stck_sdpr", 0)),  # 52주 최고
                "low_52w": int(item.get("stck_lwpr", 0)),   # 52주 최저
            })

        return result

    def calculate_momentum(self, stock_code: str) -> MomentumData:
        """
        모멘텀 데이터 계산 (일봉 데이터 기반)
        """
        # 일봉 데이터 조회 (최근 250일)
        history = self.get_stock_history(stock_code, period="D", count=250)

        if len(history) < 250:
            raise ValueError(f"데이터 부족: {len(history)}일")

        current_price = history[0]['close']

        # 기간별 수익률 계산
        return_1m = (current_price - history[21]['close']) / history[21]['close'] * 100
        return_3m = (current_price - history[63]['close']) / history[63]['close'] * 100
        return_6m = (current_price - history[126]['close']) / history[126]['close'] * 100
        return_12m = (current_price - history[249]['close']) / history[249]['close'] * 100

        # 52주 고저가
        prices = [h['close'] for h in history]
        high_52w = max(prices)
        low_52w = min(prices)
        distance_from_high = (current_price - high_52w) / high_52w * 100

        return MomentumData(
            code=stock_code,
            return_1m=return_1m,
            return_3m=return_3m,
            return_6m=return_6m,
            return_12m=return_12m,
            high_52w=high_52w,
            low_52w=low_52w,
            distance_from_high=distance_from_high
        )
```

### 11.4 스크리닝 서비스 설계

```python
# src/strategy/screener.py

from dataclasses import dataclass
from typing import List
from src.api.kis_quant import KISQuantClient, FinancialData, MomentumData


@dataclass
class StockScore:
    """종목별 통합 점수"""
    code: str
    name: str
    value_score: float
    momentum_score: float
    quality_score: float
    composite_score: float
    rank: int


class MultiFactorScreener:
    """멀티팩터 종목 스크리너"""

    def __init__(self, client: KISQuantClient):
        self.client = client

        # 팩터 가중치
        self.weights = {
            'value': 0.40,
            'momentum': 0.30,
            'quality': 0.30
        }

    def screen(self, target_count: int = 20) -> List[StockScore]:
        """
        종목 스크리닝 실행

        Args:
            target_count: 선정할 종목 수

        Returns:
            StockScore 리스트 (점수 순)
        """
        # 1단계: 유니버스 구성 (시가총액 상위 300)
        universe = self.client.get_market_cap_ranking(count=300)

        scores = []

        for stock in universe:
            try:
                # 2단계: 각 팩터 점수 계산
                financial = self.client.get_financial_data(stock.code)
                momentum = self.client.calculate_momentum(stock.code)

                # 기본 필터 (재무 건전성)
                if not self._pass_basic_filter(financial):
                    continue

                # 점수 계산
                value_score = self._calculate_value_score(financial)
                momentum_score = self._calculate_momentum_score(momentum)
                quality_score = self._calculate_quality_score(financial)

                composite = (
                    value_score * self.weights['value'] +
                    momentum_score * self.weights['momentum'] +
                    quality_score * self.weights['quality']
                )

                scores.append(StockScore(
                    code=stock.code,
                    name=stock.name,
                    value_score=value_score,
                    momentum_score=momentum_score,
                    quality_score=quality_score,
                    composite_score=composite,
                    rank=0
                ))

            except Exception as e:
                print(f"스크리닝 오류 ({stock.code}): {e}")
                continue

        # 3단계: 순위 정렬
        scores.sort(key=lambda x: x.composite_score, reverse=True)

        for i, score in enumerate(scores, 1):
            score.rank = i

        # 4단계: 섹터 분산 적용 (필요시)
        # final_selection = self._apply_sector_diversification(scores, target_count)

        return scores[:target_count]

    def _pass_basic_filter(self, financial: FinancialData) -> bool:
        """기본 필터 (필수 조건)"""
        # 흑자 기업
        if financial.per <= 0:
            return False
        # 과도한 고평가 제외
        if financial.per > 50:
            return False
        # 자본잠식 제외
        if financial.pbr <= 0:
            return False
        # 최소 수익성
        if financial.roe < 3:
            return False
        # 과도한 부채 제외
        if financial.debt_ratio > 300:
            return False

        return True

    def _calculate_value_score(self, financial: FinancialData) -> float:
        """가치 점수 계산 (0~100)"""
        score = 50  # 기본 점수

        # PER 점수 (낮을수록 좋음)
        if financial.per < 8:
            score += 20
        elif financial.per < 12:
            score += 10
        elif financial.per > 25:
            score -= 15

        # PBR 점수 (낮을수록 좋음)
        if financial.pbr < 0.7:
            score += 20
        elif financial.pbr < 1.0:
            score += 10
        elif financial.pbr > 3:
            score -= 15

        # 배당수익률 점수
        if financial.dividend_yield > 4:
            score += 10
        elif financial.dividend_yield > 2:
            score += 5

        return max(0, min(100, score))

    def _calculate_momentum_score(self, momentum: MomentumData) -> float:
        """모멘텀 점수 계산 (0~100)"""
        score = 50

        # 12개월 수익률
        if momentum.return_12m > 30:
            score += 20
        elif momentum.return_12m > 15:
            score += 10
        elif momentum.return_12m < -10:
            score -= 15

        # 6개월 수익률
        if momentum.return_6m > 20:
            score += 15
        elif momentum.return_6m > 10:
            score += 7
        elif momentum.return_6m < -5:
            score -= 10

        # 52주 고점 근접도
        if momentum.distance_from_high > -5:
            score += 10  # 고점 근접 (강한 모멘텀)
        elif momentum.distance_from_high < -30:
            score -= 10  # 고점 대비 급락

        # 단기 과열 페널티
        if momentum.return_1m > 20:
            score -= 10

        return max(0, min(100, score))

    def _calculate_quality_score(self, financial: FinancialData) -> float:
        """퀄리티 점수 계산 (0~100)"""
        score = 50

        # ROE 점수
        if financial.roe > 20:
            score += 20
        elif financial.roe > 12:
            score += 10
        elif financial.roe < 5:
            score -= 15

        # 영업이익률 점수
        if financial.operating_margin > 15:
            score += 15
        elif financial.operating_margin > 8:
            score += 7
        elif financial.operating_margin < 3:
            score -= 10

        # 부채비율 점수 (낮을수록 좋음)
        if financial.debt_ratio < 50:
            score += 15
        elif financial.debt_ratio < 100:
            score += 7
        elif financial.debt_ratio > 200:
            score -= 15

        return max(0, min(100, score))
```

### 11.5 구현 로드맵

```
┌─────────────────────────────────────────────────────────────┐
│                      구현 로드맵                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Phase 1: 데이터 수집 기반 (1~2주)                           │
│  ├─ [ ] 재무비율 API 구현 (FHKST66430300)                   │
│  ├─ [ ] 시가총액 순위 API 구현 (FHPST01740000)               │
│  ├─ [ ] 거래량 순위 API 구현 (FHPST01710000)                 │
│  └─ [ ] 52주 신고저가 API 구현 (FHPST01730000)               │
│                                                             │
│  Phase 2: 팩터 계산 엔진 (1주)                               │
│  ├─ [ ] 가치 점수 계산기 구현                                │
│  ├─ [ ] 모멘텀 점수 계산기 구현                              │
│  ├─ [ ] 퀄리티 점수 계산기 구현                              │
│  └─ [ ] 통합 점수 계산기 구현                                │
│                                                             │
│  Phase 3: 스크리닝 서비스 (1주)                              │
│  ├─ [ ] 종목 스크리너 클래스 구현                            │
│  ├─ [ ] 섹터 분산 로직 구현                                  │
│  ├─ [ ] 데이터 캐싱 구현                                     │
│  └─ [ ] 스케줄러 연동                                        │
│                                                             │
│  Phase 4: 매매 실행 (1~2주)                                  │
│  ├─ [ ] 매수 타이밍 판단 로직                                │
│  ├─ [ ] 매도 타이밍 판단 로직                                │
│  ├─ [ ] 손절/익절 자동화                                     │
│  └─ [ ] 리밸런싱 자동화                                      │
│                                                             │
│  Phase 5: 모니터링 & 알림 (1주)                              │
│  ├─ [ ] 리스크 모니터링 대시보드                             │
│  ├─ [ ] 텔레그램 알림 연동                                   │
│  └─ [ ] 일일/주간 리포트 생성                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 11.6 디렉토리 구조

```
src/
├── api/
│   ├── kis_auth.py          # 인증 (기존)
│   ├── kis_client.py        # 기본 클라이언트 (기존)
│   ├── kis_quant.py         # 퀀트 확장 클라이언트 (신규)
│   └── kis_websocket.py     # 실시간 (기존)
│
├── strategy/
│   ├── __init__.py
│   ├── screener.py          # 종목 스크리너 (신규)
│   ├── factors/
│   │   ├── value.py         # 가치 팩터
│   │   ├── momentum.py      # 모멘텀 팩터
│   │   └── quality.py       # 퀄리티 팩터
│   ├── signals/
│   │   ├── buy_signal.py    # 매수 신호
│   │   ├── sell_signal.py   # 매도 신호
│   │   └── technical.py     # 기술적 지표
│   └── risk/
│       ├── stop_loss.py     # 손절 관리
│       ├── take_profit.py   # 익절 관리
│       └── position.py      # 포지션 관리
│
├── portfolio/
│   ├── manager.py           # 포트폴리오 관리
│   ├── rebalancer.py        # 리밸런싱
│   └── risk_monitor.py      # 리스크 모니터링
│
└── scheduler/
    ├── daily_job.py         # 일일 작업
    ├── weekly_job.py        # 주간 작업
    └── monthly_job.py       # 월간 작업
```

---

## 부록: 체크리스트

### 매수 전 체크리스트

```
□ 종목이 복합 점수 상위 20위 이내인가?
□ 시장 환경(KOSPI 추세)을 확인했는가?
□ 기술적 매수 신호 점수가 60점 이상인가?
□ RSI가 70 이하인가? (과매수 아님)
□ 포지션 크기가 총 자본의 10% 이하인가?
□ 손절가를 사전에 설정했는가?
□ 섹터 분산 규칙을 준수하는가?
```

### 매도 전 체크리스트

```
□ 손절가에 도달했는가? → 즉시 매도
□ 익절 목표가에 도달했는가? → 단계적 매도
□ 복합 점수가 하위 30%로 떨어졌는가?
□ 기술적 매도 신호가 2개 이상인가?
□ 리밸런싱 시점에 순위권 이탈했는가?
```

### 월간 점검 체크리스트

```
□ 포트폴리오 수익률 기록
□ 벤치마크(KOSPI) 대비 성과 비교
□ MDD 확인 (20% 초과 여부)
□ 거래비용 합계 확인
□ 승률 및 손익비 계산
□ 전략 수정 필요성 검토
```

---

> **문서 버전 이력**
> - v1.0 (2024-12-25): 최초 작성
