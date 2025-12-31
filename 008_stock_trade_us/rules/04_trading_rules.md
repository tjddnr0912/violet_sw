# 매매 실행 규칙

## 주문 유형

### 시장가 주문 (Market Order)
```python
order_type = "01"  # KIS API 코드

# 사용 조건
- 유동성 충분한 종목 (거래량 > 10,000)
- 호가 스프레드 < 0.3%
- 급한 진입/청산 필요 시

# 슬리피지 예상: 0.1% ~ 0.3%
```

### 지정가 주문 (Limit Order)
```python
order_type = "00"  # KIS API 코드

# 사용 조건
- 유동성 부족 종목
- 호가 스프레드 > 0.3%
- 비용 절감 필요 시

# 가격 설정
buy_price = current_price * 0.998   # 0.2% 아래
sell_price = current_price * 1.002  # 0.2% 위
```

### 조건부 지정가
```python
order_type = "03"  # KIS API 코드

# 장 시작 시 시장가로 전환
# 사용: 장 시작 동시호가 참여
```

## 주문 실행 흐름

```
1. 신호 생성
   ↓
2. 주문 사전 검증
   - 잔고 확인
   - 한도 확인
   - 리스크 체크
   ↓
3. 주문 생성
   - 수량 계산
   - 가격 결정
   ↓
4. 주문 전송
   - dry_run 체크
   - API 호출
   ↓
5. 체결 확인
   - 미체결 모니터링
   - 정정/취소 처리
   ↓
6. 기록 및 알림
   - 거래 로그
   - 텔레그램 알림
```

## 주문 수량 계산

### 매수 수량
```python
def calculate_buy_quantity(stock_code, target_value, current_price):
    # 기본 계산
    quantity = int(target_value / current_price)

    # 최소 1주
    quantity = max(quantity, 1)

    # 유동성 한도
    avg_volume = get_avg_volume(stock_code)
    max_qty = int(avg_volume * 0.01)  # 일평균의 1%
    quantity = min(quantity, max_qty)

    return quantity
```

### 매도 수량
```python
def calculate_sell_quantity(position, action_type):
    if action_type == "FULL":
        return position.quantity
    elif action_type == "HALF":
        return position.quantity // 2
    elif action_type == "PARTIAL":
        return int(position.quantity * sell_ratio)
```

## 체결 관리

### 미체결 처리
```python
# 미체결 확인 간격
CHECK_INTERVAL = 30  # 초

# 미체결 허용 시간
MAX_PENDING_TIME = 300  # 5분

# 처리 로직
if pending_time > MAX_PENDING_TIME:
    if can_modify:
        modify_order(order_id, new_price)
    else:
        cancel_order(order_id)
        resubmit_as_market()
```

### 부분 체결
```python
# 부분 체결 시
if filled_qty < order_qty:
    remaining = order_qty - filled_qty

    if remaining_value > MIN_ORDER_VALUE:
        submit_additional_order(remaining)
    else:
        log_partial_fill()
```

## 매매 시간 규칙

### 정규장
```python
MARKET_OPEN = "09:00"
MARKET_CLOSE = "15:30"

# 주문 가능 시간
ORDER_START = "09:00"
ORDER_END = "15:20"  # 마감 10분 전까지

# 리밸런싱 선호 시간
PREFERRED_HOURS = ["09:30", "14:00"]  # 장 초반, 후반
```

### 동시호가
```python
# 장 시작 동시호가
OPEN_AUCTION_START = "08:30"
OPEN_AUCTION_END = "09:00"

# 장 마감 동시호가
CLOSE_AUCTION_START = "15:20"
CLOSE_AUCTION_END = "15:30"
```

### 시간외 거래
```python
# 시간외 단일가
AFTER_HOURS_START = "15:40"
AFTER_HOURS_END = "18:00"

# 주의: 유동성 매우 낮음, 큰 물량 비권장
```

## 비용 관리

### 수수료
```python
# 기본 수수료율
COMMISSION_RATE = 0.00015  # 0.015%

# 최소 수수료
MIN_COMMISSION = 0  # 대부분 무료

# 수수료 계산
commission = max(trade_value * COMMISSION_RATE, MIN_COMMISSION)
```

### 세금
```python
# 매도 시 증권거래세
TRANSACTION_TAX = 0.0018  # 0.18% (코스피)
# KOSDAQ: 0.0023 (0.23%)

# 농특세 (2024년 폐지 예정)
AGRICULTURAL_TAX = 0.0015  # 0.15%
```

### 슬리피지
```python
# 예상 슬리피지
SLIPPAGE_RATE = 0.001  # 0.1%

# 총 비용 추정
total_cost = commission + tax + (trade_value * SLIPPAGE_RATE)
```

## Dry-Run 모드

### 모의 실행
```python
if config.dry_run:
    # 실제 주문 대신 로깅
    log_simulated_order(order)

    # 가상 체결 시뮬레이션
    simulated_fill = simulate_fill(order)

    # 가상 포지션 업데이트
    update_virtual_positions(simulated_fill)

    return SimulatedOrderResult(success=True)
```

### 전환 규칙
```python
# dry_run → 실전 전환 조건
LIVE_TRADING_PREREQUISITES = [
    "30일 이상 dry_run 테스트",
    "양의 수익률 달성",
    "최대 낙폭 < 10%",
    "API 연동 오류 0회",
]
```

## 에러 처리

### 주문 실패
```python
ERROR_HANDLERS = {
    "INSUFFICIENT_BALANCE": lambda: log_and_skip(),
    "INVALID_QUANTITY": lambda: recalculate_and_retry(),
    "MARKET_CLOSED": lambda: queue_for_next_session(),
    "RATE_LIMIT": lambda: wait_and_retry(seconds=1),
    "API_ERROR": lambda: retry_with_backoff(max_retries=3),
}
```

### 재시도 로직
```python
def submit_order_with_retry(order, max_retries=3):
    for attempt in range(max_retries):
        try:
            result = submit_order(order)
            return result
        except RetryableError as e:
            wait_time = 0.5 * (2 ** attempt)  # 지수 백오프
            time.sleep(wait_time)
        except FatalError as e:
            log_error(e)
            send_alert(e)
            return None

    return None
```

## 거래 기록

### 로그 형식
```python
trade_log = {
    "timestamp": "2024-12-26T09:30:00",
    "action": "BUY",
    "stock_code": "005930",
    "stock_name": "삼성전자",
    "quantity": 10,
    "price": 70000,
    "amount": 700000,
    "commission": 105,
    "order_type": "MARKET",
    "order_id": "KIS123456",
    "status": "FILLED",
}
```

### 거래 내역 저장
```python
# JSON 형식으로 저장
TRADE_HISTORY_FILE = "data/quant/trade_history.json"

def save_trade(trade):
    with open(TRADE_HISTORY_FILE, "a") as f:
        f.write(json.dumps(trade) + "\n")
```
