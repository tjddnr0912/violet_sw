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

| 레짐 | 모드 | 진입 배수 | 손절 배수 | 청산 타겟 |
|------|------|----------|----------|----------|
| Strong Bullish | 추세추종 | 1.0x | 1.0x | BB Upper |
| Bullish | 추세추종 | 1.0x | 1.0x | BB Upper |
| Neutral | 관망 | 1.2x | 1.0x | BB Middle |
| Bearish | 평균회귀 | 1.3x | 0.85x | BB Middle |
| Strong Bearish | 평균회귀 | 1.5x | 0.8x | BB Middle |
| Ranging | 박스권 | 1.0x | 1.0x | BB Upper/Lower |

> **Note (2026-01)**: Bearish/Strong Bearish 레짐의 진입 조건 완화 및 손절 여유 확보
> - Bearish: 진입 배수 1.5 → 1.3, 손절 배수 0.7 → 0.85
> - Strong Bearish: 진입 배수 2.0 → 1.5, 손절 배수 0.5 → 0.8

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
| Bearish | 2 + Extreme Oversold |
| Strong Bearish | 3 + Extreme Oversold |
| Ranging | 2 |

### Extreme Oversold 조건 (Bearish 레짐 전용)

Bearish/Strong Bearish 레짐에서는 스코어 충족 외에 **Extreme Oversold** 조건 필요:

```python
# 3가지 중 2가지 이상 충족 시 진입 허용
extreme_conditions = [
    rsi < 20,           # RSI 극단적 과매도
    stoch_k < 10,       # Stochastic 극단적 과매도
    price <= bb_lower   # BB Lower 터치
]
is_extreme_oversold = sum(extreme_conditions) >= 2
```

| 조건 | 임계값 |
|------|--------|
| RSI | < 20 |
| Stochastic K | < 10 |
| BB Lower | price <= bb_lower |

## 청산 전략

### 1. Chandelier Exit (손절)

```python
# ATR 기반 동적 손절
atr_stop = entry_price - (ATR * chandelier_multiplier)

# 레짐별 손절 배수 조정 (2026-01 업데이트)
# Bearish: 0.85 (기존 0.7 → 완화)
# Strong Bearish: 0.8 (기존 0.5 → 완화)
if regime == 'bearish':
    chandelier_multiplier *= 0.85
elif regime == 'strong_bearish':
    chandelier_multiplier *= 0.8
```

### 2. Trailing Stop (TP1 이후 수익 보호)

TP1 도달 후 활성화되는 동적 손절선:

```python
# TP1 달성 후 활성화
if position.first_target_hit:
    # 최고가 갱신 시 손절선도 상향
    if current_price > position.highest_high:
        position.highest_high = current_price
        new_stop = highest_high * (1 - trailing_pct / 100)  # 기본 2%

        # 손절선은 상향만 가능 (하향 금지)
        if new_stop > position.stop_loss:
            position.stop_loss = new_stop
```

| 설정 | 값 | 설명 |
|------|-----|------|
| `trailing_pct` | 2.0% | 최고가 대비 하락 허용폭 |
| 활성화 조건 | TP1 달성 후 | 수익 구간에서만 작동 |
| 방향 | 상향만 | 손절선 하향 방지 |

### 3. Profit Target (익절)

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
| EXTREME | 0.5x | 2.5 | +2 |

> **Note (2026-01)**: Chandelier 배수 최소값이 2.0 → 2.5로 상향됨 (과도한 손절 방지)

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

### 관찰 모드 (Observation Mode)

연속 손실 발생 시 자동으로 새 진입을 일시 중단하는 보호 장치:

```python
# 관찰 모드 진입 조건
if consecutive_losses >= 3:
    observation_mode = True

# 관찰 모드 동작
if observation_mode:
    # 새 진입 불가 (BUY 신호 무시)
    # 손절/익절은 정상 처리
    skip_new_entries()
```

| 상태 | 새 진입 | 손절 | 익절 |
|------|--------|------|------|
| 정상 | ✅ | ✅ | ✅ |
| 관찰 모드 | ❌ | ✅ | ✅ |

**로그 메시지:**
- 진입 시: `🔍 관찰 모드 활성: {reason}`
- 건너뜀: `⏸️ 관찰 모드: 새 진입 건너뜀`

### 포지션 사이징

```python
# ATR 기반 포지션 크기
risk_per_trade = capital * 0.01  # 1%
position_size = risk_per_trade / (ATR * chandelier_multiplier)
```
