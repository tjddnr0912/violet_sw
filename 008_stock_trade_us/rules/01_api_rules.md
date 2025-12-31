# API 사용 규칙

## KIS Open API 제한사항

### 요청 한도
- **초당 요청 수**: 최대 20회/초
- **일일 요청 수**: 100,000회/일 (모의투자 기준)
- **시가총액 조회**: 최대 30개 종목만 반환

### 토큰 관리
```python
# 토큰 캐싱 위치
config/token.json

# 토큰 구조
{
    "access_token": "...",
    "token_type": "Bearer",
    "expires_at": "2024-12-26T10:00:00"
}

# 갱신 조건
- expires_at 10분 전 자동 갱신
- 401 응답 시 즉시 갱신 시도
```

### API 엔드포인트

| 기능 | 엔드포인트 | 비고 |
|------|-----------|------|
| 토큰 발급 | `/oauth2/tokenP` | POST |
| 시가총액 순위 | `/uapi/domestic-stock/v1/ranking/market-cap` | 최대 30개 |
| 현재가 | `/uapi/domestic-stock/v1/quotations/inquire-price` | |
| 일봉 | `/uapi/domestic-stock/v1/quotations/inquire-daily-price` | 최대 100일 |
| 재무 데이터 | `/uapi/domestic-stock/v1/finance/financial-ratio` | |
| 주문 | `/uapi/domestic-stock/v1/trading/order-cash` | 모의/실전 URL 다름 |
| 잔고 조회 | `/uapi/domestic-stock/v1/trading/inquire-balance` | |

### 모의투자 vs 실전투자

```python
# URL 차이
VIRTUAL_URL = "https://openapivts.koreainvestment.com:29443"
REAL_URL = "https://openapi.koreainvestment.com:9443"

# 헤더 차이
# 모의투자: tr_id에 "V" 접두사 (예: VTTC0802U)
# 실전투자: tr_id 그대로 (예: TTTC0802U)
```

### 에러 코드

| 코드 | 의미 | 대응 |
|------|------|------|
| 401 | 인증 실패 | 토큰 재발급 |
| 429 | 요청 한도 초과 | 1초 대기 후 재시도 |
| 500 | 서버 오류 | 최대 3회 재시도 |
| APBK1027 | 영업일 아님 | 스킵 |
| APBK1028 | 장 시작 전 | 대기 |

## pykrx 사용 규칙

### KOSPI200 유니버스 조회
```python
from pykrx import stock

# 구성종목 조회 (거래일 기준)
tickers = stock.get_index_portfolio_deposit_file("1028")  # KOSPI200

# 시가총액 조회
marcap = stock.get_market_cap_by_ticker(date)

# 주의: 공휴일에는 데이터 없음
# 해결: 최대 7일 전까지 거래일 탐색
```

### 거래일 탐색 로직
```python
from datetime import datetime, timedelta

def find_trading_date(target_date, max_days=7):
    for i in range(max_days):
        check_date = target_date - timedelta(days=i)
        date_str = check_date.strftime("%Y%m%d")
        marcap = stock.get_market_cap_by_ticker(date_str)
        if not marcap.empty:
            return date_str
    return None
```

## WebSocket 규칙

### 연결 관리
```python
# 최대 구독 종목: 100개
# 연결 유지: 30초마다 ping
# 재연결: 연결 끊김 시 5초 후 자동 재연결
```

### 구독 데이터 형식
```python
{
    "stock_code": "005930",
    "current_price": 70000,
    "change_rate": 1.23,
    "volume": 1234567,
    "timestamp": "2024-12-26T09:30:00"
}
```

## API 호출 패턴

### 배치 처리
```python
# 200개 종목 데이터 수집 시
# - 20개씩 배치 처리
# - 배치 간 0.5초 대기
# - 진행률 콜백 제공

for i in range(0, len(stocks), 20):
    batch = stocks[i:i+20]
    for stock in batch:
        data = client.get_price(stock)
    time.sleep(0.5)
    progress_callback(i + 20, len(stocks))
```

### 재시도 로직
```python
def api_call_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except RateLimitError:
            time.sleep(1)
        except AuthError:
            refresh_token()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))
```
