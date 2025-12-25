# 리스크 관리 규칙

## 포지션 사이징

### 동일 가중 방식 (기본)
```python
# 목표 종목 수: 20개
# 종목당 비중: 5%
position_weight = 1.0 / target_count
position_value = total_capital * position_weight
```

### 변동성 기반 사이징
```python
# ATR (Average True Range) 사용
atr = calculate_atr(prices, period=14)
atr_percent = atr / current_price

# 목표 변동성: 2%
target_volatility = 0.02
position_size = target_volatility / atr_percent

# 최대 한도 적용
position_size = min(position_size, max_position_size)
```

### 켈리 기준
```python
# 승률과 손익비 기반
win_rate = 0.55
profit_loss_ratio = 1.5

kelly = win_rate - (1 - win_rate) / profit_loss_ratio
half_kelly = kelly / 2  # 보수적 접근

# 최대 25%로 제한
position_size = min(half_kelly, 0.25)
```

## 손절/익절 규칙

### 손절 (Stop-Loss)
```python
# 고정 비율 손절
stop_loss_pct = 0.07  # -7%
stop_price = entry_price * (1 - stop_loss_pct)

# ATR 기반 손절
stop_price = entry_price - (atr * 2.0)

# 추적 손절 (Trailing Stop)
trailing_stop = highest_since_entry * (1 - trailing_pct)
stop_price = max(stop_price, trailing_stop)
```

### 익절 (Take-Profit)
```python
# 고정 비율 익절
take_profit_pct = 0.15  # +15%
tp_price = entry_price * (1 + take_profit_pct)

# 분할 익절
tp1_price = entry_price * 1.10  # +10%에서 50% 매도
tp2_price = entry_price * 1.20  # +20%에서 나머지 매도

# 손익비 기반
risk = entry_price - stop_price
reward = risk * reward_ratio  # 손익비 2:1
tp_price = entry_price + reward
```

## 리밸런싱 규칙

### 정기 리밸런싱
```python
# 빈도
REBALANCE_FREQUENCY = "M"  # Monthly (월 1회)
# 옵션: "W" (주간), "M" (월간), "Q" (분기)

# 실행 조건
- 마지막 리밸런싱으로부터 지정 기간 경과
- 장 중 (09:30 ~ 15:20)
- 월요일 (또는 월초 첫 거래일)
```

### 비중 이탈 리밸런싱
```python
# 목표 비중 대비 이탈 허용 범위
DEVIATION_THRESHOLD = 0.02  # 2%

# 종목별 체크
for position in positions:
    deviation = abs(position.weight - target_weight)
    if deviation > DEVIATION_THRESHOLD:
        add_to_rebalance_list(position)
```

### 리밸런싱 액션
```python
# 매수 대상
for stock in new_selections:
    if stock not in current_holdings:
        action = "BUY"
        quantity = calculate_quantity(stock, target_weight)

# 매도 대상
for stock in current_holdings:
    if stock not in new_selections:
        action = "SELL"
        quantity = current_quantity

# 비중 조정
for stock in both:
    weight_diff = target_weight - current_weight
    if abs(weight_diff) > DEVIATION_THRESHOLD:
        action = "ADJUST"
        quantity = calculate_adjustment(weight_diff)
```

## 일일 리스크 한도

### 손실 한도
```python
# 일일 최대 손실
MAX_DAILY_LOSS = 0.03  # -3%

# 체크 로직
daily_pnl = (current_value - start_value) / start_value
if daily_pnl < -MAX_DAILY_LOSS:
    stop_trading = True
    send_alert("일일 손실 한도 도달")
```

### 연속 손실 한도
```python
# 연속 손절 횟수
MAX_CONSECUTIVE_LOSSES = 3

if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
    pause_trading(hours=24)
    reduce_position_size(factor=0.5)
```

### 거래 빈도 한도
```python
# 일일 최대 거래
MAX_DAILY_TRADES = 20

# 분당 최대 주문
MAX_ORDERS_PER_MINUTE = 5
```

## 섹터 집중 리스크

### 섹터 비중 한도
```python
MAX_SECTOR_WEIGHT = 0.30  # 30%

# 체크 로직
for sector, allocation in sector_allocations.items():
    if allocation.weight > MAX_SECTOR_WEIGHT:
        violations.append({
            "sector": sector,
            "weight": allocation.weight,
            "action": "REDUCE"
        })
```

### 최소 분산
```python
MIN_SECTOR_COUNT = 3  # 최소 3개 섹터

active_sectors = count_active_sectors(positions)
if active_sectors < MIN_SECTOR_COUNT:
    alert("섹터 분산 부족")
```

## 유동성 리스크

### 거래량 체크
```python
# 최소 일평균 거래량
MIN_AVG_VOLUME = 10000  # 1만주

# 거래량 대비 주문량
MAX_VOLUME_RATIO = 0.01  # 일평균의 1%

order_quantity = min(
    target_quantity,
    avg_volume * MAX_VOLUME_RATIO
)
```

### 호가 스프레드
```python
# 최대 스프레드
MAX_SPREAD = 0.005  # 0.5%

spread = (ask - bid) / mid
if spread > MAX_SPREAD:
    use_limit_order = True
    delay_execution = True
```

## 비상 정지 조건

```python
EMERGENCY_STOP_CONDITIONS = [
    daily_loss > 0.05,           # 일일 -5% 손실
    total_loss > 0.10,           # 총 -10% 손실
    consecutive_losses >= 5,      # 5연속 손절
    api_errors >= 10,            # API 에러 10회
    execution_failures >= 3,      # 주문 실패 3회
]

if any(EMERGENCY_STOP_CONDITIONS):
    engine.emergency_stop()
    send_urgent_alert("비상 정지 발동")
```

## 리스크 모니터링

### 실시간 모니터링
```python
# 10분마다 체크
MONITOR_INTERVAL = 600  # seconds

def monitor():
    check_daily_pnl()
    check_position_limits()
    check_sector_concentration()
    check_liquidity()

    if alerts:
        send_telegram_alerts(alerts)
```

### 일간 리포트
```python
# 장 마감 후 생성
def daily_report():
    return {
        "date": today,
        "pnl": daily_pnl,
        "trades": trade_count,
        "wins": win_count,
        "losses": loss_count,
        "max_drawdown": max_dd,
        "sharpe": calculate_sharpe(),
    }
```
