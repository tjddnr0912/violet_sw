# 02. Ver3 매매 전략

## 시장 레짐 분류

### 레짐 판단 기준

```python
ema_diff_pct = (EMA50 - EMA200) / EMA200 * 100

if ema_diff_pct > 5.0:
    regime = "strong_bullish"
elif ema_diff_pct > 2.0:
    regime = "bullish"
elif ema_diff_pct > -2.0:
    regime = "neutral"
elif ema_diff_pct > -5.0:
    regime = "bearish"
else:
    regime = "strong_bearish"

# ADX < 20이면 ranging으로 오버라이드
if adx < 20:
    regime = "ranging"
```

### 레짐별 전략 모드

| 레짐 | 모드 | 진입 기준 | 청산 타겟 |
|------|------|----------|----------|
| Strong Bullish | 추세추종 | 기본 스코어 | BB Upper |
| Bullish | 추세추종 | 기본 스코어 | BB Upper |
| Neutral | 관망 | 높은 스코어 | BB Middle |
| Bearish | 평균회귀 | 높은 스코어 | BB Middle |
| Strong Bearish | 평균회귀 | 매우 높은 스코어 | BB Middle |
| Ranging | 박스권 | 기본 스코어 | BB Upper/Lower |

## 진입 스코어 시스템

### 스코어 구성요소

```python
entry_score = 0

# 1. BB Touch (1점)
if price <= bb_lower:
    entry_score += 1.0 * weights['bb_touch']

# 2. RSI Oversold (1점)
if rsi < rsi_oversold_threshold:  # 기본 30
    entry_score += 1.0 * weights['rsi_oversold']

# 3. Stochastic Cross (2점)
if stoch_k < stoch_oversold and stoch_k crosses above stoch_d:
    entry_score += 2.0 * weights['stoch_cross']
```

### 레짐별 최소 스코어

| 레짐 | 최소 스코어 |
|------|-------------|
| Strong Bullish | 1 |
| Bullish | 1 |
| Neutral | 2 |
| Bearish | 2 |
| Strong Bearish | 3 |
| Ranging | 2 |

## 청산 전략

### 1. Chandelier Exit (손절)

```python
# ATR 기반 동적 손절
atr_stop = entry_price - (ATR * chandelier_multiplier)

# 레짐별 배수 조정
if regime in ['bearish', 'strong_bearish']:
    chandelier_multiplier *= 0.8  # 더 타이트
```

### 2. Profit Target (익절)

| 모드 | 타겟 | 청산 비율 |
|------|------|----------|
| 추세추종 | BB Upper | 50% → 50% |
| 평균회귀 | BB Middle | 100% (전량) |

### 3. 부분 청산 (TP1/TP2)

```python
# TP1: 1.5R (50% 청산)
tp1_price = entry_price + (risk * 1.5)

# TP2: 2.5R (나머지 전량 청산)
tp2_price = entry_price + (risk * 2.5)
```

## 동적 파라미터 조정

### 변동성 레벨

```python
atr_percent = ATR / price * 100

if atr_percent < 1.5:
    volatility = "LOW"
elif atr_percent < 3.0:
    volatility = "NORMAL"
elif atr_percent < 5.0:
    volatility = "HIGH"
else:
    volatility = "EXTREME"
```

### 변동성별 조정

| 변동성 | 포지션 크기 | Chandelier 배수 | 최소 스코어 |
|--------|-------------|-----------------|-------------|
| LOW | 1.2x | 3.5 | 기본 |
| NORMAL | 1.0x | 3.0 | 기본 |
| HIGH | 0.7x | 2.5 | +1 |
| EXTREME | 0.5x | 2.0 | +2 |

## 피라미딩 (추가 진입)

```python
max_entries = 3

# 진입 크기
entry_1 = base_size * 1.00  # 100%
entry_2 = base_size * 0.50  # 50%
entry_3 = base_size * 0.25  # 25%

# 조건: 가격이 이전 진입가 대비 X% 하락 시
pyramid_threshold = 3.0  # %
```

## 리스크 관리

### 일일 한도

```python
max_daily_loss_pct = 3.0  # 일일 최대 손실 3%
max_consecutive_losses = 3  # 연속 손실 횟수
max_positions = 2  # 동시 최대 포지션
```

### 포지션 사이징

```python
# ATR 기반 포지션 크기
risk_per_trade = capital * 0.01  # 1%
position_size = risk_per_trade / (ATR * chandelier_multiplier)
```
